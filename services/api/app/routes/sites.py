from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from landintel.domain.models import SiteCandidate
from landintel.domain.schemas import (
    ExtantPermissionCheckRequest,
    SiteDetailRead,
    SiteFromClusterRequest,
    SiteGeometryUpdateRequest,
    SiteListResponse,
)
from landintel.jobs.service import (
    enqueue_site_scenario_geometry_refresh_job,
    enqueue_site_scenario_suggest_refresh_job,
)
from landintel.planning.enrich import refresh_site_planning_context
from landintel.planning.extant_permission import (
    audit_extant_permission_check,
    evaluate_site_extant_permission,
)
from landintel.services.sites_readback import get_site, list_sites
from landintel.sites.service import (
    SiteBuildError,
    build_or_refresh_site_from_cluster,
    save_site_geometry_revision,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..dependencies import get_db_session

router = APIRouter(prefix="/api/sites", tags=["sites"])


@router.post("/from-cluster/{cluster_id}", response_model=SiteDetailRead)
def create_site_from_cluster(
    cluster_id: UUID,
    request: SiteFromClusterRequest | None = None,
    session: Session = Depends(get_db_session),
) -> SiteDetailRead:
    try:
        site = build_or_refresh_site_from_cluster(
            session=session,
            cluster_id=cluster_id,
            requested_by=request.requested_by if request is not None else None,
        )
        enqueue_site_scenario_suggest_refresh_job(
            session=session,
            site_id=str(site.id),
            requested_by=request.requested_by if request is not None else None,
        )
        session.commit()
        session.expire_all()
    except SiteBuildError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    site_detail = get_site(session, site_id=site.id)
    if site_detail is None:  # pragma: no cover - defensive only
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site was not persisted.")
    return site_detail


@router.get("", response_model=SiteListResponse)
def list_site_candidates(
    q: str | None = Query(default=None),
    borough: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db_session),
) -> SiteListResponse:
    return list_sites(
        session=session,
        q=q,
        borough=borough,
        status=status_filter,
        limit=limit,
        offset=offset,
    )


@router.get("/{site_id}", response_model=SiteDetailRead)
def get_site_detail(
    site_id: UUID,
    session: Session = Depends(get_db_session),
) -> SiteDetailRead:
    site = get_site(session, site_id=site_id)
    if site is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Site detail not found.", "site_id": str(site_id)},
        )
    return site


@router.post("/{site_id}/geometry", response_model=SiteDetailRead)
def create_site_geometry(
    site_id: UUID,
    request: SiteGeometryUpdateRequest,
    session: Session = Depends(get_db_session),
) -> SiteDetailRead:
    try:
        site = save_site_geometry_revision(
            session=session,
            site_id=site_id,
            geom_4326=request.geom_4326,
            source_type=request.source_type,
            confidence=request.confidence,
            reason=request.reason,
            created_by=request.created_by,
            raw_asset_id=request.raw_asset_id,
        )
        enqueue_site_scenario_geometry_refresh_job(
            session=session,
            site_id=str(site.id),
            requested_by=request.created_by,
        )
        session.commit()
        session.expire_all()
    except SiteBuildError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    site_detail = get_site(session, site_id=site.id)
    if site_detail is None:  # pragma: no cover - defensive only
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Site detail not found after save.",
        )
    return site_detail


@router.post("/{site_id}/extant-permission-check", response_model=SiteDetailRead)
def rerun_extant_permission(
    site_id: UUID,
    request: ExtantPermissionCheckRequest | None = None,
    session: Session = Depends(get_db_session),
) -> SiteDetailRead:
    site = session.execute(
        select(SiteCandidate).where(SiteCandidate.id == site_id)
    ).scalar_one_or_none()
    if site is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Site detail not found.", "site_id": str(site_id)},
        )

    refresh_site_planning_context(
        session=session,
        site=site,
        requested_by=request.requested_by if request is not None else None,
    )
    result = evaluate_site_extant_permission(session=session, site=site)
    audit_extant_permission_check(
        session=session,
        site=site,
        requested_by=request.requested_by if request is not None else None,
        result=result,
    )
    session.commit()
    session.expire_all()

    site_detail = get_site(session, site_id=site_id)
    if site_detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Site detail not found after extant-permission check.",
        )
    return site_detail
