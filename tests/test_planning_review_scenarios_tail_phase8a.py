from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from landintel.domain.enums import (
    AppRoleName,
    AssessmentOverrideType,
    AuditExportStatus,
    BaselinePackStatus,
    EligibilityStatus,
    ExtantPermissionStatus,
    GeomConfidence,
    HistoricalLabelClass,
    HistoricalLabelDecision,
    PriceBasisType,
    ProposalForm,
    ScenarioSource,
    ScenarioStatus,
    SourceCoverageStatus,
    SourceFreshnessStatus,
    SourceParseStatus,
    ValuationQuality,
    VisibilityMode,
)
from landintel.domain.models import AuditExport, ValuationAssumptionSet
from landintel.domain.schemas import AssessmentOverrideRequest, ScenarioConfirmRequest
from landintel.planning import extant_permission as extant_permission_service
from landintel.planning import historical_labels as historical_labels_service
from landintel.planning import import_common as import_common_service
from landintel.review import audit_export as audit_export_service
from landintel.review import overrides as overrides_service
from landintel.review import visibility as visibility_service
from landintel.review.visibility import ReviewAccessError
from landintel.scenarios import normalize as normalize_service
from landintel.scenarios import suggest as suggest_service


class _MemoryStorage:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bytes, str | None]] = []

    def put_bytes(self, path: str, content: bytes, content_type: str | None = None) -> None:
        self.calls.append((path, content, content_type))


class _FakeGeometry:
    geom_type = "Polygon"

    def __init__(self, *, overlap_area: float = 150.0, distance_m: float = 0.0) -> None:
        self.area = 100.0
        self._overlap_area = overlap_area
        self._distance_m = distance_m

    def intersects(self, _other: object) -> bool:
        return True

    def intersection(self, _other: object) -> SimpleNamespace:
        return SimpleNamespace(area=self._overlap_area)

    def distance(self, _other: object) -> float:
        return self._distance_m


class _FakeResult:
    def __init__(self, value: object) -> None:
        self._value = value

    def scalar_one_or_none(self) -> object:
        return self._value


class _Dumpable:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def model_dump(self, *, mode: str = "json") -> dict[str, object]:
        del mode
        return dict(self.payload)


class _FakeAssessmentDetail:
    def __init__(self, assessment_id: str) -> None:
        self._assessment_id = assessment_id
        self.site_summary = _Dumpable(
            {
                "id": "site-1",
                "borough_id": "camden",
                "display_name": "Camden fixture site",
            }
        )
        self.scenario_summary = _Dumpable(
            {
                "id": "scenario-1",
                "template_key": "resi_5_9_full",
                "status": ScenarioStatus.ANALYST_CONFIRMED.value,
            }
        )
        self.visibility = _Dumpable(
            {
                "scope_key": "scope-1",
                "visibility_mode": VisibilityMode.VISIBLE_REVIEWER_ONLY.value,
                "exposure_mode": "VISIBLE_REVIEWER_ONLY",
            }
        )

    def model_dump(self, *, mode: str = "json") -> dict[str, object]:
        del mode
        return {
            "id": self._assessment_id,
            "site_id": "site-1",
            "scenario_id": "scenario-1",
            "note": "fixture assessment detail",
        }


class _FakeAuditExportSession:
    def __init__(self, assessment_run: object) -> None:
        self._assessment_run = assessment_run
        self._exports: dict[UUID, AuditExport] = {}
        self.added: list[object] = []

    def execute(self, _stmt: object) -> _FakeResult:
        return _FakeResult(self._assessment_run)

    def get(self, model: object, ident: UUID) -> AuditExport | None:
        if model is AuditExport:
            return self._exports.get(ident)
        return None

    def add(self, obj: object) -> None:
        self.added.append(obj)
        if isinstance(obj, AuditExport):
            if obj.created_at is None:
                obj.created_at = datetime.now(UTC)
            self._exports[obj.id] = obj

    def flush(self) -> None:
        return None


def _make_planning_application(
    *,
    external_ref: str,
    source_priority: int,
    decision: str,
    decision_date: date,
    valid_date: date,
    route_normalized: str = "FULL",
    application_type: str = "FULL",
    proposal_description: str = "Fixture residential proposal.",
    units_proposed: int = 8,
    decision_type: str = "FULL_RESIDENTIAL",
    status: str = "APPROVED",
    borough_id: str = "camden",
    source_system: str = "BOROUGH_REGISTER",
    geometry: _FakeGeometry | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        borough_id=borough_id,
        source_system=source_system,
        source_snapshot_id=uuid4(),
        external_ref=external_ref,
        application_type=application_type,
        proposal_description=proposal_description,
        status=status,
        source_priority=source_priority,
        raw_record_json={"dwelling_use": "C3"},
        decision_type=decision_type,
        route_normalized=route_normalized,
        valid_date=valid_date,
        decision_date=decision_date,
        decision=decision,
        units_proposed=units_proposed,
        source_url=f"https://example.test/{external_ref}",
        documents=[SimpleNamespace(asset_id=uuid4())],
        _geometry=geometry or _FakeGeometry(),
        _site_area_sqm=120.0,
    )


def test_import_common_snapshot_and_document_dedupe_branches(tmp_path, db_session) -> None:
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        '{"dataset_meta":{"title":"fixture"},"items":[{"id":1}]}',
        encoding="utf-8",
    )

    storage = _MemoryStorage()
    snapshot, asset, payload = import_common_service.register_dataset_snapshot(
        session=db_session,
        storage=storage,
        fixture_path=fixture_path,
        dataset_key="camden-fixture",
        source_family="borough_register",
        source_name="fixture-source",
        schema_key="schema-v1",
        coverage_note="fixture coverage note",
        freshness_status=SourceFreshnessStatus.FRESH,
        requested_by="pytest",
    )
    duplicate_snapshot, duplicate_asset, duplicate_payload = (
        import_common_service.register_dataset_snapshot(
            session=db_session,
            storage=storage,
            fixture_path=fixture_path,
            dataset_key="camden-fixture",
            source_family="borough_register",
            source_name="fixture-source",
            schema_key="schema-v1",
            coverage_note="fixture coverage note",
            freshness_status=SourceFreshnessStatus.FRESH,
            requested_by="pytest",
        )
    )

    assert snapshot.id == duplicate_snapshot.id
    assert asset.id == duplicate_asset.id
    assert payload == duplicate_payload
    assert snapshot.parse_status == SourceParseStatus.PARSED
    assert len(storage.calls) == 1

    first_asset = import_common_service.store_document_asset(
        session=db_session,
        storage=storage,
        source_snapshot_id=snapshot.id,
        dataset_key="camden-fixture",
        original_url="https://example.test/doc-1.pdf",
        content=b"fixture document",
        mime_type="application/pdf",
    )
    second_asset = import_common_service.store_document_asset(
        session=db_session,
        storage=storage,
        source_snapshot_id=snapshot.id,
        dataset_key="camden-fixture",
        original_url="https://example.test/doc-2.pdf",
        content=b"fixture document",
        mime_type="application/pdf",
    )

    assert first_asset.id == second_asset.id
    assert first_asset.storage_path == second_asset.storage_path
    assert len(storage.calls) == 2


def test_historical_labels_payload_branches_cover_positive_negative_excluded_and_duplicate(
    monkeypatch,
) -> None:
    geometry = _FakeGeometry(overlap_area=200.0)
    source_snapshot_ids = {str(uuid4()), str(uuid4())}

    def _fake_geometry(application: SimpleNamespace) -> _FakeGeometry:
        return application._geometry

    monkeypatch.setattr(historical_labels_service, "planning_application_geometry", _fake_geometry)
    monkeypatch.setattr(
        historical_labels_service, "planning_application_area_sqm", lambda _application: 120.0
    )
    monkeypatch.setattr(
        historical_labels_service,
        "build_designation_profile_for_geometry",
        lambda **_kwargs: ({"brownfield_part1": False}, source_snapshot_ids),
    )
    monkeypatch.setattr(
        historical_labels_service,
        "derive_archetype_key",
        lambda **_kwargs: "resi_5_9_full::fixture",
    )

    stronger_case = _make_planning_application(
        external_ref="CAM/2024/0001/FUL",
        source_priority=200,
        decision="APPROVED",
        decision_date=date(2024, 6, 1),
        valid_date=date(2024, 1, 1),
        geometry=geometry,
    )
    positive_payload = historical_labels_service._build_label_payload(
        session=SimpleNamespace(),
        application=stronger_case,
        stronger_cases=[],
    )
    assert positive_payload["label_class"] == HistoricalLabelClass.POSITIVE
    assert positive_payload["label_decision"] == HistoricalLabelDecision.APPROVE
    assert positive_payload["site_geometry_confidence"] == GeomConfidence.MEDIUM

    duplicate_case = _make_planning_application(
        external_ref="CAM/2024/0002/FUL",
        source_priority=100,
        decision="APPROVED",
        decision_date=date(2024, 6, 1),
        valid_date=date(2024, 1, 10),
        geometry=geometry,
    )
    duplicate_payload = historical_labels_service._build_label_payload(
        session=SimpleNamespace(),
        application=duplicate_case,
        stronger_cases=[stronger_case],
    )
    assert duplicate_payload["label_class"] == HistoricalLabelClass.EXCLUDED
    assert duplicate_payload["label_decision"] == HistoricalLabelDecision.DUPLICATE
    assert "Stronger source" in duplicate_payload["label_reason"]

    negative_case = _make_planning_application(
        external_ref="CAM/2024/0003/FUL",
        source_priority=90,
        decision="REFUSED",
        decision_date=date(2026, 4, 1),
        valid_date=date(2024, 1, 1),
        geometry=geometry,
    )
    negative_payload = historical_labels_service._build_label_payload(
        session=SimpleNamespace(),
        application=negative_case,
        stronger_cases=[],
    )
    assert negative_payload["label_class"] == HistoricalLabelClass.CENSORED
    assert negative_payload["label_decision"] == HistoricalLabelDecision.REFUSE
    assert "18-month label window" in negative_payload["label_reason"]

    prior_approval_case = _make_planning_application(
        external_ref="CAM/2024/0004/PRE",
        source_priority=80,
        decision="APPROVED",
        decision_date=date(2024, 6, 1),
        valid_date=date(2024, 1, 1),
        route_normalized="PRIOR_APPROVAL_EXT",
        application_type="PRIOR_APPROVAL",
        geometry=geometry,
    )
    prior_approval_payload = historical_labels_service._build_label_payload(
        session=SimpleNamespace(),
        application=prior_approval_case,
        stronger_cases=[stronger_case],
    )
    assert prior_approval_payload["label_class"] == HistoricalLabelClass.EXCLUDED
    assert prior_approval_payload["label_decision"] == HistoricalLabelDecision.NON_RELEVANT
    assert "Prior approval" in prior_approval_payload["label_reason"]


def test_extant_permission_brownfield_exclusion_and_informative_paths(monkeypatch) -> None:
    site = SimpleNamespace(
        borough_id="camden",
        geom_27700="POLYGON((0 0, 20 0, 20 20, 0 20, 0 0))",
        site_area_sqm=400.0,
        planning_links=[],
    )
    monkeypatch.setattr(
        extant_permission_service, "load_wkt_geometry", lambda *_args, **_kwargs: _FakeGeometry()
    )
    monkeypatch.setattr(
        extant_permission_service,
        "list_latest_coverage_snapshots",
        lambda **_kwargs: [
            SimpleNamespace(
                source_family="BOROUGH_REGISTER", coverage_status=SourceCoverageStatus.COMPLETE
            ),
            SimpleNamespace(
                source_family="PRIOR_APPROVAL", coverage_status=SourceCoverageStatus.COMPLETE
            ),
            SimpleNamespace(
                source_family="BROWNFIELD", coverage_status=SourceCoverageStatus.COMPLETE
            ),
        ],
    )
    monkeypatch.setattr(
        extant_permission_service,
        "planning_application_snapshot",
        lambda _link: {
            "source_system": "BOROUGH_REGISTER",
            "external_ref": "CAM/2024/0001/FUL",
            "source_url": "https://example.test/CAM/2024/0001/FUL",
            "source_snapshot_id": uuid4(),
            "raw_record_json": {"dwelling_use": "C3", "active_extant": False},
            "route_normalized": "FULL",
            "decision_type": "FULL_RESIDENTIAL",
            "status": "APPROVED",
        },
    )

    active_state = SimpleNamespace(
        id=uuid4(),
        borough_id="camden",
        external_ref="BF-1",
        source_url="https://example.test/bf-1",
        source_snapshot_id=uuid4(),
        geom_27700="POLYGON((0 0, 20 0, 20 20, 0 20, 0 0))",
        part="PART_2",
        pip_status="ACTIVE",
        tdc_status=None,
        effective_from=date(2026, 1, 1),
        effective_to=None,
        raw_record_json={},
    )
    monkeypatch.setattr(
        extant_permission_service,
        "match_generic_geometry",
        lambda **_kwargs: SimpleNamespace(overlap_pct=0.25, overlap_sqm=120.0, distance_m=0.0),
    )
    monkeypatch.setattr(
        extant_permission_service,
        "list_brownfield_states_for_site",
        lambda **_kwargs: [active_state],
    )

    active = extant_permission_service.evaluate_site_extant_permission(
        session=SimpleNamespace(),
        site=site,
        as_of_date=date(2026, 4, 18),
    )
    assert active.status == ExtantPermissionStatus.ACTIVE_EXTANT_PERMISSION_FOUND
    assert active.eligibility_status == EligibilityStatus.FAIL
    assert active.matched_records[0].source_kind == "brownfield_state"

    active_state.part = "PART_1"
    active_state.pip_status = None
    active_state.tdc_status = None
    informative = extant_permission_service.evaluate_site_extant_permission(
        session=SimpleNamespace(),
        site=site,
        as_of_date=date(2026, 4, 18),
    )
    assert informative.status == ExtantPermissionStatus.NO_ACTIVE_PERMISSION_FOUND
    assert informative.eligibility_status == EligibilityStatus.PASS
    assert informative.matched_records[0].source_kind == "brownfield_state"
    assert informative.matched_records[0].material is True


def test_visibility_gate_visible_hidden_and_internal_block_redaction(monkeypatch) -> None:
    scope_id = uuid4()
    model_release_id = uuid4()
    result = SimpleNamespace(
        release_scope_key="scope-1",
        approval_probability_raw=0.62,
        approval_probability_display=0.60,
        model_release_id=model_release_id,
    )
    ledger = SimpleNamespace(
        model_artifact_hash="artifact-hash",
        validation_artifact_hash="validation-hash",
        calibration_hash="calibration-hash",
        replay_verification_status="VERIFIED",
        result_payload_hash="payload-hash",
    )
    assessment_run = SimpleNamespace(result=result, prediction_ledger=ledger)
    scope = SimpleNamespace(
        id=scope_id,
        scope_key="scope-1",
        visibility_mode=VisibilityMode.VISIBLE_REVIEWER_ONLY,
        model_release_id=model_release_id,
        model_release=SimpleNamespace(
            model_artifact_hash="artifact-hash",
            validation_artifact_hash="validation-hash",
            calibration_artifact_hash="calibration-hash",
        ),
    )

    monkeypatch.setattr(
        visibility_service, "load_active_scope", lambda _session, *, scope_key: scope
    )
    monkeypatch.setattr(
        visibility_service, "get_open_incident_for_scope", lambda *args, **_kwargs: None
    )
    monkeypatch.setattr(visibility_service, "_payload_hash_matches", lambda _run: True)

    visible = visibility_service.evaluate_assessment_visibility(
        session=SimpleNamespace(),
        assessment_run=assessment_run,
        viewer_role=AppRoleName.REVIEWER,
        include_hidden=False,
    )
    assert visible.exposure_mode == "VISIBLE_REVIEWER_ONLY"
    assert visible.visible_probability_allowed is True
    assert visible.hidden_probability_allowed is False
    assert visible.blocked is False

    hidden = visibility_service.evaluate_assessment_visibility(
        session=SimpleNamespace(),
        assessment_run=assessment_run,
        viewer_role=AppRoleName.ADMIN,
        include_hidden=True,
    )
    assert hidden.exposure_mode == "HIDDEN_INTERNAL"
    assert hidden.hidden_probability_allowed is True
    assert hidden.visible_probability_allowed is False

    monkeypatch.setattr(visibility_service, "_payload_hash_matches", lambda _run: False)
    redacted = visibility_service.evaluate_assessment_visibility(
        session=SimpleNamespace(),
        assessment_run=assessment_run,
        viewer_role=AppRoleName.ANALYST,
        include_hidden=False,
    )
    assert redacted.blocked is True
    assert redacted.blocked_reason_codes == ["OUTPUT_BLOCKED"]
    assert redacted.blocked_reason_text == visibility_service._BLOCK_REASON_TEXT["OUTPUT_BLOCKED"]
    assert redacted.active_incident_id is None


def test_override_payload_summary_and_validation_branches(monkeypatch) -> None:
    assumption_set_id = uuid4()
    assumption_set = SimpleNamespace(id=assumption_set_id, version="2026-04")
    valuation_run = SimpleNamespace(
        id=uuid4(),
        valuation_assumption_set_id=assumption_set_id,
        valuation_assumption_set=SimpleNamespace(version="2026-04"),
        result=SimpleNamespace(
            id=uuid4(),
            post_permission_value_low=180000.0,
            post_permission_value_mid=220000.0,
            post_permission_value_high=250000.0,
            uplift_low=80000.0,
            uplift_mid=120000.0,
            uplift_high=150000.0,
            expected_uplift_mid=30000.0,
            valuation_quality=ValuationQuality.HIGH,
            manual_review_required=False,
            basis_json={"basis_available": True},
            sense_check_json={"ok": True},
            result_json={"flag": "ok"},
            payload_hash="abc",
            created_at=datetime(2026, 4, 18, tzinfo=UTC),
        ),
    )
    run = SimpleNamespace(valuation_runs=[], result=SimpleNamespace(approval_probability_raw=0.25))

    fake_session = SimpleNamespace(
        get=lambda model, ident: assumption_set
        if model is ValuationAssumptionSet and ident == assumption_set_id
        else None
    )
    monkeypatch.setattr(
        overrides_service,
        "build_or_refresh_valuation_for_assessment_with_assumption_set",
        lambda **_kwargs: valuation_run,
    )

    acquisition_request = AssessmentOverrideRequest(
        override_type=AssessmentOverrideType.ACQUISITION_BASIS,
        reason="Manual acquisition basis for fixture run.",
        acquisition_basis_gbp=125000.125,
        acquisition_basis_type=PriceBasisType.GUIDE_PRICE,
        requested_by="pytest",
        actor_role=AppRoleName.ANALYST,
    )
    assert overrides_service._validate_override_role(acquisition_request) == AppRoleName.ANALYST
    acquisition_payload, acquisition_run = overrides_service._build_override_payload(
        session=fake_session,
        run=run,
        request=acquisition_request,
        actor_name="pytest",
    )
    assert acquisition_run is None
    assert acquisition_payload["acquisition_basis_gbp"] == 125000.12
    assert acquisition_payload["acquisition_basis_type"] == PriceBasisType.GUIDE_PRICE.value

    review_request = AssessmentOverrideRequest(
        override_type=AssessmentOverrideType.REVIEW_DISPOSITION,
        reason="Resolve the manual review.",
        resolve_manual_review=True,
        requested_by="pytest",
        actor_role=AppRoleName.REVIEWER,
    )
    assert overrides_service._validate_override_role(review_request) == AppRoleName.REVIEWER
    review_payload, review_run = overrides_service._build_override_payload(
        session=fake_session,
        run=run,
        request=review_request,
        actor_name="pytest",
    )
    assert review_run is None
    assert review_payload["resolve_manual_review"] is True

    assumption_request = AssessmentOverrideRequest(
        override_type=AssessmentOverrideType.VALUATION_ASSUMPTION_SET,
        reason="Use updated valuation assumptions.",
        valuation_assumption_set_id=assumption_set_id,
        requested_by="pytest",
        actor_role=AppRoleName.REVIEWER,
    )
    assumption_payload, assumption_run = overrides_service._build_override_payload(
        session=fake_session,
        run=run,
        request=assumption_request,
        actor_name="pytest",
    )
    assert assumption_run is valuation_run
    assert assumption_payload["valuation_assumption_version"] == "2026-04"
    assert assumption_payload["valuation_run_id"] == str(valuation_run.id)

    serialized = overrides_service._serialize_effective_valuation(
        assessment_run=run,
        valuation_run=valuation_run,
        basis_override=SimpleNamespace(
            override_json={
                "acquisition_basis_gbp": 125000.0,
                "acquisition_basis_type": PriceBasisType.GUIDE_PRICE.value,
            },
            reason="Manual basis",
        ),
    )
    assert serialized is not None
    assert serialized.uplift_mid == 95000.0
    assert serialized.expected_uplift_mid == 23750.0
    assert serialized.basis_json["override_applied"] is True
    assert serialized.basis_json["basis_type"] == PriceBasisType.GUIDE_PRICE.value

    with pytest.raises(ReviewAccessError):
        overrides_service._validate_override_role(
            AssessmentOverrideRequest(
                override_type=AssessmentOverrideType.REVIEW_DISPOSITION,
                reason="Reject analyst role.",
                resolve_manual_review=True,
                requested_by="pytest",
                actor_role=AppRoleName.ANALYST,
            )
        )


def test_audit_export_builds_manifest_once_and_reuses_export(monkeypatch) -> None:
    assessment_id = uuid4()
    valuation_run = SimpleNamespace(id=uuid4())
    run = SimpleNamespace(
        id=assessment_id,
        result=SimpleNamespace(id=uuid4(), model_release_id=uuid4()),
        prediction_ledger=SimpleNamespace(id=uuid4()),
        valuation_runs=[],
        overrides=[],
    )
    fake_session = _FakeAuditExportSession(run)
    monkeypatch.setattr(
        audit_export_service,
        "get_assessment",
        lambda **_kwargs: _FakeAssessmentDetail(str(assessment_id)),
    )
    monkeypatch.setattr(
        audit_export_service,
        "frozen_valuation_run",
        lambda assessment_run: valuation_run if assessment_run.id == assessment_id else None,
    )
    monkeypatch.setattr(
        audit_export_service,
        "_serialize_audit_events",
        lambda **_kwargs: [
            {
                "id": "event-1",
                "action": "assessment_override_created",
                "entity_type": "assessment_run",
                "entity_id": str(assessment_id),
                "created_at": "2026-04-18T10:00:00+00:00",
            }
        ],
    )
    storage = _MemoryStorage()

    export = audit_export_service.build_assessment_audit_export(
        session=fake_session,
        storage=storage,
        assessment_id=assessment_id,
        requested_by="pytest",
        actor_role=AppRoleName.REVIEWER,
    )
    export_again = audit_export_service.build_assessment_audit_export(
        session=fake_session,
        storage=storage,
        assessment_id=assessment_id,
        requested_by="pytest",
        actor_role=AppRoleName.REVIEWER,
    )

    assert export.id == export_again.id
    assert len(storage.calls) == 1
    assert export.status == AuditExportStatus.READY
    assert export.manifest_json["assessment"]["id"] == str(assessment_id)
    assert export.manifest_json["site_summary"]["borough_id"] == "camden"
    assert export.manifest_json["visibility"]["scope_key"] == "scope-1"
    assert any(
        event["action"] == "assessment_override_created"
        for event in export.manifest_json["audit_event_refs"]
    )


def test_suggest_refresh_and_normalize_reject_helpers_cover_missing_geometry_and_audit_branches(
    monkeypatch,
) -> None:
    site = SimpleNamespace(
        id=uuid4(),
        borough_id="camden",
        site_area_sqm=120.0,
        geom_hash="geom-hash",
        geometry_revisions=[],
        scenarios=[],
        display_name="Fixture site",
    )
    monkeypatch.setattr(
        suggest_service,
        "get_enabled_scenario_templates",
        lambda _session, template_keys=None: [
            SimpleNamespace(
                key="resi_5_9_full",
                config_json={"target_sqm_per_home": 180.0},
            )
        ],
    )
    monkeypatch.setattr(
        suggest_service,
        "get_borough_baseline_pack",
        lambda **_kwargs: SimpleNamespace(status=BaselinePackStatus.SIGNED_OFF),
    )
    monkeypatch.setattr(
        suggest_service,
        "evaluate_site_extant_permission",
        lambda **_kwargs: SimpleNamespace(
            status=ExtantPermissionStatus.NO_ACTIVE_PERMISSION_FOUND,
            eligibility_status=EligibilityStatus.PASS,
            coverage_gaps=[],
        ),
    )
    monkeypatch.setattr(
        suggest_service,
        "assemble_site_evidence",
        lambda **_kwargs: SimpleNamespace(model_dump=lambda **_dump_kwargs: {}),
    )

    response = suggest_service.refresh_site_scenarios(
        session=SimpleNamespace(),
        site=site,
        requested_by="pytest",
    )
    assert response.items == []
    assert response.excluded_templates[0].reasons[0].code == "NO_GEOMETRY_REVISION"

    collector: list[object] = []
    fake_session = SimpleNamespace(add=collector.append, flush=lambda: None)
    current_revision = SimpleNamespace(id=uuid4(), geom_hash="geom-hash")
    scenario = SimpleNamespace(
        id=uuid4(),
        site_id=uuid4(),
        site=SimpleNamespace(
            scenarios=[],
            geom_hash="geom-hash",
            geometry_revisions=[current_revision],
        ),
        status=ScenarioStatus.ANALYST_CONFIRMED,
        manual_review_required=False,
        is_current=True,
        is_headline=True,
        rationale_json={},
        reviews=[],
        assessment_runs=[],
        site_geometry_revision_id=current_revision.id,
        red_line_geom_hash="geom-hash",
        scenario_source=ScenarioSource.ANALYST,
        template_key="resi_5_9_full",
        template_version="v1",
        proposal_form=ProposalForm.REDEVELOPMENT,
        units_assumed=6,
        route_assumed="FULL",
        height_band_assumed="MID_RISE",
        net_developable_area_pct=0.7,
        housing_mix_assumed_json={},
        parking_assumption=None,
        affordable_housing_assumption=None,
        access_assumption=None,
        stale_reason=None,
        updated_at=datetime(2026, 4, 18, tzinfo=UTC),
    )
    scenario.site.scenarios.append(scenario)
    monkeypatch.setattr(normalize_service, "_load_scenario", lambda **_kwargs: scenario)
    monkeypatch.setattr(
        normalize_service, "_current_geometry_revision", lambda _site: current_revision
    )

    rejected = normalize_service.confirm_or_update_scenario(
        session=fake_session,
        scenario_id=scenario.id,
        request=ScenarioConfirmRequest(
            requested_by="pytest",
            action="REJECT",
            review_notes="Not viable for the fixture.",
        ),
    )
    assert rejected.status == ScenarioStatus.REJECTED
    assert rejected.manual_review_required is False
    assert rejected.is_current is False
    assert rejected.is_headline is False
    assert "SCENARIO_REJECTED" in rejected.rationale_json["warning_codes"]
    assert any(getattr(item, "action", None) == "scenario_rejected" for item in collector)
