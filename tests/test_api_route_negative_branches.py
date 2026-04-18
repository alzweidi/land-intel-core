from __future__ import annotations

from importlib import import_module
from types import SimpleNamespace
from uuid import uuid4

from landintel.assessments.service import AssessmentBuildError
from landintel.domain.enums import GoldSetReviewStatus
from landintel.review.visibility import ReviewAccessError
from landintel.scenarios.normalize import ScenarioNormalizeError
from landintel.sites.service import SiteBuildError

admin_routes = import_module("services.api.app.routes.admin")
assessments_routes = import_module("services.api.app.routes.assessments")
scenarios_routes = import_module("services.api.app.routes.scenarios")
sites_routes = import_module("services.api.app.routes.sites")


def _raise_site_build_error(*args, **kwargs):
    raise SiteBuildError("boom")


def _raise_assessment_build_error(*args, **kwargs):
    raise AssessmentBuildError("boom")


def _raise_review_access_error(*args, **kwargs):
    raise ReviewAccessError("boom")


def _raise_scenario_normalize_error(*args, **kwargs):
    raise ScenarioNormalizeError("boom")


def test_listing_and_cluster_routes_return_expected_negative_statuses(client):
    empty_upload = client.post(
        "/api/listings/import/csv",
        files={"file": ("empty.csv", b"", "text/csv")},
    )
    assert empty_upload.status_code == 400
    assert empty_upload.json()["detail"]["message"] == "CSV upload is empty."

    missing_listing_id = uuid4()
    missing_listing = client.get(f"/api/listings/{missing_listing_id}")
    assert missing_listing.status_code == 404
    assert missing_listing.json()["detail"] == {
        "message": "Listing not found.",
        "listing_id": str(missing_listing_id),
    }

    missing_cluster_id = uuid4()
    missing_cluster = client.get(f"/api/listing-clusters/{missing_cluster_id}")
    assert missing_cluster.status_code == 404
    assert missing_cluster.json()["detail"] == {
        "message": "Listing cluster not found.",
        "cluster_id": str(missing_cluster_id),
    }


def test_site_route_error_and_missing_detail_branches(client, monkeypatch):
    cluster_id = uuid4()
    site_id = uuid4()

    monkeypatch.setattr(
        sites_routes,
        "build_or_refresh_site_from_cluster",
        _raise_site_build_error,
    )
    created = client.post(
        f"/api/sites/from-cluster/{cluster_id}",
        json={"requested_by": "pytest"},
    )
    assert created.status_code == 422
    assert created.json()["detail"] == "boom"

    monkeypatch.setattr(
        sites_routes,
        "build_or_refresh_site_from_cluster",
        lambda *args, **kwargs: SimpleNamespace(id=site_id),
    )
    monkeypatch.setattr(
        sites_routes, "enqueue_site_scenario_suggest_refresh_job", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(sites_routes, "get_site", lambda *args, **kwargs: None)
    missing_after_create = client.post(
        f"/api/sites/from-cluster/{cluster_id}",
        json={"requested_by": "pytest"},
    )
    assert missing_after_create.status_code == 404
    assert missing_after_create.json()["detail"] == "Site was not persisted."

    monkeypatch.setattr(
        sites_routes,
        "save_site_geometry_revision",
        _raise_site_build_error,
    )
    geometry_failure = client.post(
        f"/api/sites/{site_id}/geometry",
        json={"geom_4326": {"type": "Point", "coordinates": [0, 0]}},
    )
    assert geometry_failure.status_code == 422
    assert geometry_failure.json()["detail"] == "boom"

    monkeypatch.setattr(
        sites_routes,
        "save_site_geometry_revision",
        lambda *args, **kwargs: SimpleNamespace(id=site_id),
    )
    monkeypatch.setattr(
        sites_routes,
        "enqueue_site_scenario_geometry_refresh_job",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(sites_routes, "get_site", lambda *args, **kwargs: None)
    missing_after_geometry = client.post(
        f"/api/sites/{site_id}/geometry",
        json={"geom_4326": {"type": "Point", "coordinates": [0, 0]}},
    )
    assert missing_after_geometry.status_code == 404
    assert missing_after_geometry.json()["detail"] == "Site detail not found after save."


def test_site_read_routes_and_extant_permission_missing_sites_return_404(client):
    site_id = uuid4()

    detail = client.get(f"/api/sites/{site_id}")
    assert detail.status_code == 404
    assert detail.json()["detail"] == {
        "message": "Site detail not found.",
        "site_id": str(site_id),
    }

    extant = client.post(
        f"/api/sites/{site_id}/extant-permission-check",
        json={"requested_by": "pytest"},
    )
    assert extant.status_code == 404
    assert extant.json()["detail"] == {
        "message": "Site detail not found.",
        "site_id": str(site_id),
    }


def test_scenario_route_error_and_missing_detail_branches(client, monkeypatch):
    site_id = uuid4()
    scenario_id = uuid4()

    monkeypatch.setattr(
        scenarios_routes,
        "suggest_scenarios_for_site",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    suggestion_failure = client.post(
        f"/api/sites/{site_id}/scenarios/suggest",
        json={"requested_by": "pytest"},
    )
    assert suggestion_failure.status_code == 422
    assert suggestion_failure.json()["detail"] == "boom"

    missing = client.get(f"/api/scenarios/{scenario_id}")
    assert missing.status_code == 404
    assert missing.json()["detail"] == {
        "message": "Scenario detail not found.",
        "scenario_id": str(scenario_id),
    }

    monkeypatch.setattr(
        scenarios_routes,
        "confirm_or_update_scenario",
        _raise_scenario_normalize_error,
    )
    confirm_failure = client.post(
        f"/api/scenarios/{scenario_id}/confirm",
        json={"requested_by": "pytest", "review_notes": "boom"},
    )
    assert confirm_failure.status_code == 422
    assert confirm_failure.json()["detail"] == "boom"

    monkeypatch.setattr(
        scenarios_routes,
        "confirm_or_update_scenario",
        lambda *args, **kwargs: SimpleNamespace(id=scenario_id),
    )
    monkeypatch.setattr(scenarios_routes, "get_scenario_detail", lambda *args, **kwargs: None)
    confirm_missing = client.post(
        f"/api/scenarios/{scenario_id}/confirm",
        json={"requested_by": "pytest", "review_notes": "boom"},
    )
    assert confirm_missing.status_code == 404
    assert confirm_missing.json()["detail"] == {
        "message": "Scenario detail not found.",
        "scenario_id": str(scenario_id),
    }


def test_opportunity_detail_missing_returns_404(client):
    site_id = uuid4()
    detail = client.get(f"/api/opportunities/{site_id}")
    assert detail.status_code == 404
    assert detail.json()["detail"] == {
        "message": "Opportunity detail not found.",
        "site_id": str(site_id),
    }


def test_assessment_route_error_and_missing_detail_branches(client, auth_headers, monkeypatch):
    assessment_id = uuid4()

    monkeypatch.setattr(
        assessments_routes,
        "create_or_refresh_assessment_run",
        _raise_assessment_build_error,
    )
    build_failure = client.post(
        "/api/assessments",
        json={
            "site_id": str(uuid4()),
            "scenario_id": str(uuid4()),
            "as_of_date": "2026-04-15",
            "requested_by": "pytest",
        },
        headers=auth_headers("reviewer"),
    )
    assert build_failure.status_code == 422
    assert build_failure.json()["detail"] == "boom"

    monkeypatch.setattr(
        assessments_routes,
        "create_or_refresh_assessment_run",
        lambda *args, **kwargs: SimpleNamespace(id=assessment_id),
    )
    monkeypatch.setattr(assessments_routes, "get_assessment", lambda *args, **kwargs: None)
    missing_after_create = client.post(
        "/api/assessments",
        json={
            "site_id": str(uuid4()),
            "scenario_id": str(uuid4()),
            "as_of_date": "2026-04-15",
            "requested_by": "pytest",
        },
        headers=auth_headers("reviewer"),
    )
    assert missing_after_create.status_code == 404
    assert missing_after_create.json()["detail"] == {
        "message": "Assessment detail not found.",
        "assessment_id": str(assessment_id),
    }

    detail_missing = client.get(
        f"/api/assessments/{assessment_id}",
        headers=auth_headers("analyst"),
    )
    assert detail_missing.status_code == 404
    assert detail_missing.json()["detail"] == {
        "message": "Assessment detail not found.",
        "assessment_id": str(assessment_id),
    }


def test_assessment_override_and_audit_export_error_branches(
    client,
    auth_headers,
    monkeypatch,
):
    assessment_id = uuid4()

    monkeypatch.setattr(
        assessments_routes,
        "apply_assessment_override",
        _raise_review_access_error,
    )
    override_failure = client.post(
        f"/api/assessments/{assessment_id}/override",
        json={
            "requested_by": "pytest",
            "actor_role": "analyst",
            "override_type": "ACQUISITION_BASIS",
            "reason": "boom",
            "acquisition_basis_gbp": 900000,
            "acquisition_basis_type": "GUIDE_PRICE",
        },
        headers=auth_headers("analyst"),
    )
    assert override_failure.status_code == 422
    assert override_failure.json()["detail"] == "boom"

    monkeypatch.setattr(
        assessments_routes,
        "apply_assessment_override",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(assessments_routes, "get_assessment", lambda *args, **kwargs: None)
    override_missing = client.post(
        f"/api/assessments/{assessment_id}/override",
        json={
            "requested_by": "pytest",
            "actor_role": "analyst",
            "override_type": "ACQUISITION_BASIS",
            "reason": "boom",
            "acquisition_basis_gbp": 900000,
            "acquisition_basis_type": "GUIDE_PRICE",
        },
        headers=auth_headers("analyst"),
    )
    assert override_missing.status_code == 404
    assert override_missing.json()["detail"] == {
        "message": "Assessment detail not found.",
        "assessment_id": str(assessment_id),
    }

    monkeypatch.setattr(
        assessments_routes,
        "build_assessment_audit_export",
        _raise_review_access_error,
    )
    audit_export_failure = client.get(
        f"/api/assessments/{assessment_id}/audit-export?requested_by=pytest",
        headers=auth_headers("reviewer"),
    )
    assert audit_export_failure.status_code == 422
    assert audit_export_failure.json()["detail"] == "boom"


def test_admin_route_error_and_missing_detail_branches(client, auth_headers, monkeypatch):
    snapshot_id = uuid4()
    case_id = uuid4()
    release_id = uuid4()
    scope_key = "test-scope"

    missing_snapshot = client.get(
        f"/api/admin/source-snapshots/{snapshot_id}",
        headers=auth_headers("admin"),
    )
    assert missing_snapshot.status_code == 404
    assert missing_snapshot.json()["detail"] == {
        "message": "Source snapshot not found.",
        "snapshot_id": str(snapshot_id),
    }

    missing_case = client.get(
        f"/api/admin/gold-set/cases/{case_id}",
        headers=auth_headers("reviewer"),
    )
    assert missing_case.status_code == 404
    assert missing_case.json()["detail"] == {
        "message": "Gold-set case not found.",
        "case_id": str(case_id),
    }

    monkeypatch.setattr(admin_routes, "_ensure_historical_labels", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        admin_routes,
        "get_historical_label_case",
        lambda *args, **kwargs: SimpleNamespace(id=case_id),
    )
    monkeypatch.setattr(admin_routes, "review_historical_label_case", lambda *args, **kwargs: None)
    monkeypatch.setattr(admin_routes, "get_gold_set_case_read", lambda *args, **kwargs: None)
    review_missing = client.post(
        f"/api/admin/gold-set/cases/{case_id}/review",
        json={
            "review_status": GoldSetReviewStatus.CONFIRMED.value,
            "review_notes": "pytest",
            "notable_policy_issues": [],
            "extant_permission_outcome": "NO_ACTIVE_PERMISSION_FOUND",
            "site_geometry_confidence": "MEDIUM",
            "reviewed_by": "pytest",
        },
        headers=auth_headers("reviewer"),
    )
    assert review_missing.status_code == 404
    assert review_missing.json()["detail"] == {
        "message": "Gold-set case not found after review.",
        "case_id": str(case_id),
    }

    monkeypatch.setattr(
        admin_routes,
        "retire_model_release",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("boom")),
    )
    retire_failure = client.post(
        f"/api/admin/model-releases/{release_id}/retire",
        json={"requested_by": "pytest"},
        headers=auth_headers("admin"),
    )
    assert retire_failure.status_code == 422
    assert retire_failure.json()["detail"] == "boom"

    incident_failure = client.post(
        f"/api/admin/release-scopes/{scope_key}/incident",
        json={
            "requested_by": "pytest",
            "action": "noop",
            "reason": "boom",
        },
        headers=auth_headers("admin"),
    )
    assert incident_failure.status_code == 422
    assert incident_failure.json()["detail"] == "Unsupported incident action 'noop'."
