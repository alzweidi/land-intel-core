from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from landintel.assessments.service import AssessmentBuildError, create_or_refresh_assessment_run
from landintel.domain.schemas import (
    AssessmentDetailRead,
    AssessmentListResponse,
    AssessmentRequest,
    PlaceholderResponse,
)
from landintel.services.assessments_readback import get_assessment, list_assessments
from sqlalchemy.orm import Session

from ..dependencies import get_db_session

router = APIRouter(tags=["assessments"])


@router.post("/api/assessments", response_model=AssessmentDetailRead)
def create_assessment(
    request: AssessmentRequest,
    session: Session = Depends(get_db_session),
) -> AssessmentDetailRead:
    try:
        run = create_or_refresh_assessment_run(
            session=session,
            site_id=request.site_id,
            scenario_id=request.scenario_id,
            as_of_date=request.as_of_date,
            requested_by=request.requested_by,
        )
        session.commit()
        session.expire_all()
    except AssessmentBuildError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    detail = get_assessment(session=session, assessment_id=run.id)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Assessment detail not found.", "assessment_id": str(run.id)},
        )
    return detail


@router.get("/api/assessments", response_model=AssessmentListResponse)
def get_assessment_runs(
    site_id: UUID | None = Query(default=None),
    scenario_id: UUID | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db_session),
) -> AssessmentListResponse:
    return list_assessments(
        session=session,
        site_id=site_id,
        scenario_id=scenario_id,
        limit=limit,
        offset=offset,
    )


@router.get("/api/assessments/{assessment_id}", response_model=AssessmentDetailRead)
def get_assessment_detail(
    assessment_id: UUID,
    session: Session = Depends(get_db_session),
) -> AssessmentDetailRead:
    detail = get_assessment(session=session, assessment_id=assessment_id)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Assessment detail not found.", "assessment_id": str(assessment_id)},
        )
    return detail


@router.post("/api/assessments/{assessment_id}/override", response_model=PlaceholderResponse)
def override_assessment(assessment_id: UUID) -> PlaceholderResponse:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={
            "message": "Analyst overrides remain deferred to Phase 8.",
            "assessment_id": str(assessment_id),
        },
    )
