from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest
from landintel.domain.enums import JobStatus
from landintel.domain.schemas import SiteScenarioSuggestResponse

import services.worker.app.jobs.assessment as worker_assessment
import services.worker.app.jobs.planning_enrich as worker_planning
import services.worker.app.jobs.scenarios as worker_scenarios
import services.worker.app.jobs.site_build as worker_site_build
import services.worker.app.jobs.valuation as worker_valuation
import services.worker.app.main as worker_main


class _ContextFactory:
    def __init__(self, session):
        self._session = session

    def __call__(self):
        return self

    def __enter__(self):
        return self._session

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class _ExecuteResult:
    def __init__(self, *, site=None, sites=None):
        self._site = site
        self._sites = list(sites or [])

    def scalar_one_or_none(self):
        return self._site

    def scalars(self):
        return self

    def all(self):
        return list(self._sites)


class _Session:
    def __init__(self, *, execute_result=None, execute_results=None, get_result=None):
        self.execute_calls: list[object] = []
        self.get_calls: list[tuple[object, object]] = []
        self.execute_results = list(execute_results or [])
        if execute_result is not None:
            self.execute_results.append(execute_result)
        self.get_result = get_result
        self.commit_count = 0
        self.flush_count = 0

    def execute(self, stmt):
        self.execute_calls.append(stmt)
        if self.execute_results:
            return self.execute_results.pop(0)
        return _ExecuteResult()

    def get(self, model, identity):
        self.get_calls.append((model, identity))
        return self.get_result

    def commit(self):
        self.commit_count += 1

    def flush(self):
        self.flush_count += 1


class _HeartbeatEvent:
    def __init__(self, wait_results: list[bool]):
        self.wait_results = list(wait_results)
        self.wait_calls: list[object] = []
        self.was_set = False

    def wait(self, timeout):
        self.wait_calls.append(timeout)
        if self.wait_results:
            return self.wait_results.pop(0)
        return True

    def set(self):
        self.was_set = True


class _InlineThread:
    def __init__(self, *, target, name, daemon):
        self.target = target
        self.name = name
        self.daemon = daemon
        self.started = False
        self.join_timeout = None

    def start(self):
        self.started = True
        self.target()

    def join(self, timeout=None):
        self.join_timeout = timeout


class _StopEvent:
    def __init__(self):
        self.was_set = False

    def set(self):
        self.was_set = True


class _JoinThread:
    def __init__(self):
        self.join_timeout = None

    def join(self, timeout=None):
        self.join_timeout = timeout


def _job(*, payload=None, requested_by=None, status=JobStatus.RUNNING, job_id="job-1"):
    return SimpleNamespace(
        id=job_id,
        payload_json=dict(payload or {}),
        requested_by=requested_by,
        status=status,
    )


@pytest.mark.parametrize(
    ("wait_results", "expected_refresh_calls"),
    [
        ([True], 0),
        ([False], 1),
    ],
)
def test_start_job_heartbeat_stops_without_spinning(
    monkeypatch,
    wait_results,
    expected_refresh_calls,
):
    event = _HeartbeatEvent(wait_results=wait_results)
    thread = None
    refresh_calls: list[dict[str, object]] = []

    def fake_refresh_job_lock(session, *, job_id, worker_id):
        refresh_calls.append({"session": session, "job_id": job_id, "worker_id": worker_id})
        return False

    monkeypatch.setattr(worker_main.threading, "Event", lambda: event)
    monkeypatch.setattr(worker_main.threading, "Thread", _InlineThread)
    monkeypatch.setattr(worker_main, "refresh_job_lock", fake_refresh_job_lock)

    stop_event, thread = worker_main._start_job_heartbeat(
        settings=SimpleNamespace(worker_id="worker-1"),
        session_factory=_ContextFactory(_Session()),
        job_id="job-123",
    )

    assert isinstance(thread, _InlineThread)
    assert thread.started is True
    assert thread.name == "job-heartbeat-job-123"
    assert event.wait_calls == [worker_main.JOB_HEARTBEAT_INTERVAL_SECONDS]
    assert len(refresh_calls) == expected_refresh_calls
    assert stop_event.was_set is False


def test_process_next_job_does_not_mark_failed_after_status_changes(
    monkeypatch,
    test_settings,
):
    session = _Session()
    heartbeat_stop = _StopEvent()
    heartbeat_thread = _JoinThread()
    job = _job(job_id="job-9")

    def dispatch_job(*, session, job, settings, storage):
        job.status = JobStatus.SUCCEEDED
        raise RuntimeError("boom")

    mark_failed_calls: list[dict[str, object]] = []

    monkeypatch.setattr(worker_main, "claim_next_job", lambda **kwargs: job)
    monkeypatch.setattr(
        worker_main,
        "_start_job_heartbeat",
        lambda **kwargs: (heartbeat_stop, heartbeat_thread),
    )
    monkeypatch.setattr(
        worker_main,
        "mark_job_failed",
        lambda **kwargs: mark_failed_calls.append(kwargs),
    )

    handled = worker_main.process_next_job(
        settings=SimpleNamespace(worker_id=test_settings.worker_id, worker_max_attempts=5),
        session_factory=_ContextFactory(session),
        dispatch_job=dispatch_job,
        storage=object(),
    )

    assert handled is False
    assert session.commit_count == 2
    assert heartbeat_stop.was_set is True
    assert heartbeat_thread.join_timeout == 1
    assert mark_failed_calls == []


@pytest.mark.parametrize(
    ("function", "payload_key"),
    [
        (worker_assessment.run_assessment_feature_snapshot_build_job, "assessment_id"),
        (worker_assessment.run_comparable_retrieval_build_job, "assessment_id"),
    ],
)
def test_assessment_snapshot_workers_build_from_payload_and_flush(
    monkeypatch,
    function,
    payload_key,
):
    calls: list[dict[str, object]] = []
    session = _Session()
    assessment_id = "11111111-1111-1111-1111-111111111111"

    monkeypatch.setattr(
        worker_assessment,
        "build_assessment_artifacts_for_run",
        lambda **kwargs: calls.append(kwargs),
    )

    function(
        session=session,
        job=_job(payload={payload_key: assessment_id}, requested_by=""),
        storage="storage",
    )

    assert calls == [
        {
            "session": session,
            "assessment_run_id": UUID(assessment_id),
            "requested_by": "worker",
            "storage": "storage",
        }
    ]
    assert session.flush_count == 1


def test_assessment_refresh_workers_write_result_payload_and_flush(
    monkeypatch,
):
    summary = SimpleNamespace(total=4, positive=2, negative=1, excluded=1, censored=0)
    replay_summary = {"verified": 7, "failed": 0}
    session = _Session()

    monkeypatch.setattr(
        worker_assessment,
        "rebuild_historical_case_labels",
        lambda **kwargs: summary,
    )
    monkeypatch.setattr(
        worker_assessment,
        "replay_verify_all_assessments",
        lambda **kwargs: replay_summary,
    )

    historical_job = _job(payload={"seed": True}, requested_by="")
    worker_assessment.run_historical_label_rebuild_job(session=session, job=historical_job)
    assert historical_job.payload_json == {
        "seed": True,
        "result": {
            "total": 4,
            "positive": 2,
            "negative": 1,
            "excluded": 1,
            "censored": 0,
        },
    }

    gold_set_job = _job(payload={"seed": True}, requested_by="")
    worker_assessment.run_gold_set_refresh_job(session=session, job=gold_set_job)
    assert gold_set_job.payload_json == {
        "seed": True,
        "result": {
            "total": 4,
            "positive": 2,
            "negative": 1,
            "excluded": 1,
            "censored": 0,
        },
    }

    replay_job = _job(payload={"seed": True}, requested_by="pytest")
    worker_assessment.run_replay_verification_batch_job(
        session=session,
        job=replay_job,
        storage="storage",
    )
    assert replay_job.payload_json == {"seed": True, "result": replay_summary}
    assert session.flush_count == 3


def test_planning_ingest_jobs_use_fixture_defaults_and_optional_layers(
    monkeypatch,
):
    calls: list[tuple[str, str, object]] = []
    session = _Session()

    def recorder(name):
        def _record(*, session, storage, fixture_path, requested_by):
            calls.append((name, fixture_path.name, requested_by))

        return _record

    monkeypatch.setattr(worker_planning, "import_pld_fixture", recorder("pld"))
    monkeypatch.setattr(
        worker_planning,
        "import_borough_register_fixture",
        recorder("borough"),
    )
    monkeypatch.setattr(worker_planning, "import_brownfield_fixture", recorder("brownfield"))
    monkeypatch.setattr(worker_planning, "import_policy_area_fixture", recorder("policy"))
    monkeypatch.setattr(worker_planning, "import_constraint_fixture", recorder("constraint"))
    monkeypatch.setattr(worker_planning, "import_flood_fixture", recorder("flood"))
    monkeypatch.setattr(
        worker_planning,
        "import_heritage_article4_fixture",
        recorder("heritage"),
    )
    monkeypatch.setattr(worker_planning, "import_baseline_pack_fixture", recorder("baseline"))

    worker_planning.run_pld_ingest_job(session=session, job=_job(requested_by=""), storage="s3")
    assert calls == [("pld", "pld_applications.json", "worker")]

    calls.clear()
    worker_planning.run_borough_register_ingest_job(
        session=session,
        job=_job(requested_by="", payload={"include_supporting_layers": False}),
        storage="s3",
    )
    assert calls == [("borough", "borough_register_camden.json", "worker")]

    calls.clear()
    worker_planning.run_borough_register_ingest_job(
        session=session,
        job=_job(requested_by="pytest"),
        storage="s3",
    )
    assert calls == [
        ("borough", "borough_register_camden.json", "pytest"),
        ("brownfield", "brownfield_sites.geojson", "pytest"),
        ("policy", "policy_areas.geojson", "pytest"),
        ("constraint", "constraint_features.geojson", "pytest"),
        ("flood", "flood_zones.geojson", "pytest"),
        ("heritage", "heritage_article4.geojson", "pytest"),
        ("baseline", "baseline_packs.json", "pytest"),
    ]


def test_planning_refresh_jobs_cover_success_and_missing_site(monkeypatch):
    site = SimpleNamespace(id="site-1")
    planning_calls: list[dict[str, object]] = []
    audit_calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        worker_planning,
        "refresh_site_planning_context",
        lambda **kwargs: planning_calls.append(kwargs),
    )
    monkeypatch.setattr(
        worker_planning,
        "evaluate_site_extant_permission",
        lambda **kwargs: {"status": "PASS"},
    )
    monkeypatch.setattr(
        worker_planning,
        "audit_extant_permission_check",
        lambda **kwargs: audit_calls.append(kwargs),
    )

    planning_session = _Session(execute_result=_ExecuteResult(site=site))
    worker_planning.run_site_planning_enrich_job(
        session=planning_session,
        job=_job(payload={"site_id": "11111111-1111-1111-1111-111111111111"}, requested_by=""),
    )
    assert planning_calls[0]["site"] is site
    assert planning_calls[0]["requested_by"] == "worker"
    assert planning_session.flush_count == 1

    extant_session = _Session(execute_result=_ExecuteResult(site=site))
    worker_planning.run_site_extant_permission_recheck_job(
        session=extant_session,
        job=_job(
            payload={"site_id": "11111111-1111-1111-1111-111111111111"}, requested_by="pytest"
        ),
    )
    assert planning_calls[1]["site"] is site
    assert audit_calls[0]["site"] is site
    assert audit_calls[0]["result"] == {"status": "PASS"}
    assert extant_session.flush_count == 1

    site_two = SimpleNamespace(id="site-2")
    borough_session = _Session(execute_result=_ExecuteResult(sites=[site, site_two]))
    refresh_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        worker_planning,
        "refresh_site_planning_context",
        lambda **kwargs: refresh_calls.append(kwargs),
    )
    worker_planning.run_source_coverage_refresh_job(
        session=borough_session,
        job=_job(payload={"borough_id": "camden"}, requested_by=""),
    )
    assert [call["site"] for call in refresh_calls] == [site, site_two]
    assert borough_session.flush_count == 1

    all_session = _Session(execute_result=_ExecuteResult(sites=[site]))
    refresh_calls.clear()
    worker_planning.run_source_coverage_refresh_job(
        session=all_session,
        job=_job(payload={}, requested_by=""),
    )
    assert [call["site"] for call in refresh_calls] == [site]
    assert all_session.flush_count == 1

    missing_session = _Session(execute_result=_ExecuteResult(site=None))
    with pytest.raises(worker_planning.SiteBuildError):
        worker_planning.run_site_planning_enrich_job(
            session=missing_session,
            job=_job(payload={"site_id": "11111111-1111-1111-1111-111111111111"}),
        )


def test_scenario_workers_cover_success_paths_and_missing_records(monkeypatch):
    site = SimpleNamespace(id="site-1")
    scenario = SimpleNamespace(id="scenario-1")
    suggest_calls: list[dict[str, object]] = []
    stale_calls: list[dict[str, object]] = []
    rulepack_calls: list[dict[str, object]] = []
    evidence_calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        worker_scenarios,
        "suggest_scenarios_for_site",
        lambda **kwargs: (
            suggest_calls.append(kwargs)
            or SiteScenarioSuggestResponse(
                site_id=UUID("11111111-1111-1111-1111-111111111111"),
                headline_scenario_id=None,
                items=[],
                excluded_templates=[],
            )
        ),
    )
    monkeypatch.setattr(
        worker_scenarios,
        "mark_site_scenarios_stale_for_geometry_change",
        lambda **kwargs: stale_calls.append(kwargs),
    )
    monkeypatch.setattr(
        worker_scenarios,
        "refresh_site_scenarios_after_rulepack_change",
        lambda **kwargs: rulepack_calls.append(kwargs),
    )
    monkeypatch.setattr(
        worker_scenarios,
        "refresh_scenario_evidence",
        lambda **kwargs: evidence_calls.append(kwargs),
    )

    suggest_session = _Session(execute_result=_ExecuteResult(site=site))
    worker_scenarios.run_site_scenario_suggest_refresh_job(
        session=suggest_session,
        job=_job(
            payload={
                "site_id": "11111111-1111-1111-1111-111111111111",
                "template_keys": ["resi_5_9_full", "", 7],
                "manual_seed": 1,
            },
            requested_by="",
        ),
        storage=object(),
    )
    assert suggest_calls == [
        {
            "session": suggest_session,
            "site_id": UUID("11111111-1111-1111-1111-111111111111"),
            "requested_by": "worker",
            "template_keys": ["resi_5_9_full", "7"],
            "manual_seed": True,
        }
    ]
    assert suggest_session.flush_count == 1

    geometry_session = _Session(execute_result=_ExecuteResult(site=site))
    worker_scenarios.run_site_scenario_geometry_refresh_job(
        session=geometry_session,
        job=_job(payload={"site_id": "11111111-1111-1111-1111-111111111111"}, requested_by=""),
    )
    assert stale_calls == [
        {
            "session": geometry_session,
            "site": site,
            "requested_by": "worker",
        }
    ]
    assert geometry_session.flush_count == 1

    site_two = SimpleNamespace(id="site-2")
    borough_session = _Session(execute_result=_ExecuteResult(sites=[site, site_two]))
    worker_scenarios.run_borough_rulepack_scenario_refresh_job(
        session=borough_session,
        job=_job(payload={"borough_id": "camden"}, requested_by="pytest"),
    )
    assert [call["site"] for call in rulepack_calls] == [site, site_two]
    assert borough_session.flush_count == 1

    evidence_session = _Session(get_result=scenario)
    worker_scenarios.run_scenario_evidence_refresh_job(
        session=evidence_session,
        job=_job(payload={"scenario_id": "22222222-2222-2222-2222-222222222222"}, requested_by=""),
    )
    assert evidence_calls == [{"session": evidence_session, "scenario": scenario}]
    assert evidence_session.flush_count == 1

    missing_site_session = _Session(execute_result=_ExecuteResult(site=None))
    with pytest.raises(worker_scenarios.SiteBuildError):
        worker_scenarios.run_site_scenario_geometry_refresh_job(
            session=missing_site_session,
            job=_job(payload={"site_id": "11111111-1111-1111-1111-111111111111"}),
        )

    missing_scenario_session = _Session(get_result=None)
    with pytest.raises(worker_scenarios.ScenarioNormalizeError):
        worker_scenarios.run_scenario_evidence_refresh_job(
            session=missing_scenario_session,
            job=_job(payload={"scenario_id": "22222222-2222-2222-2222-222222222222"}),
        )


def test_site_build_refresh_jobs_cover_success_and_missing_site(monkeypatch):
    site = SimpleNamespace(id="site-1")
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        worker_site_build,
        "build_or_refresh_site_from_cluster",
        lambda **kwargs: (calls.append(kwargs) or site),
    )
    monkeypatch.setattr(
        worker_site_build,
        "refresh_site_links_and_status",
        lambda **kwargs: calls.append(kwargs),
    )
    monkeypatch.setattr(
        worker_site_build,
        "enqueue_site_scenario_suggest_refresh_job",
        lambda **kwargs: calls.append(kwargs),
    )

    build_session = _Session(execute_result=_ExecuteResult(site=site))
    worker_site_build.run_site_build_job(
        session=build_session,
        job=_job(
            payload={"cluster_id": "33333333-3333-3333-3333-333333333333"},
            requested_by="",
        ),
    )
    assert calls[0] == {
        "session": build_session,
        "cluster_id": UUID("33333333-3333-3333-3333-333333333333"),
        "requested_by": "worker",
    }
    assert calls[1] == {
        "session": build_session,
        "site_id": "site-1",
        "requested_by": "worker",
    }

    lpa_session = _Session(execute_result=_ExecuteResult(site=site))
    worker_site_build.run_site_lpa_refresh_job(
        session=lpa_session,
        job=_job(payload={"site_id": "11111111-1111-1111-1111-111111111111"}, requested_by=""),
    )
    assert calls[2] == {
        "session": lpa_session,
        "site": site,
    }
    assert lpa_session.flush_count == 1

    title_session = _Session(execute_result=_ExecuteResult(site=site))
    worker_site_build.run_site_title_refresh_job(
        session=title_session,
        job=_job(
            payload={"site_id": "11111111-1111-1111-1111-111111111111"}, requested_by="pytest"
        ),
    )
    assert calls[3] == {
        "session": title_session,
        "site": site,
    }
    assert title_session.flush_count == 1

    missing_site_session = _Session(execute_result=_ExecuteResult(site=None))
    with pytest.raises(worker_site_build.SiteBuildError):
        worker_site_build.run_site_lpa_refresh_job(
            session=missing_site_session,
            job=_job(payload={"site_id": "11111111-1111-1111-1111-111111111111"}),
        )


@pytest.mark.parametrize(
    ("dataset", "expected_keys"),
    [
        ("all", {"assumption_set_version", "hmlr_price_paid", "ukhpi", "land_comps"}),
        ("assumptions", {"assumption_set_version"}),
    ],
)
def test_valuation_data_refresh_job_records_selected_datasets(monkeypatch, dataset, expected_keys):
    session = _Session()
    calls: list[tuple[str, dict[str, object]]] = []

    def assumption_set(session):
        calls.append(("assumptions", {}))
        return SimpleNamespace(version="v1")

    def recorder(name):
        def _record(*, session, storage, fixture_path, requested_by):
            summary = SimpleNamespace(
                source_snapshot_id=f"{name}-snapshot",
                raw_asset_id=f"{name}-raw",
                imported_count=len(name),
            )
            calls.append(
                (
                    name,
                    {
                        "fixture": fixture_path.name,
                        "requested_by": requested_by,
                    },
                )
            )
            return summary

        return _record

    monkeypatch.setattr(worker_valuation, "ensure_default_assumption_set", assumption_set)
    monkeypatch.setattr(
        worker_valuation,
        "import_hmlr_price_paid_fixture",
        recorder("hmlr_price_paid"),
    )
    monkeypatch.setattr(worker_valuation, "import_ukhpi_fixture", recorder("ukhpi"))
    monkeypatch.setattr(worker_valuation, "import_land_comp_fixture", recorder("land_comps"))

    job = _job(payload={"dataset": dataset}, requested_by="")
    worker_valuation.run_valuation_data_refresh_job(session=session, job=job, storage="storage")

    result = job.payload_json["result"]
    assert result["dataset"] == dataset
    assert set(result.keys()) == {"dataset", *expected_keys}
    assert result.get("assumption_set_version") == (
        "v1" if dataset in {"all", "assumptions"} else None
    )
    assert session.flush_count == 1

    if dataset == "all":
        assert calls == [
            ("assumptions", {}),
            (
                "hmlr_price_paid",
                {"fixture": "hmlr_price_paid_london.json", "requested_by": "worker"},
            ),
            ("ukhpi", {"fixture": "ukhpi_london.json", "requested_by": "worker"}),
            ("land_comps", {"fixture": "land_comps_london.json", "requested_by": "worker"}),
        ]
    else:
        assert calls == [("assumptions", {})]


def test_valuation_run_build_job_uses_assessment_id_and_worker_default(monkeypatch):
    session = _Session()
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        worker_valuation,
        "build_assessment_artifacts_for_run",
        lambda **kwargs: calls.append(kwargs),
    )

    worker_valuation.run_valuation_run_build_job(
        session=session,
        job=_job(
            payload={"assessment_id": "44444444-4444-4444-4444-444444444444"}, requested_by=""
        ),
        storage="storage",
    )

    assert calls == [
        {
            "session": session,
            "assessment_run_id": UUID("44444444-4444-4444-4444-444444444444"),
            "requested_by": "worker",
            "storage": "storage",
        }
    ]
    assert session.flush_count == 1
