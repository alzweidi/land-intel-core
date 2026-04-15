from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from landintel.domain.schemas import AssessmentRequest, PlaceholderResponse

router = APIRouter(tags=["assessments"])


@router.post("/api/assessments", response_model=PlaceholderResponse)
def create_assessment(_: AssessmentRequest) -> PlaceholderResponse:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={
            "message": (
                "Assessments are deferred to Phase 6 after scenario confirmation "
                "and frozen features exist."
            ),
        },
    )


@router.get("/api/assessments/{assessment_id}", response_model=PlaceholderResponse)
def get_assessment(assessment_id: UUID) -> PlaceholderResponse:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={
            "message": "Assessment detail is deferred to Phase 6.",
            "assessment_id": str(assessment_id),
        },
    )


@router.post("/api/assessments/{assessment_id}/override", response_model=PlaceholderResponse)
def override_assessment(assessment_id: UUID) -> PlaceholderResponse:
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={
            "message": "Analyst overrides are deferred to Phase 8.",
            "assessment_id": str(assessment_id),
        },
    )
