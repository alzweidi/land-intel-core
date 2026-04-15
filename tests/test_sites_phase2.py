from __future__ import annotations

import uuid

import respx
from httpx import Response
from landintel.domain.enums import GeomConfidence, GeomSourceType, ListingClusterStatus
from landintel.domain.models import (
    AuditEvent,
    HmlrTitlePolygon,
    ListingCluster,
    LpaBoundary,
    SiteCandidate,
)
from landintel.geospatial.geometry import (
    build_point_geometry,
    normalize_geojson_geometry,
)
from landintel.geospatial.title_linkage import (
    build_title_union_geometry,
    compute_title_overlaps,
    select_title_candidates,
)
from landintel.jobs.service import enqueue_site_build_job
from landintel.sites.service import refresh_site_lpa_links

from tests.fixtures.listing_fixtures import (
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


def test_geometry_normalization_repair_hash_and_confidence() -> None:
    invalid_bowtie = {
        "type": "Polygon",
        "coordinates": [[
            [-0.1426, 51.5360],
            [-0.1418, 51.5364],
            [-0.1426, 51.5364],
            [-0.1418, 51.5360],
            [-0.1426, 51.5360],
        ]],
    }
    reversed_ring = {
        "type": "Polygon",
        "coordinates": [[
            [-0.1426, 51.5360],
            [-0.1418, 51.5360],
            [-0.1418, 51.5364],
            [-0.1426, 51.5364],
            [-0.1426, 51.5360],
        ]],
    }

    repaired = normalize_geojson_geometry(
        geometry_payload=invalid_bowtie,
        source_epsg=4326,
        source_type=GeomSourceType.ANALYST_DRAWN,
    )
    stable = normalize_geojson_geometry(
        geometry_payload=reversed_ring,
        source_epsg=4326,
        source_type=GeomSourceType.ANALYST_DRAWN,
    )

    assert repaired.area_sqm > 0
    assert repaired.geom_confidence == GeomConfidence.HIGH
    assert repaired.warnings
    assert stable.geom_hash == normalize_geojson_geometry(
        geometry_payload=reversed_ring,
        source_epsg=4326,
        source_type=GeomSourceType.ANALYST_DRAWN,
    ).geom_hash


def test_title_linkage_supports_multi_title(seed_reference_data, db_session) -> None:
    del seed_reference_data
    titles = db_session.query(HmlrTitlePolygon).order_by(HmlrTitlePolygon.title_number.asc()).all()
    point = build_point_geometry(lat=51.5362, lon=-0.1421).geom_27700

    candidates = select_title_candidates(
        title_polygons=titles,
        normalized_addresses=["12 example road london nw1 7aa"],
        point_geometries_27700=[point],
    )
    union = build_title_union_geometry(candidates)

    assert union is not None
    assert len(candidates) >= 2
    overlaps = compute_title_overlaps(
        site_geometry_27700=union.geom_27700,
        title_polygons=titles,
    )
    assert len(overlaps) >= 2
    assert overlaps[0].confidence in {GeomConfidence.HIGH, GeomConfidence.MEDIUM}


def test_lpa_trivial_and_material_overlap_thresholds(seed_reference_data, db_session) -> None:
    del seed_reference_data
    cluster_one = ListingCluster(
        id=uuid.uuid4(),
        cluster_key="test-trivial-lpa",
        cluster_status=ListingClusterStatus.SINGLETON,
    )
    cluster_two = ListingCluster(
        id=uuid.uuid4(),
        cluster_key="test-material-lpa",
        cluster_status=ListingClusterStatus.SINGLETON,
    )
    db_session.add_all([cluster_one, cluster_two])
    db_session.flush()

    trivial_site = SiteCandidate(
        id=uuid.uuid4(),
        listing_cluster_id=cluster_one.id,
        display_name="Trivial overlap site",
        geom_27700="",
        geom_4326={},
        geom_hash="",
        geom_source_type=GeomSourceType.ANALYST_DRAWN,
        geom_confidence=GeomConfidence.HIGH,
        site_area_sqm=0,
    )
    trivial_prepared = normalize_geojson_geometry(
        geometry_payload={
            "type": "Polygon",
            "coordinates": [[
                [-0.14200, 51.53600],
                [-0.14118, 51.53600],
                [-0.14118, 51.53634],
                [-0.14200, 51.53634],
                [-0.14200, 51.53600],
            ]],
        },
        source_epsg=4326,
        source_type=GeomSourceType.ANALYST_DRAWN,
    )
    trivial_site.geom_27700 = trivial_prepared.geom_27700_wkt
    trivial_site.geom_4326 = trivial_prepared.geom_4326
    trivial_site.geom_hash = trivial_prepared.geom_hash
    trivial_site.site_area_sqm = trivial_prepared.area_sqm
    db_session.add(trivial_site)
    db_session.flush()

    trivial_warnings = refresh_site_lpa_links(session=db_session, site=trivial_site)
    assert trivial_site.borough_id == "camden"
    assert any(item["code"] == "CROSS_LPA_TRIVIAL" for item in trivial_warnings)

    material_site = SiteCandidate(
        id=uuid.uuid4(),
        listing_cluster_id=cluster_two.id,
        display_name="Material overlap site",
        geom_27700="",
        geom_4326={},
        geom_hash="",
        geom_source_type=GeomSourceType.ANALYST_DRAWN,
        geom_confidence=GeomConfidence.HIGH,
        site_area_sqm=0,
    )
    material_prepared = normalize_geojson_geometry(
        geometry_payload={
            "type": "Polygon",
            "coordinates": [[
                [-0.14200, 51.53600],
                [-0.14100, 51.53600],
                [-0.14100, 51.53634],
                [-0.14200, 51.53634],
                [-0.14200, 51.53600],
            ]],
        },
        source_epsg=4326,
        source_type=GeomSourceType.ANALYST_DRAWN,
    )
    material_site.geom_27700 = material_prepared.geom_27700_wkt
    material_site.geom_4326 = material_prepared.geom_4326
    material_site.geom_hash = material_prepared.geom_hash
    material_site.site_area_sqm = material_prepared.area_sqm
    db_session.add(material_site)
    db_session.flush()

    material_warnings = refresh_site_lpa_links(session=db_session, site=material_site)
    assert material_site.borough_id is None
    assert any(item["code"] == "CROSS_LPA_MATERIAL" for item in material_warnings)


@respx.mock
def test_phase2_site_build_and_geometry_edit(
    client,
    session_factory,
    drain_jobs,
    seed_listing_sources,
    seed_reference_data,
) -> None:
    del seed_listing_sources
    del seed_reference_data

    respx.get(MANUAL_LISTING_URL).mock(
        return_value=Response(200, text=MANUAL_LISTING_HTML, headers={"content-type": "text/html"})
    )
    respx.get(MANUAL_BROCHURE_URL).mock(
        return_value=Response(
            200,
            content=MANUAL_BROCHURE_PDF,
            headers={"content-type": "application/pdf"},
        )
    )
    respx.get(MANUAL_MAP_URL).mock(
        return_value=Response(
            200,
            content=MANUAL_MAP_PDF,
            headers={"content-type": "application/pdf"},
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
            200,
            content=PUBLIC_BROCHURE_PDF,
            headers={"content-type": "application/pdf"},
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
    processed = drain_jobs(max_iterations=10)
    assert processed >= 3

    cluster_payload = client.get("/api/listing-clusters").json()
    active_cluster = next(
        item for item in cluster_payload["items"] if item["cluster_status"] == "ACTIVE"
    )

    build_response = client.post(
        f"/api/sites/from-cluster/{active_cluster['id']}",
        json={"requested_by": "pytest"},
    )
    assert build_response.status_code == 200
    site_payload = build_response.json()
    assert site_payload["current_geometry"]["geom_source_type"] == GeomSourceType.TITLE_UNION.value
    assert site_payload["borough_id"] == "camden"
    assert len(site_payload["title_links"]) >= 2
    assert any(item["code"] == "TITLE_LINK_INDICATIVE" for item in site_payload["warnings"])

    list_response = client.get("/api/sites")
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1

    edit_response = client.post(
        f"/api/sites/{site_payload['id']}/geometry",
        json={
            "geom_4326": {
                "type": "Polygon",
                "coordinates": [[
                    [-0.14250, 51.53600],
                    [-0.14160, 51.53600],
                    [-0.14160, 51.53638],
                    [-0.14250, 51.53638],
                    [-0.14250, 51.53600]
                ]]
            },
            "source_type": GeomSourceType.ANALYST_DRAWN.value,
            "created_by": "pytest-analyst",
            "reason": "Tightened site edge against title evidence."
        },
    )
    assert edit_response.status_code == 200
    edited_payload = edit_response.json()
    assert (
        edited_payload["current_geometry"]["geom_source_type"]
        == GeomSourceType.ANALYST_DRAWN.value
    )
    assert edited_payload["current_geometry"]["geom_confidence"] == GeomConfidence.HIGH.value
    assert len(edited_payload["geometry_revisions"]) >= 2

    with session_factory() as session:
        site = session.get(SiteCandidate, uuid.UUID(site_payload["id"]))
        assert site is not None
        assert session.query(AuditEvent).filter(AuditEvent.entity_id == str(site.id)).count() >= 2


@respx.mock
def test_site_build_job_creates_site(
    seed_listing_sources,
    seed_reference_data,
    session_factory,
    drain_jobs,
    client,
) -> None:
    del seed_listing_sources
    del seed_reference_data

    respx.get(MANUAL_LISTING_URL).mock(
        return_value=Response(200, text=MANUAL_LISTING_HTML, headers={"content-type": "text/html"})
    )
    respx.get(MANUAL_BROCHURE_URL).mock(
        return_value=Response(
            200,
            content=MANUAL_BROCHURE_PDF,
            headers={"content-type": "application/pdf"},
        )
    )
    respx.get(MANUAL_MAP_URL).mock(
        return_value=Response(
            200,
            content=MANUAL_MAP_PDF,
            headers={"content-type": "application/pdf"},
        )
    )
    client.post(
        "/api/listings/intake/url",
        json={"url": MANUAL_LISTING_URL, "source_name": "manual_url", "requested_by": "pytest"},
    )
    drain_jobs(max_iterations=5)

    with session_factory() as session:
        cluster = session.query(LpaBoundary).first()
        assert cluster is not None
        listing_cluster = client.get("/api/listing-clusters").json()["items"][0]
        enqueue_site_build_job(
            session=session,
            cluster_id=listing_cluster["id"],
            requested_by="pytest",
        )
        session.commit()

    processed = drain_jobs(max_iterations=5)
    assert processed >= 1
    assert client.get("/api/sites").json()["total"] == 1
