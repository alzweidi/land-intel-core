from __future__ import annotations

from uuid import UUID

from landintel.domain.models import SiteCandidate, SiteScenario
from landintel.scenarios.normalize import (
    ScenarioNormalizeError,
    mark_site_scenarios_stale_for_geometry_change,
    refresh_site_scenarios_after_rulepack_change,
)
from landintel.scenarios.suggest import refresh_scenario_evidence, suggest_scenarios_for_site
from landintel.sites.service import SiteBuildError
from sqlalchemy import select


def run_site_scenario_suggest_refresh_job(*, session, job) -> None:
    template_keys = [
        str(item)
        for item in list(job.payload_json.get("template_keys") or [])
        if str(item)
    ]
    suggest_scenarios_for_site(
        session=session,
        site_id=UUID(str(job.payload_json["site_id"])),
        requested_by=job.requested_by or "worker",
        template_keys=template_keys or None,
        manual_seed=bool(job.payload_json.get("manual_seed", False)),
    )
    session.flush()


def run_site_scenario_geometry_refresh_job(*, session, job) -> None:
    site = _load_site(session=session, site_id=UUID(str(job.payload_json["site_id"])))
    mark_site_scenarios_stale_for_geometry_change(
        session=session,
        site=site,
        requested_by=job.requested_by or "worker",
    )
    session.flush()


def run_borough_rulepack_scenario_refresh_job(*, session, job) -> None:
    borough_id = str(job.payload_json["borough_id"])
    sites = session.execute(
        select(SiteCandidate).where(SiteCandidate.borough_id == borough_id)
    ).scalars().all()
    for site in sites:
        refresh_site_scenarios_after_rulepack_change(
            session=session,
            site=site,
            requested_by=job.requested_by or "worker",
        )
    session.flush()


def run_scenario_evidence_refresh_job(*, session, job) -> None:
    scenario = session.get(SiteScenario, UUID(str(job.payload_json["scenario_id"])))
    if scenario is None:
        raise ScenarioNormalizeError(
            f"Scenario '{job.payload_json['scenario_id']}' was not found."
        )
    refresh_scenario_evidence(session=session, scenario=scenario)
    session.flush()


def _load_site(*, session, site_id: UUID) -> SiteCandidate:
    site = session.execute(
        select(SiteCandidate).where(SiteCandidate.id == site_id)
    ).scalar_one_or_none()
    if site is None:
        raise SiteBuildError(f"Site '{site_id}' was not found.")
    return site
