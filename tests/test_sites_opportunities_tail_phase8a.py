from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

from landintel.domain.enums import (
    AppRoleName,
    AssessmentRunState,
    EligibilityStatus,
    EstimateQuality,
    EstimateStatus,
    ExtantPermissionStatus,
    GeomConfidence,
    GeomSourceType,
    ListingClusterStatus,
    ListingStatus,
    OpportunityBand,
    PriceBasisType,
    ProposalForm,
    ScenarioSource,
    ScenarioStatus,
    SiteStatus,
    ValuationQuality,
    VisibilityMode,
)
from landintel.domain.models import ListingCluster, SiteCandidate
from landintel.domain.schemas import (
    AssessmentDetailRead,
    AssessmentOverrideSummaryRead,
    EvidencePackRead,
    ExtantPermissionRead,
    OpportunitySummaryRead,
    SiteScenarioSummaryRead,
    ValuationResultRead,
    VisibilityGateRead,
)
from landintel.geospatial.geometry import normalize_geojson_geometry
from landintel.services import opportunities_readback, readback, sites_readback
from landintel.services.sites_readback import serialize_site_summary
from landintel.sites.service import refresh_site_lpa_links, refresh_site_title_links


def _fixed_uuid(seed: int) -> UUID:
    return UUID(f"00000000-0000-0000-0000-{seed:012d}")


def _make_geometry(*, lon: float, lat: float):
    return normalize_geojson_geometry(
        geometry_payload={"type": "Point", "coordinates": [lon, lat]},
        source_epsg=4326,
        source_type=GeomSourceType.ANALYST_DRAWN,
    )


def _make_site(
    *,
    site_id: UUID,
    cluster_id: UUID,
    display_name: str,
    borough_id: str | None,
    lon: float,
    lat: float,
    site_status: SiteStatus = SiteStatus.DRAFT,
    manual_review_required: bool = False,
):
    prepared = _make_geometry(lon=lon, lat=lat)
    return SiteCandidate(
        id=site_id,
        listing_cluster_id=cluster_id,
        display_name=display_name,
        borough_id=borough_id,
        geom_27700=prepared.geom_27700_wkt,
        geom_4326=prepared.geom_4326,
        geom_hash=prepared.geom_hash,
        geom_source_type=GeomSourceType.ANALYST_DRAWN,
        geom_confidence=GeomConfidence.HIGH,
        site_area_sqm=prepared.area_sqm,
        site_status=site_status,
        manual_review_required=manual_review_required,
        warning_json={"summary": [{"code": "SITE_NOTE", "message": "Fixture note"}]},
    )


def _make_visibility_gate(
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


def _valuation_result(expected_uplift_mid: float = 33.0) -> ValuationResultRead:
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


def test_site_service_and_readback_tail_branches(
    client,
    seed_reference_data,
    db_session,
    monkeypatch,
):
    del seed_reference_data

    outside_cluster = ListingCluster(
        id=_fixed_uuid(11),
        cluster_key="outside-cluster",
        cluster_status=ListingClusterStatus.SINGLETON,
    )
    outside_site = _make_site(
        site_id=_fixed_uuid(12),
        cluster_id=outside_cluster.id,
        display_name="Outside boundary site",
        borough_id="camden",
        lon=0.0,
        lat=0.0,
    )
    db_session.add_all([outside_cluster, outside_site])
    db_session.flush()

    lpa_warnings = refresh_site_lpa_links(session=db_session, site=outside_site)
    title_warnings = refresh_site_title_links(session=db_session, site=outside_site)
    assert outside_site.borough_id is None
    assert [row["code"] for row in lpa_warnings] == ["LPA_UNRESOLVED"]
    assert [row["code"] for row in title_warnings] == ["NO_TITLE_LINK"]

    camden_cluster = ListingCluster(
        id=_fixed_uuid(13),
        cluster_key="camden-cluster",
        cluster_status=ListingClusterStatus.SINGLETON,
    )
    camden_site = _make_site(
        site_id=_fixed_uuid(14),
        cluster_id=camden_cluster.id,
        display_name="Camden fixture site",
        borough_id="camden",
        lon=-0.1421,
        lat=51.5362,
    )
    db_session.add_all([camden_cluster, camden_site])
    db_session.commit()

    monkeypatch.setattr(
        sites_readback,
        "list_latest_coverage_snapshots",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        sites_readback,
        "list_brownfield_states_for_site",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        sites_readback,
        "get_borough_baseline_pack",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        sites_readback,
        "evaluate_site_extant_permission",
        lambda *args, **kwargs: ExtantPermissionRead.model_construct(
            status=ExtantPermissionStatus.NO_ACTIVE_PERMISSION_FOUND,
            eligibility_status=EligibilityStatus.PASS,
            manual_review_required=False,
            summary="Fixture extant permission",
        ),
    )
    monkeypatch.setattr(
        sites_readback,
        "assemble_site_evidence",
        lambda *args, **kwargs: EvidencePackRead.model_construct(
            for_=[],
            against=[],
            unknown=[],
        ),
    )

    detail = readback.get_site(db_session, site_id=camden_site.id)
    assert detail is not None
    assert detail.current_listing is None
    assert detail.source_documents == []
    assert detail.source_snapshots == []
    assert detail.scenarios == []

    summary = serialize_site_summary(camden_site)
    assert summary.current_listing is None
    assert summary.warnings[0].code == "SITE_NOTE"

    listing_stub = SimpleNamespace(
        id=_fixed_uuid(16),
        current_snapshot_id=None,
        snapshots=[
            SimpleNamespace(
                id=_fixed_uuid(15),
                headline="Fallback headline",
                guide_price_gbp=100_000,
                price_basis_type=PriceBasisType.GUIDE_PRICE,
                address_text="Fallback address",
            )
        ],
        canonical_url="https://example.test/listing",
        latest_status=ListingStatus.LIVE,
        source=SimpleNamespace(name="fixture-source"),
    )
    serialized_listing = sites_readback._serialize_site_listing(listing_stub)
    assert serialized_listing is not None
    assert serialized_listing.headline == "Fallback headline"

    site_list = readback.list_sites(
        db_session,
        q="Camden",
        borough="camden",
        status=SiteStatus.DRAFT.value,
    )
    assert site_list.total == 1
    assert site_list.items[0].id == camden_site.id

    route_detail = client.get(f"/api/sites/{camden_site.id}")
    assert route_detail.status_code == 200
    assert route_detail.json()["current_listing"] is None

    route_list = client.get(
        "/api/sites",
        params={
            "q": "Camden",
            "borough": "camden",
            "status": SiteStatus.DRAFT.value,
        },
    )
    assert route_list.status_code == 200
    assert route_list.json()["total"] == 1


def test_opportunity_tail_branches_cover_redaction_hold_and_filters(monkeypatch):
    site = SimpleNamespace(
        id=_fixed_uuid(51),
        display_name="Fixture opportunity site",
        borough_id="camden",
        borough=SimpleNamespace(name="Camden"),
        site_status=SiteStatus.DRAFT,
        manual_review_required=False,
        warning_json={},
        geom_4326={"type": "Point", "coordinates": [-0.1421, 51.5362]},
        geom_source_type=GeomSourceType.ANALYST_DRAWN,
        geom_confidence=GeomConfidence.HIGH,
        site_area_sqm=100.0,
        current_price_gbp=150_000,
        current_price_basis_type=PriceBasisType.GUIDE_PRICE,
        current_listing=SimpleNamespace(
            id=_fixed_uuid(65),
            canonical_url="https://example.test/listing",
            latest_status=ListingStatus.LIVE,
            source=SimpleNamespace(name="fixture-source"),
            snapshots=[
                SimpleNamespace(
                    id=_fixed_uuid(52),
                    headline="Opportunity headline",
                    guide_price_gbp=150_000,
                    price_basis_type=PriceBasisType.GUIDE_PRICE,
                    address_text="1 Fixture Road",
                    auction_date=date.today() + timedelta(days=3),
                )
            ],
            current_snapshot_id=_fixed_uuid(52),
            documents=[],
        ),
        listing_cluster=SimpleNamespace(
            id=_fixed_uuid(64),
            cluster_key="fixture-cluster",
            cluster_status=ListingClusterStatus.SINGLETON,
            members=[],
        ),
        geom_hash="site-hash",
    )
    scenario = SimpleNamespace(id=_fixed_uuid(53))
    result = SimpleNamespace(
        id=_fixed_uuid(54),
        eligibility_status=EligibilityStatus.PASS,
        estimate_status=EstimateStatus.NONE,
        estimate_quality=EstimateQuality.MEDIUM,
        approval_probability_raw=0.61,
        manual_review_required=False,
        result_json={
            "score_execution_status": "HIDDEN_ONLY",
            "support_summary": {"same_borough_support_count": 3},
        },
    )
    run = SimpleNamespace(
        id=_fixed_uuid(55),
        site_id=site.id,
        scenario_id=scenario.id,
        state=AssessmentRunState.READY,
        site=site,
        scenario=scenario,
        result=result,
        valuation_runs=[],
        overrides=[],
        prediction_ledger=SimpleNamespace(
            replay_verification_status="HASH_CAPTURED",
        ),
    )
    valuation_run = SimpleNamespace(
        id=_fixed_uuid(56),
        valuation_assumption_set_id=_fixed_uuid(57),
        valuation_assumption_set=SimpleNamespace(version="fixture-v1"),
        result=SimpleNamespace(
            id=_fixed_uuid(58),
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
    redacted_visibility = _make_visibility_gate(
        viewer_role=AppRoleName.ANALYST,
        blocked=False,
        hidden_allowed=False,
        visible_allowed=False,
    )
    blocked_visibility = _make_visibility_gate(
        viewer_role=AppRoleName.REVIEWER,
        blocked=True,
        blocked_reason_codes=["NO_SCOPE"],
        blocked_reason_text="No active release scope is registered for this assessment.",
    )
    replay_blocked_visibility = _make_visibility_gate(
        viewer_role=AppRoleName.REVIEWER,
        blocked=True,
        blocked_reason_codes=["REPLAY_FAILED"],
        blocked_reason_text="Replay failed.",
    )
    visible_visibility = _make_visibility_gate(
        viewer_role=AppRoleName.ANALYST,
        blocked=False,
        hidden_allowed=True,
    )

    monkeypatch.setattr(
        opportunities_readback,
        "_latest_runs_by_site",
        lambda *args, **kwargs: [run],
    )
    monkeypatch.setattr(
        opportunities_readback,
        "evaluate_assessment_visibility",
        lambda *args, **kwargs: (
            blocked_visibility
            if kwargs.get("viewer_role") == AppRoleName.REVIEWER
            else redacted_visibility
        ),
    )
    monkeypatch.setattr(
        opportunities_readback,
        "build_override_summary",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        opportunities_readback,
        "frozen_valuation_run",
        lambda *args, **kwargs: valuation_run,
    )
    monkeypatch.setattr(
        opportunities_readback,
        "serialize_assessment_detail",
        lambda *args, **kwargs: AssessmentDetailRead.model_construct(),
    )
    monkeypatch.setattr(
        opportunities_readback,
        "serialize_site_scenario_summary",
        lambda *args, **kwargs: SiteScenarioSummaryRead.model_construct(
            id=scenario.id,
            site_id=site.id,
            template_key="resi_5_9_full",
            template_version="1",
            proposal_form=ProposalForm.INFILL,
            units_assumed=6,
            route_assumed="FULL",
            height_band_assumed="3-4 storeys",
            net_developable_area_pct=75.0,
            red_line_geom_hash=site.geom_hash,
            scenario_source=ScenarioSource.ANALYST,
            status=ScenarioStatus.SUGGESTED,
            supersedes_id=None,
            is_current=True,
            is_headline=True,
            heuristic_rank=1,
            manual_review_required=False,
            stale_reason=None,
            housing_mix_assumed_json={},
            parking_assumption=None,
            affordable_housing_assumption=None,
            access_assumption=None,
            reason_codes=[],
            missing_data_flags=[],
            warning_codes=[],
        ),
    )

    detail = opportunities_readback.get_opportunity(
        SimpleNamespace(),
        site_id=site.id,
        viewer_role=AppRoleName.ANALYST,
        include_hidden=False,
    )
    assert detail is not None
    assert detail.valuation.expected_uplift_mid is None
    assert detail.probability_band == OpportunityBand.HOLD
    assert "No active release scope" in detail.hold_reason
    assert detail.ranking_factors["expected_uplift_mid"] is None
    assert (
        opportunities_readback._ranking_output_blocked(
            run=run,
            visibility=replay_blocked_visibility,
        )
        is False
    )
    assert (
        opportunities_readback._ranking_output_blocked(
            run=run,
            visibility=blocked_visibility,
        )
        is True
    )

    monkeypatch.setattr(
        opportunities_readback,
        "evaluate_assessment_visibility",
        lambda *args, **kwargs: visible_visibility,
    )
    monkeypatch.setattr(
        opportunities_readback,
        "build_override_summary",
        lambda *args, **kwargs: AssessmentOverrideSummaryRead.model_construct(
            active_overrides=[],
            effective_review_status=None,
            effective_manual_review_required=None,
            ranking_suppressed=True,
            display_block_reason="Ranking suppressed by override.",
            effective_valuation=_valuation_result(),
        ),
    )
    suppressed_detail = opportunities_readback.get_opportunity(
        SimpleNamespace(),
        site_id=site.id,
        viewer_role=AppRoleName.ANALYST,
        include_hidden=False,
    )
    assert suppressed_detail is not None
    assert suppressed_detail.probability_band == OpportunityBand.HOLD
    assert suppressed_detail.hold_reason == "Ranking suppressed by override."
    assert suppressed_detail.valuation.expected_uplift_mid == 33.0

    fake_summaries = [
        OpportunitySummaryRead.model_construct(
            site_id=site.id,
            display_name=site.display_name,
            borough_id="camden",
            borough_name="Camden",
            assessment_id=run.id,
            scenario_id=scenario.id,
            probability_band=OpportunityBand.HOLD,
            hold_reason="Matched fixture",
            ranking_reason="Matched fixture",
            hidden_mode_only=True,
            visibility=visible_visibility,
            display_block_reason=None,
            eligibility_status=EligibilityStatus.PASS,
            estimate_status=EstimateStatus.NONE,
            manual_review_required=False,
            valuation_quality=ValuationQuality.MEDIUM,
            asking_price_gbp=150_000,
            asking_price_basis_type=None,
            auction_date=date.today() + timedelta(days=3),
            post_permission_value_mid=125_000.0,
            uplift_mid=25_000.0,
            expected_uplift_mid=33.0,
            same_borough_support_count=3,
            site_summary=site,
            scenario_summary=scenario,
        ),
        OpportunitySummaryRead.model_construct(
            site_id=_fixed_uuid(59),
            display_name="Other site",
            borough_id="southwark",
            borough_name="Southwark",
            assessment_id=_fixed_uuid(60),
            scenario_id=_fixed_uuid(61),
            probability_band=OpportunityBand.BAND_B,
            hold_reason=None,
            ranking_reason="Other",
            hidden_mode_only=True,
            visibility=visible_visibility,
            display_block_reason=None,
            eligibility_status=EligibilityStatus.PASS,
            estimate_status=EstimateStatus.NONE,
            manual_review_required=True,
            valuation_quality=ValuationQuality.LOW,
            asking_price_gbp=250_000,
            asking_price_basis_type=None,
            auction_date=date.today() + timedelta(days=30),
            post_permission_value_mid=None,
            uplift_mid=None,
            expected_uplift_mid=None,
            same_borough_support_count=0,
            site_summary=site,
            scenario_summary=scenario,
        ),
    ]
    monkeypatch.setattr(
        opportunities_readback,
        "_latest_runs_by_site",
        lambda *args, **kwargs: [
            run,
            SimpleNamespace(id=_fixed_uuid(62), site_id=_fixed_uuid(63)),
        ],
    )
    monkeypatch.setattr(
        opportunities_readback,
        "_serialize_opportunity_summary",
        lambda *args, **kwargs: (
            fake_summaries[0] if kwargs["run"].site_id == run.site_id else fake_summaries[1]
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
