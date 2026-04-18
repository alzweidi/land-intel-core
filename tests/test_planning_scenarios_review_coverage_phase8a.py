from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from landintel.assessments.service import create_or_refresh_assessment_run
from landintel.domain.enums import (
    AppRoleName,
    AssessmentOverrideStatus,
    AssessmentOverrideType,
    EligibilityStatus,
    ExtantPermissionStatus,
    GeomConfidence,
    GoldSetReviewStatus,
    HistoricalLabelClass,
    HistoricalLabelDecision,
    PriceBasisType,
    ProposalForm,
    ReviewStatus,
    ScenarioStatus,
    SourceCoverageStatus,
    SourceFreshnessStatus,
    SourceParseStatus,
    VisibilityMode,
)
from landintel.domain.models import (
    AssessmentOverride,
    AssessmentRun,
    AuditEvent,
    HistoricalCaseLabel,
    LpaBoundary,
    PlanningApplication,
    SourceSnapshot,
)
from landintel.domain.schemas import AssessmentOverrideRequest, ScenarioConfirmRequest
from landintel.features.build import FEATURE_VERSION
from landintel.planning import extant_permission as extant_permission_service
from landintel.planning import historical_labels as historical_labels_service
from landintel.planning import import_common as import_common_service
from landintel.review import audit_export as audit_export_service
from landintel.review import overrides as overrides_service
from landintel.review import visibility as visibility_service
from landintel.scenarios import normalize as normalize_service
from landintel.scenarios import suggest as suggest_service
from sqlalchemy import select

from tests.test_assessments_phase5a import _build_confirmed_camden_scenario


class _MemoryStorage:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bytes, str | None]] = []

    def put_bytes(self, path: str, content: bytes, content_type: str | None = None) -> None:
        self.calls.append((path, content, content_type))


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
                "display_name": "Camden test site",
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
                "visibility_mode": VisibilityMode.HIDDEN_ONLY.value,
                "exposure_mode": "HIDDEN_INTERNAL",
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


def _make_source_snapshot(db_session, *, source_snapshot_id: UUID) -> SourceSnapshot:
    snapshot = SourceSnapshot(
        id=source_snapshot_id,
        source_family="BOROUGH_REGISTER",
        source_name="fixture-source",
        source_uri="file:///tmp/fixture.json",
        schema_hash="a" * 64,
        content_hash="b" * 64,
        freshness_status=SourceFreshnessStatus.FRESH,
        parse_status=SourceParseStatus.PARSED,
        manifest_json={},
    )
    db_session.add(snapshot)
    db_session.flush()
    return snapshot


def _make_planning_application(
    db_session,
    *,
    source_snapshot_id: UUID,
    external_ref: str,
    source_priority: int,
    status: str = "APPROVED",
    decision_type: str = "FULL_RESIDENTIAL",
    route_normalized: str = "FULL",
    raw_record_json: dict[str, object] | None = None,
) -> PlanningApplication:
    application = PlanningApplication(
        source_system="BOROUGH_REGISTER",
        source_snapshot_id=source_snapshot_id,
        external_ref=external_ref,
        application_type="FULL",
        proposal_description=f"Fixture application for {external_ref}.",
        status=status,
        source_priority=source_priority,
        raw_record_json=raw_record_json or {},
        decision_type=decision_type,
        route_normalized=route_normalized,
        valid_date=date(2026, 4, 1),
        borough_id="camden",
        source_url=f"https://example.test/{external_ref}",
    )
    db_session.add(application)
    db_session.flush()
    return application


def test_import_common_registers_dataset_snapshots_and_coverage_branches(
    tmp_path: Path,
    db_session,
) -> None:
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
    assert len(storage.calls) == 1
    assert snapshot.parse_status == SourceParseStatus.PARSED

    boundary = LpaBoundary(
        id="camden",
        name="Camden",
        geom_27700="POLYGON((0 0, 10 0, 10 10, 0 10, 0 0))",
        geom_4326={},
        geom_hash="c" * 64,
        area_sqm=100.0,
        source_snapshot_id=asset.source_snapshot_id,
    )
    db_session.add(boundary)
    db_session.flush()

    imported = import_common_service.upsert_coverage_snapshots(
        session=db_session,
        source_snapshot=snapshot,
        coverage_rows=[
            {
                "borough_id": "camden",
                "coverage_status": "COMPLETE",
                "freshness_status": "FRESH",
            }
        ],
    )
    assert imported == 1
    db_session.commit()

    coverage_rows = (
        db_session.execute(
            select(import_common_service.SourceCoverageSnapshot).where(
                import_common_service.SourceCoverageSnapshot.borough_id == "camden"
            )
        )
        .scalars()
        .all()
    )
    assert len(coverage_rows) == 1
    assert coverage_rows[0].coverage_status == SourceCoverageStatus.COMPLETE

    with pytest.raises(ValueError, match="unknown borough"):
        import_common_service.upsert_coverage_snapshots(
            session=db_session,
            source_snapshot=snapshot,
            coverage_rows=[
                {
                    "borough_id": "missing-borough",
                    "coverage_status": "PARTIAL",
                    "freshness_status": "STALE",
                }
            ],
        )


def test_extant_permission_evaluate_site_branches_cover_real_return_paths(
    monkeypatch,
) -> None:
    site = SimpleNamespace(
        borough_id="camden",
        geom_27700="POLYGON((0 0, 20 0, 20 20, 0 20, 0 0))",
        site_area_sqm=400.0,
        planning_links=[
            SimpleNamespace(
                planning_application=SimpleNamespace(
                    id=uuid4(),
                    source_system="BOROUGH_REGISTER",
                    external_ref="CAM/2026/0001/FUL",
                    source_url="https://example.test/CAM/2026/0001/FUL",
                    source_snapshot_id=uuid4(),
                    raw_record_json={"dwelling_use": "C3", "active_extant": True},
                    route_normalized="FULL",
                    decision_type="FULL_RESIDENTIAL",
                    status="APPROVED",
                    application_type="FULL",
                ),
                overlap_pct=0.20,
                distance_m=0.0,
                link_type="POLYGON_OVERLAP",
                source_snapshot_id=uuid4(),
            )
        ],
    )

    monkeypatch.setattr(
        extant_permission_service, "load_wkt_geometry", lambda *_args, **_kwargs: object()
    )

    def _material_overlap(*, site_geometry, application):
        del site_geometry, application
        return 150.0

    monkeypatch.setattr(extant_permission_service, "_planning_overlap_sqm", _material_overlap)
    monkeypatch.setattr(
        extant_permission_service,
        "planning_application_snapshot",
        lambda link: {
            "source_system": link.planning_application.source_system,
            "external_ref": link.planning_application.external_ref,
            "source_url": link.planning_application.source_url,
            "source_snapshot_id": link.source_snapshot_id,
            "raw_record_json": link.planning_application.raw_record_json,
            "route_normalized": link.planning_application.route_normalized,
            "decision_type": link.planning_application.decision_type,
            "status": link.planning_application.status,
        },
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
        "list_brownfield_states_for_site",
        lambda **_kwargs: [],
    )

    active = extant_permission_service.evaluate_site_extant_permission(
        session=SimpleNamespace(),
        site=site,
        as_of_date=date(2026, 4, 18),
    )
    assert active.status == ExtantPermissionStatus.ACTIVE_EXTANT_PERMISSION_FOUND
    assert active.eligibility_status == EligibilityStatus.FAIL
    assert active.manual_review_required is False
    assert active.matched_records[0].material is True

    site.planning_links[0].overlap_pct = 0.02
    monkeypatch.setattr(extant_permission_service, "_planning_overlap_sqm", lambda **_kwargs: 15.0)
    non_material = extant_permission_service.evaluate_site_extant_permission(
        session=SimpleNamespace(),
        site=site,
        as_of_date=date(2026, 4, 18),
    )
    assert non_material.status == ExtantPermissionStatus.NON_MATERIAL_OVERLAP_MANUAL_REVIEW
    assert non_material.eligibility_status == EligibilityStatus.ABSTAIN
    assert non_material.manual_review_required is True

    site.planning_links[0].planning_application.raw_record_json = {
        "dwelling_use": "C3",
        "active_extant": False,
    }
    monkeypatch.setattr(
        extant_permission_service,
        "list_latest_coverage_snapshots",
        lambda **_kwargs: [
            SimpleNamespace(
                source_family="BOROUGH_REGISTER", coverage_status=SourceCoverageStatus.COMPLETE
            )
        ],
    )
    mandatory_gap = extant_permission_service.evaluate_site_extant_permission(
        session=SimpleNamespace(),
        site=site,
        as_of_date=date(2026, 4, 18),
    )
    assert mandatory_gap.status == ExtantPermissionStatus.UNRESOLVED_MISSING_MANDATORY_SOURCE
    assert mandatory_gap.manual_review_required is True

    site.planning_links[0].planning_application.raw_record_json = {
        "dwelling_use": "C3",
        "active_extant": True,
    }
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
        lambda link: {
            "source_system": "PLD",
            "external_ref": link.planning_application.external_ref,
            "source_url": link.planning_application.source_url,
            "source_snapshot_id": link.source_snapshot_id,
            "raw_record_json": link.planning_application.raw_record_json,
            "route_normalized": link.planning_application.route_normalized,
            "decision_type": link.planning_application.decision_type,
            "status": link.planning_application.status,
        },
    )
    contradictory = extant_permission_service.evaluate_site_extant_permission(
        session=SimpleNamespace(),
        site=site,
        as_of_date=date(2026, 4, 18),
    )
    assert contradictory.status == ExtantPermissionStatus.CONTRADICTORY_SOURCE_MANUAL_REVIEW
    assert contradictory.manual_review_required is True

    site.planning_links[0].planning_application.raw_record_json = {
        "dwelling_use": "C3",
        "active_extant": False,
    }
    monkeypatch.setattr(
        extant_permission_service,
        "planning_application_snapshot",
        lambda link: {
            "source_system": link.planning_application.source_system,
            "external_ref": link.planning_application.external_ref,
            "source_url": link.planning_application.source_url,
            "source_snapshot_id": link.source_snapshot_id,
            "raw_record_json": {
                "dwelling_use": "C3",
                "expiry_date": "2025-01-01",
                "active_extant": False,
            },
            "route_normalized": "FULL",
            "decision_type": "FULL_RESIDENTIAL",
            "status": "APPROVED",
        },
    )
    no_active = extant_permission_service.evaluate_site_extant_permission(
        session=SimpleNamespace(),
        site=site,
        as_of_date=date(2026, 4, 18),
    )
    assert no_active.status == ExtantPermissionStatus.NO_ACTIVE_PERMISSION_FOUND
    assert no_active.eligibility_status == EligibilityStatus.PASS
    assert no_active.summary.startswith("No active extant residential permission")


def test_historical_labels_rebuild_review_and_filter_branches(db_session, monkeypatch) -> None:
    source_snapshot = _make_source_snapshot(db_session, source_snapshot_id=uuid4())
    applications = [
        _make_planning_application(
            db_session,
            source_snapshot_id=source_snapshot.id,
            external_ref="CAM/2026/0001/FUL",
            source_priority=100,
        ),
        _make_planning_application(
            db_session,
            source_snapshot_id=source_snapshot.id,
            external_ref="CAM/2026/0002/FUL",
            source_priority=90,
            status="REFUSED",
            decision_type="FULL_RESIDENTIAL",
        ),
        _make_planning_application(
            db_session,
            source_snapshot_id=source_snapshot.id,
            external_ref="CAM/2026/0003/FUL",
            source_priority=80,
            status="WITHDRAWN",
            decision_type="FULL_RESIDENTIAL",
        ),
        _make_planning_application(
            db_session,
            source_snapshot_id=source_snapshot.id,
            external_ref="CAM/2026/0004/FUL",
            source_priority=70,
            status="INVALID",
            decision_type="FULL_RESIDENTIAL",
        ),
    ]

    existing = HistoricalCaseLabel(
        planning_application_id=applications[0].id,
        label_version=FEATURE_VERSION,
        borough_id="camden",
        template_key="resi_5_9_full",
        proposal_form=ProposalForm.INFILL,
        route_normalized="FULL",
        units_proposed=8,
        site_area_sqm=120.0,
        label_class=HistoricalLabelClass.POSITIVE,
        label_decision=HistoricalLabelDecision.APPROVE,
        label_reason="Existing fixture label",
        valid_date=date(2026, 4, 1),
        first_substantive_decision_date=date(2026, 4, 2),
        label_window_end=date(2026, 4, 30),
        source_priority_used=100,
        archetype_key="resi_5_9_full::inf",
        designation_profile_json={"existing": True},
        provenance_json={"seed": True},
        source_snapshot_ids_json=[str(source_snapshot.id)],
        raw_asset_ids_json=[],
        review_status=GoldSetReviewStatus.CONFIRMED,
        review_notes="Seeded review note",
        reviewed_by="seed-reviewer",
        reviewed_at=datetime(2026, 4, 10, tzinfo=UTC),
        notable_policy_issues_json=["heritage"],
        extant_permission_outcome="NO_ACTIVE_PERMISSION_FOUND",
        site_geometry_confidence=GeomConfidence.HIGH,
    )
    db_session.add(existing)
    db_session.flush()

    payloads = {
        applications[0].external_ref: {
            "template_key": "resi_5_9_full",
            "proposal_form": ProposalForm.INFILL,
            "units_proposed": 8,
            "site_area_sqm": 120.0,
            "label_class": HistoricalLabelClass.POSITIVE,
            "label_decision": HistoricalLabelDecision.APPROVE,
            "label_reason": "Approved in fixture",
            "first_substantive_decision_date": date(2026, 4, 2),
            "label_window_end": date(2026, 4, 30),
            "archetype_key": "resi_5_9_full::inf",
            "designation_profile_json": {"type": "positive"},
            "provenance_json": {"source": "fixture"},
            "source_snapshot_ids_json": [str(source_snapshot.id)],
            "raw_asset_ids_json": [str(uuid4())],
            "site_geometry_confidence": GeomConfidence.HIGH,
        },
        applications[1].external_ref: {
            "template_key": "resi_5_9_full",
            "proposal_form": ProposalForm.INFILL,
            "units_proposed": 4,
            "site_area_sqm": 90.0,
            "label_class": HistoricalLabelClass.NEGATIVE,
            "label_decision": HistoricalLabelDecision.REFUSE,
            "label_reason": "Refused in fixture",
            "first_substantive_decision_date": date(2026, 4, 3),
            "label_window_end": date(2026, 4, 30),
            "archetype_key": "resi_5_9_full::inf",
            "designation_profile_json": {"type": "negative"},
            "provenance_json": {"source": "fixture"},
            "source_snapshot_ids_json": [str(source_snapshot.id)],
            "raw_asset_ids_json": [str(uuid4())],
            "site_geometry_confidence": GeomConfidence.MEDIUM,
        },
        applications[2].external_ref: {
            "template_key": "resi_5_9_full",
            "proposal_form": ProposalForm.REDEVELOPMENT,
            "units_proposed": 2,
            "site_area_sqm": 80.0,
            "label_class": HistoricalLabelClass.EXCLUDED,
            "label_decision": HistoricalLabelDecision.WITHDRAWN,
            "label_reason": "Withdrawn in fixture",
            "first_substantive_decision_date": date(2026, 4, 4),
            "label_window_end": date(2026, 4, 30),
            "archetype_key": "resi_5_9_full::red",
            "designation_profile_json": {"type": "excluded"},
            "provenance_json": {"source": "fixture"},
            "source_snapshot_ids_json": [str(source_snapshot.id)],
            "raw_asset_ids_json": [str(uuid4())],
            "site_geometry_confidence": GeomConfidence.LOW,
        },
        applications[3].external_ref: {
            "template_key": "resi_5_9_full",
            "proposal_form": ProposalForm.BROWNFIELD_REUSE,
            "units_proposed": 1,
            "site_area_sqm": 70.0,
            "label_class": HistoricalLabelClass.CENSORED,
            "label_decision": HistoricalLabelDecision.INVALID,
            "label_reason": "Invalid in fixture",
            "first_substantive_decision_date": date(2026, 4, 5),
            "label_window_end": date(2026, 4, 30),
            "archetype_key": "resi_5_9_full::brownfield",
            "designation_profile_json": {"type": "censored"},
            "provenance_json": {"source": "fixture"},
            "source_snapshot_ids_json": [str(source_snapshot.id)],
            "raw_asset_ids_json": [str(uuid4())],
            "site_geometry_confidence": GeomConfidence.INSUFFICIENT,
        },
    }

    def _fake_build_label_payload(*, application, **_kwargs):
        payload = payloads[application.external_ref]
        return {
            "template_key": payload["template_key"],
            "proposal_form": payload["proposal_form"],
            "site_area_sqm": payload["site_area_sqm"],
            "label_class": payload["label_class"],
            "label_decision": payload["label_decision"],
            "label_reason": payload["label_reason"],
            "first_substantive_decision_date": payload["first_substantive_decision_date"],
            "label_window_end": payload["label_window_end"],
            "archetype_key": payload["archetype_key"],
            "designation_profile_json": payload["designation_profile_json"],
            "provenance_json": payload["provenance_json"],
            "source_snapshot_ids_json": payload["source_snapshot_ids_json"],
            "raw_asset_ids_json": payload["raw_asset_ids_json"],
            "site_geometry_confidence": payload["site_geometry_confidence"],
        }

    monkeypatch.setattr(
        historical_labels_service, "_build_label_payload", _fake_build_label_payload
    )

    summary = historical_labels_service.rebuild_historical_case_labels(
        session=db_session,
        requested_by="pytest",
    )
    assert summary.total == 4
    assert summary.positive == 1
    assert summary.negative == 1
    assert summary.excluded == 1
    assert summary.censored == 1

    rebuilt = db_session.execute(
        select(HistoricalCaseLabel).where(
            HistoricalCaseLabel.planning_application_id == applications[0].id
        )
    ).scalar_one()
    assert rebuilt.review_status == GoldSetReviewStatus.CONFIRMED
    assert rebuilt.review_notes == "Seeded review note"
    assert rebuilt.reviewed_by == "seed-reviewer"
    assert rebuilt.extant_permission_outcome == "NO_ACTIVE_PERMISSION_FOUND"

    confirmed_cases = historical_labels_service.list_historical_label_cases(
        session=db_session,
        review_status=GoldSetReviewStatus.CONFIRMED,
        template_key="resi_5_9_full",
    )
    assert [case.planning_application_id for case in confirmed_cases] == [applications[0].id]

    reviewed = historical_labels_service.review_historical_label_case(
        session=db_session,
        case=rebuilt,
        review_status=GoldSetReviewStatus.EXCLUDED,
        review_notes="Reviewed out of scope.",
        notable_policy_issues=["access"],
        extant_permission_outcome="ACTIVE_EXTANT_PERMISSION_FOUND",
        site_geometry_confidence=GeomConfidence.MEDIUM,
        reviewed_by="pytest",
    )
    assert reviewed.review_status == GoldSetReviewStatus.EXCLUDED
    assert reviewed.reviewed_by == "pytest"
    assert reviewed.reviewed_at is not None

    audit_event = db_session.execute(
        select(AuditEvent)
        .where(AuditEvent.action == "historical_label_reviewed")
        .where(AuditEvent.entity_id == str(rebuilt.id))
    ).scalar_one()
    assert audit_event.before_json["review_status"] == GoldSetReviewStatus.CONFIRMED.value


def test_visibility_gate_branches_cover_hidden_visible_redacted_and_blocked_paths(
    monkeypatch,
) -> None:
    def _make_run(*, scope_key: str, raw_probability: float, display_probability: float | None):
        return SimpleNamespace(
            result=SimpleNamespace(
                release_scope_key=scope_key,
                approval_probability_raw=raw_probability,
                approval_probability_display=display_probability,
                model_release_id=None,
                review_status=ReviewStatus.NOT_REQUIRED,
                manual_review_required=False,
            ),
            prediction_ledger=SimpleNamespace(),
        )

    monkeypatch.setattr(visibility_service, "_payload_hash_matches", lambda _run: True)
    monkeypatch.setattr(
        visibility_service,
        "load_active_scope",
        lambda _session, *, scope_key: SimpleNamespace(
            id=uuid4(),
            scope_key=scope_key,
            visibility_mode=VisibilityMode.HIDDEN_ONLY,
            model_release=None,
            model_release_id=None,
        ),
    )
    monkeypatch.setattr(
        visibility_service, "get_open_incident_for_scope", lambda *args, **_kwargs: None
    )

    hidden_internal = visibility_service.evaluate_assessment_visibility(
        session=SimpleNamespace(),
        assessment_run=_make_run(
            scope_key="scope-1", raw_probability=0.62, display_probability=0.60
        ),
        viewer_role=AppRoleName.REVIEWER,
        include_hidden=True,
    )
    assert hidden_internal.exposure_mode == "HIDDEN_INTERNAL"
    assert hidden_internal.hidden_probability_allowed is True
    assert hidden_internal.visible_probability_allowed is False
    assert hidden_internal.blocked is False
    assert hidden_internal.replay_verified is True

    monkeypatch.setattr(
        visibility_service,
        "load_active_scope",
        lambda _session, *, scope_key: SimpleNamespace(
            id=uuid4(),
            scope_key=scope_key,
            visibility_mode=VisibilityMode.VISIBLE_REVIEWER_ONLY,
            model_release=None,
            model_release_id=None,
        ),
    )
    visible_reviewer = visibility_service.evaluate_assessment_visibility(
        session=SimpleNamespace(),
        assessment_run=_make_run(
            scope_key="scope-1", raw_probability=0.62, display_probability=0.60
        ),
        viewer_role=AppRoleName.REVIEWER,
        include_hidden=False,
    )
    assert visible_reviewer.exposure_mode == "VISIBLE_REVIEWER_ONLY"
    assert visible_reviewer.visible_probability_allowed is True
    assert visible_reviewer.hidden_probability_allowed is False
    assert visible_reviewer.blocked is False

    analyst_redacted = visibility_service.evaluate_assessment_visibility(
        session=SimpleNamespace(),
        assessment_run=_make_run(
            scope_key="scope-1", raw_probability=0.62, display_probability=0.60
        ),
        viewer_role=AppRoleName.ANALYST,
        include_hidden=False,
    )
    assert analyst_redacted.exposure_mode == "REDACTED"
    assert analyst_redacted.blocked is False
    assert analyst_redacted.blocked_reason_codes == ["ROLE_REDACTED"]
    assert analyst_redacted.visible_probability_allowed is False

    monkeypatch.setattr(
        visibility_service,
        "get_open_incident_for_scope",
        lambda *args, **_kwargs: SimpleNamespace(id=uuid4(), reason="Pytest kill switch open."),
    )
    blocked = visibility_service.evaluate_assessment_visibility(
        session=SimpleNamespace(),
        assessment_run=_make_run(
            scope_key="scope-1", raw_probability=0.62, display_probability=0.60
        ),
        viewer_role=AppRoleName.REVIEWER,
        include_hidden=False,
    )
    assert blocked.blocked is True
    assert "ACTIVE_INCIDENT" in blocked.blocked_reason_codes
    assert blocked.active_incident_reason == "Pytest kill switch open."
    assert blocked.blocked_reason_text == visibility_service._BLOCK_REASON_TEXT["ACTIVE_INCIDENT"]


def test_override_summary_application_and_audit_export_reuse(
    client,
    drain_jobs,
    seed_listing_sources,
    seed_planning_data,
    db_session,
    monkeypatch,
) -> None:
    del seed_listing_sources
    del seed_planning_data

    site_payload, scenario_payload = _build_confirmed_camden_scenario(client, drain_jobs)
    run = create_or_refresh_assessment_run(
        session=db_session,
        site_id=UUID(site_payload["id"]),
        scenario_id=UUID(scenario_payload["id"]),
        as_of_date=date(2026, 4, 15),
        requested_by="pytest",
    )
    db_session.commit()
    db_session.refresh(run)

    review_override = AssessmentOverride(
        assessment_run_id=run.id,
        override_type=AssessmentOverrideType.REVIEW_DISPOSITION,
        status=AssessmentOverrideStatus.ACTIVE,
        actor_name="reviewer@example.test",
        actor_role=AppRoleName.REVIEWER,
        reason="Resolve manual review.",
        override_json={"resolve_manual_review": True},
        created_at=datetime(2026, 4, 18, 10, 0, tzinfo=UTC),
    )
    ranking_override = AssessmentOverride(
        assessment_run_id=run.id,
        override_type=AssessmentOverrideType.RANKING_SUPPRESSION,
        status=AssessmentOverrideStatus.ACTIVE,
        actor_name="reviewer@example.test",
        actor_role=AppRoleName.REVIEWER,
        reason="Hide ranking while evidence settles.",
        override_json={
            "ranking_suppressed": True,
            "display_block_reason": "Temporary publication hold.",
        },
        created_at=datetime(2026, 4, 18, 10, 5, tzinfo=UTC),
    )
    db_session.add_all([review_override, ranking_override])
    db_session.flush()

    summary = overrides_service.build_override_summary(session=db_session, assessment_run=run)
    assert summary is not None
    assert summary.effective_review_status == ReviewStatus.COMPLETED
    assert summary.effective_manual_review_required is False
    assert summary.ranking_suppressed is True
    assert summary.display_block_reason == "Temporary publication hold."
    assert summary.active_overrides[0].override_type == AssessmentOverrideType.RANKING_SUPPRESSION

    basis_request = AssessmentOverrideRequest(
        override_type=AssessmentOverrideType.ACQUISITION_BASIS,
        reason="Manual acquisition basis for fixture run.",
        acquisition_basis_gbp=125000.125,
        acquisition_basis_type=PriceBasisType.GUIDE_PRICE,
        requested_by="pytest",
        actor_role=AppRoleName.ANALYST,
    )
    overrides_service.apply_assessment_override(
        session=db_session,
        assessment_id=run.id,
        request=basis_request,
    )
    db_session.commit()
    db_session.expire_all()
    run = db_session.get(AssessmentRun, run.id)
    assert run is not None

    basis_overrides = (
        db_session.execute(
            select(AssessmentOverride)
            .where(AssessmentOverride.assessment_run_id == run.id)
            .where(AssessmentOverride.override_type == AssessmentOverrideType.ACQUISITION_BASIS)
            .order_by(AssessmentOverride.created_at.asc())
        )
        .scalars()
        .all()
    )
    assert len(basis_overrides) == 1
    assert basis_overrides[0].override_json["acquisition_basis_gbp"] == 125000.12

    overrides_service.apply_assessment_override(
        session=db_session,
        assessment_id=run.id,
        request=AssessmentOverrideRequest(
            override_type=AssessmentOverrideType.ACQUISITION_BASIS,
            reason="Updated acquisition basis after review.",
            acquisition_basis_gbp=130000.0,
            acquisition_basis_type=PriceBasisType.ASKING_PRICE,
            requested_by="pytest",
            actor_role=AppRoleName.ANALYST,
        ),
    )
    db_session.commit()
    db_session.expire_all()
    run = db_session.get(AssessmentRun, run.id)
    assert run is not None

    refreshed_basis_overrides = (
        db_session.execute(
            select(AssessmentOverride)
            .where(AssessmentOverride.assessment_run_id == run.id)
            .where(AssessmentOverride.override_type == AssessmentOverrideType.ACQUISITION_BASIS)
            .order_by(AssessmentOverride.created_at.asc())
        )
        .scalars()
        .all()
    )
    assert len(refreshed_basis_overrides) == 2
    assert refreshed_basis_overrides[-1].supersedes_id == refreshed_basis_overrides[0].id

    summary_after_basis = overrides_service.build_override_summary(
        session=db_session, assessment_run=run
    )
    assert summary_after_basis is not None
    assert (
        summary_after_basis.active_overrides[0].override_type
        == AssessmentOverrideType.ACQUISITION_BASIS
    )
    assert summary_after_basis.effective_review_status == ReviewStatus.COMPLETED
    assert summary_after_basis.ranking_suppressed is True

    fake_detail = _FakeAssessmentDetail(str(run.id))
    fake_valuation_run = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(audit_export_service, "get_assessment", lambda **_kwargs: fake_detail)
    monkeypatch.setattr(
        audit_export_service,
        "frozen_valuation_run",
        lambda assessment_run: fake_valuation_run if assessment_run.id == run.id else None,
    )
    monkeypatch.setattr(
        audit_export_service,
        "_serialize_audit_events",
        lambda **_kwargs: [
            {
                "id": "event-1",
                "action": "assessment_override_created",
                "entity_type": "assessment_run",
                "entity_id": str(run.id),
                "created_at": "2026-04-18T10:00:00+00:00",
            }
        ],
    )
    storage = _MemoryStorage()

    export = audit_export_service.build_assessment_audit_export(
        session=db_session,
        storage=storage,
        assessment_id=run.id,
        requested_by="pytest",
        actor_role=AppRoleName.REVIEWER,
    )
    export_again = audit_export_service.build_assessment_audit_export(
        session=db_session,
        storage=storage,
        assessment_id=run.id,
        requested_by="pytest",
        actor_role=AppRoleName.REVIEWER,
    )

    assert export.id == export_again.id
    assert len(storage.calls) == 1
    assert export.manifest_json["assessment"]["id"] == str(run.id)
    assert export.manifest_json["site_summary"]["borough_id"] == "camden"
    assert export.manifest_json["scenario_summary"]["template_key"] == "resi_5_9_full"
    assert export.manifest_json["visibility"]["scope_key"] == "scope-1"
    assert any(
        event["action"] == "assessment_override_created"
        for event in export.manifest_json["audit_event_refs"]
    )


def test_suggest_and_normalize_helper_branches_cover_true_and_edit_paths() -> None:
    deduped = suggest_service._dedupe(["a", "a", "b", "c", "b"])
    assert deduped == ["a", "b", "c"]

    allowed, reasons = suggest_service._auto_confirm_allowed(
        site=SimpleNamespace(geom_confidence=GeomConfidence.HIGH),
        template_key="resi_5_9_full",
        preferred_route="FULL",
        support=suggest_service.CandidateSupport(application=None, strong=True),
        extant_permission=SimpleNamespace(eligibility_status=EligibilityStatus.PASS),
        missing_data_flags=[],
        warning_codes=[],
    )
    assert allowed is True
    assert isinstance(reasons, list)

    default_request = ScenarioConfirmRequest(requested_by="pytest")
    edited_request = ScenarioConfirmRequest(
        requested_by="pytest",
        units_assumed=8,
        proposal_form=ProposalForm.INFILL,
        route_assumed="FULL",
        review_notes="Apply analyst edits.",
    )
    assert normalize_service._edits_present(default_request) is False
    assert normalize_service._edits_present(edited_request) is True

    scenario = SimpleNamespace(
        proposal_form=ProposalForm.BACKLAND,
        units_assumed=4,
        route_assumed="OUTLINE",
        height_band_assumed="LOW-RISE",
        net_developable_area_pct=0.5,
        housing_mix_assumed_json={"studio": 1.0},
        parking_assumption=None,
        affordable_housing_assumption=None,
        access_assumption=None,
        review_notes=None,
    )
    normalize_service._apply_request_fields(target=scenario, request=edited_request)
    assert scenario.units_assumed == 8
    assert scenario.proposal_form == ProposalForm.INFILL
    assert scenario.route_assumed == "FULL"
