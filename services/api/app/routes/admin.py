from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from landintel.auth import RequestActor, resolve_request_actor_name
from landintel.domain.enums import AppRoleName, GoldSetReviewStatus
from landintel.domain.models import AssessmentRun
from landintel.domain.schemas import (
    HistoricalLabelCaseRead,
    HistoricalLabelListResponse,
    HistoricalLabelReviewRequest,
    IncidentActionRequest,
    IncidentRecordRead,
    JobRunRead,
    ListingSourceRead,
    ModelReleaseActivateRequest,
    ModelReleaseDetailRead,
    ModelReleaseListResponse,
    ModelReleaseRebuildRequest,
    ModelReleaseRetireRequest,
    PlaceholderResponse,
    ReleaseScopeVisibilityRequest,
    SourceSnapshotRead,
)
from landintel.jobs.service import enqueue_gold_set_refresh_job, list_jobs
from landintel.monitoring.health import build_data_health, build_model_health
from landintel.planning.historical_labels import (
    get_historical_label_case,
    rebuild_historical_case_labels,
    review_historical_label_case,
)
from landintel.review.visibility import (
    ReviewAccessError,
    open_scope_incident,
    resolve_scope_incident,
    set_scope_visibility,
)
from landintel.scoring.release import (
    activate_model_release,
    build_hidden_model_releases,
    retire_model_release,
)
from landintel.services.assessments_readback import (
    get_assessment,
    get_gold_set_case_read,
    list_gold_set_cases_read,
)
from landintel.services.listings_readback import (
    get_source_snapshot,
    list_listing_sources,
    list_source_snapshots,
)
from landintel.services.model_releases_readback import (
    get_model_release_read,
    list_model_releases_read,
)
from landintel.storage.base import StorageAdapter
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..dependencies import (
    get_db_session,
    get_storage_adapter,
    require_admin_actor,
    require_reviewer_actor,
)

router = APIRouter(prefix="/api", tags=["admin"])


@router.get("/health/data")
def get_data_health(
    session: Session = Depends(get_db_session),
    _actor: RequestActor = Depends(require_admin_actor),
) -> dict[str, object]:
    return build_data_health(session)


@router.get("/health/model")
def get_model_health(
    session: Session = Depends(get_db_session),
    _actor: RequestActor = Depends(require_admin_actor),
) -> dict[str, object]:
    return build_model_health(session)


@router.get("/admin/jobs", response_model=list[JobRunRead])
def get_jobs(
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_db_session),
    _actor: RequestActor = Depends(require_admin_actor),
) -> list[JobRunRead]:
    return [JobRunRead.model_validate(job) for job in list_jobs(session=session, limit=limit)]


@router.get("/admin/review-queue")
def get_review_queue(
    limit: int = Query(default=25, ge=1, le=100),
    session: Session = Depends(get_db_session),
    _actor: RequestActor = Depends(require_reviewer_actor),
) -> dict[str, object]:
    run_ids = session.execute(
        select(AssessmentRun.id).order_by(AssessmentRun.updated_at.desc()).limit(limit)
    ).scalars().all()
    items = [
        get_assessment(
            session=session,
            assessment_id=run_id,
            include_hidden=False,
            viewer_role=AppRoleName.REVIEWER,
        )
        for run_id in run_ids
    ]
    details = [item for item in items if item is not None]
    data_health = build_data_health(session)
    failing_boroughs = [
        row
        for row in list(data_health.get("coverage") or [])
        if row.get("coverage_status") != "COMPLETE" or row.get("freshness_status") != "FRESH"
    ]
    manual_review_cases = [
        {
            "assessment_id": str(item.id),
            "site_id": str(item.site_id),
            "display_name": (
                item.site_summary.display_name if item.site_summary else str(item.site_id)
            ),
            "review_status": item.review_status.value,
            "manual_review_required": item.manual_review_required,
            "visibility_mode": (
                None if item.visibility is None else item.visibility.visibility_mode.value
            ),
        }
        for item in details
        if item.manual_review_required
        or (
            item.override_summary is not None
            and item.override_summary.display_block_reason is not None
        )
    ]
    blocked_cases = [
        {
            "assessment_id": str(item.id),
            "site_id": str(item.site_id),
            "display_name": (
                item.site_summary.display_name if item.site_summary else str(item.site_id)
            ),
            "blocked_reason": (
                None if item.visibility is None else item.visibility.blocked_reason_text
            ),
            "visibility_mode": (
                None if item.visibility is None else item.visibility.visibility_mode.value
            ),
            "display_block_reason": (
                None
                if item.override_summary is None
                else item.override_summary.display_block_reason
            ),
        }
        for item in details
        if (
            item.visibility is not None
            and (item.visibility.blocked or item.visibility.blocked_reason_codes)
        )
        or (
            item.override_summary is not None
            and item.override_summary.display_block_reason is not None
        )
    ]
    recent_cases = [
        {
            "assessment_id": str(item.id),
            "display_name": (
                item.site_summary.display_name if item.site_summary else str(item.site_id)
            ),
            "updated_at": item.updated_at.isoformat(),
            "estimate_status": item.estimate_status.value,
            "manual_review_required": item.manual_review_required,
        }
        for item in details
    ]
    return {
        "manual_review_cases": manual_review_cases,
        "blocked_cases": blocked_cases,
        "recent_cases": recent_cases,
        "failing_boroughs": failing_boroughs,
    }


@router.get("/admin/source-snapshots", response_model=list[SourceSnapshotRead])
def get_source_snapshots(
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_db_session),
    _actor: RequestActor = Depends(require_admin_actor),
) -> list[SourceSnapshotRead]:
    return list_source_snapshots(session=session, limit=limit)


@router.get("/admin/source-snapshots/{snapshot_id}", response_model=SourceSnapshotRead)
def get_source_snapshot_detail(
    snapshot_id: UUID,
    session: Session = Depends(get_db_session),
    _actor: RequestActor = Depends(require_admin_actor),
) -> SourceSnapshotRead:
    snapshot = get_source_snapshot(session=session, snapshot_id=snapshot_id)
    if snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Source snapshot not found.", "snapshot_id": str(snapshot_id)},
        )
    return snapshot


@router.get("/admin/listing-sources", response_model=list[ListingSourceRead])
def get_listing_sources(
    session: Session = Depends(get_db_session),
    _actor: RequestActor = Depends(require_admin_actor),
) -> list[ListingSourceRead]:
    return list_listing_sources(session=session)


@router.get("/admin/phase-status", response_model=PlaceholderResponse)
def get_phase_status(
    _actor: RequestActor = Depends(require_admin_actor),
) -> PlaceholderResponse:
    return PlaceholderResponse(
        detail=(
            "Phase 8A safety controls are active. Hidden scoring remains the default, visible "
            "probability stays off unless a scope is explicitly enabled, and override, incident, "
            "audit-export, and health-control surfaces are now in scope for internal operations."
        ),
        surface="admin.phase-status",
        spec_phase="Phase 8A",
    )


@router.get("/admin/gold-set/cases", response_model=HistoricalLabelListResponse)
def get_gold_set_cases(
    review_status: GoldSetReviewStatus | None = Query(default=None),
    template_key: str | None = Query(default=None),
    session: Session = Depends(get_db_session),
    _actor: RequestActor = Depends(require_reviewer_actor),
) -> HistoricalLabelListResponse:
    _ensure_historical_labels(session=session)
    return list_gold_set_cases_read(
        session=session,
        review_status=review_status,
        template_key=template_key,
    )


@router.get("/admin/gold-set/cases/{case_id}", response_model=HistoricalLabelCaseRead)
def get_gold_set_case_detail(
    case_id: UUID,
    session: Session = Depends(get_db_session),
    _actor: RequestActor = Depends(require_reviewer_actor),
) -> HistoricalLabelCaseRead:
    _ensure_historical_labels(session=session)
    case = get_gold_set_case_read(session=session, case_id=case_id)
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Gold-set case not found.", "case_id": str(case_id)},
        )
    return case


@router.post("/admin/gold-set/cases/{case_id}/review", response_model=HistoricalLabelCaseRead)
def review_gold_set_case(
    case_id: UUID,
    request: HistoricalLabelReviewRequest,
    session: Session = Depends(get_db_session),
    actor: RequestActor = Depends(require_reviewer_actor),
) -> HistoricalLabelCaseRead:
    _ensure_historical_labels(session=session)
    case = get_historical_label_case(session=session, case_id=case_id)
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Gold-set case not found.", "case_id": str(case_id)},
        )
    review_historical_label_case(
        session=session,
        case=case,
        review_status=request.review_status,
        review_notes=request.review_notes,
        notable_policy_issues=request.notable_policy_issues,
        extant_permission_outcome=request.extant_permission_outcome,
        site_geometry_confidence=request.site_geometry_confidence,
        reviewed_by=resolve_request_actor_name(actor, request.reviewed_by or "api-review"),
    )
    session.commit()
    session.expire_all()
    detail = get_gold_set_case_read(session=session, case_id=case_id)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Gold-set case not found after review.", "case_id": str(case_id)},
        )
    return detail


@router.post("/admin/gold-set/refresh", response_model=JobRunRead)
def refresh_gold_set(
    session: Session = Depends(get_db_session),
    actor: RequestActor = Depends(require_reviewer_actor),
) -> JobRunRead:
    job = enqueue_gold_set_refresh_job(
        session=session,
        requested_by=resolve_request_actor_name(actor, "api-admin"),
    )
    session.commit()
    return JobRunRead.model_validate(job)


@router.get("/admin/model-releases", response_model=ModelReleaseListResponse)
def get_model_releases(
    template_key: str | None = Query(default=None),
    session: Session = Depends(get_db_session),
    _actor: RequestActor = Depends(require_admin_actor),
) -> ModelReleaseListResponse:
    return list_model_releases_read(session=session, template_key=template_key)


@router.get("/admin/model-releases/{release_id}", response_model=ModelReleaseDetailRead)
def get_model_release_detail(
    release_id: UUID,
    session: Session = Depends(get_db_session),
    _actor: RequestActor = Depends(require_admin_actor),
) -> ModelReleaseDetailRead:
    detail = get_model_release_read(session=session, release_id=release_id)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Model release not found.", "release_id": str(release_id)},
        )
    return detail


@router.post("/admin/model-releases/rebuild", response_model=ModelReleaseListResponse)
def rebuild_model_releases(
    request: ModelReleaseRebuildRequest,
    session: Session = Depends(get_db_session),
    storage: StorageAdapter = Depends(get_storage_adapter),
    actor: RequestActor = Depends(require_admin_actor),
) -> ModelReleaseListResponse:
    build_hidden_model_releases(
        session=session,
        storage=storage,
        requested_by=resolve_request_actor_name(actor, request.requested_by or "api-admin"),
        template_keys=request.template_keys,
        auto_activate_hidden=request.auto_activate_hidden,
    )
    session.commit()
    return list_model_releases_read(session=session)


@router.post(
    "/admin/model-releases/{release_id}/activate",
    response_model=ModelReleaseDetailRead,
)
def activate_hidden_release(
    release_id: UUID,
    request: ModelReleaseActivateRequest,
    session: Session = Depends(get_db_session),
    actor: RequestActor = Depends(require_admin_actor),
) -> ModelReleaseDetailRead:
    try:
        activate_model_release(
            session=session,
            release_id=release_id,
            requested_by=resolve_request_actor_name(actor, request.requested_by or "api-admin"),
        )
        session.commit()
    except (ReviewAccessError, ValueError) as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    detail = get_model_release_read(session=session, release_id=release_id)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Model release not found.", "release_id": str(release_id)},
        )
    return detail


@router.post(
    "/admin/model-releases/{release_id}/retire",
    response_model=ModelReleaseDetailRead,
)
def retire_hidden_release(
    release_id: UUID,
    request: ModelReleaseRetireRequest,
    session: Session = Depends(get_db_session),
    actor: RequestActor = Depends(require_admin_actor),
) -> ModelReleaseDetailRead:
    try:
        retire_model_release(
            session=session,
            release_id=release_id,
            requested_by=resolve_request_actor_name(actor, request.requested_by or "api-admin"),
        )
        session.commit()
    except (ReviewAccessError, ValueError) as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    detail = get_model_release_read(session=session, release_id=release_id)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Model release not found.", "release_id": str(release_id)},
        )
    return detail


@router.post(
    "/admin/release-scopes/{scope_key}/visibility",
    response_model=ModelReleaseListResponse,
)
def update_release_scope_visibility(
    scope_key: str,
    request: ReleaseScopeVisibilityRequest,
    session: Session = Depends(get_db_session),
    actor: RequestActor = Depends(require_admin_actor),
) -> ModelReleaseListResponse:
    try:
        set_scope_visibility(
            session=session,
            scope_key=scope_key,
            visibility_mode=request.visibility_mode,
            requested_by=resolve_request_actor_name(actor, request.requested_by or "api-admin"),
            actor_role=actor.role,
            reason=request.reason,
        )
        session.commit()
    except ReviewAccessError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    return list_model_releases_read(session=session)


@router.post(
    "/admin/release-scopes/{scope_key}/incident",
    response_model=IncidentRecordRead,
)
def manage_release_scope_incident(
    scope_key: str,
    request: IncidentActionRequest,
    session: Session = Depends(get_db_session),
    actor: RequestActor = Depends(require_admin_actor),
) -> IncidentRecordRead:
    try:
        normalized = request.action.strip().upper()
        if normalized == "OPEN":
            incident = open_scope_incident(
                session=session,
                scope_key=scope_key,
                requested_by=resolve_request_actor_name(actor, request.requested_by or "api-admin"),
                actor_role=actor.role,
                reason=request.reason,
            )
        elif normalized in {"RESOLVE", "ROLLBACK"}:
            incident = resolve_scope_incident(
                session=session,
                scope_key=scope_key,
                requested_by=resolve_request_actor_name(actor, request.requested_by or "api-admin"),
                actor_role=actor.role,
                reason=request.reason,
                rollback_visibility=normalized == "ROLLBACK",
            )
        else:
            raise ReviewAccessError(f"Unsupported incident action '{request.action}'.")
        session.commit()
    except ReviewAccessError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    return IncidentRecordRead(
        id=incident.id,
        scope_key=incident.scope_key,
        template_key=incident.template_key,
        borough_id=incident.borough_id,
        incident_type=incident.incident_type,
        status=incident.status,
        reason=incident.reason,
        previous_visibility_mode=incident.previous_visibility_mode,
        applied_visibility_mode=incident.applied_visibility_mode,
        created_by=incident.created_by,
        resolved_by=incident.resolved_by,
        created_at=incident.created_at,
        resolved_at=incident.resolved_at,
    )


def _ensure_historical_labels(*, session: Session) -> None:
    existing = list_gold_set_cases_read(session=session)
    if existing.total > 0:
        return
    rebuild_historical_case_labels(session=session, requested_by="api-read")
    session.commit()
    session.expire_all()
