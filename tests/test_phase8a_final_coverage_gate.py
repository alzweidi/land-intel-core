from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import landintel.geospatial.bootstrap as geo_bootstrap
import pytest
from landintel.connectors import tabular_feed
from landintel.domain.enums import (
    GeomSourceType,
    ListingStatus,
    ListingType,
    PriceBasisType,
    ScenarioStatus,
)
from landintel.domain.models import (
    ListingCluster,
    ListingClusterMember,
    ListingItem,
    ListingSnapshot,
)
from landintel.geospatial import reference_data
from landintel.geospatial.geometry import normalize_geojson_geometry
from landintel.listings import service as listings_service
from landintel.services import opportunities_readback
from landintel.sites import service as site_service


def test_tabular_feed_json_scalar_payload_is_rejected() -> None:
    with pytest.raises(ValueError, match="top-level row list"):
        tabular_feed._load_json_rows(b'"not-a-row-list"')


def test_geospatial_bootstrap_wrappers_normalize_fixture_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lpa_calls: dict[str, object] = {}
    titles_calls: dict[str, object] = {}
    lpa_result = object()
    titles_result = object()

    def _capture_lpa(**kwargs):
        lpa_calls.update(kwargs)
        return lpa_result

    def _capture_titles(**kwargs):
        titles_calls.update(kwargs)
        return titles_result

    monkeypatch.setattr(geo_bootstrap, "_import_lpa_boundaries_fixture", _capture_lpa)
    monkeypatch.setattr(geo_bootstrap, "_import_hmlr_title_polygons_fixture", _capture_titles)

    assert (
        geo_bootstrap.import_lpa_boundaries(
            session="session",
            storage="storage",
            fixture_path="fixtures/lpa.geojson",
            requested_by="pytest",
        )
        is lpa_result
    )
    assert lpa_calls["fixture_path"] == Path("fixtures/lpa.geojson")

    assert (
        geo_bootstrap.import_hmlr_title_polygons(
            session="session",
            storage="storage",
            fixture_path="fixtures/titles.geojson",
            requested_by="pytest",
        )
        is titles_result
    )
    assert titles_calls["fixture_path"] == Path("fixtures/titles.geojson")


def test_reference_data_identifier_helpers_cover_fallback_paths() -> None:
    assert reference_data._clean_identifier(" none ") is None
    assert reference_data._derive_lpa_slug(None) is None
    assert reference_data._derive_lpa_slug("Barnet & Camden") == "barnet_and_camden"
    assert (
        reference_data._resolve_lpa_boundary_id(
            properties={"name": None, "gss_code": " E09000001 "},
            feature={"id": "feature-id"},
            geom_hash="abcdef1234567890",
        )
        == "E09000001"
    )
    assert (
        reference_data._resolve_lpa_boundary_id(
            properties={"name": " none ", "gss_code": " none "},
            feature={"id": None},
            geom_hash="abcdef1234567890",
        )
        == "lpa_abcdef123456"
    )


def test_list_auto_site_build_cluster_ids_skip_non_live_and_empty_clusters(
    db_session,
    seed_listing_sources,
) -> None:
    source = seed_listing_sources["example_public_page"]
    now = datetime.now(UTC)

    live_listing = ListingItem(
        source_id=source.id,
        source_listing_id="eligible-cluster",
        canonical_url="https://example.test/eligible-cluster",
        listing_type=ListingType.LAND,
        first_seen_at=now,
        last_seen_at=now,
    )
    withdrawn_listing = ListingItem(
        source_id=source.id,
        source_listing_id="withdrawn-cluster",
        canonical_url="https://example.test/withdrawn-cluster",
        listing_type=ListingType.LAND,
        first_seen_at=now,
        last_seen_at=now,
    )
    db_session.add_all([live_listing, withdrawn_listing])
    db_session.flush()

    live_snapshot = ListingSnapshot(
        listing_item_id=live_listing.id,
        source_snapshot_id=uuid.uuid4(),
        observed_at=now,
        headline="Eligible land listing",
        description_text="Live land listing",
        guide_price_gbp=100_000,
        price_basis_type=PriceBasisType.GUIDE_PRICE,
        status=ListingStatus.LIVE,
        address_text="1 Eligible Street, London",
        normalized_address="1 eligible street london",
        lat=51.5,
        lon=-0.1,
        raw_record_json={},
        search_text="eligible",
    )
    withdrawn_snapshot = ListingSnapshot(
        listing_item_id=withdrawn_listing.id,
        source_snapshot_id=uuid.uuid4(),
        observed_at=now,
        headline="Withdrawn land listing",
        description_text="Withdrawn land listing",
        guide_price_gbp=120_000,
        price_basis_type=PriceBasisType.GUIDE_PRICE,
        status=ListingStatus.WITHDRAWN,
        address_text="2 Withdrawn Street, London",
        normalized_address="2 withdrawn street london",
        lat=51.51,
        lon=-0.11,
        raw_record_json={},
        search_text="withdrawn",
    )
    db_session.add_all([live_snapshot, withdrawn_snapshot])
    db_session.flush()
    live_listing.current_snapshot_id = live_snapshot.id
    withdrawn_listing.current_snapshot_id = withdrawn_snapshot.id

    live_cluster = ListingCluster(
        id=uuid.uuid4(),
        cluster_key="live-cluster",
        cluster_status="ACTIVE",
    )
    withdrawn_cluster = ListingCluster(
        id=uuid.uuid4(),
        cluster_key="withdrawn-cluster",
        cluster_status="ACTIVE",
    )
    empty_cluster = ListingCluster(
        id=uuid.uuid4(),
        cluster_key="empty-cluster",
        cluster_status="ACTIVE",
    )
    db_session.add_all([live_cluster, withdrawn_cluster, empty_cluster])
    db_session.flush()
    db_session.add_all(
        [
            ListingClusterMember(
                id=uuid.uuid4(),
                listing_cluster_id=live_cluster.id,
                listing_item_id=live_listing.id,
                confidence=1.0,
                rules_json={"reasons": ["eligible"]},
            ),
            ListingClusterMember(
                id=uuid.uuid4(),
                listing_cluster_id=withdrawn_cluster.id,
                listing_item_id=withdrawn_listing.id,
                confidence=1.0,
                rules_json={"reasons": ["withdrawn"]},
            ),
        ]
    )
    db_session.commit()

    assert listings_service.list_auto_site_build_cluster_ids(db_session) == [live_cluster.id]


def test_opportunity_helpers_cover_invalid_session_and_auto_confirmed_states() -> None:
    assert (
        opportunities_readback._get_site_without_ready_assessment(
            object(),
            site_id=uuid.uuid4(),
        )
        is None
    )
    assert (
        opportunities_readback._unassessed_hold_reason(
            site_summary=SimpleNamespace(warnings=[], manual_review_required=False),
            scenario_summary=SimpleNamespace(
                status=ScenarioStatus.AUTO_CONFIRMED,
                missing_data_flags=[],
                manual_review_required=False,
            ),
        )
        == "No ready assessment is available yet."
    )


def test_site_geometry_helpers_cover_official_title_union_and_missing_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = normalize_geojson_geometry(
        geometry_payload={"type": "Point", "coordinates": [-0.1421, 51.5362]},
        source_epsg=4326,
        source_type=GeomSourceType.POINT_ONLY,
    )
    monkeypatch.setattr(
        site_service,
        "maybe_import_title_union_for_listing_point",
        lambda **_kwargs: prepared,
    )

    hints = site_service.ClusterSpatialHints(
        normalized_addresses=[],
        point_geometries_27700=[],
        current_listing=SimpleNamespace(),
        current_snapshot=SimpleNamespace(
            raw_record_json={},
            lat=51.5362,
            lon=-0.1421,
        ),
    )

    assert (
        site_service._derive_cluster_geometry(
            session=SimpleNamespace(),
            cluster=SimpleNamespace(),
            hints=hints,
            requested_by="pytest",
        )
        is prepared
    )
    assert site_service._raw_local_authority(None) is None
