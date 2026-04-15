from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from landintel.domain.schemas import PlaceholderResponse

router = APIRouter(tags=["scenarios"])


@router.post("/api/sites/{site_id}/scenarios/suggest", response_model=PlaceholderResponse)
def suggest_scenarios(site_id: UUID) -> PlaceholderResponse:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"message": "Scenario suggestion is deferred to Phase 4.", "site_id": str(site_id)},
    )


@router.post("/api/scenarios/{scenario_id}/confirm", response_model=PlaceholderResponse)
def confirm_scenario(scenario_id: UUID) -> PlaceholderResponse:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={
            "message": "Scenario confirmation is deferred to Phase 4.",
            "scenario_id": str(scenario_id),
        },
    )


@router.get("/api/scenarios/{scenario_id}", response_model=PlaceholderResponse)
def get_scenario(scenario_id: UUID) -> PlaceholderResponse:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={
            "message": "Scenario detail is deferred to Phase 4.",
            "scenario_id": str(scenario_id),
        },
    )
