from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from uuid import UUID

from landintel.assessments.comparables import _select_members
from landintel.assessments.service import (
    create_or_refresh_assessment_run,
    replay_verify_all_assessments,
)
from landintel.domain.enums import (
    ComparableOutcome,
    GeomConfidence,
    GoldSetReviewStatus,
    HistoricalLabelClass,
)
from landintel.features.build import FEATURE_VERSION
from landintel.planning.historical_labels import (
    list_historical_label_cases,
    rebuild_historical_case_labels,
)

from tests.test_planning_phase3a import _build_camden_site


def _build_confirmed_camden_scenario(client, drain_jobs):
    site_payload = _build_camden_site(client, drain_jobs)
    suggest = client.post(
        f"/api/sites/{site_payload['id']}/scenarios/suggest",
        json={
            "requested_by": "pytest",
            "template_keys": ["resi_5_9_full"],
            "manual_seed": True,
        },
    )
    assert suggest.status_code == 200
    suggestions = suggest.json()["items"]
    scenario_id = next(
        item["id"] for item in suggestions if item["template_key"] == "resi_5_9_full"
    )
    confirm = client.post(
        f"/api/scenarios/{scenario_id}/confirm",
        json={"requested_by": "pytest", "review_notes": "Confirmed for Phase 5A assessment tests."},
    )
    assert confirm.status_code == 200
    return site_payload, confirm.json()


def test_historical_label_rebuild_maps_positive_negative_and_excluded(
    seed_planning_data, db_session
):
    del seed_planning_data
    summary = rebuild_historical_case_labels(session=db_session, requested_by="pytest")
    assert summary.positive >= 1
    assert summary.negative >= 1

    rows = list_historical_label_cases(session=db_session)
    by_ref = {row.planning_application.external_ref: row for row in rows}
    assert by_ref["CAM/2025/1100/P"].label_class == HistoricalLabelClass.POSITIVE
    assert by_ref["CAM/2024/0707/F"].label_class == HistoricalLabelClass.NEGATIVE
    assert by_ref["CAM/2026/3001/PA"].label_class == HistoricalLabelClass.EXCLUDED
    assert "Prior approval" in (by_ref["CAM/2026/3001/PA"].label_reason or "")


def test_comparable_fallback_prefers_borough_then_form_then_archetype():
    site = SimpleNamespace(borough_id="camden")
    scenario = SimpleNamespace(units_assumed=6, proposal_form=SimpleNamespace(value="INFILL"))
    rows = [
        SimpleNamespace(
            id="same-borough",
            borough_id="camden",
            proposal_form=SimpleNamespace(value="BACKLAND"),
            template_key="resi_5_9_full",
            label_class=HistoricalLabelClass.POSITIVE,
            units_proposed=6,
            site_area_sqm=410.0,
            archetype_key="other",
            designation_profile_json={},
            first_substantive_decision_date=date(2024, 6, 1),
            valid_date=date(2024, 2, 1),
            planning_application=SimpleNamespace(id="pa-1"),
        ),
        SimpleNamespace(
            id="same-form",
            borough_id="southwark",
            proposal_form=SimpleNamespace(value="INFILL"),
            template_key="resi_5_9_full",
            label_class=HistoricalLabelClass.POSITIVE,
            units_proposed=6,
            site_area_sqm=405.0,
            archetype_key="other",
            designation_profile_json={},
            first_substantive_decision_date=date(2024, 5, 1),
            valid_date=date(2024, 1, 15),
            planning_application=SimpleNamespace(id="pa-2"),
        ),
        SimpleNamespace(
            id="archetype",
            borough_id="hackney",
            proposal_form=SimpleNamespace(value="BACKLAND"),
            template_key="resi_5_9_full",
            label_class=HistoricalLabelClass.POSITIVE,
            units_proposed=7,
            site_area_sqm=395.0,
            archetype_key="match-archetype",
            designation_profile_json={"policy_families": ["SITE_ALLOCATION"]},
            first_substantive_decision_date=date(2023, 9, 1),
            valid_date=date(2023, 4, 10),
            planning_application=SimpleNamespace(id="pa-3"),
        ),
    ]
    matches = _select_members(
        site=site,
        scenario=scenario,
        site_area_sqm=400.0,
        site_archetype="match-archetype",
        site_designation_profile={"policy_families": ["SITE_ALLOCATION"]},
        scenario_form_value="INFILL",
        rows=rows,
        outcome=ComparableOutcome.APPROVED,
        as_of_date=date(2026, 4, 15),
    )
    assert [item.fallback_path for item in matches] == [
        "same_borough_same_template",
        "london_same_template",
        "archetype_same_template",
    ]


def test_assessment_run_builds_frozen_pre_score_artifacts(
    client,
    drain_jobs,
    seed_listing_sources,
    seed_planning_data,
    db_session,
):
    del seed_listing_sources
    del seed_planning_data
    site_payload, scenario_payload = _build_confirmed_camden_scenario(client, drain_jobs)

    run = create_or_refresh_assessment_run(
        session=db_session,
        site_id=UUID(site_payload["id"]),
        scenario_id=UUID(scenario_payload["id"]),
        as_of_date=date(2025, 6, 30),
        requested_by="pytest",
    )
    db_session.commit()
    db_session.refresh(run)

    assert run.state.value == "READY"
    assert run.feature_snapshot is not None
    assert run.feature_snapshot.feature_version == FEATURE_VERSION
    assert run.result is not None
    assert run.result.estimate_status.value == "NONE"
    assert run.result.approval_probability_raw is None
    assert run.result.approval_probability_display is None
    assert run.comparable_case_set is not None
    assert run.prediction_ledger is not None

    values = run.feature_snapshot.feature_json["values"]
    missing_flags = run.feature_snapshot.feature_json["missing_flags"]
    assert values["prior_approval_history_count"] == 0
    assert values["onsite_negative_count"] == 0
    assert missing_flags["ptal_bucket"] is True
    assert missing_flags["distance_to_station_m"] is True


def test_assessment_api_returns_stable_pre_score_payload_and_replay_hashes(
    client,
    drain_jobs,
    seed_listing_sources,
    seed_planning_data,
):
    del seed_listing_sources
    del seed_planning_data
    site_payload, scenario_payload = _build_confirmed_camden_scenario(client, drain_jobs)
    request_payload = {
        "site_id": site_payload["id"],
        "scenario_id": scenario_payload["id"],
        "as_of_date": "2026-04-15",
        "requested_by": "pytest",
    }

    first = client.post("/api/assessments", json=request_payload)
    assert first.status_code == 200
    first_payload = first.json()
    assert first_payload["result"]["estimate_status"] == "NONE"
    assert first_payload["result"]["approval_probability_raw"] is None
    assert first_payload["result"]["approval_probability_display"] is None
    assert "Phase 5A" in first_payload["note"]
    assert first_payload["comparable_case_set"]["approved_count"] >= 1
    assert first_payload["comparable_case_set"]["refused_count"] >= 1
    assert first_payload["prediction_ledger"]["result_payload_hash"]

    second = client.post("/api/assessments", json=request_payload)
    assert second.status_code == 200
    second_payload = second.json()
    assert second_payload["id"] == first_payload["id"]
    assert (
        second_payload["feature_snapshot"]["feature_hash"]
        == first_payload["feature_snapshot"]["feature_hash"]
    )
    assert (
        second_payload["prediction_ledger"]["result_payload_hash"]
        == first_payload["prediction_ledger"]["result_payload_hash"]
    )

    detail = client.get(f"/api/assessments/{first_payload['id']}")
    assert detail.status_code == 200
    detail_payload = detail.json()
    assert detail_payload["evidence"]["for"]
    assert detail_payload["evidence"]["against"]
    assert detail_payload["evidence"]["unknown"]
    assert (
        detail_payload["prediction_ledger"]["feature_hash"]
        == detail_payload["feature_snapshot"]["feature_hash"]
    )


def test_replay_verification_and_gold_set_review_flow(
    client,
    drain_jobs,
    seed_listing_sources,
    seed_planning_data,
    db_session,
):
    del seed_listing_sources
    del seed_planning_data
    site_payload, scenario_payload = _build_confirmed_camden_scenario(client, drain_jobs)
    create = client.post(
        "/api/assessments",
        json={
            "site_id": site_payload["id"],
            "scenario_id": scenario_payload["id"],
            "as_of_date": "2026-04-15",
            "requested_by": "pytest",
        },
    )
    assert create.status_code == 200

    replay = replay_verify_all_assessments(db_session)
    assert replay["failed"] == 0
    assert replay["checks"]
    assert all(check["feature_hash_matches"] for check in replay["checks"])
    assert all(check["payload_hash_matches"] for check in replay["checks"])

    cases = client.get("/api/admin/gold-set/cases")
    assert cases.status_code == 200
    payload = cases.json()
    assert payload["items"]
    case_id = payload["items"][0]["id"]

    reviewed = client.post(
        f"/api/admin/gold-set/cases/{case_id}/review",
        json={
            "review_status": GoldSetReviewStatus.CONFIRMED.value,
            "review_notes": "Confirmed against fixture provenance.",
            "notable_policy_issues": ["heritage"],
            "extant_permission_outcome": "NO_ACTIVE_PERMISSION_FOUND",
            "site_geometry_confidence": GeomConfidence.MEDIUM.value,
            "reviewed_by": "pytest",
        },
    )
    assert reviewed.status_code == 200
    reviewed_payload = reviewed.json()
    assert reviewed_payload["review_status"] == GoldSetReviewStatus.CONFIRMED.value
    assert reviewed_payload["review_notes"] == "Confirmed against fixture provenance."
    assert reviewed_payload["planning_application"]["external_ref"]
