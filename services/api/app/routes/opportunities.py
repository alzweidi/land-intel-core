from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from landintel.domain.schemas import PlaceholderResponse

router = APIRouter(prefix="/api/opportunities", tags=["opportunities"])


@router.get("/", response_model=PlaceholderResponse)
def list_opportunities() -> PlaceholderResponse:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={
            "message": (
                "Opportunity ranking is deferred to Phase 7 and probability "
                "remains hidden until later phases."
            ),
        },
    )


@router.get("/{site_id}", response_model=PlaceholderResponse)
def get_opportunity(site_id: UUID) -> PlaceholderResponse:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"message": "Opportunity detail is deferred to Phase 7.", "site_id": str(site_id)},
    )
