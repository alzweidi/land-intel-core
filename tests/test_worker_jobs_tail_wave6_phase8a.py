from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from landintel.domain.enums import JobType
from landintel.jobs import service as job_service

import services.worker.app.jobs.valuation as worker_valuation
import services.worker.app.main as worker_main


class _ExitLoop(Exception):
    pass


class _Result:
    def __init__(self, *, items=None, scalar=None):
        self._items = list(items or [])
        self._scalar = scalar

    def scalars(self):
        return self

    def scalar_one(self):
        return self._scalar

    def scalar_one_or_none(self):
        return self._scalar

    def all(self):
        return list(self._items)


class _QueueSession:
    def __init__(self, results=None):
        self._results = list(results or [])
        self.commit_count = 0

    def execute(self, stmt):
        del stmt
        if self._results:
            return self._results.pop(0)
        return _Result(items=[])

    def commit(self):
        self.commit_count += 1


class _ContextFactory:
    def __init__(self, session):
        self._session = session

    def __call__(self):
        return self

    def __enter__(self):
        return self._session

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class _FakeThread:
    def __init__(self, *, target, name, daemon):
        self.target = target
        self.name = name
        self.daemon = daemon
        self.join_timeout = None

    def start(self):
        self.target()

    def join(self, timeout=None):
        self.join_timeout = timeout


def test_job_enqueue_helpers_cover_optional_payload_variants_and_dedupe(db_session):
    site_job = job_service.enqueue_site_scenario_suggest_refresh_job(
        db_session,
        site_id="site-1",
        requested_by="pytest",
        template_keys=["alpha", "beta"],
        manual_seed=True,
    )
    repeat_site_job = job_service.enqueue_site_scenario_suggest_refresh_job(
        db_session,
        site_id="site-1",
        requested_by="pytest",
        template_keys=["alpha", "beta"],
        manual_seed=True,
    )
    coverage_job = job_service.enqueue_source_coverage_refresh_job(
        db_session,
        borough_id="camden",
        requested_by="pytest",
    )
    borough_job = job_service.enqueue_borough_register_ingest_job(
        db_session,
        fixture_path="/fixtures/borough.json",
        requested_by="pytest",
        include_supporting_layers=False,
    )
    pld_job = job_service.enqueue_pld_ingest_job(
        db_session,
        fixture_path="/fixtures/pld.json",
        requested_by="pytest",
    )

    assert site_job.id == repeat_site_job.id
    assert site_job.job_type == JobType.SITE_SCENARIO_SUGGEST_REFRESH
    assert site_job.payload_json["template_keys"] == ["alpha", "beta"]
    assert site_job.payload_json["manual_seed"] is True
    assert coverage_job.payload_json == {
        "borough_id": "camden",
        "dedupe_key": "borough:camden",
    }
    default_coverage_job = job_service.enqueue_source_coverage_refresh_job(
        db_session,
        borough_id=None,
        requested_by="pytest",
    )
    assert borough_job.payload_json == {
        "include_supporting_layers": False,
        "fixture_path": "/fixtures/borough.json",
        "dedupe_key": "fixture:/fixtures/borough.json",
    }
    default_borough_job = job_service.enqueue_borough_register_ingest_job(
        db_session,
        requested_by="pytest",
    )
    assert pld_job.payload_json == {
        "fixture_path": "/fixtures/pld.json",
        "dedupe_key": "fixture:/fixtures/pld.json",
    }
    assert default_coverage_job.payload_json == {"dedupe_key": "borough:all"}
    assert default_borough_job.payload_json == {
        "include_supporting_layers": True,
        "dedupe_key": "fixture:default-borough-register",
    }


def test_run_valuation_data_refresh_job_covers_assumptions_only_dataset(monkeypatch):
    session = SimpleNamespace(
        flush_count=0,
        flush=lambda: setattr(session, "flush_count", session.flush_count + 1),
    )
    job = SimpleNamespace(payload_json={"dataset": "assumptions"}, requested_by=None)
    import_calls = []
    monkeypatch.setattr(
        worker_valuation,
        "ensure_default_assumption_set",
        lambda session: SimpleNamespace(version="v-default"),
    )
    monkeypatch.setattr(
        worker_valuation,
        "import_hmlr_price_paid_fixture",
        lambda **kwargs: import_calls.append(("hmlr", kwargs)),
    )
    monkeypatch.setattr(
        worker_valuation,
        "import_ukhpi_fixture",
        lambda **kwargs: import_calls.append(("ukhpi", kwargs)),
    )
    monkeypatch.setattr(
        worker_valuation,
        "import_land_comp_fixture",
        lambda **kwargs: import_calls.append(("land", kwargs)),
    )

    worker_valuation.run_valuation_data_refresh_job(session=session, job=job, storage=object())

    assert session.flush_count == 1
    assert job.payload_json["result"] == {
        "dataset": "assumptions",
        "assumption_set_version": "v-default",
    }
    assert import_calls == []


def test_start_job_heartbeat_stops_when_refresh_fails(monkeypatch):
    session = SimpleNamespace(
        commit_count=0,
        commit=lambda: setattr(session, "commit_count", session.commit_count + 1),
    )
    refresh_calls = []
    job_id = uuid.uuid4()

    monkeypatch.setattr(worker_main, "JOB_HEARTBEAT_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(worker_main.threading, "Thread", _FakeThread)
    monkeypatch.setattr(
        worker_main,
        "refresh_job_lock",
        lambda session, *, job_id, worker_id: refresh_calls.append((job_id, worker_id)) or False,
    )

    stop_event, thread = worker_main._start_job_heartbeat(
        settings=SimpleNamespace(worker_id="worker-1"),
        session_factory=_ContextFactory(session),
        job_id=job_id,
    )

    assert refresh_calls == [(job_id, "worker-1")]
    assert session.commit_count == 1
    assert stop_event.is_set() is False
    assert thread.name == f"job-heartbeat-{job_id}"


def test_start_job_heartbeat_runs_one_refresh_cycle_before_stop(monkeypatch):
    class _HeartbeatEvent:
        def __init__(self):
            self.wait_calls = 0
            self.set_called = False

        def wait(self, timeout):
            del timeout
            self.wait_calls += 1
            return self.wait_calls > 1

        def set(self):
            self.set_called = True

    session = SimpleNamespace(
        commit_count=0,
        commit=lambda: setattr(session, "commit_count", session.commit_count + 1),
    )
    refresh_calls = []
    job_id = uuid.uuid4()

    monkeypatch.setattr(worker_main, "JOB_HEARTBEAT_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(worker_main.threading, "Thread", _FakeThread)
    monkeypatch.setattr(worker_main.threading, "Event", _HeartbeatEvent)

    def fake_refresh_job_lock(session, *, job_id, worker_id):
        refresh_calls.append((job_id, worker_id))
        return True

    monkeypatch.setattr(worker_main, "refresh_job_lock", fake_refresh_job_lock)

    stop_event, thread = worker_main._start_job_heartbeat(
        settings=SimpleNamespace(worker_id="worker-1"),
        session_factory=_ContextFactory(session),
        job_id=job_id,
    )

    assert refresh_calls == [(job_id, "worker-1")]
    assert session.commit_count == 1
    assert stop_event.wait_calls == 2
    assert stop_event.set_called is False
    assert thread.name == f"job-heartbeat-{job_id}"


def test_worker_main_sleeps_when_idle(monkeypatch):
    settings = SimpleNamespace(
        database_url="sqlite://",
        database_echo=False,
        worker_id="worker-1",
        worker_metrics_port=9999,
        worker_poll_interval_seconds=7,
    )
    process_calls = []
    sleep_calls = []

    monkeypatch.setattr(worker_main, "get_settings", lambda: settings)
    monkeypatch.setattr(worker_main, "configure_logging", lambda settings: None)
    monkeypatch.setattr(worker_main, "get_session_factory", lambda *args, **kwargs: object())
    monkeypatch.setattr(worker_main, "build_storage", lambda settings: object())
    monkeypatch.setattr(worker_main, "start_http_server", lambda port: None)
    monkeypatch.setattr(
        worker_main,
        "process_next_job",
        lambda **kwargs: process_calls.append(kwargs) or False,
    )
    monkeypatch.setattr(worker_main, "WORKER_LOOP_COUNT", SimpleNamespace(inc=lambda: None))

    def fake_sleep(seconds):
        sleep_calls.append(seconds)
        raise _ExitLoop

    monkeypatch.setattr(worker_main.time, "sleep", fake_sleep)

    with pytest.raises(_ExitLoop):
        worker_main.main()

    assert len(process_calls) == 1
    assert sleep_calls == [7]


def test_worker_main_continues_without_sleep_when_job_handled(monkeypatch):
    settings = SimpleNamespace(
        database_url="sqlite://",
        database_echo=False,
        worker_id="worker-1",
        worker_metrics_port=9999,
        worker_poll_interval_seconds=7,
    )
    process_calls = []

    monkeypatch.setattr(worker_main, "get_settings", lambda: settings)
    monkeypatch.setattr(worker_main, "configure_logging", lambda settings: None)
    monkeypatch.setattr(worker_main, "get_session_factory", lambda *args, **kwargs: object())
    monkeypatch.setattr(worker_main, "build_storage", lambda settings: object())
    monkeypatch.setattr(worker_main, "start_http_server", lambda port: None)
    monkeypatch.setattr(worker_main, "WORKER_LOOP_COUNT", SimpleNamespace(inc=lambda: None))

    def fail_sleep(seconds):
        del seconds
        raise AssertionError("sleep should not run when job is handled")

    monkeypatch.setattr(worker_main.time, "sleep", fail_sleep)

    def fake_process_next_job(**kwargs):
        process_calls.append(kwargs)
        if len(process_calls) == 1:
            return True
        raise _ExitLoop

    monkeypatch.setattr(worker_main, "process_next_job", fake_process_next_job)

    with pytest.raises(_ExitLoop):
        worker_main.main()

    assert len(process_calls) == 2
