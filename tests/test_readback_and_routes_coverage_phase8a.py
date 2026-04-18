from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import HTTPException
from landintel.domain.enums import (
    AppRoleName,
    AssessmentRunState,
    BaselinePackStatus,
    DocumentExtractionStatus,
    DocumentType,
    EligibilityStatus,
    EstimateQuality,
    EstimateStatus,
    GeomConfidence,
    GeomSourceType,
    ListingClusterStatus,
    ListingStatus,
    ListingType,
    OpportunityBand,
    PriceBasisType,
    ProposalForm,
    ReviewStatus,
    ScenarioSource,
    ScenarioStatus,
    SiteStatus,
    SourceFreshnessStatus,
    SourceParseStatus,
    ValuationQuality,
    VisibilityMode,
)
from landintel.domain.models import (
    ListingCluster,
    ListingClusterMember,
    ListingDocument,
    ListingItem,
    ListingSnapshot,
    RawAsset,
    SiteScenario,
    SourceSnapshot,
)
from landintel.domain.schemas import (
    AssessmentDetailRead,
    AssessmentOverrideSummaryRead,
    AssessmentRequest,
    EvidencePackRead,
    OpportunitySummaryRead,
    ValuationResultRead,
    VisibilityGateRead,
)
from landintel.services import (
    assessments_readback,
    listings_readback,
    opportunities_readback,
    scenarios_readback,
    sites_readback,
)

from services.api.app.routes import admin as admin_routes
from services.api.app.routes import assessments as assessments_routes
from services.api.app.routes import scenarios as scenarios_routes
from services.api.app.routes import sites as sites_routes
from tests.test_planning_phase3a import _build_camden_site


class _QueryResult:
    def __init__(self, *, rows=None, scalar=None):
        self._rows = list(rows or [])
        self._scalar = scalar

    def scalars(self):
        return self

    def unique(self):
        return self

    def all(self):
        return self._rows

    def scalar_one_or_none(self):
        return self._scalar

    def scalar_one(self):
        return self._scalar


class _QueuedSession:
    def __init__(self, *responses):
        self._responses = list(responses)
        self.commits = 0
        self.rollbacks = 0
        self.expired = 0

    def execute(self, *args, **kwargs):
        del args, kwargs
        return self._responses.pop(0)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def expire_all(self):
        self.expired += 1

    def get(self, model, identity):
        del model, identity
        return None


def _fixed_uuid(seed: int) -> UUID:
    return UUID(f"00000000-0000-0000-0000-{seed:012d}")


def _build_confirmed_camden_scenario(client, drain_jobs):
    site_payload = _build_camden_site(client, drain_jobs)
    suggest = client.post(
        f"/api/sites/{site_payload['id']}/scenarios/suggest",
        json={"requested_by": "pytest"},
    )
    assert suggest.status_code == 200
    suggestion = suggest.json()["items"][0]
    confirm = client.post(
        f"/api/scenarios/{suggestion['id']}/confirm",
        json={
            "requested_by": "pytest",
            "review_notes": "Confirmed for readback coverage.",
        },
    )
    assert confirm.status_code == 200
    return site_payload, confirm.json()


def _build_site_stub(*, include_listing: bool) -> SimpleNamespace:
    source_snapshot = SimpleNamespace(
        id=_fixed_uuid(301),
        source_family="PUBLIC_PAGE",
        source_name="public_page_fixture",
        source_uri="https://example.test/source",
        acquired_at=datetime(2026, 4, 15, 10, 0, tzinfo=UTC),
        effective_from=None,
        effective_to=None,
        schema_hash="schema-hash",
        content_hash="content-hash",
        coverage_note="coverage-note",
        freshness_status=SourceFreshnessStatus.FRESH,
        parse_status=SourceParseStatus.PARSED,
        parse_error_text=None,
        manifest_json={"source": "fixture"},
        raw_assets=[],
    )
    listing_snapshot = SimpleNamespace(
        id=_fixed_uuid(302),
        source_snapshot_id=source_snapshot.id,
        source_snapshot=source_snapshot,
        observed_at=datetime(2026, 4, 15, 11, 0, tzinfo=UTC),
        headline="Fixture headline",
        description_text="Fixture description",
        guide_price_gbp=150_000,
        price_basis_type=PriceBasisType.GUIDE_PRICE,
        status=ListingStatus.LIVE,
        auction_date=date(2026, 4, 20),
        address_text="1 Fixture Road",
        lat=51.5,
        lon=-0.1,
        brochure_asset=None,
        map_asset=None,
        raw_record_json={"kind": "listing"},
    )
    listing = None
    if include_listing:
        listing_source = SimpleNamespace(name="public_page_fixture")
        listing = SimpleNamespace(
            id=_fixed_uuid(303),
            source_id=_fixed_uuid(304),
            source=listing_source,
            source_listing_id="fixture-1",
            canonical_url="https://example.test/listing/1",
            listing_type=ListingType.LAND,
            first_seen_at=datetime(2026, 4, 14, 10, 0, tzinfo=UTC),
            last_seen_at=datetime(2026, 4, 15, 12, 0, tzinfo=UTC),
            latest_status=ListingStatus.LIVE,
            current_snapshot_id=listing_snapshot.id,
            snapshots=[listing_snapshot],
            documents=[],
            cluster_members=[],
            normalized_address="1 Fixture Road",
            current_price_gbp=150_000,
            current_price_basis_type=PriceBasisType.GUIDE_PRICE,
        )

    cluster = SimpleNamespace(
        id=_fixed_uuid(305),
        cluster_key="fixture-cluster",
        cluster_status=ListingClusterStatus.ACTIVE,
        members=[],
    )
    site = SimpleNamespace(
        id=_fixed_uuid(306),
        display_name="Fixture site",
        borough_id="camden",
        borough=SimpleNamespace(name="Camden"),
        site_status=SiteStatus.DRAFT,
        manual_review_required=False,
        warning_json={"coverage": [{"code": "X", "message": "Fixture warning"}]},
        geom_4326={"type": "Point", "coordinates": [-0.1, 51.5]},
        geom_27700="POINT (530000 182000)",
        geom_hash="site-hash",
        geom_source_type=GeomSourceType.ANALYST_DRAWN,
        geom_confidence=GeomConfidence.HIGH,
        site_area_sqm=123.4,
        current_price_gbp=150_000 if include_listing else None,
        current_price_basis_type=(
            PriceBasisType.GUIDE_PRICE if include_listing else PriceBasisType.UNKNOWN
        ),
        current_listing=listing,
        listing_cluster=cluster,
        geometry_revisions=[],
        lpa_links=[],
        title_links=[],
        market_events=[],
        planning_links=[],
        brownfield_states=[],
        policy_facts=[],
        constraint_facts=[],
        scenarios=[],
    )
    if listing is not None:
        listing.cluster_members = [
            SimpleNamespace(listing_cluster_id=cluster.id, listing_cluster=cluster)
        ]
        cluster.members = [SimpleNamespace(listing_item=listing, listing_cluster=cluster)]
    return site


def _build_scenario_stub(
    site: SimpleNamespace, *, template_key: str, version: str
) -> SimpleNamespace:
    return SimpleNamespace(
        id=_fixed_uuid(307),
        site_id=site.id,
        site=site,
        template_key=template_key,
        template_version=version,
        proposal_form=ProposalForm.INFILL,
        units_assumed=6,
        route_assumed="FULL",
        height_band_assumed="3-4 storeys",
        net_developable_area_pct=74.0,
        red_line_geom_hash=site.geom_hash,
        scenario_source=ScenarioSource.AUTO,
        status=ScenarioStatus.SUGGESTED,
        supersedes_id=None,
        is_current=True,
        is_headline=True,
        heuristic_rank=1,
        manual_review_required=True,
        stale_reason=None,
        housing_mix_assumed_json={"market": 6},
        parking_assumption="none",
        affordable_housing_assumption="policy-led",
        access_assumption="existing",
        rationale_json={
            "reason_codes": [
                {
                    "code": "NEAREST_HISTORICAL_SUPPORT_NOT_STRONG",
                    "message": "Nearest support remains weak.",
                    "source_label": "Fixture support",
                }
            ],
            "missing_data_flags": ["EXAMPLE_GAP"],
            "warning_codes": ["EXAMPLE_WARNING"],
        },
        reviews=[
            SimpleNamespace(
                id=_fixed_uuid(308),
                review_status=ScenarioStatus.ANALYST_CONFIRMED,
                review_notes="Confirmed in fixture.",
                reviewed_by="pytest",
                reviewed_at=datetime(2026, 4, 15, 12, 30, tzinfo=UTC),
            )
        ],
        created_at=datetime(2026, 4, 15, 12, 0, tzinfo=UTC),
        updated_at=datetime(2026, 4, 15, 12, 45, tzinfo=UTC),
        geometry_revision=None,
    )


def _build_visibility_gate(
    *,
    viewer_role: AppRoleName,
    blocked: bool,
    hidden_allowed: bool = False,
    visible_allowed: bool = False,
    blocked_reason_codes: list[str] | None = None,
    blocked_reason_text: str | None = None,
) -> VisibilityGateRead:
    return VisibilityGateRead.model_construct(
        scope_key="scope-key",
        visibility_mode=VisibilityMode.HIDDEN_ONLY,
        exposure_mode=(
            "HIDDEN_INTERNAL"
            if hidden_allowed
            else ("VISIBLE_REVIEWER_ONLY" if visible_allowed else "REDACTED")
        ),
        viewer_role=viewer_role,
        visible_probability_allowed=visible_allowed,
        hidden_probability_allowed=hidden_allowed,
        blocked=blocked,
        blocked_reason_codes=list(blocked_reason_codes or []),
        blocked_reason_text=blocked_reason_text,
        active_incident_id=None,
        active_incident_reason=None,
        replay_verified=False,
        payload_hash_matches=False,
        artifact_hashes_match=False,
        scope_release_matches_result=False,
    )


def _build_valuation_result(expected_uplift_mid: float = 33.0) -> ValuationResultRead:
    return ValuationResultRead.model_construct(
        id=_fixed_uuid(401),
        valuation_run_id=_fixed_uuid(402),
        valuation_assumption_set_id=_fixed_uuid(403),
        valuation_assumption_version="fixture-v1",
        post_permission_value_low=100_000.0,
        post_permission_value_mid=125_000.0,
        post_permission_value_high=150_000.0,
        uplift_low=10_000.0,
        uplift_mid=25_000.0,
        uplift_high=40_000.0,
        expected_uplift_mid=expected_uplift_mid,
        valuation_quality=ValuationQuality.MEDIUM,
        manual_review_required=False,
        basis_json={"basis": "fixture"},
        sense_check_json={"sense": "ok"},
        result_json={"result": "fixture"},
        payload_hash="valuation-payload-hash",
        created_at=datetime(2026, 4, 15, 13, 0, tzinfo=UTC),
    )


@pytest.fixture()
def fake_valuation_run():
    return SimpleNamespace(
        id=_fixed_uuid(404),
        valuation_assumption_set_id=_fixed_uuid(405),
        valuation_assumption_set=SimpleNamespace(version="fixture-v1"),
        result=SimpleNamespace(
            id=_fixed_uuid(406),
            post_permission_value_low=100_000.0,
            post_permission_value_mid=125_000.0,
            post_permission_value_high=150_000.0,
            uplift_low=10_000.0,
            uplift_mid=25_000.0,
            uplift_high=40_000.0,
            expected_uplift_mid=33.0,
            valuation_quality=ValuationQuality.MEDIUM,
            manual_review_required=False,
            basis_json={"basis": "fixture"},
            sense_check_json={"sense": "ok"},
            result_json={"result": "fixture"},
            payload_hash="valuation-payload-hash",
            created_at=datetime(2026, 4, 15, 13, 0, tzinfo=UTC),
        ),
    )


def test_listings_readback_branch_paths(db_session, seed_listing_sources):
    manual_source = seed_listing_sources["manual_url"]
    csv_source = seed_listing_sources["csv_import"]

    primary_snapshot = SourceSnapshot(
        id=_fixed_uuid(101),
        source_family="PUBLIC_PAGE",
        source_name="public_page_fixture",
        source_uri="https://example.test/source/a",
        acquired_at=datetime(2026, 4, 15, 11, 0, tzinfo=UTC),
        effective_from=None,
        effective_to=None,
        schema_hash="schema-a",
        content_hash="content-a",
        coverage_note="note-a",
        freshness_status=SourceFreshnessStatus.FRESH,
        parse_status=SourceParseStatus.PARSED,
        parse_error_text=None,
        manifest_json={"kind": "fixture-a"},
    )
    secondary_snapshot = SourceSnapshot(
        id=_fixed_uuid(102),
        source_family="CSV_IMPORT",
        source_name="csv_import",
        source_uri="https://example.test/source/b",
        acquired_at=datetime(2026, 4, 14, 11, 0, tzinfo=UTC),
        effective_from=None,
        effective_to=None,
        schema_hash="schema-b",
        content_hash="content-b",
        coverage_note="note-b",
        freshness_status=SourceFreshnessStatus.STALE,
        parse_status=SourceParseStatus.PARSED,
        parse_error_text=None,
        manifest_json={"kind": "fixture-b"},
    )
    db_session.add_all([primary_snapshot, secondary_snapshot])
    db_session.flush()

    brochure_asset = RawAsset(
        id=_fixed_uuid(103),
        source_snapshot_id=primary_snapshot.id,
        asset_type="brochure",
        original_url="https://example.test/brochure.pdf",
        storage_path="/tmp/brochure.pdf",
        mime_type="application/pdf",
        content_sha256="a" * 64,
        size_bytes=1234,
        fetched_at=datetime(2026, 4, 15, 11, 15, tzinfo=UTC),
    )
    map_asset = RawAsset(
        id=_fixed_uuid(104),
        source_snapshot_id=primary_snapshot.id,
        asset_type="map",
        original_url="https://example.test/map.pdf",
        storage_path="/tmp/map.pdf",
        mime_type="application/pdf",
        content_sha256="b" * 64,
        size_bytes=2345,
        fetched_at=datetime(2026, 4, 15, 11, 20, tzinfo=UTC),
    )
    document_asset = RawAsset(
        id=_fixed_uuid(105),
        source_snapshot_id=primary_snapshot.id,
        asset_type="document",
        original_url="https://example.test/doc.pdf",
        storage_path="/tmp/doc.pdf",
        mime_type="application/pdf",
        content_sha256="c" * 64,
        size_bytes=3456,
        fetched_at=datetime(2026, 4, 15, 11, 25, tzinfo=UTC),
    )
    db_session.add_all([brochure_asset, map_asset, document_asset])
    db_session.flush()

    cluster = ListingCluster(
        id=_fixed_uuid(106),
        cluster_key="cluster-fixture",
        cluster_status=ListingClusterStatus.ACTIVE,
    )
    item_primary = ListingItem(
        id=_fixed_uuid(107),
        source_id=manual_source.id,
        source=manual_source,
        source_listing_id="alpha-1",
        canonical_url="https://example.test/listings/alpha-1",
        listing_type=ListingType.LAND,
        first_seen_at=datetime(2026, 4, 10, 10, 0, tzinfo=UTC),
        last_seen_at=datetime(2026, 4, 15, 12, 0, tzinfo=UTC),
        latest_status=ListingStatus.LIVE,
        current_snapshot_id=None,
        normalized_address="12 Alpha Road",
        search_text="alpha match",
    )
    item_secondary = ListingItem(
        id=_fixed_uuid(108),
        source_id=csv_source.id,
        source=csv_source,
        source_listing_id="beta-1",
        canonical_url="https://example.test/listings/beta-1",
        listing_type=ListingType.LAND,
        first_seen_at=datetime(2026, 4, 11, 10, 0, tzinfo=UTC),
        last_seen_at=datetime(2026, 4, 15, 12, 30, tzinfo=UTC),
        latest_status=ListingStatus.LIVE,
        current_snapshot_id=None,
        normalized_address="34 Beta Road",
        search_text="beta match",
    )
    member_primary = ListingClusterMember(
        id=_fixed_uuid(109),
        listing_cluster=cluster,
        listing_item=item_primary,
        confidence=0.91,
        rules_json={"kind": "primary"},
    )
    member_secondary = ListingClusterMember(
        id=_fixed_uuid(110),
        listing_cluster=cluster,
        listing_item=item_secondary,
        confidence=0.88,
        rules_json={"kind": "secondary"},
    )
    item_primary.snapshots = [
        ListingSnapshot(
            id=_fixed_uuid(111),
            listing_item=item_primary,
            source_snapshot=primary_snapshot,
            observed_at=datetime(2026, 4, 15, 12, 0, tzinfo=UTC),
            headline="Alpha listing",
            description_text="Alpha listing description",
            guide_price_gbp=150_000,
            price_basis_type=PriceBasisType.GUIDE_PRICE,
            status=ListingStatus.LIVE,
            auction_date=date(2026, 4, 20),
            address_text="12 Alpha Road",
            lat=51.5,
            lon=-0.1,
            brochure_asset=brochure_asset,
            map_asset=map_asset,
            raw_record_json={"kind": "primary"},
        ),
        ListingSnapshot(
            id=_fixed_uuid(112),
            listing_item=item_primary,
            source_snapshot=primary_snapshot,
            observed_at=datetime(2026, 4, 14, 12, 0, tzinfo=UTC),
            headline="Alpha previous",
            description_text="Previous alpha listing",
            guide_price_gbp=145_000,
            price_basis_type=PriceBasisType.ASKING_PRICE,
            status=ListingStatus.LIVE,
            auction_date=date(2026, 4, 18),
            address_text="12 Alpha Road",
            lat=51.5,
            lon=-0.1,
            raw_record_json={"kind": "previous"},
        ),
    ]
    item_primary.current_snapshot_id = item_primary.snapshots[0].id
    item_primary.documents = [
        ListingDocument(
            id=_fixed_uuid(113),
            listing_item=item_primary,
            asset=document_asset,
            asset_id=document_asset.id,
            doc_type=DocumentType.BROCHURE,
            page_count=2,
            extraction_status=DocumentExtractionStatus.EXTRACTED,
            extracted_text="Listing brochure text",
        )
    ]
    item_secondary.snapshots = [
        ListingSnapshot(
            id=_fixed_uuid(114),
            listing_item=item_secondary,
            source_snapshot=secondary_snapshot,
            observed_at=datetime(2026, 4, 15, 11, 0, tzinfo=UTC),
            headline="Beta listing",
            description_text="Beta listing description",
            guide_price_gbp=90_000,
            price_basis_type=PriceBasisType.GUIDE_PRICE,
            status=ListingStatus.LIVE,
            auction_date=date(2026, 4, 25),
            address_text="34 Beta Road",
            lat=51.6,
            lon=-0.11,
            raw_record_json={"kind": "secondary"},
        )
    ]
    item_secondary.current_snapshot_id = item_secondary.snapshots[0].id
    cluster.members = [member_secondary, member_primary]
    db_session.add_all([cluster, item_primary, item_secondary, member_primary, member_secondary])
    db_session.commit()

    snapshots = listings_readback.list_source_snapshots(db_session, limit=2)
    assert [snapshot.id for snapshot in snapshots] == [primary_snapshot.id, secondary_snapshot.id]
    assert snapshots[0].raw_assets[0].id == brochure_asset.id
    assert (
        listings_readback.get_source_snapshot(db_session, snapshot_id=primary_snapshot.id)
        is not None
    )
    assert listings_readback.get_source_snapshot(db_session, snapshot_id=_fixed_uuid(999)) is None

    source_names = [source.name for source in listings_readback.list_listing_sources(db_session)]
    assert source_names == sorted(source_names)

    listing_page = listings_readback.list_listings(
        db_session,
        q="alpha",
        source=manual_source.name,
        status=ListingStatus.LIVE,
        listing_type=ListingType.LAND,
        min_price_gbp=100_000,
        max_price_gbp=200_000,
    )
    assert listing_page.total == 1
    assert listing_page.items[0].id == item_primary.id
    assert listing_page.items[0].current_snapshot is not None
    assert listing_page.items[0].current_snapshot.brochure_asset is not None
    assert listing_page.items[0].current_snapshot.map_asset is not None

    fallback_summary = listings_readback.serialize_listing_summary(item_secondary)
    assert fallback_summary.current_snapshot is not None
    assert fallback_summary.current_snapshot.id == item_secondary.snapshots[0].id

    missing_listing = listings_readback.get_listing(db_session, listing_id=_fixed_uuid(998))
    assert missing_listing is None
    detail = listings_readback.get_listing(db_session, listing_id=item_primary.id)
    assert detail is not None
    assert len(detail.documents) == 1
    assert len(detail.source_snapshots) == 1

    cluster_page = listings_readback.list_listing_clusters(db_session, q="beta")
    assert cluster_page.total == 1
    assert cluster_page.items[0].id == cluster.id
    assert cluster_page.items[0].members[0].id == item_secondary.id

    cluster_detail = listings_readback.get_listing_cluster(db_session, cluster_id=cluster.id)
    assert cluster_detail is not None
    assert cluster_detail.members[0].listing.id == item_secondary.id
    assert listings_readback.get_listing_cluster(db_session, cluster_id=_fixed_uuid(997)) is None

    bogus_item = SimpleNamespace(
        id=_fixed_uuid(993),
        current_snapshot_id=_fixed_uuid(996),
        snapshots=[
            SimpleNamespace(
                id=_fixed_uuid(995),
                source_snapshot=primary_snapshot,
                observed_at=datetime(2026, 4, 15, 12, 0, tzinfo=UTC),
                headline="Bogus",
                description_text=None,
                guide_price_gbp=None,
                price_basis_type=PriceBasisType.UNKNOWN,
                status=ListingStatus.LIVE,
                auction_date=None,
                address_text=None,
                lat=None,
                lon=None,
                brochure_asset=None,
                map_asset=None,
                raw_record_json={},
            )
        ],
        source=SimpleNamespace(name="public_page_fixture"),
        source_id=_fixed_uuid(994),
        source_listing_id="bogus",
        canonical_url="https://example.test/bogus",
        listing_type=ListingType.LAND,
        first_seen_at=datetime(2026, 4, 15, 10, 0, tzinfo=UTC),
        last_seen_at=datetime(2026, 4, 15, 10, 0, tzinfo=UTC),
        latest_status=ListingStatus.LIVE,
        normalized_address=None,
        cluster_members=[],
    )
    assert listings_readback.serialize_listing_summary(bogus_item).current_snapshot is None


def test_sites_and_scenarios_readback_branch_paths(
    client,
    drain_jobs,
    seed_listing_sources,
    seed_planning_data,
    db_session,
    monkeypatch,
):
    del seed_listing_sources
    del seed_planning_data
    site_payload = _build_camden_site(client, drain_jobs)
    suggest = client.post(
        f"/api/sites/{site_payload['id']}/scenarios/suggest",
        json={"requested_by": "pytest"},
    )
    assert suggest.status_code == 200
    suggestion = suggest.json()["items"][0]
    confirm = client.post(
        f"/api/scenarios/{suggestion['id']}/confirm",
        json={
            "requested_by": "pytest",
            "review_notes": "Confirmed for readback coverage.",
        },
    )
    assert confirm.status_code == 200
    db_session.add(
        SiteScenario(
            id=_fixed_uuid(602),
            site_id=UUID(site_payload["id"]),
            template_key="missing-template",
            template_version="1",
            proposal_form=ProposalForm.INFILL,
            units_assumed=8,
            route_assumed="FULL",
            height_band_assumed="4-5 storeys",
            net_developable_area_pct=80.0,
            housing_mix_assumed_json={"market": 8},
            parking_assumption="none",
            affordable_housing_assumption="policy-led",
            access_assumption="existing",
            red_line_geom_hash=site_payload["current_geometry"]["geom_hash"],
            scenario_source=ScenarioSource.ANALYST,
            status=ScenarioStatus.ANALYST_REQUIRED,
            is_current=False,
            is_headline=False,
            heuristic_rank=2,
            manual_review_required=True,
            rationale_json={
                "reason_codes": [
                    {
                        "code": "MANUAL_REVIEW_REQUIRED",
                        "message": "Manual scenario branch.",
                    }
                ],
                "missing_data_flags": ["MANUAL_GAP"],
                "warning_codes": ["MANUAL_WARNING"],
            },
        )
    )
    db_session.commit()

    site_detail = sites_readback.get_site(db_session, site_id=UUID(site_payload["id"]))
    assert site_detail is not None
    assert site_detail.current_listing is not None
    assert site_detail.scenarios
    assert site_detail.source_documents
    assert site_detail.source_snapshots

    site_list = sites_readback.list_sites(db_session, borough="camden")
    assert site_list.total >= 1
    assert site_list.items[0].current_listing is not None

    site_without_listing = _build_site_stub(include_listing=False)
    site_with_listing = _build_site_stub(include_listing=True)
    list_session = _QueuedSession(
        _QueryResult(rows=[site_with_listing, site_without_listing], scalar=2),
        _QueryResult(rows=[site_with_listing, site_without_listing], scalar=2),
    )
    list_empty_session = _QueuedSession(
        _QueryResult(rows=[], scalar=0),
        _QueryResult(rows=[], scalar=0),
    )
    get_missing_session = _QueuedSession(_QueryResult(scalar=None))

    fake_site_list = sites_readback.list_sites(list_session)
    assert fake_site_list.total == 2
    assert fake_site_list.items[0].current_listing is not None

    empty_site_list = sites_readback.list_sites(list_empty_session)
    assert empty_site_list.total == 0
    assert empty_site_list.items == []

    assert sites_readback.get_site(get_missing_session, site_id=_fixed_uuid(603)) is None

    fake_pack = SimpleNamespace(
        id=_fixed_uuid(702),
        borough_id="camden",
        version="fixture-pack",
        status=BaselinePackStatus.SIGNED_OFF,
        freshness_status=SourceFreshnessStatus.FRESH,
        signed_off_by="pytest",
        signed_off_at=datetime(2026, 4, 15, 14, 0, tzinfo=UTC),
        pack_json={"kind": "baseline"},
        source_snapshot_id=_fixed_uuid(703),
        rulepacks=[
            SimpleNamespace(
                id=_fixed_uuid(704),
                template_key="resi_5_9_full",
                status=BaselinePackStatus.SIGNED_OFF,
                freshness_status=SourceFreshnessStatus.FRESH,
                source_snapshot_id=_fixed_uuid(705),
                effective_from=date(2026, 4, 1),
                effective_to=None,
                rule_json={
                    "citations": [
                        {
                            "label": "Rule source",
                            "source_family": "BOROUGH_REGISTER",
                            "effective_date": "2026-04-01",
                            "source_url": "https://example.test/rule",
                        }
                    ]
                },
            )
        ],
    )
    fixture_scenario = _build_scenario_stub(
        site_with_listing,
        template_key="resi_5_9_full",
        version="1",
    )
    fixture_scenario.reviews = [
        SimpleNamespace(
            id=_fixed_uuid(706),
            review_status=ScenarioStatus.ANALYST_CONFIRMED,
            review_notes="Fixture review.",
            reviewed_by="pytest",
            reviewed_at=datetime(2026, 4, 15, 14, 15, tzinfo=UTC),
        )
    ]
    fixture_scenario.geometry_revision = None
    missing_scenario = _build_scenario_stub(
        site_with_listing,
        template_key="missing-template",
        version="1",
    )
    missing_scenario.is_current = False
    missing_scenario.is_headline = False
    missing_scenario.manual_review_required = True
    missing_scenario.reviews = []
    missing_scenario.geometry_revision = None
    scenario_read = _build_scenario_stub(
        site_with_listing,
        template_key="resi_5_9_full",
        version="1",
    )
    scenario_read.reviews = [
        SimpleNamespace(
            id=_fixed_uuid(706),
            review_status=ScenarioStatus.ANALYST_CONFIRMED,
            review_notes="Fixture review.",
            reviewed_by="pytest",
            reviewed_at=datetime(2026, 4, 15, 14, 15, tzinfo=UTC),
        )
    ]
    scenario_read.geometry_revision = None
    scenario_session = _QueuedSession(
        _QueryResult(scalar=scenario_read),
        _QueryResult(
            scalar=SimpleNamespace(
                id=_fixed_uuid(701),
                key="resi_5_9_full",
                version="1",
                enabled=True,
                config_json={"fixture": True},
            )
        ),
    )
    scenario_missing_session = _QueuedSession(
        _QueryResult(scalar=missing_scenario),
        _QueryResult(scalar=None),
    )
    list_scenarios_session = _QueuedSession(
        _QueryResult(
            rows=[
                fixture_scenario,
                missing_scenario,
            ]
        )
    )
    empty_scenario_session = _QueuedSession(_QueryResult(rows=[]))

    monkeypatch.setattr(
        scenarios_readback, "get_borough_baseline_pack", lambda *args, **kwargs: fake_pack
    )
    monkeypatch.setattr(
        scenarios_readback,
        "evaluate_site_extant_permission",
        lambda *args, **kwargs: SimpleNamespace(
            status="PASS", eligibility_status=EligibilityStatus.PASS
        ),
    )
    monkeypatch.setattr(
        scenarios_readback,
        "assemble_site_evidence",
        lambda *args, **kwargs: EvidencePackRead.model_construct(for_=[], against=[], unknown=[]),
    )
    monkeypatch.setattr(
        scenarios_readback,
        "assemble_scenario_evidence",
        lambda *args, **kwargs: EvidencePackRead.model_construct(for_=[], against=[], unknown=[]),
    )

    scenario_list = scenarios_readback.list_site_scenarios(
        session=list_scenarios_session,
        site_id=site_with_listing.id,
    )
    assert scenario_list.total == 2
    assert scenario_list.items[0].reason_codes

    empty_scenario_list = scenarios_readback.list_site_scenarios(
        session=empty_scenario_session,
        site_id=_fixed_uuid(707),
    )
    assert empty_scenario_list.total == 0

    scenario_summary = scenarios_readback.serialize_site_scenario_summary(
        session=list_scenarios_session,
        scenario=fixture_scenario,
        baseline_pack=fake_pack,
        site=site_with_listing,
    )
    assert scenario_summary.missing_data_flags == ["EXAMPLE_GAP"]
    assert scenario_summary.warning_codes == ["EXAMPLE_WARNING"]

    detailed = scenarios_readback.get_scenario_detail(
        session=scenario_session,
        scenario_id=scenario_list.items[0].id,
    )
    assert detailed is not None
    assert detailed.template is not None
    assert detailed.baseline_pack is not None
    assert detailed.review_history

    missing_detail = scenarios_readback.get_scenario_detail(
        session=scenario_missing_session,
        scenario_id=_fixed_uuid(708),
    )
    assert missing_detail is not None
    assert missing_detail.template is None

    assert sites_readback._serialize_site_listing(None) is None
    assert (
        sites_readback._serialize_site_listing(
            SimpleNamespace(
                id=_fixed_uuid(709),
                current_snapshot_id=_fixed_uuid(710),
                snapshots=[
                    SimpleNamespace(
                        id=_fixed_uuid(711),
                        headline="Ignored",
                        guide_price_gbp=100,
                        price_basis_type=PriceBasisType.GUIDE_PRICE,
                        address_text="Ignored",
                    )
                ],
                canonical_url="https://example.test/ignored",
                latest_status=ListingStatus.LIVE,
                source=SimpleNamespace(name="fixture"),
            )
        ).headline
        is None
    )

    warning_rows = sites_readback._flatten_warnings(
        {
            "planning": [
                {"code": "PLANNING_ONE", "message": "One"},
                {"code": 1, "message": "ignored"},
                "ignored",
            ],
            "other": "ignored",
        }
    )
    assert [row.code for row in warning_rows] == ["PLANNING_ONE"]
    assert sites_readback._flatten_warnings(None) == []

    simple_asset = SimpleNamespace(
        id=_fixed_uuid(712),
        asset_type="document",
        original_url="https://example.test/doc.pdf",
        storage_path="/tmp/doc.pdf",
        mime_type="application/pdf",
        content_sha256="d" * 64,
        size_bytes=42,
        fetched_at=datetime(2026, 4, 15, 15, 0, tzinfo=UTC),
    )
    snapshot_stub = SimpleNamespace(id=_fixed_uuid(713), raw_assets=[simple_asset])
    listing_stub = SimpleNamespace(snapshots=[SimpleNamespace(source_snapshot=snapshot_stub)])
    assert sites_readback._source_snapshots_for_listing(None) == []
    assert sites_readback._source_snapshots_for_listing(listing_stub)[0].id == snapshot_stub.id

    application = SimpleNamespace(
        id=_fixed_uuid(714),
        borough_id="camden",
        source_system="fixture",
        source_snapshot_id=_fixed_uuid(715),
        external_ref="CAM/2026/0001",
        application_type="FULL",
        proposal_description="Fixture application",
        valid_date=date(2026, 4, 1),
        decision_date=None,
        decision=None,
        decision_type=None,
        status="Registered",
        route_normalized="FULL",
        units_proposed=6,
        source_priority=1,
        source_url="https://example.test/planning",
        site_geom_4326={"type": "Point"},
        site_point_4326={"type": "Point"},
        raw_record_json={"kind": "application"},
        documents=[
            SimpleNamespace(
                id=_fixed_uuid(716),
                asset_id=simple_asset.id,
                doc_type="report",
                doc_url="https://example.test/doc",
                asset=simple_asset,
            )
        ],
    )
    with_snapshot = sites_readback._serialize_planning_application(
        application,
        source_snapshot_id=_fixed_uuid(717),
        snapshot_json={
            "id": _fixed_uuid(718),
            "documents": [
                {
                    "id": _fixed_uuid(719),
                    "asset_id": simple_asset.id,
                    "doc_type": "report",
                    "doc_url": "https://example.test/doc",
                }
            ],
        },
    )
    assert with_snapshot.source_snapshot_id == _fixed_uuid(717)
    assert len(with_snapshot.documents) == 1

    fallback_application = sites_readback._serialize_planning_application(application)
    assert fallback_application.documents[0].asset.id == simple_asset.id

    policy_area = SimpleNamespace(
        id=_fixed_uuid(720),
        borough_id="camden",
        policy_family="LP",
        policy_code="LP1",
        name="Fixture policy",
        geom_4326={"type": "Polygon"},
        legal_effective_from=date(2026, 1, 1),
        legal_effective_to=None,
        source_snapshot_id=_fixed_uuid(721),
        source_class="AUTHORITATIVE",
        source_url="https://example.test/policy",
    )
    serialized_policy = sites_readback._serialize_policy_area(
        policy_area,
        source_snapshot_id=_fixed_uuid(722),
        snapshot_json={"id": _fixed_uuid(723), "policy_code": "LP2"},
    )
    assert serialized_policy.policy_code == "LP2"
    assert serialized_policy.source_snapshot_id == _fixed_uuid(722)
    serialized_constraint = sites_readback._serialize_constraint_feature(
        SimpleNamespace(
            id=_fixed_uuid(724),
            feature_family="Flood",
            feature_subtype="Zone 3",
            authority_level="LOCAL",
            geom_4326={"type": "Polygon"},
            legal_status="Designated",
            effective_from=date(2026, 1, 1),
            effective_to=None,
            source_snapshot_id=_fixed_uuid(725),
            source_class="AUTHORITATIVE",
            source_url="https://example.test/constraint",
        ),
        source_snapshot_id=_fixed_uuid(726),
        snapshot_json={"feature_subtype": "Zone 2"},
    )
    assert serialized_constraint.feature_subtype == "Zone 2"
    assert serialized_constraint.source_snapshot_id == _fixed_uuid(726)

    assert sites_readback._serialize_baseline_pack(None) is None
    baseline_pack = sites_readback._serialize_baseline_pack(fake_pack)
    assert baseline_pack is not None
    assert baseline_pack.rulepacks[0].citations_complete is True


def test_assessment_and_opportunity_readback_branch_paths(monkeypatch, fake_valuation_run):
    site = _build_site_stub(include_listing=True)
    scenario = _build_scenario_stub(site, template_key="resi_5_9_full", version="1")
    result = SimpleNamespace(
        id=_fixed_uuid(801),
        model_release_id=_fixed_uuid(802),
        release_scope_key="scope-key",
        eligibility_status=EligibilityStatus.PASS,
        estimate_status=EstimateStatus.NONE,
        review_status=ReviewStatus.REQUIRED,
        approval_probability_raw=0.61,
        approval_probability_display="61%",
        estimate_quality=EstimateQuality.MEDIUM,
        source_coverage_quality="good",
        geometry_quality="good",
        support_quality="good",
        scenario_quality="good",
        ood_quality="low",
        ood_status="in_scope",
        manual_review_required=False,
        result_json={
            "score_execution_status": "HIDDEN_ONLY",
            "support_summary": {"same_borough_support_count": 3},
            "note": "Fixture note",
        },
        published_at=datetime(2026, 4, 15, 16, 0, tzinfo=UTC),
    )
    ledger = SimpleNamespace(
        id=_fixed_uuid(803),
        site_geom_hash=site.geom_hash,
        feature_hash="feature-hash",
        model_release_id=_fixed_uuid(804),
        release_scope_key="scope-key",
        calibration_hash="calibration-hash",
        model_artifact_hash="model-hash",
        validation_artifact_hash="validation-hash",
        response_mode="HIDDEN",
        source_snapshot_ids_json=["source-1"],
        raw_asset_ids_json=["asset-1"],
        result_payload_hash="payload-hash",
        response_json={"response_mode": "HIDDEN", "note": "original"},
        replay_verification_status="HASH_CAPTURED",
        replay_verified_at=datetime(2026, 4, 15, 16, 5, tzinfo=UTC),
        replay_verification_note="ok",
        created_at=datetime(2026, 4, 15, 16, 6, tzinfo=UTC),
    )
    run = SimpleNamespace(
        id=_fixed_uuid(805),
        site_id=site.id,
        scenario_id=scenario.id,
        as_of_date=date(2026, 4, 15),
        state=AssessmentRunState.READY,
        idempotency_key="fixture-key",
        requested_by="pytest",
        started_at=datetime(2026, 4, 15, 16, 0, tzinfo=UTC),
        finished_at=datetime(2026, 4, 15, 16, 1, tzinfo=UTC),
        error_text=None,
        created_at=datetime(2026, 4, 15, 16, 2, tzinfo=UTC),
        updated_at=datetime(2026, 4, 15, 16, 3, tzinfo=UTC),
        site=site,
        scenario=scenario,
        feature_snapshot=None,
        result=result,
        comparable_case_set=None,
        evidence_items=[],
        prediction_ledger=ledger,
        valuation_runs=[fake_valuation_run],
        overrides=[],
    )
    blocked_visibility = _build_visibility_gate(
        viewer_role=AppRoleName.ANALYST,
        blocked=True,
        blocked_reason_codes=["NO_SCOPE"],
        blocked_reason_text="No active release scope is registered for this assessment.",
    )
    hidden_visibility = _build_visibility_gate(
        viewer_role=AppRoleName.ADMIN,
        blocked=False,
        hidden_allowed=True,
    )
    visible_visibility = _build_visibility_gate(
        viewer_role=AppRoleName.REVIEWER,
        blocked=False,
        visible_allowed=True,
    )

    monkeypatch.setattr(
        assessments_readback,
        "get_borough_baseline_pack",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        assessments_readback,
        "evaluate_assessment_visibility",
        lambda *args, **kwargs: blocked_visibility,
    )
    monkeypatch.setattr(
        assessments_readback,
        "build_override_summary",
        lambda *args, **kwargs: AssessmentOverrideSummaryRead.model_construct(
            active_overrides=[],
            effective_review_status=ReviewStatus.REQUIRED,
            effective_manual_review_required=False,
            ranking_suppressed=False,
            display_block_reason="Blocked by fixture",
            effective_valuation=_build_valuation_result(),
        ),
    )
    monkeypatch.setattr(
        assessments_readback,
        "frozen_valuation_run",
        lambda *args, **kwargs: fake_valuation_run,
    )
    summary = assessments_readback.serialize_assessment_summary(session=SimpleNamespace(), run=run)
    assert summary.site_summary is not None
    assert summary.scenario_summary is not None

    blocked_result = assessments_readback._serialize_assessment_result(
        result,
        include_hidden=False,
        visibility=blocked_visibility,
    )
    assert blocked_result is not None
    assert blocked_result.result_json["hidden_score_redacted"] is True

    hidden_result = assessments_readback._serialize_assessment_result(
        result,
        include_hidden=True,
        visibility=hidden_visibility,
    )
    assert hidden_result is not None
    assert hidden_result.approval_probability_raw == 0.61

    visible_result = assessments_readback._serialize_assessment_result(
        result,
        include_hidden=False,
        visibility=visible_visibility,
    )
    assert visible_result is not None
    assert visible_result.result_json["visible_probability_mode"] == "VISIBLE_REVIEWER_ONLY"

    assert (
        assessments_readback._serialize_assessment_result(
            None,
            include_hidden=False,
            visibility=blocked_visibility,
        )
        is None
    )

    blocked_ledger = assessments_readback._serialize_prediction_ledger(
        ledger,
        include_hidden=False,
        visibility=blocked_visibility,
    )
    assert blocked_ledger is not None
    assert blocked_ledger.response_json["hidden_score_redacted"] is True

    hidden_ledger = assessments_readback._serialize_prediction_ledger(
        ledger,
        include_hidden=True,
        visibility=hidden_visibility,
    )
    assert hidden_ledger is not None
    assert hidden_ledger.response_json["note"] == "original"

    assert (
        assessments_readback._serialize_prediction_ledger(
            None,
            include_hidden=False,
            visibility=blocked_visibility,
        )
        is None
    )

    assert (
        assessments_readback._detail_note(
            run=SimpleNamespace(result=None),
            include_hidden=False,
            visibility=blocked_visibility,
        )
        == assessments_readback.PRE_SCORE_NOTE
    )
    assert (
        "no active release scope"
        in assessments_readback._detail_note(
            run=run,
            include_hidden=False,
            visibility=blocked_visibility,
        ).lower()
    )
    assert (
        "visible reviewer-only probability"
        in assessments_readback._detail_note(
            run=run,
            include_hidden=False,
            visibility=visible_visibility,
        ).lower()
    )

    valuation_result = assessments_readback._serialize_valuation_result(
        fake_valuation_run,
        visibility=blocked_visibility,
    )
    assert valuation_result is not None
    assert valuation_result.expected_uplift_mid is None

    visible_valuation = assessments_readback._serialize_valuation_result(
        fake_valuation_run,
        visibility=hidden_visibility,
    )
    assert visible_valuation is not None
    assert visible_valuation.expected_uplift_mid == 33.0

    assessment_detail = assessments_readback.serialize_assessment_detail(
        session=SimpleNamespace(),
        run=run,
        include_hidden=False,
        viewer_role=AppRoleName.ANALYST,
    )
    assert isinstance(assessment_detail, AssessmentDetailRead)
    assert assessment_detail.visibility.blocked is True
    assert assessment_detail.note == blocked_visibility.blocked_reason_text

    fake_opportunity_summary = OpportunitySummaryRead.model_construct(
        site_id=site.id,
        display_name=site.display_name,
        borough_id=site.borough_id,
        borough_name=site.borough.name,
        assessment_id=run.id,
        scenario_id=scenario.id,
        probability_band=OpportunityBand.HOLD,
        hold_reason="Blocked for fixture",
        ranking_reason="Blocked for fixture",
        hidden_mode_only=True,
        visibility=blocked_visibility,
        display_block_reason=None,
        eligibility_status=EligibilityStatus.PASS,
        estimate_status=EstimateStatus.NONE,
        manual_review_required=False,
        valuation_quality=ValuationQuality.MEDIUM,
        asking_price_gbp=150_000,
        asking_price_basis_type=PriceBasisType.GUIDE_PRICE,
        auction_date=date(2026, 4, 20),
        post_permission_value_mid=125_000.0,
        uplift_mid=25_000.0,
        expected_uplift_mid=None,
        same_borough_support_count=3,
        site_summary=site,
        scenario_summary=scenario,
    )
    fake_opportunity_summary_two = OpportunitySummaryRead.model_construct(
        site_id=_fixed_uuid(806),
        display_name="Second site",
        borough_id="southwark",
        borough_name="Southwark",
        assessment_id=_fixed_uuid(807),
        scenario_id=_fixed_uuid(808),
        probability_band=OpportunityBand.HOLD,
        hold_reason=None,
        ranking_reason="Secondary",
        hidden_mode_only=True,
        visibility=visible_visibility,
        display_block_reason=None,
        eligibility_status=EligibilityStatus.PASS,
        estimate_status=EstimateStatus.NONE,
        manual_review_required=True,
        valuation_quality=ValuationQuality.LOW,
        asking_price_gbp=None,
        asking_price_basis_type=None,
        auction_date=None,
        post_permission_value_mid=None,
        uplift_mid=None,
        expected_uplift_mid=None,
        same_borough_support_count=0,
        site_summary=site,
        scenario_summary=scenario,
    )
    monkeypatch.setattr(
        opportunities_readback,
        "_latest_runs_by_site",
        lambda *args, **kwargs: [
            run,
            SimpleNamespace(id=_fixed_uuid(809), site_id=_fixed_uuid(810)),
        ],
    )
    monkeypatch.setattr(
        opportunities_readback,
        "evaluate_assessment_visibility",
        lambda *args, **kwargs: blocked_visibility
        if kwargs.get("viewer_role") == AppRoleName.REVIEWER
        else visible_visibility,
    )
    monkeypatch.setattr(
        opportunities_readback,
        "build_override_summary",
        lambda *args, **kwargs: AssessmentOverrideSummaryRead.model_construct(
            active_overrides=[],
            effective_review_status=ReviewStatus.REQUIRED,
            effective_manual_review_required=False,
            ranking_suppressed=False,
            display_block_reason="Blocked by override",
            effective_valuation=_build_valuation_result(),
        ),
    )
    monkeypatch.setattr(
        opportunities_readback,
        "frozen_valuation_run",
        lambda *args, **kwargs: fake_valuation_run,
    )
    opportunity_detail = opportunities_readback.get_opportunity(
        SimpleNamespace(),
        site_id=site.id,
        viewer_role=AppRoleName.ANALYST,
        include_hidden=False,
    )
    assert opportunity_detail is not None
    assert opportunity_detail.valuation.expected_uplift_mid == 33.0
    assert opportunity_detail.ranking_factors["same_borough_support_count"] == 3
    assert opportunity_detail.ranking_factors["auction_date"] == "2026-04-20"

    monkeypatch.setattr(
        opportunities_readback,
        "_serialize_opportunity_summary",
        lambda *args, **kwargs: (
            fake_opportunity_summary
            if kwargs["run"].site_id == run.site_id
            else fake_opportunity_summary_two
        ),
    )
    opportunity_list = opportunities_readback.list_opportunities(
        SimpleNamespace(),
        borough="camden",
        probability_band=OpportunityBand.HOLD,
        valuation_quality=ValuationQuality.MEDIUM,
        manual_review_required=False,
        auction_deadline_days=10,
        min_price=100_000,
        max_price=200_000,
    )
    assert opportunity_list.total == 1
    assert opportunity_list.items[0].site_id == site.id


def test_route_edge_branches_cover_missing_and_visibility_paths(monkeypatch):
    assessment_id = _fixed_uuid(901)
    scenario_id = _fixed_uuid(902)
    site_id = _fixed_uuid(903)
    snapshot_id = _fixed_uuid(904)

    create_calls: list[bool] = []

    monkeypatch.setattr(
        assessments_routes,
        "create_or_refresh_assessment_run",
        lambda *args, **kwargs: SimpleNamespace(id=assessment_id),
    )
    monkeypatch.setattr(
        assessments_routes,
        "get_assessment",
        lambda *args, **kwargs: create_calls.append(kwargs["include_hidden"])
        or SimpleNamespace(id=assessment_id),
    )
    fake_session = _QueuedSession()
    fake_request = AssessmentRequest(
        site_id=site_id,
        scenario_id=scenario_id,
        as_of_date=date(2026, 4, 15),
        hidden_mode=True,
    )
    detail = assessments_routes.create_assessment(
        fake_request,
        session=fake_session,
        storage=SimpleNamespace(),
        actor=SimpleNamespace(role=AppRoleName.REVIEWER, name="reviewer", user_name="reviewer"),
    )
    assert detail.id == assessment_id
    assert create_calls == [True]

    monkeypatch.setattr(
        assessments_routes,
        "get_assessment",
        lambda *args, **kwargs: None,
    )
    with pytest.raises(HTTPException) as exc:
        assessments_routes.get_assessment_detail(
            assessment_id=assessment_id,
            hidden_mode=False,
            session=SimpleNamespace(),
            actor=SimpleNamespace(role=AppRoleName.ANALYST),
        )
    assert exc.value.status_code == 404

    monkeypatch.setattr(
        scenarios_routes,
        "get_scenario_detail",
        lambda *args, **kwargs: None,
    )
    with pytest.raises(HTTPException) as exc:
        scenarios_routes.get_scenario(
            scenario_id=scenario_id,
            session=SimpleNamespace(),
        )
    assert exc.value.status_code == 404

    monkeypatch.setattr(
        sites_routes,
        "get_site",
        lambda *args, **kwargs: None,
    )
    with pytest.raises(HTTPException) as exc:
        sites_routes.get_site_detail(
            site_id=site_id,
            session=SimpleNamespace(),
        )
    assert exc.value.status_code == 404

    monkeypatch.setattr(
        admin_routes,
        "get_source_snapshot",
        lambda *args, **kwargs: None,
    )
    with pytest.raises(HTTPException) as exc:
        admin_routes.get_source_snapshot_detail(
            snapshot_id=snapshot_id,
            session=SimpleNamespace(),
            _actor=SimpleNamespace(role=AppRoleName.ADMIN),
        )
    assert exc.value.status_code == 404

    review_queue_runs = [_fixed_uuid(905), _fixed_uuid(906)]
    review_details = {
        review_queue_runs[0]: SimpleNamespace(
            id=review_queue_runs[0],
            site_id=site_id,
            site_summary=SimpleNamespace(display_name="Manual review site"),
            manual_review_required=True,
            visibility=VisibilityGateRead.model_construct(
                scope_key="scope-key",
                visibility_mode=VisibilityMode.HIDDEN_ONLY,
                exposure_mode="REDACTED",
                viewer_role=AppRoleName.REVIEWER,
                visible_probability_allowed=False,
                hidden_probability_allowed=False,
                blocked=True,
                blocked_reason_codes=["NO_SCOPE"],
                blocked_reason_text="No active release scope is registered for this assessment.",
                active_incident_id=None,
                active_incident_reason=None,
                replay_verified=False,
                payload_hash_matches=False,
                artifact_hashes_match=False,
                scope_release_matches_result=False,
            ),
            override_summary=SimpleNamespace(display_block_reason="blocked"),
            review_status=ReviewStatus.REQUIRED,
            updated_at=datetime(2026, 4, 15, 18, 0, tzinfo=UTC),
            estimate_status=EstimateStatus.NONE,
        ),
        review_queue_runs[1]: None,
    }
    monkeypatch.setattr(
        admin_routes,
        "get_assessment",
        lambda *args, **kwargs: review_details.get(kwargs["assessment_id"]),
    )
    monkeypatch.setattr(
        admin_routes,
        "build_data_health",
        lambda *args, **kwargs: {
            "coverage": [
                {
                    "borough_id": "camden",
                    "coverage_status": "INCOMPLETE",
                    "freshness_status": "STALE",
                }
            ]
        },
    )

    class _ReviewSession:
        def execute(self, *args, **kwargs):
            del args, kwargs
            return _QueryResult(rows=review_queue_runs)

    queue = admin_routes.get_review_queue(
        limit=5,
        session=_ReviewSession(),
        _actor=SimpleNamespace(role=AppRoleName.REVIEWER),
    )
    assert queue["manual_review_cases"]
    assert queue["blocked_cases"]
    assert queue["failing_boroughs"]
    assert queue["recent_cases"]

    phase = admin_routes.get_phase_status(_actor=SimpleNamespace(role=AppRoleName.ADMIN))
    assert phase.surface == "admin.phase-status"
