from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from landintel.domain.enums import (
    AppRoleName,
    GeomConfidence,
    GoldSetReviewStatus,
    HistoricalLabelClass,
    HistoricalLabelDecision,
    ProposalForm,
    SourceCoverageStatus,
)
from landintel.domain.models import AuditExport, HistoricalCaseLabel
from landintel.features.build import FEATURE_VERSION
from landintel.planning import extant_permission as extant_permission_service
from landintel.planning import historical_labels as historical_labels_service
from landintel.review import audit_export as audit_export_service
from landintel.review.visibility import ReviewAccessError
from landintel.services import readback


class _Result:
    def __init__(self, *, rows=None, scalar=None):
        self._rows = list(rows or [])
        self._scalar = scalar

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)

    def scalar_one_or_none(self):
        return self._scalar


class _QueueSession:
    def __init__(self, *results):
        self._results = list(results)
        self.added: list[object] = []
        self.deleted: list[object] = []
        self.flushed = 0

    def execute(self, *args, **kwargs):
        del args, kwargs
        if not self._results:
            raise AssertionError("Unexpected execute() call with no queued result.")
        return self._results.pop(0)

    def add(self, obj):
        self.added.append(obj)

    def delete(self, obj):
        self.deleted.append(obj)

    def flush(self):
        self.flushed += 1


class _AuditSession:
    def __init__(self, run):
        self._run = run
        self._exports: dict[UUID, AuditExport] = {}
        self.added: list[object] = []
        self.flushed = 0
        self._run_loaded = False

    def execute(self, *args, **kwargs):
        del args, kwargs
        if not self._run_loaded:
            self._run_loaded = True
            return _Result(scalar=self._run)
        return _Result(rows=[])

    def get(self, model, ident):
        if model is AuditExport:
            return self._exports.get(ident)
        return None

    def add(self, obj):
        self.added.append(obj)
        if isinstance(obj, AuditExport):
            if obj.created_at is None:
                obj.created_at = datetime(2026, 4, 18, 12, 0, tzinfo=UTC)
            self._exports[obj.id] = obj

    def flush(self):
        self.flushed += 1


class _MemoryStorage:
    def __init__(self):
        self.calls: list[tuple[str, bytes, str | None]] = []

    def put_bytes(self, path: str, content: bytes, content_type: str | None = None):
        self.calls.append((path, content, content_type))


class _Intersection:
    def __init__(self, *, area: float = 0.0, is_empty: bool = False):
        self.area = area
        self.is_empty = is_empty


class _Geometry:
    def __init__(
        self,
        *,
        geom_type: str = "Polygon",
        area: float = 200.0,
        intersects: bool = True,
        overlap_area: float = 120.0,
        distance_m: float = 0.0,
        intersection_empty: bool = False,
    ):
        self.geom_type = geom_type
        self.area = area
        self._intersects = intersects
        self._overlap_area = overlap_area
        self._distance_m = distance_m
        self._intersection_empty = intersection_empty

    def intersects(self, _other) -> bool:
        return self._intersects

    def intersection(self, _other):
        return _Intersection(area=self._overlap_area, is_empty=self._intersection_empty)

    def distance(self, _other) -> float:
        return self._distance_m


class _AssessmentDetail:
    def __init__(self):
        self.site_summary = None
        self.scenario_summary = None
        self.visibility = None

    def model_dump(self, *, mode: str = "json"):
        del mode
        return {"id": "assessment-1", "kind": "fixture"}


def _fixed_uuid(seed: int) -> UUID:
    return UUID(f"00000000-0000-0000-0000-{seed:012d}")


def _make_application(
    *,
    seed: int,
    source_priority: int = 100,
    borough_id: str = "camden",
    route_normalized: str = "FULL",
    application_type: str = "FULL",
    decision_type: str = "FULL_RESIDENTIAL",
    status: str = "APPROVED",
    decision: str = "APPROVED",
    valid_date: date | None = date(2024, 1, 1),
    decision_date: date | None = date(2024, 6, 1),
    units_proposed: int | None = 6,
    raw_record_json: dict[str, object] | None = None,
    proposal_description: str = "Redevelopment of the site for housing.",
    geometry: _Geometry | None = None,
    area_sqm: float | None = 200.0,
):
    return SimpleNamespace(
        id=_fixed_uuid(seed),
        borough_id=borough_id,
        source_system="BOROUGH_REGISTER",
        source_priority=source_priority,
        source_snapshot_id=_fixed_uuid(seed + 100),
        external_ref=f"APP-{seed}",
        route_normalized=route_normalized,
        application_type=application_type,
        decision_type=decision_type,
        status=status,
        decision=decision,
        valid_date=valid_date,
        decision_date=decision_date,
        units_proposed=units_proposed,
        raw_record_json={"dwelling_use": "C3", **(raw_record_json or {})},
        proposal_description=proposal_description,
        documents=[SimpleNamespace(asset_id=_fixed_uuid(seed + 200))],
        _geometry=geometry,
        _area_sqm=area_sqm,
    )


def test_readback_re_exports_expected_public_api() -> None:
    assert readback.__all__ == [
        "get_site",
        "get_source_snapshot",
        "list_sites",
        "list_source_snapshots",
    ]


def test_historical_label_rebuild_list_get_and_review_paths(monkeypatch) -> None:
    application_one = _make_application(seed=1)
    application_two = _make_application(seed=2, route_normalized="OUTLINE", units_proposed=12)
    existing = HistoricalCaseLabel(
        planning_application_id=application_one.id,
        label_version=FEATURE_VERSION,
    )
    existing.review_status = GoldSetReviewStatus.CONFIRMED
    existing.review_notes = "kept"
    stale = HistoricalCaseLabel(
        planning_application_id=_fixed_uuid(99),
        label_version=FEATURE_VERSION,
    )

    payloads = iter(
        [
            {
                "template_key": "resi_5_9_full",
                "proposal_form": ProposalForm.REDEVELOPMENT,
                "site_area_sqm": 200.0,
                "label_class": HistoricalLabelClass.POSITIVE,
                "label_decision": HistoricalLabelDecision.APPROVE,
                "label_reason": None,
                "first_substantive_decision_date": date(2024, 6, 1),
                "label_window_end": date(2025, 7, 1),
                "archetype_key": "a",
                "designation_profile_json": {"brownfield_part1": False},
                "provenance_json": {"kind": "fixture-1"},
                "source_snapshot_ids_json": ["source-1"],
                "raw_asset_ids_json": ["asset-1"],
                "site_geometry_confidence": GeomConfidence.MEDIUM,
            },
            {
                "template_key": "resi_10_49_outline",
                "proposal_form": ProposalForm.INFILL,
                "site_area_sqm": 350.0,
                "label_class": HistoricalLabelClass.NEGATIVE,
                "label_decision": HistoricalLabelDecision.REFUSE,
                "label_reason": None,
                "first_substantive_decision_date": date(2024, 7, 1),
                "label_window_end": date(2025, 8, 1),
                "archetype_key": "b",
                "designation_profile_json": {"brownfield_part1": True},
                "provenance_json": {"kind": "fixture-2"},
                "source_snapshot_ids_json": ["source-2"],
                "raw_asset_ids_json": ["asset-2"],
                "site_geometry_confidence": GeomConfidence.LOW,
            },
        ]
    )
    monkeypatch.setattr(
        historical_labels_service,
        "_build_label_payload",
        lambda **_kwargs: next(payloads),
    )

    rebuild_session = _QueueSession(
        _Result(rows=[application_one, application_two]),
        _Result(rows=[existing, stale]),
    )
    summary = historical_labels_service.rebuild_historical_case_labels(
        session=rebuild_session,
        requested_by="pytest",
    )

    assert summary.total == 2
    assert summary.positive == 1
    assert summary.negative == 1
    assert stale in rebuild_session.deleted
    assert any(
        isinstance(item, HistoricalCaseLabel)
        and item.planning_application_id == application_two.id
        and item.review_status == GoldSetReviewStatus.PENDING
        for item in rebuild_session.added
    )
    assert any(
        getattr(item, "action", None) == "historical_labels_rebuilt"
        for item in rebuild_session.added
    )
    assert rebuild_session.flushed == 1

    list_session = _QueueSession(_Result(rows=[existing]))
    assert historical_labels_service.list_historical_label_cases(session=list_session) == [existing]

    get_session = _QueueSession(_Result(scalar=existing))
    assert (
        historical_labels_service.get_historical_label_case(
            session=get_session,
            case_id=existing.id,
        )
        is existing
    )

    review_session = _QueueSession()
    reviewed = historical_labels_service.review_historical_label_case(
        session=review_session,
        case=existing,
        review_status=GoldSetReviewStatus.EXCLUDED,
        review_notes="manual check",
        notable_policy_issues=["heritage"],
        extant_permission_outcome="ABSTAIN",
        site_geometry_confidence=GeomConfidence.HIGH,
        reviewed_by="pytest",
    )
    assert reviewed.review_status == GoldSetReviewStatus.EXCLUDED
    assert reviewed.reviewed_by == "pytest"
    assert review_session.flushed == 1
    assert any(
        getattr(item, "action", None) == "historical_label_reviewed"
        for item in review_session.added
    )


def test_historical_label_mapping_and_payload_helpers_cover_remaining_branches(monkeypatch) -> None:
    monkeypatch.setattr(
        historical_labels_service,
        "planning_application_geometry",
        lambda application: application._geometry,
    )
    monkeypatch.setattr(
        historical_labels_service,
        "planning_application_area_sqm",
        lambda application: application._area_sqm,
    )
    monkeypatch.setattr(
        historical_labels_service,
        "build_designation_profile_for_geometry",
        lambda **kwargs: (
            {"brownfield_part1": kwargs["geometry"].geom_type == "Point"},
            {"designation-source"},
        ),
    )
    monkeypatch.setattr(
        historical_labels_service,
        "derive_archetype_key",
        lambda **kwargs: (f"{kwargs['template_key']}::{kwargs['proposal_form'].value}"),
    )

    assert historical_labels_service._is_relevant_application(
        _make_application(seed=10, route_normalized="PRIOR_APPROVAL_EXT")
    ) == (
        False,
        "Prior approval and non-template routes are excluded from Phase 5A labels.",
    )
    assert historical_labels_service._is_relevant_application(
        _make_application(seed=11, route_normalized="APPEAL")
    ) == (False, "Appeal-only outcomes are excluded from Phase 5A labels.")
    assert historical_labels_service._is_relevant_application(
        _make_application(
            seed=12,
            decision_type="COMMERCIAL",
            raw_record_json={"dwelling_use": "B8"},
        )
    ) == (
        False,
        "Non-residential application type is excluded from the enabled templates.",
    )
    assert historical_labels_service._is_relevant_application(_make_application(seed=13)) == (
        True,
        None,
    )

    assert (
        historical_labels_service._map_template_key(_make_application(seed=14, units_proposed=2))
        == "resi_1_4_full"
    )
    assert (
        historical_labels_service._map_template_key(_make_application(seed=15, units_proposed=7))
        == "resi_5_9_full"
    )
    assert (
        historical_labels_service._map_template_key(
            _make_application(
                seed=16,
                units_proposed=12,
                route_normalized="OUTLINE",
            )
        )
        == "resi_10_49_outline"
    )
    assert (
        historical_labels_service._map_template_key(_make_application(seed=17, units_proposed=0))
        is None
    )

    assert (
        historical_labels_service._map_proposal_form(
            application=_make_application(seed=18, proposal_description="Backland homes"),
            designation_profile={},
        )
        == ProposalForm.BACKLAND
    )
    assert (
        historical_labels_service._map_proposal_form(
            application=_make_application(seed=19, proposal_description="Infill houses"),
            designation_profile={},
        )
        == ProposalForm.INFILL
    )
    assert (
        historical_labels_service._map_proposal_form(
            application=_make_application(seed=20, proposal_description="Reuse"),
            designation_profile={"brownfield_part1": True},
        )
        == ProposalForm.BROWNFIELD_REUSE
    )
    assert (
        historical_labels_service._map_proposal_form(
            application=_make_application(seed=21, proposal_description="Garage yard reuse"),
            designation_profile={},
        )
        == ProposalForm.BROWNFIELD_REUSE
    )
    assert (
        historical_labels_service._map_proposal_form(
            application=_make_application(seed=22, proposal_description="Simple housing"),
            designation_profile={},
        )
        == ProposalForm.REDEVELOPMENT
    )

    assert (
        historical_labels_service._normalized_decision(
            _make_application(seed=23, decision="Conditional approval")
        )
        == "CONDITIONAL APPROVE"
    )
    assert (
        historical_labels_service._normalized_decision(
            _make_application(seed=24, decision="Minded to grant")
        )
        == "RESOLVE TO GRANT"
    )
    assert (
        historical_labels_service._normalized_decision(
            _make_application(seed=25, decision="", status="")
        )
        == "UNDETERMINED"
    )
    assert (
        historical_labels_service._normalized_decision(
            _make_application(seed=26, decision="Withdrawn")
        )
        == "WITHDRAWN"
    )
    assert (
        historical_labels_service._normalized_decision(
            _make_application(seed=27, decision="Invalid")
        )
        == "INVALID"
    )
    assert (
        historical_labels_service._normalized_decision(
            _make_application(seed=28, decision="Duplicate")
        )
        == "DUPLICATE"
    )
    assert (
        historical_labels_service._normalized_decision(
            _make_application(seed=29, decision="Refused")
        )
        == "REFUSED"
    )
    assert (
        historical_labels_service._normalized_decision(
            _make_application(seed=30, decision="Granted")
        )
        == "APPROVED"
    )
    assert (
        historical_labels_service._normalized_decision(
            _make_application(seed=31, decision="Deferred")
        )
        == "DEFERRED"
    )

    assert historical_labels_service._description_signature(
        "Redevelopment of the site with housing"
    ) == ("housing", "redevelopment")
    assert historical_labels_service._dates_close(
        date(2024, 1, 1),
        date(2024, 1, 20),
        days=30,
    )
    assert not historical_labels_service._dates_close(
        date(2024, 1, 1),
        date(2024, 3, 20),
        days=30,
    )
    assert not historical_labels_service._dates_close(None, date(2024, 1, 1), days=30)
    assert historical_labels_service._add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)

    stronger = _make_application(
        seed=32,
        source_priority=200,
        proposal_description="Housing redevelopment",
        geometry=_Geometry(),
    )
    duplicate = _make_application(
        seed=33,
        source_priority=100,
        proposal_description="Redevelopment housing",
        geometry=_Geometry(geom_type="Point", distance_m=15.0),
    )
    assert (
        historical_labels_service._find_stronger_source(
            application=duplicate,
            stronger_cases=[stronger],
        )
        is stronger
    )
    assert not historical_labels_service._same_case(
        _make_application(seed=34, borough_id="islington"),
        stronger,
    )
    assert not historical_labels_service._same_case(
        _make_application(seed=35, units_proposed=3),
        stronger,
    )
    assert not historical_labels_service._same_case(
        _make_application(seed=36, route_normalized="OUTLINE", units_proposed=12),
        stronger,
    )
    assert not historical_labels_service._same_case(
        _make_application(seed=37, valid_date=date(2025, 6, 1)),
        stronger,
    )

    template_none = historical_labels_service._build_label_payload(
        session=SimpleNamespace(),
        application=_make_application(seed=38, units_proposed=0),
        stronger_cases=[],
    )
    assert template_none["label_class"] == HistoricalLabelClass.EXCLUDED
    assert template_none["label_decision"] == HistoricalLabelDecision.NON_RELEVANT

    outside_window = historical_labels_service._build_label_payload(
        session=SimpleNamespace(),
        application=_make_application(
            seed=39,
            decision="Approved",
            decision_date=date(2026, 8, 1),
            geometry=_Geometry(geom_type="Point"),
        ),
        stronger_cases=[],
    )
    assert outside_window["label_class"] == HistoricalLabelClass.CENSORED
    assert "18-month label window" in outside_window["label_reason"]
    assert outside_window["site_geometry_confidence"] == GeomConfidence.LOW

    negative = historical_labels_service._build_label_payload(
        session=SimpleNamespace(),
        application=_make_application(seed=40, decision="Refused"),
        stronger_cases=[],
    )
    assert negative["label_class"] == HistoricalLabelClass.NEGATIVE
    assert negative["label_decision"] == HistoricalLabelDecision.REFUSE

    withdrawn = historical_labels_service._build_label_payload(
        session=SimpleNamespace(),
        application=_make_application(seed=41, decision="Withdrawn"),
        stronger_cases=[],
    )
    assert withdrawn["label_class"] == HistoricalLabelClass.EXCLUDED
    assert withdrawn["label_decision"] == HistoricalLabelDecision.WITHDRAWN

    undetermined = historical_labels_service._build_label_payload(
        session=SimpleNamespace(),
        application=_make_application(seed=42, decision="Pending"),
        stronger_cases=[],
    )
    assert undetermined["label_class"] == HistoricalLabelClass.CENSORED
    assert undetermined["label_decision"] == HistoricalLabelDecision.UNDETERMINED

    duplicate_payload = historical_labels_service._build_label_payload(
        session=SimpleNamespace(),
        application=duplicate,
        stronger_cases=[stronger],
    )
    assert duplicate_payload["label_decision"] == HistoricalLabelDecision.DUPLICATE
    assert "Stronger source" in duplicate_payload["label_reason"]

    case = SimpleNamespace(
        review_status=GoldSetReviewStatus.CONFIRMED,
        review_notes="ok",
        reviewed_by="pytest",
        reviewed_at=datetime(2026, 4, 18, 9, 0, tzinfo=UTC),
        notable_policy_issues_json=["heritage"],
        extant_permission_outcome="PASS",
        site_geometry_confidence=GeomConfidence.MEDIUM,
    )
    assert historical_labels_service._case_payload(case) == {
        "review_status": GoldSetReviewStatus.CONFIRMED.value,
        "review_notes": "ok",
        "reviewed_by": "pytest",
        "reviewed_at": "2026-04-18T09:00:00+00:00",
        "notable_policy_issues_json": ["heritage"],
        "extant_permission_outcome": "PASS",
        "site_geometry_confidence": GeomConfidence.MEDIUM.value,
    }


def test_extant_permission_helpers_cover_remaining_overlap_and_status_paths(monkeypatch) -> None:
    monkeypatch.setattr(
        extant_permission_service,
        "MANDATORY_EXTANT_SOURCE_FAMILIES",
        ("planning", "brownfield"),
    )
    coverage_gaps = extant_permission_service._coverage_gaps(
        {
            "planning": SimpleNamespace(
                coverage_status=SourceCoverageStatus.PARTIAL,
                gap_reason="missing records",
            )
        }
    )
    assert [warning.code for warning in coverage_gaps] == [
        "MANDATORY_SOURCE_PLANNING_PARTIAL",
        "MANDATORY_SOURCE_BROWNFIELD_MISSING",
    ]

    site_geometry = _Geometry()
    application = SimpleNamespace(site_geom_27700=None)
    assert (
        extant_permission_service._planning_overlap_sqm(
            site_geometry=site_geometry,
            application=application,
        )
        is None
    )

    non_intersecting_site = _Geometry(intersects=False)
    non_intersecting = _Geometry()
    monkeypatch.setattr(
        extant_permission_service,
        "load_wkt_geometry",
        lambda _wkt: non_intersecting,
    )
    application.site_geom_27700 = "POLYGON"
    assert (
        extant_permission_service._planning_overlap_sqm(
            site_geometry=non_intersecting_site,
            application=application,
        )
        is None
    )

    empty_intersection_site = _Geometry(intersection_empty=True)
    empty_intersection = _Geometry()
    monkeypatch.setattr(
        extant_permission_service,
        "load_wkt_geometry",
        lambda _wkt: empty_intersection,
    )
    assert (
        extant_permission_service._planning_overlap_sqm(
            site_geometry=empty_intersection_site,
            application=application,
        )
        is None
    )

    overlapping_site = _Geometry(overlap_area=135.0)
    overlapping = _Geometry()
    monkeypatch.setattr(
        extant_permission_service,
        "load_wkt_geometry",
        lambda _wkt: overlapping,
    )
    assert extant_permission_service._planning_overlap_sqm(
        site_geometry=overlapping_site,
        application=application,
    ) == pytest.approx(135.0)

    assert extant_permission_service._is_material_overlap(
        overlap_pct=0.2,
        overlap_sqm=None,
        raw_record_json={},
        link_type="INTERSECTS",
    )
    assert extant_permission_service._is_material_overlap(
        overlap_pct=None,
        overlap_sqm=120.0,
        raw_record_json={},
        link_type="INTERSECTS",
    )
    assert extant_permission_service._is_material_overlap(
        overlap_pct=None,
        overlap_sqm=None,
        raw_record_json={"material_access_control": True},
        link_type="INTERSECTS",
    )
    assert extant_permission_service._is_material_overlap(
        overlap_pct=None,
        overlap_sqm=None,
        raw_record_json={"material_core_envelope": True},
        link_type="POINT_WITHIN_SITE",
    )
    assert not extant_permission_service._is_material_overlap(
        overlap_pct=0.01,
        overlap_sqm=20.0,
        raw_record_json={},
        link_type="INTERSECTS",
    )

    active_application = SimpleNamespace(
        route_normalized="FULL",
        decision_type="FULL_RESIDENTIAL",
        status="APPROVED",
        raw_record_json={"dwelling_use": "C3", "active_extant": True},
        application_type="FULL",
        external_ref="APP-1",
    )
    assert (
        extant_permission_service._is_active_residential_permission(
            active_application,
            application_snapshot={"route_normalized": "OTHER"},
            as_of_date=date(2026, 4, 18),
        )
        is False
    )
    assert (
        extant_permission_service._is_active_residential_permission(
            active_application,
            application_snapshot={"decision_type": "COMMERCIAL"},
            as_of_date=date(2026, 4, 18),
        )
        is False
    )
    assert (
        extant_permission_service._is_active_residential_permission(
            active_application,
            application_snapshot={"status": "WITHDRAWN"},
            as_of_date=date(2026, 4, 18),
        )
        is False
    )
    assert (
        extant_permission_service._is_active_residential_permission(
            active_application,
            application_snapshot={"raw_record_json": {"dwelling_use": "B8"}},
            as_of_date=date(2026, 4, 18),
        )
        is False
    )
    assert (
        extant_permission_service._is_active_residential_permission(
            active_application,
            application_snapshot={"raw_record_json": {"expiry_date": "2026-04-01"}},
            as_of_date=date(2026, 4, 18),
        )
        is False
    )
    assert (
        extant_permission_service._is_active_residential_permission(
            active_application,
            application_snapshot={"raw_record_json": {"active_extant": False}},
            as_of_date=date(2026, 4, 18),
        )
        is False
    )
    assert extant_permission_service._is_active_residential_permission(
        active_application,
        as_of_date=date(2026, 4, 18),
    )

    assert extant_permission_service._is_non_exclusionary_permission(
        active_application,
        application_snapshot={"status": "WITHDRAWN"},
        as_of_date=date(2026, 4, 18),
    )
    assert extant_permission_service._is_non_exclusionary_permission(
        active_application,
        application_snapshot={"raw_record_json": {"lapsed": True}},
        as_of_date=date(2026, 4, 18),
    )
    assert extant_permission_service._is_non_exclusionary_permission(
        active_application,
        application_snapshot={"raw_record_json": {"expiry_date": "2026-04-01"}},
        as_of_date=date(2026, 4, 18),
    )
    assert not extant_permission_service._is_non_exclusionary_permission(
        active_application,
        application_snapshot={"raw_record_json": {"expiry_date": "2026-05-01"}},
        as_of_date=date(2026, 4, 18),
    )

    assert extant_permission_service._is_residential(None)
    assert extant_permission_service._is_residential({"dwelling_use": "C3A"})
    assert not extant_permission_service._is_residential({"dwelling_use": "B8"})

    brownfield_state = SimpleNamespace(
        part="PART_2",
        effective_to=None,
        pip_status="ACTIVE",
        tdc_status=None,
        id=uuid4(),
        external_ref="BF-1",
        source_url="https://example.test/bf-1",
        source_snapshot_id=uuid4(),
        geom_27700="POLYGON",
    )
    assert not extant_permission_service._is_active_brownfield_exclusion(
        SimpleNamespace(part="PART_1", effective_to=None, pip_status="ACTIVE", tdc_status=None),
        as_of_date=date(2026, 4, 18),
    )
    assert not extant_permission_service._is_active_brownfield_exclusion(
        SimpleNamespace(
            part="PART_2",
            effective_to=date(2026, 4, 1),
            pip_status="ACTIVE",
            tdc_status=None,
        ),
        as_of_date=date(2026, 4, 18),
    )
    assert extant_permission_service._is_active_brownfield_exclusion(
        brownfield_state,
        as_of_date=date(2026, 4, 18),
    )
    assert extant_permission_service._is_active_brownfield_exclusion(
        SimpleNamespace(part="PART_2", effective_to=None, pip_status=None, tdc_status="ACTIVE"),
        as_of_date=date(2026, 4, 18),
    )

    monkeypatch.setattr(
        extant_permission_service,
        "match_generic_geometry",
        lambda **_kwargs: None,
    )
    assert (
        extant_permission_service._brownfield_match(
            site_geometry=site_geometry,
            site_area_sqm=200.0,
            state=brownfield_state,
            as_of_date=date(2026, 4, 18),
        )
        is None
    )

    monkeypatch.setattr(
        extant_permission_service,
        "match_generic_geometry",
        lambda **_kwargs: SimpleNamespace(overlap_pct=0.05, overlap_sqm=40.0, distance_m=0.0),
    )
    inactive_match = extant_permission_service._brownfield_match(
        site_geometry=site_geometry,
        site_area_sqm=200.0,
        state=SimpleNamespace(
            **{**brownfield_state.__dict__, "part": "PART_1", "pip_status": None}
        ),
        as_of_date=date(2026, 4, 18),
    )
    assert inactive_match is not None
    assert inactive_match.material is False
    assert "informative" in inactive_match.detail

    active_match = extant_permission_service._brownfield_match(
        site_geometry=site_geometry,
        site_area_sqm=200.0,
        state=brownfield_state,
        as_of_date=date(2026, 4, 18),
    )
    assert active_match is not None
    assert "active PiP/TDC evidence" in active_match.detail

    monkeypatch.setattr(
        extant_permission_service,
        "_is_active_residential_permission",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(
        extant_permission_service,
        "_is_non_exclusionary_permission",
        lambda *args, **kwargs: False,
    )
    assert "Material active" in extant_permission_service._planning_detail(
        application=active_application,
        application_snapshot={"external_ref": "APP-2", "route_normalized": "FULL"},
        material=True,
        as_of_date=date(2026, 4, 18),
    )
    assert "Potential active" in extant_permission_service._planning_detail(
        application=active_application,
        application_snapshot={"external_ref": "APP-2", "route_normalized": "FULL"},
        material=False,
        as_of_date=date(2026, 4, 18),
    )

    monkeypatch.setattr(
        extant_permission_service,
        "_is_active_residential_permission",
        lambda *args, **kwargs: False,
    )
    monkeypatch.setattr(
        extant_permission_service,
        "_is_non_exclusionary_permission",
        lambda *args, **kwargs: True,
    )
    assert "Historic or non-active planning record" in extant_permission_service._planning_detail(
        application=active_application,
        application_snapshot={"external_ref": "APP-3"},
        material=False,
        as_of_date=date(2026, 4, 18),
    )

    monkeypatch.setattr(
        extant_permission_service,
        "_is_non_exclusionary_permission",
        lambda *args, **kwargs: False,
    )
    assert (
        extant_permission_service._planning_detail(
            application=active_application,
            application_snapshot={"external_ref": "APP-4"},
            material=False,
            as_of_date=date(2026, 4, 18),
        )
        == "Planning record APP-4 was linked to the site."
    )

    assert extant_permission_service._parse_date_from_record(None, "expiry_date") is None
    assert extant_permission_service._parse_date_from_record({}, "expiry_date") is None
    assert extant_permission_service._parse_date_from_record(
        {"expiry_date": "2026-04-18"},
        "expiry_date",
    ) == date(2026, 4, 18)


def test_audit_export_failure_helper_and_minimal_manifest_paths(monkeypatch) -> None:
    monkeypatch.setattr(
        audit_export_service,
        "require_role",
        lambda *_args, **_kwargs: AppRoleName.REVIEWER,
    )

    missing_session = _QueueSession(_Result(scalar=None))
    with pytest.raises(ReviewAccessError, match="was not found"):
        audit_export_service.build_assessment_audit_export(
            session=missing_session,
            storage=_MemoryStorage(),
            assessment_id=_fixed_uuid(70),
            requested_by="pytest",
            actor_role=AppRoleName.REVIEWER,
        )

    run = SimpleNamespace(
        id=_fixed_uuid(71),
        result=None,
        prediction_ledger=None,
        valuation_runs=[],
        overrides=[],
    )
    missing_detail_session = _QueueSession(_Result(scalar=run))
    monkeypatch.setattr(audit_export_service, "get_assessment", lambda **_kwargs: None)
    with pytest.raises(ReviewAccessError, match="was not found"):
        audit_export_service.build_assessment_audit_export(
            session=missing_detail_session,
            storage=_MemoryStorage(),
            assessment_id=run.id,
            requested_by="pytest",
            actor_role=AppRoleName.REVIEWER,
        )

    assert (
        audit_export_service._serialize_audit_events(
            session=SimpleNamespace(),
            entity_refs=[],
        )
        == []
    )

    entity_refs = audit_export_service._entity_refs_for_run(
        SimpleNamespace(
            id=_fixed_uuid(72),
            result=SimpleNamespace(id=_fixed_uuid(73), model_release_id=_fixed_uuid(74)),
            prediction_ledger=SimpleNamespace(id=_fixed_uuid(75), valuation_run_id=None),
            overrides=[SimpleNamespace(id=_fixed_uuid(76))],
            valuation_runs=[],
        )
    )
    assert entity_refs == [
        ("assessment_run", str(_fixed_uuid(72))),
        ("assessment_result", str(_fixed_uuid(73))),
        ("model_release", str(_fixed_uuid(74))),
        ("prediction_ledger", str(_fixed_uuid(75))),
        ("assessment_override", str(_fixed_uuid(76))),
    ]
    assert audit_export_service._json_bytes({"b": 1, "a": 2}) == b'{"a":2,"b":1}'
    assert (
        audit_export_service._sha256(b"fixture")
        == "f16d05ec6b29248d2c61adb1e9263f78e4f7bace1b955014a2d17872cfe4064d"
    )

    monkeypatch.setattr(
        audit_export_service,
        "get_assessment",
        lambda **_kwargs: _AssessmentDetail(),
    )
    monkeypatch.setattr(
        audit_export_service,
        "frozen_valuation_run",
        lambda _run: None,
    )
    monkeypatch.setattr(
        audit_export_service,
        "_serialize_audit_events",
        lambda **_kwargs: [],
    )
    storage = _MemoryStorage()
    export_session = _AuditSession(run)
    export = audit_export_service.build_assessment_audit_export(
        session=export_session,
        storage=storage,
        assessment_id=run.id,
        requested_by="pytest",
        actor_role=AppRoleName.REVIEWER,
    )
    assert export.manifest_json["site_summary"] is None
    assert export.manifest_json["scenario_summary"] is None
    assert export.manifest_json["visibility"] is None
    assert storage.calls[0][0] == f"artifacts/audit_exports/{export.id}/manifest.json"
    assert export_session.flushed == 1
