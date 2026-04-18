from __future__ import annotations

import json
import uuid
from datetime import date
from types import SimpleNamespace

import pytest
from landintel.domain.enums import (
    CalibrationMethod,
    EligibilityStatus,
    GeomConfidence,
    MarketLandCompSourceType,
    ModelReleaseStatus,
    OpportunityBand,
    PriceBasisType,
    ProposalForm,
    ReleaseChannel,
    ScenarioStatus,
    SourceFreshnessStatus,
    SourceParseStatus,
    ValuationQuality,
)
from landintel.domain.models import (
    ActiveReleaseScope,
    MarketIndexSeries,
    MarketLandComp,
    MarketSaleComp,
    ModelRelease,
    RawAsset,
    SourceSnapshot,
    ValuationAssumptionSet,
)
from landintel.scoring.calibration import apply_calibration, fit_platt_scaler
from landintel.scoring.logreg_model import (
    _stddev,
    clamp_probability,
    derive_transform_spec,
    encode_feature_values,
    explain_base_feature_contributions,
    fit_logistic_regression,
    predict_probability,
)
from landintel.scoring.quality import (
    derive_geometry_quality,
    derive_ood_status,
    derive_scenario_quality,
    derive_source_coverage_quality,
    derive_support_quality,
    final_estimate_quality,
    round_display_probability,
)
from landintel.scoring.release import (
    activate_model_release,
    load_release_artifact_json,
    resolve_active_release,
    retire_model_release,
    scope_key_for,
)
from landintel.valuation.assumptions import (
    DEFAULT_VALUATION_ASSUMPTION_VERSION,
    ensure_default_assumption_set,
    resolve_active_assumption_set,
)
from landintel.valuation.market import (
    build_land_comp_summary,
    build_sales_comp_summary,
    rebase_price_with_ukhpi,
)
from landintel.valuation.quality import (
    derive_valuation_quality,
    evaluate_divergence,
    widen_range_for_divergence,
)
from landintel.valuation.ranking import derive_opportunity_band, ranking_sort_key
from landintel.valuation.residual import (
    build_basis_json,
    canonical_payload_hash,
    compute_residual_valuation,
    derive_area_summary,
)


class FakeStorage:
    def __init__(self, payloads: dict[str, bytes]):
        self._payloads = payloads

    def get_bytes(self, path: str) -> bytes:
        return self._payloads[path]


def _make_source_bundle(db_session):
    snapshot = SourceSnapshot(
        source_family="MARKET_TEST",
        source_name="Market test snapshot",
        source_uri="https://example.test/snapshot",
        schema_hash="a" * 64,
        content_hash="b" * 64,
        freshness_status=SourceFreshnessStatus.FRESH,
        parse_status=SourceParseStatus.PARSED,
        manifest_json={},
    )
    db_session.add(snapshot)
    db_session.flush()
    asset = RawAsset(
        source_snapshot_id=snapshot.id,
        asset_type="JSON",
        original_url="https://example.test/asset",
        storage_path=f"assets/{snapshot.id}.json",
        mime_type="application/json",
        content_sha256="c" * 64,
        size_bytes=1,
    )
    db_session.add(asset)
    db_session.flush()
    return snapshot, asset


def _make_release(
    *,
    template_key: str = "resi_5_9_full",
    borough_id: str | None = "camden",
    status: ModelReleaseStatus = ModelReleaseStatus.VALIDATED,
) -> ModelRelease:
    return ModelRelease(
        id=uuid.uuid4(),
        template_key=template_key,
        release_channel=ReleaseChannel.HIDDEN,
        scope_key=scope_key_for(template_key=template_key, borough_id=borough_id),
        scope_borough_id=borough_id,
        status=status,
        model_kind="REGULARIZED_LOGISTIC_REGRESSION",
        transform_version="v1",
        feature_version="phase6a_v1",
        calibration_method=CalibrationMethod.NONE,
        model_artifact_path=None,
        model_artifact_hash=None,
        calibration_artifact_path=None,
        calibration_artifact_hash=None,
        validation_artifact_path=None,
        validation_artifact_hash=None,
        model_card_path=None,
        model_card_hash=None,
        support_count=0,
        positive_count=0,
        negative_count=0,
        metrics_json={},
        manifest_json={},
    )


def test_calibration_helpers_cover_error_and_passthrough_paths():
    with pytest.raises(ValueError):
        fit_platt_scaler(raw_probabilities=[], labels=[])

    assert apply_calibration(0.0, calibration_artifact=None) == clamp_probability(0.0)
    assert apply_calibration(0.75, calibration_artifact={"method": "NONE"}) == clamp_probability(
        0.75
    )


def test_logreg_helpers_cover_missing_feature_and_error_paths():
    rows = [
        {"num": 1.0, "cat": "a", "flag": True},
        {"num": None, "cat": "", "flag": None},
    ]
    transform_spec = derive_transform_spec(
        feature_rows=rows,
        numeric_features=["num"],
        categorical_features=["cat"],
        boolean_features=["flag"],
    )

    assert transform_spec["numeric"]["num"]["has_missing"] is True
    assert transform_spec["categorical"]["cat"]["has_missing"] is True
    assert "__MISSING__" in transform_spec["categorical"]["cat"]["categories"]
    assert transform_spec["boolean"]["flag"]["has_missing"] is True
    assert _stddev([4.0], 4.0) == 1.0
    assert len(
        encode_feature_values({"num": None, "cat": "", "flag": None}, transform_spec=transform_spec)
    ) == 6

    with pytest.raises(ValueError):
        fit_logistic_regression(encoded_rows=[], labels=[])

    model_artifact = {
        "intercept": 0.2,
        "coefficients": [0.4, -0.6, 0.8, 0.1, -0.2, 0.3],
        "transform_spec": transform_spec,
    }
    probability, vector = predict_probability(
        model_artifact,
        feature_values={"num": 1.0, "cat": "a", "flag": True},
    )
    contributions = explain_base_feature_contributions(
        model_artifact,
        feature_values={"num": 1.0, "cat": "a", "flag": True},
    )

    assert 0.0 < probability < 1.0
    assert len(vector) == 6
    assert set(contributions) == {"num", "cat", "flag"}


def test_scoring_quality_helpers_cover_all_branches():
    assert round_display_probability(0.02) == "0%"
    assert round_display_probability(0.72) == "70%"
    assert round_display_probability(0.78) == "80%"

    assert derive_source_coverage_quality({}) == "LOW"
    assert (
        derive_source_coverage_quality(
            {
                "source_coverage": [
                    {"coverage_status": "MISSING", "freshness_status": "FRESH"},
                    {"coverage_status": "COMPLETE", "freshness_status": "FRESH"},
                ]
            }
        )
        == "LOW"
    )
    assert (
        derive_source_coverage_quality(
            {
                "source_coverage": [
                    {"coverage_status": "PARTIAL", "freshness_status": "FRESH"},
                    {"coverage_status": "COMPLETE", "freshness_status": "STALE"},
                ]
            }
        )
        == "MEDIUM"
    )
    assert (
        derive_source_coverage_quality(
            {
                "source_coverage": [
                    {"coverage_status": "COMPLETE", "freshness_status": "FRESH"},
                    {"coverage_status": "COMPLETE", "freshness_status": "FRESH"},
                ]
            }
        )
        == "HIGH"
    )

    assert derive_geometry_quality(GeomConfidence.HIGH) == "HIGH"
    assert derive_geometry_quality(GeomConfidence.MEDIUM) == "MEDIUM"
    assert derive_geometry_quality(GeomConfidence.LOW) == "LOW"

    assert (
        derive_scenario_quality(
            scenario=SimpleNamespace(
                status=ScenarioStatus.SUGGESTED,
                manual_review_required=False,
                stale_reason=None,
            ),
            site=SimpleNamespace(manual_review_required=False),
        )
        == "LOW"
    )
    assert (
        derive_scenario_quality(
            scenario=SimpleNamespace(
                status=ScenarioStatus.AUTO_CONFIRMED,
                manual_review_required=True,
                stale_reason=None,
            ),
            site=SimpleNamespace(manual_review_required=False),
        )
        == "MEDIUM"
    )
    assert (
        derive_scenario_quality(
            scenario=SimpleNamespace(
                status=ScenarioStatus.ANALYST_CONFIRMED,
                manual_review_required=False,
                stale_reason=None,
            ),
            site=SimpleNamespace(manual_review_required=False),
        )
        == "HIGH"
    )

    assert (
        derive_support_quality(
            support_count=10,
            same_borough_support_count=3,
            comparable_count=4,
        )
        == "HIGH"
    )
    assert (
        derive_support_quality(
            support_count=7,
            same_borough_support_count=1,
            comparable_count=2,
        )
        == "MEDIUM"
    )
    assert (
        derive_support_quality(
            support_count=6,
            same_borough_support_count=0,
            comparable_count=1,
        )
        == "LOW"
    )

    assert derive_ood_status(
        nearest_distance=0.4,
        same_template_support_count=6,
        same_borough_support_count=3,
        distance_thresholds={},
    ) == ("OUT_OF_DISTRIBUTION", "LOW")
    assert derive_ood_status(
        nearest_distance=0.4,
        same_template_support_count=7,
        same_borough_support_count=0,
        distance_thresholds={},
    ) == ("EDGE_OF_SUPPORT", "LOW")
    assert derive_ood_status(
        nearest_distance=None,
        same_template_support_count=7,
        same_borough_support_count=1,
        distance_thresholds={},
    ) == ("EDGE_OF_SUPPORT", "LOW")
    assert derive_ood_status(
        nearest_distance=4.0,
        same_template_support_count=7,
        same_borough_support_count=1,
        distance_thresholds={"medium": 1.8, "high": 3.0},
    ) == ("OUT_OF_DISTRIBUTION", "LOW")
    assert derive_ood_status(
        nearest_distance=2.0,
        same_template_support_count=7,
        same_borough_support_count=1,
        distance_thresholds={"medium": 1.8, "high": 3.0},
    ) == ("EDGE_OF_SUPPORT", "MEDIUM")
    assert derive_ood_status(
        nearest_distance=1.0,
        same_template_support_count=7,
        same_borough_support_count=1,
        distance_thresholds={"medium": 1.8, "high": 3.0},
    ) == ("IN_SUPPORT", "HIGH")

    assert final_estimate_quality(quality_components=[]) == ValuationQuality.LOW
    assert final_estimate_quality(quality_components=["HIGH", "HIGH"]) == ValuationQuality.HIGH
    assert final_estimate_quality(quality_components=["HIGH", "MEDIUM"]) == ValuationQuality.MEDIUM
    assert final_estimate_quality(quality_components=["HIGH", "LOW"]) == ValuationQuality.LOW


def test_release_and_assumption_helpers_cover_lookup_and_activation_paths(db_session, tmp_path):
    exact_release = _make_release(template_key="resi_5_9_full", borough_id="camden")
    global_release = _make_release(template_key="resi_5_9_full", borough_id=None)
    db_session.add_all([exact_release, global_release])
    db_session.flush()

    db_session.add(
        ActiveReleaseScope(
            scope_key=exact_release.scope_key,
            template_key=exact_release.template_key,
            release_channel=exact_release.release_channel,
            borough_id=exact_release.scope_borough_id,
            model_release_id=exact_release.id,
        )
    )
    db_session.add(
        ActiveReleaseScope(
            scope_key=global_release.scope_key,
            template_key=global_release.template_key,
            release_channel=global_release.release_channel,
            borough_id=global_release.scope_borough_id,
            model_release_id=global_release.id,
        )
    )
    db_session.commit()

    resolved, scope_key = resolve_active_release(
        session=db_session,
        template_key="resi_5_9_full",
        borough_id="camden",
    )
    assert resolved is not None
    assert resolved.id == exact_release.id
    assert scope_key == exact_release.scope_key

    resolved_global, global_scope_key = resolve_active_release(
        session=db_session,
        template_key="resi_5_9_full",
        borough_id="hackney",
    )
    assert resolved_global is not None
    assert resolved_global.id == global_release.id
    assert global_scope_key == global_release.scope_key

    scope_only, missing_scope_key = resolve_active_release(
        session=db_session,
        template_key="resi_10_49_outline",
        borough_id="camden",
    )
    assert scope_only is None
    assert missing_scope_key == scope_key_for(
        template_key="resi_10_49_outline",
        borough_id=None,
    )

    storage = FakeStorage(
        {
            "artifacts/model_releases/test-release/model.json": json.dumps({"ok": True}).encode(),
        }
    )
    artifact_release = _make_release(template_key="resi_1_4_full")
    artifact_release.model_artifact_path = "artifacts/model_releases/test-release/model.json"
    db_session.add(artifact_release)
    db_session.flush()
    assert load_release_artifact_json(
        storage=storage,
        release=artifact_release,
        artifact="model",
    ) == {"ok": True}
    assert load_release_artifact_json(
        storage=storage,
        release=artifact_release,
        artifact="calibration",
    ) is None

    ready_release = _make_release(template_key="resi_10_49_outline", borough_id="camden")
    prior_release = _make_release(template_key="resi_10_49_outline", borough_id="camden")
    ready_release.id = uuid.uuid4()
    prior_release.id = uuid.uuid4()
    ready_release.scope_key = prior_release.scope_key
    db_session.add_all([ready_release, prior_release])
    db_session.flush()
    db_session.add(
        ActiveReleaseScope(
            scope_key=prior_release.scope_key,
            template_key=prior_release.template_key,
            release_channel=prior_release.release_channel,
            borough_id=prior_release.scope_borough_id,
            model_release_id=prior_release.id,
        )
    )
    db_session.commit()

    with pytest.raises(ValueError, match="was not found"):
        activate_model_release(session=db_session, release_id=uuid.uuid4(), requested_by="pytest")

    not_ready = _make_release(status=ModelReleaseStatus.NOT_READY)
    db_session.add(not_ready)
    db_session.commit()
    with pytest.raises(ValueError, match="not ready"):
        activate_model_release(session=db_session, release_id=not_ready.id, requested_by="pytest")

    activated_scope = activate_model_release(
        session=db_session,
        release_id=ready_release.id,
        requested_by="pytest",
    )
    db_session.commit()
    assert activated_scope.model_release_id == ready_release.id
    assert prior_release.status == ModelReleaseStatus.RETIRED

    retired = retire_model_release(
        session=db_session,
        release_id=ready_release.id,
        requested_by="pytest",
    )
    db_session.commit()
    assert retired.status == ModelReleaseStatus.RETIRED

    assert ensure_default_assumption_set(db_session).version == DEFAULT_VALUATION_ASSUMPTION_VERSION
    existing_default = ensure_default_assumption_set(db_session)
    assert ensure_default_assumption_set(db_session).id == existing_default.id

    custom = ValuationAssumptionSet(
        id=uuid.uuid4(),
        version="phase7a_custom",
        cost_json={"build_cost_per_gia_sqm": {"resi_5_9_full": 1.0}},
        policy_burden_json={},
        discount_json={},
        effective_from=date(2025, 1, 1),
    )
    db_session.add(custom)
    db_session.commit()
    assert (
        resolve_active_assumption_set(
            db_session,
            as_of_date=date(2025, 1, 2),
            version="phase7a_custom",
        ).id
        == custom.id
    )
    with pytest.raises(ValueError):
        resolve_active_assumption_set(db_session, as_of_date=date(2025, 1, 2), version="missing")


def test_market_and_residual_helpers_cover_fallback_paths(db_session):
    snapshot, asset = _make_source_bundle(db_session)

    sale_with_area = MarketSaleComp(
        id=uuid.uuid4(),
        transaction_ref="sale-1",
        borough_id="camden",
        source_snapshot_id=snapshot.id,
        raw_asset_id=asset.id,
        sale_date=date(2024, 5, 1),
        price_gbp=800000,
        property_type="HOUSE",
        tenure=None,
        postcode_district=None,
        address_text=None,
        floor_area_sqm=100.0,
        rebased_price_per_sqm_hint=None,
        raw_record_json={},
    )
    sale_with_hint = MarketSaleComp(
        id=uuid.uuid4(),
        transaction_ref="sale-2",
        borough_id=None,
        source_snapshot_id=snapshot.id,
        raw_asset_id=asset.id,
        sale_date=date(2024, 6, 1),
        price_gbp=600000,
        property_type="HOUSE",
        tenure=None,
        postcode_district=None,
        address_text=None,
        floor_area_sqm=None,
        rebased_price_per_sqm_hint=5000.0,
        raw_record_json={},
    )
    index_borough = MarketIndexSeries(
        id=uuid.uuid4(),
        borough_id="camden",
        index_key="UKHPI",
        period_month=date(2024, 5, 1),
        index_value=100.0,
        source_snapshot_id=snapshot.id,
        raw_asset_id=asset.id,
        raw_record_json={},
    )
    index_global = MarketIndexSeries(
        id=uuid.uuid4(),
        borough_id="camden",
        index_key="UKHPI",
        period_month=date(2026, 4, 1),
        index_value=120.0,
        source_snapshot_id=snapshot.id,
        raw_asset_id=asset.id,
        raw_record_json={},
    )
    land_same_borough = MarketLandComp(
        id=uuid.uuid4(),
        comp_ref="land-1",
        borough_id="camden",
        template_key="resi_5_9_full",
        proposal_form=None,
        comp_source_type=MarketLandCompSourceType.ANALYST_BENCHMARK,
        evidence_date=date(2024, 5, 1),
        unit_count=6,
        site_area_sqm=400.0,
        post_permission_value_low=100000.0,
        post_permission_value_mid=120000.0,
        post_permission_value_high=140000.0,
        source_url=None,
        source_snapshot_id=snapshot.id,
        raw_asset_id=asset.id,
        raw_record_json={},
    )
    land_template_only = MarketLandComp(
        id=uuid.uuid4(),
        comp_ref="land-2",
        borough_id="hackney",
        template_key="resi_5_9_full",
        proposal_form=None,
        comp_source_type=MarketLandCompSourceType.ANALYST_BENCHMARK,
        evidence_date=date(2024, 6, 1),
        unit_count=6,
        site_area_sqm=410.0,
        post_permission_value_low=110000.0,
        post_permission_value_mid=130000.0,
        post_permission_value_high=150000.0,
        source_url=None,
        source_snapshot_id=snapshot.id,
        raw_asset_id=asset.id,
        raw_record_json={},
    )
    land_form_only = MarketLandComp(
        id=uuid.uuid4(),
        comp_ref="land-3",
        borough_id="southwark",
        template_key="resi_1_4_full",
        proposal_form=ProposalForm.REDEVELOPMENT,
        comp_source_type=MarketLandCompSourceType.ANALYST_BENCHMARK,
        evidence_date=date(2024, 7, 1),
        unit_count=4,
        site_area_sqm=390.0,
        post_permission_value_low=90000.0,
        post_permission_value_mid=95000.0,
        post_permission_value_high=100000.0,
        source_url=None,
        source_snapshot_id=snapshot.id,
        raw_asset_id=asset.id,
        raw_record_json={},
    )
    empty_land = MarketLandComp(
        id=uuid.uuid4(),
        comp_ref="land-4",
        borough_id="camden",
        template_key="resi_10_49_outline",
        proposal_form=None,
        comp_source_type=MarketLandCompSourceType.ANALYST_BENCHMARK,
        evidence_date=date(2024, 7, 1),
        unit_count=4,
        site_area_sqm=390.0,
        post_permission_value_low=None,
        post_permission_value_mid=None,
        post_permission_value_high=None,
        source_url=None,
        source_snapshot_id=snapshot.id,
        raw_asset_id=asset.id,
        raw_record_json={},
    )
    db_session.add_all(
        [
            sale_with_area,
            sale_with_hint,
            index_borough,
            index_global,
            land_same_borough,
            land_template_only,
            land_form_only,
            empty_land,
        ]
    )
    db_session.commit()

    assert _make_source_bundle(db_session)[0].source_family == "MARKET_TEST"
    assert rebase_price_with_ukhpi(
        session=db_session,
        borough_id="camden",
        price_gbp=100.0,
        sale_date=date(2024, 5, 17),
        as_of_date=date(2026, 4, 15),
    ) == 120.0
    assert rebase_price_with_ukhpi(
        session=db_session,
        borough_id="hackney",
        price_gbp=100.0,
        sale_date=date(2024, 5, 17),
        as_of_date=date(2026, 4, 15),
    ) == 100.0
    assert rebase_price_with_ukhpi(
        session=db_session,
        borough_id="nope",
        price_gbp=100.0,
        sale_date=date(2024, 5, 17),
        as_of_date=date(2024, 5, 17),
    ) == 100.0

    sales_summary = build_sales_comp_summary(
        session=db_session,
        borough_id="camden",
        as_of_date=date(2026, 4, 15),
        max_age_months=36,
    )
    assert sales_summary.count == 2
    assert sales_summary.price_per_sqm_mid is not None

    empty_sales = build_sales_comp_summary(
        session=db_session,
        borough_id="camden",
        as_of_date=date(2020, 1, 1),
        max_age_months=12,
    )
    assert empty_sales.count == 0
    assert empty_sales.price_per_sqm_mid is None

    borough_summary = build_land_comp_summary(
        session=db_session,
        borough_id="camden",
        template_key="resi_5_9_full",
        proposal_form=None,
        as_of_date=date(2026, 4, 15),
    )
    assert borough_summary.fallback_path == "same_borough_same_template"
    assert borough_summary.count == 1

    template_summary = build_land_comp_summary(
        session=db_session,
        borough_id="hackney",
        template_key="resi_5_9_full",
        proposal_form=None,
        as_of_date=date(2026, 4, 15),
    )
    assert template_summary.fallback_path == "same_borough_same_template"
    assert template_summary.count == 1

    form_summary = build_land_comp_summary(
        session=db_session,
        borough_id="camden",
        template_key="resi_10_49_outline",
        proposal_form=ProposalForm.REDEVELOPMENT,
        as_of_date=date(2026, 4, 15),
    )
    assert form_summary.fallback_path == "same_borough_same_template"
    assert form_summary.count == 0

    empty_land_summary = build_land_comp_summary(
        session=db_session,
        borough_id="camden",
        template_key="resi_10_49_outline",
        proposal_form=None,
        as_of_date=date(2020, 1, 1),
    )
    assert empty_land_summary.count == 0
    assert empty_land_summary.post_permission_value_mid is None

    assert derive_valuation_quality(
        asking_price_present=True,
        sales_comp_count=5,
        land_comp_count=2,
        policy_inputs_known=True,
        scenario_area_stable=True,
        divergence_material=False,
    ).valuation_quality == ValuationQuality.HIGH
    assert derive_valuation_quality(
        asking_price_present=True,
        sales_comp_count=4,
        land_comp_count=1,
        policy_inputs_known=True,
        scenario_area_stable=True,
        divergence_material=False,
    ).valuation_quality == ValuationQuality.MEDIUM
    assert derive_valuation_quality(
        asking_price_present=False,
        sales_comp_count=2,
        land_comp_count=0,
        policy_inputs_known=False,
        scenario_area_stable=False,
        divergence_material=True,
    ).manual_review_required is True

    assert evaluate_divergence(
        primary_mid=None,
        secondary_mid=1.0,
        threshold_pct=0.2,
        threshold_abs_gbp=1.0,
    ) is False
    assert evaluate_divergence(
        primary_mid=100.0,
        secondary_mid=70.0,
        threshold_pct=0.2,
        threshold_abs_gbp=40.0,
    ) is True
    assert widen_range_for_divergence(
        primary_low=None,
        primary_mid=None,
        primary_high=None,
        secondary_low=None,
        secondary_mid=None,
        secondary_high=None,
    ) == (None, None, None)
    assert widen_range_for_divergence(
        primary_low=1.0,
        primary_mid=2.0,
        primary_high=3.0,
        secondary_low=0.5,
        secondary_mid=1.5,
        secondary_high=4.0,
    ) == (0.5, 1.75, 4.0)

    scenario = SimpleNamespace(
        template_key="resi_5_9_full",
        units_assumed=6,
        housing_mix_assumed_json={},
    )
    assumption_set = SimpleNamespace(
        cost_json={
            "standard_unit_sizes_nsa_sqm": {"2_bed": 72.0, "3_bed": 94.0},
            "default_mix_by_template": {"resi_5_9_full": {"2_bed": 0.5, "3_bed": 0.5}},
            "gia_multiplier": 1.15,
            "build_cost_per_gia_sqm": {"resi_5_9_full": 2000.0},
            "externals_pct": 0.08,
            "professional_fees_pct": 0.1,
            "planning_surveys_legal_pct": 0.03,
            "contingency_pct": 0.05,
            "finance_pct": 0.06,
            "developer_margin_pct": 0.18,
        },
        policy_burden_json={
            "mayoral_cil_per_sqm": 60.0,
            "borough_cil_per_sqm": {"camden": 35.0, "default": 20.0},
            "affordable_housing_trigger_units": {"default": 10},
            "affordable_housing_burden_pct_of_gdv": {"default": 0.1},
        },
        discount_json={},
        version="phase7a_pytest",
    )
    area_summary = derive_area_summary(scenario=scenario, assumption_set=assumption_set)
    assert area_summary.unit_mix_counts == {"2_bed": 3, "3_bed": 3}
    assert area_summary.nsa_sqm == 498.0
    assert area_summary.gia_sqm == 572.7

    basis_missing = build_basis_json(
        SimpleNamespace(
            borough_id="camden",
            current_price_gbp=None,
            current_price_basis_type=PriceBasisType.UNKNOWN,
        )
    )
    assert basis_missing["basis_available"] is False
    basis_present = build_basis_json(
        SimpleNamespace(
            borough_id="camden",
            current_price_gbp=900000,
            current_price_basis_type=PriceBasisType.GUIDE_PRICE,
        )
    )
    assert basis_present["basis_available"] is True

    residual = compute_residual_valuation(
        site=SimpleNamespace(
            borough_id="camden",
            current_price_gbp=None,
            current_price_basis_type=PriceBasisType.UNKNOWN,
        ),
        scenario=scenario,
        assumption_set=assumption_set,
        price_per_sqm_low=None,
        price_per_sqm_mid=1000.0,
        price_per_sqm_high=1200.0,
    )
    assert residual.result_json["status"] == "INSUFFICIENT_MARKET_DATA"
    assert residual.uplift_mid is None

    assert canonical_payload_hash({"b": 2, "a": 1}) == canonical_payload_hash({"a": 1, "b": 2})


def test_ranking_helpers_cover_band_holds_and_sorting():
    assert derive_opportunity_band(
        eligibility_status=EligibilityStatus.ABSTAIN,
        approval_probability_raw=None,
        estimate_quality=None,
        manual_review_required=False,
        score_execution_status=None,
    ).probability_band == OpportunityBand.HOLD
    assert derive_opportunity_band(
        eligibility_status=None,
        approval_probability_raw=None,
        estimate_quality=None,
        manual_review_required=False,
        score_execution_status="NO_ACTIVE_HIDDEN_RELEASE",
    ).hold_reason == "No active hidden release is available for this scope."
    assert derive_opportunity_band(
        eligibility_status=None,
        approval_probability_raw=0.75,
        estimate_quality="HIGH",
        manual_review_required=False,
        score_execution_status=None,
    ).probability_band == OpportunityBand.BAND_A
    assert derive_opportunity_band(
        eligibility_status=None,
        approval_probability_raw=0.60,
        estimate_quality="HIGH",
        manual_review_required=False,
        score_execution_status=None,
    ).probability_band == OpportunityBand.BAND_B
    assert derive_opportunity_band(
        eligibility_status=None,
        approval_probability_raw=0.45,
        estimate_quality="HIGH",
        manual_review_required=False,
        score_execution_status=None,
    ).probability_band == OpportunityBand.BAND_C
    assert derive_opportunity_band(
        eligibility_status=None,
        approval_probability_raw=0.20,
        estimate_quality="HIGH",
        manual_review_required=False,
        score_execution_status=None,
    ).probability_band == OpportunityBand.BAND_D

    assert ranking_sort_key(
        probability_band=OpportunityBand.BAND_A,
        expected_uplift_mid=1000.0,
        valuation_quality=ValuationQuality.HIGH,
        auction_date=None,
        today=date(2026, 4, 15),
        asking_price_present=False,
        same_borough_support_count=0,
        display_name="Alpha",
    ) < ranking_sort_key(
        probability_band=OpportunityBand.BAND_B,
        expected_uplift_mid=1000.0,
        valuation_quality=ValuationQuality.HIGH,
        auction_date=None,
        today=date(2026, 4, 15),
        asking_price_present=False,
        same_borough_support_count=0,
        display_name="Bravo",
    )
