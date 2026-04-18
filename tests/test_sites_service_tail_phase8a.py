from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest
from landintel.domain.enums import (
    GeomSourceType,
    ListingClusterStatus,
    ListingStatus,
    ListingType,
    PriceBasisType,
    SourceFreshnessStatus,
    SourceParseStatus,
)
from landintel.domain.models import (
    ListingCluster,
    ListingClusterMember,
    ListingItem,
    ListingSnapshot,
    RawAsset,
    SourceSnapshot,
)
from landintel.geospatial.geometry import normalize_geojson_geometry
from landintel.scenarios import normalize as scenario_normalize
from landintel.sites.service import (
    SiteBuildError,
    build_or_refresh_site_from_cluster,
    refresh_site_links_and_status,
    refresh_site_lpa_links,
    refresh_site_title_links,
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


def _make_raw_asset(*, asset_id: UUID, source_snapshot_id: UUID) -> RawAsset:
    return RawAsset(
        id=asset_id,
        source_snapshot_id=source_snapshot_id,
        asset_type="brochure",
        original_url=f"https://example.test/assets/{asset_id}.pdf",
        storage_path=f"/tmp/{asset_id}.pdf",
        mime_type="application/pdf",
        content_sha256=f"{asset_id.hex}"[:64].ljust(64, "0"),
        size_bytes=1024,
        fetched_at=datetime(2026, 4, 15, 10, 5, tzinfo=UTC),
    )


def _make_cluster_fixture(
    *,
    cluster_id: UUID,
    listing_id: UUID,
    snapshot_id: UUID,
    source_snapshot: SourceSnapshot,
    source,
    canonical_url: str,
    latest_status: ListingStatus = ListingStatus.LIVE,
    headline: str | None = None,
    address_text: str | None = None,
    normalized_address: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    raw_record_json: dict[str, object] | None = None,
    brochure_asset_id: UUID | None = None,
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
        latest_status=latest_status,
        normalized_address=normalized_address,
        search_text=normalized_address or headline or canonical_url,
    )
    snapshot = ListingSnapshot(
        id=snapshot_id,
        listing_item=listing,
        source_snapshot=source_snapshot,
        observed_at=datetime(2026, 4, 15, 11, 0, tzinfo=UTC),
        headline=headline,
        description_text=f"Fixture listing {listing_id}",
        guide_price_gbp=150_000,
        price_basis_type=PriceBasisType.GUIDE_PRICE,
        status=latest_status,
        auction_date=date(2026, 4, 20),
        address_text=address_text,
        normalized_address=normalized_address,
        lat=lat,
        lon=lon,
        brochure_asset_id=brochure_asset_id,
        raw_record_json=raw_record_json or {},
        search_text=normalized_address or headline or canonical_url,
    )
    member = ListingClusterMember(
        id=uuid4(),
        listing_cluster=cluster,
        listing_item=listing,
        confidence=0.95,
        rules_json={"fixture": True},
    )
    listing.snapshots = [snapshot]
    listing.current_snapshot_id = snapshot.id
    listing.cluster_members = [member]
    cluster.members = [member]
    return cluster, listing, snapshot, member


def test_build_or_refresh_site_from_cluster_covers_geometry_fallbacks_and_link_warnings(
    db_session,
    seed_listing_sources,
    seed_reference_data,
    seed_planning_data,
):
    del seed_reference_data
    del seed_planning_data

    manual_source = seed_listing_sources["manual_url"]
    source_snapshot = _make_source_snapshot(
        snapshot_id=_fixed_uuid(101),
        source_name=manual_source.name,
    )
    raw_asset = _make_raw_asset(asset_id=_fixed_uuid(102), source_snapshot_id=source_snapshot.id)
    db_session.add_all([source_snapshot, raw_asset])
    db_session.flush()

    geo_cluster, geo_listing, geo_snapshot, _ = _make_cluster_fixture(
        cluster_id=_fixed_uuid(11),
        listing_id=_fixed_uuid(12),
        snapshot_id=_fixed_uuid(13),
        source_snapshot=source_snapshot,
        source=manual_source,
        canonical_url="https://example.test/listings/geo",
        headline=None,
        address_text="1 Geometry Road",
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
        brochure_asset_id=raw_asset.id,
    )
    bbox_cluster, bbox_listing, bbox_snapshot, _ = _make_cluster_fixture(
        cluster_id=_fixed_uuid(21),
        listing_id=_fixed_uuid(22),
        snapshot_id=_fixed_uuid(23),
        source_snapshot=source_snapshot,
        source=manual_source,
        canonical_url="https://example.test/listings/bbox",
        headline="BBox headline",
        address_text=None,
        normalized_address=None,
        lat=51.5362,
        lon=-0.1421,
        raw_record_json={"bbox_4326": [-0.1423, 51.5360, -0.1419, 51.5364]},
    )
    outside_cluster, outside_listing, outside_snapshot, _ = _make_cluster_fixture(
        cluster_id=_fixed_uuid(31),
        listing_id=_fixed_uuid(32),
        snapshot_id=_fixed_uuid(33),
        source_snapshot=source_snapshot,
        source=manual_source,
        canonical_url="https://example.test/listings/outside",
        headline=None,
        address_text=None,
        normalized_address=None,
        lat=0.0,
        lon=0.0,
    )
    inside_cluster, inside_listing, inside_snapshot, _ = _make_cluster_fixture(
        cluster_id=_fixed_uuid(41),
        listing_id=_fixed_uuid(42),
        snapshot_id=_fixed_uuid(43),
        source_snapshot=source_snapshot,
        source=manual_source,
        canonical_url="https://example.test/listings/inside",
        headline=None,
        address_text=None,
        normalized_address=None,
        lat=51.5362,
        lon=-0.1421,
    )
    empty_cluster = ListingCluster(
        id=_fixed_uuid(51),
        cluster_key="cluster-empty",
        cluster_status=ListingClusterStatus.ACTIVE,
    )

    db_session.add_all(
        [
            geo_cluster,
            geo_listing,
            geo_snapshot,
            bbox_cluster,
            bbox_listing,
            bbox_snapshot,
            outside_cluster,
            outside_listing,
            outside_snapshot,
            inside_cluster,
            inside_listing,
            inside_snapshot,
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

    geo_site = build_or_refresh_site_from_cluster(
        session=db_session,
        cluster_id=geo_cluster.id,
        requested_by="pytest",
    )
    assert geo_site.display_name == "1 Geometry Road"
    assert geo_site.current_listing_id == geo_listing.id
    assert geo_site.current_price_gbp == 150_000
    assert geo_site.geometry_revisions[0].raw_asset_id == raw_asset.id

    bbox_site = build_or_refresh_site_from_cluster(
        session=db_session,
        cluster_id=bbox_cluster.id,
        requested_by="pytest",
    )
    assert bbox_site.display_name == "BBox headline"

    outside_site = build_or_refresh_site_from_cluster(
        session=db_session,
        cluster_id=outside_cluster.id,
        requested_by="pytest",
    )
    assert outside_site.display_name == "https://example.test/listings/outside"
    lpa_warnings = refresh_site_lpa_links(session=db_session, site=outside_site)
    title_warnings = refresh_site_title_links(session=db_session, site=outside_site)
    assert [item["code"] for item in lpa_warnings] == ["LPA_UNRESOLVED"]
    assert [item["code"] for item in title_warnings] == ["NO_TITLE_LINK"]
    refresh_site_links_and_status(session=db_session, site=outside_site)
    assert outside_site.manual_review_required is True

    inside_site = build_or_refresh_site_from_cluster(
        session=db_session,
        cluster_id=inside_cluster.id,
        requested_by="pytest",
    )
    assert inside_site.display_name == "https://example.test/listings/inside"
    assert inside_site.borough_id == "camden"
    assert refresh_site_lpa_links(session=db_session, site=inside_site) == []
    assert [
        item["code"] for item in refresh_site_title_links(session=db_session, site=inside_site)
    ] == ["TITLE_LINK_INDICATIVE"]
    refresh_site_links_and_status(session=db_session, site=inside_site)


def test_save_site_geometry_revision_and_refresh_cover_stale_and_preserve_paths(
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
        snapshot_id=_fixed_uuid(201),
        source_name=manual_source.name,
    )
    db_session.add(source_snapshot)
    db_session.flush()

    cluster, listing, snapshot, _ = _make_cluster_fixture(
        cluster_id=_fixed_uuid(202),
        listing_id=_fixed_uuid(203),
        snapshot_id=_fixed_uuid(204),
        source_snapshot=source_snapshot,
        source=manual_source,
        canonical_url="https://example.test/listings/refresh",
        headline="Refresh headline",
        address_text="2 Refresh Road",
        normalized_address="2 refresh road london nw1 7aa",
        lat=51.5362,
        lon=-0.1421,
        raw_record_json={
            "geometry_4326": _polygon_geometry(
                west=-0.1422,
                south=51.5361,
                east=-0.1418,
                north=51.5365,
            ).geom_4326,
        },
    )
    db_session.add_all([cluster, listing, snapshot])
    db_session.commit()

    site = build_or_refresh_site_from_cluster(
        session=db_session,
        cluster_id=cluster.id,
        requested_by="pytest",
    )
    original_geom_hash = site.geom_hash
    original_revision_count = len(site.geometry_revisions)

    with pytest.raises(SiteBuildError, match="was not found"):
        save_site_geometry_revision(
            session=db_session,
            site_id=_fixed_uuid(999),
            geom_4326={"type": "Point", "coordinates": [-0.1421, 51.5362]},
            source_type=GeomSourceType.ANALYST_DRAWN,
            confidence=None,
            reason="missing site",
            created_by="pytest",
            raw_asset_id=None,
        )

    stale_calls: list[tuple[str | None, UUID]] = []

    def _record_stale(*, session, site, requested_by):
        del session
        stale_calls.append((requested_by, site.id))

    monkeypatch.setattr(
        scenario_normalize,
        "mark_site_scenarios_stale_for_geometry_change",
        _record_stale,
    )

    analyst_drawn = save_site_geometry_revision(
        session=db_session,
        site_id=site.id,
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
    assert analyst_drawn.geom_source_type == GeomSourceType.ANALYST_DRAWN
    assert analyst_drawn.geom_hash != original_geom_hash
    assert len(analyst_drawn.geometry_revisions) == original_revision_count + 1
    assert stale_calls == [("pytest", site.id)]

    snapshot.raw_record_json = {"bbox_4326": [-0.1430, 51.5358, -0.1410, 51.5366]}
    db_session.commit()

    refreshed = build_or_refresh_site_from_cluster(
        session=db_session,
        cluster_id=cluster.id,
        requested_by="pytest",
    )
    assert refreshed.geom_source_type == GeomSourceType.ANALYST_DRAWN
    assert refreshed.geom_hash == analyst_drawn.geom_hash
    assert len(refreshed.geometry_revisions) >= original_revision_count + 1

    source_polygon = save_site_geometry_revision(
        session=db_session,
        site_id=site.id,
        geom_4326={
            "type": "Polygon",
            "coordinates": [
                [
                    [-0.1425, 51.5360],
                    [-0.1415, 51.5360],
                    [-0.1415, 51.5363],
                    [-0.1425, 51.5363],
                    [-0.1425, 51.5360],
                ]
            ],
        },
        source_type=GeomSourceType.SOURCE_POLYGON,
        confidence=None,
        reason="Source polygon refresh",
        created_by="pytest",
        raw_asset_id=None,
    )
    assert source_polygon.geom_source_type == GeomSourceType.SOURCE_POLYGON
    assert len(stale_calls) == 2
