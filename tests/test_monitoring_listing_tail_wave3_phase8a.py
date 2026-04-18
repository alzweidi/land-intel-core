from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from landintel.connectors.base import ConnectorAsset, ConnectorRunOutput, ParsedListing
from landintel.domain import models
from landintel.domain.enums import (
    ComplianceMode,
    ConnectorType,
    EligibilityStatus,
    GeomConfidence,
    GeomSourceType,
    JobStatus,
    JobType,
    ListingStatus,
    ListingType,
    SourceClass,
    SourceCoverageStatus,
    SourceFreshnessStatus,
    SourceParseStatus,
)
from landintel.domain.models import (
    BoroughBaselinePack,
    BoroughRulepack,
    BrownfieldSiteState,
    JobRun,
    ListingCluster,
    ListingItem,
    ListingSource,
    LpaBoundary,
    PlanningApplication,
    PlanningApplicationDocument,
    PlanningConstraintFeature,
    PolicyArea,
    SiteCandidate,
    SourceCoverageSnapshot,
    SourceSnapshot,
)
from landintel.listings import service as listings_service
from landintel.monitoring import health as health_service
from landintel.planning import import_common as import_common_service

FIXED_NOW = datetime(2026, 4, 18, 10, 0, tzinfo=UTC)


class _MemoryStorage:
    def __init__(self) -> None:
        self._payloads: dict[str, bytes] = {}
        self.calls: list[tuple[str, bytes, str]] = []

    def put_bytes(self, path: str, payload: bytes, *, content_type: str) -> None:
        self.calls.append((path, payload, content_type))
        self._payloads[path] = payload

    def get_bytes(self, path: str) -> bytes:
        if path not in self._payloads:
            raise FileNotFoundError(path)
        return self._payloads[path]


class _QueuedResult:
    def __init__(self, *, items=None, scalar=None, rows=None):
        self._items = list(items or [])
        self._scalar = scalar
        self._rows = list(rows or [])

    def scalars(self):
        return self

    def all(self):
        return self._rows if self._rows else self._items

    def scalar_one(self):
        return self._scalar

    def scalar_one_or_none(self):
        return self._scalar


class _QueuedSession:
    def __init__(self, results):
        self.results = list(results)

    def execute(self, *_args, **_kwargs):
        if not self.results:
            raise AssertionError("unexpected execute call")
        return self.results.pop(0)


def _polygon_geojson():
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [0.0, 0.0],
                [0.0, 10.0],
                [10.0, 10.0],
                [10.0, 0.0],
                [0.0, 0.0],
            ]
        ],
    }


def _fake_geometry_result():
    return SimpleNamespace(
        geom_27700_wkt="POLYGON((0 0, 0 10, 10 10, 10 0, 0 0))",
        geom_4326={"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]]},
    )


def _make_source_snapshot(*, source_family: str = "planning") -> SourceSnapshot:
    return SourceSnapshot(
        id=uuid4(),
        source_family=source_family,
        source_name=f"{source_family}-fixture",
        source_uri="file:///fixture.json",
        acquired_at=FIXED_NOW,
        schema_hash="a" * 64,
        content_hash="b" * 64,
        freshness_status=SourceFreshnessStatus.FRESH,
        parse_status=SourceParseStatus.PARSED,
        manifest_json={},
        coverage_note="fixture note",
    )


def test_monitoring_helpers_cover_parse_empty_and_assessment_metric_edges():
    assert (
        health_service._listing_parse_success_rate(_QueuedSession([_QueuedResult(scalar=0)]))
        is None
    )

    run_one_id = uuid4()
    run_two_id = uuid4()
    scored_rows = [
        SimpleNamespace(
            assessment_run_id=run_one_id,
            assessment_run=SimpleNamespace(scenario=SimpleNamespace(template_key="template-a")),
            approval_probability_raw=0.92,
            approval_probability_display="HIGH",
            manual_review_required=True,
            ood_status="OUT_OF_SUPPORT",
            eligibility_status=EligibilityStatus.PASS,
            result_json={
                "validation_summary": {
                    "metrics": {
                        "brier_score": 0.21,
                        "calibration_by_band": [{"band": "HIGH", "expected": 0.8}],
                    }
                }
            },
        ),
        SimpleNamespace(
            assessment_run_id=run_two_id,
            assessment_run=SimpleNamespace(scenario=SimpleNamespace(template_key="template-a")),
            approval_probability_raw=0.12,
            approval_probability_display="LOW",
            manual_review_required=True,
            ood_status="IN_SUPPORT",
            eligibility_status=EligibilityStatus.ABSTAIN,
            result_json={
                "validation_summary": {
                    "metrics": {
                        "log_loss": 0.42,
                    }
                }
            },
        ),
    ]
    reviewer_overrides = [
        SimpleNamespace(
            assessment_run_id=run_one_id,
            status=SimpleNamespace(value="ACTIVE"),
            override_json={"resolve_manual_review": True},
            created_at=datetime(2026, 4, 18, 10, 5, tzinfo=UTC),
        )
    ]
    metrics = health_service._assessment_model_metrics(
        _QueuedSession(
            [
                _QueuedResult(items=scored_rows),
                _QueuedResult(items=reviewer_overrides),
            ]
        )
    )

    assert metrics["calibration_by_probability_band"] == [
        {
            "template_key": "template-a",
            "band": "HIGH",
            "expected": 0.8,
        }
    ]
    assert metrics["brier_score"] == 0.21
    assert metrics["log_loss"] == 0.42
    assert metrics["manual_review_agreement_by_band"] == [
        {"band": "HIGH", "total": 1, "completed": 1, "agreement_rate": 1.0},
        {"band": "LOW", "total": 1, "completed": 0, "agreement_rate": 0.0},
    ]
    assert metrics["false_positive_reviewer_rate"] == 0.5
    assert metrics["abstain_rate"] == 0.5
    assert metrics["ood_rate"] == 0.5
    assert metrics["template_level_performance"] == [
        {
            "template_key": "template-a",
            "count": 2,
            "brier_score": 0.21,
            "log_loss": 0.42,
            "ood_rate": 0.5,
        }
    ]


def test_listing_service_persistence_and_rebuild_branches(db_session):
    source = ListingSource(
        name="fixture-source",
        connector_type=ConnectorType.PUBLIC_PAGE,
        compliance_mode=ComplianceMode.COMPLIANT_AUTOMATED,
        refresh_policy_json={"interval_hours": 24},
        active=True,
    )
    db_session.add(source)
    db_session.flush()

    manual_blocked = SimpleNamespace(
        name="manual-blocked",
        compliance_mode=ComplianceMode.CSV_ONLY,
        active=True,
    )
    csv_blocked = SimpleNamespace(
        name="csv-blocked",
        compliance_mode=ComplianceMode.COMPLIANT_AUTOMATED,
        active=True,
    )
    with pytest.raises(Exception, match="Manual URL intake is blocked"):
        listings_service.enforce_compliance(
            source=manual_blocked,
            job=SimpleNamespace(job_type=JobType.MANUAL_URL_SNAPSHOT),
        )
    with pytest.raises(Exception, match="CSV import is blocked"):
        listings_service.enforce_compliance(
            source=csv_blocked,
            job=SimpleNamespace(job_type=JobType.CSV_IMPORT_SNAPSHOT),
        )

    job_one = JobRun(
        id=uuid4(),
        job_type=JobType.LISTING_SOURCE_RUN,
        payload_json={"source_name": source.name},
        status=JobStatus.QUEUED,
        attempts=1,
        run_at=FIXED_NOW,
        next_run_at=FIXED_NOW,
        locked_at=None,
        worker_id=None,
        error_text=None,
        requested_by="pytest",
    )
    listing_one = ParsedListing(
        source_listing_id="listing-1",
        canonical_url="https://example.test/listing-1",
        observed_at=FIXED_NOW,
        status=ListingStatus.LIVE,
        address_text="1 Example Road",
        normalized_address="1 example road",
        map_asset_key="map-asset",
    )
    output_one = ConnectorRunOutput(
        source_name=source.name,
        source_family="listing",
        source_uri="https://example.test/source",
        observed_at=FIXED_NOW,
        coverage_note="fixture coverage",
        parse_status=SourceParseStatus.PARSED,
        manifest_json={"source": "fixture"},
        assets=[
            ConnectorAsset(
                asset_key="map-asset",
                asset_type="HTML",
                role="MAP",
                original_url="https://example.test/map.html",
                content=b"<html>map</html>",
                content_type="text/html",
                fetched_at=FIXED_NOW,
            )
        ],
        listings=[listing_one],
    )
    storage = _MemoryStorage()

    result_one = listings_service.persist_connector_output(
        session=db_session,
        job=job_one,
        source=source,
        output=output_one,
        storage=storage,
    )
    result_two = listings_service.persist_connector_output(
        session=db_session,
        job=job_one,
        source=source,
        output=output_one,
        storage=storage,
    )
    db_session.flush()

    assert result_one.source_snapshot_id == result_two.source_snapshot_id
    assert result_one.listing_item_ids == result_two.listing_item_ids

    listing_item = (
        db_session.query(ListingItem).filter(ListingItem.source_listing_id == "listing-1").one()
    )
    assert listing_item.current_snapshot_id is not None

    existing_update_item = ListingItem(
        source_id=source.id,
        source_listing_id="listing-existing",
        canonical_url="https://example.test/original",
        listing_type=ListingType.UNKNOWN,
        latest_status=ListingStatus.UNKNOWN,
        search_text="original",
        last_seen_at=FIXED_NOW - timedelta(hours=2),
    )
    db_session.add(existing_update_item)
    db_session.flush()

    job_two = JobRun(
        id=uuid4(),
        job_type=JobType.LISTING_SOURCE_RUN,
        payload_json={"source_name": source.name},
        status=JobStatus.QUEUED,
        attempts=1,
        run_at=FIXED_NOW,
        next_run_at=FIXED_NOW,
        locked_at=None,
        worker_id=None,
        error_text=None,
        requested_by="pytest",
    )
    output_two = ConnectorRunOutput(
        source_name=source.name,
        source_family="listing",
        source_uri="https://example.test/source-2",
        observed_at=datetime(2026, 4, 18, 10, 30, tzinfo=UTC),
        coverage_note="fixture coverage",
        parse_status=SourceParseStatus.PARSED,
        manifest_json={"source": "fixture-2"},
        assets=[
            ConnectorAsset(
                asset_key="map-asset",
                asset_type="HTML",
                role="MAP",
                original_url="https://example.test/map.html",
                content=b"<html>map</html>",
                content_type="text/html",
                fetched_at=datetime(2026, 4, 18, 10, 30, tzinfo=UTC),
            )
        ],
        listings=[
            ParsedListing(
                source_listing_id="listing-existing",
                canonical_url="https://example.test/listing-existing",
                observed_at=datetime(2026, 4, 18, 10, 30, tzinfo=UTC),
                status=ListingStatus.SOLD_STC,
                address_text="2 Example Road",
                normalized_address="2 example road",
                map_asset_key="map-asset",
            )
        ],
    )
    result_three = listings_service.persist_connector_output(
        session=db_session,
        job=job_two,
        source=source,
        output=output_two,
        storage=_MemoryStorage(),
    )
    updated_listing = (
        db_session.query(ListingItem)
        .filter(ListingItem.source_listing_id == "listing-existing")
        .one()
    )

    assert result_three.listing_item_ids == [updated_listing.id]
    assert updated_listing.canonical_url == "https://example.test/listing-existing"
    assert updated_listing.last_seen_at == datetime(2026, 4, 18, 10, 30, tzinfo=UTC)
    assert updated_listing.latest_status == ListingStatus.SOLD_STC

    dummy_listing = ListingItem(
        source_id=source.id,
        source_listing_id="listing-missing-snapshot",
        canonical_url="https://example.test/listing-missing",
        listing_type=ListingType.UNKNOWN,
        latest_status=ListingStatus.UNKNOWN,
        search_text="missing snapshot",
        current_snapshot_id=uuid4(),
    )
    seed_cluster = ListingCluster(
        id=uuid4(),
        cluster_key="seed-cluster",
    )
    site = SiteCandidate(
        listing_cluster_id=seed_cluster.id,
        display_name="site-no-current-listing",
        geom_27700="POLYGON((0 0, 0 5, 5 5, 5 0, 0 0))",
        geom_4326={},
        geom_hash="c" * 64,
        geom_source_type=GeomSourceType.SOURCE_POLYGON,
        geom_confidence=GeomConfidence.HIGH,
        site_area_sqm=25.0,
    )
    db_session.add_all([dummy_listing, seed_cluster, site])
    db_session.flush()

    cluster_id = uuid4()
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        listings_service,
        "build_clusters",
        lambda inputs: [
            SimpleNamespace(
                cluster_id=cluster_id,
                cluster_key="cluster-1",
                cluster_status=models.ListingClusterStatus.ACTIVE,
                members=[
                    SimpleNamespace(
                        listing_item_id=listing_item.id,
                        confidence=0.95,
                        reasons=["same listing"],
                    )
                ],
            )
        ],
    )
    try:
        clusters = listings_service.rebuild_listing_clusters(db_session)
    finally:
        monkeypatch.undo()

    assert len(clusters) == 1
    assert clusters[0].id == cluster_id
    assert clusters[0].cluster_key == "cluster-1"

    sources = [
        ListingSource(
            name="a-source",
            connector_type=models.ConnectorType.MANUAL_URL,
            compliance_mode=ComplianceMode.MANUAL_ONLY,
            refresh_policy_json={"run_mode": "manual"},
            active=True,
        ),
        ListingSource(
            name="z-source",
            connector_type=models.ConnectorType.CSV_IMPORT,
            compliance_mode=ComplianceMode.CSV_ONLY,
            refresh_policy_json={"run_mode": "manual"},
            active=True,
        ),
    ]
    db_session.add_all(sources)
    db_session.flush()

    ordered = listings_service.list_listing_sources(session=db_session)
    assert [row.name for row in ordered[:2]] == ["a-source", "fixture-source"]


def test_import_common_row_upserts_and_parser_branches(tmp_path: Path, db_session):
    storage = _MemoryStorage()
    source_snapshot = _make_source_snapshot()
    db_session.add(source_snapshot)

    boundary = LpaBoundary(
        id="camden",
        name="Camden",
        geom_27700="POLYGON((0 0, 0 10, 10 10, 10 0, 0 0))",
        geom_4326={},
        geom_hash="d" * 64,
        area_sqm=100.0,
        source_snapshot_id=source_snapshot.id,
    )
    db_session.add(boundary)
    db_session.flush()

    imported_coverage = import_common_service.upsert_coverage_snapshots(
        session=db_session,
        source_snapshot=source_snapshot,
        coverage_rows=[
            {
                "borough_id": "camden",
                "coverage_status": "COMPLETE",
                "freshness_status": "FRESH",
                "coverage_note": "fixture coverage note",
            }
        ],
    )
    assert imported_coverage == 1
    db_session.flush()
    coverage_row = db_session.query(SourceCoverageSnapshot).filter_by(borough_id="camden").one()
    assert coverage_row.coverage_status == SourceCoverageStatus.COMPLETE
    assert coverage_row.coverage_note == "fixture coverage note"

    fixture_doc = import_common_service.store_document_asset(
        session=db_session,
        storage=storage,
        source_snapshot_id=source_snapshot.id,
        dataset_key="camden-fixture",
        original_url="https://example.test/doc-1.pdf",
        content=b"fixture document",
        mime_type="application/pdf",
    )
    duplicate_doc = import_common_service.store_document_asset(
        session=db_session,
        storage=storage,
        source_snapshot_id=source_snapshot.id,
        dataset_key="camden-fixture",
        original_url="https://example.test/doc-2.pdf",
        content=b"fixture document",
        mime_type="application/pdf",
    )
    assert fixture_doc.id == duplicate_doc.id

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        import_common_service,
        "normalize_geojson_geometry",
        lambda **kwargs: _fake_geometry_result(),
    )
    try:
        app_imported = import_common_service.upsert_planning_application_rows(
            session=db_session,
            storage=_MemoryStorage(),
            dataset_key="camden-fixture",
            source_snapshot=source_snapshot,
            source_system="BOROUGH_REGISTER",
            source_priority=3,
            applications=[
                {
                    "borough_id": "camden",
                    "external_ref": "CAM/2026/0001/FUL",
                    "application_type": "FULL",
                    "proposal_description": "Test proposal",
                    "valid_date": "2026-04-18",
                    "decision_date": "2026-04-19",
                    "decision": "APPROVED",
                    "decision_type": "FULL_RESIDENTIAL",
                    "status": "APPROVED",
                    "route_normalized": "FULL",
                    "units_proposed": "12",
                    "source_url": "https://example.test/app",
                    "geometry_4326": _polygon_geojson(),
                    "documents": [
                        {
                            "doc_url": "https://example.test/doc-3.txt",
                            "content_text": "planning document",
                            "mime_type": "text/plain",
                        }
                    ],
                }
            ],
        )
        brownfield_imported = import_common_service.upsert_brownfield_rows(
            session=db_session,
            source_snapshot=source_snapshot,
            features=[
                {
                    "properties": {
                        "borough_id": "camden",
                        "external_ref": "brownfield-1",
                        "part": "PART_2",
                    },
                    "geometry": _polygon_geojson(),
                }
            ],
        )
        policy_imported = import_common_service.upsert_policy_area_rows(
            session=db_session,
            source_snapshot=source_snapshot,
            features=[
                {
                    "properties": {
                        "borough_id": "camden",
                        "policy_family": "design",
                        "policy_code": "D1",
                        "name": "Design policy",
                    },
                    "geometry": _polygon_geojson(),
                }
            ],
        )
        constraint_imported = import_common_service.upsert_constraint_rows(
            session=db_session,
            source_snapshot=source_snapshot,
            features=[
                {
                    "properties": {
                        "feature_family": "heritage",
                        "feature_subtype": "listed_building",
                        "external_ref": "constraint-1",
                    },
                    "geometry": _polygon_geojson(),
                }
            ],
        )
        baseline_imported = import_common_service.upsert_baseline_pack_rows(
            session=db_session,
            source_snapshot=source_snapshot,
            baseline_packs=[
                {
                    "borough_id": "camden",
                    "version": "2026-04",
                    "status": "SIGNED_OFF",
                    "freshness_status": "FRESH",
                    "signed_off_by": "analyst",
                    "signed_off_at": "2026-04-18T10:00:00Z",
                    "pack_json": {"pilot": True},
                    "rulepacks": [
                        {
                            "template_key": "resi_5_9_full",
                            "status": "SIGNED_OFF",
                            "freshness_status": "FRESH",
                            "rule_json": {"enabled": True},
                        }
                    ],
                }
            ],
        )
    finally:
        monkeypatch.undo()

    assert app_imported == 1
    assert brownfield_imported == 1
    assert policy_imported == 1
    assert constraint_imported == 1
    assert baseline_imported == 1
    assert db_session.query(PlanningApplication).filter_by(external_ref="CAM/2026/0001/FUL").one()
    assert db_session.query(PlanningApplicationDocument).count() == 1
    assert db_session.query(BrownfieldSiteState).filter_by(external_ref="brownfield-1").one()
    assert db_session.query(PolicyArea).filter_by(policy_code="D1").one()
    assert (
        db_session.query(PlanningConstraintFeature)
        .filter_by(feature_subtype="listed_building")
        .one()
    )
    assert db_session.query(BoroughBaselinePack).filter_by(version="2026-04").one()
    db_session.flush()
    assert db_session.query(BoroughRulepack).filter_by(template_key="resi_5_9_full").one()

    assert import_common_service.dataset_meta({"meta": {"title": "fixture"}}) == {
        "title": "fixture"
    }
    assert import_common_service.dataset_meta({"metadata": {"title": "fallback"}}) == {
        "title": "fallback"
    }
    assert import_common_service.dataset_meta({}) == {}

    assert (
        import_common_service.parse_source_class(None, SourceClass.AUTHORITATIVE)
        == SourceClass.AUTHORITATIVE
    )
    assert (
        import_common_service.parse_source_class("MARKET", SourceClass.AUTHORITATIVE)
        == SourceClass.MARKET
    )

    assert import_common_service._extension_for_mime("application/json") == ".json"
    assert import_common_service._extension_for_mime("text/html") == ".html"
    assert import_common_service._parse_date(date(2026, 4, 18)) == date(2026, 4, 18)
    assert import_common_service._parse_date(datetime(2026, 4, 18, 10, 0, tzinfo=UTC)) == date(
        2026, 4, 18
    )
    assert import_common_service._parse_datetime(
        datetime(2026, 4, 18, 10, 0, tzinfo=UTC)
    ) == datetime(2026, 4, 18, 10, 0, tzinfo=UTC)
    assert import_common_service._parse_datetime(date(2026, 4, 18)) == datetime(
        2026, 4, 18, 0, 0, tzinfo=UTC
    )
    assert import_common_service._parse_datetime("2026-04-18T10:00:00Z") == datetime(
        2026, 4, 18, 10, 0, tzinfo=UTC
    )
    assert import_common_service._parse_datetime("2026-04-18T10:00:00") == datetime(
        2026, 4, 18, 10, 0, tzinfo=UTC
    )
    assert import_common_service._parse_int("12") == 12
