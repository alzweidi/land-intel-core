from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest
from landintel.domain.enums import (
    GeomConfidence,
    GeomSourceType,
    ListingClusterStatus,
    ListingStatus,
    ListingType,
    PriceBasisType,
    SiteStatus,
    SourceFreshnessStatus,
    SourceParseStatus,
)
from landintel.domain.models import (
    ListingCluster,
    ListingClusterMember,
    ListingItem,
    ListingSnapshot,
    RawAsset,
    SiteCandidate,
    SourceSnapshot,
)
from landintel.geospatial.geometry import normalize_geojson_geometry
from landintel.scenarios import normalize as scenario_normalize
from landintel.services import sites_readback
from landintel.sites import service as sites_service
from landintel.sites.service import (
    SiteBuildError,
    build_or_refresh_site_from_cluster,
    refresh_site_lpa_links,
    save_site_geometry_revision,
)


def _fixed_uuid(seed: int) -> UUID:
    return UUID(f"00000000-0000-0000-0000-{seed:012d}")


def _point_geometry(*, lon: float, lat: float):
    return normalize_geojson_geometry(
        geometry_payload={"type": "Point", "coordinates": [lon, lat]},
        source_epsg=4326,
        source_type=GeomSourceType.POINT_ONLY,
    )


def _polygon_geometry(*, west: float, south: float, east: float, north: float):
    return normalize_geojson_geometry(
        geometry_payload={
            "type": "Polygon",
            "coordinates": [
                [
                    [west, south],
                    [east, south],
                    [east, north],
                    [west, north],
                    [west, south],
                ]
            ],
        },
        source_epsg=4326,
        source_type=GeomSourceType.ANALYST_DRAWN,
    )


def _make_source_snapshot(*, snapshot_id: UUID, source_name: str) -> SourceSnapshot:
    return SourceSnapshot(
        id=snapshot_id,
        source_family="PUBLIC_PAGE",
        source_name=source_name,
        source_uri=f"https://example.test/{source_name}/{snapshot_id}",
        acquired_at=datetime(2026, 4, 15, 10, 0, tzinfo=UTC),
        effective_from=None,
        effective_to=None,
        schema_hash=f"schema-{snapshot_id}",
        content_hash=f"content-{snapshot_id}",
        coverage_note="fixture coverage",
        freshness_status=SourceFreshnessStatus.FRESH,
        parse_status=SourceParseStatus.PARSED,
        parse_error_text=None,
        manifest_json={"source_name": source_name},
    )


def _make_listing_bundle(
    *,
    cluster_id: UUID,
    listing_id: UUID,
    snapshot_id: UUID,
    source_snapshot: SourceSnapshot,
    source,
    canonical_url: str,
    normalized_address: str | None = None,
    headline: str | None = None,
    address_text: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    current_snapshot_id: UUID | None = None,
    raw_record_json: dict[str, object] | None = None,
    brochure_asset: RawAsset | None = None,
) -> tuple[ListingCluster, ListingItem, ListingSnapshot, ListingClusterMember]:
    cluster = ListingCluster(
        id=cluster_id,
        cluster_key=f"cluster-{cluster_id}",
        cluster_status=ListingClusterStatus.ACTIVE,
    )
    listing = ListingItem(
        id=listing_id,
        source_id=source.id,
        source=source,
        source_listing_id=f"listing-{listing_id}",
        canonical_url=canonical_url,
        listing_type=ListingType.LAND,
        first_seen_at=datetime(2026, 4, 14, 10, 0, tzinfo=UTC),
        last_seen_at=datetime(2026, 4, 15, 10, 0, tzinfo=UTC),
        latest_status=ListingStatus.LIVE,
        normalized_address=normalized_address,
        search_text=normalized_address or headline or canonical_url,
    )
    snapshot = ListingSnapshot(
        id=snapshot_id,
        listing_item=listing,
        source_snapshot=source_snapshot,
        observed_at=datetime(2026, 4, 15, 11, 0, tzinfo=UTC),
        headline=headline,
        description_text="Fixture listing",
        guide_price_gbp=150_000,
        price_basis_type=PriceBasisType.GUIDE_PRICE,
        status=ListingStatus.LIVE,
        auction_date=date(2026, 4, 20),
        address_text=address_text,
        normalized_address=normalized_address,
        lat=lat,
        lon=lon,
        brochure_asset=brochure_asset,
        raw_record_json=raw_record_json or {},
        search_text=normalized_address or headline or canonical_url,
    )
    member = ListingClusterMember(
        id=uuid4(),
        listing_cluster=cluster,
        listing_item=listing,
        confidence=0.9,
        rules_json={"fixture": True},
    )
    listing.snapshots = [snapshot]
    listing.current_snapshot_id = (
        current_snapshot_id if current_snapshot_id is not None else snapshot.id
    )
    cluster.members = [member]
    listing.cluster_members = [member]
    return cluster, listing, snapshot, member


def _make_site_candidate(*, site_id: UUID, cluster_id: UUID, lon: float, lat: float):
    prepared = _point_geometry(lon=lon, lat=lat)
    return SiteCandidate(
        id=site_id,
        listing_cluster_id=cluster_id,
        display_name="Fixture site",
        borough_id="camden",
        geom_27700=prepared.geom_27700_wkt,
        geom_4326=prepared.geom_4326,
        geom_hash=prepared.geom_hash,
        geom_source_type=GeomSourceType.POINT_ONLY,
        geom_confidence=GeomConfidence.INSUFFICIENT,
        site_area_sqm=0.0,
        site_status=SiteStatus.INSUFFICIENT_GEOMETRY,
        manual_review_required=False,
        warning_json={},
    )


def test_build_or_refresh_site_from_cluster_covers_geometry_and_refresh_branches(
    db_session,
    seed_listing_sources,
    seed_reference_data,
    seed_planning_data,
    monkeypatch,
):
    del seed_reference_data
    del seed_planning_data

    manual_source = seed_listing_sources["manual_url"]
    source_snapshot = _make_source_snapshot(
        snapshot_id=_fixed_uuid(101),
        source_name=manual_source.name,
    )
    raw_asset = RawAsset(
        id=_fixed_uuid(102),
        source_snapshot_id=source_snapshot.id,
        asset_type="brochure",
        original_url="https://example.test/brochure.pdf",
        storage_path="/tmp/brochure.pdf",
        mime_type="application/pdf",
        content_sha256="a" * 64,
        size_bytes=1024,
        fetched_at=datetime(2026, 4, 15, 10, 5, tzinfo=UTC),
    )
    db_session.add_all([source_snapshot, raw_asset])
    db_session.flush()

    bbox_cluster, bbox_listing, bbox_snapshot, _ = _make_listing_bundle(
        cluster_id=_fixed_uuid(11),
        listing_id=_fixed_uuid(12),
        snapshot_id=_fixed_uuid(13),
        source_snapshot=source_snapshot,
        source=manual_source,
        canonical_url="https://example.test/listings/bbox",
        address_text=None,
        headline=None,
        normalized_address=None,
        lat=51.5362,
        lon=-0.1421,
        current_snapshot_id=None,
        raw_record_json={"bbox_4326": [-0.1423, 51.5360, -0.1419, 51.5364]},
        brochure_asset=raw_asset,
    )
    geometry_cluster, geometry_listing, geometry_snapshot, _ = _make_listing_bundle(
        cluster_id=_fixed_uuid(21),
        listing_id=_fixed_uuid(22),
        snapshot_id=_fixed_uuid(23),
        source_snapshot=source_snapshot,
        source=manual_source,
        canonical_url="https://example.test/listings/geometry",
        address_text="1 Geometry Road",
        headline=None,
        normalized_address="1 geometry road london nw1 7aa",
        lat=51.5362,
        lon=-0.1421,
        raw_record_json={
            "geometry_4326": _polygon_geometry(
                west=-0.1423,
                south=51.5360,
                east=-0.1419,
                north=51.5364,
            ).geom_4326,
        },
    )
    point_cluster, point_listing, point_snapshot, _ = _make_listing_bundle(
        cluster_id=_fixed_uuid(31),
        listing_id=_fixed_uuid(32),
        snapshot_id=_fixed_uuid(33),
        source_snapshot=source_snapshot,
        source=manual_source,
        canonical_url="https://example.test/listings/point",
        address_text=None,
        headline=None,
        normalized_address=None,
        lat=0.0,
        lon=0.0,
        raw_record_json={},
    )
    title_cluster, title_listing, title_snapshot, _ = _make_listing_bundle(
        cluster_id=_fixed_uuid(41),
        listing_id=_fixed_uuid(42),
        snapshot_id=_fixed_uuid(43),
        source_snapshot=source_snapshot,
        source=manual_source,
        canonical_url="https://example.test/listings/title",
        normalized_address="12 example road london nw1 7aa",
        address_text=None,
        headline=None,
        lat=None,
        lon=None,
        current_snapshot_id=None,
        raw_record_json={},
    )
    evidence_cluster = ListingCluster(
        id=_fixed_uuid(45),
        cluster_key="cluster-evidence",
        cluster_status=ListingClusterStatus.ACTIVE,
    )
    evidence_listing = ListingItem(
        id=_fixed_uuid(46),
        source_id=manual_source.id,
        source=manual_source,
        source_listing_id="listing-46",
        canonical_url="https://example.test/listings/evidence",
        listing_type=ListingType.LAND,
        first_seen_at=datetime(2026, 4, 14, 10, 0, tzinfo=UTC),
        last_seen_at=datetime(2026, 4, 15, 10, 0, tzinfo=UTC),
        latest_status=ListingStatus.LIVE,
        normalized_address=None,
        search_text="evidence",
    )
    evidence_member = ListingClusterMember(
        id=uuid4(),
        listing_cluster=evidence_cluster,
        listing_item=evidence_listing,
        confidence=0.9,
        rules_json={"fixture": True},
    )
    evidence_cluster.members = [evidence_member]
    evidence_listing.cluster_members = [evidence_member]
    evidence_listing.snapshots = []
    evidence_listing.current_snapshot_id = None
    empty_cluster = ListingCluster(
        id=_fixed_uuid(51),
        cluster_key="cluster-empty",
        cluster_status=ListingClusterStatus.ACTIVE,
    )

    db_session.add_all(
        [
            bbox_cluster,
            bbox_listing,
            bbox_snapshot,
            geometry_cluster,
            geometry_listing,
            geometry_snapshot,
            point_cluster,
            point_listing,
            point_snapshot,
            title_cluster,
            title_listing,
            title_snapshot,
            evidence_cluster,
            evidence_listing,
            evidence_member,
            empty_cluster,
        ]
    )
    db_session.commit()

    with pytest.raises(SiteBuildError, match="was not found"):
        build_or_refresh_site_from_cluster(
            session=db_session,
            cluster_id=_fixed_uuid(999),
            requested_by="pytest",
        )

    with pytest.raises(SiteBuildError, match="has no members"):
        build_or_refresh_site_from_cluster(
            session=db_session,
            cluster_id=empty_cluster.id,
            requested_by="pytest",
        )

    bbox_site = build_or_refresh_site_from_cluster(
        session=db_session,
        cluster_id=bbox_cluster.id,
        requested_by="pytest",
    )
    assert bbox_site.display_name == "https://example.test/listings/bbox"
    assert bbox_site.current_listing_id == bbox_listing.id
    assert bbox_site.current_price_gbp == 150_000
    assert bbox_site.current_price_basis_type == PriceBasisType.GUIDE_PRICE
    assert bbox_site.geom_source_type == GeomSourceType.APPROXIMATE_BBOX
    assert bbox_site.geometry_revisions[0].raw_asset_id == raw_asset.id

    stale_calls: list[tuple[str | None, UUID]] = []

    def _record_stale(*, session, site, requested_by):
        del session
        stale_calls.append((requested_by, site.id))

    monkeypatch.setattr(
        scenario_normalize,
        "mark_site_scenarios_stale_for_geometry_change",
        _record_stale,
    )

    geometry_snapshot.raw_record_json = {
        "geometry_4326": _polygon_geometry(
            west=-0.1426,
            south=51.5360,
            east=-0.1416,
            north=51.5364,
        ).geom_4326,
    }
    db_session.commit()

    refreshed = build_or_refresh_site_from_cluster(
        session=db_session,
        cluster_id=geometry_cluster.id,
        requested_by="pytest",
    )
    assert refreshed.display_name == "1 Geometry Road"
    assert refreshed.geom_source_type == GeomSourceType.SOURCE_POLYGON
    assert refreshed.geom_hash != bbox_site.geom_hash
    first_revision_count = len(refreshed.geometry_revisions)
    assert stale_calls == []

    refreshed_again = build_or_refresh_site_from_cluster(
        session=db_session,
        cluster_id=geometry_cluster.id,
        requested_by="pytest",
    )
    assert refreshed_again.id == refreshed.id
    assert len(refreshed_again.geometry_revisions) == first_revision_count

    point_site = build_or_refresh_site_from_cluster(
        session=db_session,
        cluster_id=point_cluster.id,
        requested_by="pytest",
    )
    assert point_site.geom_source_type == GeomSourceType.POINT_ONLY
    assert point_site.display_name == "https://example.test/listings/point"

    title_site = build_or_refresh_site_from_cluster(
        session=db_session,
        cluster_id=title_cluster.id,
        requested_by="pytest",
    )
    assert title_site.display_name == "https://example.test/listings/title"
    assert title_site.current_listing_id == title_listing.id

    with pytest.raises(SiteBuildError, match="was available for this cluster"):
        build_or_refresh_site_from_cluster(
            session=db_session,
            cluster_id=evidence_cluster.id,
            requested_by="pytest",
        )

    assert refresh_site_lpa_links(
        session=db_session,
        site=SiteCandidate(
            id=_fixed_uuid(62),
            listing_cluster_id=bbox_cluster.id,
            display_name="Outside site",
            borough_id="camden",
            geom_27700=_point_geometry(lon=0.0, lat=0.0).geom_27700_wkt,
            geom_4326=_point_geometry(lon=0.0, lat=0.0).geom_4326,
            geom_hash=_point_geometry(lon=0.0, lat=0.0).geom_hash,
            geom_source_type=GeomSourceType.POINT_ONLY,
            geom_confidence=GeomConfidence.INSUFFICIENT,
            site_area_sqm=0.0,
            site_status=SiteStatus.INSUFFICIENT_GEOMETRY,
            manual_review_required=False,
            warning_json={},
        ),
    ) == [
        {
            "code": "LPA_UNRESOLVED",
            "message": "No borough/LPA boundary intersected the current site geometry.",
        }
    ]


def test_save_site_geometry_revision_point_lpa_and_rulepack_branches(
    db_session,
    seed_reference_data,
    seed_planning_data,
    monkeypatch,
):
    del seed_reference_data
    del seed_planning_data

    source_snapshot = _make_source_snapshot(
        snapshot_id=_fixed_uuid(201),
        source_name="manual_url",
    )
    db_session.add(source_snapshot)
    db_session.flush()

    cluster = ListingCluster(
        id=_fixed_uuid(202),
        cluster_key="cluster-202",
        cluster_status=ListingClusterStatus.ACTIVE,
    )
    revision_cluster = ListingCluster(
        id=_fixed_uuid(205),
        cluster_key="cluster-205",
        cluster_status=ListingClusterStatus.ACTIVE,
    )
    lpa_site = _make_site_candidate(
        site_id=_fixed_uuid(203),
        cluster_id=cluster.id,
        lon=-0.1421,
        lat=51.5362,
    )
    revision_site = _make_site_candidate(
        site_id=_fixed_uuid(204),
        cluster_id=revision_cluster.id,
        lon=-0.1421,
        lat=51.5362,
    )
    db_session.add_all([cluster, revision_cluster, lpa_site, revision_site])
    db_session.commit()

    lpa_warnings = refresh_site_lpa_links(session=db_session, site=lpa_site)
    assert lpa_warnings == []
    assert lpa_site.borough_id == "camden"

    stale_calls: list[tuple[str | None, UUID]] = []

    def _record_stale(*, session, site, requested_by):
        del session
        stale_calls.append((requested_by, site.id))

    monkeypatch.setattr(
        scenario_normalize,
        "mark_site_scenarios_stale_for_geometry_change",
        _record_stale,
    )

    revision_ids = iter([_fixed_uuid(301), _fixed_uuid(301), _fixed_uuid(302)])
    monkeypatch.setattr(sites_service.uuid, "uuid4", lambda: next(revision_ids))

    first = save_site_geometry_revision(
        session=db_session,
        site_id=revision_site.id,
        geom_4326={
            "type": "Polygon",
            "coordinates": [
                [
                    [-0.1426, 51.5360],
                    [-0.1416, 51.5360],
                    [-0.1416, 51.5364],
                    [-0.1426, 51.5364],
                    [-0.1426, 51.5360],
                ]
            ],
        },
        source_type=GeomSourceType.ANALYST_DRAWN,
        confidence=None,
        reason="Analyst redraw",
        created_by="pytest",
        raw_asset_id=None,
    )
    assert first.geom_source_type == GeomSourceType.ANALYST_DRAWN
    assert first.geom_confidence == GeomConfidence.HIGH
    assert stale_calls == [("pytest", revision_site.id)]

    duplicate = save_site_geometry_revision(
        session=db_session,
        site_id=revision_site.id,
        geom_4326={
            "type": "Polygon",
            "coordinates": [
                [
                    [-0.1426, 51.5360],
                    [-0.1416, 51.5360],
                    [-0.1416, 51.5364],
                    [-0.1426, 51.5364],
                    [-0.1426, 51.5360],
                ]
            ],
        },
        source_type=GeomSourceType.ANALYST_DRAWN,
        confidence=None,
        reason="Duplicate redraw",
        created_by="pytest",
        raw_asset_id=None,
    )
    assert duplicate.geom_hash == first.geom_hash

    approximate_bbox = save_site_geometry_revision(
        session=db_session,
        site_id=revision_site.id,
        geom_4326={
            "type": "Polygon",
            "coordinates": [
                [
                    [-0.1427, 51.5360],
                    [-0.1415, 51.5360],
                    [-0.1415, 51.5365],
                    [-0.1427, 51.5365],
                    [-0.1427, 51.5360],
                ]
            ],
        },
        source_type=GeomSourceType.APPROXIMATE_BBOX,
        confidence=None,
        reason="Approximate bbox",
        created_by="pytest",
        raw_asset_id=None,
    )
    assert approximate_bbox.geom_source_type == GeomSourceType.APPROXIMATE_BBOX
    assert approximate_bbox.geom_confidence == GeomConfidence.LOW
    assert len(stale_calls) == 2

    assert sites_readback._rulepack_citations_complete(None) is False
    assert sites_readback._rulepack_citations_complete({}) is False
    assert sites_readback._rulepack_citations_complete({"citations": []}) is False
    assert sites_readback._rulepack_citations_complete({"citations": [1]}) is False
    assert (
        sites_readback._rulepack_citations_complete(
            {
                "citations": [
                    {
                        "label": "",
                        "source_family": "BOROUGH_REGISTER",
                        "effective_date": "2026-04-01",
                        "source_url": "https://example.test/rule",
                    }
                ]
            }
        )
        is False
    )
    assert (
        sites_readback._rulepack_citations_complete(
            {
                "citations": [
                    {
                        "label": "Rule",
                        "source_family": "",
                        "effective_date": "2026-04-01",
                        "source_url": "https://example.test/rule",
                    }
                ]
            }
        )
        is False
    )
    assert (
        sites_readback._rulepack_citations_complete(
            {
                "citations": [
                    {
                        "label": "Rule",
                        "source_family": "BOROUGH_REGISTER",
                        "effective_date": "",
                        "source_url": "https://example.test/rule",
                    }
                ]
            }
        )
        is False
    )
    assert (
        sites_readback._rulepack_citations_complete(
            {
                "citations": [
                    {
                        "label": "Rule",
                        "source_family": "BOROUGH_REGISTER",
                        "effective_date": "2026-04-01",
                    }
                ]
            }
        )
        is False
    )
    assert (
        sites_readback._rulepack_citations_complete(
            {
                "citations": [
                    {
                        "label": "Rule",
                        "source_family": "BOROUGH_REGISTER",
                        "effective_date": "2026-04-01",
                        "source_url": "https://example.test/rule",
                    }
                ]
            }
        )
        is True
    )
