from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from landintel.domain.enums import GoldSetReviewStatus
from landintel.domain.schemas import (
    HistoricalLabelCaseRead,
    HistoricalLabelListResponse,
    HistoricalLabelReviewRequest,
    JobRunRead,
    ListingSourceRead,
    PlaceholderResponse,
    SourceSnapshotRead,
)
from landintel.jobs.service import enqueue_gold_set_refresh_job, list_jobs
from landintel.monitoring.health import build_data_health, build_model_health_stub
from landintel.planning.historical_labels import (
    get_historical_label_case,
    rebuild_historical_case_labels,
    review_historical_label_case,
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
from sqlalchemy.orm import Session

from ..dependencies import get_db_session

router = APIRouter(prefix="/api", tags=["admin"])


@router.get("/health/data")
def get_data_health(session: Session = Depends(get_db_session)) -> dict[str, object]:
    return build_data_health(session)


@router.get("/health/model")
def get_model_health() -> dict[str, object]:
    return build_model_health_stub()


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
            "Phase 5A historical labels, frozen pre-score assessments, comparable retrieval, "
            "prediction-ledger foundations, and gold-set review are active. Model training, "
            "probability, valuation, and ranking remain deferred."
        ),
        surface="admin.phase-status",
        spec_phase="Phase 5A",
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


def _ensure_historical_labels(*, session: Session) -> None:
    existing = list_gold_set_cases_read(session=session)
    if existing.total > 0:
        return
    rebuild_historical_case_labels(session=session, requested_by="api-read")
    session.commit()
    session.expire_all()
