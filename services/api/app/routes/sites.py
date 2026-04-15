from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from landintel.domain.schemas import PlaceholderResponse

router = APIRouter(prefix="/api/sites", tags=["sites"])


@router.post("/from-cluster/{cluster_id}", response_model=PlaceholderResponse)
def create_site_from_cluster(cluster_id: UUID) -> PlaceholderResponse:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={
            "message": "Site creation is deferred to Phase 2.",
            "cluster_id": str(cluster_id),
        },
    )


@router.get("/", response_model=PlaceholderResponse)
def list_sites() -> PlaceholderResponse:
    return PlaceholderResponse(
        detail="Site browsing is deferred to Phase 2.",
        surface="sites.index",
        spec_phase="Phase 2",
    )


@router.get("/{site_id}", response_model=PlaceholderResponse)
def get_site(site_id: UUID) -> PlaceholderResponse:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"message": "Site detail is deferred to Phase 2.", "site_id": str(site_id)},
    )


@router.post("/{site_id}/geometry", response_model=PlaceholderResponse)
def create_site_geometry(site_id: UUID) -> PlaceholderResponse:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"message": "Geometry editing is deferred to Phase 2.", "site_id": str(site_id)},
    )


@router.post("/{site_id}/extant-permission-check", response_model=PlaceholderResponse)
def rerun_extant_permission(site_id: UUID) -> PlaceholderResponse:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={
            "message": "Extant permission checks are deferred to Phase 3.",
            "site_id": str(site_id),
        },
    )

