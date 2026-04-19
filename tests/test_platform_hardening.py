from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import sys
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import landintel.geospatial.bootstrap as geo_bootstrap
import landintel.monitoring.health as health_mod
import landintel.planning.bootstrap as planning_bootstrap
import landintel.valuation.bootstrap as valuation_bootstrap
import pytest
from fastapi import Response
from landintel.auth.session import SESSION_HEADER_NAME, resolve_request_actor
from landintel.domain.enums import (
    AppRoleName,
    ComplianceMode,
    ConnectorType,
    JobStatus,
    JobType,
    StorageBackend,
)
from landintel.domain.models import JobRun, ListingSource
from landintel.jobs.service import (
    enqueue_cluster_rebuild_job,
    enqueue_connector_run_job,
    enqueue_site_build_job,
    mark_job_succeeded,
)
from landintel.storage.factory import build_storage
from landintel.storage.local import LocalFileStorageAdapter
from landintel.storage.supabase import SupabaseStorageAdapter
from starlette.requests import Request

import services.api.app.dependencies as api_dependencies
import services.api.app.main as api_main
import services.scheduler.app.main as scheduler_main
import services.worker.app.jobs.connectors as connector_jobs
import services.worker.app.main as worker_main


def _signed_session_token(*, secret: str, role: str, expires_at: datetime | None = None) -> str:
    payload = {
        "user": {
            "id": f"{role}@example.test",
            "email": f"{role}@example.test",
            "name": role.title(),
            "role": role,
        },
        "issuedAt": datetime.now(UTC).isoformat(),
        "expiresAt": (expires_at or (datetime.now(UTC) + timedelta(hours=1))).isoformat(),
    }
    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_token = base64.urlsafe_b64encode(payload_json).decode("ascii").rstrip("=")
    signature = hmac.new(
        secret.encode("utf-8"),
        payload_token.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    signature_token = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
    return f"{payload_token}.{signature_token}"


def _request(
    *,
    headers: dict[str, str] | None = None,
    cookies: dict[str, str] | None = None,
) -> Request:
    raw_headers = [
        (key.lower().encode("ascii"), value.encode("utf-8"))
        for key, value in (headers or {}).items()
    ]
    if cookies:
        cookie_header = "; ".join(f"{key}={value}" for key, value in cookies.items())
        raw_headers.append((b"cookie", cookie_header.encode("utf-8")))
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": raw_headers,
        "client": ("127.0.0.1", 1234),
        "server": ("testserver", 80),
    }
    return Request(scope)


class _DummyContextFactory:
    def __init__(self, session: SimpleNamespace) -> None:
        self._session = session

    def __call__(self):
        return self

    def __enter__(self):
        return self._session

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class _FakeThread:
    def __init__(self) -> None:
        self.join_timeout: float | None = None

    def join(self, timeout: float | None = None) -> None:
        self.join_timeout = timeout


class _FakeStopEvent:
    def __init__(self) -> None:
        self.was_set = False

    def set(self) -> None:
        self.was_set = True


def _job(db_session, job_type: JobType, payload_json: dict[str, object] | None = None) -> JobRun:
    now = datetime.now(UTC)
    job = JobRun(
        job_type=job_type,
        payload_json=payload_json or {},
        status=JobStatus.RUNNING,
        run_at=now,
        next_run_at=now,
        requested_by="pytest",
        attempts=1,
    )
    db_session.add(job)
    db_session.flush()
    return job


def test_build_storage_and_supabase_adapter_behaviour(monkeypatch, test_settings):
    local = build_storage(test_settings)
    assert isinstance(local, LocalFileStorageAdapter)

    settings = test_settings.model_copy(
        update={
            "storage_backend": StorageBackend.SUPABASE,
            "supabase_url": "https://example.supabase.co",
            "supabase_service_role_key": "service-role",
            "supabase_storage_bucket": "landintel",
        }
    )
    adapter = build_storage(settings)
    assert isinstance(adapter, SupabaseStorageAdapter)

    calls: dict[str, object] = {}

    class _Response:
        def __init__(self, status_code: int, *, content: bytes = b"", text: str = "") -> None:
            self.status_code = status_code
            self.content = content
            self.text = text

    def fake_post(url, *, content, headers, timeout):
        calls["post"] = {
            "url": url,
            "content": content,
            "headers": headers,
            "timeout": timeout,
        }
        return _Response(201)

    def fake_get(url, *, headers, timeout):
        calls.setdefault("get", []).append({"url": url, "headers": headers, "timeout": timeout})
        if url.endswith("/missing.txt"):
            return _Response(404)
        return _Response(200, content=b"stored-bytes")

    monkeypatch.setattr("landintel.storage.supabase.httpx.post", fake_post)
    monkeypatch.setattr("landintel.storage.supabase.httpx.get", fake_get)

    stored = adapter.put_bytes("folder/object.txt", b"payload", content_type="text/plain")
    assert stored.storage_path == "folder/object.txt"
    assert stored.size_bytes == 7
    assert calls["post"]["headers"]["x-upsert"] == "false"

    assert adapter.get_bytes("folder/object.txt") == b"stored-bytes"
    with pytest.raises(FileNotFoundError):
        adapter.get_bytes("missing.txt")

    bad_settings = settings.model_copy(
        update={
            "supabase_url": "",
            "supabase_service_role_key": "",
        }
    )
    with pytest.raises(ValueError):
        build_storage(bad_settings)


def test_geospatial_bootstrap_main_runs_imports(monkeypatch, capsys):
    session = SimpleNamespace(committed=False)
    session.commit = lambda: setattr(session, "committed", True)

    monkeypatch.setattr(
        geo_bootstrap,
        "build_parser",
        lambda: SimpleNamespace(
            parse_args=lambda: SimpleNamespace(
                dataset="all",
                lpa_path="lpa.geojson",
                titles_path="titles.geojson",
                requested_by="pytest",
            )
        ),
    )
    monkeypatch.setattr(
        geo_bootstrap,
        "get_settings",
        lambda: SimpleNamespace(database_url="sqlite://", database_echo=False),
    )
    monkeypatch.setattr(
        geo_bootstrap,
        "get_session_factory",
        lambda *args: _DummyContextFactory(session),
    )
    monkeypatch.setattr(geo_bootstrap, "build_storage", lambda settings: "storage")
    monkeypatch.setattr(
        geo_bootstrap,
        "import_lpa_boundaries",
        lambda **kwargs: SimpleNamespace(source_snapshot_id="lpa-snapshot", imported_count=2),
    )
    monkeypatch.setattr(
        geo_bootstrap,
        "import_hmlr_title_polygons",
        lambda **kwargs: SimpleNamespace(source_snapshot_id="title-snapshot", imported_count=3),
    )

    geo_bootstrap.main()

    output = capsys.readouterr().out
    assert "Imported LPA boundaries: snapshot=lpa-snapshot features=2" in output
    assert "Imported title polygons: snapshot=title-snapshot features=3" in output
    assert session.committed is True


def test_planning_bootstrap_main_runs_imports(monkeypatch, capsys):
    session = SimpleNamespace(committed=False)
    session.commit = lambda: setattr(session, "committed", True)
    result = SimpleNamespace(
        source_snapshot_id="planning-snapshot",
        imported_count=1,
        coverage_count=1,
    )

    monkeypatch.setattr(
        planning_bootstrap,
        "build_parser",
        lambda: SimpleNamespace(
            parse_args=lambda: SimpleNamespace(
                dataset="all",
                pld_path="pld.json",
                borough_register_path="borough.json",
                brownfield_path="brownfield.geojson",
                policy_path="policy.geojson",
                constraints_path="constraints.geojson",
                flood_path="flood.geojson",
                heritage_path="heritage.geojson",
                baseline_pack_path="baseline.json",
                requested_by="pytest",
            )
        ),
    )
    monkeypatch.setattr(
        planning_bootstrap,
        "get_settings",
        lambda: SimpleNamespace(database_url="sqlite://", database_echo=False),
    )
    monkeypatch.setattr(
        planning_bootstrap,
        "get_session_factory",
        lambda *args: _DummyContextFactory(session),
    )
    monkeypatch.setattr(planning_bootstrap, "build_storage", lambda settings: "storage")
    for name in (
        "import_pld_fixture",
        "import_borough_register_fixture",
        "import_brownfield_fixture",
        "import_policy_area_fixture",
        "import_constraint_fixture",
        "import_flood_fixture",
        "import_heritage_article4_fixture",
        "import_baseline_pack_fixture",
    ):
        monkeypatch.setattr(planning_bootstrap, name, lambda **kwargs: result)

    planning_bootstrap.main()

    output = capsys.readouterr().out
    assert "Imported PLD fixture: snapshot=planning-snapshot records=1 coverage=1" in output
    assert (
        "Imported baseline-pack fixture: snapshot=planning-snapshot records=1 coverage=1"
        in output
    )
    assert session.committed is True


def test_valuation_bootstrap_main_runs_imports(monkeypatch, capsys):
    session = SimpleNamespace(committed=False)
    session.commit = lambda: setattr(session, "committed", True)
    result = SimpleNamespace(
        source_snapshot_id="valuation-snapshot",
        imported_count=2,
        coverage_count=2,
    )

    monkeypatch.setattr(
        valuation_bootstrap,
        "build_parser",
        lambda: SimpleNamespace(
            parse_args=lambda: SimpleNamespace(
                dataset="all",
                hmlr_price_paid_path="price-paid.json",
                ukhpi_path="ukhpi.json",
                land_comps_path="land-comps.json",
                requested_by="pytest",
            )
        ),
    )
    monkeypatch.setattr(
        valuation_bootstrap,
        "get_settings",
        lambda: SimpleNamespace(database_url="sqlite://", database_echo=False),
    )
    monkeypatch.setattr(
        valuation_bootstrap,
        "get_session_factory",
        lambda *args: _DummyContextFactory(session),
    )
    monkeypatch.setattr(valuation_bootstrap, "build_storage", lambda settings: "storage")
    monkeypatch.setattr(
        valuation_bootstrap,
        "ensure_default_assumption_set",
        lambda db_session: SimpleNamespace(version="v1", id="assumption-set"),
    )
    monkeypatch.setattr(
        valuation_bootstrap,
        "import_hmlr_price_paid_fixture",
        lambda **kwargs: result,
    )
    monkeypatch.setattr(valuation_bootstrap, "import_ukhpi_fixture", lambda **kwargs: result)
    monkeypatch.setattr(valuation_bootstrap, "import_land_comp_fixture", lambda **kwargs: result)

    valuation_bootstrap.main()

    output = capsys.readouterr().out
    assert "Seeded valuation assumptions: version=v1 id=assumption-set" in output
    assert "Imported land comps fixture: snapshot=valuation-snapshot records=2 coverage=2" in output
    assert session.committed is True


def test_scheduler_tick_only_enqueues_due_compliant_sources(db_session, session_factory):
    now = datetime.now(UTC)
    db_session.add_all(
        [
            ListingSource(
                name="due-source",
                connector_type=ConnectorType.PUBLIC_PAGE,
                compliance_mode=ComplianceMode.COMPLIANT_AUTOMATED,
                refresh_policy_json={"interval_hours": 1},
                active=True,
            ),
            ListingSource(
                name="queued-source",
                connector_type=ConnectorType.PUBLIC_PAGE,
                compliance_mode=ComplianceMode.COMPLIANT_AUTOMATED,
                refresh_policy_json={"interval_hours": 1},
                active=True,
            ),
            ListingSource(
                name="recent-source",
                connector_type=ConnectorType.PUBLIC_PAGE,
                compliance_mode=ComplianceMode.COMPLIANT_AUTOMATED,
                refresh_policy_json={"interval_hours": 24},
                active=True,
            ),
            ListingSource(
                name="manual-source",
                connector_type=ConnectorType.MANUAL_URL,
                compliance_mode=ComplianceMode.MANUAL_ONLY,
                refresh_policy_json={"interval_hours": 1},
                active=True,
            ),
        ]
    )
    db_session.flush()
    db_session.add_all(
        [
            JobRun(
                job_type=JobType.LISTING_SOURCE_RUN,
                payload_json={"source_name": "queued-source"},
                status=JobStatus.QUEUED,
                run_at=now,
                next_run_at=now,
                requested_by="pytest",
            ),
            JobRun(
                job_type=JobType.LISTING_SOURCE_RUN,
                payload_json={"source_name": "recent-source"},
                status=JobStatus.SUCCEEDED,
                run_at=now,
                next_run_at=now,
                requested_by="pytest",
                created_at=now,
            ),
        ]
    )
    db_session.commit()

    scheduler_main.scheduler_tick(session_factory)

    db_session.expire_all()
    jobs = db_session.query(JobRun).filter(JobRun.job_type == JobType.LISTING_SOURCE_RUN).all()
    due_jobs = [job for job in jobs if job.payload_json.get("source_name") == "due-source"]
    queued_jobs = [job for job in jobs if job.payload_json.get("source_name") == "queued-source"]
    recent_jobs = [job for job in jobs if job.payload_json.get("source_name") == "recent-source"]
    manual_jobs = [job for job in jobs if job.payload_json.get("source_name") == "manual-source"]

    assert len(due_jobs) == 1
    assert due_jobs[0].requested_by == "scheduler"
    assert len(queued_jobs) == 1
    assert len(recent_jobs) == 1
    assert manual_jobs == []


def test_scheduler_tick_skips_interval_less_sources_and_coerces_naive_created_at(
    db_session,
    session_factory,
):
    now_aware = datetime.now(UTC)
    now_naive = datetime.now()
    db_session.add_all(
        [
            ListingSource(
                name="due-source",
                connector_type=ConnectorType.PUBLIC_PAGE,
                compliance_mode=ComplianceMode.COMPLIANT_AUTOMATED,
                refresh_policy_json={"interval_hours": 1},
                active=True,
            ),
            ListingSource(
                name="interval-less-source",
                connector_type=ConnectorType.PUBLIC_PAGE,
                compliance_mode=ComplianceMode.COMPLIANT_AUTOMATED,
                refresh_policy_json={},
                active=True,
            ),
            ListingSource(
                name="recent-source",
                connector_type=ConnectorType.PUBLIC_PAGE,
                compliance_mode=ComplianceMode.COMPLIANT_AUTOMATED,
                refresh_policy_json={"interval_hours": 24},
                active=True,
            ),
        ]
    )
    db_session.flush()
    db_session.add(
        JobRun(
            job_type=JobType.LISTING_SOURCE_RUN,
            payload_json={"source_name": "recent-source"},
            status=JobStatus.SUCCEEDED,
            run_at=now_aware,
            next_run_at=now_aware,
            requested_by="pytest",
            created_at=now_naive,
        )
    )
    db_session.commit()

    scheduler_main.scheduler_tick(session_factory)

    db_session.expire_all()
    jobs = db_session.query(JobRun).filter(JobRun.job_type == JobType.LISTING_SOURCE_RUN).all()
    by_source = {
        source_name: [job for job in jobs if job.payload_json.get("source_name") == source_name]
        for source_name in {"due-source", "interval-less-source", "recent-source"}
    }
    assert len(by_source["due-source"]) == 1
    assert by_source["due-source"][0].requested_by == "scheduler"
    assert by_source["interval-less-source"] == []
    assert len(by_source["recent-source"]) == 1


def test_dependency_guards_reject_invalid_session_and_role_branches():
    invalid_reviewer = SimpleNamespace(
        session_token_present=True,
        authenticated=False,
        role=AppRoleName.REVIEWER,
    )
    with pytest.raises(Exception) as excinfo:
        api_dependencies.require_reviewer_actor(invalid_reviewer)
    assert getattr(excinfo.value, "status_code", None) == 401

    wrong_reviewer = SimpleNamespace(
        session_token_present=False,
        authenticated=True,
        role=AppRoleName.ANALYST,
    )
    with pytest.raises(Exception) as excinfo:
        api_dependencies.require_reviewer_actor(wrong_reviewer)
    assert getattr(excinfo.value, "status_code", None) == 403

    invalid_admin = SimpleNamespace(
        session_token_present=True,
        authenticated=False,
        role=AppRoleName.ADMIN,
    )
    with pytest.raises(Exception) as excinfo:
        api_dependencies.require_admin_actor(invalid_admin)
    assert getattr(excinfo.value, "status_code", None) == 401

    wrong_admin = SimpleNamespace(
        session_token_present=False,
        authenticated=True,
        role=AppRoleName.REVIEWER,
    )
    with pytest.raises(Exception) as excinfo:
        api_dependencies.require_admin_actor(wrong_admin)
    assert getattr(excinfo.value, "status_code", None) == 403


def test_database_ready_covers_success_and_failure(session_factory):
    assert health_mod.database_ready(session_factory) is True

    def failing_factory():
        raise RuntimeError("boom")

    assert health_mod.database_ready(failing_factory) is False


def test_api_lifespan_runs_migrations_when_enabled(monkeypatch):
    calls: dict[str, object] = {}

    def fake_upgrade(config, target):
        calls["upgrade"] = (config, target)

    fake_command_module = SimpleNamespace(upgrade=fake_upgrade)
    fake_alembic_module = SimpleNamespace(command=fake_command_module)
    fake_config_module = SimpleNamespace(Config=lambda path: f"config:{path}")
    monkeypatch.setitem(sys.modules, "alembic", fake_alembic_module)
    monkeypatch.setitem(sys.modules, "alembic.config", fake_config_module)

    app = SimpleNamespace(
        state=SimpleNamespace(settings=SimpleNamespace(run_db_migrations=True))
    )

    async def _run_lifespan() -> None:
        async with api_main.lifespan(app):
            pass

    asyncio.run(_run_lifespan())

    assert calls["upgrade"] == ("config:alembic.ini", "head")


@pytest.mark.parametrize(
    ("job_type", "handler_name"),
    [
        (JobType.MANUAL_URL_SNAPSHOT, "execute_listing_job"),
        (JobType.CSV_IMPORT_SNAPSHOT, "execute_listing_job"),
        (JobType.LISTING_SOURCE_RUN, "execute_listing_job"),
        (JobType.LISTING_CLUSTER_REBUILD, "rebuild_listing_clusters"),
        (JobType.SITE_BUILD_REFRESH, "run_site_build_job"),
        (JobType.SITE_LPA_LINK_REFRESH, "run_site_lpa_refresh_job"),
        (JobType.SITE_TITLE_LINK_REFRESH, "run_site_title_refresh_job"),
        (JobType.PLD_INGEST_REFRESH, "run_pld_ingest_job"),
        (JobType.BOROUGH_REGISTER_INGEST, "run_borough_register_ingest_job"),
        (JobType.SITE_PLANNING_ENRICH, "run_site_planning_enrich_job"),
        (JobType.SITE_EXTANT_PERMISSION_RECHECK, "run_site_extant_permission_recheck_job"),
        (JobType.SOURCE_COVERAGE_REFRESH, "run_source_coverage_refresh_job"),
        (JobType.SITE_SCENARIO_SUGGEST_REFRESH, "run_site_scenario_suggest_refresh_job"),
        (JobType.SITE_SCENARIO_GEOMETRY_REFRESH, "run_site_scenario_geometry_refresh_job"),
        (JobType.BOROUGH_RULEPACK_SCENARIO_REFRESH, "run_borough_rulepack_scenario_refresh_job"),
        (JobType.SCENARIO_EVIDENCE_REFRESH, "run_scenario_evidence_refresh_job"),
        (JobType.HISTORICAL_LABEL_REBUILD, "run_historical_label_rebuild_job"),
        (JobType.ASSESSMENT_FEATURE_SNAPSHOT_BUILD, "run_assessment_feature_snapshot_build_job"),
        (JobType.COMPARABLE_RETRIEVAL_BUILD, "run_comparable_retrieval_build_job"),
        (JobType.REPLAY_VERIFICATION_BATCH, "run_replay_verification_batch_job"),
        (JobType.GOLD_SET_REFRESH, "run_gold_set_refresh_job"),
        (JobType.VALUATION_DATA_REFRESH, "run_valuation_data_refresh_job"),
        (JobType.VALUATION_RUN_BUILD, "run_valuation_run_build_job"),
    ],
)
def test_dispatch_connector_job_routes_supported_job_types(
    db_session,
    test_settings,
    storage,
    monkeypatch,
    job_type,
    handler_name,
):
    calls: list[dict[str, object]] = []

    def recorder(*args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})

    monkeypatch.setattr(connector_jobs, handler_name, recorder)
    job = _job(db_session, job_type)

    handled = connector_jobs.dispatch_connector_job(
        session=db_session,
        job=job,
        settings=test_settings,
        storage=storage,
    )

    assert handled is True
    assert len(calls) == 1
    assert job.status == JobStatus.SUCCEEDED


def test_dispatch_connector_job_marks_unknown_types_failed(monkeypatch, test_settings, storage):
    class _UnknownJobType:
        value = "UNKNOWN"

    fake_job = SimpleNamespace(job_type=_UnknownJobType(), attempts=0, status=JobStatus.RUNNING)
    captured: dict[str, object] = {}

    def fake_mark_job_failed(session, job, *, error_text, max_attempts):
        captured["error_text"] = error_text
        captured["max_attempts"] = max_attempts

    monkeypatch.setattr(connector_jobs, "mark_job_failed", fake_mark_job_failed)

    handled = connector_jobs.dispatch_connector_job(
        session=SimpleNamespace(),
        job=fake_job,
        settings=test_settings,
        storage=storage,
    )

    assert handled is False
    assert "Unsupported job type for connector dispatcher" in captured["error_text"]
    assert captured["max_attempts"] == test_settings.worker_max_attempts


def test_process_next_job_handles_empty_success_and_failure(
    db_session,
    session_factory,
    test_settings,
    storage,
    monkeypatch,
):
    assert worker_main.process_next_job(
        settings=test_settings,
        session_factory=session_factory,
        dispatch_job=lambda **kwargs: True,
        storage=storage,
    ) is False

    stop_event = _FakeStopEvent()
    heartbeat_thread = _FakeThread()
    monkeypatch.setattr(
        worker_main,
        "_start_job_heartbeat",
        lambda **kwargs: (stop_event, heartbeat_thread),
    )

    enqueue_connector_run_job(
        db_session,
        source_name="manual_url",
        requested_by="pytest",
    )
    db_session.commit()

    def succeed(*, session, job, settings, storage):
        mark_job_succeeded(session, job)
        return True

    assert worker_main.process_next_job(
        settings=test_settings,
        session_factory=session_factory,
        dispatch_job=succeed,
        storage=storage,
    ) is True
    assert stop_event.was_set is True
    assert heartbeat_thread.join_timeout == 1

    enqueue_connector_run_job(
        db_session,
        source_name="manual_url",
        requested_by="pytest",
    )
    db_session.commit()

    assert worker_main.process_next_job(
        settings=test_settings,
        session_factory=session_factory,
        dispatch_job=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
        storage=storage,
    ) is False
    db_session.expire_all()
    failed = db_session.query(JobRun).order_by(JobRun.created_at.desc()).first()
    assert failed is not None
    assert failed.status == JobStatus.FAILED
    assert failed.error_text == "boom"


def test_worker_main_starts_metrics_and_process_loop(monkeypatch):
    settings = SimpleNamespace(
        database_url="sqlite://",
        database_echo=False,
        worker_metrics_port=19101,
        worker_id="worker-1",
        worker_poll_interval_seconds=7,
    )
    calls: dict[str, object] = {}

    monkeypatch.setattr(worker_main, "get_settings", lambda: settings)
    monkeypatch.setattr(
        worker_main,
        "configure_logging",
        lambda current: calls.setdefault("configured", current),
    )
    monkeypatch.setattr(worker_main, "get_session_factory", lambda *args: "session-factory")
    monkeypatch.setattr(worker_main, "build_storage", lambda current: "storage")
    monkeypatch.setattr(
        worker_main,
        "start_http_server",
        lambda port: calls.setdefault("port", port),
    )
    def fake_process_next_job(**kwargs):
        calls["process_args"] = kwargs
        return False

    monkeypatch.setattr(worker_main, "process_next_job", fake_process_next_job)
    monkeypatch.setattr(
        worker_main.time,
        "sleep",
        lambda seconds: (_ for _ in ()).throw(SystemExit(seconds)),
    )

    with pytest.raises(SystemExit) as excinfo:
        worker_main.main()

    assert excinfo.value.args[0] == 7
    assert calls["port"] == 19101
    assert calls["process_args"]["settings"] is settings
    assert calls["process_args"]["session_factory"] == "session-factory"
    assert calls["process_args"]["storage"] == "storage"


def test_scheduler_main_registers_interval_job(monkeypatch):
    settings = SimpleNamespace(
        database_url="sqlite://",
        database_echo=False,
        scheduler_poll_interval_seconds=90,
    )
    calls: dict[str, object] = {}

    class DummyScheduler:
        def __init__(self, *, timezone):
            calls["timezone"] = timezone

        def add_job(self, func, trigger, *, seconds, id, replace_existing, args):
            calls["job"] = {
                "func": func,
                "trigger": trigger,
                "seconds": seconds,
                "id": id,
                "replace_existing": replace_existing,
                "args": args,
            }

        def start(self):
            raise SystemExit("scheduler-stop")

    monkeypatch.setattr(scheduler_main, "get_settings", lambda: settings)
    monkeypatch.setattr(
        scheduler_main,
        "configure_logging",
        lambda current: calls.setdefault("configured", current),
    )
    monkeypatch.setattr(scheduler_main, "get_session_factory", lambda *args: "session-factory")
    monkeypatch.setattr(scheduler_main, "BlockingScheduler", DummyScheduler)

    with pytest.raises(SystemExit):
        scheduler_main.main()

    assert calls["timezone"] == "UTC"
    assert calls["job"]["func"] is scheduler_main.scheduler_tick
    assert calls["job"]["seconds"] == 90
    assert calls["job"]["id"] == "listing-refresh-enqueue"
    assert calls["job"]["args"] == ["session-factory"]


def test_api_main_health_ready_and_metrics_routes(client, monkeypatch):
    monkeypatch.setattr(api_main, "database_ready", lambda session_factory: False)
    degraded = client.get("/readyz")
    assert degraded.status_code == 503
    assert degraded.json() == {"status": "degraded"}

    monkeypatch.setattr(api_main, "database_ready", lambda session_factory: True)
    ready = client.get("/readyz")
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready"}

    monkeypatch.setattr(
        api_main,
        "metrics_response",
        lambda: Response("landintel_metric 1\n", media_type="text/plain"),
    )
    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert "landintel_metric 1" in metrics.text
    assert client.get("/healthz").json() == {"status": "ok"}


def test_resolve_request_actor_uses_header_and_cookie_and_rejects_invalid_tokens(
    test_settings,
    auth_headers,
):
    reviewer_request = _request(headers=auth_headers("reviewer"))
    reviewer_actor = resolve_request_actor(request=reviewer_request, settings=test_settings)
    assert reviewer_actor.role == AppRoleName.REVIEWER
    assert reviewer_actor.authenticated is True
    assert reviewer_actor.user_email == "reviewer@example.test"

    admin_cookie_request = _request(
        cookies={
            test_settings.web_auth_session_cookie_name: auth_headers("admin")[SESSION_HEADER_NAME]
        }
    )
    admin_actor = resolve_request_actor(request=admin_cookie_request, settings=test_settings)
    assert admin_actor.role == AppRoleName.ADMIN
    assert admin_actor.authenticated is True

    invalid_role_request = _request(
        headers={
            SESSION_HEADER_NAME: _signed_session_token(
                secret=test_settings.web_auth_session_secret,
                role="owner",
            )
        }
    )
    invalid_role_actor = resolve_request_actor(
        request=invalid_role_request,
        settings=test_settings,
    )
    assert invalid_role_actor.role == AppRoleName.ANALYST
    assert invalid_role_actor.authenticated is False
    assert invalid_role_actor.session_error == "INVALID_SESSION_ROLE"

    expired_request = _request(
        headers={
            SESSION_HEADER_NAME: _signed_session_token(
                secret=test_settings.web_auth_session_secret,
                role="reviewer",
                expires_at=datetime.now(UTC) - timedelta(minutes=1),
            )
        }
    )
    expired_actor = resolve_request_actor(request=expired_request, settings=test_settings)
    assert expired_actor.session_token_present is True
    assert expired_actor.session_error == "INVALID_OR_EXPIRED_SESSION"


def test_admin_model_release_routes_cover_rebuild_activate_retire_and_errors(
    client,
    seed_planning_data,
    seed_listing_sources,
    auth_headers,
):
    del seed_planning_data
    del seed_listing_sources

    rebuild = client.post(
        "/api/admin/model-releases/rebuild",
        json={"requested_by": "pytest", "auto_activate_hidden": False},
        headers=auth_headers("admin"),
    )
    assert rebuild.status_code == 200
    rebuild_payload = rebuild.json()
    assert rebuild_payload["total"] >= 3

    supported = next(
        item for item in rebuild_payload["items"] if item["template_key"] == "resi_5_9_full"
    )
    unsupported = next(
        item for item in rebuild_payload["items"] if item["template_key"] == "resi_1_4_full"
    )

    filtered = client.get(
        "/api/admin/model-releases?template_key=resi_5_9_full",
        headers=auth_headers("admin"),
    )
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1

    detail = client.get(
        f"/api/admin/model-releases/{supported['id']}",
        headers=auth_headers("admin"),
    )
    assert detail.status_code == 200
    assert detail.json()["id"] == supported["id"]

    not_ready = client.post(
        f"/api/admin/model-releases/{unsupported['id']}/activate",
        json={"requested_by": "pytest"},
        headers=auth_headers("admin"),
    )
    assert not_ready.status_code == 422

    activated = client.post(
        f"/api/admin/model-releases/{supported['id']}/activate",
        json={"requested_by": "pytest"},
        headers=auth_headers("admin"),
    )
    assert activated.status_code == 200
    assert activated.json()["status"] == "ACTIVE"
    assert activated.json()["active_scope_count"] == 1

    retired = client.post(
        f"/api/admin/model-releases/{supported['id']}/retire",
        json={"requested_by": "pytest"},
        headers=auth_headers("admin"),
    )
    assert retired.status_code == 200
    assert retired.json()["status"] == "RETIRED"

    phase_status = client.get("/api/admin/phase-status", headers=auth_headers("admin"))
    assert phase_status.status_code == 200
    assert phase_status.json()["spec_phase"] == "Phase 8A"

    sources = client.get("/api/admin/listing-sources", headers=auth_headers("admin"))
    assert sources.status_code == 200
    source_rows = sources.json()
    assert {row["name"] for row in source_rows} >= {
        "manual_url",
        "csv_import",
        "example_public_page",
    }
    example_public_page = next(row for row in source_rows if row["name"] == "example_public_page")
    assert example_public_page["refresh_policy_json"]["interval_hours"] == 24

    missing_release = client.get(
        f"/api/admin/model-releases/{uuid.uuid4()}",
        headers=auth_headers("admin"),
    )
    assert missing_release.status_code == 404

    missing_snapshot = client.get(
        f"/api/admin/source-snapshots/{uuid.uuid4()}",
        headers=auth_headers("admin"),
    )
    assert missing_snapshot.status_code == 404


def test_job_service_deduplicates_and_reuses_existing_jobs(db_session):
    first = enqueue_cluster_rebuild_job(db_session, requested_by="pytest")
    second = enqueue_cluster_rebuild_job(db_session, requested_by="pytest")
    assert first.id == second.id

    site_first = enqueue_site_build_job(
        db_session,
        cluster_id="cluster-1",
        requested_by="pytest",
    )
    site_second = enqueue_site_build_job(
        db_session,
        cluster_id="cluster-1",
        requested_by="pytest",
    )
    assert site_first.id == site_second.id

    connector_first = enqueue_connector_run_job(
        db_session,
        source_name="example_public_page",
        requested_by="pytest",
    )
    connector_second = enqueue_connector_run_job(
        db_session,
        source_name="example_public_page",
        requested_by="pytest",
    )
    assert connector_first.id == connector_second.id
