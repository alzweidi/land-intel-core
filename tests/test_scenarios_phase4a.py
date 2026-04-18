from __future__ import annotations

import uuid

from landintel.domain.enums import (
    EligibilityStatus,
    GeomConfidence,
    GeomSourceType,
    ScenarioSource,
    ScenarioStatus,
)
from landintel.domain.models import SiteScenario
from landintel.domain.schemas import ScenarioConfirmRequest
from landintel.planning.enrich import get_borough_baseline_pack
from landintel.scenarios.normalize import (
    confirm_or_update_scenario,
    mark_site_scenarios_stale_for_geometry_change,
)
from landintel.scenarios.suggest import _auto_confirm_allowed, _citations_complete

from tests.test_planning_phase3a import _build_camden_site, _build_southwark_site


def test_rulepack_citations_require_durable_provenance() -> None:
    assert _citations_complete(
        [
            {
                "label": "Rule source",
                "source_family": "BOROUGH_REGISTER",
                "effective_date": "2026-04-01",
                "url": "https://camden.example/planning/CAM-2025-1100-P",
            }
        ]
    )
    assert _citations_complete(
        [
            {
                "label": "Rule source",
                "source_family": "BOROUGH_REGISTER",
                "effective_date": "2026-04-01",
                "source_snapshot_id": "snapshot-1",
            }
        ]
    )
    assert not _citations_complete([])
    assert not _citations_complete([{"label": "Rule source"}])
    assert not _citations_complete([{"source_family": "BOROUGH_REGISTER"}])
    assert not _citations_complete(
        [{"label": "Rule source", "source_family": "BOROUGH_REGISTER"}]
    )
    assert not _citations_complete(
        [
            {
                "label": "Rule source",
                "source_family": "BOROUGH_REGISTER",
                "url": "https://camden.example/planning/CAM-2025-1100-P",
            }
        ]
    )


def test_auto_confirm_gate_stays_conservative_without_strong_history() -> None:
    site = type("SiteStub", (), {"geom_confidence": GeomConfidence.MEDIUM})()
    allowed, reasons = _auto_confirm_allowed(
        site=site,
        template_key="resi_5_9_full",
        preferred_route="FULL",
        support=type("SupportStub", (), {"strong": False})(),
        extant_permission=type("ExtantStub", (), {"eligibility_status": EligibilityStatus.PASS})(),
        missing_data_flags=[],
        warning_codes=[],
    )
    assert allowed is False
    assert any(code == "AUTO_CONFIRM_BLOCKED_HISTORICAL_SUPPORT" for code, _ in reasons)


def test_camden_site_scenarios_suggest_and_read_back(
    client,
    drain_jobs,
    seed_listing_sources,
    seed_planning_data,
):
    del seed_listing_sources
    del seed_planning_data
    site_payload = _build_camden_site(client, drain_jobs)

    suggest = client.post(
        f"/api/sites/{site_payload['id']}/scenarios/suggest",
        json={"requested_by": "pytest"},
    )
    assert suggest.status_code == 200
    suggested = suggest.json()
    assert suggested["items"]
    assert all(item["template_key"].startswith("resi_") for item in suggested["items"])
    assert all(item["status"] == ScenarioStatus.ANALYST_REQUIRED for item in suggested["items"])
    assert all(item["manual_review_required"] for item in suggested["items"])
    assert all(
        "NEAREST_HISTORICAL_SUPPORT_NOT_STRONG" in item["missing_data_flags"]
        for item in suggested["items"]
    )

    detail = client.get(f"/api/sites/{site_payload['id']}").json()
    assert detail["scenarios"]
    assert detail["evidence"]["for"]
    assert any(item["topic"] == "scenario_fit" for item in detail["evidence"]["for"])


def test_scenario_confirm_with_edits_supersedes_auto_suggestion(
    client,
    drain_jobs,
    seed_listing_sources,
    seed_planning_data,
):
    del seed_listing_sources
    del seed_planning_data
    site_payload = _build_camden_site(client, drain_jobs)
    suggest = client.post(
        f"/api/sites/{site_payload['id']}/scenarios/suggest",
        json={"requested_by": "pytest"},
    ).json()
    scenario_id = suggest["items"][0]["id"]

    response = client.post(
        f"/api/scenarios/{scenario_id}/confirm",
        json={
            "requested_by": "pytest",
            "units_assumed": 7,
            "review_notes": "Analyst confirms seven-unit full-route test scenario.",
        },
    )
    assert response.status_code == 200
    detail = response.json()
    assert detail["status"] == ScenarioStatus.ANALYST_CONFIRMED
    assert detail["scenario_source"] == ScenarioSource.ANALYST
    assert detail["supersedes_id"] == scenario_id
    assert detail["units_assumed"] == 7
    assert detail["red_line_geom_hash"] == site_payload["current_geometry"]["geom_hash"]
    assert any(
        review["review_status"] == ScenarioStatus.ANALYST_CONFIRMED
        for review in detail["review_history"]
    )


def test_confirmed_scenario_becomes_stale_after_geometry_change(
    client,
    drain_jobs,
    seed_listing_sources,
    seed_planning_data,
):
    del seed_listing_sources
    del seed_planning_data
    site_payload = _build_camden_site(client, drain_jobs)
    suggest = client.post(
        f"/api/sites/{site_payload['id']}/scenarios/suggest",
        json={"requested_by": "pytest"},
    ).json()
    scenario_id = suggest["items"][0]["id"]

    confirmed = client.post(
        f"/api/scenarios/{scenario_id}/confirm",
        json={"requested_by": "pytest", "review_notes": "Confirm without edits."},
    ).json()
    live_scenario_id = confirmed["id"]

    geometry_update = client.post(
        f"/api/sites/{site_payload['id']}/geometry",
        json={
            "geom_4326": {
                "type": "Polygon",
                "coordinates": [[
                    [-0.14270, 51.53594],
                    [-0.14144, 51.53594],
                    [-0.14144, 51.53640],
                    [-0.14270, 51.53640],
                    [-0.14270, 51.53594]
                ]]
            },
            "source_type": GeomSourceType.ANALYST_DRAWN,
            "confidence": GeomConfidence.HIGH,
            "reason": "Broader analyst red line for Phase 4A stale-state test.",
            "created_by": "pytest"
        },
    )
    assert geometry_update.status_code == 200

    stale = client.get(f"/api/scenarios/{live_scenario_id}")
    assert stale.status_code == 200
    payload = stale.json()
    assert payload["status"] == ScenarioStatus.ANALYST_REQUIRED
    assert payload["manual_review_required"] is True
    assert payload["stale_reason"]
    assert "SCENARIO_STALE_GEOMETRY" in payload["warning_codes"]


def test_active_extant_permission_excludes_new_scenario_suggestions(
    client,
    drain_jobs,
    seed_listing_sources,
    seed_planning_data,
):
    del seed_listing_sources
    del seed_planning_data
    site_payload = _build_southwark_site(client, drain_jobs)

    suggest = client.post(
        f"/api/sites/{site_payload['id']}/scenarios/suggest",
        json={"requested_by": "pytest"},
    )
    assert suggest.status_code == 200
    payload = suggest.json()
    assert payload["items"] == []
    assert payload["excluded_templates"]
    assert all(
        any(reason["code"] == "ACTIVE_EXTANT_PERMISSION_FOUND" for reason in item["reasons"])
        for item in payload["excluded_templates"]
    )


def test_rulepack_fixture_is_visible_through_baseline_pack(seed_planning_data, db_session):
    del seed_planning_data
    pack = get_borough_baseline_pack(session=db_session, borough_id="camden")
    assert pack is not None
    assert len(pack.rulepacks) == 3
    assert all(
        _citations_complete(list(rule.rule_json.get("citations") or []))
        for rule in pack.rulepacks
    )


def test_confirm_keeps_extant_abstain_sites_in_analyst_required(
    client,
    drain_jobs,
    seed_listing_sources,
    seed_planning_data,
    db_session,
):
    del seed_listing_sources
    del seed_planning_data
    site_payload = _build_camden_site(client, drain_jobs)
    suggest = client.post(
        f"/api/sites/{site_payload['id']}/scenarios/suggest",
        json={"requested_by": "pytest"},
    ).json()
    scenario_id = uuid.UUID(suggest["items"][0]["id"])

    db_session.expire_all()
    scenario = db_session.get(SiteScenario, scenario_id)
    assert scenario is not None
    scenario.site.borough_id = "islington"
    db_session.flush()

    confirmed = confirm_or_update_scenario(
        session=db_session,
        scenario_id=scenario_id,
        request=ScenarioConfirmRequest(
            requested_by="pytest",
            review_notes="Confirm while mandatory coverage is incomplete.",
        ),
    )
    assert confirmed.status == ScenarioStatus.ANALYST_REQUIRED
    assert confirmed.manual_review_required is True
    assert confirmed.stale_reason is not None
    assert "extant permission screening must abstain" in confirmed.stale_reason.lower()


def test_mark_site_scenarios_stale_for_geometry_change_downgrades_confirmed_status(
    client,
    drain_jobs,
    seed_listing_sources,
    seed_planning_data,
    db_session,
):
    del seed_listing_sources
    del seed_planning_data
    site_payload = _build_camden_site(client, drain_jobs)
    suggest = client.post(
        f"/api/sites/{site_payload['id']}/scenarios/suggest",
        json={"requested_by": "pytest"},
    ).json()
    db_session.expire_all()
    scenario = db_session.get(SiteScenario, uuid.UUID(suggest["items"][0]["id"]))
    assert scenario is not None
    scenario.status = ScenarioStatus.ANALYST_CONFIRMED
    scenario.manual_review_required = False
    site = scenario.site
    site.geom_hash = "deadbeef" * 8
    changed = mark_site_scenarios_stale_for_geometry_change(
        session=db_session,
        site=site,
        requested_by="pytest",
    )
    assert changed == 1
    assert scenario.status == ScenarioStatus.ANALYST_REQUIRED
    assert scenario.manual_review_required is True
    assert scenario.stale_reason
