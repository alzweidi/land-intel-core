from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from landintel.domain.enums import (
    AppRoleName,
    AssessmentOverrideStatus,
    AssessmentOverrideType,
    PriceBasisType,
    ReviewStatus,
)
from landintel.domain.models import (
    AssessmentOverride,
    AssessmentRun,
    AuditEvent,
    ValuationAssumptionSet,
    ValuationRun,
)
from landintel.domain.schemas import (
    AssessmentOverrideRead,
    AssessmentOverrideRequest,
    AssessmentOverrideSummaryRead,
    ValuationResultRead,
)
from landintel.review.visibility import ReviewAccessError, require_role
from landintel.valuation.service import (
    build_or_refresh_valuation_for_assessment_with_assumption_set,
    latest_valuation_run,
)


def apply_assessment_override(
    *,
    session: Session,
    assessment_id: UUID,
    request: AssessmentOverrideRequest,
) -> AssessmentRun:
    run = session.execute(
        select(AssessmentRun)
        .where(AssessmentRun.id == assessment_id)
        .options(
            selectinload(AssessmentRun.result),
            selectinload(AssessmentRun.valuation_runs).selectinload(ValuationRun.result),
            selectinload(AssessmentRun.valuation_runs).selectinload(
                ValuationRun.valuation_assumption_set
            ),
            selectinload(AssessmentRun.overrides),
        )
    ).scalar_one_or_none()
    if run is None:
        raise ReviewAccessError(f"Assessment '{assessment_id}' was not found.")

    actor_role = _validate_override_role(request)
    actor_name = request.requested_by or "api-override"
    override_json, valuation_run = _build_override_payload(
        session=session,
        run=run,
        request=request,
        actor_name=actor_name,
    )

    active_prior = [
        row
        for row in run.overrides
        if row.override_type == request.override_type
        and row.status == AssessmentOverrideStatus.ACTIVE
    ]
    latest_prior = active_prior[0] if active_prior else None
    for row in active_prior:
        row.status = AssessmentOverrideStatus.SUPERSEDED
        row.resolved_by = actor_name
        row.resolved_at = datetime.now(UTC)

    override = AssessmentOverride(
        assessment_run_id=run.id,
        assessment_result_id=None if run.result is None else run.result.id,
        valuation_run_id=None if valuation_run is None else valuation_run.id,
        override_type=request.override_type,
        status=AssessmentOverrideStatus.ACTIVE,
        actor_name=actor_name,
        actor_role=actor_role,
        reason=request.reason,
        override_json=override_json,
        supersedes_id=None if latest_prior is None else latest_prior.id,
    )
    session.add(override)
    session.add(
        AuditEvent(
            action="assessment_override_created",
            entity_type="assessment_run",
            entity_id=str(run.id),
            before_json={
                "active_override_ids": [str(row.id) for row in active_prior],
            },
            after_json={
                "override_id": str(override.id),
                "override_type": override.override_type.value,
                "actor_name": actor_name,
                "actor_role": actor_role.value,
                "reason": request.reason,
                "override_json": override_json,
            },
        )
    )
    session.flush()
    return run


def build_override_summary(
    *,
    session: Session,
    assessment_run: AssessmentRun,
) -> AssessmentOverrideSummaryRead | None:
    active_overrides = [
        row
        for row in sorted(
            assessment_run.overrides,
            key=lambda item: (item.created_at, str(item.id)),
            reverse=True,
        )
        if row.status == AssessmentOverrideStatus.ACTIVE
    ]
    if not active_overrides:
        return None

    by_type = {row.override_type: row for row in active_overrides}
    effective_review_status = (
        None if assessment_run.result is None else assessment_run.result.review_status
    )
    effective_manual_review_required = (
        None if assessment_run.result is None else assessment_run.result.manual_review_required
    )
    ranking_suppressed = False
    display_block_reason = None

    review_override = by_type.get(AssessmentOverrideType.REVIEW_DISPOSITION)
    if review_override is not None and bool(
        review_override.override_json.get("resolve_manual_review")
    ):
        effective_review_status = ReviewStatus.COMPLETED
        effective_manual_review_required = False

    ranking_override = by_type.get(AssessmentOverrideType.RANKING_SUPPRESSION)
    if ranking_override is not None:
        ranking_suppressed = bool(ranking_override.override_json.get("ranking_suppressed"))
        display_block_reason = _text_or_none(
            ranking_override.override_json.get("display_block_reason")
        )

    effective_valuation_run = _resolve_effective_valuation_run(
        session=session,
        assessment_run=assessment_run,
        assumption_override=by_type.get(AssessmentOverrideType.VALUATION_ASSUMPTION_SET),
    )
    effective_valuation = _serialize_effective_valuation(
        assessment_run=assessment_run,
        valuation_run=effective_valuation_run,
        basis_override=by_type.get(AssessmentOverrideType.ACQUISITION_BASIS),
    )

    return AssessmentOverrideSummaryRead(
        active_overrides=[_serialize_override(row) for row in active_overrides],
        effective_review_status=effective_review_status,
        effective_manual_review_required=effective_manual_review_required,
        ranking_suppressed=ranking_suppressed,
        display_block_reason=display_block_reason,
        effective_valuation=effective_valuation,
    )


def _validate_override_role(request: AssessmentOverrideRequest) -> AppRoleName:
    if request.override_type in {
        AssessmentOverrideType.ACQUISITION_BASIS,
        AssessmentOverrideType.VALUATION_ASSUMPTION_SET,
    }:
        return require_role(
            request.actor_role,
            allowed_roles={AppRoleName.ANALYST, AppRoleName.REVIEWER, AppRoleName.ADMIN},
        )
    if request.override_type == AssessmentOverrideType.REVIEW_DISPOSITION:
        return require_role(
            request.actor_role,
            allowed_roles={AppRoleName.REVIEWER, AppRoleName.ADMIN},
        )
    return require_role(request.actor_role, allowed_roles={AppRoleName.ADMIN})


def _build_override_payload(
    *,
    session: Session,
    run: AssessmentRun,
    request: AssessmentOverrideRequest,
    actor_name: str,
) -> tuple[dict[str, object], ValuationRun | None]:
    if request.override_type == AssessmentOverrideType.ACQUISITION_BASIS:
        if request.acquisition_basis_gbp is None:
            raise ReviewAccessError("Acquisition-basis override requires acquisition_basis_gbp.")
        basis_type = request.acquisition_basis_type or PriceBasisType.GUIDE_PRICE
        return (
            {
                "acquisition_basis_gbp": round(float(request.acquisition_basis_gbp), 2),
                "acquisition_basis_type": basis_type.value,
            },
            None,
        )

    if request.override_type == AssessmentOverrideType.VALUATION_ASSUMPTION_SET:
        if request.valuation_assumption_set_id is None:
            raise ReviewAccessError(
                "Valuation-assumption override requires valuation_assumption_set_id."
            )
        assumption_set = session.get(ValuationAssumptionSet, request.valuation_assumption_set_id)
        if assumption_set is None:
            raise ReviewAccessError(
                f"Valuation assumption set '{request.valuation_assumption_set_id}' was not found."
            )
        valuation_run = build_or_refresh_valuation_for_assessment_with_assumption_set(
            session=session,
            assessment_run=run,
            valuation_assumption_set=assumption_set,
            requested_by=actor_name,
        )
        return (
            {
                "valuation_assumption_set_id": str(assumption_set.id),
                "valuation_assumption_version": assumption_set.version,
                "valuation_run_id": str(valuation_run.id),
            },
            valuation_run,
        )

    if request.override_type == AssessmentOverrideType.REVIEW_DISPOSITION:
        return (
            {
                "review_resolution_note": request.review_resolution_note,
                "resolve_manual_review": bool(request.resolve_manual_review),
            },
            None,
        )

    return (
        {
            "ranking_suppressed": bool(request.ranking_suppressed),
            "display_block_reason": request.display_block_reason,
        },
        None,
    )


def _resolve_effective_valuation_run(
    *,
    session: Session,
    assessment_run: AssessmentRun,
    assumption_override: AssessmentOverride | None,
) -> ValuationRun | None:
    if assumption_override is not None:
        run_id = assumption_override.override_json.get("valuation_run_id")
        if isinstance(run_id, str):
            run = next(
                (
                    row
                    for row in assessment_run.valuation_runs
                    if str(row.id) == run_id
                ),
                None,
            )
            if run is not None:
                return run
            return session.get(ValuationRun, UUID(run_id))
    return latest_valuation_run(assessment_run)


def _serialize_effective_valuation(
    *,
    assessment_run: AssessmentRun,
    valuation_run: ValuationRun | None,
    basis_override: AssessmentOverride | None,
) -> ValuationResultRead | None:
    if valuation_run is None or valuation_run.result is None:
        return None
    result = valuation_run.result
    basis_json = dict(result.basis_json or {})
    uplift_low = result.uplift_low
    uplift_mid = result.uplift_mid
    uplift_high = result.uplift_high
    expected_uplift_mid = result.expected_uplift_mid

    if basis_override is not None:
        basis_price = float(basis_override.override_json["acquisition_basis_gbp"])
        basis_type = str(
            basis_override.override_json.get("acquisition_basis_type")
            or PriceBasisType.GUIDE_PRICE.value
        )
        uplift_low = (
            None
            if result.post_permission_value_low is None
            else round(result.post_permission_value_low - basis_price, 2)
        )
        uplift_mid = (
            None
            if result.post_permission_value_mid is None
            else round(result.post_permission_value_mid - basis_price, 2)
        )
        uplift_high = (
            None
            if result.post_permission_value_high is None
            else round(result.post_permission_value_high - basis_price, 2)
        )
        expected_uplift_mid = (
            None
            if uplift_mid is None or assessment_run.result is None
            or assessment_run.result.approval_probability_raw is None
            else round(float(assessment_run.result.approval_probability_raw) * uplift_mid, 2)
        )
        basis_json = {
            **basis_json,
            "basis_available": True,
            "basis_price_gbp": basis_price,
            "basis_type": basis_type,
            "override_applied": True,
            "override_source": "assessment_override",
            "override_reason": basis_override.reason,
        }

    return ValuationResultRead(
        id=result.id,
        valuation_run_id=valuation_run.id,
        valuation_assumption_set_id=valuation_run.valuation_assumption_set_id,
        valuation_assumption_version=valuation_run.valuation_assumption_set.version,
        post_permission_value_low=result.post_permission_value_low,
        post_permission_value_mid=result.post_permission_value_mid,
        post_permission_value_high=result.post_permission_value_high,
        uplift_low=uplift_low,
        uplift_mid=uplift_mid,
        uplift_high=uplift_high,
        expected_uplift_mid=expected_uplift_mid,
        valuation_quality=result.valuation_quality,
        manual_review_required=result.manual_review_required,
        basis_json=basis_json,
        sense_check_json=dict(result.sense_check_json or {}),
        result_json=dict(result.result_json or {}),
        payload_hash=result.payload_hash,
        created_at=result.created_at,
    )


def _serialize_override(row: AssessmentOverride) -> AssessmentOverrideRead:
    return AssessmentOverrideRead(
        id=row.id,
        override_type=row.override_type,
        status=row.status,
        actor_name=row.actor_name,
        actor_role=row.actor_role,
        reason=row.reason,
        override_json=dict(row.override_json or {}),
        supersedes_id=row.supersedes_id,
        resolved_by=row.resolved_by,
        resolved_at=row.resolved_at,
        created_at=row.created_at,
    )


def _text_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
