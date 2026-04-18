from __future__ import annotations

import json
from datetime import UTC, date, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import HTTPException
from landintel.auth import session as auth_session
from landintel.connectors.public_page import GenericPublicPageConnector
from landintel.domain.enums import AppRoleName, GeomConfidence, ScenarioStatus, SourceParseStatus
from landintel.scoring import score as score_service

import services.api.app.routes.assessments as assessment_routes
import services.api.app.routes.scenarios as scenario_routes
import services.api.app.routes.sites as site_routes
import services.scheduler.app.main as scheduler_main
import services.worker.app.main as worker_main


class _RouteSession:
    def __init__(self, *, scalar=None):
        self.scalar = scalar
        self.commits = 0
        self.rollbacks = 0
        self.expired = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def expire_all(self):
        self.expired += 1

    def execute(self, *args, **kwargs):
        del args, kwargs
        return SimpleNamespace(scalar_one_or_none=lambda: self.scalar)


class _SchedulerStub:
    def __init__(self, *, timezone: str):
        self.timezone = timezone
        self.jobs: list[dict[str, object]] = []
        self.started = False

    def add_job(self, func, trigger, **kwargs):
        self.jobs.append({"func": func, "trigger": trigger, **kwargs})

    def start(self):
        self.started = True


class _FetchedAsset:
    def __init__(self):
        self.final_url = "https://example.test/index"
        self.content = b'<html><body><a href="/skip">Skip</a></body></html>'
        self.content_type = "text/html"
        self.fetched_at = datetime(2026, 4, 18, 10, 0, tzinfo=UTC)
        self.status_code = 200
        self.headers = {"content-type": "text/html"}
        self.page_title = "Fixture"


def _fixed_uuid(seed: int) -> UUID:
    return UUID(f"00000000-0000-0000-0000-{seed:012d}")


def _session_token(payload: object, *, secret: str) -> str:
    payload_part = auth_session._encode_base64url(json.dumps(payload).encode("utf-8"))
    signature = auth_session._sign_payload(payload_part, secret)
    return f"{payload_part}.{signature}"


def test_runtime_main_wiring_and_worker_sleep_branch(monkeypatch) -> None:
    naive = datetime(2026, 4, 18, 10, 0)
    assert scheduler_main._coerce_utc(naive).tzinfo is UTC

    scheduler_instances: list[_SchedulerStub] = []
    monkeypatch.setattr(
        scheduler_main,
        "get_settings",
        lambda: SimpleNamespace(
            database_url="postgresql://fixture",
            database_echo=False,
            scheduler_poll_interval_seconds=30,
        ),
    )
    monkeypatch.setattr(scheduler_main, "configure_logging", lambda _settings: None)
    monkeypatch.setattr(
        scheduler_main,
        "get_session_factory",
        lambda *_args, **_kwargs: "session-factory",
    )
    monkeypatch.setattr(
        scheduler_main,
        "BlockingScheduler",
        lambda *, timezone: scheduler_instances.append(_SchedulerStub(timezone=timezone))
        or scheduler_instances[-1],
    )
    scheduler_main.main()
    assert scheduler_instances[0].timezone == "UTC"
    assert scheduler_instances[0].jobs[0]["id"] == "listing-refresh-enqueue"
    assert scheduler_instances[0].started is True

    monkeypatch.setattr(
        worker_main,
        "get_settings",
        lambda: SimpleNamespace(
            database_url="postgresql://fixture",
            database_echo=False,
            worker_id="worker-1",
            worker_metrics_port=9101,
            worker_poll_interval_seconds=3,
        ),
    )
    monkeypatch.setattr(worker_main, "configure_logging", lambda _settings: None)
    monkeypatch.setattr(
        worker_main,
        "get_session_factory",
        lambda *_args, **_kwargs: "session-factory",
    )
    monkeypatch.setattr(worker_main, "build_storage", lambda _settings: "storage")
    monkeypatch.setattr(worker_main, "start_http_server", lambda _port: None)
    monkeypatch.setattr(worker_main, "dispatch_connector_job", lambda **_kwargs: True)
    monkeypatch.setattr(worker_main, "process_next_job", lambda **_kwargs: False)
    monkeypatch.setattr(
        worker_main.time,
        "sleep",
        lambda _seconds: (_ for _ in ()).throw(RuntimeError("stop")),
    )
    with pytest.raises(RuntimeError, match="stop"):
        worker_main.main()


def test_route_handlers_raise_404_after_successful_service_calls(monkeypatch) -> None:
    assessment_session = _RouteSession()
    monkeypatch.setattr(
        assessment_routes,
        "create_or_refresh_assessment_run",
        lambda **_kwargs: SimpleNamespace(id=_fixed_uuid(1)),
    )
    monkeypatch.setattr(assessment_routes, "get_assessment", lambda **_kwargs: None)
    with pytest.raises(HTTPException) as assessment_error:
        assessment_routes.create_assessment(
            request=SimpleNamespace(
                site_id=_fixed_uuid(2),
                scenario_id=_fixed_uuid(3),
                as_of_date=date(2026, 4, 18),
                requested_by=None,
                hidden_mode=False,
            ),
            session=assessment_session,
            storage=object(),
            actor=SimpleNamespace(
                role=AppRoleName.ANALYST,
                user_name=None,
                user_email=None,
                user_id=None,
            ),
        )
    assert assessment_error.value.status_code == 404
    assert assessment_session.commits == 1

    scenario_session = _RouteSession()
    monkeypatch.setattr(
        scenario_routes,
        "confirm_or_update_scenario",
        lambda **_kwargs: SimpleNamespace(id=_fixed_uuid(4)),
    )
    monkeypatch.setattr(scenario_routes, "get_scenario_detail", lambda **_kwargs: None)
    with pytest.raises(HTTPException) as scenario_error:
        scenario_routes.confirm_scenario(
            scenario_id=_fixed_uuid(4),
            request=SimpleNamespace(),
            session=scenario_session,
        )
    assert scenario_error.value.status_code == 404
    assert scenario_session.commits == 1

    site_session = _RouteSession(scalar=SimpleNamespace(id=_fixed_uuid(5)))
    monkeypatch.setattr(site_routes, "refresh_site_planning_context", lambda **_kwargs: None)
    monkeypatch.setattr(
        site_routes,
        "evaluate_site_extant_permission",
        lambda **_kwargs: SimpleNamespace(),
    )
    monkeypatch.setattr(site_routes, "audit_extant_permission_check", lambda **_kwargs: None)
    monkeypatch.setattr(site_routes, "get_site", lambda *_args, **_kwargs: None)
    with pytest.raises(HTTPException) as site_error:
        site_routes.rerun_extant_permission(
            site_id=_fixed_uuid(5),
            request=SimpleNamespace(requested_by="pytest"),
            session=site_session,
        )
    assert site_error.value.status_code == 404
    assert site_session.commits == 1


def test_auth_session_decode_non_dict_payload_and_naive_datetime_branch() -> None:
    token = _session_token(
        ["not", "a", "dict"],
        secret="secret",
    )
    assert auth_session._decode_session_token(token=token, secret="secret") is None

    parsed = auth_session._parse_datetime("2026-04-18T10:00:00")
    assert parsed is not None
    assert parsed.tzinfo is UTC


def test_public_page_connector_failed_parse_uses_seed_asset_timestamp() -> None:
    fetcher = SimpleNamespace(fetch_asset=lambda _url: _FetchedAsset())
    connector = GenericPublicPageConnector(fetcher)
    output = connector.run(
        context=SimpleNamespace(
            source_name="public-page",
            requested_by="pytest",
            refresh_policy_json={
                "seed_urls": ["https://example.test/index"],
                "listing_link_selector": "a",
                "listing_url_patterns": [r"/match$"],
                "max_listings": 5,
            },
        ),
        payload={},
    )
    assert output.parse_status == SourceParseStatus.FAILED
    assert output.listings == []
    assert output.observed_at == datetime(2026, 4, 18, 10, 0, tzinfo=UTC)
    assert output.manifest_json["listing_count"] == 0


def test_score_frozen_assessment_falls_back_for_invalid_feature_enums(monkeypatch) -> None:
    monkeypatch.setattr(score_service, "encode_feature_values", lambda *_args, **_kwargs: [1.0])
    monkeypatch.setattr(
        score_service,
        "predict_probability_from_vector",
        lambda *_args, **_kwargs: 0.52,
    )
    monkeypatch.setattr(
        score_service,
        "apply_calibration",
        lambda *_args, **_kwargs: 0.41,
    )
    monkeypatch.setattr(
        score_service,
        "derive_source_coverage_quality",
        lambda _coverage_json: "LOW",
    )
    monkeypatch.setattr(
        score_service,
        "derive_geometry_quality",
        lambda _confidence: "MEDIUM",
    )
    monkeypatch.setattr(
        score_service,
        "derive_scenario_quality",
        lambda **_kwargs: "HIGH",
    )
    monkeypatch.setattr(
        score_service,
        "derive_support_quality",
        lambda **_kwargs: "SPARSE",
    )
    monkeypatch.setattr(
        score_service,
        "derive_ood_status",
        lambda **_kwargs: ("OUT_OF_SUPPORT", "LOW"),
    )
    monkeypatch.setattr(
        score_service,
        "final_estimate_quality",
        lambda **_kwargs: SimpleNamespace(value="LOW"),
    )
    monkeypatch.setattr(
        score_service,
        "generate_hidden_score_explanation",
        lambda **_kwargs: {"drivers": ["policy"]},
    )

    result = score_service.score_frozen_assessment(
        model_artifact={"transform_spec": {}, "training_support": {}},
        calibration_artifact=None,
        validation_artifact={"status": "ok", "metrics": {"auc": 0.75}},
        release_id="release-1",
        feature_json={
            "values": {
                "geom_confidence": "NOT_A_REAL_ENUM",
                "scenario_status": "NOT_A_REAL_STATUS",
                "scenario_is_stale": True,
            }
        },
        coverage_json={"source_coverage": []},
        site=SimpleNamespace(
            borough_id="camden",
            geom_confidence=GeomConfidence.HIGH,
            manual_review_required=False,
        ),
        scenario=SimpleNamespace(
            manual_review_required=False,
            status=ScenarioStatus.ANALYST_CONFIRMED,
            stale_reason=None,
        ),
        evidence=SimpleNamespace(),
        comparable_case_set=None,
        comparable_payload={"approved": [], "refused": [], "strategy": "fixture"},
    )
    assert result["approval_probability_raw"] == 0.41
    assert result["geometry_quality"] == "MEDIUM"
    assert result["scenario_quality"] == "HIGH"
    assert result["ood_status"] == "OUT_OF_SUPPORT"
    assert result["manual_review_required"] is True
