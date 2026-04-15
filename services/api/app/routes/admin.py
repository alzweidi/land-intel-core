from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from landintel.domain.schemas import JobRunRead, PlaceholderResponse, SourceSnapshotRead
from landintel.jobs.service import list_jobs
from landintel.monitoring.health import build_data_health_stub, build_model_health_stub
from landintel.services.readback import get_source_snapshot, list_source_snapshots
from sqlalchemy.orm import Session

from ..dependencies import get_db_session

router = APIRouter(prefix="/api", tags=["admin"])


@router.get("/health/data")
def get_data_health() -> dict[str, object]:
    return build_data_health_stub()


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
    snapshots = list_source_snapshots(session=session, limit=limit)
    return [SourceSnapshotRead.model_validate(snapshot) for snapshot in snapshots]


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
    return SourceSnapshotRead.model_validate(snapshot)


@router.get("/admin/phase-status", response_model=PlaceholderResponse)
def get_phase_status() -> PlaceholderResponse:
    return PlaceholderResponse(
        detail=(
            "Phase status is represented by docs plus the placeholder surfaces "
            "in this skeleton."
        ),
        surface="admin.phase-status",
        spec_phase="Phase 0",
    )
