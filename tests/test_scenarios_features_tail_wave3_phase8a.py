from __future__ import annotations

from collections import deque
from datetime import UTC, date, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest
from landintel.domain.enums import (
    BaselinePackStatus,
    EligibilityStatus,
    ExtantPermissionStatus,
    GeomConfidence,
    ProposalForm,
    ScenarioSource,
    ScenarioStatus,
    SourceFreshnessStatus,
)
from landintel.domain.models import SiteScenario
from landintel.domain.schemas import ScenarioConfirmRequest, ScenarioReasonRead
from landintel.features import build as features_build
from landintel.scenarios import normalize as normalize_service
from landintel.scenarios import suggest as suggest_service


class _Result:
    def __init__(self, *, scalar=None, items=None):
        self._scalar = scalar
        self._items = list(items or [])

    def scalar_one_or_none(self):
        return self._scalar

    def scalar_one(self):
        if self._scalar is None:
            raise LookupError("missing scalar")
        return self._scalar

    def scalars(self):
        return self

    def unique(self):
        return self

    def all(self):
        return list(self._items)


class _Session:
    def __init__(self, *, execute_results=None, get_result=None):
        self.execute_results = deque(execute_results or [])
        self.get_result = get_result
        self.added: list[object] = []
        self.flush_count = 0
        self.execute_calls: list[object] = []

    def execute(self, stmt):
        self.execute_calls.append(stmt)
        if self.execute_results:
            return self.execute_results.popleft()
        return _Result(items=[])

    def get(self, model, identity):
        del model, identity
        return self.get_result

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        self.flush_count += 1


def _site(
    *,
    site_id: str = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
    borough_id: str = "camden",
    geom_hash: str = "site-hash-1",
    area_sqm: float = 250.0,
    geom_confidence: GeomConfidence = GeomConfidence.HIGH,
    display_name: str = "Camden fixture site",
):
    return SimpleNamespace(
        id=UUID(site_id),
        borough_id=borough_id,
        display_name=display_name,
        geom_hash=geom_hash,
        site_area_sqm=area_sqm,
        geom_confidence=geom_confidence,
        geometry_revisions=[],
        scenarios=[],
        planning_links=[],
        policy_facts=[],
        constraint_facts=[],
    )


def _revision(*, geom_hash: str, revision_id: str = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"):
    return SimpleNamespace(id=UUID(revision_id), geom_hash=geom_hash)


def _template(*, key: str = "resi_5_9_full"):
    return SimpleNamespace(
        key=key,
        version="1.0",
        config_json={
            "site_area_sqm_range": {"min": 100.0, "max": 350.0},
            "units_range": {"min": 5, "max": 9},
            "default_net_developable_area_pct": 0.7,
            "default_route": "FULL",
            "default_proposal_form": ProposalForm.REDEVELOPMENT,
            "default_height_band": "MID_RISE",
        },
    )


def _rulepack(*, template_key: str):
    return SimpleNamespace(
        template_key=template_key,
        freshness_status=SourceFreshnessStatus.FRESH,
        rule_json={
            "citations": [
                {
                    "label": "Rule source",
                    "source_family": "BOROUGH_REGISTER",
                    "effective_date": "2026-04-01",
                    "source_snapshot_id": str(UUID("aaaaaaaa-0000-0000-0000-000000000001")),
                }
            ],
            "scenario_rules": {},
        },
    )


def _extant_permission(
    *,
    status: ExtantPermissionStatus = ExtantPermissionStatus.NO_ACTIVE_PERMISSION_FOUND,
    eligibility_status: EligibilityStatus = EligibilityStatus.PASS,
    summary: str = "clean",
):
    return SimpleNamespace(
        status=status,
        eligibility_status=eligibility_status,
        coverage_gaps=[],
        summary=summary,
    )


def _application(
    *,
    external_ref: str = "CAM-2026-1000",
    route_normalized: str = "FULL",
    units_proposed: int = 8,
    decision: str = "APPROVED",
    status: str = "APPROVED",
    decision_type: str = "FULL_RESIDENTIAL",
    proposal_description: str = "Residential flat scheme.",
    source_system: str = "BOROUGH_REGISTER",
):
    return SimpleNamespace(
        id=UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
        external_ref=external_ref,
        source_url=f"https://example.test/{external_ref}",
        source_snapshot_id=UUID("dddddddd-dddd-dddd-dddd-dddddddddddd"),
        documents=[SimpleNamespace(asset_id=UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"))],
        source_system=source_system,
        status=status,
        decision=decision,
        decision_type=decision_type,
        route_normalized=route_normalized,
        units_proposed=units_proposed,
        proposal_description=proposal_description,
        valid_date=date(2025, 1, 1),
        decision_date=date(2025, 1, 2),
        source_priority=1,
        raw_record_json={},
    )


def _link(app, distance_m: int = 0):
    return SimpleNamespace(planning_application=app, distance_m=distance_m)


def _scenario(
    *,
    scenario_id: str,
    site,
    status: ScenarioStatus,
    scenario_source: ScenarioSource,
    is_current: bool = True,
    is_headline: bool = False,
    heuristic_rank: int | None = 4,
    red_line_geom_hash: str | None = None,
):
    return SimpleNamespace(
        id=UUID(scenario_id),
        site=site,
        site_id=site.id,
        template_key="resi_5_9_full",
        template_version="1.0",
        proposal_form=ProposalForm.REDEVELOPMENT,
        units_assumed=6,
        route_assumed="FULL",
        height_band_assumed="MID_RISE",
        net_developable_area_pct=0.7,
        housing_mix_assumed_json={},
        parking_assumption=None,
        affordable_housing_assumption=None,
        access_assumption=None,
        site_geometry_revision_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        red_line_geom_hash=red_line_geom_hash or site.geom_hash,
        scenario_source=scenario_source,
        status=status,
        supersedes_id=None,
        is_current=is_current,
        is_headline=is_headline,
        heuristic_rank=heuristic_rank,
        manual_review_required=False,
        stale_reason=None,
        rationale_json={"warning_codes": []},
        evidence_json={},
        created_by="pytest",
        updated_at=datetime(2025, 1, 1, tzinfo=UTC),
        assessment_runs=[],
        reviews=[],
    )


def _policy_row(*, family: str, source_snapshot_id: str):
    return SimpleNamespace(
        policy_family=family,
        geom_27700="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
        source_snapshot_id=UUID(source_snapshot_id),
        legal_effective_from=date(2025, 1, 1),
        legal_effective_to=None,
    )


def _constraint_row(*, family: str, subtype: str, source_snapshot_id: str):
    return SimpleNamespace(
        feature_family=family,
        feature_subtype=subtype,
        geom_27700="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
        source_snapshot_id=UUID(source_snapshot_id),
        effective_from=date(2025, 1, 1),
        effective_to=None,
    )


def _brownfield_row(
    *, part: str, source_snapshot_id: str, pip_status: str = "", tdc_status: str = ""
):
    return SimpleNamespace(
        part=part,
        geom_27700="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
        source_snapshot_id=UUID(source_snapshot_id),
        effective_from=date(2025, 1, 1),
        effective_to=None,
        pip_status=pip_status,
        tdc_status=tdc_status,
    )


def test_suggest_helpers_cover_no_support_route_and_no_geometry_fast_exit(monkeypatch):
    assert suggest_service._citations_complete(
        [
            {
                "label": "Rule source",
                "source_family": "BOROUGH_REGISTER",
                "effective_date": "2026-04-01",
                "url": "https://example.test/rule",
            }
        ]
    )
    assert not suggest_service._citations_complete([])

    app = _application()
    support_none = suggest_service._nearest_historical_support(
        site=_site(),
        min_units=5,
        max_units=9,
        route_assumed="FULL",
    )
    assert support_none.application is None
    assert support_none.strong is False

    site = _site()
    site.planning_links = [
        _link(_application(source_system="PLD"), distance_m=1),
        _link(_application(units_proposed=None), distance_m=1),
        _link(app, distance_m=2),
    ]
    support = suggest_service._nearest_historical_support(
        site=site,
        min_units=5,
        max_units=9,
        route_assumed="FULL",
    )
    assert support.application is app
    assert support.strong is True

    allowed, reasons = suggest_service._auto_confirm_allowed(
        site=SimpleNamespace(geom_confidence=GeomConfidence.LOW),
        template_key="resi_5_9_full",
        preferred_route="DIAGONAL",
        support=SimpleNamespace(strong=False),
        extant_permission=SimpleNamespace(eligibility_status=EligibilityStatus.FAIL),
        missing_data_flags=["MISSING"],
        warning_codes=["RULEPACK_STALE"],
    )
    assert allowed is False
    assert {code for code, _ in reasons} == {
        "AUTO_CONFIRM_BLOCKED_GEOMETRY",
        "AUTO_CONFIRM_BLOCKED_EXTANT",
        "AUTO_CONFIRM_BLOCKED_MISSING_DATA",
        "AUTO_CONFIRM_BLOCKED_STALE_SOURCE",
        "AUTO_CONFIRM_BLOCKED_HISTORICAL_SUPPORT",
        "AUTO_CONFIRM_BLOCKED_ROUTE",
    }
    assert suggest_service._dedupe(["a", "", "a", "b"]) == ["a", "b"]

    monkeypatch.setattr(
        suggest_service,
        "get_enabled_scenario_templates",
        lambda _session, template_keys=None: [_template(key="resi_5_9_full")],
    )
    monkeypatch.setattr(
        suggest_service,
        "get_borough_baseline_pack",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        suggest_service,
        "evaluate_site_extant_permission",
        lambda **kwargs: _extant_permission(),
    )
    monkeypatch.setattr(
        suggest_service,
        "assemble_site_evidence",
        lambda **kwargs: SimpleNamespace(model_dump=lambda **dump_kwargs: {}),
    )

    response = suggest_service.refresh_site_scenarios(
        session=object(),
        site=_site(),
        requested_by="pytest",
    )
    assert response.items == []
    assert response.excluded_templates[0].reasons[0].code == "NO_GEOMETRY_REVISION"


def test_suggest_candidate_persistence_and_stale_marking(monkeypatch):
    site = _site()
    site.geometry_revisions = [_revision(geom_hash=site.geom_hash)]
    existing_auto = _scenario(
        scenario_id="11111111-1111-1111-1111-111111111111",
        site=site,
        status=ScenarioStatus.AUTO_CONFIRMED,
        scenario_source=ScenarioSource.AUTO,
        is_current=True,
        is_headline=True,
    )
    existing_analyst = _scenario(
        scenario_id="22222222-2222-2222-2222-222222222222",
        site=site,
        status=ScenarioStatus.ANALYST_CONFIRMED,
        scenario_source=ScenarioSource.ANALYST,
        is_current=True,
        is_headline=False,
        heuristic_rank=0,
    )
    site.scenarios = [existing_auto, existing_analyst]
    template = _template()
    candidate = suggest_service.ScenarioCandidate(
        template_key=template.key,
        template_version=template.version,
        proposal_form=ProposalForm.REDEVELOPMENT,
        units_assumed=7,
        route_assumed="FULL",
        height_band_assumed="MID_RISE",
        net_developable_area_pct=0.7,
        housing_mix_assumed_json={"one_bed": 3},
        parking_assumption="on-site",
        affordable_housing_assumption="35%",
        access_assumption="west access",
        heuristic_rank=1,
        score=9,
        status=ScenarioStatus.AUTO_CONFIRMED,
        manual_review_required=False,
        reason_codes=[ScenarioReasonRead(code="AREA_CAPACITY_HEURISTIC", message="fixture")],
        missing_data_flags=[],
        warning_codes=[],
        support=suggest_service.CandidateSupport(application=_application(), strong=True),
    )
    session = _Session()

    monkeypatch.setattr(
        suggest_service,
        "get_enabled_scenario_templates",
        lambda _session, template_keys=None: [template],
    )
    monkeypatch.setattr(
        suggest_service,
        "get_borough_baseline_pack",
        lambda **kwargs: SimpleNamespace(
            status=BaselinePackStatus.PILOT_READY,
            freshness_status=SourceFreshnessStatus.FRESH,
            rulepacks=[],
        ),
    )
    monkeypatch.setattr(
        suggest_service,
        "evaluate_site_extant_permission",
        lambda **kwargs: _extant_permission(),
    )
    monkeypatch.setattr(
        suggest_service,
        "assemble_site_evidence",
        lambda **kwargs: SimpleNamespace(model_dump=lambda **dump_kwargs: {"site": "evidence"}),
    )
    monkeypatch.setattr(
        suggest_service,
        "assemble_scenario_evidence",
        lambda **kwargs: SimpleNamespace(model_dump=lambda **dump_kwargs: {"scenario": "evidence"}),
    )
    monkeypatch.setattr(
        suggest_service,
        "_evaluate_template_candidate",
        lambda **kwargs: (candidate, None),
    )
    monkeypatch.setattr(
        "landintel.services.scenarios_readback.serialize_site_scenario_summary",
        lambda **kwargs: SimpleNamespace(
            id=kwargs["scenario"].id,
            site_id=kwargs["scenario"].site_id,
            template_key=kwargs["scenario"].template_key,
            template_version=kwargs["scenario"].template_version,
            proposal_form=kwargs["scenario"].proposal_form,
            units_assumed=kwargs["scenario"].units_assumed,
            route_assumed=kwargs["scenario"].route_assumed,
            height_band_assumed=kwargs["scenario"].height_band_assumed,
            net_developable_area_pct=kwargs["scenario"].net_developable_area_pct,
            red_line_geom_hash=kwargs["scenario"].red_line_geom_hash,
            scenario_source=kwargs["scenario"].scenario_source,
            status=kwargs["scenario"].status,
            supersedes_id=kwargs["scenario"].supersedes_id,
            is_current=kwargs["scenario"].is_current,
            is_headline=bool(kwargs["scenario"].is_headline),
            heuristic_rank=kwargs["scenario"].heuristic_rank,
            manual_review_required=kwargs["scenario"].manual_review_required,
            stale_reason=kwargs["scenario"].stale_reason,
            housing_mix_assumed_json=kwargs["scenario"].housing_mix_assumed_json,
            parking_assumption=kwargs["scenario"].parking_assumption,
            affordable_housing_assumption=kwargs["scenario"].affordable_housing_assumption,
            access_assumption=kwargs["scenario"].access_assumption,
            reason_codes=[],
            missing_data_flags=[],
            warning_codes=[],
        ).__dict__,
    )

    response = suggest_service.refresh_site_scenarios(
        session=session,
        site=site,
        requested_by="pytest",
    )
    assert response.headline_scenario_id == existing_auto.id
    assert len(response.items) == 1
    assert response.items[0].is_headline is False
    assert any(isinstance(item, SiteScenario) for item in session.added)
    assert existing_auto.is_current is False
    assert existing_auto.is_headline is False
    persisted = next(item for item in session.added if isinstance(item, SiteScenario))
    assert persisted.status == ScenarioStatus.AUTO_CONFIRMED
    assert persisted.red_line_geom_hash == site.geom_hash


def test_normalize_helpers_cover_current_revision_request_fields_and_supersede(monkeypatch):
    site = _site()
    current_revision = _revision(geom_hash=site.geom_hash)
    site.geometry_revisions = [
        SimpleNamespace(id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"), geom_hash="old"),
        current_revision,
    ]

    assert normalize_service._current_geometry_revision(_site()) is None
    assert normalize_service._current_geometry_revision(site) is current_revision

    scenario = _scenario(
        scenario_id="33333333-3333-3333-3333-333333333333",
        site=site,
        status=ScenarioStatus.AUTO_CONFIRMED,
        scenario_source=ScenarioSource.AUTO,
    )
    assert normalize_service._edits_present(ScenarioConfirmRequest()) is False
    assert (
        normalize_service._edits_present(
            ScenarioConfirmRequest(requested_by="pytest", units_assumed=8)
        )
        is True
    )

    request = ScenarioConfirmRequest(
        requested_by="pytest",
        proposal_form=ProposalForm.BACKLAND,
        units_assumed=8,
        route_assumed="OUTLINE",
        height_band_assumed="LOW_RISE",
        net_developable_area_pct=0.61,
        housing_mix_assumed_json={"studio": 1},
        parking_assumption="none",
        affordable_housing_assumption="20%",
        access_assumption="shared access",
    )
    normalize_service._apply_request_fields(target=scenario, request=request)
    assert scenario.proposal_form == ProposalForm.BACKLAND
    assert scenario.units_assumed == 8
    assert scenario.route_assumed == "OUTLINE"
    assert scenario.housing_mix_assumed_json == {"studio": 1}

    payload = normalize_service._scenario_payload(scenario)
    assert payload["scenario_id"] == str(scenario.id)
    assert payload["status"] == ScenarioStatus.AUTO_CONFIRMED.value

    normalize_service._append_warning_code(scenario, "SCENARIO_STALE_GEOMETRY")
    normalize_service._append_warning_code(scenario, "SCENARIO_STALE_GEOMETRY")
    assert scenario.rationale_json["warning_codes"] == ["SCENARIO_STALE_GEOMETRY"]
    normalize_service._remove_warning_code(scenario, "SCENARIO_STALE_GEOMETRY")
    assert scenario.rationale_json["warning_codes"] == []

    session = _Session(execute_results=[_Result(scalar=scenario)])
    loaded = normalize_service._load_scenario(session=session, scenario_id=scenario.id)
    assert loaded is scenario
    with pytest.raises(normalize_service.ScenarioNormalizeError):
        normalize_service._load_scenario(
            session=_Session(execute_results=[_Result(scalar=None)]),
            scenario_id=UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"),
        )

    superseded = normalize_service._superseding_scenario(
        session=_Session(),
        source=scenario,
        current_revision=current_revision,
        request=ScenarioConfirmRequest(requested_by="pytest", units_assumed=9),
    )
    assert superseded.supersedes_id == scenario.id
    assert superseded.scenario_source == ScenarioSource.ANALYST
    assert superseded.units_assumed == 9
    assert superseded.is_current is True

    rejected_site = _site()
    rejected_site.geometry_revisions = [current_revision]
    rejected_scenario = _scenario(
        scenario_id="44444444-4444-4444-4444-444444444444",
        site=rejected_site,
        status=ScenarioStatus.AUTO_CONFIRMED,
        scenario_source=ScenarioSource.AUTO,
    )
    rejected_site.scenarios = [rejected_scenario]
    session = _Session()
    monkeypatch.setattr(
        normalize_service,
        "_load_scenario",
        lambda **kwargs: rejected_scenario,
    )
    monkeypatch.setattr(
        normalize_service,
        "evaluate_site_extant_permission",
        lambda **kwargs: _extant_permission(),
    )
    monkeypatch.setattr(
        normalize_service,
        "refresh_scenario_evidence",
        lambda **kwargs: None,
    )
    result = normalize_service.confirm_or_update_scenario(
        session=session,
        scenario_id=rejected_scenario.id,
        request=ScenarioConfirmRequest(
            requested_by="pytest",
            action="REJECT",
            review_notes="not suitable",
        ),
    )
    assert result.status == ScenarioStatus.REJECTED
    assert result.is_current is False
    assert result.is_headline is False
    assert session.flush_count == 1


def test_feature_helpers_cover_designation_profile_and_archetype():
    class _FeatureSession:
        def __init__(self):
            self.results = deque(
                [
                    _Result(
                        items=[
                            _policy_row(
                                family="SITE_ALLOCATION",
                                source_snapshot_id="11111111-1111-1111-1111-111111111111",
                            ),
                            _policy_row(
                                family="DENSITY_GUIDANCE",
                                source_snapshot_id="22222222-2222-2222-2222-222222222222",
                            ),
                        ]
                    ),
                    _Result(
                        items=[
                            _constraint_row(
                                family="heritage",
                                subtype="conservation_area",
                                source_snapshot_id="33333333-3333-3333-3333-333333333333",
                            ),
                            _constraint_row(
                                family="flood",
                                subtype="zone2",
                                source_snapshot_id="44444444-4444-4444-4444-444444444444",
                            ),
                        ]
                    ),
                    _Result(
                        items=[
                            _brownfield_row(
                                part="PART_1",
                                source_snapshot_id="55555555-5555-5555-5555-555555555555",
                                pip_status="ACTIVE",
                            ),
                            _brownfield_row(
                                part="PART_2",
                                source_snapshot_id="66666666-6666-6666-6666-666666666666",
                                tdc_status="ACTIVE",
                            ),
                        ]
                    ),
                ]
            )

        def execute(self, stmt):
            del stmt
            return self.results.popleft()

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        features_build,
        "match_generic_geometry",
        lambda **kwargs: True,
    )
    profile, source_ids = features_build.build_designation_profile_for_geometry(
        session=_FeatureSession(),
        geometry=SimpleNamespace(),
        area_sqm=200.0,
        as_of_date=date(2026, 4, 18),
    )
    assert profile["has_site_allocation"] is True
    assert profile["has_density_guidance"] is True
    assert profile["has_conservation_area"] is True
    assert profile["has_flood_zone"] is True
    assert profile["brownfield_part1"] is True
    assert profile["brownfield_part2_active"] is True
    assert profile["pip_active"] is True
    assert profile["tdc_active"] is True
    assert "11111111-1111-1111-1111-111111111111" in source_ids
    assert "66666666-6666-6666-6666-666666666666" in source_ids

    assert (
        features_build.derive_archetype_key(
            template_key="resi_5_9_full",
            proposal_form=ProposalForm.REDEVELOPMENT,
            designation_profile=profile,
        )
        == "resi_5_9_full:REDEVELOPMENT:heritage:brownfield:flood"
    )
    assert (
        features_build.planning_application_geometry(
            SimpleNamespace(site_geom_27700=None, site_point_27700=None)
        )
        is None
    )
    assert (
        features_build.planning_application_area_sqm(
            SimpleNamespace(site_geom_27700=None, site_point_27700=None)
        )
        == 0.0
    )
    assert (
        features_build.planning_application_area_sqm(
            SimpleNamespace(
                site_geom_27700="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))", site_point_27700=None
            )
        )
        == 1.0
    )
    monkeypatch.undo()
