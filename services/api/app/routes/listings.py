from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from landintel.domain.enums import ListingStatus, ListingType
from landintel.domain.schemas import (
    ConnectorRunRequest,
    JobAcceptedResponse,
    ListingClusterDetailRead,
    ListingClusterListResponse,
    ListingDetailRead,
    ListingListResponse,
    ManualUrlIntakeRequest,
)
from landintel.jobs.service import (
    enqueue_connector_run_job,
    enqueue_csv_import_job,
    enqueue_manual_url_job,
)
from landintel.services.listings_readback import (
    get_listing,
    get_listing_cluster,
    list_listing_clusters,
    list_listings,
)
from sqlalchemy.orm import Session

from ..dependencies import get_db_session

router = APIRouter(tags=["listings"])


@router.post(
    "/api/listings/intake/url",
    response_model=JobAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def intake_manual_url(
    payload: ManualUrlIntakeRequest,
    session: Session = Depends(get_db_session),
) -> JobAcceptedResponse:
    job = enqueue_manual_url_job(
        session=session,
        url=str(payload.url),
        source_name=payload.source_name,
        requested_by=payload.requested_by,
    )
    session.commit()
    return JobAcceptedResponse(job_id=job.id, status=job.status, job_type=job.job_type)


@router.post(
    "/api/listings/import/csv",
    response_model=JobAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def import_csv(
    file: UploadFile = File(...),
    source_name: str = Form(default="csv_import"),
    requested_by: str | None = Form(default=None),
    session: Session = Depends(get_db_session),
) -> JobAcceptedResponse:
    csv_bytes = await file.read()
    if not csv_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "CSV upload is empty."},
        )

    job = enqueue_csv_import_job(
        session=session,
        source_name=source_name,
        filename=file.filename or "import.csv",
        csv_bytes=csv_bytes,
        requested_by=requested_by,
    )
    session.commit()
    return JobAcceptedResponse(job_id=job.id, status=job.status, job_type=job.job_type)


@router.post(
    "/api/listings/connectors/{source_key}/run",
    response_model=JobAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def run_connector(
    source_key: str,
    payload: ConnectorRunRequest,
    session: Session = Depends(get_db_session),
) -> JobAcceptedResponse:
    job = enqueue_connector_run_job(
        session=session,
        source_name=source_key,
        requested_by=payload.requested_by,
    )
    session.commit()
    return JobAcceptedResponse(job_id=job.id, status=job.status, job_type=job.job_type)


@router.get("/api/listings", response_model=ListingListResponse)
def get_listings(
    q: str | None = Query(default=None),
    source: str | None = Query(default=None),
    status_filter: ListingStatus | None = Query(default=None, alias="status"),
    listing_type: ListingType | None = Query(default=None),
    min_price_gbp: int | None = Query(default=None, ge=0),
    max_price_gbp: int | None = Query(default=None, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db_session),
) -> ListingListResponse:
    return list_listings(
        session=session,
        q=q,
        source=source,
        status=status_filter,
        listing_type=listing_type,
        min_price_gbp=min_price_gbp,
        max_price_gbp=max_price_gbp,
        limit=limit,
        offset=offset,
    )


@router.get("/api/listings/{listing_id}", response_model=ListingDetailRead)
def get_listing_detail(
    listing_id: UUID,
    session: Session = Depends(get_db_session),
) -> ListingDetailRead:
    listing = get_listing(session=session, listing_id=listing_id)
    if listing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Listing not found.", "listing_id": str(listing_id)},
        )
    return listing


@router.get("/api/listing-clusters", response_model=ListingClusterListResponse)
def get_clusters(
    q: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db_session),
) -> ListingClusterListResponse:
    return list_listing_clusters(session=session, q=q, limit=limit, offset=offset)


@router.get("/api/listing-clusters/{cluster_id}", response_model=ListingClusterDetailRead)
def get_cluster_detail(
    cluster_id: UUID,
    session: Session = Depends(get_db_session),
) -> ListingClusterDetailRead:
    cluster = get_listing_cluster(session=session, cluster_id=cluster_id)
    if cluster is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Listing cluster not found.", "cluster_id": str(cluster_id)},
        )
    return cluster
