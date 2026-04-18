from __future__ import annotations

import math
import uuid
from datetime import UTC, datetime

from landintel.assessments.service import (
    create_or_refresh_assessment_run,
    replay_verify_all_assessments,
)
from landintel.domain import models
from landintel.domain.enums import (
    CalibrationMethod,
    GeomConfidence,
    GeomSourceType,
    ModelReleaseStatus,
    ReleaseChannel,
)
from landintel.domain.models import ModelRelease
from landintel.domain.schemas import EvidencePackRead
from landintel.planning.historical_labels import rebuild_historical_case_labels
from landintel.scoring.calibration import apply_calibration
from landintel.scoring.explain import generate_hidden_score_explanation
from landintel.scoring.quality import (
    derive_ood_status,
    final_estimate_quality,
    round_display_probability,
)
from landintel.scoring.release import (
    activate_model_release,
    build_hidden_model_releases,
    resolve_active_release,
    scope_key_for,
)
from landintel.scoring.train import build_training_manifest, load_training_rows

from tests.test_assessments_phase5a import _build_confirmed_camden_scenario


def _build_hidden_releases(*, db_session, storage):
    releases = build_hidden_model_releases(
        session=db_session,
        storage=storage,
        requested_by="pytest",
        auto_activate_hidden=True,
    )
    db_session.commit()
    return {release.template_key: release for release in releases}


def test_hidden_release_build_is_honest_about_supported_templates(
    seed_planning_data,
    db_session,
    storage,
):
    del seed_planning_data
    releases = _build_hidden_releases(db_session=db_session, storage=storage)

    supported = releases["resi_5_9_full"]
    assert supported.status == ModelReleaseStatus.ACTIVE
    assert supported.support_count >= 7
    assert supported.positive_count >= 3
    assert supported.negative_count >= 3
    assert supported.model_artifact_path
    assert supported.calibration_artifact_path
    assert supported.validation_artifact_path
    assert supported.model_card_path

    for template_key in ("resi_1_4_full", "resi_10_49_outline"):
        release = releases[template_key]
        assert release.status == ModelReleaseStatus.NOT_READY
        assert release.support_count == 0
        assert release.reason_text is not None
        assert "Support count 0 is below the hidden-release minimum" in release.reason_text
        assert release.model_artifact_path is None
        assert release.calibration_artifact_path is None


def test_training_manifest_is_stable_and_leakage_safe(seed_planning_data, db_session):
    del seed_planning_data
    rebuild_historical_case_labels(session=db_session, requested_by="pytest")
    rows = load_training_rows(session=db_session, template_key="resi_5_9_full")

    first = build_training_manifest(template_key="resi_5_9_full", rows=rows)
    second = build_training_manifest(template_key="resi_5_9_full", rows=rows)

    assert first["status"] == "VALIDATED"
    assert first["payload_hash"] == second["payload_hash"]
    assert first["model_artifact"]["transform_spec"] == second["model_artifact"]["transform_spec"]
    assert first["validation"]["leakage_checks"]["forbidden_features_clean"] is True
    assert first["validation"]["leakage_checks"]["forbidden_features_present"] == []
    assert first["validation"]["leakage_checks"]["feature_as_of_matches_validation_date"] is True
    assert first["validation"]["leakage_checks"]["no_current_decision_in_pit_window"] is True


def test_probability_rounding_calibration_ood_and_quality_helpers():
    assert round_display_probability(0.00) == "0%"
    assert round_display_probability(0.03) == "5%"
    assert round_display_probability(0.72) == "70%"
    assert round_display_probability(0.78) == "80%"
    assert round_display_probability(0.99) == "100%"

    calibrated_same = apply_calibration(
        0.73,
        calibration_artifact={"method": "PLATT", "intercept": 0.0, "slope": 1.0},
    )
    assert math.isclose(calibrated_same, 0.73, rel_tol=0.0, abs_tol=1e-12)

    adjusted = apply_calibration(
        0.25,
        calibration_artifact={"method": "PLATT", "intercept": 0.2, "slope": 1.1},
    )
    assert 0.0 < adjusted < 1.0
    assert not math.isclose(adjusted, 0.25)

    in_support = derive_ood_status(
        nearest_distance=0.4,
        same_template_support_count=9,
        same_borough_support_count=3,
        distance_thresholds={"medium": 1.2, "high": 2.0},
    )
    assert in_support == ("IN_SUPPORT", "HIGH")

    edge_support = derive_ood_status(
        nearest_distance=1.5,
        same_template_support_count=9,
        same_borough_support_count=1,
        distance_thresholds={"medium": 1.2, "high": 2.0},
    )
    assert edge_support == ("EDGE_OF_SUPPORT", "MEDIUM")

    out_of_distribution = derive_ood_status(
        nearest_distance=2.5,
        same_template_support_count=9,
        same_borough_support_count=1,
        distance_thresholds={"medium": 1.2, "high": 2.0},
    )
    assert out_of_distribution == ("OUT_OF_DISTRIBUTION", "LOW")

    assert final_estimate_quality(quality_components=["HIGH", "HIGH"]) == "HIGH"
    assert final_estimate_quality(quality_components=["HIGH", "MEDIUM"]) == "MEDIUM"
    assert final_estimate_quality(quality_components=["HIGH", "LOW"]) == "LOW"


def test_explanation_generator_orders_drivers_and_surfaces_unknowns():
    model_artifact = {
        "transform_spec": {
            "numeric": {
                "site_area_sqm": {
                    "median": 100.0,
                    "mean": 100.0,
                    "std": 10.0,
                    "has_missing": False,
                }
            },
            "categorical": {"borough_id": {"categories": ["camden"], "has_missing": False}},
            "boolean": {"has_flood_zone": {"has_missing": False}},
            "encoded_feature_names": [
                "site_area_sqm",
                "borough_id=camden",
                "has_flood_zone",
            ],
            "encoded_feature_bases": [
                "site_area_sqm",
                "borough_id",
                "has_flood_zone",
            ],
        },
        "coefficients": [1.5, -0.8, -1.2],
        "intercept": 0.0,
    }
    explanation = generate_hidden_score_explanation(
        model_artifact=model_artifact,
        feature_json={
            "values": {
                "site_area_sqm": 120.0,
                "borough_id": "camden",
                "has_flood_zone": True,
            },
            "missing_flags": {
                "ptal_bucket": True,
                "distance_to_station_m": False,
            },
        },
        evidence=EvidencePackRead(
            for_=[],
            against=[],
            unknown=[],
        ),
        comparable_payload={
            "approved": [{"planning_application_id": "approved-case"}],
            "refused": [{"planning_application_id": "refused-case"}],
        },
        coverage_json={
            "source_coverage": [
                {
                    "source_family": "borough_register",
                    "coverage_status": "COMPLETE",
                    "freshness_status": "FRESH",
                    "gap_reason": None,
                }
            ]
        },
        model_release_id="release-1",
    )

    assert explanation["target_definition"].startswith("Positive first substantive decision")
    assert explanation["top_positive_drivers"][0]["feature"] == "site_area_sqm"
    assert explanation["top_negative_drivers"][0]["feature"] == "has_flood_zone"
    assert explanation["top_negative_drivers"][1]["feature"] == "borough_id"
    assert explanation["unknowns"][0]["feature"] == "ptal_bucket"
    assert explanation["comparable_approved_cases"][0]["planning_application_id"] == "approved-case"
    assert explanation["comparable_refused_cases"][0]["planning_application_id"] == "refused-case"
    assert explanation["model_release_id"] == "release-1"


def test_hidden_score_assessment_is_redacted_by_default_and_replay_stable(
    client,
    drain_jobs,
    seed_listing_sources,
    seed_planning_data,
    db_session,
    storage,
    auth_headers,
):
    del seed_listing_sources
    del seed_planning_data
    releases = _build_hidden_releases(db_session=db_session, storage=storage)
    assert releases["resi_5_9_full"].status == ModelReleaseStatus.ACTIVE

    site_payload, scenario_payload = _build_confirmed_camden_scenario(client, drain_jobs)
    payload = {
        "site_id": site_payload["id"],
        "scenario_id": scenario_payload["id"],
        "as_of_date": "2026-04-15",
        "requested_by": "pytest",
    }

    create = client.post("/api/assessments", json=payload)
    assert create.status_code == 200
    created = create.json()
    assert created["result"]["approval_probability_raw"] is None
    assert created["result"]["approval_probability_display"] is None
    assert created["result"]["result_json"]["hidden_score_redacted"] is True
    assert created["prediction_ledger"]["model_release_id"] is None
    assert created["prediction_ledger"]["response_json"]["hidden_score_redacted"] is True
    assert created["prediction_ledger"]["replay_verification_status"] == "HASH_CAPTURED"

    detail_hidden = client.get(
        f"/api/assessments/{created['id']}?hidden_mode=true",
        headers=auth_headers("reviewer"),
    )
    assert detail_hidden.status_code == 200
    hidden_before_replay = detail_hidden.json()
    assert hidden_before_replay["result"]["approval_probability_raw"] is None
    assert hidden_before_replay["result"]["approval_probability_display"] is None

    replay = replay_verify_all_assessments(db_session, storage=storage)
    assert replay["failed"] == 0
    db_session.commit()

    detail_hidden = client.get(
        f"/api/assessments/{created['id']}?hidden_mode=true",
        headers=auth_headers("reviewer"),
    )
    assert detail_hidden.status_code == 200
    hidden = detail_hidden.json()
    assert hidden["result"]["estimate_status"] == "ESTIMATE_AVAILABLE_MANUAL_REVIEW_REQUIRED"
    assert hidden["result"]["approval_probability_raw"] is not None
    assert hidden["result"]["approval_probability_display"] is not None
    assert hidden["result"]["estimate_quality"] is not None
    assert hidden["result"]["ood_status"] is not None
    assert hidden["result"]["model_release_id"] is not None
    assert hidden["prediction_ledger"]["response_mode"] == "HIDDEN_SCORE"
    assert hidden["prediction_ledger"]["model_release_id"] == hidden["result"]["model_release_id"]
    assert "explanation" in hidden["result"]["result_json"]

    second = client.post(
        "/api/assessments",
        json={**payload, "hidden_mode": True},
        headers=auth_headers("reviewer"),
    )
    assert second.status_code == 200
    repeated = second.json()
    assert repeated["id"] == hidden["id"]
    assert (
        repeated["feature_snapshot"]["feature_hash"]
        == hidden["feature_snapshot"]["feature_hash"]
    )
    assert (
        repeated["prediction_ledger"]["result_payload_hash"]
        == hidden["prediction_ledger"]["result_payload_hash"]
    )

    assert replay["checks"]
    assert all(check["feature_hash_matches"] for check in replay["checks"])
    assert all(check["payload_hash_matches"] for check in replay["checks"])
    assert all(check["scored_fields_match"] for check in replay["checks"])


def test_replay_verification_fails_when_scored_fields_diverge(
    client,
    drain_jobs,
    seed_listing_sources,
    seed_planning_data,
    db_session,
    storage,
    auth_headers,
    monkeypatch,
):
    del seed_listing_sources
    del seed_planning_data
    _build_hidden_releases(db_session=db_session, storage=storage)

    site_payload, scenario_payload = _build_confirmed_camden_scenario(client, drain_jobs)
    created = client.post(
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
    assert created.status_code == 200
    created_payload = created.json()

    from landintel.assessments import service as assessment_service

    original_score = assessment_service.score_frozen_assessment

    def divergent_score(**kwargs):
        replay_score = original_score(**kwargs)
        replay_score["approval_probability_raw"] = min(
            float(replay_score["approval_probability_raw"]) + 0.1,
            0.999999,
        )
        replay_score["approval_probability_display"] = "95%"
        replay_score["estimate_quality"] = "LOW"
        replay_score["ood_status"] = "OUT_OF_DISTRIBUTION"
        replay_score["explanation"] = {"diverged": True}
        return replay_score

    monkeypatch.setattr(assessment_service, "score_frozen_assessment", divergent_score)

    replay = replay_verify_all_assessments(db_session, storage=storage)
    assert replay["failed"] == 1
    assert replay["checks"][0]["scored_fields_match"] is False
    assert replay["checks"][0]["replay_passed"] is False

    db_session.commit()
    db_session.expire_all()
    run = db_session.get(models.AssessmentRun, uuid.UUID(created_payload["id"]))
    assert run is not None
    assert run.prediction_ledger is not None
    assert run.prediction_ledger.replay_verification_status == "FAILED"
    assert "scored_fields_match" in str(run.prediction_ledger.replay_verification_note)


def test_replay_verification_uses_frozen_site_and_scenario_state(
    client,
    drain_jobs,
    seed_listing_sources,
    seed_planning_data,
    db_session,
    storage,
    auth_headers,
):
    del seed_listing_sources
    del seed_planning_data
    _build_hidden_releases(db_session=db_session, storage=storage)

    site_payload, scenario_payload = _build_confirmed_camden_scenario(client, drain_jobs)
    created = client.post(
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
    assert created.status_code == 200

    run = db_session.get(models.AssessmentRun, uuid.UUID(created.json()["id"]))
    assert run is not None
    run.site.borough_id = "hackney"
    run.site.geom_confidence = GeomConfidence.LOW
    run.site.manual_review_required = True
    run.scenario.manual_review_required = True
    run.scenario.stale_reason = "Geometry changed after confirmation."
    db_session.commit()

    replay = replay_verify_all_assessments(db_session, storage=storage)
    assert replay["failed"] == 0
    assert replay["checks"][0]["scored_fields_match"] is True
    assert replay["checks"][0]["replay_passed"] is True


def test_geometry_reconfirmation_supersedes_assessed_scenario_without_breaking_replay(
    client,
    drain_jobs,
    seed_listing_sources,
    seed_planning_data,
    db_session,
    storage,
    auth_headers,
):
    del seed_listing_sources
    del seed_planning_data
    _build_hidden_releases(db_session=db_session, storage=storage)

    site_payload, scenario_payload = _build_confirmed_camden_scenario(client, drain_jobs)
    created = client.post(
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
    assert created.status_code == 200
    created_payload = created.json()
    assessment_run_id = uuid.UUID(created_payload["id"])
    original_scenario_id = scenario_payload["id"]

    geometry_update = client.post(
        f"/api/sites/{site_payload['id']}/geometry",
        json={
            "geom_4326": {
                "type": "Polygon",
                "coordinates": [[
                    [-0.14270, 51.53594],
                    [-0.14130, 51.53594],
                    [-0.14130, 51.53644],
                    [-0.14270, 51.53644],
                    [-0.14270, 51.53594]
                ]]
            },
            "source_type": GeomSourceType.ANALYST_DRAWN,
            "confidence": GeomConfidence.HIGH,
            "reason": "Geometry change before reconfirmation replay test.",
            "created_by": "pytest"
        },
    )
    assert geometry_update.status_code == 200

    reconfirmed = client.post(
        f"/api/scenarios/{original_scenario_id}/confirm",
        json={"requested_by": "pytest", "review_notes": "Reconfirm after geometry change."},
    )
    assert reconfirmed.status_code == 200
    reconfirmed_payload = reconfirmed.json()
    assert reconfirmed_payload["id"] != original_scenario_id
    assert reconfirmed_payload["supersedes_id"] == original_scenario_id

    new_assessment = client.post(
        "/api/assessments",
        json={
            "site_id": site_payload["id"],
            "scenario_id": reconfirmed_payload["id"],
            "as_of_date": "2026-04-15",
            "requested_by": "pytest",
            "hidden_mode": True,
        },
        headers=auth_headers("reviewer"),
    )
    assert new_assessment.status_code == 200

    replay = replay_verify_all_assessments(db_session, storage=storage)
    assert replay["failed"] == 0

    db_session.expire_all()
    old_run = db_session.get(models.AssessmentRun, assessment_run_id)
    new_run = db_session.get(models.AssessmentRun, uuid.UUID(new_assessment.json()["id"]))
    assert old_run is not None
    assert new_run is not None
    assert old_run.scenario_id == uuid.UUID(original_scenario_id)
    assert old_run.prediction_ledger is not None
    assert new_run.prediction_ledger is not None
    assert old_run.prediction_ledger.site_geom_hash != new_run.prediction_ledger.site_geom_hash
    assert old_run.prediction_ledger.replay_verification_status == "VERIFIED"
    assert new_run.prediction_ledger.replay_verification_status == "VERIFIED"


def test_model_release_activation_and_rollback(seed_planning_data, db_session, storage):
    del seed_planning_data
    releases = _build_hidden_releases(db_session=db_session, storage=storage)
    first = releases["resi_5_9_full"]
    assert first.status == ModelReleaseStatus.ACTIVE

    successor = ModelRelease(
        id=uuid.uuid4(),
        template_key=first.template_key,
        release_channel=ReleaseChannel.HIDDEN,
        scope_key=first.scope_key,
        scope_borough_id=first.scope_borough_id,
        status=ModelReleaseStatus.VALIDATED,
        model_kind=first.model_kind,
        transform_version=f"{first.transform_version}_alt",
        feature_version=first.feature_version,
        calibration_method=CalibrationMethod.PLATT,
        model_artifact_path=first.model_artifact_path,
        model_artifact_hash=first.model_artifact_hash,
        calibration_artifact_path=first.calibration_artifact_path,
        calibration_artifact_hash=first.calibration_artifact_hash,
        validation_artifact_path=first.validation_artifact_path,
        validation_artifact_hash=first.validation_artifact_hash,
        model_card_path=first.model_card_path,
        model_card_hash=first.model_card_hash,
        train_window_start=first.train_window_start,
        train_window_end=first.train_window_end,
        support_count=first.support_count,
        positive_count=first.positive_count,
        negative_count=first.negative_count,
        metrics_json=dict(first.metrics_json or {}),
        manifest_json=dict(first.manifest_json or {}),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add(successor)
    db_session.commit()

    activate_model_release(
        session=db_session,
        release_id=successor.id,
        requested_by="pytest-rollback",
    )
    db_session.commit()
    db_session.refresh(first)
    db_session.refresh(successor)
    active_after_successor, active_scope_key = resolve_active_release(
        session=db_session,
        template_key="resi_5_9_full",
    )
    assert active_scope_key == scope_key_for(template_key="resi_5_9_full")
    assert active_after_successor is not None
    assert active_after_successor.id == successor.id
    assert first.status == ModelReleaseStatus.RETIRED

    activate_model_release(
        session=db_session,
        release_id=first.id,
        requested_by="pytest-rollback",
    )
    db_session.commit()
    db_session.refresh(first)
    db_session.refresh(successor)
    rolled_back, _ = resolve_active_release(
        session=db_session,
        template_key="resi_5_9_full",
    )
    assert rolled_back is not None
    assert rolled_back.id == first.id
    assert first.status == ModelReleaseStatus.ACTIVE
    assert successor.status == ModelReleaseStatus.RETIRED


def test_scored_assessment_can_be_built_directly_from_service(
    client,
    drain_jobs,
    seed_listing_sources,
    seed_planning_data,
    db_session,
    storage,
):
    del seed_listing_sources
    del seed_planning_data
    _build_hidden_releases(db_session=db_session, storage=storage)
    site_payload, scenario_payload = _build_confirmed_camden_scenario(client, drain_jobs)

    run = create_or_refresh_assessment_run(
        session=db_session,
        site_id=uuid.UUID(site_payload["id"]),
        scenario_id=uuid.UUID(scenario_payload["id"]),
        as_of_date=datetime(2026, 4, 15, tzinfo=UTC).date(),
        requested_by="pytest",
        storage=storage,
    )
    db_session.commit()
    db_session.refresh(run)

    assert run.result is not None
    assert run.result.model_release_id is not None
    assert run.result.approval_probability_raw is not None
    assert run.result.approval_probability_display is not None
    assert run.result.result_json["score_execution_status"] == "HIDDEN_ESTIMATE_AVAILABLE"
    assert run.prediction_ledger is not None
    assert run.prediction_ledger.response_mode == "HIDDEN_SCORE"
