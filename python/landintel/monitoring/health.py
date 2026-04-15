from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, selectinload

from landintel.domain.enums import ModelReleaseStatus
from landintel.domain.models import (
    ActiveReleaseScope,
    AssessmentRun,
    BoroughBaselinePack,
    ModelRelease,
    SiteCandidate,
    SourceCoverageSnapshot,
    ValuationResult,
    ValuationRun,
)


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

    return {
        "status": status,
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
    return {
        "status": status,
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
