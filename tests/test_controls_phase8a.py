from __future__ import annotations

import uuid

from landintel.domain.models import AssessmentRun
from landintel.scoring.release import scope_key_for

from tests.test_assessments_phase5a import _build_confirmed_camden_scenario
from tests.test_scoring_phase6a import _build_hidden_releases


def _build_scored_assessment(*, client, drain_jobs, db_session, storage, auth_headers):
    _build_hidden_releases(db_session=db_session, storage=storage)
    site_payload, scenario_payload = _build_confirmed_camden_scenario(client, drain_jobs)
    assessment = client.post(
        "/api/assessments",
        json={
            "site_id": site_payload["id"],
            "scenario_id": scenario_payload["id"],
            "as_of_date": "2026-04-15",
            "requested_by": "pytest",
            "hidden_mode": True,
        },
        headers=auth_headers("reviewer"),
    )
    assert assessment.status_code == 200
    payload = assessment.json()
    return site_payload, scenario_payload, payload


def test_assessment_override_round_trip_preserves_original_result(
    client,
    drain_jobs,
    seed_listing_sources,
    seed_planning_data,
    seed_valuation_data,
    db_session,
    storage,
    auth_headers,
):
    del seed_listing_sources
    del seed_planning_data
    del seed_valuation_data

    _site, _scenario, assessment = _build_scored_assessment(
        client=client,
        drain_jobs=drain_jobs,
        db_session=db_session,
        storage=storage,
        auth_headers=auth_headers,
    )
    original_uplift_mid = assessment["valuation"]["uplift_mid"]
    original_payload_hash = assessment["prediction_ledger"]["result_payload_hash"]
    original_probability_raw = assessment["result"]["approval_probability_raw"]

    override = client.post(
        f"/api/assessments/{assessment['id']}/override",
        json={
            "requested_by": "pytest",
            "actor_role": "analyst",
            "override_type": "ACQUISITION_BASIS",
            "reason": "Correct acquisition basis from analyst evidence.",
            "acquisition_basis_gbp": 900000,
            "acquisition_basis_type": "GUIDE_PRICE",
        },
        headers=auth_headers("analyst"),
    )
    assert override.status_code == 200
    payload = override.json()

    assert payload["result"]["approval_probability_raw"] is None
    assert payload["valuation"]["uplift_mid"] == original_uplift_mid
    assert payload["prediction_ledger"]["result_payload_hash"] == original_payload_hash
    assert payload["override_summary"] is not None
    assert (
        payload["override_summary"]["active_overrides"][0]["override_type"]
        == "ACQUISITION_BASIS"
    )
    assert payload["override_summary"]["effective_valuation"]["uplift_mid"] != original_uplift_mid
    assert (
        payload["override_summary"]["effective_valuation"]["basis_json"]["override_applied"]
        is True
    )

    hidden = client.get(
        f"/api/assessments/{assessment['id']}?hidden_mode=true",
        headers=auth_headers("reviewer"),
    )
    assert hidden.status_code == 200
    hidden_payload = hidden.json()
    assert hidden_payload["result"]["approval_probability_raw"] == original_probability_raw
    assert hidden_payload["prediction_ledger"]["result_payload_hash"] == original_payload_hash
    assert hidden_payload["valuation"]["uplift_mid"] == original_uplift_mid
    assert (
        hidden_payload["override_summary"]["effective_valuation"]["uplift_mid"]
        != original_uplift_mid
    )


def test_override_history_is_append_only_while_effective_state_uses_latest_entry(
    client,
    drain_jobs,
    seed_listing_sources,
    seed_planning_data,
    seed_valuation_data,
    db_session,
    storage,
    auth_headers,
):
    del seed_listing_sources
    del seed_planning_data
    del seed_valuation_data

    _site, _scenario, assessment = _build_scored_assessment(
        client=client,
        drain_jobs=drain_jobs,
        db_session=db_session,
        storage=storage,
        auth_headers=auth_headers,
    )

    first = client.post(
        f"/api/assessments/{assessment['id']}/override",
        json={
            "requested_by": "pytest",
            "override_type": "ACQUISITION_BASIS",
            "reason": "First basis correction.",
            "acquisition_basis_gbp": 900000,
            "acquisition_basis_type": "GUIDE_PRICE",
        },
        headers=auth_headers("analyst"),
    )
    assert first.status_code == 200

    second = client.post(
        f"/api/assessments/{assessment['id']}/override",
        json={
            "requested_by": "pytest",
            "override_type": "ACQUISITION_BASIS",
            "reason": "Second basis correction.",
            "acquisition_basis_gbp": 850000,
            "acquisition_basis_type": "GUIDE_PRICE",
        },
        headers=auth_headers("analyst"),
    )
    assert second.status_code == 200

    db_session.expire_all()
    run = db_session.get(AssessmentRun, uuid.UUID(assessment["id"]))
    assert run is not None
    basis_overrides = [
        row
        for row in run.overrides
        if row.override_type.value == "ACQUISITION_BASIS"
    ]
    assert len(basis_overrides) == 2
    latest, prior = basis_overrides[0], basis_overrides[1]
    assert latest.supersedes_id == prior.id
    assert latest.reason == "Second basis correction."
    assert prior.reason == "First basis correction."
    assert prior.status.value == "ACTIVE"

    payload = second.json()
    assert len(payload["override_summary"]["active_overrides"]) == 1
    assert (
        payload["override_summary"]["active_overrides"][0]["reason"]
        == "Second basis correction."
    )

    export = client.get(
        f"/api/assessments/{assessment['id']}/audit-export?requested_by=pytest",
        headers=auth_headers("reviewer"),
    )
    assert export.status_code == 200
    basis_rows = [
        row
        for row in export.json()["manifest_json"]["override_history"]
        if row["override_type"] == "ACQUISITION_BASIS"
    ]
    assert len(basis_rows) == 2
    assert {row["reason"] for row in basis_rows} == {
        "First basis correction.",
        "Second basis correction.",
    }


def test_override_role_gating_and_visibility_kill_switch_with_rollback(
    client,
    drain_jobs,
    seed_listing_sources,
    seed_planning_data,
    seed_valuation_data,
    db_session,
    storage,
    auth_headers,
):
    del seed_listing_sources
    del seed_planning_data
    del seed_valuation_data

    site_payload, scenario_payload, assessment = _build_scored_assessment(
        client=client,
        drain_jobs=drain_jobs,
        db_session=db_session,
        storage=storage,
        auth_headers=auth_headers,
    )
    scope_key = assessment["result"]["release_scope_key"]
    assert scope_key == scope_key_for(template_key=scenario_payload["template_key"])

    forbidden_override = client.post(
        f"/api/assessments/{assessment['id']}/override",
        json={
            "requested_by": "pytest",
            "actor_role": "analyst",
            "override_type": "REVIEW_DISPOSITION",
            "reason": "Analyst should not be able to resolve manual review.",
            "review_resolution_note": "Invalid attempt.",
            "resolve_manual_review": True,
        },
        headers=auth_headers("analyst"),
    )
    assert forbidden_override.status_code == 422

    forbidden_visibility = client.post(
        f"/api/admin/release-scopes/{scope_key}/visibility",
        json={
            "requested_by": "pytest",
            "actor_role": "reviewer",
            "visibility_mode": "VISIBLE_REVIEWER_ONLY",
            "reason": "Reviewer should not be able to change scope visibility.",
        },
        headers=auth_headers("reviewer"),
    )
    assert forbidden_visibility.status_code == 403

    enabled = client.post(
        f"/api/admin/release-scopes/{scope_key}/visibility",
        json={
            "requested_by": "pytest",
            "actor_role": "admin",
            "visibility_mode": "VISIBLE_REVIEWER_ONLY",
            "reason": "Pytest reviewer-visible scope enablement.",
        },
        headers=auth_headers("admin"),
    )
    assert enabled.status_code == 422
    assert "borough-scoped active release" in enabled.json()["detail"]

    analyst_read = client.get(f"/api/assessments/{assessment['id']}")
    assert analyst_read.status_code == 200
    analyst_payload = analyst_read.json()
    assert analyst_payload["result"]["approval_probability_display"] is None
    assert analyst_payload["visibility"]["visible_probability_allowed"] is False
    assert analyst_payload["visibility"]["blocked"] is False

    reviewer_read = client.get(
        f"/api/assessments/{assessment['id']}",
        headers=auth_headers("reviewer"),
    )
    assert reviewer_read.status_code == 200
    reviewer_payload = reviewer_read.json()
    assert reviewer_payload["result"]["approval_probability_display"] is None
    assert reviewer_payload["result"]["approval_probability_raw"] is None
    assert reviewer_payload["visibility"]["visible_probability_allowed"] is False
    assert reviewer_payload["visibility"]["visibility_mode"] == "HIDDEN_ONLY"

    incident_open = client.post(
        f"/api/admin/release-scopes/{scope_key}/incident",
        json={
            "requested_by": "pytest",
            "actor_role": "admin",
            "action": "OPEN",
            "reason": "Pytest kill switch open.",
        },
        headers=auth_headers("admin"),
    )
    assert incident_open.status_code == 200
    incident_payload = incident_open.json()
    assert incident_payload["status"] == "OPEN"
    assert incident_payload["applied_visibility_mode"] == "DISABLED"

    blocked_read = client.get(
        f"/api/assessments/{assessment['id']}",
        headers=auth_headers("reviewer"),
    )
    assert blocked_read.status_code == 200
    blocked_payload = blocked_read.json()
    assert blocked_payload["result"]["approval_probability_display"] is None
    assert blocked_payload["visibility"]["blocked"] is True
    assert "ACTIVE_INCIDENT" in blocked_payload["visibility"]["blocked_reason_codes"]
    assert blocked_payload["visibility"]["active_incident_reason"] == "Pytest kill switch open."
    assert blocked_payload["visibility"]["replay_verified"] is True

    analyst_blocked_read = client.get(f"/api/assessments/{assessment['id']}")
    assert analyst_blocked_read.status_code == 200
    analyst_blocked_payload = analyst_blocked_read.json()
    assert analyst_blocked_payload["visibility"]["blocked"] is True
    assert analyst_blocked_payload["visibility"]["active_incident_reason"] is None
    assert analyst_blocked_payload["visibility"]["active_incident_id"] is None
    assert analyst_blocked_payload["visibility"]["replay_verified"] is None
    assert analyst_blocked_payload["visibility"]["payload_hash_matches"] is None
    assert analyst_blocked_payload["visibility"]["artifact_hashes_match"] is None
    assert analyst_blocked_payload["visibility"]["scope_release_matches_result"] is None
    assert analyst_blocked_payload["visibility"]["blocked_reason_text"] == (
        "Visible publication is currently blocked for this scope."
    )

    blocked_opportunity = client.get(
        f"/api/opportunities/{site_payload['id']}",
        headers=auth_headers("reviewer"),
    )
    assert blocked_opportunity.status_code == 200
    opportunity_payload = blocked_opportunity.json()
    assert opportunity_payload["probability_band"] == "Hold"
    assert opportunity_payload["hold_reason"] is not None

    analyst_blocked_opportunity = client.get(f"/api/opportunities/{site_payload['id']}")
    assert analyst_blocked_opportunity.status_code == 200
    analyst_opportunity_payload = analyst_blocked_opportunity.json()
    assert analyst_opportunity_payload["visibility"]["active_incident_reason"] is None
    assert analyst_opportunity_payload["visibility"]["replay_verified"] is None

    incident_rollback = client.post(
        f"/api/admin/release-scopes/{scope_key}/incident",
        json={
            "requested_by": "pytest",
            "actor_role": "admin",
            "action": "ROLLBACK",
            "reason": "Pytest kill switch rollback.",
        },
        headers=auth_headers("admin"),
    )
    assert incident_rollback.status_code == 200
    rollback_payload = incident_rollback.json()
    assert rollback_payload["status"] == "RESOLVED"

    reviewer_after = client.get(
        f"/api/assessments/{assessment['id']}",
        headers=auth_headers("reviewer"),
    )
    assert reviewer_after.status_code == 200
    reviewer_after_payload = reviewer_after.json()
    assert reviewer_after_payload["result"]["approval_probability_display"] is None
    assert reviewer_after_payload["visibility"]["blocked"] is False
    assert reviewer_after_payload["visibility"]["visibility_mode"] == "HIDDEN_ONLY"


def test_health_review_queue_and_audit_export_payloads(
    client,
    drain_jobs,
    seed_listing_sources,
    seed_planning_data,
    seed_valuation_data,
    db_session,
    storage,
    auth_headers,
):
    del seed_listing_sources
    del seed_planning_data
    del seed_valuation_data

    _site_payload, scenario_payload, assessment = _build_scored_assessment(
        client=client,
        drain_jobs=drain_jobs,
        db_session=db_session,
        storage=storage,
        auth_headers=auth_headers,
    )
    scope_key = assessment["result"]["release_scope_key"]
    assert scope_key is not None

    ranking_override = client.post(
        f"/api/assessments/{assessment['id']}/override",
        json={
            "requested_by": "pytest",
            "actor_role": "admin",
            "override_type": "RANKING_SUPPRESSION",
            "reason": "Temporarily suppress ranking display for pytest.",
            "ranking_suppressed": True,
            "display_block_reason": "Blocked for pytest ranking suppression.",
        },
        headers=auth_headers("admin"),
    )
    assert ranking_override.status_code == 200

    incident_open = client.post(
        f"/api/admin/release-scopes/{scope_key}/incident",
        json={
            "requested_by": "pytest",
            "actor_role": "admin",
            "action": "OPEN",
            "reason": "Pytest data-quality incident.",
        },
        headers=auth_headers("admin"),
    )
    assert incident_open.status_code == 200

    data_health = client.get("/api/health/data", headers=auth_headers("admin"))
    assert data_health.status_code == 200
    data_payload = data_health.json()
    assert "connector_failure_rate" in data_payload
    assert "listing_parse_success_rate" in data_payload
    assert "geometry_confidence_distribution" in data_payload
    assert "valuation_metrics" in data_payload

    model_health = client.get("/api/health/model", headers=auth_headers("admin"))
    assert model_health.status_code == 200
    model_payload = model_health.json()
    assert "calibration_by_probability_band" in model_payload
    assert "brier_score" in model_payload
    assert "economic_health" in model_payload
    assert any(scope["scope_key"] == scope_key for scope in model_payload["active_scopes"])

    review_queue = client.get("/api/admin/review-queue", headers=auth_headers("reviewer"))
    assert review_queue.status_code == 200
    queue_payload = review_queue.json()
    assert any(
        item["assessment_id"] == assessment["id"]
        for item in queue_payload["manual_review_cases"]
    )
    assert any(item["assessment_id"] == assessment["id"] for item in queue_payload["blocked_cases"])
    assert "failing_boroughs" in queue_payload

    audit_export = client.get(
        f"/api/assessments/{assessment['id']}/audit-export?requested_by=pytest",
        headers=auth_headers("reviewer"),
    )
    assert audit_export.status_code == 200
    export_payload = audit_export.json()
    assert export_payload["manifest_hash"] is not None
    assert export_payload["manifest_path"] is not None
    manifest = export_payload["manifest_json"]
    assert manifest["assessment"]["id"] == assessment["id"]
    assert manifest["scenario_summary"]["id"] == scenario_payload["id"]
    assert manifest["visibility"]["scope_key"] == scope_key
    assert any(
        row["override_type"] == "RANKING_SUPPRESSION"
        for row in manifest["override_history"]
    )
    assert manifest["audit_event_refs"]
    assert any(row["entity_type"] == "valuation_run" for row in manifest["audit_event_refs"])
