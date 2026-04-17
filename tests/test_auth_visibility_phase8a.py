from __future__ import annotations

import pytest
from landintel.config import DEFAULT_WEB_AUTH_SESSION_SECRET, Settings
from pydantic import ValidationError

from tests.test_controls_phase8a import _build_scored_assessment


def test_assessment_hidden_mode_requires_privileged_session(
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

    forged = client.get(
        f"/api/assessments/{assessment['id']}?hidden_mode=true&viewer_role=reviewer"
    )
    assert forged.status_code == 200
    forged_payload = forged.json()
    assert forged_payload["result"]["approval_probability_raw"] is None
    assert forged_payload["visibility"]["viewer_role"] == "analyst"
    assert forged_payload["visibility"]["hidden_probability_allowed"] is False
    assert forged_payload["result"]["estimate_quality"] is None
    assert forged_payload["result"]["ood_status"] is None
    assert forged_payload["result"]["source_coverage_quality"] is None

    reviewer = client.get(
        f"/api/assessments/{assessment['id']}?hidden_mode=true",
        headers=auth_headers("reviewer"),
    )
    assert reviewer.status_code == 200
    reviewer_payload = reviewer.json()
    assert reviewer_payload["result"]["approval_probability_raw"] is not None
    assert reviewer_payload["visibility"]["viewer_role"] == "reviewer"
    assert reviewer_payload["visibility"]["hidden_probability_allowed"] is True
    assert reviewer_payload["result"]["estimate_quality"] is not None
    assert reviewer_payload["result"]["ood_status"] is not None


def test_forged_actor_role_no_longer_grants_reviewer_or_admin_access(
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

    site_payload, _scenario, assessment = _build_scored_assessment(
        client=client,
        drain_jobs=drain_jobs,
        db_session=db_session,
        storage=storage,
        auth_headers=auth_headers,
    )
    scope_key = assessment["result"]["release_scope_key"]

    forged_export = client.get(
        f"/api/assessments/{assessment['id']}/audit-export?actor_role=reviewer&requested_by=pytest"
    )
    assert forged_export.status_code == 403

    reviewer_export = client.get(
        f"/api/assessments/{assessment['id']}/audit-export?requested_by=pytest",
        headers=auth_headers("reviewer"),
    )
    assert reviewer_export.status_code == 200

    forged_admin = client.post(
        f"/api/admin/release-scopes/{scope_key}/visibility",
        json={
            "requested_by": "pytest",
            "actor_role": "admin",
            "visibility_mode": "VISIBLE_REVIEWER_ONLY",
            "reason": "Forged admin attempt.",
        },
    )
    assert forged_admin.status_code == 403

    reviewer_admin = client.post(
        f"/api/admin/release-scopes/{scope_key}/visibility",
        json={
            "requested_by": "pytest",
            "actor_role": "admin",
            "visibility_mode": "VISIBLE_REVIEWER_ONLY",
            "reason": "Reviewer cannot escalate to admin.",
        },
        headers=auth_headers("reviewer"),
    )
    assert reviewer_admin.status_code == 403

    admin_attempt = client.post(
        f"/api/admin/release-scopes/{scope_key}/visibility",
        json={
            "requested_by": "pytest",
            "visibility_mode": "VISIBLE_REVIEWER_ONLY",
            "reason": "Admin-authenticated request reaches business rule checks.",
        },
        headers=auth_headers("admin"),
    )
    assert admin_attempt.status_code == 422
    assert "borough-scoped active release" in admin_attempt.json()["detail"]

    forged_hidden_opportunity = client.get(
        f"/api/opportunities/{site_payload['id']}?hidden_mode=true&viewer_role=reviewer"
    )
    assert forged_hidden_opportunity.status_code == 200
    forged_opportunity_payload = forged_hidden_opportunity.json()
    assert (
        forged_opportunity_payload["assessment"]["visibility"]["hidden_probability_allowed"]
        is False
    )


def test_non_dev_settings_require_non_default_web_auth_secret():
    with pytest.raises(ValidationError):
        Settings(
            app_env="production",
            web_auth_session_secret=DEFAULT_WEB_AUTH_SESSION_SECRET,
        )

    settings = Settings(
        app_env="development",
        web_auth_session_secret=DEFAULT_WEB_AUTH_SESSION_SECRET,
    )
    assert settings.web_auth_session_secret == DEFAULT_WEB_AUTH_SESSION_SECRET


def test_missing_app_env_with_non_local_database_requires_explicit_secret():
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            database_url="postgresql+psycopg://landintel:landintel@prod-db:5432/landintel",
            web_auth_session_secret=DEFAULT_WEB_AUTH_SESSION_SECRET,
        )
