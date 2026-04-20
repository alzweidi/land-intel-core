from __future__ import annotations

from uuid import UUID

from landintel.domain.models import SiteCandidate
from landintel.jobs.service import enqueue_site_scenario_suggest_refresh_job
from landintel.sites.service import (
    SiteBuildError,
    build_or_refresh_site_from_cluster,
    refresh_site_links_and_status,
)
from sqlalchemy import select


def run_site_build_job(*, session, job) -> None:
    cluster_id = UUID(str(job.payload_json["cluster_id"]))
    site = build_or_refresh_site_from_cluster(
        session=session,
        cluster_id=cluster_id,
        requested_by=job.requested_by or "worker",
    )
    enqueue_site_scenario_suggest_refresh_job(
        session=session,
        site_id=str(site.id),
        requested_by=job.requested_by or "worker",
    )
    session.flush()


def run_site_lpa_refresh_job(*, session, job) -> None:
    site = _load_site(session=session, site_id=UUID(str(job.payload_json["site_id"])))
    refresh_site_links_and_status(session=session, site=site)
    session.flush()


def run_site_title_refresh_job(*, session, job) -> None:
    site = _load_site(session=session, site_id=UUID(str(job.payload_json["site_id"])))
    refresh_site_links_and_status(session=session, site=site)
    session.flush()


def _load_site(*, session, site_id: UUID) -> SiteCandidate:
    site = session.execute(
        select(SiteCandidate).where(SiteCandidate.id == site_id)
    ).scalar_one_or_none()
    if site is None:
        raise SiteBuildError(f"Site '{site_id}' was not found.")
    return site
