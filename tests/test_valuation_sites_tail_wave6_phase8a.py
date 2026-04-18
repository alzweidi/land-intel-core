from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import landintel.sites.service as site_service
from landintel.domain.enums import (
    GeomSourceType,
    ListingClusterStatus,
    ListingStatus,
    ListingType,
    PriceBasisType,
    ProposalForm,
    SourceFreshnessStatus,
    SourceParseStatus,
)
from landintel.domain.models import (
    ListingCluster,
    ListingClusterMember,
    ListingItem,
    ListingSnapshot,
    MarketIndexSeries,
    MarketLandComp,
    MarketSaleComp,
    SourceSnapshot,
)
from landintel.geospatial.geometry import normalize_geojson_geometry
from landintel.scenarios import normalize as scenario_normalize
from landintel.sites.service import (
    build_or_refresh_site_from_cluster,
)
from landintel.valuation.assumptions import ensure_default_assumption_set
from landintel.valuation.market import (
    _parse_date,
    _parse_int,
    _resolve_index_value,
    build_land_comp_summary,
    build_sales_comp_summary,
    import_hmlr_price_paid_fixture,
    import_land_comp_fixture,
    import_ukhpi_fixture,
)
from landintel.valuation.residual import (
    _mix_to_counts,
    compute_residual_valuation,
    derive_area_summary,
)
from sqlalchemy import select

import services.worker.app.jobs.valuation as worker_valuation


def _fixed_uuid(seed: int) -> UUID:
    return UUID(f"00000000-0000-0000-0000-{seed:012d}")


def _make_sourceless_cluster_fixture(
    *,
    cluster_id: UUID,
    listing_id: UUID,
    source,
    canonical_url: str,
    latest_status: ListingStatus = ListingStatus.LIVE,
) -> tuple[ListingCluster, ListingItem, ListingClusterMember]:
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
        normalized_address=None,
        search_text=canonical_url,
        current_snapshot_id=None,
        snapshots=[],
    )
    member = ListingClusterMember(
        id=uuid4(),
        listing_cluster=cluster,
        listing_item=listing,
        confidence=0.95,
        rules_json={"fixture": True},
    )
    listing.cluster_members = [member]
    cluster.members = [member]
    return cluster, listing, member


def test_site_refresh_without_current_snapshot_and_noop_geometry_stale_marking(
    db_session,
    seed_listing_sources,
    seed_reference_data,
    seed_planning_data,
    monkeypatch,
):
    del seed_reference_data
    del seed_planning_data

    manual_source = seed_listing_sources["manual_url"]
    cluster, listing, member = _make_sourceless_cluster_fixture(
        cluster_id=_fixed_uuid(11),
        listing_id=_fixed_uuid(12),
        source=manual_source,
        canonical_url="https://example.test/listings/no-snapshot",
    )
    db_session.add_all([cluster, listing, member])
    db_session.commit()

    prepared = normalize_geojson_geometry(
        geometry_payload={"type": "Point", "coordinates": [-0.1421, 51.5362]},
        source_epsg=4326,
        source_type=GeomSourceType.POINT_ONLY,
    )
    monkeypatch.setattr(
        site_service,
        "_build_cluster_hints",
        lambda cluster: SimpleNamespace(
            normalized_addresses=[],
            point_geometries_27700=[],
            current_listing=listing,
            current_snapshot=None,
        ),
    )
    monkeypatch.setattr(
        site_service,
        "_derive_cluster_geometry",
        lambda **_kwargs: prepared,
    )

    site = build_or_refresh_site_from_cluster(
        session=db_session,
        cluster_id=cluster.id,
        requested_by="pytest",
    )
    assert site.current_listing_id == listing.id
    assert site.current_price_gbp is None
    assert site.current_price_basis_type == PriceBasisType.UNKNOWN
    assert site.display_name == "https://example.test/listings/no-snapshot"

    price_source_snapshot = SourceSnapshot(
        id=_fixed_uuid(13),
        source_family="PUBLIC_PAGE",
        source_name=manual_source.name,
        source_uri="https://example.test/source/priced",
        acquired_at=datetime(2026, 4, 15, 10, 0, tzinfo=UTC),
        effective_from=None,
        effective_to=None,
        schema_hash="priced-schema-hash",
        content_hash="priced-content-hash",
        coverage_note="fixture coverage",
        freshness_status=SourceFreshnessStatus.FRESH,
        parse_status=SourceParseStatus.PARSED,
        parse_error_text=None,
        manifest_json={"fixture": True},
    )
    priced_cluster = ListingCluster(
        id=_fixed_uuid(21),
        cluster_key="cluster-priced",
        cluster_status=ListingClusterStatus.ACTIVE,
    )
    priced_listing = ListingItem(
        id=_fixed_uuid(22),
        source_id=manual_source.id,
        source=manual_source,
        source_listing_id="listing-priced",
        canonical_url="https://example.test/listings/priced",
        listing_type=ListingType.LAND,
        first_seen_at=datetime(2026, 4, 14, 10, 0, tzinfo=UTC),
        last_seen_at=datetime(2026, 4, 15, 10, 0, tzinfo=UTC),
        latest_status=ListingStatus.LIVE,
        normalized_address="3 priced road london nw1 7aa",
        search_text="3 priced road london nw1 7aa",
    )
    priced_snapshot = ListingSnapshot(
        id=_fixed_uuid(23),
        listing_item=priced_listing,
        source_snapshot=price_source_snapshot,
        observed_at=datetime(2026, 4, 15, 11, 0, tzinfo=UTC),
        headline="Priced headline",
        description_text="Fixture listing with current price basis.",
        guide_price_gbp=175_000,
        price_basis_type=PriceBasisType.GUIDE_PRICE,
        status=ListingStatus.LIVE,
        auction_date=date(2026, 4, 20),
        address_text="3 Priced Road",
        normalized_address="3 priced road london nw1 7aa",
        lat=51.5362,
        lon=-0.1421,
        brochure_asset_id=None,
        raw_record_json={},
        search_text="3 priced road london nw1 7aa",
    )
    priced_member = ListingClusterMember(
        id=uuid4(),
        listing_cluster=priced_cluster,
        listing_item=priced_listing,
        confidence=0.95,
        rules_json={"fixture": True},
    )
    priced_listing.snapshots = [priced_snapshot]
    priced_listing.current_snapshot_id = priced_snapshot.id
    priced_listing.cluster_members = [priced_member]
    priced_cluster.members = [priced_member]
    db_session.add_all([price_source_snapshot, priced_cluster, priced_listing, priced_snapshot])
    db_session.commit()

    monkeypatch.setattr(
        site_service,
        "_build_cluster_hints",
        lambda cluster: SimpleNamespace(
            normalized_addresses=[],
            point_geometries_27700=[],
            current_listing=priced_listing,
            current_snapshot=priced_snapshot,
        ),
    )
    priced_site = build_or_refresh_site_from_cluster(
        session=db_session,
        cluster_id=priced_cluster.id,
        requested_by="pytest",
    )
    assert priced_site.current_listing_id == priced_listing.id
    assert priced_site.current_price_gbp == 175_000
    assert priced_site.current_price_basis_type == PriceBasisType.GUIDE_PRICE

    refresh_stale_calls: list[tuple[str | None, UUID]] = []

    def _record_stale(*, session, site, requested_by):
        del session
        refresh_stale_calls.append((requested_by, site.id))

    monkeypatch.setattr(
        scenario_normalize,
        "mark_site_scenarios_stale_for_geometry_change",
        _record_stale,
    )

    refreshed_prepared = normalize_geojson_geometry(
        geometry_payload={"type": "Point", "coordinates": [-0.1422, 51.5363]},
        source_epsg=4326,
        source_type=GeomSourceType.POINT_ONLY,
    )
    monkeypatch.setattr(
        site_service,
        "_derive_cluster_geometry",
        lambda **_kwargs: refreshed_prepared,
    )
    refreshed_site = build_or_refresh_site_from_cluster(
        session=db_session,
        cluster_id=cluster.id,
        requested_by="pytest",
    )
    assert refreshed_site.id == site.id
    assert refreshed_site.geom_hash == refreshed_prepared.geom_hash
    assert refresh_stale_calls == [("pytest", site.id)]


def test_valuation_importers_update_existing_rows_and_summary_fallbacks(
    db_session,
    storage,
    seed_reference_data,
    seed_valuation_data,
):
    del seed_reference_data

    fixtures_root = Path(__file__).parent / "fixtures" / "valuation"

    sale_before = db_session.execute(select(MarketSaleComp).limit(1)).scalar_one()
    index_before = db_session.execute(select(MarketIndexSeries).limit(1)).scalar_one()
    land_before = db_session.execute(select(MarketLandComp).limit(1)).scalar_one()

    sale_before.price_gbp = -1
    index_before.index_value = -1.0
    land_before.post_permission_value_mid = -1.0
    db_session.flush()

    fallback_index = MarketIndexSeries(
        id=_fixed_uuid(305),
        borough_id=None,
        index_key="UKHPI",
        period_month=date(2026, 4, 1),
        index_value=123.45,
        source_snapshot_id=index_before.source_snapshot_id,
        raw_asset_id=index_before.raw_asset_id,
        raw_record_json={"kind": "fallback"},
    )
    db_session.add(fallback_index)
    db_session.flush()

    hmlr_result = import_hmlr_price_paid_fixture(
        session=db_session,
        storage=storage,
        fixture_path=fixtures_root / "hmlr_price_paid_london.json",
        requested_by="pytest",
    )
    del hmlr_result
    ukhpi_result = import_ukhpi_fixture(
        session=db_session,
        storage=storage,
        fixture_path=fixtures_root / "ukhpi_london.json",
        requested_by="pytest",
    )
    del ukhpi_result
    land_result = import_land_comp_fixture(
        session=db_session,
        storage=storage,
        fixture_path=fixtures_root / "land_comps_london.json",
        requested_by="pytest",
    )
    del land_result

    sale_after = db_session.get(MarketSaleComp, sale_before.id)
    index_after = db_session.get(MarketIndexSeries, index_before.id)
    land_after = db_session.get(MarketLandComp, land_before.id)
    assert sale_after is not None
    assert index_after is not None
    assert land_after is not None
    assert sale_after.price_gbp != -1
    assert index_after.index_value != -1.0
    assert land_after.post_permission_value_mid != -1.0

    sale_snapshot_id = seed_valuation_data["hmlr_price_paid"].source_snapshot_id
    sale_asset_id = seed_valuation_data["hmlr_price_paid"].raw_asset_id
    land_snapshot_id = seed_valuation_data["land_comps"].source_snapshot_id
    land_asset_id = seed_valuation_data["land_comps"].raw_asset_id

    sale_area = MarketSaleComp(
        id=_fixed_uuid(301),
        transaction_ref="manual-sale-area",
        borough_id="legacy",
        source_snapshot_id=sale_snapshot_id,
        raw_asset_id=sale_asset_id,
        sale_date=date(2000, 1, 1),
        price_gbp=200_000,
        property_type="FLAT",
        tenure=None,
        postcode_district=None,
        address_text="Manual area sale",
        floor_area_sqm=100.0,
        rebased_price_per_sqm_hint=None,
        raw_record_json={"kind": "area"},
    )
    sale_hint = MarketSaleComp(
        id=_fixed_uuid(302),
        transaction_ref="manual-sale-hint",
        borough_id="legacy",
        source_snapshot_id=sale_snapshot_id,
        raw_asset_id=sale_asset_id,
        sale_date=date(2000, 1, 1),
        price_gbp=0,
        property_type="FLAT",
        tenure=None,
        postcode_district=None,
        address_text="Manual hint sale",
        floor_area_sqm=None,
        rebased_price_per_sqm_hint=2_500.0,
        raw_record_json={"kind": "hint"},
    )
    sale_empty = MarketSaleComp(
        id=_fixed_uuid(304),
        transaction_ref="manual-sale-empty",
        borough_id="legacy",
        source_snapshot_id=sale_snapshot_id,
        raw_asset_id=sale_asset_id,
        sale_date=date(2000, 1, 1),
        price_gbp=150_000,
        property_type="FLAT",
        tenure=None,
        postcode_district=None,
        address_text="Manual empty sale",
        floor_area_sqm=None,
        rebased_price_per_sqm_hint=None,
        raw_record_json={"kind": "empty"},
    )

    existing_land = db_session.execute(
        select(MarketLandComp)
        .where(MarketLandComp.proposal_form == ProposalForm.REDEVELOPMENT)
        .limit(1)
    ).scalar_one()
    land_manual = MarketLandComp(
        id=_fixed_uuid(303),
        comp_ref="manual-land-proposal-fallback",
        borough_id="legacy-borough",
        template_key="manual-proposal-template",
        proposal_form=ProposalForm.REDEVELOPMENT,
        comp_source_type=existing_land.comp_source_type,
        evidence_date=date(2000, 1, 1),
        unit_count=4,
        site_area_sqm=400.0,
        post_permission_value_low=100_000.0,
        post_permission_value_mid=125_000.0,
        post_permission_value_high=150_000.0,
        source_url="https://example.test/manual-land",
        source_snapshot_id=land_snapshot_id,
        raw_asset_id=land_asset_id,
        raw_record_json={"kind": "proposal_form_fallback"},
    )

    db_session.add_all([sale_area, sale_hint, sale_empty, land_manual])
    db_session.commit()

    sales_summary = build_sales_comp_summary(
        session=db_session,
        borough_id="legacy",
        as_of_date=date(2000, 1, 1),
        max_age_months=12,
        limit=6,
    )
    assert sales_summary.count == 2
    assert sales_summary.price_per_sqm_low == 2_115.0
    assert sales_summary.price_per_sqm_mid == 2_250.0
    assert sales_summary.price_per_sqm_high == 2_385.0
    assert _parse_date(date(2026, 4, 18)) == date(2026, 4, 18)
    assert _parse_int("") is None
    assert _parse_int("12") == 12
    assert (
        _resolve_index_value(
            session=db_session,
            borough_id="missing-borough",
            period_month=date(2026, 4, 1),
        )
        == 123.45
    )

    land_summary = build_land_comp_summary(
        session=db_session,
        borough_id="other-borough",
        template_key="unseen-template",
        proposal_form=ProposalForm.REDEVELOPMENT,
        as_of_date=date(2000, 1, 1),
        limit=6,
    )
    assert land_summary.count == 1
    assert land_summary.fallback_path == "proposal_form_fallback"
    assert land_summary.post_permission_value_mid == 125_000.0


def test_residual_zero_mix_and_zero_unit_branching(db_session):
    assumption_set = ensure_default_assumption_set(db_session)
    scenario = SimpleNamespace(
        template_key="resi_5_9_full",
        units_assumed=0,
        housing_mix_assumed_json={"2_bed": 0.0, "3_bed": 0.0},
    )

    area_summary = derive_area_summary(scenario=scenario, assumption_set=assumption_set)
    assert area_summary.unit_mix_counts == {"2_bed": 0}
    assert area_summary.nsa_sqm == 0.0
    assert area_summary.gia_sqm == 0.0

    residual = compute_residual_valuation(
        site=SimpleNamespace(
            borough_id="camden",
            current_price_gbp=None,
            current_price_basis_type=PriceBasisType.UNKNOWN,
        ),
        scenario=scenario,
        assumption_set=assumption_set,
        price_per_sqm_low=5_600.0,
        price_per_sqm_mid=6_100.0,
        price_per_sqm_high=6_600.0,
    )
    assert residual.basis_json["basis_available"] is False
    assert residual.result_json["status"] == "INSUFFICIENT_MARKET_DATA"
    assert residual.result_json["derived_area"]["unit_mix_counts"] == {"2_bed": 0}


def test_residual_mix_allocation_break_branch(db_session):
    assumption_set = ensure_default_assumption_set(db_session)
    scenario = SimpleNamespace(
        template_key="resi_5_9_full",
        units_assumed=3,
        housing_mix_assumed_json={"2_bed": 0.5, "3_bed": 0.5},
    )

    area_summary = derive_area_summary(scenario=scenario, assumption_set=assumption_set)
    assert area_summary.unit_mix_counts == {"2_bed": 2, "3_bed": 1}
    assert area_summary.nsa_sqm == 238.0
    assert area_summary.gia_sqm == 273.7

    residual = compute_residual_valuation(
        site=SimpleNamespace(
            borough_id="camden",
            current_price_gbp=900000,
            current_price_basis_type=PriceBasisType.GUIDE_PRICE,
        ),
        scenario=scenario,
        assumption_set=assumption_set,
        price_per_sqm_low=5_600.0,
        price_per_sqm_mid=6_100.0,
        price_per_sqm_high=6_600.0,
    )
    assert residual.result_json["status"] == "READY"
    assert residual.result_json["derived_area"]["unit_mix_counts"] == {"2_bed": 2, "3_bed": 1}
    assert residual.uplift_mid is not None


def test_residual_mix_allocation_immediate_break_branch(db_session):
    assumption_set = ensure_default_assumption_set(db_session)
    scenario = SimpleNamespace(
        template_key="resi_5_9_full",
        units_assumed=2,
        housing_mix_assumed_json={"2_bed": 0.5, "3_bed": 0.5},
    )

    area_summary = derive_area_summary(scenario=scenario, assumption_set=assumption_set)
    assert area_summary.unit_mix_counts == {"2_bed": 1, "3_bed": 1}
    assert area_summary.nsa_sqm == 166.0
    assert area_summary.gia_sqm == 190.9


def test_residual_empty_mix_payload_falls_back_to_two_bed() -> None:
    assert _mix_to_counts(units_assumed=4, mix_payload={}) == {"2_bed": 4}


def test_valuation_data_refresh_job_skips_assumption_seed_for_partial_dataset(
    db_session,
    storage,
    seed_reference_data,
    seed_valuation_data,
):
    del seed_reference_data
    del seed_valuation_data

    job = SimpleNamespace(
        payload_json={"dataset": "ukhpi"},
        requested_by=None,
    )

    worker_valuation.run_valuation_data_refresh_job(
        session=db_session,
        job=job,
        storage=storage,
    )
    assert job.payload_json["result"]["dataset"] == "ukhpi"
    assert "assumption_set_version" not in job.payload_json["result"]
    assert "ukhpi" in job.payload_json["result"]
