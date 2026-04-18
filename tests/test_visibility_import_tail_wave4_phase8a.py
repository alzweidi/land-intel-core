from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from landintel.domain import models
from landintel.domain.enums import (
    AppRoleName,
    AssessmentOverrideStatus,
    AssessmentOverrideType,
    BaselinePackStatus,
    EligibilityStatus,
    GeomConfidence,
    GeomSourceType,
    IncidentStatus,
    JobStatus,
    JobType,
    ModelReleaseStatus,
    SourceCoverageStatus,
    SourceFreshnessStatus,
    SourceParseStatus,
    VisibilityMode,
)
from landintel.monitoring import health as health_service
from landintel.planning import import_common
from landintel.review.visibility import (
    ReviewAccessError,
    evaluate_assessment_visibility,
    open_scope_incident,
    resolve_scope_incident,
    set_scope_visibility,
)
from sqlalchemy import select

POLYGON_WKT = "POLYGON ((0 0, 100 0, 100 100, 0 100, 0 0))"
POLYGON_GEOJSON = {
    "type": "Polygon",
    "coordinates": [[[0, 0], [100, 0], [100, 100], [0, 100], [0, 0]]],
}
POINT_GEOJSON = {"type": "Point", "coordinates": [50, 50]}


class _MemoryStorage:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str | None]] = {}

    def put_bytes(self, storage_path: str, content: bytes, content_type: str | None = None) -> None:
        self.objects[storage_path] = (content, content_type)


def _geom_result() -> SimpleNamespace:
    return SimpleNamespace(geom_27700_wkt=POLYGON_WKT, geom_4326=POLYGON_GEOJSON)


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _make_source_snapshot(
    *,
    source_family: str = "planning",
    source_name: str = "Planning register",
    coverage_note: str = "source note",
    parse_status: SourceParseStatus = SourceParseStatus.PARSED,
) -> models.SourceSnapshot:
    return models.SourceSnapshot(
        id=uuid4(),
        source_family=source_family,
        source_name=source_name,
        source_uri="file:///tmp/source.json",
        schema_hash=_sha(f"{source_family}:schema"),
        content_hash=_sha(f"{source_family}:content"),
        coverage_note=coverage_note,
        freshness_status=SourceFreshnessStatus.FRESH,
        parse_status=parse_status,
        manifest_json={"source_family": source_family},
    )


def _make_listing_cluster(session, *, cluster_key: str) -> models.ListingCluster:
    cluster = models.ListingCluster(cluster_key=cluster_key)
    session.add(cluster)
    session.flush()
    return cluster


def _make_site_candidate(
    session,
    *,
    cluster: models.ListingCluster,
    display_name: str,
) -> models.SiteCandidate:
    site = models.SiteCandidate(
        listing_cluster_id=cluster.id,
        display_name=display_name,
        geom_27700=POLYGON_WKT,
        geom_4326=POLYGON_GEOJSON,
        geom_hash=_sha(display_name),
        geom_source_type=GeomSourceType.ANALYST_DRAWN,
        geom_confidence=GeomConfidence.HIGH,
        site_area_sqm=1000.0,
        warning_json={},
    )
    session.add(site)
    session.flush()
    return site


def _make_site_scenario(
    session,
    *,
    site: models.SiteCandidate,
    template_key: str,
    red_line_geom_hash: str,
) -> models.SiteScenario:
    scenario = models.SiteScenario(
        site_id=site.id,
        template_key=template_key,
        template_version="v1",
        proposal_form="OUTLINE",
        units_assumed=12,
        route_assumed="APPROVAL",
        height_band_assumed="4-6",
        net_developable_area_pct=0.42,
        red_line_geom_hash=red_line_geom_hash,
    )
    session.add(scenario)
    session.flush()
    return scenario


def _make_release(
    session,
    *,
    template_key: str,
    scope_key: str,
    status: ModelReleaseStatus,
) -> models.ModelRelease:
    release = models.ModelRelease(
        template_key=template_key,
        scope_key=scope_key,
        model_kind="fixture-model",
        transform_version="t1",
        feature_version="f1",
        status=status,
        model_artifact_hash=_sha(f"{scope_key}:model"),
        calibration_artifact_hash=_sha(f"{scope_key}:calibration"),
        validation_artifact_hash=_sha(f"{scope_key}:validation"),
    )
    session.add(release)
    session.flush()
    return release


def _make_active_scope(
    session,
    *,
    release: models.ModelRelease,
    scope_key: str,
    borough_id: str | None,
    visibility_mode: VisibilityMode = VisibilityMode.HIDDEN_ONLY,
    visibility_reason: str | None = None,
) -> models.ActiveReleaseScope:
    scope = models.ActiveReleaseScope(
        scope_key=scope_key,
        template_key=release.template_key,
        model_release_id=release.id,
        borough_id=borough_id,
        visibility_mode=visibility_mode,
        visibility_reason=visibility_reason,
        activated_by="seed",
    )
    session.add(scope)
    session.flush()
    return scope


def _make_signed_off_pack(
    session,
    *,
    borough_id: str,
    template_key: str,
) -> models.BoroughBaselinePack:
    pack = models.BoroughBaselinePack(
        borough_id=borough_id,
        version="2026.04",
        status=BaselinePackStatus.SIGNED_OFF,
        freshness_status=SourceFreshnessStatus.FRESH,
        signed_off_by="planner@example.com",
        signed_off_at=datetime(2026, 4, 18, 9, 30, tzinfo=UTC),
        pack_json={"template_key": template_key},
    )
    session.add(pack)
    session.flush()
    rulepack = models.BoroughRulepack(
        borough_baseline_pack_id=pack.id,
        template_key=template_key,
        status=BaselinePackStatus.SIGNED_OFF,
        freshness_status=SourceFreshnessStatus.FRESH,
        effective_from=date(2026, 4, 18),
        rule_json={"template_key": template_key},
    )
    session.add(rulepack)
    session.flush()
    return pack


def test_evaluate_assessment_visibility_redacts_when_scope_missing() -> None:
    assessment_run = SimpleNamespace(
        result=SimpleNamespace(
            release_scope_key=None,
            model_release_id=uuid4(),
            approval_probability_raw=0.74,
            approval_probability_display="HIGH",
        ),
        prediction_ledger=None,
    )

    gate = evaluate_assessment_visibility(
        session=None,
        assessment_run=assessment_run,
        viewer_role="analyst",
    )

    assert gate.scope_key is None
    assert gate.blocked is True
    assert gate.blocked_reason_codes == ["NO_SCOPE"]
    assert gate.blocked_reason_text == "No active release scope is registered for this assessment."
    assert gate.exposure_mode == "REDACTED"
    assert gate.artifact_hashes_match is None
    assert gate.scope_release_matches_result is None


def test_scope_visibility_and_incident_lifecycle_covers_expected_branches(db_session) -> None:
    release = _make_release(
        db_session,
        template_key="template-visibility",
        scope_key="scope-visibility",
        status=ModelReleaseStatus.ACTIVE,
    )

    hidden_scope = _make_active_scope(
        db_session,
        release=release,
        scope_key="scope-hidden",
        borough_id=None,
    )
    hidden_scope = set_scope_visibility(
        session=db_session,
        scope_key=hidden_scope.scope_key,
        visibility_mode=VisibilityMode.HIDDEN_ONLY,
        requested_by=None,
        actor_role="admin",
        reason="keep hidden",
    )
    assert hidden_scope.visibility_mode == VisibilityMode.HIDDEN_ONLY
    assert hidden_scope.visibility_reason == "keep hidden"
    assert hidden_scope.visibility_updated_by == "api-admin"
    assert hidden_scope.visible_enabled_by is None
    assert hidden_scope.visible_enabled_at is None

    boroughless_scope = _make_active_scope(
        db_session,
        release=release,
        scope_key="scope-visible-no-borough",
        borough_id=None,
    )
    with pytest.raises(ReviewAccessError, match="borough-scoped active release"):
        set_scope_visibility(
            session=db_session,
            scope_key=boroughless_scope.scope_key,
            visibility_mode=VisibilityMode.VISIBLE_REVIEWER_ONLY,
            requested_by="reviewer@example.com",
            actor_role=AppRoleName.ADMIN,
            reason="should fail",
        )

    missing_pack_scope = _make_active_scope(
        db_session,
        release=release,
        scope_key="scope-visible-no-pack",
        borough_id="E09000001",
    )
    with pytest.raises(ReviewAccessError, match="signed-off borough baseline pack"):
        set_scope_visibility(
            session=db_session,
            scope_key=missing_pack_scope.scope_key,
            visibility_mode=VisibilityMode.VISIBLE_REVIEWER_ONLY,
            requested_by="reviewer@example.com",
            actor_role=AppRoleName.ADMIN,
            reason="should fail",
        )

    missing_rulepack_scope = _make_active_scope(
        db_session,
        release=release,
        scope_key="scope-visible-no-rulepack",
        borough_id="E09000002",
    )
    pack = models.BoroughBaselinePack(
        borough_id="E09000002",
        version="2026.04",
        status=BaselinePackStatus.SIGNED_OFF,
        freshness_status=SourceFreshnessStatus.FRESH,
        signed_off_by="planner@example.com",
        signed_off_at=datetime(2026, 4, 18, 9, 30, tzinfo=UTC),
        pack_json={"template_key": release.template_key},
    )
    db_session.add(pack)
    db_session.flush()
    with pytest.raises(ReviewAccessError, match="signed-off borough rulepack"):
        set_scope_visibility(
            session=db_session,
            scope_key=missing_rulepack_scope.scope_key,
            visibility_mode=VisibilityMode.VISIBLE_REVIEWER_ONLY,
            requested_by="reviewer@example.com",
            actor_role="admin",
            reason="should fail",
        )

    success_scope = _make_active_scope(
        db_session,
        release=release,
        scope_key="scope-visible-success",
        borough_id="E09000003",
    )
    _make_signed_off_pack(
        db_session,
        borough_id="E09000003",
        template_key=release.template_key,
    )
    success_scope = set_scope_visibility(
        session=db_session,
        scope_key=success_scope.scope_key,
        visibility_mode=VisibilityMode.VISIBLE_REVIEWER_ONLY,
        requested_by="reviewer@example.com",
        actor_role="admin",
        reason="enable reviewer visibility",
    )
    assert success_scope.visibility_mode == VisibilityMode.VISIBLE_REVIEWER_ONLY
    assert success_scope.visible_enabled_by == "reviewer@example.com"
    assert success_scope.visible_enabled_at is not None

    incident = open_scope_incident(
        session=db_session,
        scope_key=success_scope.scope_key,
        requested_by="reviewer@example.com",
        actor_role=AppRoleName.ADMIN,
        reason="visible probability blocked",
    )
    assert incident.status == IncidentStatus.OPEN
    assert incident.previous_visibility_mode == VisibilityMode.VISIBLE_REVIEWER_ONLY

    repeated = open_scope_incident(
        session=db_session,
        scope_key=success_scope.scope_key,
        requested_by="reviewer@example.com",
        actor_role="admin",
        reason="ignored because already open",
    )
    assert repeated.id == incident.id

    resolved = resolve_scope_incident(
        session=db_session,
        scope_key=success_scope.scope_key,
        requested_by="reviewer@example.com",
        actor_role="admin",
        reason="incident cleared",
        rollback_visibility=True,
    )
    assert resolved.status == IncidentStatus.RESOLVED
    assert success_scope.visibility_mode == VisibilityMode.VISIBLE_REVIEWER_ONLY
    assert success_scope.visible_enabled_by == "reviewer@example.com"
    assert success_scope.visible_enabled_at is not None


def test_import_common_row_upserts_and_dedup_paths(db_session) -> None:
    storage = _MemoryStorage()
    source_snapshot = _make_source_snapshot()
    db_session.add(source_snapshot)
    db_session.flush()

    boundary = models.LpaBoundary(
        id="E09000004",
        name="Camden",
        geom_27700=POLYGON_WKT,
        geom_hash=_sha("camden-boundary"),
        area_sqm=12345.0,
        source_snapshot_id=source_snapshot.id,
    )
    db_session.add(boundary)
    db_session.flush()

    coverage_imported = import_common.upsert_coverage_snapshots(
        session=db_session,
        source_snapshot=source_snapshot,
        coverage_rows=[
            {
                "borough_id": boundary.id,
                "coverage_status": SourceCoverageStatus.PARTIAL.value,
            }
        ],
    )
    assert coverage_imported == 1

    repeated_asset = import_common.store_document_asset(
        session=db_session,
        storage=storage,
        source_snapshot_id=source_snapshot.id,
        dataset_key="planning-register",
        original_url="https://example.com/committee-report.pdf",
        content=b"committee report",
        mime_type="application/pdf",
    )
    repeated_asset_again = import_common.store_document_asset(
        session=db_session,
        storage=storage,
        source_snapshot_id=source_snapshot.id,
        dataset_key="planning-register",
        original_url="https://example.com/committee-report.pdf",
        content=b"committee report",
        mime_type="application/pdf",
    )
    assert repeated_asset_again.id == repeated_asset.id

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        import_common, "normalize_geojson_geometry", lambda **kwargs: _geom_result()
    )
    try:
        applications_imported = import_common.upsert_planning_application_rows(
            session=db_session,
            storage=storage,
            dataset_key="planning-register",
            source_snapshot=source_snapshot,
            source_system="fixture-system",
            source_priority=7,
            applications=[
                {
                    "external_ref": "PA-001",
                    "borough_id": boundary.id,
                    "application_type": "FULL",
                    "proposal_description": "Residential conversion",
                    "valid_date": "2026-04-01",
                    "decision_date": "2026-04-02",
                    "decision": "APPROVED",
                    "decision_type": "COMMITTEE",
                    "status": "VALIDATED",
                    "route_normalized": "FULL",
                    "units_proposed": "12",
                    "geometry_4326": POLYGON_GEOJSON,
                    "point_4326": POINT_GEOJSON,
                    "documents": [
                        {
                            "doc_url": "https://example.com/committee-report.pdf",
                            "doc_type": "committee-report",
                            "mime_type": "application/pdf",
                            "content_text": "committee report",
                        }
                    ],
                }
            ],
        )
        assert applications_imported == 1

        brownfield_imported = import_common.upsert_brownfield_rows(
            session=db_session,
            source_snapshot=source_snapshot,
            features=[
                {
                    "geometry": POLYGON_GEOJSON,
                    "properties": {
                        "borough_id": boundary.id,
                        "external_ref": "BF-001",
                        "part": "PART_1",
                        "pip_status": "PIP",
                        "tdc_status": "TDC",
                        "effective_from": "2026-04-01",
                        "effective_to": "2026-05-01",
                    },
                }
            ],
        )
        assert brownfield_imported == 1

        policy_imported = import_common.upsert_policy_area_rows(
            session=db_session,
            source_snapshot=source_snapshot,
            features=[
                {
                    "geometry": POLYGON_GEOJSON,
                    "properties": {
                        "borough_id": boundary.id,
                        "policy_family": "local-plan",
                        "policy_code": "LP1",
                        "name": "Policy one",
                        "source_class": "AUTHORITATIVE",
                    },
                }
            ],
        )
        assert policy_imported == 1

        constraint_imported = import_common.upsert_constraint_rows(
            session=db_session,
            source_snapshot=source_snapshot,
            features=[
                {
                    "geometry": POLYGON_GEOJSON,
                    "properties": {
                        "feature_family": "heritage",
                        "feature_subtype": "listed-building",
                        "external_ref": "C-001",
                        "authority_level": "BOROUGH",
                    },
                }
            ],
        )
        assert constraint_imported == 1

        pack_imported = import_common.upsert_baseline_pack_rows(
            session=db_session,
            source_snapshot=source_snapshot,
            baseline_packs=[
                {
                    "borough_id": boundary.id,
                    "version": "2026.04",
                    "status": "SIGNED_OFF",
                    "signed_off_at": "2026-04-18T09:30:00Z",
                    "rulepacks": [
                        {
                            "template_key": "template-a",
                            "status": "SIGNED_OFF",
                            "rule_json": {"template_key": "template-a"},
                        }
                    ],
                }
            ],
        )
        assert pack_imported == 1
    finally:
        monkeypatch.undo()
    db_session.flush()

    coverage_row = db_session.execute(select(models.SourceCoverageSnapshot)).scalar_one()
    assert coverage_row.coverage_status == SourceCoverageStatus.PARTIAL
    assert coverage_row.coverage_note == source_snapshot.coverage_note

    planning_application = db_session.execute(select(models.PlanningApplication)).scalar_one()
    assert planning_application.external_ref == "PA-001"
    assert planning_application.site_geom_27700 == POLYGON_WKT
    assert planning_application.site_point_27700 == POLYGON_WKT

    document = db_session.execute(select(models.PlanningApplicationDocument)).scalar_one()
    assert document.doc_url == "https://example.com/committee-report.pdf"
    assert document.asset_id == repeated_asset.id

    assert db_session.execute(select(models.BrownfieldSiteState)).scalar_one().part == "PART_1"
    assert db_session.execute(select(models.PolicyArea)).scalar_one().policy_code == "LP1"
    assert (
        db_session.execute(select(models.PlanningConstraintFeature)).scalar_one().feature_subtype
        == "listed-building"
    )

    pack = db_session.execute(select(models.BoroughBaselinePack)).scalar_one()
    assert pack.status == BaselinePackStatus.SIGNED_OFF
    rulepack = db_session.execute(select(models.BoroughRulepack)).scalar_one()
    assert rulepack.template_key == "template-a"
    assert import_common._parse_int(None) is None


def test_build_data_health_warns_on_partial_coverage_and_reports_rates(db_session) -> None:
    source_snapshot = _make_source_snapshot(parse_status=SourceParseStatus.PARSED)
    db_session.add(source_snapshot)
    db_session.flush()

    boundary = models.LpaBoundary(
        id="E09000005",
        name="Coverage Borough",
        geom_27700=POLYGON_WKT,
        geom_hash=_sha("coverage-borough"),
        area_sqm=22222.0,
        source_snapshot_id=source_snapshot.id,
    )
    db_session.add(boundary)

    db_session.add(
        models.SourceCoverageSnapshot(
            borough_id=boundary.id,
            source_family="PLANNING",
            coverage_geom_27700=POLYGON_WKT,
            coverage_status=SourceCoverageStatus.PARTIAL,
            freshness_status=SourceFreshnessStatus.FRESH,
            source_snapshot_id=source_snapshot.id,
            coverage_note="partial borough coverage",
        )
    )
    db_session.add(
        models.BoroughBaselinePack(
            borough_id=boundary.id,
            version="2026.04",
            status=BaselinePackStatus.SIGNED_OFF,
            freshness_status=SourceFreshnessStatus.FRESH,
            signed_off_by="planner@example.com",
            signed_off_at=datetime(2026, 4, 18, 9, 30, tzinfo=UTC),
        )
    )
    db_session.add_all(
        [
            models.JobRun(job_type=JobType.MANUAL_URL_SNAPSHOT, status=JobStatus.FAILED),
            models.JobRun(job_type=JobType.CSV_IMPORT_SNAPSHOT, status=JobStatus.SUCCEEDED),
        ]
    )
    db_session.flush()

    result = health_service.build_data_health(db_session)

    assert result["status"] == "warning"
    assert result["connector_failure_rate"] == pytest.approx(0.5)
    assert result["listing_parse_success_rate"] == pytest.approx(1.0)
    assert result["geometry_confidence_distribution"] == {}
    assert result["extant_permission_unresolved_rate"] is None
    assert result["borough_baseline_coverage"] == {"total": 1, "signed_off": 1, "pilot_ready": 0}
    assert result["coverage"][0]["coverage_status"] == "PARTIAL"
    assert result["coverage"][0]["coverage_note"] == "partial borough coverage"


def test_build_model_health_warns_on_not_ready_release_and_manual_review_metrics(
    db_session,
) -> None:
    cluster = _make_listing_cluster(db_session, cluster_key="cluster-health")
    site = _make_site_candidate(db_session, cluster=cluster, display_name="Health Site")
    scenario = _make_site_scenario(
        db_session,
        site=site,
        template_key="template-health",
        red_line_geom_hash=_sha("red-line"),
    )
    release = _make_release(
        db_session,
        template_key="template-health",
        scope_key="scope-health",
        status=ModelReleaseStatus.NOT_READY,
    )
    scope = _make_active_scope(
        db_session,
        release=release,
        scope_key="scope-health",
        borough_id="E09000006",
        visibility_mode=VisibilityMode.VISIBLE_REVIEWER_ONLY,
        visibility_reason="pilot visible scope",
    )

    assessment_run_one = models.AssessmentRun(
        site_id=site.id,
        scenario_id=scenario.id,
        as_of_date=date(2026, 4, 18),
        idempotency_key="health-assessment-run-1",
    )
    assessment_run_two = models.AssessmentRun(
        site_id=site.id,
        scenario_id=scenario.id,
        as_of_date=date(2026, 4, 18),
        idempotency_key="health-assessment-run-2",
    )
    db_session.add_all([assessment_run_one, assessment_run_two])
    db_session.flush()

    result_one = models.AssessmentResult(
        assessment_run_id=assessment_run_one.id,
        model_release_id=release.id,
        release_scope_key=scope.scope_key,
        eligibility_status=EligibilityStatus.PASS,
        approval_probability_raw=0.82,
        approval_probability_display="HIGH",
        manual_review_required=True,
        ood_status="OUT_OF_SUPPORT",
        result_json={
            "validation_summary": {
                "metrics": {
                    "brier_score": 0.2,
                    "log_loss": 0.3,
                    "calibration_by_band": [
                        {"band": "HIGH", "observed_rate": 1.0, "predicted_rate": 0.8}
                    ],
                }
            }
        },
    )
    result_two = models.AssessmentResult(
        assessment_run_id=assessment_run_two.id,
        model_release_id=release.id,
        release_scope_key=scope.scope_key,
        eligibility_status=EligibilityStatus.ABSTAIN,
        approval_probability_raw=0.31,
        approval_probability_display="LOW",
        manual_review_required=True,
        ood_status="IN_SUPPORT",
        result_json={
            "validation_summary": {
                "metrics": {
                    "brier_score": 0.4,
                    "log_loss": 0.5,
                    "calibration_by_band": [
                        {"band": "LOW", "observed_rate": 0.0, "predicted_rate": 0.2}
                    ],
                }
            }
        },
    )
    db_session.add_all([result_one, result_two])
    db_session.add(
        models.AssessmentOverride(
            assessment_run_id=assessment_run_one.id,
            override_type=AssessmentOverrideType.REVIEW_DISPOSITION,
            status=AssessmentOverrideStatus.ACTIVE,
            actor_name="reviewer@example.com",
            actor_role=AppRoleName.REVIEWER.value,
            reason="resolved manually in fixture",
            override_json={"resolve_manual_review": True},
        )
    )
    db_session.flush()

    result = health_service.build_model_health(db_session)

    assert result["status"] == "warning"
    assert result["brier_score"] == pytest.approx(0.3)
    assert result["log_loss"] == pytest.approx(0.4)
    assert result["false_positive_reviewer_rate"] == pytest.approx(0.5)
    assert result["abstain_rate"] == pytest.approx(0.5)
    assert result["ood_rate"] == pytest.approx(0.5)
    assert result["economic_health"]["total"] == 0
    assert result["releases"][0]["status"] == "NOT_READY"
    assert (
        result["active_scopes"][0]["visibility_mode"] == VisibilityMode.VISIBLE_REVIEWER_ONLY.value
    )

    bands = {entry["band"]: entry for entry in result["manual_review_agreement_by_band"]}
    assert bands["HIGH"]["completed"] == 1
    assert bands["LOW"]["completed"] == 0
    assert bands["HIGH"]["agreement_rate"] == pytest.approx(1.0)
    assert bands["LOW"]["agreement_rate"] == pytest.approx(0.0)

    performance = result["template_level_performance"][0]
    assert performance["template_key"] == "template-health"
    assert performance["count"] == 2
    assert performance["brier_score"] == pytest.approx(0.3)
    assert performance["log_loss"] == pytest.approx(0.4)
    assert performance["ood_rate"] == pytest.approx(0.5)
