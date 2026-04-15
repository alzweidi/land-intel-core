from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from landintel.assessments.service import AssessmentBuildError, create_or_refresh_assessment_run
from landintel.domain.enums import AppRoleName
from landintel.domain.schemas import (
    AssessmentDetailRead,
    AssessmentListResponse,
    AssessmentOverrideRequest,
    AssessmentRequest,
    AuditExportRead,
)
from landintel.review.audit_export import build_assessment_audit_export
from landintel.review.overrides import apply_assessment_override
from landintel.review.visibility import ReviewAccessError
from landintel.services.assessments_readback import get_assessment, list_assessments
from landintel.storage.base import StorageAdapter
from sqlalchemy.orm import Session

from ..dependencies import get_db_session, get_storage_adapter

router = APIRouter(tags=["assessments"])


@router.post("/api/assessments", response_model=AssessmentDetailRead)
def create_assessment(
    request: AssessmentRequest,
    session: Session = Depends(get_db_session),
    storage: StorageAdapter = Depends(get_storage_adapter),
) -> AssessmentDetailRead:
    try:
        run = create_or_refresh_assessment_run(
            session=session,
            site_id=request.site_id,
            scenario_id=request.scenario_id,
            as_of_date=request.as_of_date,
            requested_by=request.requested_by,
            storage=storage,
        )
        session.commit()
        session.expire_all()
    except AssessmentBuildError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    detail = get_assessment(
        session=session,
        assessment_id=run.id,
        include_hidden=request.hidden_mode,
        viewer_role=(
            request.viewer_role
            if request.viewer_role is not None
            else (AppRoleName.REVIEWER if request.hidden_mode else AppRoleName.ANALYST)
        ),
    )
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
    hidden_mode: bool = Query(default=False),
    viewer_role: AppRoleName | None = Query(default=None),
    session: Session = Depends(get_db_session),
) -> AssessmentDetailRead:
    detail = get_assessment(
        session=session,
        assessment_id=assessment_id,
        include_hidden=hidden_mode,
        viewer_role=(
            viewer_role
            if viewer_role is not None
            else (AppRoleName.REVIEWER if hidden_mode else AppRoleName.ANALYST)
        ),
    )
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Assessment detail not found.", "assessment_id": str(assessment_id)},
        )
    return detail


@router.post("/api/assessments/{assessment_id}/override", response_model=AssessmentDetailRead)
def override_assessment(
    assessment_id: UUID,
    request: AssessmentOverrideRequest,
    session: Session = Depends(get_db_session),
) -> AssessmentDetailRead:
    try:
        apply_assessment_override(
            session=session,
            assessment_id=assessment_id,
            request=request,
        )
        session.commit()
        session.expire_all()
    except ReviewAccessError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    detail = get_assessment(
        session=session,
        assessment_id=assessment_id,
        include_hidden=request.actor_role in {AppRoleName.REVIEWER, AppRoleName.ADMIN},
        viewer_role=request.actor_role,
    )
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Assessment detail not found.", "assessment_id": str(assessment_id)},
        )
    return detail


@router.get("/api/assessments/{assessment_id}/audit-export", response_model=AuditExportRead)
def get_assessment_audit_export(
    assessment_id: UUID,
    requested_by: str | None = Query(default="api-audit-export"),
    actor_role: AppRoleName = Query(default=AppRoleName.REVIEWER),
    session: Session = Depends(get_db_session),
    storage: StorageAdapter = Depends(get_storage_adapter),
) -> AuditExportRead:
    try:
        export = build_assessment_audit_export(
            session=session,
            storage=storage,
            assessment_id=assessment_id,
            requested_by=requested_by,
            actor_role=actor_role,
        )
        session.commit()
    except ReviewAccessError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    return export
