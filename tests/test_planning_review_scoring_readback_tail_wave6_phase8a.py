from __future__ import annotations

import json
from datetime import UTC, date, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from landintel.domain import models
from landintel.domain.enums import (
    AppRoleName,
    AssessmentRunState,
    BaselinePackStatus,
    CalibrationMethod,
    EvidenceImportance,
    IncidentStatus,
    IncidentType,
    ModelReleaseStatus,
    ReleaseChannel,
    SourceClass,
    SourceCoverageStatus,
    SourceFreshnessStatus,
    SourceParseStatus,
    VisibilityMode,
)
from landintel.domain.schemas import AssessmentListResponse, AssessmentSummaryRead
from landintel.planning import enrich as enrich_service
from landintel.planning import historical_labels as historical_labels_service
from landintel.planning import import_common as import_common_service
from landintel.planning.constants import (
    SOURCE_FAMILY_BOROUGH_REGISTER,
    SOURCE_FAMILY_PRIOR_APPROVAL,
)
from landintel.planning.planning_register_normalize import import_borough_register_fixture
from landintel.review import overrides as overrides_service
from landintel.review import visibility as visibility_service
from landintel.scoring import release as scoring_release
from landintel.scoring import train as scoring_train
from landintel.services import assessments_readback, listings_readback
from sqlalchemy import select


class _MemoryStorage:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bytes, str | None]] = []

    def put_bytes(self, path: str, content: bytes, content_type: str | None = None) -> None:
        self.calls.append((path, content, content_type))


class _QueryResult:
    def __init__(self, *, rows=None, scalar=None):
        self._rows = list(rows or [])
        self._scalar = scalar

    def scalars(self):
        return self

    def unique(self):
        return self

    def all(self):
        return self._rows

    def scalar_one_or_none(self):
        return self._scalar

    def scalar_one(self):
        return self._scalar


class _QueuedSession:
    def __init__(self, *responses, get_result=None):
        self._responses = list(responses)
        self.added: list[object] = []
        self.flushed = 0
        self.get_result = get_result

    def execute(self, *args, **kwargs):
        del args, kwargs
        if not self._responses:
            raise AssertionError("Unexpected execute() call with no queued response.")
        return self._responses.pop(0)

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        self.flushed += 1

    def get(self, *args, **kwargs):
        del args, kwargs
        return self.get_result


class _PointGeometry:
    def __init__(self, distance_m: float) -> None:
        self.geom_type = "Point"
        self._distance_m = distance_m

    def within(self, _other: object) -> bool:
        return False

    def intersects(self, _other: object) -> bool:
        return False

    def distance(self, _other: object) -> float:
        return self._distance_m


def _fake_geometry_result() -> SimpleNamespace:
    return SimpleNamespace(geom_27700_wkt="POLYGON((0 0, 10 0, 10 10, 0 10, 0 0))", geom_4326={})


def _make_source_snapshot(
    *,
    source_family: str = "planning",
    source_name: str = "Planning test snapshot",
    coverage_note: str = "fixture coverage note",
    parse_status: SourceParseStatus = SourceParseStatus.PARSED,
) -> models.SourceSnapshot:
    return models.SourceSnapshot(
        id=uuid4(),
        source_family=source_family,
        source_name=source_name,
        source_uri="file:///tmp/source.json",
        schema_hash="a" * 64,
        content_hash="b" * 64,
        coverage_note=coverage_note,
        freshness_status=SourceFreshnessStatus.FRESH,
        parse_status=parse_status,
        manifest_json={"source_family": source_family},
    )


def _make_boundary(*, source_snapshot_id: UUID, boundary_id: str = "camden") -> models.LpaBoundary:
    return models.LpaBoundary(
        id=boundary_id,
        name="Camden",
        geom_27700="POLYGON((0 0, 100 0, 100 100, 0 100, 0 0))",
        geom_4326={},
        geom_hash="c" * 64,
        area_sqm=10_000.0,
        source_snapshot_id=source_snapshot_id,
    )


def _make_release(
    *,
    scope_key: str,
    template_key: str = "resi_5_9_full",
    borough_id: str = "camden",
    status: ModelReleaseStatus = ModelReleaseStatus.VALIDATED,
) -> models.ModelRelease:
    return models.ModelRelease(
        id=uuid4(),
        template_key=template_key,
        release_channel=ReleaseChannel.HIDDEN,
        scope_key=scope_key,
        scope_borough_id=borough_id,
        status=status,
        model_kind="REGULARIZED_LOGISTIC_REGRESSION",
        transform_version="v1",
        feature_version="phase8a_v1",
        calibration_method=CalibrationMethod.NONE,
        model_artifact_path=None,
        model_artifact_hash=None,
        calibration_artifact_path=None,
        calibration_artifact_hash=None,
        validation_artifact_path=None,
        validation_artifact_hash=None,
        model_card_path=None,
        model_card_hash=None,
        support_count=0,
        positive_count=0,
        negative_count=0,
        metrics_json={},
        manifest_json={},
    )


def _seed_scope_with_release(
    db_session,
    *,
    scope_key: str,
    borough_id: str = "camden",
    template_key: str = "resi_5_9_full",
) -> tuple[models.ModelRelease, models.ActiveReleaseScope]:
    release = _make_release(scope_key=scope_key, borough_id=borough_id, template_key=template_key)
    scope = models.ActiveReleaseScope(
        scope_key=scope_key,
        template_key=template_key,
        release_channel=release.release_channel,
        borough_id=borough_id,
        model_release_id=release.id,
    )
    db_session.add_all([release, scope])
    db_session.flush()
    return release, scope


def _summary_model(*, row_id: UUID) -> AssessmentSummaryRead:
    return AssessmentSummaryRead.model_construct(
        id=row_id,
        site_id=uuid4(),
        scenario_id=uuid4(),
        as_of_date=date(2026, 4, 18),
        state=AssessmentRunState.READY,
        idempotency_key="fixture-key",
        requested_by="pytest",
        created_at=datetime(2026, 4, 18, tzinfo=UTC),
        updated_at=datetime(2026, 4, 18, tzinfo=UTC),
    )


def test_planning_register_import_covers_prior_approval_duplication_and_document_rows(
    db_session,
    tmp_path,
    monkeypatch,
) -> None:
    bootstrap_snapshot = _make_source_snapshot()
    db_session.add(bootstrap_snapshot)
    db_session.flush()
    db_session.add(_make_boundary(source_snapshot_id=bootstrap_snapshot.id))
    db_session.flush()

    fixture_path = tmp_path / "borough_register_fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "meta": {
                    "coverage_note": "meta coverage note",
                    "freshness_status": "STALE",
                    "coverage": [
                        {
                            "borough_id": "camden",
                            "source_family": SOURCE_FAMILY_BOROUGH_REGISTER,
                            "coverage_status": "PARTIAL",
                            "gap_reason": "Missing committee PDF archive.",
                        }
                    ],
                },
                "applications": [
                    {
                        "borough_id": "camden",
                        "external_ref": "CAM/2026/0001/FUL",
                        "application_type": "FULL",
                        "proposal_description": "Residential conversion for the fixture import.",
                        "valid_date": "2026-04-01",
                        "decision_date": "2026-04-02",
                        "decision": "APPROVED",
                        "decision_type": "COMMITTEE",
                        "status": "VALIDATED",
                        "route_normalized": "FULL",
                        "units_proposed": "12",
                        "source_url": "https://example.test/CAM/2026/0001/FUL",
                        "geometry_4326": {"type": "Polygon", "coordinates": []},
                        "documents": [
                            {
                                "doc_url": "https://example.test/doc-1.pdf",
                                "doc_type": "committee-report",
                                "mime_type": "application/pdf",
                                "content_text": "Committee report text.",
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    storage = _MemoryStorage()
    monkeypatch.setattr(
        import_common_service,
        "normalize_geojson_geometry",
        lambda **_kwargs: _fake_geometry_result(),
    )

    result = import_borough_register_fixture(
        session=db_session,
        storage=storage,
        fixture_path=fixture_path,
        requested_by="pytest",
    )

    assert result.coverage_count == 2
    assert result.imported_count == 1
    assert bootstrap_snapshot.coverage_note == "fixture coverage note"
    assert bootstrap_snapshot.freshness_status == SourceFreshnessStatus.FRESH

    coverage_rows = db_session.execute(
        select(models.SourceCoverageSnapshot).order_by(models.SourceCoverageSnapshot.source_family)
    ).scalars().all()
    assert {row.source_family for row in coverage_rows} == {
        SOURCE_FAMILY_BOROUGH_REGISTER,
        SOURCE_FAMILY_PRIOR_APPROVAL,
    }
    assert {row.coverage_status for row in coverage_rows} == {SourceCoverageStatus.PARTIAL}

    application = db_session.execute(select(models.PlanningApplication)).scalar_one()
    assert application.external_ref == "CAM/2026/0001/FUL"
    assert application.source_system == "BOROUGH_REGISTER"
    assert application.site_geom_27700 == "POLYGON((0 0, 10 0, 10 10, 0 10, 0 0))"

    document = db_session.execute(select(models.PlanningApplicationDocument)).scalar_one()
    assert document.doc_url == "https://example.test/doc-1.pdf"
    assert document.doc_type == "committee-report"
    assert document.asset_id is not None
    assert len(storage.calls) == 2


def test_import_common_reference_layer_creation_branches(db_session, monkeypatch) -> None:
    source_snapshot = _make_source_snapshot(source_family="planning_reference")
    db_session.add(source_snapshot)
    db_session.flush()
    db_session.add(_make_boundary(source_snapshot_id=source_snapshot.id))
    db_session.flush()

    monkeypatch.setattr(
        import_common_service,
        "normalize_geojson_geometry",
        lambda **_kwargs: _fake_geometry_result(),
    )

    brownfield_imported = import_common_service.upsert_brownfield_rows(
        session=db_session,
        source_snapshot=source_snapshot,
        features=[
            {
                "geometry": {"type": "Polygon", "coordinates": []},
                "properties": {
                    "borough_id": "camden",
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
    policy_imported = import_common_service.upsert_policy_area_rows(
        session=db_session,
        source_snapshot=source_snapshot,
        features=[
            {
                "geometry": {"type": "Polygon", "coordinates": []},
                "properties": {
                    "borough_id": "camden",
                    "policy_family": "design",
                    "policy_code": "D1",
                    "name": "Design policy",
                    "source_class": SourceClass.AUTHORITATIVE.value,
                },
            }
        ],
    )
    constraint_imported = import_common_service.upsert_constraint_rows(
        session=db_session,
        source_snapshot=source_snapshot,
        features=[
            {
                "geometry": {"type": "Polygon", "coordinates": []},
                "properties": {
                    "feature_family": "heritage",
                    "feature_subtype": "listed_building",
                    "external_ref": "C-001",
                    "authority_level": "BOROUGH",
                },
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
                "status": BaselinePackStatus.SIGNED_OFF.value,
                "freshness_status": SourceFreshnessStatus.FRESH.value,
                "signed_off_by": "analyst",
                "signed_off_at": "2026-04-18T10:00:00Z",
                "pack_json": {"pilot": True},
                "rulepacks": [
                    {
                        "template_key": "resi_5_9_full",
                        "status": BaselinePackStatus.SIGNED_OFF.value,
                        "freshness_status": SourceFreshnessStatus.FRESH.value,
                        "rule_json": {"enabled": True},
                    }
                ],
            }
        ],
    )

    assert brownfield_imported == 1
    assert policy_imported == 1
    assert constraint_imported == 1
    assert baseline_imported == 1
    db_session.flush()

    brownfield = db_session.execute(select(models.BrownfieldSiteState)).scalar_one()
    assert brownfield.external_ref == "BF-001"
    assert brownfield.part == "PART_1"

    policy = db_session.execute(select(models.PolicyArea)).scalar_one()
    assert policy.policy_code == "D1"
    assert policy.source_class == SourceClass.AUTHORITATIVE

    constraint = db_session.execute(select(models.PlanningConstraintFeature)).scalar_one()
    assert constraint.feature_subtype == "listed_building"

    pack = db_session.execute(select(models.BoroughBaselinePack)).scalar_one()
    assert pack.status == BaselinePackStatus.SIGNED_OFF
    rulepack = db_session.execute(select(models.BoroughRulepack)).scalar_one()
    assert rulepack.template_key == "resi_5_9_full"
    assert rulepack.status == BaselinePackStatus.SIGNED_OFF


def test_existing_row_and_fallback_branches_cover_remaining_tails(
    db_session,
    tmp_path,
    monkeypatch,
) -> None:
    source_snapshot = _make_source_snapshot(source_family="planning_existing")
    db_session.add(source_snapshot)
    db_session.flush()
    db_session.add(_make_boundary(source_snapshot_id=source_snapshot.id))
    db_session.flush()

    monkeypatch.setattr(
        import_common_service,
        "normalize_geojson_geometry",
        lambda **_kwargs: _fake_geometry_result(),
    )

    fixture_path = tmp_path / "borough_register_existing_fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "meta": {
                    "coverage_note": "meta coverage note",
                    "freshness_status": "STALE",
                    "coverage": [
                        {
                            "borough_id": "camden",
                            "source_family": SOURCE_FAMILY_BOROUGH_REGISTER,
                            "coverage_status": "PARTIAL",
                        },
                        {
                            "borough_id": "camden",
                            "source_family": SOURCE_FAMILY_PRIOR_APPROVAL,
                            "coverage_status": "COMPLETE",
                        },
                    ],
                },
                "applications": [
                    {
                        "borough_id": "camden",
                        "external_ref": "CAM/2026/0002/FUL",
                        "application_type": "FULL",
                        "proposal_description": (
                            "Residential conversion for the existing-row import."
                        ),
                        "valid_date": "2026-04-03",
                        "decision_date": "2026-04-04",
                        "decision": "APPROVED",
                        "decision_type": "COMMITTEE",
                        "status": "VALIDATED",
                        "route_normalized": "FULL",
                        "units_proposed": "8",
                        "source_url": "https://example.test/CAM/2026/0002/FUL",
                        "geometry_4326": {"type": "Polygon", "coordinates": []},
                        "point_4326": {"type": "Point", "coordinates": []},
                        "documents": [
                            {
                                "doc_url": "https://example.test/doc-existing.pdf",
                                "doc_type": "committee-report",
                                "mime_type": "application/pdf",
                                "content_text": "Committee report text.",
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    first_register = import_borough_register_fixture(
        session=db_session,
        storage=_MemoryStorage(),
        fixture_path=fixture_path,
        requested_by="pytest",
    )
    second_storage = _MemoryStorage()
    second_register = import_borough_register_fixture(
        session=db_session,
        storage=second_storage,
        fixture_path=fixture_path,
        requested_by="pytest",
    )
    assert first_register.coverage_count == 2
    assert second_register.coverage_count == 2
    assert second_register.imported_count == 1

    app_payload = {
        "borough_id": "camden",
        "external_ref": "CAM/2026/0003/FUL",
        "application_type": "FULL",
        "proposal_description": "Second pass application payload.",
        "valid_date": "2026-04-05",
        "decision_date": "2026-04-06",
        "decision": "APPROVED",
        "decision_type": "COMMITTEE",
        "status": "VALIDATED",
        "route_normalized": "FULL",
        "units_proposed": "6",
        "source_url": "https://example.test/CAM/2026/0003/FUL",
        "geometry_4326": {"type": "Polygon", "coordinates": []},
        "point_4326": {"type": "Point", "coordinates": []},
        "documents": [
            {
                "doc_url": "https://example.test/doc-existing-2.pdf",
                "doc_type": "committee-report",
                "mime_type": "application/pdf",
                "content_text": "Committee report text.",
            }
        ],
    }
    import_common_service.upsert_planning_application_rows(
        session=db_session,
        storage=_MemoryStorage(),
        dataset_key="planning-existing",
        source_snapshot=source_snapshot,
        source_system="BOROUGH_REGISTER",
        source_priority=10,
        applications=[app_payload],
    )
    import_common_service.upsert_planning_application_rows(
        session=db_session,
        storage=_MemoryStorage(),
        dataset_key="planning-existing",
        source_snapshot=source_snapshot,
        source_system="BOROUGH_REGISTER",
        source_priority=10,
        applications=[app_payload],
    )

    brownfield_payload = {
        "geometry": {"type": "Polygon", "coordinates": []},
        "properties": {
            "borough_id": "camden",
            "external_ref": "BF-002",
            "part": "PART_2",
            "pip_status": "PIP",
            "tdc_status": "TDC",
            "effective_from": "2026-04-07",
            "effective_to": "2026-05-07",
        },
    }
    import_common_service.upsert_brownfield_rows(
        session=db_session,
        source_snapshot=source_snapshot,
        features=[brownfield_payload],
    )
    db_session.flush()
    import_common_service.upsert_brownfield_rows(
        session=db_session,
        source_snapshot=source_snapshot,
        features=[brownfield_payload],
    )

    policy_payload = {
        "geometry": {"type": "Polygon", "coordinates": []},
        "properties": {
            "borough_id": "camden",
            "policy_family": "design",
            "policy_code": "D2",
            "name": "Design policy two",
            "source_class": SourceClass.AUTHORITATIVE.value,
        },
    }
    import_common_service.upsert_policy_area_rows(
        session=db_session,
        source_snapshot=source_snapshot,
        features=[policy_payload],
    )
    db_session.flush()
    import_common_service.upsert_policy_area_rows(
        session=db_session,
        source_snapshot=source_snapshot,
        features=[policy_payload],
    )

    constraint_payload = {
        "geometry": {"type": "Polygon", "coordinates": []},
        "properties": {
            "feature_family": "heritage",
            "feature_subtype": "listed_building",
            "external_ref": "C-002",
            "authority_level": "BOROUGH",
        },
    }
    import_common_service.upsert_constraint_rows(
        session=db_session,
        source_snapshot=source_snapshot,
        features=[constraint_payload],
    )
    db_session.flush()
    import_common_service.upsert_constraint_rows(
        session=db_session,
        source_snapshot=source_snapshot,
        features=[constraint_payload],
    )

    pack_payload = {
        "borough_id": "camden",
        "version": "2026-05",
        "status": BaselinePackStatus.SIGNED_OFF.value,
        "freshness_status": SourceFreshnessStatus.FRESH.value,
        "signed_off_by": "analyst",
        "signed_off_at": "2026-04-18T10:00:00Z",
        "pack_json": {"pilot": True},
        "rulepacks": [
            {
                "template_key": "resi_5_9_full",
                "status": BaselinePackStatus.SIGNED_OFF.value,
                "freshness_status": SourceFreshnessStatus.FRESH.value,
                "rule_json": {"enabled": True},
            }
        ],
    }
    import_common_service.upsert_baseline_pack_rows(
        session=db_session,
        source_snapshot=source_snapshot,
        baseline_packs=[pack_payload],
    )
    db_session.flush()
    import_common_service.upsert_baseline_pack_rows(
        session=db_session,
        source_snapshot=source_snapshot,
        baseline_packs=[pack_payload],
    )

    db_session.flush()
    assert db_session.execute(select(models.PlanningApplication)).scalars().all()
    assert db_session.execute(select(models.BrownfieldSiteState)).scalars().all()
    assert db_session.execute(select(models.PolicyArea)).scalars().all()
    assert db_session.execute(select(models.PlanningConstraintFeature)).scalars().all()
    assert db_session.execute(select(models.BoroughBaselinePack)).scalars().all()
    assert db_session.execute(select(models.BoroughRulepack)).scalars().all()
    assert db_session.execute(select(models.PlanningApplicationDocument)).scalars().all()

    visible_scope_key = "scope-no-rollback"
    _, visible_scope = _seed_scope_with_release(
        db_session,
        scope_key=visible_scope_key,
        borough_id="camden",
        template_key="resi_10_49_outline",
    )
    visible_scope.visibility_mode = VisibilityMode.DISABLED
    visible_incident = models.IncidentRecord(
        active_release_scope_id=visible_scope.id,
        scope_key=visible_scope_key,
        template_key="resi_10_49_outline",
        incident_type=IncidentType.VISIBILITY_KILL_SWITCH,
        status=IncidentStatus.OPEN,
        reason="Do not rollback visibility.",
        previous_visibility_mode=VisibilityMode.VISIBLE_REVIEWER_ONLY,
        applied_visibility_mode=VisibilityMode.DISABLED,
        created_by="pytest",
    )
    db_session.add(visible_incident)
    db_session.flush()
    resolved = visibility_service.resolve_scope_incident(
        session=db_session,
        scope_key=visible_scope_key,
        requested_by="pytest-no-rollback",
        actor_role=AppRoleName.ADMIN,
        reason="Resolve without visibility rollback.",
        rollback_visibility=False,
    )
    assert resolved.id == visible_incident.id
    assert resolved.status == IncidentStatus.RESOLVED
    assert visible_scope.visibility_mode == VisibilityMode.DISABLED
    assert visible_scope.visible_enabled_by is None

    class _ActivationSession:
        def __init__(self) -> None:
            self.added: list[object] = []

        def get(self, model, ident):
            if model is models.ModelRelease and ident == active_release.id:
                return active_release
            if model is models.ModelRelease and ident == missing_prior_release.id:
                return None
            return None

        def execute(self, *_args, **_kwargs):
            return _QueryResult(scalar=existing_scope)

        def add(self, obj):
            self.added.append(obj)

        def flush(self):
            return None

    active_release = _make_release(scope_key="scope-activate-no-prior")
    missing_prior_release = _make_release(scope_key="scope-activate-no-prior")
    existing_scope = SimpleNamespace(
        scope_key=active_release.scope_key,
        model_release_id=missing_prior_release.id,
        template_key=active_release.template_key,
        release_channel=active_release.release_channel,
        borough_id=active_release.scope_borough_id,
    )
    activation_session = _ActivationSession()
    activation_session.added.append(active_release)
    activation_session.added.append(missing_prior_release)
    activated = scoring_release.activate_model_release(
        session=activation_session,
        release_id=active_release.id,
        requested_by="pytest",
    )
    assert activated is existing_scope
    assert active_release.status == ModelReleaseStatus.ACTIVE

    monkeypatch.setattr(
        assessments_readback,
        "serialize_assessment_summary",
        lambda **kwargs: _summary_model(row_id=kwargs["run"].id),
    )
    site_only_row = SimpleNamespace(id=uuid4(), site_id=uuid4(), scenario_id=uuid4())
    scenario_only_row = SimpleNamespace(id=uuid4(), site_id=uuid4(), scenario_id=uuid4())
    site_only_session = _QueuedSession(
        _QueryResult(scalar=1),
        _QueryResult(rows=[site_only_row]),
    )
    scenario_only_session = _QueuedSession(
        _QueryResult(scalar=1),
        _QueryResult(rows=[scenario_only_row]),
    )
    assessments_readback.list_assessments(
        session=site_only_session,
        site_id=uuid4(),
        limit=10,
        offset=0,
    )
    assessments_readback.list_assessments(
        session=scenario_only_session,
        scenario_id=uuid4(),
        limit=10,
        offset=0,
    )


def test_planning_enrich_historical_labels_and_listing_snapshot_branches(
    monkeypatch,
    db_session,
) -> None:
    assert enrich_service.get_borough_baseline_pack(session=db_session, borough_id=None) is None

    monkeypatch.setattr(
        enrich_service,
        "load_wkt_geometry",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("bad wkt")),
    )
    assert (
        enrich_service._intersects_geometry(
            SimpleNamespace(intersects=lambda _other: True),
            "bad",
        )
        is False
    )
    assert (
        enrich_service._importance_from_record(
            None,
            default=EvidenceImportance.LOW,
        )
        == EvidenceImportance.LOW
    )
    assert (
        enrich_service._importance_from_record(
            {"severity": None},
            default=EvidenceImportance.HIGH,
        )
        == EvidenceImportance.HIGH
    )

    monkeypatch.setattr(
        historical_labels_service,
        "planning_application_geometry",
        lambda application: application._geometry,
    )

    def _make_application(*, description: str, geometry: _PointGeometry) -> SimpleNamespace:
        return SimpleNamespace(
            borough_id="camden",
            units_proposed=12,
            route_normalized="FULL",
            application_type="FULL",
            valid_date=date(2026, 1, 1),
            proposal_description=description,
            _geometry=geometry,
        )

    close_geometry = _PointGeometry(distance_m=20.0)
    candidate_close = _make_application(
        description="Provide residential homes for the fixture scheme.",
        geometry=close_geometry,
    )
    stronger_close = _make_application(
        description="Provide residential homes for the fixture scheme.",
        geometry=close_geometry,
    )
    assert historical_labels_service._same_case(candidate_close, stronger_close) is True

    far_geometry = _PointGeometry(distance_m=40.0)
    candidate_far = _make_application(
        description="Provide residential homes for the fixture scheme.",
        geometry=far_geometry,
    )
    stronger_far = _make_application(
        description="Provide residential homes for the fixture scheme.",
        geometry=far_geometry,
    )
    assert historical_labels_service._same_case(candidate_far, stronger_far) is True

    snapshot = SimpleNamespace(id=uuid4())
    item = SimpleNamespace(current_snapshot_id=None, snapshots=[snapshot])
    assert listings_readback._current_snapshot_for(item) is snapshot


def test_assessments_readback_branch_and_release_helper_branches(monkeypatch, db_session) -> None:
    rows = [SimpleNamespace(id=uuid4(), site_id=uuid4(), scenario_id=uuid4())]
    session = _QueuedSession(_QueryResult(scalar=1), _QueryResult(rows=rows))
    monkeypatch.setattr(
        assessments_readback,
        "serialize_assessment_summary",
        lambda **kwargs: _summary_model(row_id=kwargs["run"].id),
    )

    response = assessments_readback.list_assessments(
        session=session,
        site_id=rows[0].site_id,
        scenario_id=rows[0].scenario_id,
        limit=10,
        offset=0,
    )
    assert isinstance(response, AssessmentListResponse)
    assert response.total == 1
    assert response.items[0].id == rows[0].id

    assert scoring_train._nearest_neighbor_distance([1.0, 2.0], []) is None
    assert scoring_train._percentile([], 0.5) == 0.0

    release_id = uuid4()
    release = SimpleNamespace(id=release_id)
    fallback_release = SimpleNamespace(id=uuid4())

    class _OverrideSession:
        def get(self, model, ident):
            if model is models.ValuationRun and ident == fallback_release.id:
                return fallback_release
            return None

    monkeypatch.setattr(
        overrides_service,
        "frozen_valuation_run",
        lambda assessment_run: SimpleNamespace(
            id=uuid4(),
            source="frozen",
            assessment_run=assessment_run,
        ),
    )

    assessment_run = SimpleNamespace(
        valuation_runs=[release],
        result=SimpleNamespace(),
    )
    override = SimpleNamespace(override_json={"valuation_run_id": str(release.id)})
    resolved = overrides_service._resolve_effective_valuation_run(
        session=_OverrideSession(),
        assessment_run=assessment_run,
        assumption_override=override,
    )
    assert resolved is release

    assessment_run_without_match = SimpleNamespace(valuation_runs=[], result=SimpleNamespace())
    fallback_override = SimpleNamespace(
        override_json={"valuation_run_id": str(fallback_release.id)}
    )
    resolved_fallback = overrides_service._resolve_effective_valuation_run(
        session=_OverrideSession(),
        assessment_run=assessment_run_without_match,
        assumption_override=fallback_override,
    )
    assert resolved_fallback is fallback_release

    non_string_override = SimpleNamespace(override_json={"valuation_run_id": 123})
    frozen_non_string = overrides_service._resolve_effective_valuation_run(
        session=_OverrideSession(),
        assessment_run=assessment_run_without_match,
        assumption_override=non_string_override,
    )
    assert frozen_non_string.source == "frozen"

    frozen = overrides_service._resolve_effective_valuation_run(
        session=_OverrideSession(),
        assessment_run=assessment_run_without_match,
        assumption_override=None,
    )
    assert frozen.source == "frozen"

    scope_key = "scope-rollback-visible"
    _, rollback_scope = _seed_scope_with_release(
        db_session,
        scope_key=scope_key,
        borough_id="camden",
        template_key="resi_10_49_outline",
    )
    rollback_scope.visibility_mode = VisibilityMode.DISABLED
    rollback_incident = models.IncidentRecord(
        active_release_scope_id=rollback_scope.id,
        scope_key=scope_key,
        template_key="resi_10_49_outline",
        incident_type=IncidentType.VISIBILITY_KILL_SWITCH,
        status=IncidentStatus.OPEN,
        reason="Rollback after reviewer-visible toggle.",
        previous_visibility_mode=VisibilityMode.VISIBLE_REVIEWER_ONLY,
        applied_visibility_mode=VisibilityMode.DISABLED,
        created_by="pytest",
    )
    db_session.add(rollback_incident)
    db_session.flush()

    resolved_incident = visibility_service.resolve_scope_incident(
        session=db_session,
        scope_key=scope_key,
        requested_by="pytest-rollback",
        actor_role=AppRoleName.ADMIN,
        reason="Restore the previous reviewer-visible mode.",
        rollback_visibility=True,
    )
    assert resolved_incident.id == rollback_incident.id
    assert resolved_incident.status == IncidentStatus.RESOLVED
    assert rollback_scope.visibility_mode == VisibilityMode.VISIBLE_REVIEWER_ONLY
    assert rollback_scope.visibility_reason == "Restore the previous reviewer-visible mode."
    assert rollback_scope.visibility_updated_by == "pytest-rollback"
    assert rollback_scope.visible_enabled_by == "pytest-rollback"
    assert rollback_scope.visible_enabled_at is not None

    existing_release = _make_release(scope_key="scope-existing")
    existing_scope = models.ActiveReleaseScope(
        scope_key="scope-existing",
        template_key=existing_release.template_key,
        release_channel=existing_release.release_channel,
        borough_id="camden",
        model_release_id=existing_release.id,
    )
    successor_release = _make_release(scope_key="scope-existing")
    db_session.add_all([existing_release, existing_scope, successor_release])
    db_session.flush()
    activated_scope = scoring_release.activate_model_release(
        session=db_session,
        release_id=successor_release.id,
        requested_by="pytest",
    )
    assert activated_scope.model_release_id == successor_release.id
    assert existing_release.status == ModelReleaseStatus.RETIRED

    fresh_release = _make_release(scope_key="scope-fresh")
    db_session.add(fresh_release)
    db_session.flush()
    fresh_scope = scoring_release.activate_model_release(
        session=db_session,
        release_id=fresh_release.id,
        requested_by="pytest",
    )
    assert fresh_scope.model_release_id == fresh_release.id

    with pytest.raises(ValueError, match="was not found"):
        scoring_release.retire_model_release(
            session=db_session,
            release_id=uuid4(),
            requested_by="pytest",
        )

    template = SimpleNamespace(key="resi_5_9_full")
    existing_template_release = SimpleNamespace(id=uuid4())
    release_lookup_id = existing_template_release.id

    class _ReleaseSession:
        def get(self, model, ident):
            if model is models.ModelRelease and ident == release_lookup_id:
                return existing_template_release
            return None

    monkeypatch.setattr(scoring_release, "load_training_rows", lambda **_kwargs: [{"row": 1}])
    monkeypatch.setattr(
        scoring_release,
        "build_training_manifest",
        lambda **_kwargs: {
            "payload_hash": "payload-hash",
            "status": "VALIDATED",
            "validation": {"ok": True},
        },
    )
    monkeypatch.setattr(scoring_release, "_release_id", lambda **_kwargs: release_lookup_id)
    assert (
        scoring_release._build_template_release(
            session=_ReleaseSession(),
            storage=SimpleNamespace(),
            template=template,
            requested_by="pytest",
        )
        is existing_template_release
    )
