from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from landintel.auth import RequestActor
from landintel.domain.enums import AppRoleName, OpportunityBand, ValuationQuality
from landintel.domain.schemas import OpportunityDetailRead, OpportunityListResponse
from landintel.services.opportunities_readback import get_opportunity, list_opportunities
from sqlalchemy.orm import Session

from ..dependencies import get_db_session, get_request_actor

router = APIRouter(prefix="/api/opportunities", tags=["opportunities"])


@router.get("/", response_model=OpportunityListResponse)
def get_opportunities(
    borough: str | None = Query(default=None),
    probability_band: OpportunityBand | None = Query(default=None),
    valuation_quality: ValuationQuality | None = Query(default=None),
    manual_review_required: bool | None = Query(default=None),
    auction_deadline_days: int | None = Query(default=None, ge=0),
    min_price: int | None = Query(default=None, ge=0),
    max_price: int | None = Query(default=None, ge=0),
    hidden_mode: bool = Query(default=False),
    session: Session = Depends(get_db_session),
    actor: RequestActor = Depends(get_request_actor),
) -> OpportunityListResponse:
    return list_opportunities(
        session=session,
        borough=borough,
        probability_band=probability_band,
        valuation_quality=valuation_quality,
        manual_review_required=manual_review_required,
        auction_deadline_days=auction_deadline_days,
        min_price=min_price,
        max_price=max_price,
        include_hidden=hidden_mode and actor.role in {AppRoleName.REVIEWER, AppRoleName.ADMIN},
        viewer_role=actor.role,
    )


@router.get("/{site_id}", response_model=OpportunityDetailRead)
def get_opportunity_detail(
    site_id: UUID,
    hidden_mode: bool = Query(default=False),
    session: Session = Depends(get_db_session),
    actor: RequestActor = Depends(get_request_actor),
) -> OpportunityDetailRead:
    detail = get_opportunity(
        session=session,
        site_id=site_id,
        include_hidden=hidden_mode and actor.role in {AppRoleName.REVIEWER, AppRoleName.ADMIN},
        viewer_role=actor.role,
    )
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Opportunity detail not found.", "site_id": str(site_id)},
        )
    return detail
