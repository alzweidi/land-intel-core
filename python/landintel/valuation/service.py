from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from landintel.domain.models import (
    AssessmentRun,
    AuditEvent,
    ValuationAssumptionSet,
    ValuationResult,
    ValuationRun,
)
from landintel.valuation.assumptions import resolve_active_assumption_set
from landintel.valuation.market import build_land_comp_summary, build_sales_comp_summary
from landintel.valuation.quality import (
    derive_valuation_quality,
    evaluate_divergence,
    widen_range_for_divergence,
)
from landintel.valuation.residual import canonical_payload_hash, compute_residual_valuation

VALUATION_NAMESPACE = uuid.UUID("7a93524d-3fd6-4f0d-a0ff-bdd2bc5e8ab6")


class ValuationBuildError(ValueError):
    pass


def build_or_refresh_valuation_for_assessment(
    *,
    session: Session,
    assessment_run: AssessmentRun,
    requested_by: str | None,
) -> ValuationRun:
    if assessment_run.feature_snapshot is None or assessment_run.result is None:
        raise ValuationBuildError("Assessment run must have frozen features and a result first.")

    assumption_set = resolve_active_assumption_set(
        session,
        as_of_date=assessment_run.as_of_date,
    )
    input_hash = _valuation_input_hash(
        assessment_run=assessment_run,
        assumption_set=assumption_set,
    )
    run = _get_or_create_run(
        session=session,
        assessment_run=assessment_run,
        assumption_set=assumption_set,
        input_hash=input_hash,
    )
    if run.state.value == "READY" and run.result is not None and run.input_hash == input_hash:
        return run

    run.state = run.state.__class__.PENDING
    run.input_hash = input_hash
    run.error_text = None
    run.finished_at = None
    session.flush()

    try:
        discount_json = dict(assumption_set.discount_json or {})
        sales_summary = build_sales_comp_summary(
            session=session,
            borough_id=assessment_run.site.borough_id,
            as_of_date=assessment_run.as_of_date,
            max_age_months=int(discount_json.get("market_comp_max_age_months") or 36),
        )
        land_summary = build_land_comp_summary(
            session=session,
            borough_id=assessment_run.site.borough_id,
            template_key=assessment_run.scenario.template_key,
            proposal_form=assessment_run.scenario.proposal_form,
            as_of_date=assessment_run.as_of_date,
        )
        residual = compute_residual_valuation(
            site=assessment_run.site,
            scenario=assessment_run.scenario,
            assumption_set=assumption_set,
            price_per_sqm_low=sales_summary.price_per_sqm_low,
            price_per_sqm_mid=sales_summary.price_per_sqm_mid,
            price_per_sqm_high=sales_summary.price_per_sqm_high,
        )

        divergence_material = evaluate_divergence(
            primary_mid=residual.post_permission_value_mid,
            secondary_mid=land_summary.post_permission_value_mid,
            threshold_pct=float(discount_json.get("sense_check_material_divergence_pct") or 0.2),
            threshold_abs_gbp=float(
                discount_json.get("sense_check_material_divergence_gbp") or 250000.0
            ),
        )
        final_low, final_mid, final_high = residual_values = (
            residual.post_permission_value_low,
            residual.post_permission_value_mid,
            residual.post_permission_value_high,
        )
        if divergence_material:
            final_low, final_mid, final_high = widen_range_for_divergence(
                primary_low=residual.post_permission_value_low,
                primary_mid=residual.post_permission_value_mid,
                primary_high=residual.post_permission_value_high,
                secondary_low=land_summary.post_permission_value_low,
                secondary_mid=land_summary.post_permission_value_mid,
                secondary_high=land_summary.post_permission_value_high,
            )

        basis_price = residual.basis_json.get("basis_price_gbp")
        uplift_low = (
            None
            if basis_price is None or final_low is None
            else round(final_low - float(basis_price), 2)
        )
        uplift_mid = (
            None
            if basis_price is None or final_mid is None
            else round(final_mid - float(basis_price), 2)
        )
        uplift_high = (
            None
            if basis_price is None or final_high is None
            else round(final_high - float(basis_price), 2)
        )
        expected_uplift_mid = (
            None
            if uplift_mid is None or assessment_run.result.approval_probability_raw is None
            else round(float(assessment_run.result.approval_probability_raw) * uplift_mid, 2)
        )

        policy_inputs_known = assessment_run.site.borough_id is not None
        scenario_area_stable = (
            not assessment_run.scenario.manual_review_required
            and not bool(assessment_run.scenario.stale_reason)
        )
        quality = derive_valuation_quality(
            asking_price_present=bool(residual.basis_json.get("basis_available")),
            sales_comp_count=sales_summary.count,
            land_comp_count=land_summary.count,
            policy_inputs_known=policy_inputs_known,
            scenario_area_stable=scenario_area_stable,
            divergence_material=divergence_material,
        )

        sense_check_json = {
            "fallback_path": land_summary.fallback_path,
            "count": land_summary.count,
            "post_permission_value_low": land_summary.post_permission_value_low,
            "post_permission_value_mid": land_summary.post_permission_value_mid,
            "post_permission_value_high": land_summary.post_permission_value_high,
            "divergence_material": divergence_material,
            "threshold_pct": float(discount_json.get("sense_check_material_divergence_pct") or 0.2),
            "threshold_abs_gbp": float(
                discount_json.get("sense_check_material_divergence_gbp") or 250000.0
            ),
            "source_snapshot_ids": sorted(land_summary.source_snapshot_ids),
            "raw_asset_ids": sorted(land_summary.raw_asset_ids),
        }
        result_json = {
            **dict(residual.result_json or {}),
            "sales_comp_summary": {
                "count": sales_summary.count,
                "price_per_sqm_low": sales_summary.price_per_sqm_low,
                "price_per_sqm_mid": sales_summary.price_per_sqm_mid,
                "price_per_sqm_high": sales_summary.price_per_sqm_high,
                "source_snapshot_ids": sorted(sales_summary.source_snapshot_ids),
                "raw_asset_ids": sorted(sales_summary.raw_asset_ids),
            },
            "sense_check_summary": sense_check_json,
            "divergence_widened": divergence_material
            and residual_values != (final_low, final_mid, final_high),
            "quality_reasons": quality.reasons,
            "assumption_version": assumption_set.version,
        }
        payload_hash = canonical_payload_hash(
            {
                "assessment_run_id": str(assessment_run.id),
                "valuation_assumption_set_id": str(assumption_set.id),
                "post_permission_value_low": final_low,
                "post_permission_value_mid": final_mid,
                "post_permission_value_high": final_high,
                "uplift_low": uplift_low,
                "uplift_mid": uplift_mid,
                "uplift_high": uplift_high,
                "expected_uplift_mid": expected_uplift_mid,
                "valuation_quality": quality.valuation_quality.value,
                "manual_review_required": quality.manual_review_required,
                "basis_json": residual.basis_json,
                "sense_check_json": sense_check_json,
                "result_json": result_json,
            }
        )
        result = run.result or ValuationResult(valuation_run_id=run.id)
        result.post_permission_value_low = final_low
        result.post_permission_value_mid = final_mid
        result.post_permission_value_high = final_high
        result.uplift_low = uplift_low
        result.uplift_mid = uplift_mid
        result.uplift_high = uplift_high
        result.expected_uplift_mid = expected_uplift_mid
        result.valuation_quality = quality.valuation_quality
        result.manual_review_required = quality.manual_review_required
        result.basis_json = dict(residual.basis_json)
        result.sense_check_json = sense_check_json
        result.result_json = result_json
        result.payload_hash = payload_hash
        session.add(result)
        run.result = result

        run.state = run.state.__class__.READY
        run.finished_at = datetime.now(UTC)
        run.error_text = None
        session.add(
            AuditEvent(
                action="valuation_run_built",
                entity_type="valuation_run",
                entity_id=str(run.id),
                before_json=None,
                after_json={
                    "assessment_run_id": str(assessment_run.id),
                    "valuation_assumption_set_id": str(assumption_set.id),
                    "requested_by": requested_by,
                    "payload_hash": payload_hash,
                },
            )
        )
        session.flush()
        return run
    except Exception as exc:
        run.state = run.state.__class__.FAILED
        run.finished_at = datetime.now(UTC)
        run.error_text = str(exc)
        session.flush()
        raise


def latest_valuation_run(assessment_run: AssessmentRun) -> ValuationRun | None:
    if not assessment_run.valuation_runs:
        return None
    return sorted(
        assessment_run.valuation_runs,
        key=lambda row: (row.created_at, str(row.id)),
        reverse=True,
    )[0]


def _get_or_create_run(
    *,
    session: Session,
    assessment_run: AssessmentRun,
    assumption_set: ValuationAssumptionSet,
    input_hash: str,
) -> ValuationRun:
    existing = next(
        (
            row
            for row in assessment_run.valuation_runs
            if row.valuation_assumption_set_id == assumption_set.id
        ),
        None,
    )
    if existing is not None:
        existing.input_hash = input_hash
        return existing

    run = ValuationRun(
        id=uuid.uuid5(VALUATION_NAMESPACE, f"{assessment_run.id}:{assumption_set.id}"),
        assessment_run_id=assessment_run.id,
        valuation_assumption_set_id=assumption_set.id,
        input_hash=input_hash,
    )
    session.add(run)
    session.flush()
    return run


def _valuation_input_hash(
    *,
    assessment_run: AssessmentRun,
    assumption_set: ValuationAssumptionSet,
) -> str:
    feature_hash = (
        None
        if assessment_run.feature_snapshot is None
        else assessment_run.feature_snapshot.feature_hash
    )
    return canonical_payload_hash(
        {
            "assessment_run_id": str(assessment_run.id),
            "feature_hash": feature_hash,
            "scenario_id": str(assessment_run.scenario_id),
            "scenario_geom_hash": assessment_run.scenario.red_line_geom_hash,
            "current_price_gbp": assessment_run.site.current_price_gbp,
            "current_price_basis_type": assessment_run.site.current_price_basis_type.value
            if assessment_run.site.current_price_basis_type
            else None,
            "approval_probability_raw": assessment_run.result.approval_probability_raw,
            "valuation_assumption_set_id": str(assumption_set.id),
            "valuation_assumption_set_version": assumption_set.version,
            "cost_json": assumption_set.cost_json,
            "policy_burden_json": assumption_set.policy_burden_json,
            "discount_json": assumption_set.discount_json,
        }
    )
