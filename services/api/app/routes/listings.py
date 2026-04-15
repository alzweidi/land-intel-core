from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from landintel.domain.schemas import (
    ManualUrlIntakeRequest,
    ManualUrlIntakeResponse,
    PlaceholderResponse,
)
from landintel.jobs.service import enqueue_manual_url_job
from sqlalchemy.orm import Session

from ..dependencies import get_db_session

router = APIRouter(prefix="/api/listings", tags=["listings"])


@router.post(
    "/intake/url",
    response_model=ManualUrlIntakeResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def intake_manual_url(
    payload: ManualUrlIntakeRequest,
    session: Session = Depends(get_db_session),
) -> ManualUrlIntakeResponse:
    job = enqueue_manual_url_job(
        session=session,
        url=str(payload.url),
        source_name=payload.source_name,
        requested_by=payload.requested_by,
    )
    session.commit()
    return ManualUrlIntakeResponse(job_id=job.id, status=job.status, job_type=job.job_type)


@router.get("/", response_model=PlaceholderResponse)
def list_listings() -> PlaceholderResponse:
    return PlaceholderResponse(
        detail="Listing search is deferred to Phase 1.",
        surface="listings.index",
        spec_phase="Phase 1",
    )


@router.get("/{listing_id}", response_model=PlaceholderResponse)
def get_listing(listing_id: UUID) -> PlaceholderResponse:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={
            "message": "Listing detail is deferred to Phase 1.",
            "listing_id": str(listing_id),
        },
    )
