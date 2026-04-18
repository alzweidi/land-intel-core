from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from landintel.domain.enums import (
    AppRoleName,
    AssessmentRunState,
    OpportunityBand,
    PriceBasisType,
    ValuationQuality,
)
from landintel.domain.models import (
    AssessmentRun,
    ComparableCaseMember,
    ComparableCaseSet,
    ListingItem,
    SiteCandidate,
    SiteScenario,
    ValuationRun,
)
from landintel.domain.schemas import (
    OpportunityDetailRead,
    OpportunityListResponse,
    OpportunitySummaryRead,
    ValuationResultRead,
)
from landintel.review.overrides import build_override_summary
from landintel.review.visibility import evaluate_assessment_visibility
from landintel.services.assessments_readback import serialize_assessment_detail
from landintel.services.scenarios_readback import serialize_site_scenario_summary
from landintel.services.sites_readback import serialize_site_summary
from landintel.valuation.ranking import derive_opportunity_band, ranking_sort_key
from landintel.valuation.service import frozen_valuation_run


def list_opportunities(
    session: Session,
    *,
    borough: str | None = None,
    probability_band: OpportunityBand | None = None,
    valuation_quality: ValuationQuality | None = None,
    manual_review_required: bool | None = None,
    auction_deadline_days: int | None = None,
    min_price: int | None = None,
    max_price: int | None = None,
    viewer_role: AppRoleName | str | None = AppRoleName.ANALYST,
    include_hidden: bool = False,
) -> OpportunityListResponse:
    runs = _latest_runs_by_site(session)
    today = date.today()
    items = [
        _serialize_opportunity_summary(
            session=session,
            run=run,
            viewer_role=viewer_role,
            include_hidden=include_hidden,
        )
        for run in runs
    ]
    filtered: list[OpportunitySummaryRead] = []
    for item in items:
        if borough and item.borough_id != borough:
            continue
        if probability_band and item.probability_band != probability_band:
            continue
        if valuation_quality and item.valuation_quality != valuation_quality:
            continue
        if (
            manual_review_required is not None
            and item.manual_review_required != manual_review_required
        ):
            continue
        if (
            min_price is not None
            and (item.asking_price_gbp is None or item.asking_price_gbp < min_price)
        ):
            continue
        if (
            max_price is not None
            and (item.asking_price_gbp is None or item.asking_price_gbp > max_price)
        ):
            continue
        if auction_deadline_days is not None:
            if item.auction_date is None:
                continue
            days_until = (item.auction_date - today).days
            if days_until < 0 or days_until > auction_deadline_days:
                continue
        filtered.append(item)

    filtered.sort(
        key=lambda item: ranking_sort_key(
            probability_band=item.probability_band,
            expected_uplift_mid=item.expected_uplift_mid,
            valuation_quality=item.valuation_quality,
            auction_date=item.auction_date,
            today=today,
            asking_price_present=item.asking_price_gbp is not None,
            same_borough_support_count=item.same_borough_support_count,
            display_name=item.display_name,
        )
    )
    return OpportunityListResponse(items=filtered, total=len(filtered))


def get_opportunity(
    session: Session,
    *,
    site_id: UUID,
    viewer_role: AppRoleName | str | None = AppRoleName.ANALYST,
    include_hidden: bool = False,
) -> OpportunityDetailRead | None:
    runs = _latest_runs_by_site(session)
    run = next((item for item in runs if item.site_id == site_id), None)
    if run is None:
        return None
    summary = _serialize_opportunity_summary(
        session=session,
        run=run,
        viewer_role=viewer_role,
        include_hidden=include_hidden,
    )
    valuation_run = frozen_valuation_run(run)
    override_summary = build_override_summary(session=session, assessment_run=run)
    effective_valuation = (
        override_summary.effective_valuation
        if override_summary is not None and override_summary.effective_valuation is not None
        else serialize_valuation_result(valuation_run)
    )
    if (
        effective_valuation is not None
        and not (
            summary.visibility is not None
            and (
                summary.visibility.hidden_probability_allowed
                or summary.visibility.visible_probability_allowed
            )
        )
    ):
        effective_valuation = effective_valuation.model_copy(update={"expected_uplift_mid": None})
    return OpportunityDetailRead(
        **summary.model_dump(),
        assessment=serialize_assessment_detail(
            session=session,
            run=run,
            include_hidden=include_hidden,
            viewer_role=viewer_role,
        ),
        valuation=(
            effective_valuation
            if effective_valuation is not None
            else serialize_valuation_result(valuation_run)
        ),
        ranking_factors=_ranking_factors(run, summary),
    )


def _latest_runs_by_site(session: Session) -> list[AssessmentRun]:
    rows = (
        session.execute(
            select(AssessmentRun)
            .where(AssessmentRun.state == AssessmentRunState.READY)
            .options(*_opportunity_load_options())
            .order_by(AssessmentRun.created_at.desc())
        )
        .scalars()
        .unique()
        .all()
    )
    latest: dict[UUID, AssessmentRun] = {}
    for row in rows:
        latest.setdefault(row.site_id, row)
    return list(latest.values())


def _serialize_opportunity_summary(
    *,
    session: Session,
    run: AssessmentRun,
    viewer_role: AppRoleName | str | None,
    include_hidden: bool,
) -> OpportunitySummaryRead:
    site = run.site
    scenario = run.scenario
    result = run.result
    visibility = evaluate_assessment_visibility(
        session=session,
        assessment_run=run,
        viewer_role=viewer_role,
        include_hidden=include_hidden,
    )
    ranking_visibility = evaluate_assessment_visibility(
        session=session,
        assessment_run=run,
        viewer_role=AppRoleName.REVIEWER,
        include_hidden=False,
    )
    override_summary = build_override_summary(session=session, assessment_run=run)
    valuation_run = frozen_valuation_run(run)
    effective_valuation = (
        override_summary.effective_valuation
        if override_summary is not None and override_summary.effective_valuation is not None
        else serialize_valuation_result(valuation_run)
    )
    if effective_valuation is not None and not (
        visibility.hidden_probability_allowed or visibility.visible_probability_allowed
    ):
        effective_valuation = effective_valuation.model_copy(update={"expected_uplift_mid": None})
    score_execution_status = (
        None
        if result is None
        else str((result.result_json or {}).get("score_execution_status") or "")
    )
    ranking_suppressed = bool(
        override_summary.ranking_suppressed if override_summary is not None else False
    )
    if result is not None and _ranking_output_blocked(run=run, visibility=ranking_visibility):
        band = OpportunityBand.HOLD
        hold_reason = (
            ranking_visibility.blocked_reason_text or "Visible planning band is blocked."
        )
    elif ranking_suppressed:
        band = OpportunityBand.HOLD
        hold_reason = (
            override_summary.display_block_reason
            if override_summary is not None
            else "Ranking is suppressed by an active override."
        )
    else:
        derived = derive_opportunity_band(
            eligibility_status=None if result is None else result.eligibility_status,
            approval_probability_raw=(
                None if result is None else result.approval_probability_raw
            ),
            estimate_quality=(
                None
                if result is None or result.estimate_quality is None
                else result.estimate_quality.value
            ),
            manual_review_required=bool(result.manual_review_required) if result else True,
            score_execution_status=score_execution_status or None,
        )
        band = derived.probability_band
        hold_reason = derived.hold_reason
    same_borough_support_count = _same_borough_support_count(run)
    ranking_reason = (
        f"{band.value}: {hold_reason}"
        if hold_reason
        else (
            "Planning band is set from hidden internal support. Within-band ordering uses "
            "expected uplift, valuation quality, urgency, asking-price presence, and "
            "same-borough support."
        )
    )
    return OpportunitySummaryRead(
        site_id=site.id,
        display_name=site.display_name,
        borough_id=site.borough_id,
        borough_name=site.borough.name if site.borough else None,
        assessment_id=run.id,
        scenario_id=scenario.id,
        probability_band=band,
        hold_reason=hold_reason,
        ranking_reason=ranking_reason,
        hidden_mode_only=not visibility.visible_probability_allowed,
        visibility=visibility,
        display_block_reason=(
            None if override_summary is None else override_summary.display_block_reason
        ),
        eligibility_status=None if result is None else result.eligibility_status,
        estimate_status=None if result is None else result.estimate_status,
        manual_review_required=(
            bool(
                override_summary.effective_manual_review_required
                if override_summary is not None
                and override_summary.effective_manual_review_required is not None
                else result.manual_review_required
            )
            or (
                effective_valuation.manual_review_required
                if effective_valuation is not None
                else False
            )
        )
        if result is not None
        else True,
        valuation_quality=(
            None if effective_valuation is None else effective_valuation.valuation_quality
        ),
        asking_price_gbp=site.current_price_gbp,
        asking_price_basis_type=(
            None
            if site.current_price_basis_type == PriceBasisType.UNKNOWN
            else site.current_price_basis_type
        ),
        auction_date=_current_auction_date(site.current_listing),
        post_permission_value_mid=(
            None if effective_valuation is None else effective_valuation.post_permission_value_mid
        ),
        uplift_mid=None if effective_valuation is None else effective_valuation.uplift_mid,
        expected_uplift_mid=(
            None if effective_valuation is None else effective_valuation.expected_uplift_mid
        ),
        same_borough_support_count=same_borough_support_count,
        site_summary=serialize_site_summary(site),
        scenario_summary=serialize_site_scenario_summary(
            session=session,
            scenario=scenario,
            baseline_pack=None,
            site=site,
        ),
    )


def _ranking_output_blocked(*, run: AssessmentRun, visibility) -> bool:
    if not visibility.blocked:
        return False
    return not (
        set(visibility.blocked_reason_codes or []) == {"REPLAY_FAILED"}
        and run.prediction_ledger is not None
        and run.prediction_ledger.replay_verification_status == "HASH_CAPTURED"
    )


def _same_borough_support_count(run: AssessmentRun) -> int:
    if run.result is None:
        return 0
    support_summary = dict((run.result.result_json or {}).get("support_summary") or {})
    return int(support_summary.get("same_borough_support_count") or 0)


def _current_auction_date(listing: ListingItem | None) -> date | None:
    if listing is None or not listing.snapshots:
        return None
    current = next(
        (row for row in listing.snapshots if row.id == listing.current_snapshot_id),
        None,
    )
    snapshot = current or listing.snapshots[0]
    return snapshot.auction_date


def _ranking_factors(
    run: AssessmentRun,
    summary: OpportunitySummaryRead,
) -> dict[str, object]:
    return {
        "probability_band": summary.probability_band.value,
        "hold_reason": summary.hold_reason,
        "expected_uplift_mid": summary.expected_uplift_mid,
        "valuation_quality": (
            None if summary.valuation_quality is None else summary.valuation_quality.value
        ),
        "auction_date": (
            None if summary.auction_date is None else summary.auction_date.isoformat()
        ),
        "asking_price_present": summary.asking_price_gbp is not None,
        "same_borough_support_count": summary.same_borough_support_count,
        "assessment_id": str(run.id),
    }


def serialize_valuation_result(
    valuation_run: ValuationRun | None,
) -> ValuationResultRead | None:
    if valuation_run is None or valuation_run.result is None:
        return None
    result = valuation_run.result
    return ValuationResultRead(
        id=result.id,
        valuation_run_id=valuation_run.id,
        valuation_assumption_set_id=valuation_run.valuation_assumption_set_id,
        valuation_assumption_version=valuation_run.valuation_assumption_set.version,
        post_permission_value_low=result.post_permission_value_low,
        post_permission_value_mid=result.post_permission_value_mid,
        post_permission_value_high=result.post_permission_value_high,
        uplift_low=result.uplift_low,
        uplift_mid=result.uplift_mid,
        uplift_high=result.uplift_high,
        expected_uplift_mid=result.expected_uplift_mid,
        valuation_quality=result.valuation_quality,
        manual_review_required=result.manual_review_required,
        basis_json=dict(result.basis_json or {}),
        sense_check_json=dict(result.sense_check_json or {}),
        result_json=dict(result.result_json or {}),
        payload_hash=result.payload_hash,
        created_at=result.created_at,
    )


def _opportunity_load_options():
    return (
        selectinload(AssessmentRun.site).selectinload(SiteCandidate.borough),
        selectinload(AssessmentRun.site).selectinload(SiteCandidate.listing_cluster),
        selectinload(AssessmentRun.site)
        .selectinload(SiteCandidate.current_listing)
        .selectinload(ListingItem.snapshots),
        selectinload(AssessmentRun.scenario).selectinload(SiteScenario.reviews),
        selectinload(AssessmentRun.result),
        selectinload(AssessmentRun.valuation_runs).selectinload(ValuationRun.result),
        selectinload(AssessmentRun.valuation_runs).selectinload(
            ValuationRun.valuation_assumption_set
        ),
        selectinload(AssessmentRun.comparable_case_set)
        .selectinload(ComparableCaseSet.members)
        .selectinload(ComparableCaseMember.planning_application),
        selectinload(AssessmentRun.feature_snapshot),
        selectinload(AssessmentRun.evidence_items),
        selectinload(AssessmentRun.prediction_ledger),
    )
