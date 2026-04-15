from __future__ import annotations

import uuid
from datetime import date
from types import SimpleNamespace

from landintel.domain import models
from landintel.domain.enums import (
    OpportunityBand,
    PriceBasisType,
    ProposalForm,
    ScenarioSource,
    ScenarioStatus,
    ValuationQuality,
)
from landintel.scoring.quality import round_display_probability
from landintel.valuation.assumptions import (
    DEFAULT_VALUATION_ASSUMPTION_VERSION,
    ensure_default_assumption_set,
)
from landintel.valuation.market import rebase_price_with_ukhpi
from landintel.valuation.quality import (
    derive_valuation_quality,
    evaluate_divergence,
    widen_range_for_divergence,
)
from landintel.valuation.ranking import derive_opportunity_band, ranking_sort_key
from landintel.valuation.residual import compute_residual_valuation, derive_area_summary

from tests.test_assessments_phase5a import _build_confirmed_camden_scenario
from tests.test_planning_phase3a import _build_southwark_site
from tests.test_scoring_phase6a import _build_hidden_releases


def _simple_site(*, borough_id: str = "camden", price: int | None = 950000):
    return SimpleNamespace(
        borough_id=borough_id,
        current_price_gbp=price,
        current_price_basis_type=(
            PriceBasisType.GUIDE_PRICE if price is not None else PriceBasisType.UNKNOWN
        ),
    )


def _simple_scenario(*, template_key: str = "resi_5_9_full", units_assumed: int = 6):
    return SimpleNamespace(
        template_key=template_key,
        units_assumed=units_assumed,
        housing_mix_assumed_json={},
    )


def _confirm_template_scenario(
    *,
    client,
    db_session,
    site_id: str,
    template_key: str | None,
) -> dict[str, object]:
    payload = {
        "requested_by": "pytest",
        "manual_seed": True,
    }
    if template_key is not None:
        payload["template_keys"] = [template_key]
    suggest = client.post(
        f"/api/sites/{site_id}/scenarios/suggest",
        json=payload,
    )
    assert suggest.status_code == 200
    items = suggest.json()["items"]
    scenario_payload = next(
        (
            item
            for item in items
            if template_key is not None and item["template_key"] == template_key
        ),
        None,
    )
    if scenario_payload is None:
        scenario_payload = next(
            (item for item in items if item["template_key"] != "resi_5_9_full"),
            None,
        )
    if scenario_payload is None:
        site = db_session.get(models.SiteCandidate, uuid.UUID(site_id))
        assert site is not None
        current_revision = next(
            (
                row
                for row in site.geometry_revisions
                if row.geom_hash == site.geom_hash
            ),
            None,
        )
        if current_revision is None:
            current_revision = site.geometry_revisions[0]
        manual = models.SiteScenario(
            id=uuid.uuid4(),
            site_id=site.id,
            template_key="resi_1_4_full",
            template_version="v1",
            proposal_form=ProposalForm.REDEVELOPMENT,
            units_assumed=4,
            route_assumed="FULL",
            height_band_assumed="1_4_STOREYS",
            net_developable_area_pct=0.65,
            housing_mix_assumed_json={"2_bed": 0.5, "3_bed": 0.5},
            parking_assumption="Car-light assumption for Phase 7A unsupported-template setup.",
            affordable_housing_assumption="Default small-site assumption.",
            access_assumption="Frontage access assumed from current listing evidence.",
            site_geometry_revision_id=current_revision.id,
            red_line_geom_hash=site.geom_hash,
            scenario_source=ScenarioSource.ANALYST,
            status=ScenarioStatus.ANALYST_CONFIRMED,
            is_current=True,
            is_headline=False,
            manual_review_required=False,
            rationale_json={"manual_seed": True},
            evidence_json={},
            created_by="pytest",
        )
        db_session.add(manual)
        db_session.commit()
        return {"id": str(manual.id), "template_key": manual.template_key}
    confirm = client.post(
        f"/api/scenarios/{scenario_payload['id']}/confirm",
        json={
            "requested_by": "pytest",
            "review_notes": "Confirmed for valuation testing.",
        },
    )
    assert confirm.status_code == 200
    confirmed = confirm.json()
    assert confirmed["status"] == ScenarioStatus.ANALYST_CONFIRMED.value
    return {
        "id": confirmed["id"],
        "template_key": confirmed["template_key"],
    }


def test_area_derivation_and_missing_basis_handling(db_session):
    assumption_set = ensure_default_assumption_set(db_session)
    area = derive_area_summary(
        scenario=_simple_scenario(template_key="resi_5_9_full", units_assumed=6),
        assumption_set=assumption_set,
    )
    assert area.unit_mix_counts == {"1_bed": 1, "2_bed": 3, "3_bed": 2}
    assert area.nsa_sqm == 456.0
    assert area.gia_sqm == 524.4

    residual = compute_residual_valuation(
        site=_simple_site(price=None),
        scenario=_simple_scenario(template_key="resi_5_9_full", units_assumed=6),
        assumption_set=assumption_set,
        price_per_sqm_low=5600.0,
        price_per_sqm_mid=6100.0,
        price_per_sqm_high=6600.0,
    )
    assert residual.post_permission_value_mid is not None
    assert residual.uplift_low is None
    assert residual.uplift_mid is None
    assert residual.uplift_high is None
    assert residual.basis_json["basis_available"] is False


def test_ukhpi_rebasing_and_quality_helpers(seed_valuation_data, db_session):
    del seed_valuation_data
    rebased = rebase_price_with_ukhpi(
        session=db_session,
        borough_id="camden",
        price_gbp=800000.0,
        sale_date=date(2024, 5, 17),
        as_of_date=date(2026, 4, 15),
    )
    assert round(rebased, 2) == 859282.37

    divergence = evaluate_divergence(
        primary_mid=1500000.0,
        secondary_mid=1100000.0,
        threshold_pct=0.2,
        threshold_abs_gbp=250000.0,
    )
    assert divergence is True
    assert widen_range_for_divergence(
        primary_low=1300000.0,
        primary_mid=1500000.0,
        primary_high=1700000.0,
        secondary_low=1000000.0,
        secondary_mid=1100000.0,
        secondary_high=1250000.0,
    ) == (1000000.0, 1300000.0, 1700000.0)

    quality = derive_valuation_quality(
        asking_price_present=False,
        sales_comp_count=2,
        land_comp_count=0,
        policy_inputs_known=True,
        scenario_area_stable=True,
        divergence_material=True,
    )
    assert quality.valuation_quality == ValuationQuality.LOW
    assert quality.manual_review_required is True
    assert "Acquisition basis is missing." in quality.reasons


def test_missing_probability_holds_band_and_ranking_is_planning_first():
    assert round_display_probability(0.77) == "75%"

    hold = derive_opportunity_band(
        eligibility_status=None,
        approval_probability_raw=None,
        estimate_quality=None,
        manual_review_required=True,
        score_execution_status="NO_ACTIVE_HIDDEN_RELEASE",
    )
    assert hold.probability_band == OpportunityBand.HOLD
    assert hold.hold_reason == "No active hidden release is available for this scope."

    stronger_planning = ranking_sort_key(
        probability_band=OpportunityBand.BAND_B,
        expected_uplift_mid=2500000.0,
        valuation_quality=ValuationQuality.LOW,
        auction_date=None,
        today=date(2026, 4, 15),
        asking_price_present=False,
        same_borough_support_count=0,
        display_name="Band B site",
    )
    weaker_planning = ranking_sort_key(
        probability_band=OpportunityBand.BAND_C,
        expected_uplift_mid=9000000.0,
        valuation_quality=ValuationQuality.HIGH,
        auction_date=None,
        today=date(2026, 4, 15),
        asking_price_present=True,
        same_borough_support_count=5,
        display_name="Band C site",
    )
    assert stronger_planning < weaker_planning


def test_assessment_builds_valuation_block_and_replay_is_stable(
    client,
    drain_jobs,
    seed_listing_sources,
    seed_planning_data,
    seed_valuation_data,
    db_session,
    storage,
):
    del seed_listing_sources
    del seed_planning_data
    del seed_valuation_data
    _build_hidden_releases(db_session=db_session, storage=storage)
    site_payload, scenario_payload = _build_confirmed_camden_scenario(client, drain_jobs)

    payload = {
        "site_id": site_payload["id"],
        "scenario_id": scenario_payload["id"],
        "as_of_date": "2026-04-15",
        "requested_by": "pytest",
        "hidden_mode": True,
    }
    first = client.post("/api/assessments", json=payload)
    assert first.status_code == 200
    first_payload = first.json()
    assert first_payload["valuation"] is not None
    assert (
        first_payload["valuation"]["valuation_assumption_version"]
        == DEFAULT_VALUATION_ASSUMPTION_VERSION
    )
    assert first_payload["valuation"]["post_permission_value_mid"] is not None
    assert first_payload["valuation"]["uplift_mid"] is not None
    assert first_payload["valuation"]["expected_uplift_mid"] is not None
    assert first_payload["valuation"]["payload_hash"]

    second = client.post("/api/assessments", json=payload)
    assert second.status_code == 200
    second_payload = second.json()
    assert second_payload["id"] == first_payload["id"]
    assert second_payload["valuation"]["payload_hash"] == first_payload["valuation"]["payload_hash"]
    assert (
        second_payload["prediction_ledger"]["result_payload_hash"]
        == first_payload["prediction_ledger"]["result_payload_hash"]
    )

    detail = client.get(f"/api/assessments/{first_payload['id']}?hidden_mode=true")
    assert detail.status_code == 200
    detail_payload = detail.json()
    assert detail_payload["valuation"]["sense_check_json"]["fallback_path"]
    assert detail_payload["valuation"]["valuation_quality"] in {"MEDIUM", "LOW", "HIGH"}


def test_opportunities_endpoint_ranks_scored_sites_and_holds_no_release_cases(
    client,
    drain_jobs,
    seed_listing_sources,
    seed_planning_data,
    seed_valuation_data,
    db_session,
    storage,
):
    del seed_listing_sources
    del seed_planning_data
    del seed_valuation_data
    _build_hidden_releases(db_session=db_session, storage=storage)

    camden_site, camden_scenario = _build_confirmed_camden_scenario(client, drain_jobs)
    camden_assessment = client.post(
        "/api/assessments",
        json={
            "site_id": camden_site["id"],
            "scenario_id": camden_scenario["id"],
            "as_of_date": "2026-04-15",
            "requested_by": "pytest",
            "hidden_mode": True,
        },
    )
    assert camden_assessment.status_code == 200

    southwark_site = _build_southwark_site(client, drain_jobs)
    southwark_scenario = _confirm_template_scenario(
        client=client,
        db_session=db_session,
        site_id=southwark_site["id"],
        template_key=None,
    )
    southwark_assessment = client.post(
        "/api/assessments",
        json={
            "site_id": southwark_site["id"],
            "scenario_id": southwark_scenario["id"],
            "as_of_date": "2026-04-15",
            "requested_by": "pytest",
            "hidden_mode": True,
        },
    )
    assert southwark_assessment.status_code == 200

    opportunities = client.get("/api/opportunities")
    assert opportunities.status_code == 200
    payload = opportunities.json()
    assert payload["total"] >= 2
    by_site = {item["site_id"]: item for item in payload["items"]}
    assert by_site[camden_site["id"]]["probability_band"] in {
        "Band A",
        "Band B",
        "Band C",
        "Band D",
    }
    assert by_site[camden_site["id"]]["expected_uplift_mid"] is not None
    assert by_site[southwark_site["id"]]["probability_band"] == "Hold"
    assert by_site[southwark_site["id"]]["expected_uplift_mid"] is None
    assert by_site[southwark_site["id"]]["hold_reason"]
    assert by_site[southwark_site["id"]]["expected_uplift_mid"] is None
    assert southwark_scenario["template_key"] != "resi_5_9_full"

    detail = client.get(f"/api/opportunities/{camden_site['id']}")
    assert detail.status_code == 200
    detail_payload = detail.json()
    assert detail_payload["valuation"] is not None
    assert detail_payload["assessment"] is not None
    assert (
        detail_payload["ranking_factors"]["probability_band"]
        == detail_payload["probability_band"]
    )
