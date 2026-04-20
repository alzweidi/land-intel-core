from __future__ import annotations

from pathlib import Path
from uuid import UUID

from landintel.domain.models import SiteCandidate
from landintel.planning.enrich import refresh_site_planning_context
from landintel.planning.extant_permission import (
    audit_extant_permission_check,
    evaluate_site_extant_permission,
)
from landintel.planning.official_sources import (
    import_borough_register_fixture,
    import_brownfield_fixture,
    import_constraint_fixture,
    import_flood_fixture,
    import_heritage_article4_fixture,
    import_pld_fixture,
    import_policy_area_fixture,
)
from landintel.planning.reference_layers import import_baseline_pack_fixture
from landintel.sites.service import SiteBuildError
from sqlalchemy import select


def run_pld_ingest_job(*, session, job, storage) -> None:
    fixture_path = job.payload_json.get("fixture_path") or _fixture_path("pld_applications.json")
    import_pld_fixture(
        session=session,
        storage=storage,
        fixture_path=Path(str(fixture_path)),
        requested_by=job.requested_by or "worker",
    )


def run_borough_register_ingest_job(*, session, job, storage) -> None:
    fixture_path = job.payload_json.get("fixture_path") or _fixture_path(
        "borough_register_camden.json"
    )
    import_borough_register_fixture(
        session=session,
        storage=storage,
        fixture_path=Path(str(fixture_path)),
        requested_by=job.requested_by or "worker",
    )
    if bool(job.payload_json.get("include_supporting_layers", True)):
        import_brownfield_fixture(
            session=session,
            storage=storage,
            fixture_path=_fixture_path("brownfield_sites.geojson"),
            requested_by=job.requested_by or "worker",
        )
        import_policy_area_fixture(
            session=session,
            storage=storage,
            fixture_path=_fixture_path("policy_areas.geojson"),
            requested_by=job.requested_by or "worker",
        )
        import_constraint_fixture(
            session=session,
            storage=storage,
            fixture_path=_fixture_path("constraint_features.geojson"),
            requested_by=job.requested_by or "worker",
        )
        import_flood_fixture(
            session=session,
            storage=storage,
            fixture_path=_fixture_path("flood_zones.geojson"),
            requested_by=job.requested_by or "worker",
        )
        import_heritage_article4_fixture(
            session=session,
            storage=storage,
            fixture_path=_fixture_path("heritage_article4.geojson"),
            requested_by=job.requested_by or "worker",
        )
        import_baseline_pack_fixture(
            session=session,
            storage=storage,
            fixture_path=_fixture_path("baseline_packs.json"),
            requested_by=job.requested_by or "worker",
        )


def run_site_planning_enrich_job(*, session, job) -> None:
    site = _load_site(session=session, site_id=UUID(str(job.payload_json["site_id"])))
    refresh_site_planning_context(
        session=session,
        site=site,
        requested_by=job.requested_by or "worker",
    )
    session.flush()


def run_site_extant_permission_recheck_job(*, session, job) -> None:
    site = _load_site(session=session, site_id=UUID(str(job.payload_json["site_id"])))
    refresh_site_planning_context(
        session=session,
        site=site,
        requested_by=job.requested_by or "worker",
    )
    result = evaluate_site_extant_permission(session=session, site=site)
    audit_extant_permission_check(
        session=session,
        site=site,
        requested_by=job.requested_by or "worker",
        result=result,
    )
    session.flush()


def run_source_coverage_refresh_job(*, session, job) -> None:
    borough_id = (
        str(job.payload_json.get("borough_id"))
        if job.payload_json.get("borough_id")
        else None
    )
    stmt = select(SiteCandidate)
    if borough_id:
        stmt = stmt.where(SiteCandidate.borough_id == borough_id)

    sites = session.execute(stmt).scalars().all()
    for site in sites:
        refresh_site_planning_context(
            session=session,
            site=site,
            requested_by=job.requested_by or "worker",
        )
    session.flush()


def _load_site(*, session, site_id: UUID) -> SiteCandidate:
    site = session.execute(
        select(SiteCandidate).where(SiteCandidate.id == site_id)
    ).scalar_one_or_none()
    if site is None:
        raise SiteBuildError(f"Site '{site_id}' was not found.")
    return site


def _fixture_path(filename: str) -> Path:
    return Path(__file__).resolve().parents[4] / "tests" / "fixtures" / "planning" / filename
