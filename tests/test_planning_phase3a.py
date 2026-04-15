from __future__ import annotations

import io
import uuid

import respx
from httpx import Response
from landintel.domain.enums import (
    EligibilityStatus,
    ExtantPermissionStatus,
    GeomConfidence,
    GeomSourceType,
    ListingClusterStatus,
    PriceBasisType,
)
from landintel.domain.models import (
    ListingCluster,
    PlanningApplication,
    PlanningApplicationDocument,
    RawAsset,
    SiteCandidate,
)
from landintel.geospatial.geometry import normalize_geojson_geometry
from landintel.planning.enrich import refresh_site_planning_context
from landintel.planning.extant_permission import evaluate_site_extant_permission

from tests.fixtures.listing_fixtures import (
    CSV_IMPORT_TEXT,
    MANUAL_BROCHURE_PDF,
    MANUAL_BROCHURE_URL,
    MANUAL_LISTING_HTML,
    MANUAL_LISTING_URL,
    MANUAL_MAP_PDF,
    MANUAL_MAP_URL,
    PUBLIC_BROCHURE_PDF,
    PUBLIC_BROCHURE_URL,
    PUBLIC_INDEX_HTML,
    PUBLIC_INDEX_URL,
    PUBLIC_LISTING_HTML,
    PUBLIC_LISTING_URL,
)


def _make_site(
    db_session, *, site_id: uuid.UUID, cluster_key: str, geometry_4326: dict, borough_id: str
) -> SiteCandidate:
    cluster = ListingCluster(
        id=uuid.uuid4(),
        cluster_key=cluster_key,
        cluster_status=ListingClusterStatus.SINGLETON,
    )
    db_session.add(cluster)
    db_session.flush()

    prepared = normalize_geojson_geometry(
        geometry_payload=geometry_4326,
        source_epsg=4326,
        source_type=GeomSourceType.ANALYST_DRAWN,
        confidence=GeomConfidence.HIGH,
    )
    site = SiteCandidate(
        id=site_id,
        listing_cluster_id=cluster.id,
        display_name=cluster_key,
        borough_id=borough_id,
        geom_27700=prepared.geom_27700_wkt,
        geom_4326=prepared.geom_4326,
        geom_hash=prepared.geom_hash,
        geom_source_type=prepared.geom_source_type,
        geom_confidence=prepared.geom_confidence,
        site_area_sqm=prepared.area_sqm,
        current_price_basis_type=PriceBasisType.UNKNOWN,
    )
    db_session.add(site)
    db_session.flush()
    return site


@respx.mock
def _build_camden_site(client, drain_jobs):
    respx.get(MANUAL_LISTING_URL).mock(
        return_value=Response(200, text=MANUAL_LISTING_HTML, headers={"content-type": "text/html"})
    )
    respx.get(MANUAL_BROCHURE_URL).mock(
        return_value=Response(
            200, content=MANUAL_BROCHURE_PDF, headers={"content-type": "application/pdf"}
        )
    )
    respx.get(MANUAL_MAP_URL).mock(
        return_value=Response(
            200, content=MANUAL_MAP_PDF, headers={"content-type": "application/pdf"}
        )
    )
    respx.get(PUBLIC_INDEX_URL).mock(
        return_value=Response(200, text=PUBLIC_INDEX_HTML, headers={"content-type": "text/html"})
    )
    respx.get(PUBLIC_LISTING_URL).mock(
        return_value=Response(200, text=PUBLIC_LISTING_HTML, headers={"content-type": "text/html"})
    )
    respx.get(PUBLIC_BROCHURE_URL).mock(
        return_value=Response(
            200, content=PUBLIC_BROCHURE_PDF, headers={"content-type": "application/pdf"}
        )
    )

    client.post(
        "/api/listings/intake/url",
        json={"url": MANUAL_LISTING_URL, "source_name": "manual_url", "requested_by": "pytest"},
    )
    client.post(
        "/api/listings/connectors/public_page_fixture/run",
        json={"requested_by": "pytest"},
    )
    processed = drain_jobs(max_iterations=12)
    assert processed >= 3

    cluster_payload = client.get("/api/listing-clusters").json()
    active_cluster = next(
        item for item in cluster_payload["items"] if item["cluster_status"] == "ACTIVE"
    )
    response = client.post(
        f"/api/sites/from-cluster/{active_cluster['id']}",
        json={"requested_by": "pytest"},
    )
    assert response.status_code == 200
    return response.json()


def _build_southwark_site(client, drain_jobs):
    upload = io.BytesIO(CSV_IMPORT_TEXT.encode("utf-8"))
    response = client.post(
        "/api/listings/import/csv",
        data={"source_name": "csv_import", "requested_by": "pytest"},
        files={"file": ("southwark.csv", upload, "text/csv")},
    )
    assert response.status_code == 202
    processed = drain_jobs(max_iterations=8)
    assert processed >= 2

    listings = client.get("/api/listings?source=csv_import").json()["items"]
    listing = next(
        (
            item
            for item in listings
            if "peckham" in str(item.get("headline", "")).lower()
            or "southwark" in str(item.get("borough", "")).lower()
        ),
        listings[0],
    )
    build = client.post(
        f"/api/sites/from-cluster/{listing['cluster_id']}",
        json={"requested_by": "pytest"},
    )
    assert build.status_code == 200
    return build.json()


def test_camden_site_planning_enrichment_and_evidence(
    client,
    drain_jobs,
    seed_listing_sources,
    seed_planning_data,
):
    del seed_listing_sources
    del seed_planning_data

    payload = _build_camden_site(client, drain_jobs)

    assert payload["planning_history"]
    assert payload["policy_facts"]
    assert payload["constraint_facts"]
    assert payload["source_coverage"]
    assert payload["baseline_pack"]["borough_id"] == "camden"
    assert (
        payload["extant_permission"]["status"] == ExtantPermissionStatus.NO_ACTIVE_PERMISSION_FOUND
    )
    assert payload["evidence"]["for"]
    assert payload["evidence"]["against"]
    assert payload["evidence"]["unknown"]


def test_extant_permission_endpoint_rechecks_camden_site(
    client,
    drain_jobs,
    seed_listing_sources,
    seed_planning_data,
):
    del seed_listing_sources
    del seed_planning_data
    payload = _build_camden_site(client, drain_jobs)

    response = client.post(
        f"/api/sites/{payload['id']}/extant-permission-check",
        json={"requested_by": "pytest"},
    )
    assert response.status_code == 200
    detail = response.json()
    assert (
        detail["extant_permission"]["status"] == ExtantPermissionStatus.NO_ACTIVE_PERMISSION_FOUND
    )
    assert any(item["topic"] == "source_coverage" for item in detail["evidence"]["unknown"])


def test_brownfield_part1_is_not_treated_as_pip(seed_planning_data, db_session):
    del seed_planning_data
    site = _make_site(
        db_session,
        site_id=uuid.uuid4(),
        cluster_key="camden-part1-site",
        borough_id="camden",
        geometry_4326={
            "type": "Polygon",
            "coordinates": [
                [
                    [-0.14256, 51.53601],
                    [-0.14156, 51.53601],
                    [-0.14156, 51.53633],
                    [-0.14256, 51.53633],
                    [-0.14256, 51.53601],
                ]
            ],
        },
    )
    refresh_site_planning_context(session=db_session, site=site, requested_by="pytest")
    result = evaluate_site_extant_permission(session=db_session, site=site)
    assert result.status == ExtantPermissionStatus.NO_ACTIVE_PERMISSION_FOUND
    assert any("Historic or non-exclusionary" in reason for reason in result.reasons)


def test_brownfield_part2_active_is_exclusionary(
    client,
    drain_jobs,
    seed_listing_sources,
    seed_planning_data,
):
    del seed_listing_sources
    del seed_planning_data
    payload = _build_southwark_site(client, drain_jobs)
    assert (
        payload["extant_permission"]["status"]
        == ExtantPermissionStatus.ACTIVE_EXTANT_PERMISSION_FOUND
    )
    assert any(item["topic"] == "brownfield" for item in payload["evidence"]["against"])


def test_active_permission_outranks_lapsed_history(seed_planning_data, db_session):
    del seed_planning_data
    site = _make_site(
        db_session,
        site_id=uuid.uuid4(),
        cluster_key="camden-active-check",
        borough_id="camden",
        geometry_4326={
            "type": "Polygon",
            "coordinates": [
                [
                    [-0.14256, 51.53600],
                    [-0.14157, 51.53600],
                    [-0.14157, 51.53634],
                    [-0.14256, 51.53634],
                    [-0.14256, 51.53600],
                ]
            ],
        },
    )
    refresh_site_planning_context(session=db_session, site=site, requested_by="pytest")
    initial = evaluate_site_extant_permission(session=db_session, site=site)
    assert initial.status == ExtantPermissionStatus.NO_ACTIVE_PERMISSION_FOUND

    active_app = PlanningApplication(
        id=uuid.uuid4(),
        borough_id="camden",
        source_system="BOROUGH_REGISTER",
        source_snapshot_id=site.planning_links[0].planning_application.source_snapshot_id,
        external_ref="CAM/2026/9999/A",
        application_type="FULL",
        proposal_description="Active full residential permission over the example site.",
        decision_type="FULL_RESIDENTIAL",
        status="APPROVED",
        route_normalized="FULL",
        source_priority=100,
        source_url="https://camden.example/planning/CAM-2026-9999-A",
        site_geom_27700=site.geom_27700,
        site_geom_4326=site.geom_4326,
        raw_record_json={"dwelling_use": "C3", "active_extant": True, "expiry_date": "2028-01-01"},
    )
    db_session.add(active_app)
    db_session.flush()
    refresh_site_planning_context(session=db_session, site=site, requested_by="pytest")
    updated = evaluate_site_extant_permission(session=db_session, site=site)
    assert updated.status == ExtantPermissionStatus.ACTIVE_EXTANT_PERMISSION_FOUND


def test_missing_coverage_never_returns_false_clean_permission_state(
    seed_planning_data, db_session
):
    del seed_planning_data
    site = _make_site(
        db_session,
        site_id=uuid.uuid4(),
        cluster_key="islington-gap-site",
        borough_id="islington",
        geometry_4326={
            "type": "Polygon",
            "coordinates": [
                [
                    [-0.14080, 51.53600],
                    [-0.13990, 51.53600],
                    [-0.13990, 51.53630],
                    [-0.14080, 51.53630],
                    [-0.14080, 51.53600],
                ]
            ],
        },
    )
    refresh_site_planning_context(session=db_session, site=site, requested_by="pytest")
    result = evaluate_site_extant_permission(session=db_session, site=site)
    assert result.status == ExtantPermissionStatus.UNRESOLVED_MISSING_MANDATORY_SOURCE
    assert result.eligibility_status == EligibilityStatus.ABSTAIN
    assert result.status != ExtantPermissionStatus.NO_ACTIVE_PERMISSION_FOUND


def test_data_health_exposes_coverage_and_baseline_pack(
    client,
    seed_planning_data,
):
    del seed_planning_data
    response = client.get("/api/health/data")
    assert response.status_code == 200
    payload = response.json()
    assert payload["coverage"]
    assert any(item["source_family"] == "BOROUGH_REGISTER" for item in payload["coverage"])
    assert payload["baseline_packs"]


def test_planning_documents_reference_persisted_raw_assets(seed_planning_data, db_session):
    del seed_planning_data
    documents = db_session.query(PlanningApplicationDocument).all()
    assert documents
    for document in documents:
        assert db_session.get(RawAsset, document.asset_id) is not None
