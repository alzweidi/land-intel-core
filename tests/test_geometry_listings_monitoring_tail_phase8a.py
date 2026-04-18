from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest
from landintel.domain.enums import (
    GeomConfidence,
    GeomSourceType,
    JobStatus,
    ListingClusterStatus,
    ListingStatus,
    ListingType,
    ModelReleaseStatus,
    PriceBasisType,
)
from landintel.geospatial import geometry as geometry_service
from landintel.geospatial import title_linkage as title_service
from landintel.listings import clustering as clustering_service
from landintel.listings import parsing as parsing_service
from landintel.monitoring import health as health_service
from shapely.geometry import GeometryCollection, Point, Polygon, box

import services.scheduler.app.main as scheduler_main
import services.worker.app.jobs.valuation as worker_valuation
import services.worker.app.main as worker_main


class _Result:
    def __init__(self, *, items=None, scalar=None, rows=None):
        self._items = list(items or [])
        self._scalar = scalar
        self._rows = list(rows or [])

    def scalars(self):
        return self

    def scalar_one(self):
        return self._scalar

    def scalar_one_or_none(self):
        return self._scalar

    def unique(self):
        return self

    def all(self):
        return list(self._items if self._items else self._rows)


class _QueueSession:
    def __init__(self, results=None):
        self._results = list(results or [])
        self.commit_count = 0
        self.executed = []

    def execute(self, stmt):
        self.executed.append(stmt)
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


def _title_polygon(*, title_number: str, address: str | None, geom) -> SimpleNamespace:
    return SimpleNamespace(
        title_number=title_number,
        normalized_address=address,
        geom_27700=geom.wkt,
    )


def test_geometry_normalization_helpers_cover_repair_collection_and_status_branches() -> None:
    with pytest.raises(geometry_service.GeometryNormalizationError):
        geometry_service.load_geojson_geometry({"type": "GeometryCollection", "geometries": []})

    with pytest.raises(geometry_service.GeometryNormalizationError):
        geometry_service.load_wkt_geometry("GEOMETRYCOLLECTION EMPTY")

    geom = box(0, 0, 10, 10)
    assert (
        geometry_service.transform_geometry(
            geom,
            from_epsg=geometry_service.CANONICAL_EPSG,
            to_epsg=geometry_service.CANONICAL_EPSG,
        )
        is geom
    )

    repaired = geometry_service.normalize_input_geometry(
        geometry=Polygon([(0, 0), (10, 10), (0, 10), (10, 0), (0, 0)]),
        source_epsg=geometry_service.CANONICAL_EPSG,
        source_type=GeomSourceType.SOURCE_POLYGON,
        confidence=GeomConfidence.HIGH,
    )
    assert repaired.geom_confidence == GeomConfidence.HIGH
    assert repaired.area_sqm > 0
    assert any(item.code == "GEOMETRY_REPAIRED" for item in repaired.warnings)

    collapsed = geometry_service.normalize_input_geometry(
        geometry=GeometryCollection([box(0, 0, 4, 4), Point(10, 10)]),
        source_epsg=geometry_service.CANONICAL_EPSG,
        source_type=GeomSourceType.SOURCE_POLYGON,
    )
    assert collapsed.geom_27700.geom_type == "Polygon"
    assert collapsed.warnings == []

    assert (
        geometry_service.derive_geom_confidence(
            source_type=GeomSourceType.POINT_ONLY,
            geometry_27700=Point(1, 1),
        )
        == GeomConfidence.INSUFFICIENT
    )
    assert (
        geometry_service.derive_geom_confidence(
            source_type=GeomSourceType.APPROXIMATE_BBOX,
            geometry_27700=box(0, 0, 1, 1),
        )
        == GeomConfidence.LOW
    )
    assert (
        geometry_service.derive_site_status(
            geom_confidence=GeomConfidence.INSUFFICIENT,
            manual_review_required=False,
        )
        == geometry_service.SiteStatus.INSUFFICIENT_GEOMETRY
    )
    assert (
        geometry_service.derive_site_status(
            geom_confidence=GeomConfidence.LOW,
            manual_review_required=False,
        )
        == geometry_service.SiteStatus.MANUAL_REVIEW
    )
    assert (
        geometry_service.derive_site_status(
            geom_confidence=GeomConfidence.HIGH,
            manual_review_required=False,
        )
        == geometry_service.SiteStatus.ACTIVE
    )


def test_title_linkage_helpers_cover_candidates_union_and_overlap_confidence() -> None:
    title_a = _title_polygon(
        title_number="T-001",
        address="12 example road london nw1",
        geom=box(0, 0, 10, 10),
    )
    title_b = _title_polygon(
        title_number="T-002",
        address="12 example road",
        geom=box(20, 0, 30, 10),
    )
    title_c = _title_polygon(
        title_number="T-003",
        address="irrelevant",
        geom=box(40, 0, 50, 10),
    )

    candidates = title_service.select_title_candidates(
        title_polygons=[title_c, title_b, title_a],
        normalized_addresses=["12 example road london nw1", "unused"],
        point_geometries_27700=[Point(5, 5)],
    )

    assert [candidate.title_polygon.title_number for candidate in candidates] == [
        "T-001",
        "T-002",
    ]
    assert candidates[0].score == 1.0
    assert "listing_address_exact_title_address" in candidates[0].reasons
    assert "listing_point_intersects_title" in candidates[0].reasons
    assert candidates[1].score == 0.8
    assert "listing_address_partial_title_address" in candidates[1].reasons
    assert title_service.build_title_union_geometry([]) is None

    union_geometry = title_service.build_title_union_geometry(candidates)
    assert union_geometry is not None
    assert union_geometry.geom_confidence == GeomConfidence.MEDIUM

    overlaps = title_service.compute_title_overlaps(
        site_geometry_27700=box(0, 0, 10, 10),
        title_polygons=[
            _title_polygon(title_number="T-100", address=None, geom=box(0, 0, 10, 10)),
            _title_polygon(title_number="T-200", address=None, geom=box(5, 0, 15, 10)),
            _title_polygon(title_number="T-300", address=None, geom=box(9, 0, 19, 10)),
            _title_polygon(title_number="T-400", address=None, geom=box(20, 0, 30, 10)),
        ],
    )
    assert [item.title_polygon.title_number for item in overlaps] == [
        "T-100",
        "T-200",
        "T-300",
    ]
    assert [item.confidence for item in overlaps] == [
        GeomConfidence.HIGH,
        GeomConfidence.MEDIUM,
        GeomConfidence.LOW,
    ]

    point_overlap = title_service.compute_title_overlaps(
        site_geometry_27700=Point(2, 2),
        title_polygons=[_title_polygon(title_number="T-500", address=None, geom=box(0, 0, 10, 10))],
    )
    assert point_overlap[0].overlap_pct == 1.0
    assert point_overlap[0].overlap_sqm == 0.0
    assert point_overlap[0].confidence == GeomConfidence.HIGH


def test_listing_clustering_builds_expected_clusters_and_edge_reasons() -> None:
    a = clustering_service.ClusterListingInput(
        listing_item_id=uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        canonical_url="https://example.com/a",
        normalized_address="12 example road london",
        headline="Camden Yard Site",
        guide_price_gbp=1_000_000,
        lat=51.50,
        lon=-0.10,
        document_hashes=("hash-a",),
    )
    b = clustering_service.ClusterListingInput(
        listing_item_id=uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        canonical_url="https://example.com/a",
        normalized_address="44 rye lane london",
        headline="Different Listing",
        guide_price_gbp=2_000_000,
        lat=51.60,
        lon=-0.20,
        document_hashes=("hash-b",),
    )
    c = clustering_service.ClusterListingInput(
        listing_item_id=uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
        canonical_url="https://example.com/c",
        normalized_address="22 example road london",
        headline="Shared Hash Listing",
        guide_price_gbp=1_500_000,
        lat=51.40,
        lon=-0.11,
        document_hashes=("shared",),
    )
    d = clustering_service.ClusterListingInput(
        listing_item_id=uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd"),
        canonical_url="https://example.org/d",
        normalized_address="55 other road london",
        headline="Shared Hash Listing Variant",
        guide_price_gbp=1_600_000,
        lat=51.41,
        lon=-0.12,
        document_hashes=("shared",),
    )
    e = clustering_service.ClusterListingInput(
        listing_item_id=uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"),
        canonical_url="https://example.net/e",
        normalized_address="66 example road london",
        headline="Camden Yard Site",
        guide_price_gbp=1_200_000,
        lat=51.51,
        lon=-0.101,
        document_hashes=("hash-e",),
    )
    f = clustering_service.ClusterListingInput(
        listing_item_id=uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"),
        canonical_url="https://example.net/f",
        normalized_address="66 example road london",
        headline="Camden Yard Site London",
        guide_price_gbp=1_245_000,
        lat=51.5101,
        lon=-0.1011,
        document_hashes=("hash-f",),
    )
    g = clustering_service.ClusterListingInput(
        listing_item_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        canonical_url="https://example.org/g",
        normalized_address="single listing",
        headline="Singleton",
        guide_price_gbp=None,
        lat=None,
        lon=None,
        document_hashes=(),
    )

    results = clustering_service.build_clusters([g, d, a, f, c, b, e])

    assert len(results) == 4
    singleton = next(
        cluster for cluster in results if cluster.cluster_status == ListingClusterStatus.SINGLETON
    )
    assert singleton.members[0].reasons == ["singleton"]

    paired = [
        cluster for cluster in results if cluster.cluster_status == ListingClusterStatus.ACTIVE
    ]
    assert {len(cluster.members) for cluster in paired} == {2}
    canonical_pair = next(
        cluster
        for cluster in paired
        if {member.listing_item_id for member in cluster.members}
        == {a.listing_item_id, b.listing_item_id}
    )
    assert {member.confidence for member in canonical_pair.members} == {0.995}
    assert any("canonical_url_exact" in member.reasons for member in canonical_pair.members)
    hash_pair = next(
        cluster
        for cluster in paired
        if {member.listing_item_id for member in cluster.members}
        == {c.listing_item_id, d.listing_item_id}
    )
    assert {member.confidence for member in hash_pair.members} == {0.98}
    assert any("document_hash_exact" in member.reasons for member in hash_pair.members)
    address_pair = next(
        cluster
        for cluster in paired
        if {member.listing_item_id for member in cluster.members}
        == {e.listing_item_id, f.listing_item_id}
    )
    assert max(member.confidence for member in address_pair.members) == 0.995
    assert any("normalized_address_exact" in member.reasons for member in address_pair.members)


def test_parsing_helpers_cover_normalization_price_date_status_and_coordinates() -> None:
    assert parsing_service.normalize_space(["  Camden", "Yard  "]) == "Camden, Yard"
    assert parsing_service.normalize_space("  one   two  ") == "one two"
    assert (
        parsing_service.normalize_url("https://example.com/listing/?a=1#section")
        == "https://example.com/listing/?a=1"
    )
    assert (
        parsing_service.normalize_address("12 Example Rd., London N1")
        == "12 example road london n1"
    )
    assert parsing_service.build_search_text("one", None, "two") == "one two"
    assert (
        parsing_service.extract_text_content(
            "<html><head><style>.x{}</style><script>bad()</script></head>"
            "<body> Hello  world </body></html>"
        )
        == "Hello world"
    )
    assert parsing_service.parse_price("Guide price £1.25m") == (
        1_250_000,
        PriceBasisType.GUIDE_PRICE,
    )
    assert parsing_service.parse_price("Offers in excess of £900k") == (
        900_000,
        PriceBasisType.OFFERS_IN_EXCESS_OF,
    )
    assert parsing_service.parse_price("POA") == (None, PriceBasisType.PRICE_ON_APPLICATION)
    assert (
        parsing_service.detect_price_basis("Guide price for auction")
        == PriceBasisType.AUCTION_GUIDE
    )
    assert parsing_service.parse_optional_date("Viewing 1 Jan 2024") == date(2024, 1, 1)
    assert parsing_service.parse_optional_date("Viewing 31 Feb 2024") is None
    assert parsing_service.detect_listing_status("Sold STC") == ListingStatus.SOLD_STC
    assert parsing_service.detect_listing_status("Under offer") == ListingStatus.UNDER_OFFER
    assert parsing_service.detect_listing_type("Garage court") == ListingType.GARAGE_COURT
    assert (
        parsing_service.detect_listing_type("Development opportunity")
        == ListingType.REDEVELOPMENT_SITE
    )
    assert parsing_service.detect_listing_type("plain house") == ListingType.UNKNOWN
    assert parsing_service.extract_coordinates_from_text("51.5012 blah -0.1412") == (
        51.5012,
        -0.1412,
    )


def test_database_ready_reports_success_and_failure() -> None:
    class _Factory:
        def __init__(self, session):
            self.session = session

        def __call__(self):
            return self

        def __enter__(self):
            return self.session

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

    class _Session:
        def __init__(self, fail=False):
            self.fail = fail

        def execute(self, stmt):
            if self.fail:
                raise RuntimeError("boom")
            return None

    assert health_service.database_ready(_Factory(_Session())) is True
    assert health_service.database_ready(_Factory(_Session(fail=True))) is False


def test_build_data_health_and_model_health_cover_summary_and_warning_paths(monkeypatch) -> None:
    coverage_complete = SimpleNamespace(
        borough_id="camden",
        source_family="planning",
        coverage_status=SimpleNamespace(value="COMPLETE"),
        gap_reason=None,
        freshness_status=SimpleNamespace(value="FRESH"),
        coverage_note="ok",
        source_snapshot_id=uuid.uuid4(),
        captured_at=datetime(2025, 1, 2, tzinfo=UTC),
    )
    coverage_partial = SimpleNamespace(
        borough_id="camden",
        source_family="title",
        coverage_status=SimpleNamespace(value="PARTIAL"),
        gap_reason="missing",
        freshness_status=SimpleNamespace(value="STALE"),
        coverage_note="needs review",
        source_snapshot_id=None,
        captured_at=datetime(2025, 1, 1, tzinfo=UTC),
    )
    baseline_rule = SimpleNamespace(
        template_key="rule-1",
        status=SimpleNamespace(value="SIGNED_OFF"),
        freshness_status=SimpleNamespace(value="FRESH"),
        source_snapshot_id=uuid.uuid4(),
    )
    baseline_pack = SimpleNamespace(
        borough_id="camden",
        version="v1",
        status=SimpleNamespace(value="PILOT_READY"),
        freshness_status=SimpleNamespace(value="FRESH"),
        signed_off_by="analyst",
        signed_off_at=datetime(2025, 1, 3, tzinfo=UTC),
        rulepacks=[baseline_rule],
    )
    valuation_row = SimpleNamespace(
        uplift_mid=None,
        valuation_quality=SimpleNamespace(value="GOOD"),
    )
    site = SimpleNamespace(id="site-1")

    session = _QueueSession(
        results=[
            _Result(items=[coverage_partial, coverage_complete]),
            _Result(items=[baseline_pack]),
            _Result(items=[valuation_row]),
            _Result(scalar=1),
            _Result(scalar=4),
            _Result(scalar=1),
            _Result(scalar=8),
            _Result(scalar=6),
            _Result(rows=[(SimpleNamespace(value="HIGH"), 2), (SimpleNamespace(value="LOW"), 1)]),
            _Result(items=[site]),
        ]
    )
    valuation_metrics_calls = []
    unresolved_calls = []
    monkeypatch.setattr(
        health_service,
        "update_valuation_metrics",
        lambda metrics: valuation_metrics_calls.append(metrics),
    )
    monkeypatch.setattr(
        health_service,
        "evaluate_site_extant_permission",
        lambda **kwargs: unresolved_calls.append(kwargs)
        or SimpleNamespace(status=SimpleNamespace(value="UNRESOLVED_MISSING_MANDATORY_SOURCE")),
    )

    data_health = health_service.build_data_health(session)

    assert data_health["status"] == "warning"
    assert data_health["connector_failure_rate"] == 0.25
    assert data_health["listing_parse_success_rate"] == 0.75
    assert data_health["geometry_confidence_distribution"] == {"HIGH": 2, "LOW": 1}
    assert data_health["extant_permission_unresolved_rate"] == 1.0
    assert data_health["borough_baseline_coverage"] == {
        "total": 1,
        "signed_off": 0,
        "pilot_ready": 1,
    }
    assert valuation_metrics_calls[0]["total"] == 1
    assert valuation_metrics_calls[0]["valuation_quality_distribution"] == {"GOOD": 1}
    assert len(unresolved_calls) == 1

    releases = SimpleNamespace(
        id=uuid.uuid4(),
        template_key="template-a",
        scope_key="scope-a",
        status=ModelReleaseStatus.NOT_READY,
        support_count=1,
        positive_count=0,
        negative_count=1,
        reason_text="not ready",
        model_kind="classifier",
        created_at=datetime(2025, 1, 4, tzinfo=UTC),
        activated_at=None,
        active_scopes=[],
    )
    active_scope = SimpleNamespace(
        scope_key="scope-a",
        template_key="template-a",
        model_release_id=uuid.uuid4(),
        activated_at=datetime(2025, 1, 5, tzinfo=UTC),
        visibility_mode=SimpleNamespace(value="HIDDEN_ONLY"),
        visibility_reason="fixture",
    )

    model_session = _QueueSession(
        results=[_Result(items=[releases]), _Result(items=[active_scope])]
    )
    monkeypatch.setattr(
        health_service,
        "_assessment_model_metrics",
        lambda session: {
            "calibration_by_probability_band": [],
            "brier_score": None,
            "log_loss": None,
            "manual_review_agreement_by_band": [],
            "false_positive_reviewer_rate": None,
            "abstain_rate": None,
            "ood_rate": None,
            "template_level_performance": [],
        },
    )
    monkeypatch.setattr(
        health_service,
        "_build_valuation_metrics",
        lambda session: {
            "total": 0,
            "uplift_null_rate": None,
            "asking_price_missing_rate": None,
            "valuation_quality_distribution": {},
        },
    )

    model_health = health_service.build_model_health(model_session)
    assert model_health["status"] == "warning"
    assert model_health["releases"][0]["status"] == ModelReleaseStatus.NOT_READY.value
    assert model_health["active_scopes"][0]["visibility_mode"] == "HIDDEN_ONLY"


def test_scheduler_tick_enqueues_only_due_compliant_sources(monkeypatch) -> None:
    now = datetime(2025, 4, 18, 12, 0, tzinfo=UTC)
    monkeypatch.setattr(
        scheduler_main,
        "datetime",
        SimpleNamespace(now=lambda tz: now, min=datetime.min),
    )

    assert scheduler_main._coerce_utc(datetime(2025, 4, 18, 12, 0)).tzinfo == UTC
    assert scheduler_main._coerce_utc(datetime(2025, 4, 18, 12, 0, tzinfo=UTC)) == datetime(
        2025, 4, 18, 12, 0, tzinfo=UTC
    )

    sources = [
        SimpleNamespace(
            name="source-a",
            refresh_policy_json={"interval_hours": 24},
        ),
        SimpleNamespace(
            name="source-b",
            refresh_policy_json={},
        ),
        SimpleNamespace(
            name="source-c",
            refresh_policy_json={"interval_hours": 1},
        ),
        SimpleNamespace(
            name="source-d",
            refresh_policy_json={"interval_hours": 1},
        ),
    ]
    jobs = [
        SimpleNamespace(
            payload_json={"source_name": "source-c"},
            status=JobStatus.QUEUED,
            created_at=now - timedelta(hours=2),
        ),
        SimpleNamespace(
            payload_json={"source_name": "source-d"},
            status=JobStatus.SUCCEEDED,
            created_at=now - timedelta(minutes=20),
        ),
        SimpleNamespace(
            payload_json={"source_name": "source-a"},
            status=JobStatus.SUCCEEDED,
            created_at=now - timedelta(days=2),
        ),
    ]
    session = _QueueSession(results=[_Result(items=sources), _Result(items=jobs)])
    enqueued = []
    monkeypatch.setattr(
        scheduler_main,
        "enqueue_connector_run_job",
        lambda **kwargs: enqueued.append(kwargs),
    )

    scheduler_main.scheduler_tick(_ContextFactory(session))

    assert enqueued == [
        {
            "session": session,
            "source_name": "source-a",
            "requested_by": "scheduler",
        }
    ]
    assert session.commit_count == 1


@pytest.mark.parametrize(
    ("job_result", "expected_handled"),
    [
        (None, False),
        (SimpleNamespace(id="job-1", status=JobStatus.RUNNING), True),
    ],
)
def test_worker_process_next_job_covers_no_job_and_success_paths(
    monkeypatch,
    job_result,
    expected_handled,
) -> None:
    session = _QueueSession()
    heartbeat_event = _StopEvent()
    heartbeat_thread = _JoinThread()
    dispatch_calls = []
    heartbeat_calls = []

    monkeypatch.setattr(worker_main, "claim_next_job", lambda **kwargs: job_result)
    monkeypatch.setattr(
        worker_main,
        "_start_job_heartbeat",
        lambda **kwargs: heartbeat_calls.append(kwargs) or (heartbeat_event, heartbeat_thread),
    )
    monkeypatch.setattr(
        worker_main,
        "dispatch_connector_job",
        lambda **kwargs: dispatch_calls.append(kwargs) or True,
    )

    handled = worker_main.process_next_job(
        settings=SimpleNamespace(worker_id="worker-1", worker_max_attempts=3),
        session_factory=_ContextFactory(session),
        dispatch_job=worker_main.dispatch_connector_job,
        storage=object(),
    )

    assert handled is expected_handled
    if job_result is None:
        assert session.commit_count == 1
        assert heartbeat_calls == []
        assert dispatch_calls == []
    else:
        assert session.commit_count == 2
        assert heartbeat_event.was_set is True
        assert heartbeat_thread.join_timeout == 1
        assert len(heartbeat_calls) == 1
        assert len(dispatch_calls) == 1


def test_valuation_refresh_and_build_jobs_write_expected_payloads(monkeypatch) -> None:
    session = SimpleNamespace(
        flush_count=0, flush=lambda: setattr(session, "flush_count", session.flush_count + 1)
    )
    job = SimpleNamespace(payload_json={"dataset": "all"}, requested_by="pytest")
    calls = []
    storage = object()

    monkeypatch.setattr(
        worker_valuation,
        "ensure_default_assumption_set",
        lambda session: SimpleNamespace(version="v-default"),
    )
    monkeypatch.setattr(
        worker_valuation,
        "import_hmlr_price_paid_fixture",
        lambda **kwargs: calls.append(("hmlr", kwargs))
        or SimpleNamespace(
            source_snapshot_id=uuid.uuid4(),
            raw_asset_id=uuid.uuid4(),
            imported_count=3,
        ),
    )
    monkeypatch.setattr(
        worker_valuation,
        "import_ukhpi_fixture",
        lambda **kwargs: calls.append(("ukhpi", kwargs))
        or SimpleNamespace(
            source_snapshot_id=uuid.uuid4(),
            raw_asset_id=uuid.uuid4(),
            imported_count=4,
        ),
    )
    monkeypatch.setattr(
        worker_valuation,
        "import_land_comp_fixture",
        lambda **kwargs: calls.append(("land", kwargs))
        or SimpleNamespace(
            source_snapshot_id=uuid.uuid4(),
            raw_asset_id=uuid.uuid4(),
            imported_count=5,
        ),
    )

    worker_valuation.run_valuation_data_refresh_job(session=session, job=job, storage=storage)

    assert session.flush_count == 1
    assert job.payload_json["result"]["dataset"] == "all"
    assert "assumption_set_version" in job.payload_json["result"]
    assert set(job.payload_json["result"]) >= {
        "dataset",
        "assumption_set_version",
        "hmlr_price_paid",
        "ukhpi",
        "land_comps",
    }
    assert [kind for kind, _ in calls] == ["hmlr", "ukhpi", "land"]

    build_calls = []
    monkeypatch.setattr(
        worker_valuation,
        "build_assessment_artifacts_for_run",
        lambda **kwargs: build_calls.append(kwargs),
    )
    run_job = SimpleNamespace(
        payload_json={"assessment_id": "11111111-1111-1111-1111-111111111111"}, requested_by=""
    )
    worker_valuation.run_valuation_run_build_job(session=session, job=run_job, storage=storage)

    assert build_calls == [
        {
            "session": session,
            "assessment_run_id": uuid.UUID("11111111-1111-1111-1111-111111111111"),
            "requested_by": "worker",
            "storage": storage,
        }
    ]
