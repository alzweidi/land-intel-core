from __future__ import annotations

from collections import deque
from datetime import UTC, datetime
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
from landintel.domain.models import AuditEvent, ScenarioReview, SiteScenario
from landintel.domain.schemas import ScenarioConfirmRequest, ScenarioReasonRead
from landintel.scenarios import normalize as normalize_service
from landintel.scenarios import suggest as suggest_service


class _Result:
    def __init__(self, *, scalar=None, items=None):
        self._scalar = scalar
        self._items = list(items or [])

    def scalar_one(self):
        if self._scalar is None:
            raise LookupError("missing scalar")
        return self._scalar

    def scalar_one_or_none(self):
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


def _revision(*, geom_hash: str, revision_id: str = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"):
    return SimpleNamespace(id=UUID(revision_id), geom_hash=geom_hash)


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
    )


def _template(
    *,
    key: str = "resi_5_9_full",
    version: str = "1.0",
    config_json: dict[str, object] | None = None,
):
    return SimpleNamespace(
        key=key,
        version=version,
        config_json=config_json
        or {
            "site_area_sqm_range": {"min": 100.0, "max": 350.0},
            "units_range": {"min": 5, "max": 9},
            "default_net_developable_area_pct": 0.7,
            "default_route": "FULL",
            "default_proposal_form": ProposalForm.REDEVELOPMENT,
            "default_height_band": "MID_RISE",
        },
    )


def _rulepack(
    *,
    template_key: str,
    citations: list[dict[str, object]] | None,
    freshness_status: SourceFreshnessStatus = SourceFreshnessStatus.FRESH,
    scenario_rules: dict[str, object] | None = None,
):
    return SimpleNamespace(
        template_key=template_key,
        freshness_status=freshness_status,
        rule_json={
            "citations": citations or [],
            "scenario_rules": scenario_rules or {},
        },
    )


def _extant_permission(
    *,
    status: ExtantPermissionStatus = ExtantPermissionStatus.NO_ACTIVE_PERMISSION_FOUND,
    eligibility_status: EligibilityStatus = EligibilityStatus.PASS,
    coverage_gaps: list[SimpleNamespace] | None = None,
    summary: str = "clean",
):
    return SimpleNamespace(
        status=status,
        eligibility_status=eligibility_status,
        coverage_gaps=coverage_gaps or [],
        summary=summary,
    )


def _strong_planning_application(
    *,
    external_ref: str = "CAM-2026-1000",
    source_priority: int = 1,
    decision: str = "APPROVED",
    status: str = "APPROVED",
    route_normalized: str = "FULL",
    units_proposed: int = 8,
    decision_type: str = "FULL_RESIDENTIAL",
    proposal_description: str = "Residential flat scheme.",
):
    return SimpleNamespace(
        id=UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
        external_ref=external_ref,
        source_url=f"https://example.test/{external_ref}",
        source_snapshot_id=UUID("dddddddd-dddd-dddd-dddd-dddddddddddd"),
        documents=[SimpleNamespace(asset_id=UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"))],
        source_system="BOROUGH_REGISTER",
        status=status,
        decision=decision,
        decision_type=decision_type,
        route_normalized=route_normalized,
        units_proposed=units_proposed,
        proposal_description=proposal_description,
        source_priority=source_priority,
        valid_date=datetime(2025, 1, 1, tzinfo=UTC).date(),
        decision_date=datetime(2025, 1, 2, tzinfo=UTC).date(),
    )


def _link(app, distance_m: int = 0):
    return SimpleNamespace(planning_application=app, distance_m=distance_m)


def _scenario_stub(
    *,
    scenario_id: str,
    site,
    status: ScenarioStatus = ScenarioStatus.AUTO_CONFIRMED,
    scenario_source: ScenarioSource = ScenarioSource.AUTO,
    is_current: bool = True,
    is_headline: bool = False,
    heuristic_rank: int | None = 4,
    stale_reason: str | None = None,
    review_history: list[ScenarioReview] | None = None,
    assessment_runs: list[object] | None = None,
    red_line_geom_hash: str | None = None,
    units_assumed: int = 6,
):
    return SimpleNamespace(
        id=UUID(scenario_id),
        site=site,
        site_id=site.id,
        template_key="resi_5_9_full",
        template_version="1.0",
        proposal_form=ProposalForm.REDEVELOPMENT,
        units_assumed=units_assumed,
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
        stale_reason=stale_reason,
        rationale_json={"warning_codes": []},
        evidence_json={},
        created_by="pytest",
        updated_at=datetime(2025, 1, 1, tzinfo=UTC),
        assessment_runs=list(assessment_runs or []),
        reviews=list(review_history or []),
    )


def test_suggest_entrypoint_delegates_and_missing_geometry_excludes_templates(monkeypatch):
    site = _site()
    refresh_calls: list[dict[str, object]] = []
    real_refresh = suggest_service.refresh_site_scenarios

    monkeypatch.setattr(suggest_service, "_load_site", lambda **kwargs: site)
    monkeypatch.setattr(
        suggest_service,
        "refresh_site_scenarios",
        lambda **kwargs: refresh_calls.append(kwargs) or SimpleNamespace(site_id=site.id),
    )

    response = suggest_service.suggest_scenarios_for_site(
        session=object(),
        site_id=site.id,
        requested_by="pytest",
    )
    assert response.site_id == site.id
    assert refresh_calls and refresh_calls[0]["site"] is site
    assert refresh_calls[0]["requested_by"] == "pytest"

    monkeypatch.setattr(
        suggest_service,
        "get_enabled_scenario_templates",
        lambda _session, template_keys=None: [
            _template(key=value) for value in (template_keys or ["resi_5_9_full"])
        ],
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
    exclusion_response = real_refresh(
        session=object(),
        site=SimpleNamespace(
            id=site.id,
            borough_id=site.borough_id,
            geom_hash=site.geom_hash,
            geom_confidence=GeomConfidence.HIGH,
            site_area_sqm=150.0,
            geometry_revisions=[],
            scenarios=[],
            planning_links=[],
            display_name="Camden fixture site",
        ),
        requested_by="pytest",
        template_keys=["resi_5_9_full", "resi_10_20_full"],
    )
    assert exclusion_response.site_id == site.id
    assert exclusion_response.items == []
    assert [item.template_key for item in exclusion_response.excluded_templates] == [
        "resi_5_9_full",
        "resi_10_20_full",
    ]
    assert all(
        reason.code == "NO_GEOMETRY_REVISION"
        for item in exclusion_response.excluded_templates
        for reason in item.reasons
    )


def test_suggest_helpers_cover_gatekeeping_and_auto_confirm_branches():
    assert suggest_service._citations_complete(
        [
            {
                "label": "Rule source",
                "source_family": "BOROUGH_REGISTER",
                "effective_date": "2026-04-01",
                "source_snapshot_id": str(UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")),
            }
        ]
    )
    assert not suggest_service._citations_complete([])
    assert not suggest_service._citations_complete(
        [{"label": "Rule source", "source_family": "BOROUGH_REGISTER"}]
    )

    residential = _strong_planning_application()
    non_residential = _strong_planning_application(
        decision_type="MIXED_USE",
        proposal_description="Commercial shell only.",
    )
    assert suggest_service._historical_status_is_strong(residential)
    assert not suggest_service._historical_status_is_strong(
        SimpleNamespace(**{**residential.__dict__, "status": "REFUSED"})
    )
    assert suggest_service._is_residential_history(residential)
    assert not suggest_service._is_residential_history(non_residential)

    site = _site()
    weak_app = _strong_planning_application(
        external_ref="CAM-2026-1001",
        route_normalized="OUTLINE",
        units_proposed=3,
        decision="REFUSED",
        status="REFUSED",
        decision_type="MIXED_USE",
        proposal_description="Commercial shell only.",
    )
    site.planning_links = [_link(weak_app, distance_m=5), _link(residential, distance_m=20)]
    support = suggest_service._nearest_historical_support(
        site=site,
        min_units=5,
        max_units=9,
        route_assumed="FULL",
    )
    assert support.application is residential
    assert support.strong is True

    blocked_allowed, blocked_reasons = suggest_service._auto_confirm_allowed(
        site=SimpleNamespace(geom_confidence=GeomConfidence.LOW),
        template_key="resi_5_9_full",
        preferred_route="DIAGONAL",
        support=SimpleNamespace(strong=False),
        extant_permission=SimpleNamespace(eligibility_status=EligibilityStatus.FAIL),
        missing_data_flags=["GEOMETRY_CONFIDENCE_BELOW_MEDIUM"],
        warning_codes=["RULEPACK_STALE"],
    )
    assert blocked_allowed is False
    assert {code for code, _ in blocked_reasons} == {
        "AUTO_CONFIRM_BLOCKED_GEOMETRY",
        "AUTO_CONFIRM_BLOCKED_EXTANT",
        "AUTO_CONFIRM_BLOCKED_MISSING_DATA",
        "AUTO_CONFIRM_BLOCKED_STALE_SOURCE",
        "AUTO_CONFIRM_BLOCKED_HISTORICAL_SUPPORT",
        "AUTO_CONFIRM_BLOCKED_ROUTE",
    }

    allowed, reasons = suggest_service._auto_confirm_allowed(
        site=SimpleNamespace(geom_confidence=GeomConfidence.HIGH),
        template_key="resi_5_9_full",
        preferred_route="FULL",
        support=SimpleNamespace(strong=True),
        extant_permission=SimpleNamespace(eligibility_status=EligibilityStatus.PASS),
        missing_data_flags=[],
        warning_codes=[],
    )
    assert allowed is True
    assert reasons == []
    assert suggest_service._dedupe(["A", "A", "", "B", "A", "B"]) == ["A", "B"]


def test_suggest_template_candidate_branches_cover_exclusions_and_scoring():
    template = _template()
    clean_rulepack = _rulepack(
        template_key=template.key,
        citations=[
            {
                "label": "Rule source",
                "source_family": "BOROUGH_REGISTER",
                "effective_date": "2026-04-01",
                "source_snapshot_id": str(UUID("aaaaaaaa-0000-0000-0000-000000000001")),
            }
        ],
    )
    stale_rulepack = _rulepack(
        template_key=template.key,
        citations=clean_rulepack.rule_json["citations"],
        freshness_status=SourceFreshnessStatus.STALE,
    )
    baseline_pack = SimpleNamespace(
        status=BaselinePackStatus.PILOT_READY,
        freshness_status=SourceFreshnessStatus.FRESH,
        rulepacks=[clean_rulepack],
    )
    stale_baseline_pack = SimpleNamespace(
        status=BaselinePackStatus.STALE,
        freshness_status=SourceFreshnessStatus.STALE,
        rulepacks=[stale_rulepack],
    )
    common_extant = _extant_permission()

    no_geometry_site = _site(area_sqm=0.0)
    result = suggest_service._evaluate_template_candidate(
        session=object(),
        site=no_geometry_site,
        baseline_pack=baseline_pack,
        template=template,
        extant_permission=common_extant,
        manual_seed=False,
    )
    assert result[1].reasons[0].code == "SITE_AREA_UNAVAILABLE"

    bad_citations_pack = SimpleNamespace(
        status=BaselinePackStatus.PILOT_READY,
        freshness_status=SourceFreshnessStatus.FRESH,
        rulepacks=[_rulepack(template_key=template.key, citations=[])],
    )
    result = suggest_service._evaluate_template_candidate(
        session=object(),
        site=_site(),
        baseline_pack=bad_citations_pack,
        template=template,
        extant_permission=common_extant,
        manual_seed=False,
    )
    assert result[1].reasons[0].code == "RULEPACK_CITATIONS_MISSING"

    missing_rulepack_result = suggest_service._evaluate_template_candidate(
        session=object(),
        site=_site(),
        baseline_pack=SimpleNamespace(
            status=BaselinePackStatus.PILOT_READY,
            freshness_status=SourceFreshnessStatus.FRESH,
            rulepacks=[],
        ),
        template=template,
        extant_permission=common_extant,
        manual_seed=False,
    )
    assert missing_rulepack_result[1].reasons[0].code == "RULEPACK_MISSING"

    active_extant_result = suggest_service._evaluate_template_candidate(
        session=object(),
        site=_site(),
        baseline_pack=baseline_pack,
        template=template,
        extant_permission=_extant_permission(
            status=ExtantPermissionStatus.ACTIVE_EXTANT_PERMISSION_FOUND
        ),
        manual_seed=False,
    )
    assert active_extant_result[1].reasons[0].code == "ACTIVE_EXTANT_PERMISSION_FOUND"

    out_of_range_result = suggest_service._evaluate_template_candidate(
        session=object(),
        site=_site(area_sqm=999.0),
        baseline_pack=baseline_pack,
        template=template,
        extant_permission=common_extant,
        manual_seed=False,
    )
    assert out_of_range_result[1].reasons[0].code == "SITE_AREA_OUTSIDE_TEMPLATE_RANGE"

    supportive_site = _site(area_sqm=999.0, geom_confidence=GeomConfidence.LOW)
    supportive_site.planning_links = []
    candidate_result = suggest_service._evaluate_template_candidate(
        session=object(),
        site=supportive_site,
        baseline_pack=stale_baseline_pack,
        template=template,
        extant_permission=_extant_permission(
            eligibility_status=EligibilityStatus.ABSTAIN,
            coverage_gaps=[SimpleNamespace(code="MANDATORY_SOURCE_PLANNING_REGISTER")],
            summary="coverage incomplete",
        ),
        manual_seed=True,
    )
    candidate, exclusion = candidate_result
    assert exclusion is None
    assert candidate is not None
    assert candidate.status == ScenarioStatus.ANALYST_REQUIRED
    assert candidate.manual_review_required is True
    assert "GEOMETRY_CONFIDENCE_BELOW_MEDIUM" in candidate.missing_data_flags
    assert "EXTANT_PERMISSION_ABSTAIN" in candidate.missing_data_flags
    assert "MANDATORY_SOURCE_PLANNING_REGISTER" in candidate.missing_data_flags
    assert "NEAREST_HISTORICAL_SUPPORT_NOT_STRONG" in candidate.missing_data_flags
    assert "RULEPACK_STALE" in candidate.warning_codes
    assert "BASELINE_PACK_STALE" in candidate.warning_codes
    assert "SOURCE_COVERAGE_GAP" in candidate.warning_codes

    strong_site = _site(area_sqm=250.0, geom_confidence=GeomConfidence.HIGH)
    strong_site.planning_links = [_link(_strong_planning_application())]
    strong_candidate, strong_exclusion = suggest_service._evaluate_template_candidate(
        session=object(),
        site=strong_site,
        baseline_pack=baseline_pack,
        template=template,
        extant_permission=_extant_permission(),
        manual_seed=False,
    )
    assert strong_exclusion is None
    assert strong_candidate is not None
    assert strong_candidate.status == ScenarioStatus.AUTO_CONFIRMED
    assert strong_candidate.manual_review_required is False
    assert any(
        reason.code == "STRONG_HISTORICAL_SUPPORT" for reason in strong_candidate.reason_codes
    )


def test_suggest_refresh_persists_candidate_and_assigns_headline(monkeypatch):
    site = _site()
    site.geometry_revisions = [_revision(geom_hash=site.geom_hash)]
    template = _template()
    candidate = suggest_service.ScenarioCandidate(
        template_key=template.key,
        template_version=template.version,
        proposal_form=ProposalForm.REDEVELOPMENT,
        units_assumed=6,
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
        reason_codes=[
            ScenarioReasonRead(code="AREA_CAPACITY_HEURISTIC", message="fixture"),
        ],
        missing_data_flags=[],
        warning_codes=[],
        support=suggest_service.CandidateSupport(
            application=_strong_planning_application(),
            strong=True,
        ),
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
        lambda **kwargs: {
            "id": str(kwargs["scenario"].id),
            "site_id": str(kwargs["scenario"].site_id),
            "template_key": kwargs["scenario"].template_key,
            "template_version": kwargs["scenario"].template_version,
            "proposal_form": kwargs["scenario"].proposal_form,
            "units_assumed": kwargs["scenario"].units_assumed,
            "route_assumed": kwargs["scenario"].route_assumed,
            "height_band_assumed": kwargs["scenario"].height_band_assumed,
            "net_developable_area_pct": kwargs["scenario"].net_developable_area_pct,
            "red_line_geom_hash": kwargs["scenario"].red_line_geom_hash,
            "scenario_source": kwargs["scenario"].scenario_source,
            "status": kwargs["scenario"].status,
            "supersedes_id": kwargs["scenario"].supersedes_id,
            "is_current": kwargs["scenario"].is_current,
            "is_headline": kwargs["scenario"].is_headline,
            "heuristic_rank": kwargs["scenario"].heuristic_rank,
            "manual_review_required": kwargs["scenario"].manual_review_required,
            "stale_reason": kwargs["scenario"].stale_reason,
            "housing_mix_assumed_json": kwargs["scenario"].housing_mix_assumed_json,
            "parking_assumption": kwargs["scenario"].parking_assumption,
            "affordable_housing_assumption": kwargs["scenario"].affordable_housing_assumption,
            "access_assumption": kwargs["scenario"].access_assumption,
            "reason_codes": [],
            "missing_data_flags": [],
            "warning_codes": [],
        },
    )

    response = suggest_service.refresh_site_scenarios(
        session=session,
        site=site,
        requested_by="pytest",
    )

    assert response.site_id == site.id
    assert response.headline_scenario_id is not None
    assert len(response.items) == 1
    assert response.items[0].is_headline is True
    assert any(isinstance(item, SiteScenario) for item in session.added)
    persisted = next(item for item in session.added if isinstance(item, SiteScenario))
    assert persisted.status == ScenarioStatus.AUTO_CONFIRMED
    assert persisted.scenario_source == ScenarioSource.AUTO
    assert persisted.red_line_geom_hash == site.geom_hash
    assert session.flush_count >= 1


def test_normalize_load_confirm_and_supersede_branches(monkeypatch):
    missing_session = _Session(execute_results=[_Result(scalar=None)])
    with pytest.raises(normalize_service.ScenarioNormalizeError):
        normalize_service._load_scenario(
            session=missing_session,
            scenario_id=UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"),
        )

    site = _site()
    current_revision = _revision(geom_hash=site.geom_hash)
    older_revision = _revision(
        geom_hash="older-hash",
        revision_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
    )
    site.geometry_revisions = [older_revision, current_revision]

    scenario = _scenario_stub(
        scenario_id="11111111-1111-1111-1111-111111111111",
        site=site,
        status=ScenarioStatus.AUTO_CONFIRMED,
        scenario_source=ScenarioSource.AUTO,
        is_current=True,
        is_headline=True,
    )
    other = _scenario_stub(
        scenario_id="22222222-2222-2222-2222-222222222222",
        site=site,
        status=ScenarioStatus.ANALYST_CONFIRMED,
        scenario_source=ScenarioSource.ANALYST,
        is_current=True,
        is_headline=False,
        heuristic_rank=2,
    )
    site.scenarios = [scenario, other]

    refresh_calls = []
    monkeypatch.setattr(
        normalize_service,
        "refresh_scenario_evidence",
        lambda **kwargs: refresh_calls.append(kwargs),
    )

    reject_site = _site()
    reject_site.geometry_revisions = [current_revision]
    reject_scenario = _scenario_stub(
        scenario_id="11111111-1111-1111-1111-111111111111",
        site=reject_site,
        status=ScenarioStatus.AUTO_CONFIRMED,
        scenario_source=ScenarioSource.AUTO,
        is_current=True,
        is_headline=True,
    )
    reject_other = _scenario_stub(
        scenario_id="22222222-2222-2222-2222-222222222222",
        site=reject_site,
        status=ScenarioStatus.ANALYST_CONFIRMED,
        scenario_source=ScenarioSource.ANALYST,
        is_current=True,
        is_headline=False,
        heuristic_rank=2,
    )
    reject_site.scenarios = [reject_scenario, reject_other]
    reject_session = _Session()
    monkeypatch.setattr(
        normalize_service,
        "_load_scenario",
        lambda **kwargs: reject_scenario,
    )
    rejected = normalize_service.confirm_or_update_scenario(
        session=reject_session,
        scenario_id=reject_scenario.id,
        request=ScenarioConfirmRequest(
            requested_by="pytest",
            action="REJECT",
            review_notes="not suitable",
        ),
    )
    assert rejected.status == ScenarioStatus.REJECTED
    assert rejected.is_current is False
    assert rejected.is_headline is False
    assert any(isinstance(item, ScenarioReview) for item in reject_session.added)
    assert any(isinstance(item, AuditEvent) for item in reject_session.added)
    assert not refresh_calls

    pass_site = _site()
    pass_site.geometry_revisions = [current_revision]
    pass_scenario = _scenario_stub(
        scenario_id="33333333-3333-3333-3333-333333333333",
        site=pass_site,
        status=ScenarioStatus.AUTO_CONFIRMED,
        scenario_source=ScenarioSource.AUTO,
        is_current=True,
        is_headline=True,
    )
    pass_other = _scenario_stub(
        scenario_id="44444444-4444-4444-4444-444444444444",
        site=pass_site,
        status=ScenarioStatus.ANALYST_CONFIRMED,
        scenario_source=ScenarioSource.ANALYST,
        is_current=True,
        is_headline=False,
        heuristic_rank=2,
    )
    pass_site.scenarios = [pass_scenario, pass_other]
    pass_session = _Session()
    monkeypatch.setattr(
        normalize_service,
        "_load_scenario",
        lambda **kwargs: pass_scenario,
    )
    monkeypatch.setattr(
        normalize_service,
        "evaluate_site_extant_permission",
        lambda **kwargs: _extant_permission(),
    )
    updated = normalize_service.confirm_or_update_scenario(
        session=pass_session,
        scenario_id=pass_scenario.id,
        request=ScenarioConfirmRequest(requested_by="pytest"),
    )
    assert updated is pass_scenario
    assert updated.status == ScenarioStatus.ANALYST_CONFIRMED
    assert updated.scenario_source == ScenarioSource.ANALYST
    assert updated.manual_review_required is False
    assert updated.stale_reason is None
    assert refresh_calls
    assert pass_session.flush_count == 1

    supersede_site = _site()
    supersede_site.geometry_revisions = [current_revision]
    supersede_scenario = _scenario_stub(
        scenario_id="55555555-5555-5555-5555-555555555555",
        site=supersede_site,
        status=ScenarioStatus.AUTO_CONFIRMED,
        scenario_source=ScenarioSource.AUTO,
        is_current=True,
        is_headline=True,
    )
    supersede_other = _scenario_stub(
        scenario_id="66666666-6666-6666-6666-666666666666",
        site=supersede_site,
        status=ScenarioStatus.ANALYST_CONFIRMED,
        scenario_source=ScenarioSource.ANALYST,
        is_current=True,
        is_headline=False,
        heuristic_rank=2,
    )
    supersede_site.scenarios = [supersede_scenario, supersede_other]
    supersede_session = _Session()
    monkeypatch.setattr(
        normalize_service,
        "_load_scenario",
        lambda **kwargs: supersede_scenario,
    )
    monkeypatch.setattr(
        normalize_service,
        "evaluate_site_extant_permission",
        lambda **kwargs: _extant_permission(
            status=ExtantPermissionStatus.UNRESOLVED_MISSING_MANDATORY_SOURCE,
            eligibility_status=EligibilityStatus.FAIL,
            summary="missing mandatory source",
        ),
    )
    superseded = normalize_service.confirm_or_update_scenario(
        session=supersede_session,
        scenario_id=supersede_scenario.id,
        request=ScenarioConfirmRequest(requested_by="pytest", units_assumed=7),
    )
    assert superseded is not supersede_scenario
    assert superseded.supersedes_id == supersede_scenario.id
    assert superseded.status == ScenarioStatus.OUT_OF_SCOPE
    assert superseded.manual_review_required is True
    assert superseded.scenario_source == ScenarioSource.ANALYST
    assert superseded.units_assumed == 7
    assert superseded.is_current is True


def test_normalize_headline_and_stale_helpers_cover_recompute_and_refresh_paths():
    site = _site()
    confirmed = _scenario_stub(
        scenario_id="44444444-4444-4444-4444-444444444444",
        site=site,
        status=ScenarioStatus.ANALYST_CONFIRMED,
        scenario_source=ScenarioSource.ANALYST,
        is_current=True,
        is_headline=False,
        heuristic_rank=5,
    )
    auto = _scenario_stub(
        scenario_id="55555555-5555-5555-5555-555555555555",
        site=site,
        status=ScenarioStatus.AUTO_CONFIRMED,
        scenario_source=ScenarioSource.AUTO,
        is_current=True,
        is_headline=False,
        heuristic_rank=1,
    )
    suggested = _scenario_stub(
        scenario_id="66666666-6666-6666-6666-666666666666",
        site=site,
        status=ScenarioStatus.SUGGESTED,
        scenario_source=ScenarioSource.AUTO,
        is_current=True,
        is_headline=False,
        heuristic_rank=0,
    )
    site.scenarios = [suggested, auto, confirmed]
    normalize_service._recompute_headline(site)
    assert confirmed.is_headline is True
    assert auto.is_headline is False

    site.scenarios = [auto, suggested]
    for row in site.scenarios:
        row.is_headline = False
    normalize_service._recompute_headline(site)
    assert auto.is_headline is True

    site.scenarios = [suggested, auto]
    auto.heuristic_rank = 9
    suggested.heuristic_rank = 2
    for row in site.scenarios:
        row.status = ScenarioStatus.SUGGESTED
        row.is_headline = False
    normalize_service._recompute_headline(site)
    assert suggested.is_headline is True

    stale_site = _site(geom_hash="new-hash")
    stale_match = _scenario_stub(
        scenario_id="77777777-7777-7777-7777-777777777777",
        site=stale_site,
        status=ScenarioStatus.AUTO_CONFIRMED,
        scenario_source=ScenarioSource.AUTO,
        is_current=True,
        is_headline=True,
        red_line_geom_hash="old-hash",
    )
    stale_rejected = _scenario_stub(
        scenario_id="88888888-8888-8888-8888-888888888888",
        site=stale_site,
        status=ScenarioStatus.REJECTED,
        scenario_source=ScenarioSource.AUTO,
        is_current=True,
        is_headline=False,
        red_line_geom_hash="old-hash",
    )
    stale_current = _scenario_stub(
        scenario_id="99999999-9999-9999-9999-999999999999",
        site=stale_site,
        status=ScenarioStatus.AUTO_CONFIRMED,
        scenario_source=ScenarioSource.AUTO,
        is_current=False,
        is_headline=False,
        red_line_geom_hash="old-hash",
    )
    stale_same = _scenario_stub(
        scenario_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1",
        site=stale_site,
        status=ScenarioStatus.ANALYST_CONFIRMED,
        scenario_source=ScenarioSource.ANALYST,
        is_current=True,
        is_headline=False,
        red_line_geom_hash=stale_site.geom_hash,
    )
    stale_site.scenarios = [stale_match, stale_rejected, stale_current, stale_same]
    stale_session = _Session()
    changed = normalize_service.mark_site_scenarios_stale_for_geometry_change(
        session=stale_session,
        site=stale_site,
        requested_by="pytest",
    )
    assert changed == 1
    assert stale_match.status == ScenarioStatus.ANALYST_REQUIRED
    assert stale_match.manual_review_required is True
    assert "SCENARIO_STALE_GEOMETRY" in stale_match.rationale_json["warning_codes"]
    assert any(isinstance(item, ScenarioReview) for item in stale_session.added)
    assert any(isinstance(item, AuditEvent) for item in stale_session.added)
    assert stale_rejected.status == ScenarioStatus.REJECTED
    assert stale_current.is_current is False
    assert stale_same.manual_review_required is False

    rulepack_site = _site()
    rulepack_current = _scenario_stub(
        scenario_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb1",
        site=rulepack_site,
        status=ScenarioStatus.AUTO_CONFIRMED,
        scenario_source=ScenarioSource.AUTO,
        is_current=True,
        is_headline=True,
        red_line_geom_hash=rulepack_site.geom_hash,
    )
    rulepack_rejected = _scenario_stub(
        scenario_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbb2",
        site=rulepack_site,
        status=ScenarioStatus.REJECTED,
        scenario_source=ScenarioSource.AUTO,
        is_current=True,
        is_headline=False,
        red_line_geom_hash=rulepack_site.geom_hash,
    )
    rulepack_site.scenarios = [rulepack_current, rulepack_rejected]
    rulepack_session = _Session()
    changed = normalize_service.refresh_site_scenarios_after_rulepack_change(
        session=rulepack_session,
        site=rulepack_site,
        requested_by="pytest",
    )
    assert changed == 1
    assert rulepack_current.status == ScenarioStatus.ANALYST_REQUIRED
    assert rulepack_current.manual_review_required is True
    assert "RULEPACK_REFRESH_REQUIRED" in rulepack_current.rationale_json["warning_codes"]
    assert any(isinstance(item, ScenarioReview) for item in rulepack_session.added)
    assert any(isinstance(item, AuditEvent) for item in rulepack_session.added)
    assert rulepack_rejected.status == ScenarioStatus.REJECTED
