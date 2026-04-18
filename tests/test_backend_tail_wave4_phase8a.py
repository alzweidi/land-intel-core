from __future__ import annotations

import json
import runpy
import sys
import time
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import ClassVar
from uuid import UUID

import landintel.connectors.public_page as public_page_service
import pytest
from landintel.auth import session as auth_session
from landintel.connectors.public_page import GenericPublicPageConnector
from landintel.domain.enums import PriceBasisType, SourceParseStatus
from landintel.valuation import service as valuation_service

import services.api.app.routes.assessments as assessment_routes
import services.api.app.routes.scenarios as scenario_routes


class _BlockingSchedulerStub:
    instances: ClassVar[list[_BlockingSchedulerStub]] = []

    def __init__(self, *, timezone: str):
        self.timezone = timezone
        self.jobs: list[dict[str, object]] = []
        _BlockingSchedulerStub.instances.append(self)

    def add_job(self, func, trigger, **kwargs):
        self.jobs.append({"func": func, "trigger": trigger, **kwargs})

    def start(self):
        raise RuntimeError("scheduler-stop")


class _SessionFactory:
    def __call__(self):
        return self

    def __enter__(self):
        return SimpleNamespace(commit=lambda: None)

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


def _fixed_uuid(seed: int) -> UUID:
    return UUID(f"00000000-0000-0000-0000-{seed:012d}")


def _token(payload: object, *, secret: str) -> str:
    payload_part = auth_session._encode_base64url(json.dumps(payload).encode("utf-8"))
    signature = auth_session._sign_payload(payload_part, secret)
    return f"{payload_part}.{signature}"


def test_tail_helpers_cover_invalid_split_public_page_dedupe_and_routes(monkeypatch) -> None:
    assert auth_session._decode_session_token(token="missing-delimiter", secret="secret") is None

    captured_urls: list[str] = []
    monkeypatch.setattr(
        public_page_service,
        "capture_listing_page",
        lambda *, fetcher, url, asset_prefix: (
            captured_urls.append(url)
            or SimpleNamespace(
                assets=[],
                listing=SimpleNamespace(observed_at=datetime(2026, 4, 18, 12, 0, tzinfo=UTC)),
            )
        ),
    )
    connector = GenericPublicPageConnector(fetcher=SimpleNamespace())
    output = connector.run(
        context=SimpleNamespace(
            source_name="public-page",
            requested_by="pytest",
            refresh_policy_json={
                "seed_urls": [
                    "https://example.test/listing",
                    "https://example.test/listing",
                    "https://example.test/other",
                ],
                "max_listings": 2,
            },
        ),
        payload={},
    )
    assert output.parse_status == SourceParseStatus.PARSED
    assert captured_urls == [
        "https://example.test/listing",
        "https://example.test/other",
    ]

    expected_assessment_list = SimpleNamespace(items=["assessment"], total=1)
    monkeypatch.setattr(
        assessment_routes,
        "list_assessments",
        lambda **_kwargs: expected_assessment_list,
    )
    assert (
        assessment_routes.get_assessment_runs(
            site_id=_fixed_uuid(1),
            scenario_id=_fixed_uuid(2),
            limit=5,
            offset=1,
            session=object(),
        )
        is expected_assessment_list
    )

    expected_scenarios = SimpleNamespace(items=["scenario"], total=1)
    monkeypatch.setattr(
        scenario_routes,
        "list_site_scenarios",
        lambda **_kwargs: expected_scenarios,
    )
    assert (
        scenario_routes.get_site_scenarios(
            site_id=_fixed_uuid(3),
            session=object(),
        )
        is expected_scenarios
    )


def test_valuation_basis_fallback_and_main_guards_via_runpy(monkeypatch) -> None:
    assert valuation_service._frozen_basis_inputs(
        SimpleNamespace(feature_snapshot=SimpleNamespace(feature_json={"values": "not-a-dict"}))
    ) == (None, PriceBasisType.UNKNOWN)

    monkeypatch.setattr(
        "landintel.config.get_settings",
        lambda: SimpleNamespace(
            database_url="postgresql://fixture",
            database_echo=False,
            scheduler_poll_interval_seconds=15,
        ),
    )
    monkeypatch.setattr("landintel.db.session.get_session_factory", lambda *_args: "factory")
    monkeypatch.setattr("landintel.logging.configure_logging", lambda _settings: None)
    monkeypatch.setattr(
        "apscheduler.schedulers.blocking.BlockingScheduler",
        _BlockingSchedulerStub,
    )
    sys.modules.pop("services.scheduler.app.main", None)
    with pytest.raises(RuntimeError, match="scheduler-stop"):
        runpy.run_module("services.scheduler.app.main", run_name="__main__")
    assert _BlockingSchedulerStub.instances[-1].jobs[0]["id"] == "listing-refresh-enqueue"

    monkeypatch.setattr(
        "landintel.config.get_settings",
        lambda: SimpleNamespace(
            database_url="postgresql://fixture",
            database_echo=False,
            worker_id="worker-1",
            worker_metrics_port=9102,
            worker_poll_interval_seconds=1,
        ),
    )
    monkeypatch.setattr(
        "landintel.db.session.get_session_factory",
        lambda *_args: _SessionFactory(),
    )
    monkeypatch.setattr("landintel.logging.configure_logging", lambda _settings: None)
    monkeypatch.setattr("landintel.storage.factory.build_storage", lambda _settings: "storage")
    monkeypatch.setattr("prometheus_client.start_http_server", lambda _port: None)
    monkeypatch.setattr("landintel.jobs.service.claim_next_job", lambda **_kwargs: None)
    monkeypatch.setattr(
        "landintel.monitoring.metrics.WORKER_LOOP_COUNT",
        SimpleNamespace(inc=lambda: None),
    )
    monkeypatch.setattr(
        time,
        "sleep",
        lambda _seconds: (_ for _ in ()).throw(RuntimeError("worker-stop")),
    )
    sys.modules.pop("services.worker.app.main", None)
    with pytest.raises(RuntimeError, match="worker-stop"):
        runpy.run_module("services.worker.app.main", run_name="__main__")
