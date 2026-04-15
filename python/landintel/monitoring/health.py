from __future__ import annotations

from collections import defaultdict

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, selectinload

from landintel.domain.enums import (
    AssessmentOverrideType,
    EligibilityStatus,
    JobStatus,
    JobType,
    ModelReleaseStatus,
    SourceParseStatus,
)
from landintel.domain.models import (
    ActiveReleaseScope,
    AssessmentOverride,
    AssessmentResult,
    AssessmentRun,
    BoroughBaselinePack,
    JobRun,
    ModelRelease,
    SiteCandidate,
    SourceCoverageSnapshot,
    SourceSnapshot,
    ValuationResult,
    ValuationRun,
)
from landintel.monitoring.metrics import update_valuation_metrics
from landintel.planning.extant_permission import evaluate_site_extant_permission


def database_ready(session_factory) -> bool:
    try:
        with session_factory() as session:
            session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def build_data_health(session: Session) -> dict[str, object]:
    coverage_rows = session.execute(
        select(SourceCoverageSnapshot).order_by(SourceCoverageSnapshot.captured_at.desc())
    ).scalars().all()
    latest: dict[tuple[str, str], SourceCoverageSnapshot] = {}
    for row in coverage_rows:
        latest.setdefault((row.borough_id, row.source_family), row)

    baseline_packs = session.execute(
        select(BoroughBaselinePack)
        .options(selectinload(BoroughBaselinePack.rulepacks))
        .order_by(BoroughBaselinePack.created_at.desc())
    ).scalars().all()
    status = "ok"
    if any(row.coverage_status.value != "COMPLETE" for row in latest.values()):
        status = "warning"
    valuation_metrics = _build_valuation_metrics(session)
    update_valuation_metrics(valuation_metrics)
    connector_failure_rate = _connector_failure_rate(session)
    listing_parse_success = _listing_parse_success_rate(session)
    geometry_distribution = _geometry_confidence_distribution(session)
    extant_unresolved = _extant_unresolved_rate(session)
    baseline_coverage = _baseline_coverage_summary(baseline_packs)

    return {
        "status": status,
        "connector_failure_rate": connector_failure_rate,
        "listing_parse_success_rate": listing_parse_success,
        "geometry_confidence_distribution": geometry_distribution,
        "extant_permission_unresolved_rate": extant_unresolved,
        "borough_baseline_coverage": baseline_coverage,
        "coverage": [
            {
                "borough_id": row.borough_id,
                "source_family": row.source_family,
                "coverage_status": row.coverage_status.value,
                "gap_reason": row.gap_reason,
                "freshness_status": row.freshness_status.value,
                "coverage_note": row.coverage_note,
                "source_snapshot_id": (
                    str(row.source_snapshot_id) if row.source_snapshot_id else None
                ),
                "captured_at": row.captured_at.isoformat(),
            }
            for row in latest.values()
        ],
        "baseline_packs": [
            {
                "borough_id": pack.borough_id,
                "version": pack.version,
                "status": pack.status.value,
                "freshness_status": pack.freshness_status.value,
                "signed_off_by": pack.signed_off_by,
                "signed_off_at": pack.signed_off_at.isoformat() if pack.signed_off_at else None,
                "rulepacks": [
                    {
                        "template_key": rule.template_key,
                        "status": rule.status.value,
                        "freshness_status": rule.freshness_status.value,
                        "source_snapshot_id": (
                            str(rule.source_snapshot_id) if rule.source_snapshot_id else None
                        ),
                    }
                    for rule in pack.rulepacks
                ],
            }
            for pack in baseline_packs
        ],
        "valuation_metrics": valuation_metrics,
    }


def build_model_health(session: Session) -> dict[str, object]:
    releases = session.execute(
        select(ModelRelease)
        .options(selectinload(ModelRelease.active_scopes))
        .order_by(ModelRelease.created_at.desc())
    ).scalars().all()
    active_scopes = session.execute(
        select(ActiveReleaseScope)
        .options(selectinload(ActiveReleaseScope.model_release))
        .order_by(ActiveReleaseScope.scope_key.asc())
    ).scalars().all()
    status = "ok"
    if any(release.status == ModelReleaseStatus.NOT_READY for release in releases):
        status = "warning"
    assessment_metrics = _assessment_model_metrics(session)
    economic_health = _build_valuation_metrics(session)
    return {
        "status": status,
        "calibration_by_probability_band": assessment_metrics["calibration_by_probability_band"],
        "brier_score": assessment_metrics["brier_score"],
        "log_loss": assessment_metrics["log_loss"],
        "manual_review_agreement_by_band": assessment_metrics["manual_review_agreement_by_band"],
        "false_positive_reviewer_rate": assessment_metrics["false_positive_reviewer_rate"],
        "abstain_rate": assessment_metrics["abstain_rate"],
        "ood_rate": assessment_metrics["ood_rate"],
        "template_level_performance": assessment_metrics["template_level_performance"],
        "economic_health": {
            **economic_health,
            "realized_backtests": None,
        },
        "releases": [
            {
                "id": str(release.id),
                "template_key": release.template_key,
                "scope_key": release.scope_key,
                "status": release.status.value,
                "support_count": release.support_count,
                "positive_count": release.positive_count,
                "negative_count": release.negative_count,
                "reason_text": release.reason_text,
                "model_kind": release.model_kind,
                "created_at": release.created_at.isoformat(),
                "activated_at": (
                    None if release.activated_at is None else release.activated_at.isoformat()
                ),
            }
            for release in releases
        ],
        "active_scopes": [
            {
                "scope_key": scope.scope_key,
                "template_key": scope.template_key,
                "model_release_id": str(scope.model_release_id),
                "activated_at": scope.activated_at.isoformat(),
                "visibility_mode": scope.visibility_mode.value,
                "visibility_reason": scope.visibility_reason,
            }
            for scope in active_scopes
        ],
    }


def _build_valuation_metrics(session: Session) -> dict[str, object]:
    valuation_rows = session.execute(
        select(ValuationResult)
        .join(ValuationRun, ValuationRun.id == ValuationResult.valuation_run_id)
        .join(AssessmentRun, AssessmentRun.id == ValuationRun.assessment_run_id)
        .join(SiteCandidate, SiteCandidate.id == AssessmentRun.site_id)
    ).scalars().all()
    total = len(valuation_rows)
    if total == 0:
        return {
            "total": 0,
            "uplift_null_rate": None,
            "asking_price_missing_rate": None,
            "valuation_quality_distribution": {},
        }

    uplift_null_count = sum(1 for row in valuation_rows if row.uplift_mid is None)
    asking_price_missing_count = session.execute(
        select(func.count())
        .select_from(AssessmentRun)
        .join(ValuationRun, ValuationRun.assessment_run_id == AssessmentRun.id)
        .join(SiteCandidate, SiteCandidate.id == AssessmentRun.site_id)
        .where(SiteCandidate.current_price_gbp.is_(None))
    ).scalar_one()
    quality_distribution: dict[str, int] = {}
    for row in valuation_rows:
        quality_distribution[row.valuation_quality.value] = (
            quality_distribution.get(row.valuation_quality.value, 0) + 1
        )
    return {
        "total": total,
        "uplift_null_rate": round(uplift_null_count / total, 4),
        "asking_price_missing_rate": round(asking_price_missing_count / total, 4),
        "valuation_quality_distribution": quality_distribution,
    }


def _connector_failure_rate(session: Session) -> float | None:
    connector_types = [
        JobType.MANUAL_URL_SNAPSHOT,
        JobType.CSV_IMPORT_SNAPSHOT,
        JobType.LISTING_SOURCE_RUN,
    ]
    total = session.execute(
        select(func.count()).select_from(JobRun).where(JobRun.job_type.in_(connector_types))
    ).scalar_one()
    if total == 0:
        return None
    failed = session.execute(
        select(func.count())
        .select_from(JobRun)
        .where(JobRun.job_type.in_(connector_types))
        .where(JobRun.status.in_([JobStatus.FAILED, JobStatus.DEAD]))
    ).scalar_one()
    return round(failed / total, 4)


def _listing_parse_success_rate(session: Session) -> float | None:
    total = session.execute(select(func.count()).select_from(SourceSnapshot)).scalar_one()
    if total == 0:
        return None
    successful = session.execute(
        select(func.count())
        .select_from(SourceSnapshot)
        .where(
            SourceSnapshot.parse_status.in_(
                [SourceParseStatus.PARSED, SourceParseStatus.PARTIAL]
            )
        )
    ).scalar_one()
    return round(successful / total, 4)


def _geometry_confidence_distribution(session: Session) -> dict[str, int]:
    rows = session.execute(
        select(SiteCandidate.geom_confidence, func.count()).group_by(SiteCandidate.geom_confidence)
    ).all()
    return {row[0].value: int(row[1]) for row in rows}


def _extant_unresolved_rate(session: Session) -> float | None:
    sites = session.execute(select(SiteCandidate)).scalars().all()
    if not sites:
        return None
    unresolved = 0
    for site in sites:
        evaluation = evaluate_site_extant_permission(session=session, site=site)
        if evaluation.status.value in {
            "UNRESOLVED_MISSING_MANDATORY_SOURCE",
            "CONTRADICTORY_SOURCE_MANUAL_REVIEW",
            "NON_MATERIAL_OVERLAP_MANUAL_REVIEW",
        }:
            unresolved += 1
    return round(unresolved / len(sites), 4)


def _baseline_coverage_summary(baseline_packs: list[BoroughBaselinePack]) -> dict[str, object]:
    total = len(baseline_packs)
    signed_off = sum(1 for pack in baseline_packs if pack.status.value == "SIGNED_OFF")
    pilot_ready = sum(1 for pack in baseline_packs if pack.status.value == "PILOT_READY")
    return {
        "total": total,
        "signed_off": signed_off,
        "pilot_ready": pilot_ready,
    }


def _assessment_model_metrics(session: Session) -> dict[str, object]:
    results = (
        session.execute(
            select(AssessmentResult)
            .join(AssessmentRun, AssessmentRun.id == AssessmentResult.assessment_run_id)
            .options(selectinload(AssessmentResult.assessment_run))
        )
        .scalars()
        .all()
    )
    scored = [row for row in results if row.approval_probability_raw is not None]
    calibration_by_band = []
    brier_scores = []
    log_losses = []
    template_metrics: dict[str, dict[str, object]] = {}
    band_review: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "completed": 0})
    reviewer_overrides = (
        session.execute(
            select(AssessmentOverride).where(
                AssessmentOverride.override_type == AssessmentOverrideType.REVIEW_DISPOSITION
            )
        )
        .scalars()
        .all()
    )
    reviewer_override_by_run = {
        row.assessment_run_id: row
        for row in sorted(reviewer_overrides, key=lambda item: item.created_at, reverse=True)
        if row.status.value == "ACTIVE"
    }
    false_positive_denominator = 0
    false_positive_numerator = 0
    abstain_count = sum(1 for row in results if row.eligibility_status == EligibilityStatus.ABSTAIN)
    ood_count = sum(1 for row in scored if (row.ood_status or "") != "IN_SUPPORT")

    for row in scored:
        template_key = row.assessment_run.scenario.template_key
        metrics = template_metrics.setdefault(
            template_key,
            {"count": 0, "brier_scores": [], "log_losses": [], "ood_count": 0},
        )
        validation_metrics = dict(
            (row.result_json or {}).get("validation_summary", {}).get("metrics") or {}
        )
        if validation_metrics.get("brier_score") is not None:
            brier_scores.append(float(validation_metrics["brier_score"]))
            metrics["brier_scores"].append(float(validation_metrics["brier_score"]))
        if validation_metrics.get("log_loss") is not None:
            log_losses.append(float(validation_metrics["log_loss"]))
            metrics["log_losses"].append(float(validation_metrics["log_loss"]))
        if row.ood_status and row.ood_status != "IN_SUPPORT":
            metrics["ood_count"] += 1
        metrics["count"] += 1

        for band_row in list(validation_metrics.get("calibration_by_band") or []):
            calibration_by_band.append(
                {
                    "template_key": template_key,
                    **band_row,
                }
            )

        display_band = row.approval_probability_display or "UNKNOWN"
        band_review[display_band]["total"] += 1
        review_override = reviewer_override_by_run.get(row.assessment_run_id)
        if review_override is not None and bool(
            review_override.override_json.get("resolve_manual_review")
        ):
            band_review[display_band]["completed"] += 1
            if row.manual_review_required:
                false_positive_denominator += 1
                false_positive_numerator += 1
        elif row.manual_review_required:
            false_positive_denominator += 1

    template_level_performance = []
    for template_key, metrics in sorted(template_metrics.items()):
        count = int(metrics["count"])
        template_level_performance.append(
            {
                "template_key": template_key,
                "count": count,
                "brier_score": None
                if not metrics["brier_scores"]
                else round(sum(metrics["brier_scores"]) / len(metrics["brier_scores"]), 6),
                "log_loss": None
                if not metrics["log_losses"]
                else round(sum(metrics["log_losses"]) / len(metrics["log_losses"]), 6),
                "ood_rate": None
                if count == 0
                else round(int(metrics["ood_count"]) / count, 4),
            }
        )

    return {
        "calibration_by_probability_band": calibration_by_band,
        "brier_score": (
            None
            if not brier_scores
            else round(sum(brier_scores) / len(brier_scores), 6)
        ),
        "log_loss": None if not log_losses else round(sum(log_losses) / len(log_losses), 6),
        "manual_review_agreement_by_band": [
            {
                "band": band,
                "total": counts["total"],
                "completed": counts["completed"],
                "agreement_rate": None
                if counts["total"] == 0
                else round(counts["completed"] / counts["total"], 4),
            }
            for band, counts in sorted(band_review.items())
        ],
        "false_positive_reviewer_rate": None
        if false_positive_denominator == 0
        else round(false_positive_numerator / false_positive_denominator, 4),
        "abstain_rate": None if not results else round(abstain_count / len(results), 4),
        "ood_rate": None if not scored else round(ood_count / len(scored), 4),
        "template_level_performance": template_level_performance,
    }
