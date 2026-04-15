from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from landintel.domain.enums import GoldSetReviewStatus
from landintel.domain.schemas import (
    HistoricalLabelCaseRead,
    HistoricalLabelListResponse,
    HistoricalLabelReviewRequest,
    JobRunRead,
    ListingSourceRead,
    ModelReleaseActivateRequest,
    ModelReleaseDetailRead,
    ModelReleaseListResponse,
    ModelReleaseRebuildRequest,
    ModelReleaseRetireRequest,
    PlaceholderResponse,
    SourceSnapshotRead,
)
from landintel.jobs.service import enqueue_gold_set_refresh_job, list_jobs
from landintel.monitoring.health import build_data_health, build_model_health
from landintel.planning.historical_labels import (
    get_historical_label_case,
    rebuild_historical_case_labels,
    review_historical_label_case,
)
from landintel.scoring.release import (
    activate_model_release,
    build_hidden_model_releases,
    retire_model_release,
)
from landintel.services.assessments_readback import (
    get_gold_set_case_read,
    list_gold_set_cases_read,
)
from landintel.services.listings_readback import (
    get_source_snapshot,
    list_listing_sources,
    list_source_snapshots,
)
from landintel.services.model_releases_readback import (
    get_model_release_read,
    list_model_releases_read,
)
from landintel.storage.base import StorageAdapter
from sqlalchemy.orm import Session

from ..dependencies import get_db_session, get_storage_adapter

router = APIRouter(prefix="/api", tags=["admin"])


@router.get("/health/data")
def get_data_health(session: Session = Depends(get_db_session)) -> dict[str, object]:
    return build_data_health(session)


@router.get("/health/model")
def get_model_health(session: Session = Depends(get_db_session)) -> dict[str, object]:
    return build_model_health(session)


@router.get("/admin/jobs", response_model=list[JobRunRead])
def get_jobs(
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_db_session),
) -> list[JobRunRead]:
    return [JobRunRead.model_validate(job) for job in list_jobs(session=session, limit=limit)]


@router.get("/admin/source-snapshots", response_model=list[SourceSnapshotRead])
def get_source_snapshots(
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_db_session),
) -> list[SourceSnapshotRead]:
    return list_source_snapshots(session=session, limit=limit)


@router.get("/admin/source-snapshots/{snapshot_id}", response_model=SourceSnapshotRead)
def get_source_snapshot_detail(
    snapshot_id: UUID,
    session: Session = Depends(get_db_session),
) -> SourceSnapshotRead:
    snapshot = get_source_snapshot(session=session, snapshot_id=snapshot_id)
    if snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Source snapshot not found.", "snapshot_id": str(snapshot_id)},
        )
    return snapshot


@router.get("/admin/listing-sources", response_model=list[ListingSourceRead])
def get_listing_sources(
    session: Session = Depends(get_db_session),
) -> list[ListingSourceRead]:
    return list_listing_sources(session=session)


@router.get("/admin/phase-status", response_model=PlaceholderResponse)
def get_phase_status() -> PlaceholderResponse:
    return PlaceholderResponse(
        detail=(
            "Phase 7A hidden scoring, valuation, and planning-first ranking are active for "
            "internal use. Historical labels, frozen assessments, release registry, hidden-only "
            "probabilities, immutable valuation runs, and replay-safe ledger rows are in scope. "
            "Visible rollout, overrides control plane, kill switches, and broader dashboards "
            "remain deferred."
        ),
        surface="admin.phase-status",
        spec_phase="Phase 7A",
    )


@router.get("/admin/gold-set/cases", response_model=HistoricalLabelListResponse)
def get_gold_set_cases(
    review_status: GoldSetReviewStatus | None = Query(default=None),
    template_key: str | None = Query(default=None),
    session: Session = Depends(get_db_session),
) -> HistoricalLabelListResponse:
    _ensure_historical_labels(session=session)
    return list_gold_set_cases_read(
        session=session,
        review_status=review_status,
        template_key=template_key,
    )


@router.get("/admin/gold-set/cases/{case_id}", response_model=HistoricalLabelCaseRead)
def get_gold_set_case_detail(
    case_id: UUID,
    session: Session = Depends(get_db_session),
) -> HistoricalLabelCaseRead:
    _ensure_historical_labels(session=session)
    case = get_gold_set_case_read(session=session, case_id=case_id)
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Gold-set case not found.", "case_id": str(case_id)},
        )
    return case


@router.post("/admin/gold-set/cases/{case_id}/review", response_model=HistoricalLabelCaseRead)
def review_gold_set_case(
    case_id: UUID,
    request: HistoricalLabelReviewRequest,
    session: Session = Depends(get_db_session),
) -> HistoricalLabelCaseRead:
    _ensure_historical_labels(session=session)
    case = get_historical_label_case(session=session, case_id=case_id)
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Gold-set case not found.", "case_id": str(case_id)},
        )
    review_historical_label_case(
        session=session,
        case=case,
        review_status=request.review_status,
        review_notes=request.review_notes,
        notable_policy_issues=request.notable_policy_issues,
        extant_permission_outcome=request.extant_permission_outcome,
        site_geometry_confidence=request.site_geometry_confidence,
        reviewed_by=request.reviewed_by,
    )
    session.commit()
    session.expire_all()
    detail = get_gold_set_case_read(session=session, case_id=case_id)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Gold-set case not found after review.", "case_id": str(case_id)},
        )
    return detail


@router.post("/admin/gold-set/refresh", response_model=JobRunRead)
def refresh_gold_set(
    session: Session = Depends(get_db_session),
) -> JobRunRead:
    job = enqueue_gold_set_refresh_job(session=session, requested_by="api-admin")
    session.commit()
    return JobRunRead.model_validate(job)


@router.get("/admin/model-releases", response_model=ModelReleaseListResponse)
def get_model_releases(
    template_key: str | None = Query(default=None),
    session: Session = Depends(get_db_session),
) -> ModelReleaseListResponse:
    return list_model_releases_read(session=session, template_key=template_key)


@router.get("/admin/model-releases/{release_id}", response_model=ModelReleaseDetailRead)
def get_model_release_detail(
    release_id: UUID,
    session: Session = Depends(get_db_session),
) -> ModelReleaseDetailRead:
    detail = get_model_release_read(session=session, release_id=release_id)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Model release not found.", "release_id": str(release_id)},
        )
    return detail


@router.post("/admin/model-releases/rebuild", response_model=ModelReleaseListResponse)
def rebuild_model_releases(
    request: ModelReleaseRebuildRequest,
    session: Session = Depends(get_db_session),
    storage: StorageAdapter = Depends(get_storage_adapter),
) -> ModelReleaseListResponse:
    build_hidden_model_releases(
        session=session,
        storage=storage,
        requested_by=request.requested_by or "api-admin",
        template_keys=request.template_keys,
        auto_activate_hidden=request.auto_activate_hidden,
    )
    session.commit()
    return list_model_releases_read(session=session)


@router.post(
    "/admin/model-releases/{release_id}/activate",
    response_model=ModelReleaseDetailRead,
)
def activate_hidden_release(
    release_id: UUID,
    request: ModelReleaseActivateRequest,
    session: Session = Depends(get_db_session),
) -> ModelReleaseDetailRead:
    try:
        activate_model_release(
            session=session,
            release_id=release_id,
            requested_by=request.requested_by or "api-admin",
        )
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    detail = get_model_release_read(session=session, release_id=release_id)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Model release not found.", "release_id": str(release_id)},
        )
    return detail


@router.post(
    "/admin/model-releases/{release_id}/retire",
    response_model=ModelReleaseDetailRead,
)
def retire_hidden_release(
    release_id: UUID,
    request: ModelReleaseRetireRequest,
    session: Session = Depends(get_db_session),
) -> ModelReleaseDetailRead:
    try:
        retire_model_release(
            session=session,
            release_id=release_id,
            requested_by=request.requested_by or "api-admin",
        )
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    detail = get_model_release_read(session=session, release_id=release_id)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Model release not found.", "release_id": str(release_id)},
        )
    return detail


def _ensure_historical_labels(*, session: Session) -> None:
    existing = list_gold_set_cases_read(session=session)
    if existing.total > 0:
        return
    rebuild_historical_case_labels(session=session, requested_by="api-read")
    session.commit()
    session.expire_all()
