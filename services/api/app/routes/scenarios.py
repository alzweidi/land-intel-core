from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from landintel.domain.schemas import (
    ScenarioConfirmRequest,
    ScenarioSuggestRequest,
    SiteScenarioDetailRead,
    SiteScenarioListResponse,
    SiteScenarioSuggestResponse,
)
from landintel.scenarios.normalize import ScenarioNormalizeError, confirm_or_update_scenario
from landintel.scenarios.suggest import suggest_scenarios_for_site
from landintel.services.scenarios_readback import get_scenario_detail, list_site_scenarios
from sqlalchemy.orm import Session

from ..dependencies import get_db_session

router = APIRouter(tags=["scenarios"])


@router.post(
    "/api/sites/{site_id}/scenarios/suggest",
    response_model=SiteScenarioSuggestResponse,
)
def suggest_scenarios(
    site_id: UUID,
    request: ScenarioSuggestRequest | None = None,
    session: Session = Depends(get_db_session),
) -> SiteScenarioSuggestResponse:
    payload = request or ScenarioSuggestRequest()
    try:
        response = suggest_scenarios_for_site(
            session=session,
            site_id=site_id,
            requested_by=payload.requested_by,
            template_keys=payload.template_keys,
            manual_seed=payload.manual_seed,
        )
        session.commit()
        session.expire_all()
        return response
    except Exception as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.get(
    "/api/sites/{site_id}/scenarios",
    response_model=SiteScenarioListResponse,
)
def get_site_scenarios(
    site_id: UUID,
    session: Session = Depends(get_db_session),
) -> SiteScenarioListResponse:
    return list_site_scenarios(session=session, site_id=site_id)


@router.get(
    "/api/scenarios/{scenario_id}",
    response_model=SiteScenarioDetailRead,
)
def get_scenario(
    scenario_id: UUID,
    session: Session = Depends(get_db_session),
) -> SiteScenarioDetailRead:
    scenario = get_scenario_detail(session=session, scenario_id=scenario_id)
    if scenario is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Scenario detail not found.", "scenario_id": str(scenario_id)},
        )
    return scenario


@router.post(
    "/api/scenarios/{scenario_id}/confirm",
    response_model=SiteScenarioDetailRead,
)
def confirm_scenario(
    scenario_id: UUID,
    request: ScenarioConfirmRequest,
    session: Session = Depends(get_db_session),
) -> SiteScenarioDetailRead:
    try:
        scenario = confirm_or_update_scenario(
            session=session,
            scenario_id=scenario_id,
            request=request,
        )
        session.commit()
        session.expire_all()
    except ScenarioNormalizeError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    detail = get_scenario_detail(session=session, scenario_id=scenario.id)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Scenario detail not found.", "scenario_id": str(scenario.id)},
        )
    return detail
