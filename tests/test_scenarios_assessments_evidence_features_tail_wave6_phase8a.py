from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from uuid import UUID

import pytest
from landintel.assessments import service as service_mod
from landintel.assessments.comparables import build_comparable_case_set
from landintel.assessments.service import (
    create_or_refresh_assessment_run,
    verify_assessment_replay,
)
from landintel.domain.enums import (
    BaselinePackStatus,
    ComparableOutcome,
    EligibilityStatus,
    EstimateQuality,
    EstimateStatus,
    ExtantPermissionStatus,
    GeomConfidence,
    GeomSourceType,
    GoldSetReviewStatus,
    HistoricalLabelClass,
    PriceBasisType,
    ProposalForm,
    ReviewStatus,
    ScenarioSource,
    ScenarioStatus,
    SourceClass,
    SourceFreshnessStatus,
)
from landintel.domain.models import (
    AssessmentRun,
    HistoricalCaseLabel,
    ModelRelease,
    PlanningApplication,
    PlanningConstraintFeature,
    PolicyArea,
    SiteGeometryRevision,
    SiteScenario,
)
from landintel.domain.schemas import (
    EvidencePackRead,
    ExtantPermissionRead,
    ScenarioConfirmRequest,
)
from landintel.evidence import assemble as assemble_mod
from landintel.evidence.assemble import assemble_scenario_evidence
from landintel.features import build as build_mod
from landintel.features.build import (
    FEATURE_VERSION,
    build_designation_profile_for_site_context,
    build_feature_snapshot,
)
from landintel.scenarios import normalize as normalize_mod
from landintel.scenarios import suggest as suggest_mod
from landintel.scenarios.normalize import (
    ScenarioNormalizeError,
    confirm_or_update_scenario,
    mark_site_scenarios_stale_for_geometry_change,
    refresh_site_scenarios_after_rulepack_change,
)
from landintel.scenarios.suggest import (
    CandidateSupport,
    ScenarioCandidate,
    _citations_complete,
    _evaluate_template_candidate,
    _mark_stale_current_auto_scenarios,
    _nearest_historical_support,  # noqa: F401
    _persist_candidate,
    _rulepack_for_template,
    refresh_site_scenarios,
)


def _uuid(seed: int) -> UUID:
    return UUID(f"00000000-0000-0000-0000-{seed:012d}")


class _FakeResult:
    def __init__(self, rows: list[object]):
        self._rows = list(rows)

    def scalars(self) -> _FakeResult:
        return self

    def all(self) -> list[object]:
        return list(self._rows)

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def scalar_one(self):
        if len(self._rows) != 1:
            raise AssertionError(f"Expected exactly one row, got {len(self._rows)}")
        return self._rows[0]


class _FakeSession:
    def __init__(
        self,
        *,
        rows_by_entity: dict[object, list[object]] | None = None,
        get_map: dict[tuple[object, object], object] | None = None,
    ) -> None:
        self.rows_by_entity = rows_by_entity or {}
        self.get_map = get_map or {}
        self.added: list[object] = []
        self.flush_count = 0
        self.executed: list[object] = []

    def execute(self, stmt):
        self.executed.append(stmt)
        entity = None
        descriptions = getattr(stmt, "column_descriptions", None) or []
        if descriptions:
            entity = descriptions[0].get("entity")
        return _FakeResult(self.rows_by_entity.get(entity, []))

    def add(self, obj) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        self.flush_count += 1

    def get(self, model, key):
        return self.get_map.get((model, key))


def _empty_evidence_pack() -> EvidencePackRead:
    return EvidencePackRead.model_construct(for_=[], against=[], unknown=[])


def _make_revision(*, revision_id: int, geom_hash: str) -> SiteGeometryRevision:
    return SimpleNamespace(id=_uuid(revision_id), geom_hash=geom_hash)


def _make_site(
    *,
    site_id: int,
    geom_hash: str,
    geometry_revisions: list[SiteGeometryRevision] | None = None,
    planning_links: list[object] | None = None,
    policy_facts: list[object] | None = None,
    constraint_facts: list[object] | None = None,
    scenarios: list[object] | None = None,
    borough_id: str = "camden",
    site_area_sqm: float = 120.0,
    geom_27700: str = "POLYGON ((0 0, 10 0, 10 10, 0 10, 0 0))",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=_uuid(site_id),
        display_name="Fixture site",
        borough_id=borough_id,
        geom_hash=geom_hash,
        geom_27700=geom_27700,
        geom_source_type=GeomSourceType.ANALYST_DRAWN,
        geom_confidence=GeomConfidence.HIGH,
        site_area_sqm=site_area_sqm,
        current_price_gbp=None,
        current_price_basis_type=PriceBasisType.UNKNOWN,
        manual_review_required=False,
        geometry_revisions=list(geometry_revisions or []),
        planning_links=list(planning_links or []),
        policy_facts=list(policy_facts or []),
        constraint_facts=list(constraint_facts or []),
        scenarios=list(scenarios or []),
    )


def _make_scenario(
    *,
    scenario_id: int,
    site: SimpleNamespace,
    status: ScenarioStatus = ScenarioStatus.AUTO_CONFIRMED,
    source: ScenarioSource = ScenarioSource.AUTO,
    geom_hash: str | None = None,
    current: bool = True,
    headline: bool = False,
    template_key: str = "resi_5_9_full",
    template_version: str = "v1",
    proposal_form: ProposalForm = ProposalForm.REDEVELOPMENT,
    units_assumed: int = 6,
    route_assumed: str = "FULL",
    height_band_assumed: str = "MID_RISE",
    net_developable_area_pct: float = 0.7,
    manual_review_required: bool = False,
    stale_reason: str | None = None,
    rationale_json: dict[str, object] | None = None,
    evidence_json: dict[str, object] | None = None,
    heuristic_rank: int | None = 10,
    assessment_runs: list[object] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=_uuid(scenario_id),
        site=site,
        site_id=site.id,
        template_key=template_key,
        template_version=template_version,
        proposal_form=proposal_form,
        units_assumed=units_assumed,
        route_assumed=route_assumed,
        height_band_assumed=height_band_assumed,
        net_developable_area_pct=net_developable_area_pct,
        red_line_geom_hash=geom_hash or site.geom_hash,
        scenario_source=source,
        status=status,
        supersedes_id=None,
        is_current=current,
        is_headline=headline,
        heuristic_rank=heuristic_rank,
        manual_review_required=manual_review_required,
        stale_reason=stale_reason,
        housing_mix_assumed_json={},
        parking_assumption=None,
        affordable_housing_assumption=None,
        access_assumption=None,
        reason_codes=[],
        missing_data_flags=[],
        warning_codes=[],
        rationale_json=dict(rationale_json or {}),
        evidence_json=dict(evidence_json or {}),
        assessment_runs=list(assessment_runs or []),
    )


def _make_application(
    *,
    application_id: int,
    external_ref: str,
    borough_id: str,
    proposal_description: str,
    route_normalized: str,
    units_proposed: int | None,
    status: str,
    decision: str,
    decision_type: str = "RESIDENTIAL",
    source_system: str = "BOROUGH_REGISTER",
    valid_date: date = date(2026, 1, 1),
    decision_date: date = date(2026, 2, 1),
    source_snapshot_id: str | None = None,
    geom_wkt: str = "POINT (0 0)",
    documents: list[object] | None = None,
    raw_record_json: dict[str, object] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=_uuid(application_id),
        external_ref=external_ref,
        borough_id=borough_id,
        proposal_description=proposal_description,
        route_normalized=route_normalized,
        units_proposed=units_proposed,
        status=status,
        decision=decision,
        decision_type=decision_type,
        source_system=source_system,
        source_url=f"https://example.test/{external_ref.lower()}",
        source_snapshot_id=source_snapshot_id or f"snap-{application_id}",
        valid_date=valid_date,
        decision_date=decision_date,
        site_geom_27700=geom_wkt,
        site_point_27700=None,
        documents=list(documents or []),
        raw_record_json=dict(raw_record_json or {}),
    )


def _make_label(
    *,
    label_id: int,
    application,
    borough_id: str,
    template_key: str,
    label_class: HistoricalLabelClass,
    proposal_form: ProposalForm,
    units_proposed: int | None,
    site_area_sqm: float,
    archetype_key: str,
    designation_profile_json: dict[str, object],
    source_snapshot_ids_json: list[str],
    raw_asset_ids_json: list[str],
    valid_date: date,
    decision_date: date,
    review_status: GoldSetReviewStatus = GoldSetReviewStatus.PENDING,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=_uuid(label_id),
        label_version=FEATURE_VERSION,
        label_class=label_class,
        planning_application_id=application.id,
        planning_application=application,
        borough_id=borough_id,
        template_key=template_key,
        proposal_form=proposal_form,
        units_proposed=units_proposed,
        site_area_sqm=site_area_sqm,
        archetype_key=archetype_key,
        designation_profile_json=dict(designation_profile_json),
        source_snapshot_ids_json=list(source_snapshot_ids_json),
        raw_asset_ids_json=list(raw_asset_ids_json),
        valid_date=valid_date,
        first_substantive_decision_date=decision_date,
        review_status=review_status,
    )


def _make_policy_fact(
    *,
    policy_family: str,
    effective_from: str | None,
    effective_to: str | None,
    source_snapshot_id: str,
) -> SimpleNamespace:
    return SimpleNamespace(
        source_snapshot_id=source_snapshot_id,
        policy_area=SimpleNamespace(
            policy_family=policy_family,
            source_snapshot_id=source_snapshot_id,
            raw_record_json={},
            name=policy_family.title(),
            policy_code=f"{policy_family}-CODE",
            source_url=None,
            source_class=SourceClass.AUTHORITATIVE,
        ),
        snapshot={
            "policy_family": policy_family,
            "legal_effective_from": effective_from,
            "legal_effective_to": effective_to,
            "source_snapshot_id": source_snapshot_id,
        },
    )


def _make_constraint_fact(
    *,
    feature_family: str,
    feature_subtype: str,
    effective_from: str | None,
    effective_to: str | None,
    source_snapshot_id: str,
) -> SimpleNamespace:
    return SimpleNamespace(
        source_snapshot_id=source_snapshot_id,
        constraint_feature=SimpleNamespace(
            feature_family=feature_family,
            feature_subtype=feature_subtype,
            source_snapshot_id=source_snapshot_id,
            raw_record_json={},
            name=f"{feature_family}:{feature_subtype}",
            legal_status="ACTIVE",
            source_url=None,
            source_class=SourceClass.AUTHORITATIVE,
        ),
        snapshot={
            "feature_family": feature_family,
            "feature_subtype": feature_subtype,
            "effective_from": effective_from,
            "effective_to": effective_to,
            "source_snapshot_id": source_snapshot_id,
        },
    )


def _make_template(
    *,
    key: str,
    version: str = "v1",
    config_json: dict[str, object] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(key=key, version=version, config_json=dict(config_json or {}))


def _make_rulepack(
    *,
    template_key: str,
    freshness_status: SourceFreshnessStatus = SourceFreshnessStatus.FRESH,
    rule_json: dict[str, object] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        template_key=template_key,
        freshness_status=freshness_status,
        rule_json=dict(rule_json or {}),
    )


def _make_basal_pack(
    *,
    status: BaselinePackStatus = BaselinePackStatus.SIGNED_OFF,
    rulepacks: list[object] | None = None,
    borough_id: str = "camden",
    source_snapshot_id: str = "baseline-snap",
) -> SimpleNamespace:
    return SimpleNamespace(
        status=status,
        rulepacks=list(rulepacks or []),
        borough_id=borough_id,
        source_snapshot_id=source_snapshot_id,
        freshness_status=SourceFreshnessStatus.FRESH,
    )


def _make_support_application(
    *,
    external_ref: str,
    route_normalized: str,
    units_proposed: int,
    source_snapshot_id: str,
    borough_id: str = "camden",
    decision_type: str = "RESIDENTIAL",
) -> SimpleNamespace:
    seed = abs(hash(external_ref)) % 10_000
    doc = SimpleNamespace(asset_id=_uuid(seed + 1))
    return _make_application(
        application_id=seed + 500,
        external_ref=external_ref,
        borough_id=borough_id,
        proposal_description="Residential flats",
        route_normalized=route_normalized,
        units_proposed=units_proposed,
        status="APPROVED",
        decision="APPROVED",
        decision_type=decision_type,
        source_snapshot_id=str(_uuid(seed + 2)),
        documents=[doc],
        raw_record_json={"active_extant": False},
    )


class _StopAfterAssessmentResult(Exception):
    pass


class _StopAfterReplayPayload(Exception):
    pass


def test_normalize_paths_cover_missing_geometry_and_stale_refreshes(monkeypatch):
    site = _make_site(site_id=1, geom_hash="site-hash", geometry_revisions=[])
    scenario = _make_scenario(
        scenario_id=11,
        site=site,
        status=ScenarioStatus.AUTO_CONFIRMED,
        source=ScenarioSource.AUTO,
        geom_hash="scenario-hash",
        current=True,
        headline=True,
    )
    scenario.site = site
    site.scenarios = [scenario]
    monkeypatch.setattr(normalize_mod, "_load_scenario", lambda **kwargs: scenario)

    with pytest.raises(ScenarioNormalizeError, match="No current site geometry revision"):
        confirm_or_update_scenario(
            session=_FakeSession(),
            scenario_id=scenario.id,
            request=ScenarioConfirmRequest(action="confirm", requested_by="pytest"),
        )

    current_site = _make_site(
        site_id=2,
        geom_hash="site-new-hash",
        geometry_revisions=[_make_revision(revision_id=21, geom_hash="site-new-hash")],
    )
    stale_auto = _make_scenario(
        scenario_id=22,
        site=current_site,
        status=ScenarioStatus.AUTO_CONFIRMED,
        source=ScenarioSource.AUTO,
        geom_hash="site-old-hash",
        current=True,
        headline=True,
    )
    stale_analyst = _make_scenario(
        scenario_id=23,
        site=current_site,
        status=ScenarioStatus.ANALYST_CONFIRMED,
        source=ScenarioSource.ANALYST,
        geom_hash="site-older-hash",
        current=True,
        headline=False,
    )
    same_hash = _make_scenario(
        scenario_id=24,
        site=current_site,
        status=ScenarioStatus.AUTO_CONFIRMED,
        source=ScenarioSource.AUTO,
        geom_hash="site-new-hash",
        current=True,
        headline=False,
    )
    rejected = _make_scenario(
        scenario_id=25,
        site=current_site,
        status=ScenarioStatus.REJECTED,
        source=ScenarioSource.ANALYST,
        geom_hash="site-old-hash",
        current=True,
        headline=False,
    )
    analyst_required = _make_scenario(
        scenario_id=26,
        site=current_site,
        status=ScenarioStatus.ANALYST_REQUIRED,
        source=ScenarioSource.ANALYST,
        geom_hash="site-analyst-hash",
        current=True,
        headline=False,
    )
    current_site.scenarios = [stale_auto, stale_analyst, same_hash, analyst_required, rejected]
    fake_session = _FakeSession()
    monkeypatch.setattr(normalize_mod, "_add_review", lambda **kwargs: None)
    monkeypatch.setattr(normalize_mod, "_record_scenario_audit", lambda **kwargs: None)
    monkeypatch.setattr(normalize_mod, "_recompute_headline", lambda *args, **kwargs: None)

    changed = mark_site_scenarios_stale_for_geometry_change(
        session=fake_session,
        site=current_site,
        requested_by="pytest",
    )
    assert changed == 3
    assert stale_auto.status == ScenarioStatus.ANALYST_REQUIRED
    assert stale_analyst.status == ScenarioStatus.ANALYST_REQUIRED
    assert same_hash.status == ScenarioStatus.AUTO_CONFIRMED
    assert analyst_required.status == ScenarioStatus.ANALYST_REQUIRED
    assert rejected.status == ScenarioStatus.REJECTED
    assert stale_auto.rationale_json["warning_codes"] == ["SCENARIO_STALE_GEOMETRY"]
    assert stale_analyst.rationale_json["warning_codes"] == ["SCENARIO_STALE_GEOMETRY"]
    assert analyst_required.rationale_json["warning_codes"] == ["SCENARIO_STALE_GEOMETRY"]

    rulepack_site = _make_site(
        site_id=3,
        geom_hash="rulepack-hash",
        geometry_revisions=[_make_revision(revision_id=31, geom_hash="rulepack-hash")],
    )
    rulepack_auto = _make_scenario(
        scenario_id=32,
        site=rulepack_site,
        status=ScenarioStatus.AUTO_CONFIRMED,
        source=ScenarioSource.AUTO,
        geom_hash="old-rulepack-hash",
        current=True,
        headline=True,
    )
    rulepack_analyst = _make_scenario(
        scenario_id=33,
        site=rulepack_site,
        status=ScenarioStatus.ANALYST_CONFIRMED,
        source=ScenarioSource.ANALYST,
        geom_hash="older-rulepack-hash",
        current=True,
        headline=False,
    )
    rulepack_rejected = _make_scenario(
        scenario_id=34,
        site=rulepack_site,
        status=ScenarioStatus.REJECTED,
        source=ScenarioSource.ANALYST,
        geom_hash="older-rulepack-hash",
        current=True,
        headline=False,
    )
    rulepack_site.scenarios = [rulepack_auto, rulepack_analyst, rulepack_rejected]
    changed = refresh_site_scenarios_after_rulepack_change(
        session=fake_session,
        site=rulepack_site,
        requested_by="pytest",
    )
    assert changed == 2
    assert rulepack_auto.status == ScenarioStatus.ANALYST_REQUIRED
    assert rulepack_analyst.status == ScenarioStatus.ANALYST_CONFIRMED
    assert rulepack_rejected.status == ScenarioStatus.REJECTED
    assert rulepack_auto.rationale_json["warning_codes"] == ["RULEPACK_REFRESH_REQUIRED"]


def test_suggest_refresh_and_candidate_paths_cover_skips_route_and_missing_baseline(monkeypatch):
    revision = _make_revision(revision_id=41, geom_hash="site-hash")
    site = _make_site(site_id=4, geom_hash="site-hash", geometry_revisions=[revision])
    templates = [_make_template(key="resi_5_9_full"), _make_template(key="resi_10_20_outline")]
    monkeypatch.setattr(suggest_mod, "_load_site", lambda **kwargs: site)
    monkeypatch.setattr(
        suggest_mod,
        "get_enabled_scenario_templates",
        lambda *args, **kwargs: templates,
    )
    monkeypatch.setattr(
        suggest_mod,
        "evaluate_site_extant_permission",
        lambda **kwargs: ExtantPermissionRead.model_construct(
            status=ExtantPermissionStatus.NO_ACTIVE_PERMISSION_FOUND,
            eligibility_status=EligibilityStatus.PASS,
            manual_review_required=False,
            summary="PASS",
            reasons=[],
            coverage_gaps=[],
            matched_records=[],
        ),
    )
    monkeypatch.setattr(
        suggest_mod,
        "assemble_site_evidence",
        lambda **kwargs: _empty_evidence_pack(),
    )
    monkeypatch.setattr(suggest_mod, "_evaluate_template_candidate", lambda **kwargs: (None, None))
    response = refresh_site_scenarios(
        session=_FakeSession(),
        site=site,
        requested_by="pytest",
    )
    assert response.items == []
    assert response.excluded_templates == []

    support_app = _make_support_application(
        external_ref="CAM-1",
        route_normalized="MIXED",
        units_proposed=6,
        source_snapshot_id="support-snap",
    )
    support_link = SimpleNamespace(
        planning_application_id=support_app.id,
        planning_application=support_app,
        source_snapshot_id="link-snap",
        distance_m=12.0,
    )
    rulepack = _make_rulepack(
        template_key="resi_5_9_full",
        rule_json={
            "citations": [
                {
                    "label": "Rule source",
                    "source_family": "BOROUGH_REGISTER",
                    "effective_date": "2026-04-01",
                    "source_snapshot_id": "citation-snap",
                }
            ],
            "scenario_rules": {
                "preferred_route": "MIXED",
                "allowed_routes": ["OUTLINE"],
                "units_range": {"min": 1, "max": 10},
                "site_area_sqm_range": {"min": 50, "max": 200},
                "default_net_developable_area_pct": 0.7,
                "default_height_band": "MID_RISE",
            },
        },
    )
    template = _make_template(
        key="resi_5_9_full",
        config_json={
            "default_route": "FULL",
            "target_sqm_per_home": 100.0,
            "default_proposal_form": "REDEVELOPMENT",
            "default_housing_mix": {"1br": 0.25},
            "default_net_developable_area_pct": 0.7,
        },
    )
    candidate, exclusion = _evaluate_template_candidate(
        session=_FakeSession(),
        site=_make_site(
            site_id=5,
            geom_hash="site-hash",
            geometry_revisions=[_make_revision(revision_id=51, geom_hash="site-hash")],
            planning_links=[support_link],
            site_area_sqm=120.0,
        ),
        baseline_pack=_make_basal_pack(
            status=BaselinePackStatus.SIGNED_OFF,
            rulepacks=[rulepack],
        ),
        template=template,
        extant_permission=ExtantPermissionRead.model_construct(
            status=ExtantPermissionStatus.NO_ACTIVE_PERMISSION_FOUND,
            eligibility_status=EligibilityStatus.PASS,
            manual_review_required=False,
            summary="PASS",
            reasons=[],
            coverage_gaps=[],
            matched_records=[],
        ),
        manual_seed=False,
    )
    assert exclusion is None
    assert candidate is not None
    assert candidate.route_assumed == "MIXED"
    assert candidate.status == ScenarioStatus.ANALYST_REQUIRED
    assert candidate.manual_review_required is True
    assert "ANALYST_CONFIRMATION_REQUIRED" in candidate.warning_codes
    assert any(reason.code == "AUTO_CONFIRM_BLOCKED_ROUTE" for reason in candidate.reason_codes)
    assert any(reason.code == "STRONG_HISTORICAL_SUPPORT" for reason in candidate.reason_codes)
    assert _citations_complete(rulepack.rule_json["citations"]) is True
    assert not _citations_complete(
        [
            {
                "label": "Rule source",
                "source_family": "BOROUGH_REGISTER",
                "effective_date": "2026-04-01",
            }
        ]
    )

    forced_rulepack = _make_rulepack(
        template_key="resi_5_9_full",
        rule_json={
            "citations": rulepack.rule_json["citations"],
            "scenario_rules": {
                "preferred_route": "FULL",
                "allowed_routes": ["FULL"],
                "units_range": {"min": 1, "max": 10},
                "site_area_sqm_range": {"min": 50, "max": 200},
                "default_net_developable_area_pct": 0.7,
            },
        },
    )
    monkeypatch.setattr(
        suggest_mod,
        "_rulepack_for_template",
        lambda **kwargs: forced_rulepack,
    )
    baseline_missing_candidate, exclusion = _evaluate_template_candidate(
        session=_FakeSession(),
        site=_make_site(
            site_id=6,
            geom_hash="site-hash",
            geometry_revisions=[_make_revision(revision_id=61, geom_hash="site-hash")],
            planning_links=[SimpleNamespace(
                planning_application_id=support_app.id,
                planning_application=support_app,
                source_snapshot_id="link-snap",
                distance_m=5.0,
            )],
            site_area_sqm=120.0,
        ),
        baseline_pack=None,
        template=template,
        extant_permission=ExtantPermissionRead.model_construct(
            status=ExtantPermissionStatus.NO_ACTIVE_PERMISSION_FOUND,
            eligibility_status=EligibilityStatus.PASS,
            manual_review_required=False,
            summary="PASS",
            reasons=[],
            coverage_gaps=[],
            matched_records=[],
        ),
        manual_seed=False,
    )
    assert exclusion is None
    assert baseline_missing_candidate is not None
    assert "BASELINE_PACK_MISSING" in baseline_missing_candidate.missing_data_flags
    assert baseline_missing_candidate.status == ScenarioStatus.ANALYST_REQUIRED


def test_suggest_persist_and_cleanup_helpers_cover_rulepack_lookup_and_citations(monkeypatch):
    site = _make_site(
        site_id=7,
        geom_hash="site-hash",
        geometry_revisions=[_make_revision(revision_id=71, geom_hash="site-hash")],
    )
    current_auto = _make_scenario(
        scenario_id=72,
        site=site,
        status=ScenarioStatus.AUTO_CONFIRMED,
        source=ScenarioSource.AUTO,
        geom_hash="site-hash",
        current=True,
        headline=True,
    )
    keep_auto = _make_scenario(
        scenario_id=73,
        site=site,
        status=ScenarioStatus.AUTO_CONFIRMED,
        source=ScenarioSource.AUTO,
        geom_hash="site-hash",
        current=True,
        headline=False,
    )
    non_current = _make_scenario(
        scenario_id=74,
        site=site,
        status=ScenarioStatus.AUTO_CONFIRMED,
        source=ScenarioSource.AUTO,
        geom_hash="site-hash",
        current=False,
        headline=False,
    )
    analyst_current = _make_scenario(
        scenario_id=75,
        site=site,
        status=ScenarioStatus.ANALYST_CONFIRMED,
        source=ScenarioSource.ANALYST,
        geom_hash="site-hash",
        current=True,
        headline=False,
    )
    site.scenarios = [current_auto, keep_auto, non_current, analyst_current]
    _mark_stale_current_auto_scenarios(
        session=_FakeSession(),
        site=site,
        keep_ids={keep_auto.id},
    )
    assert current_auto.is_current is False
    assert current_auto.is_headline is False
    assert keep_auto.is_current is True
    assert non_current.is_current is False
    assert analyst_current.is_current is True
    assert _rulepack_for_template(baseline_pack=None, template_key="resi_5_9_full") is None

    fake_session = _FakeSession()
    current_revision = _make_revision(revision_id=76, geom_hash="site-hash")
    candidate = ScenarioCandidate(
        template_key="resi_5_9_full",
        template_version="v1",
        proposal_form=ProposalForm.REDEVELOPMENT,
        units_assumed=6,
        route_assumed="FULL",
        height_band_assumed="MID_RISE",
        net_developable_area_pct=0.7,
        housing_mix_assumed_json={"1br": 0.25},
        parking_assumption=None,
        affordable_housing_assumption=None,
        access_assumption=None,
        heuristic_rank=12,
        score=9,
        status=ScenarioStatus.ANALYST_REQUIRED,
        manual_review_required=True,
        reason_codes=[],
        missing_data_flags=["BASELINE_PACK_MISSING"],
        warning_codes=["ANALYST_CONFIRMATION_REQUIRED"],
        support=CandidateSupport(application=None, strong=True),
    )
    persist_site = _make_site(
        site_id=8,
        geom_hash="site-hash",
        geometry_revisions=[current_revision],
    )
    extant_permission = ExtantPermissionRead.model_construct(
        status=ExtantPermissionStatus.NO_ACTIVE_PERMISSION_FOUND,
        eligibility_status=EligibilityStatus.PASS,
        manual_review_required=False,
        summary="PASS",
        reasons=[],
        coverage_gaps=[],
        matched_records=[],
    )
    monkeypatch.setattr(
        suggest_mod,
        "assemble_scenario_evidence",
        lambda **kwargs: _empty_evidence_pack(),
    )
    scenario_row = _persist_candidate(
        session=fake_session,
        site=persist_site,
        current_revision=current_revision,
        candidate=candidate,
        requested_by="pytest",
        site_evidence=_empty_evidence_pack(),
        baseline_pack=None,
        extant_permission=extant_permission,
    )
    assert scenario_row.site_geometry_revision_id == current_revision.id
    assert scenario_row.red_line_geom_hash == current_revision.geom_hash
    assert scenario_row.scenario_source == ScenarioSource.AUTO
    assert scenario_row.status == ScenarioStatus.ANALYST_REQUIRED
    assert scenario_row.is_current is True
    assert scenario_row.rationale_json["warning_codes"] == ["ANALYST_CONFIRMATION_REQUIRED"]
    assert scenario_row.evidence_json["for"] == []
    assert fake_session.added
    assert isinstance(fake_session.added[0], SiteScenario)

    assert _citations_complete(
        [
            {
                "label": "Rule source",
                "source_family": "BOROUGH_REGISTER",
                "effective_date": "2026-04-01",
                "source_snapshot_id": "citation-snap",
            }
        ]
    )
    assert not _citations_complete(
        [{"label": "Rule source", "source_family": "BOROUGH_REGISTER"}]
    )


def test_persist_candidate_creates_new_scenario_row_when_missing(monkeypatch):
    site = _make_site(
        site_id=13,
        geom_hash="site-hash",
        geometry_revisions=[_make_revision(revision_id=131, geom_hash="site-hash")],
    )
    current_revision = site.geometry_revisions[0]
    fake_session = _FakeSession()
    candidate = ScenarioCandidate(
        template_key="resi_5_9_full",
        template_version="v1",
        proposal_form=ProposalForm.REDEVELOPMENT,
        units_assumed=6,
        route_assumed="FULL",
        height_band_assumed="MID_RISE",
        net_developable_area_pct=0.7,
        housing_mix_assumed_json={"1br": 0.25},
        parking_assumption=None,
        affordable_housing_assumption=None,
        access_assumption=None,
        heuristic_rank=12,
        score=9,
        status=ScenarioStatus.ANALYST_REQUIRED,
        manual_review_required=True,
        reason_codes=[],
        missing_data_flags=["BASELINE_PACK_MISSING"],
        warning_codes=["ANALYST_CONFIRMATION_REQUIRED"],
        support=CandidateSupport(application=None, strong=True),
    )
    monkeypatch.setattr(
        suggest_mod,
        "assemble_scenario_evidence",
        lambda **kwargs: _empty_evidence_pack(),
    )
    scenario_row = _persist_candidate(
        session=fake_session,
        site=site,
        current_revision=current_revision,
        candidate=candidate,
        requested_by="pytest",
        site_evidence=_empty_evidence_pack(),
        baseline_pack=None,
        extant_permission=ExtantPermissionRead.model_construct(
            status=ExtantPermissionStatus.NO_ACTIVE_PERMISSION_FOUND,
            eligibility_status=EligibilityStatus.PASS,
            manual_review_required=False,
            summary="PASS",
            reasons=[],
            coverage_gaps=[],
            matched_records=[],
        ),
    )
    assert fake_session.added and isinstance(fake_session.added[0], SiteScenario)
    assert scenario_row.site_id == site.id
    assert scenario_row.site_geometry_revision_id == current_revision.id
    assert scenario_row.status == ScenarioStatus.ANALYST_REQUIRED
    assert scenario_row.is_current is True


def test_persist_candidate_reuses_existing_scenario_row(monkeypatch):
    site = _make_site(
        site_id=14,
        geom_hash="site-hash",
        geometry_revisions=[_make_revision(revision_id=141, geom_hash="site-hash")],
    )
    current_revision = site.geometry_revisions[0]
    existing_scenario = _make_scenario(
        scenario_id=142,
        site=site,
        status=ScenarioStatus.AUTO_CONFIRMED,
        source=ScenarioSource.AUTO,
        geom_hash="site-hash",
        current=True,
        headline=False,
    )
    fake_session = _FakeSession()
    monkeypatch.setattr(fake_session, "get", lambda model, key: existing_scenario)
    candidate = ScenarioCandidate(
        template_key="resi_5_9_full",
        template_version="v1",
        proposal_form=ProposalForm.REDEVELOPMENT,
        units_assumed=6,
        route_assumed="FULL",
        height_band_assumed="MID_RISE",
        net_developable_area_pct=0.7,
        housing_mix_assumed_json={"1br": 0.25},
        parking_assumption=None,
        affordable_housing_assumption=None,
        access_assumption=None,
        heuristic_rank=12,
        score=9,
        status=ScenarioStatus.ANALYST_REQUIRED,
        manual_review_required=True,
        reason_codes=[],
        missing_data_flags=["BASELINE_PACK_MISSING"],
        warning_codes=["ANALYST_CONFIRMATION_REQUIRED"],
        support=CandidateSupport(application=None, strong=True),
    )
    monkeypatch.setattr(
        suggest_mod,
        "assemble_scenario_evidence",
        lambda **kwargs: _empty_evidence_pack(),
    )
    scenario_row = _persist_candidate(
        session=fake_session,
        site=site,
        current_revision=current_revision,
        candidate=candidate,
        requested_by="pytest",
        site_evidence=_empty_evidence_pack(),
        baseline_pack=None,
        extant_permission=ExtantPermissionRead.model_construct(
            status=ExtantPermissionStatus.NO_ACTIVE_PERMISSION_FOUND,
            eligibility_status=EligibilityStatus.PASS,
            manual_review_required=False,
            summary="PASS",
            reasons=[],
            coverage_gaps=[],
            matched_records=[],
        ),
    )
    assert scenario_row is existing_scenario
    assert fake_session.added == []
    assert scenario_row.site_id == site.id
    assert scenario_row.site_geometry_revision_id == current_revision.id
    assert scenario_row.is_current is True


def test_build_designation_profile_skips_inactive_rows(monkeypatch):
    active_policy = _make_policy_fact(
        policy_family="SITE_ALLOCATION",
        effective_from="2025-01-01",
        effective_to=None,
        source_snapshot_id="pa-active",
    )
    inactive_policy = _make_policy_fact(
        policy_family="DENSITY_GUIDANCE",
        effective_from="2027-01-01",
        effective_to=None,
        source_snapshot_id="pa-inactive",
    )
    active_constraint = _make_constraint_fact(
        feature_family="heritage",
        feature_subtype="conservation_area",
        effective_from="2025-01-01",
        effective_to=None,
        source_snapshot_id="cf-active",
    )
    inactive_constraint = _make_constraint_fact(
        feature_family="article4",
        feature_subtype="restriction",
        effective_from="2027-01-01",
        effective_to=None,
        source_snapshot_id="cf-inactive",
    )
    site = SimpleNamespace(
        policy_facts=[active_policy, inactive_policy],
        constraint_facts=[active_constraint, inactive_constraint],
    )
    monkeypatch.setattr(build_mod, "_apply_brownfield_designations", lambda **kwargs: None)
    monkeypatch.setattr(build_mod, "policy_area_snapshot", lambda fact: fact.snapshot)
    monkeypatch.setattr(build_mod, "constraint_snapshot", lambda fact: fact.snapshot)
    session = _FakeSession(rows_by_entity={PolicyArea: [], PlanningConstraintFeature: []})

    profile, source_snapshot_ids = build_designation_profile_for_site_context(
        session=session,
        site=site,
        geometry=None,
        area_sqm=100.0,
        as_of_date=date(2026, 4, 1),
    )
    assert profile["policy_families"] == ["SITE_ALLOCATION"]
    assert profile["constraint_families"] == ["heritage:conservation_area"]
    assert profile["has_site_allocation"] is True
    assert profile["has_density_guidance"] is False
    assert profile["has_conservation_area"] is True
    assert profile["has_article4"] is False
    assert source_snapshot_ids == {"pa-active", "cf-active"}


def test_build_feature_snapshot_covers_on_site_and_nearby_counts(monkeypatch):
    site_geom = "POLYGON ((0 0, 10 0, 10 10, 0 10, 0 0))"
    site = _make_site(
        site_id=9,
        geom_hash="feature-site-hash",
        geom_27700=site_geom,
        site_area_sqm=100.0,
    )
    scenario = _make_scenario(
        scenario_id=91,
        site=site,
        status=ScenarioStatus.AUTO_CONFIRMED,
        source=ScenarioSource.AUTO,
        geom_hash="feature-site-hash",
        template_key="resi_5_9_full",
        proposal_form=ProposalForm.REDEVELOPMENT,
        units_assumed=6,
        route_assumed="FULL",
        net_developable_area_pct=0.7,
    )

    onsite_positive = _make_application(
        application_id=92,
        external_ref="ONSITE-POS",
        borough_id="camden",
        proposal_description="On-site positive",
        route_normalized="FULL",
        units_proposed=None,
        status="APPROVED",
        decision="APPROVED",
        source_snapshot_id="onsite-pos-snap",
        geom_wkt=site_geom,
        documents=[SimpleNamespace(asset_id="onsite-pos-raw")],
        raw_record_json={},
    )
    onsite_negative = _make_application(
        application_id=93,
        external_ref="ONSITE-NEG",
        borough_id="camden",
        proposal_description="On-site negative",
        route_normalized="FULL",
        units_proposed=None,
        status="REFUSED",
        decision="REFUSED",
        source_snapshot_id="onsite-neg-snap",
        geom_wkt=site_geom,
        documents=[SimpleNamespace(asset_id="onsite-neg-raw")],
        raw_record_json={},
    )
    nearby_positive = _make_application(
        application_id=94,
        external_ref="NEAR-POS",
        borough_id="camden",
        proposal_description="Nearby positive",
        route_normalized="FULL",
        units_proposed=8,
        status="APPROVED",
        decision="APPROVED",
        source_snapshot_id="near-pos-snap",
        geom_wkt="POINT (20 5)",
        documents=[SimpleNamespace(asset_id="near-pos-raw")],
        raw_record_json={},
    )
    nearby_negative = _make_application(
        application_id=95,
        external_ref="NEAR-NEG",
        borough_id="camden",
        proposal_description="Nearby negative",
        route_normalized="FULL",
        units_proposed=3,
        status="REFUSED",
        decision="REFUSED",
        source_snapshot_id="near-neg-snap",
        geom_wkt="POINT (120 5)",
        documents=[SimpleNamespace(asset_id="near-neg-raw")],
        raw_record_json={},
    )
    adjacent_negative = _make_application(
        application_id=96,
        external_ref="ADJ-NEG",
        borough_id="camden",
        proposal_description="Adjacent negative",
        route_normalized="FULL",
        units_proposed=4,
        status="REFUSED",
        decision="REFUSED",
        source_snapshot_id="adj-neg-snap",
        geom_wkt="POINT (18 5)",
        documents=[SimpleNamespace(asset_id="adj-neg-raw")],
        raw_record_json={},
    )
    nearby_context_negative = _make_application(
        application_id=97,
        external_ref="NEAR-CTX-NEG",
        borough_id="camden",
        proposal_description="Nearby context negative",
        route_normalized="FULL",
        units_proposed=4,
        status="REFUSED",
        decision="REFUSED",
        source_snapshot_id="near-ctx-neg-snap",
        geom_wkt="POINT (320 5)",
        documents=[SimpleNamespace(asset_id="near-ctx-neg-raw")],
        raw_record_json={},
    )
    site.planning_links = [
        SimpleNamespace(
            planning_application_id=onsite_positive.id,
            planning_application=onsite_positive,
            source_snapshot_id="onsite-pos-link",
            distance_m=0.0,
        ),
        SimpleNamespace(
            planning_application_id=onsite_negative.id,
            planning_application=onsite_negative,
            source_snapshot_id="onsite-neg-link",
            distance_m=0.0,
        ),
    ]
    labels = [
        _make_label(
            label_id=96,
            application=onsite_positive,
            borough_id="camden",
            template_key="resi_5_9_full",
            label_class=HistoricalLabelClass.POSITIVE,
            proposal_form=ProposalForm.REDEVELOPMENT,
            units_proposed=None,
            site_area_sqm=100.0,
            archetype_key="same-archetype",
            designation_profile_json={"has_conservation_area": True},
            source_snapshot_ids_json=["onsite-pos-snap"],
            raw_asset_ids_json=["onsite-pos-raw"],
            valid_date=date(2026, 1, 1),
            decision_date=date(2026, 2, 1),
        ),
        _make_label(
            label_id=97,
            application=onsite_negative,
            borough_id="camden",
            template_key="resi_5_9_full",
            label_class=HistoricalLabelClass.NEGATIVE,
            proposal_form=ProposalForm.REDEVELOPMENT,
            units_proposed=None,
            site_area_sqm=100.0,
            archetype_key="same-archetype",
            designation_profile_json={"has_conservation_area": True},
            source_snapshot_ids_json=["onsite-neg-snap"],
            raw_asset_ids_json=["onsite-neg-raw"],
            valid_date=date(2026, 1, 1),
            decision_date=date(2026, 2, 1),
        ),
        _make_label(
            label_id=98,
            application=nearby_positive,
            borough_id="camden",
            template_key="resi_5_9_full",
            label_class=HistoricalLabelClass.POSITIVE,
            proposal_form=ProposalForm.REDEVELOPMENT,
            units_proposed=8,
            site_area_sqm=110.0,
            archetype_key="same-archetype",
            designation_profile_json={"has_conservation_area": True},
            source_snapshot_ids_json=["near-pos-snap"],
            raw_asset_ids_json=["near-pos-raw"],
            valid_date=date(2026, 1, 1),
            decision_date=date(2026, 2, 1),
        ),
        _make_label(
            label_id=99,
            application=nearby_negative,
            borough_id="camden",
            template_key="resi_5_9_full",
            label_class=HistoricalLabelClass.NEGATIVE,
            proposal_form=ProposalForm.REDEVELOPMENT,
            units_proposed=3,
            site_area_sqm=115.0,
            archetype_key="same-archetype",
            designation_profile_json={"has_conservation_area": True},
            source_snapshot_ids_json=["near-neg-snap"],
            raw_asset_ids_json=["near-neg-raw"],
            valid_date=date(2026, 1, 1),
            decision_date=date(2026, 2, 1),
        ),
        _make_label(
            label_id=100,
            application=adjacent_negative,
            borough_id="camden",
            template_key="resi_5_9_full",
            label_class=HistoricalLabelClass.NEGATIVE,
            proposal_form=ProposalForm.REDEVELOPMENT,
            units_proposed=4,
            site_area_sqm=114.0,
            archetype_key="same-archetype",
            designation_profile_json={"has_conservation_area": True},
            source_snapshot_ids_json=["adj-neg-snap"],
            raw_asset_ids_json=["adj-neg-raw"],
            valid_date=date(2026, 1, 1),
            decision_date=date(2026, 2, 1),
        ),
        _make_label(
            label_id=101,
            application=nearby_context_negative,
            borough_id="camden",
            template_key="resi_5_9_full",
            label_class=HistoricalLabelClass.NEGATIVE,
            proposal_form=ProposalForm.REDEVELOPMENT,
            units_proposed=4,
            site_area_sqm=116.0,
            archetype_key="same-archetype",
            designation_profile_json={"has_conservation_area": True},
            source_snapshot_ids_json=["near-ctx-neg-snap"],
            raw_asset_ids_json=["near-ctx-neg-raw"],
            valid_date=date(2026, 1, 1),
            decision_date=date(2026, 2, 1),
        ),
    ]

    def _snapshot(link):
        app = link.planning_application
        return {
            "status": app.status,
            "external_ref": app.external_ref,
            "proposal_description": app.proposal_description,
            "source_system": app.source_system,
            "source_url": app.source_url,
            "source_snapshot_id": app.source_snapshot_id,
            "decision": app.decision,
            "valid_date": app.valid_date.isoformat(),
            "decision_date": app.decision_date.isoformat(),
            "route_normalized": app.route_normalized,
            "units_proposed": app.units_proposed,
            "raw_record_json": dict(app.raw_record_json),
            "documents": [{"asset_id": doc.asset_id} for doc in app.documents],
        }

    monkeypatch.setattr(build_mod, "planning_application_snapshot", _snapshot)
    monkeypatch.setattr(build_mod, "_latest_coverage_rows", lambda **kwargs: [])
    monkeypatch.setattr(
        build_mod,
        "build_designation_profile_for_site_context",
        lambda **kwargs: (
            {
                "policy_families": ["SITE_ALLOCATION"],
                "constraint_families": ["heritage:conservation_area"],
                "has_site_allocation": True,
                "has_density_guidance": False,
                "has_conservation_area": True,
                "has_article4": False,
                "has_flood_zone": False,
                "has_listed_building_nearby": False,
                "brownfield_part1": False,
                "brownfield_part2_active": False,
                "pip_active": False,
                "tdc_active": False,
            },
            {"designation-snap"},
        ),
    )

    session = _FakeSession(
            rows_by_entity={
            HistoricalCaseLabel: labels,
            PlanningApplication: [
                onsite_positive,
                onsite_negative,
                nearby_positive,
                nearby_negative,
                adjacent_negative,
                nearby_context_negative,
            ],
        }
    )
    result = build_feature_snapshot(
        session=session,
        site=site,
        scenario=scenario,
        as_of_date=date(2026, 4, 1),
    )
    values = result.feature_json["values"]
    assert values["onsite_positive_count"] == 1
    assert values["onsite_negative_count"] == 1
    assert values["onsite_max_units_approved"] is None
    assert values["onsite_max_units_refused"] is None
    assert values["adjacent_approved_0_50m"] == 1
    assert values["adjacent_refused_0_50m"] == 1
    assert values["local_precedent_refused_50_250m"] == 1
    assert values["local_context_refused_250_500m"] == 1
    assert values["same_template_positive_500m"] == 1
    assert result.source_snapshot_ids
    assert result.raw_asset_ids


def test_build_feature_snapshot_covers_adjacent_negative_window(monkeypatch):
    site_geom = "POLYGON ((0 0, 10 0, 10 10, 0 10, 0 0))"
    site = _make_site(
        site_id=16,
        geom_hash="feature-site-hash",
        geom_27700=site_geom,
        site_area_sqm=100.0,
    )
    scenario = _make_scenario(
        scenario_id=161,
        site=site,
        status=ScenarioStatus.AUTO_CONFIRMED,
        source=ScenarioSource.AUTO,
        geom_hash="feature-site-hash",
        template_key="resi_5_9_full",
        proposal_form=ProposalForm.REDEVELOPMENT,
        units_assumed=6,
        route_assumed="FULL",
        net_developable_area_pct=0.7,
    )
    adjacent_negative = _make_application(
        application_id=162,
        external_ref="ADJ-ITER-NEG",
        borough_id="camden",
        proposal_description="Adjacent negative iteration",
        route_normalized="FULL",
        units_proposed=4,
        status="REFUSED",
        decision="REFUSED",
        source_snapshot_id="adj-iter-neg-snap",
        geom_wkt="POINT (18 5)",
        documents=[SimpleNamespace(asset_id="adj-iter-neg-raw")],
        raw_record_json={},
    )
    nearby_positive = _make_application(
        application_id=163,
        external_ref="NEAR-ITER-POS",
        borough_id="camden",
        proposal_description="Nearby positive iteration",
        route_normalized="FULL",
        units_proposed=8,
        status="APPROVED",
        decision="APPROVED",
        source_snapshot_id="near-iter-pos-snap",
        geom_wkt="POINT (320 5)",
        documents=[SimpleNamespace(asset_id="near-iter-pos-raw")],
        raw_record_json={},
    )
    labels = [
        _make_label(
            label_id=164,
            application=adjacent_negative,
            borough_id="camden",
            template_key="resi_5_9_full",
            label_class=HistoricalLabelClass.NEGATIVE,
            proposal_form=ProposalForm.REDEVELOPMENT,
            units_proposed=4,
            site_area_sqm=114.0,
            archetype_key="same-archetype",
            designation_profile_json={"has_conservation_area": True},
            source_snapshot_ids_json=["adj-iter-neg-snap"],
            raw_asset_ids_json=["adj-iter-neg-raw"],
            valid_date=date(2026, 1, 1),
            decision_date=date(2026, 2, 1),
        ),
        _make_label(
            label_id=165,
            application=nearby_positive,
            borough_id="camden",
            template_key="resi_5_9_full",
            label_class=HistoricalLabelClass.POSITIVE,
            proposal_form=ProposalForm.REDEVELOPMENT,
            units_proposed=8,
            site_area_sqm=130.0,
            archetype_key="same-archetype",
            designation_profile_json={"has_conservation_area": True},
            source_snapshot_ids_json=["near-iter-pos-snap"],
            raw_asset_ids_json=["near-iter-pos-raw"],
            valid_date=date(2026, 1, 1),
            decision_date=date(2026, 2, 1),
        ),
    ]
    monkeypatch.setattr(build_mod, "planning_application_snapshot", lambda link: {})
    monkeypatch.setattr(build_mod, "_latest_coverage_rows", lambda **kwargs: [])
    monkeypatch.setattr(
        build_mod,
        "build_designation_profile_for_site_context",
        lambda **kwargs: (
            {
                "policy_families": [],
                "constraint_families": [],
                "has_site_allocation": False,
                "has_density_guidance": False,
                "has_conservation_area": False,
                "has_article4": False,
                "has_flood_zone": False,
                "has_listed_building_nearby": False,
                "brownfield_part1": False,
                "brownfield_part2_active": False,
                "pip_active": False,
                "tdc_active": False,
            },
            set(),
        ),
    )
    session = _FakeSession(
        rows_by_entity={
            HistoricalCaseLabel: labels,
            PlanningApplication: [adjacent_negative, nearby_positive],
        }
    )
    result = build_feature_snapshot(
        session=session,
        site=site,
        scenario=scenario,
        as_of_date=date(2026, 4, 1),
    )
    values = result.feature_json["values"]
    assert values["adjacent_refused_0_50m"] == 1
    assert values["local_context_approved_250_500m"] == 1


def test_build_feature_snapshot_covers_nearby_negative_branch(monkeypatch):
    site_geom = "POLYGON ((0 0, 10 0, 10 10, 0 10, 0 0))"
    site = _make_site(
        site_id=18,
        geom_hash="feature-site-hash",
        geom_27700=site_geom,
        site_area_sqm=100.0,
    )
    scenario = _make_scenario(
        scenario_id=181,
        site=site,
        status=ScenarioStatus.AUTO_CONFIRMED,
        source=ScenarioSource.AUTO,
        geom_hash="feature-site-hash",
        template_key="resi_5_9_full",
        proposal_form=ProposalForm.REDEVELOPMENT,
        units_assumed=6,
        route_assumed="FULL",
        net_developable_area_pct=0.7,
    )
    nearby_positive = _make_application(
        application_id=182,
        external_ref="NEAR-BRANCH-POS",
        borough_id="camden",
        proposal_description="Nearby positive branch",
        route_normalized="FULL",
        units_proposed=8,
        status="APPROVED",
        decision="APPROVED",
        source_snapshot_id="near-branch-pos-snap",
        geom_wkt="POINT (20 5)",
        documents=[SimpleNamespace(asset_id="near-branch-pos-raw")],
        raw_record_json={},
    )
    nearby_negative = _make_application(
        application_id=183,
        external_ref="NEAR-BRANCH-NEG",
        borough_id="camden",
        proposal_description="Nearby negative branch",
        route_normalized="FULL",
        units_proposed=4,
        status="REFUSED",
        decision="REFUSED",
        source_snapshot_id="near-branch-neg-snap",
        geom_wkt="POINT (120 5)",
        documents=[SimpleNamespace(asset_id="near-branch-neg-raw")],
        raw_record_json={},
    )
    nearby_censored = _make_application(
        application_id=186,
        external_ref="NEAR-BRANCH-CENSORED",
        borough_id="camden",
        proposal_description="Nearby censored branch",
        route_normalized="FULL",
        units_proposed=5,
        status="APPROVED",
        decision="APPROVED",
        source_snapshot_id="near-branch-censored-snap",
        geom_wkt="POINT (320 5)",
        documents=[SimpleNamespace(asset_id="near-branch-censored-raw")],
        raw_record_json={},
    )
    labels = [
        _make_label(
            label_id=184,
            application=nearby_positive,
            borough_id="camden",
            template_key="resi_5_9_full",
            label_class=HistoricalLabelClass.POSITIVE,
            proposal_form=ProposalForm.REDEVELOPMENT,
            units_proposed=8,
            site_area_sqm=110.0,
            archetype_key="same-archetype",
            designation_profile_json={"has_conservation_area": True},
            source_snapshot_ids_json=["near-branch-pos-snap"],
            raw_asset_ids_json=["near-branch-pos-raw"],
            valid_date=date(2026, 1, 1),
            decision_date=date(2026, 2, 1),
        ),
        _make_label(
            label_id=185,
            application=nearby_negative,
            borough_id="camden",
            template_key="resi_5_9_full",
            label_class=HistoricalLabelClass.NEGATIVE,
            proposal_form=ProposalForm.REDEVELOPMENT,
            units_proposed=4,
            site_area_sqm=115.0,
            archetype_key="same-archetype",
            designation_profile_json={"has_conservation_area": True},
            source_snapshot_ids_json=["near-branch-neg-snap"],
            raw_asset_ids_json=["near-branch-neg-raw"],
            valid_date=date(2026, 1, 1),
            decision_date=date(2026, 2, 1),
        ),
        _make_label(
            label_id=186,
            application=nearby_censored,
            borough_id="camden",
            template_key="resi_5_9_full",
            label_class=HistoricalLabelClass.CENSORED,
            proposal_form=ProposalForm.REDEVELOPMENT,
            units_proposed=5,
            site_area_sqm=112.0,
            archetype_key="same-archetype",
            designation_profile_json={"has_conservation_area": True},
            source_snapshot_ids_json=["near-branch-censored-snap"],
            raw_asset_ids_json=["near-branch-censored-raw"],
            valid_date=date(2026, 1, 1),
            decision_date=date(2026, 2, 1),
        ),
    ]
    monkeypatch.setattr(build_mod, "planning_application_snapshot", lambda link: {})
    monkeypatch.setattr(build_mod, "_latest_coverage_rows", lambda **kwargs: [])
    monkeypatch.setattr(
        build_mod,
        "build_designation_profile_for_site_context",
        lambda **kwargs: (
            {
                "policy_families": [],
                "constraint_families": [],
                "has_site_allocation": False,
                "has_density_guidance": False,
                "has_conservation_area": False,
                "has_article4": False,
                "has_flood_zone": False,
                "has_listed_building_nearby": False,
                "brownfield_part1": False,
                "brownfield_part2_active": False,
                "pip_active": False,
                "tdc_active": False,
            },
            set(),
        ),
    )
    session = _FakeSession(
        rows_by_entity={
            HistoricalCaseLabel: labels,
            PlanningApplication: [nearby_positive, nearby_negative, nearby_censored],
        }
    )
    result = build_feature_snapshot(
        session=session,
        site=site,
        scenario=scenario,
        as_of_date=date(2026, 4, 1),
    )
    values = result.feature_json["values"]
    assert values["adjacent_approved_0_50m"] == 1
    assert values["local_precedent_refused_50_250m"] == 1
    assert values["local_context_refused_250_500m"] == 0


def test_scenario_evidence_and_citation_url_cover_rulepack_gap_and_url_fallback():
    site = _make_site(site_id=10, geom_hash="site-hash", planning_links=[])
    scenario = _make_scenario(
        scenario_id=101,
        site=site,
        status=ScenarioStatus.ANALYST_REQUIRED,
        source=ScenarioSource.ANALYST,
        geom_hash="site-hash",
        net_developable_area_pct=0.55,
    )
    scenario.parking_assumption = "Street parking remains assumed."
    scenario.affordable_housing_assumption = "20 percent affordable housing."
    scenario.access_assumption = "Existing frontage is assumed."
    scenario.rationale_json = {
        "missing_data_flags": ["FLAG_A"],
        "warning_codes": ["RULEPACK_STALE"],
    }
    baseline_pack = _make_basal_pack(
        status=BaselinePackStatus.SIGNED_OFF,
        rulepacks=[_make_rulepack(template_key="different-template")],
    )
    packed = assemble_scenario_evidence(
        session=_FakeSession(),
        site=site,
        scenario=scenario,
        site_evidence=_empty_evidence_pack(),
        extant_permission=ExtantPermissionRead.model_construct(
            status=ExtantPermissionStatus.NO_ACTIVE_PERMISSION_FOUND,
            eligibility_status=EligibilityStatus.PASS,
            manual_review_required=False,
            summary="PASS",
            reasons=[],
            coverage_gaps=[],
            matched_records=[],
        ),
        baseline_pack=baseline_pack,
    )
    assert any(item.topic == "scenario_fit" for item in packed.for_)
    assert any(item.topic == "developable_area" for item in packed.against)
    assert any(item.topic == "scenario_gap" for item in packed.unknown)
    assert any(item.topic == "scenario_warning" for item in packed.unknown)
    assert assemble_mod._citation_url([{"source_url": "https://source.example"}]) == "https://source.example"
    assert assemble_mod._citation_url([{"url": "https://fallback.example"}]) == "https://fallback.example"
    assert assemble_mod._citation_url([{}]) is None


def test_comparable_builder_selects_all_fallback_tiers_and_tracks_sources():
    site = _make_site(site_id=11, geom_hash="site-hash", planning_links=[])
    scenario = _make_scenario(
        scenario_id=111,
        site=site,
        status=ScenarioStatus.ANALYST_CONFIRMED,
        source=ScenarioSource.ANALYST,
        geom_hash="site-hash",
        template_key="resi_5_9_full",
        proposal_form=ProposalForm.REDEVELOPMENT,
        units_assumed=6,
        route_assumed="FULL",
    )
    feature_json = {
        "values": {
            "site_area_sqm": 120.0,
            "designation_archetype_key": "same-archetype",
        },
        "designation_profile": {
            "has_conservation_area": True,
            "policy_families": ["SITE_ALLOCATION"],
        },
    }
    label_same_borough = _make_label(
        label_id=112,
        application=_make_application(
            application_id=113,
            external_ref="APP-A",
            borough_id="camden",
            proposal_description="Same borough",
            route_normalized="FULL",
            units_proposed=6,
            status="APPROVED",
            decision="APPROVED",
            source_snapshot_id="snap-a",
            geom_wkt="POINT (0 0)",
            documents=[SimpleNamespace(asset_id="raw-a")],
            raw_record_json={},
        ),
        borough_id="camden",
        template_key="resi_5_9_full",
        label_class=HistoricalLabelClass.POSITIVE,
        proposal_form=ProposalForm.REDEVELOPMENT,
        units_proposed=6,
        site_area_sqm=120.0,
        archetype_key="other",
        designation_profile_json={"has_conservation_area": True},
        source_snapshot_ids_json=["snap-a"],
        raw_asset_ids_json=["raw-a"],
        valid_date=date(2026, 1, 1),
        decision_date=date(2026, 2, 1),
    )
    label_london = _make_label(
        label_id=114,
        application=_make_application(
            application_id=115,
            external_ref="APP-B",
            borough_id="london",
            proposal_description="London same template",
            route_normalized="FULL",
            units_proposed=7,
            status="APPROVED",
            decision="APPROVED",
            source_snapshot_id="snap-b",
            geom_wkt="POINT (1 1)",
            documents=[SimpleNamespace(asset_id="raw-b")],
            raw_record_json={},
        ),
        borough_id="london",
        template_key="resi_5_9_full",
        label_class=HistoricalLabelClass.NEGATIVE,
        proposal_form=ProposalForm.REDEVELOPMENT,
        units_proposed=7,
        site_area_sqm=118.0,
        archetype_key="other",
        designation_profile_json={"has_conservation_area": False},
        source_snapshot_ids_json=["snap-b"],
        raw_asset_ids_json=["raw-b"],
        valid_date=date(2026, 1, 1),
        decision_date=date(2026, 3, 1),
    )
    label_excluded = _make_label(
        label_id=118,
        application=_make_application(
            application_id=119,
            external_ref="APP-D",
            borough_id="camden",
            proposal_description="Excluded negative",
            route_normalized="FULL",
            units_proposed=5,
            status="REFUSED",
            decision="REFUSED",
            source_snapshot_id="snap-d",
            geom_wkt="POINT (3 3)",
            documents=[SimpleNamespace(asset_id="raw-d")],
            raw_record_json={},
        ),
        borough_id="camden",
        template_key="resi_5_9_full",
        label_class=HistoricalLabelClass.NEGATIVE,
        proposal_form=ProposalForm.REDEVELOPMENT,
        units_proposed=5,
        site_area_sqm=119.0,
        archetype_key="other",
        designation_profile_json={"has_conservation_area": True},
        source_snapshot_ids_json=["snap-d"],
        raw_asset_ids_json=["raw-d"],
        valid_date=date(2026, 1, 1),
        decision_date=date(2026, 2, 1),
        review_status=GoldSetReviewStatus.EXCLUDED,
    )
    label_archetype = _make_label(
        label_id=116,
        application=_make_application(
            application_id=117,
            external_ref="APP-C",
            borough_id="elsewhere",
            proposal_description="Archetype fallback",
            route_normalized="FULL",
            units_proposed=8,
            status="APPROVED",
            decision="APPROVED",
            source_snapshot_id="snap-c",
            geom_wkt="POINT (2 2)",
            documents=[SimpleNamespace(asset_id="raw-c")],
            raw_record_json={},
        ),
        borough_id="elsewhere",
        template_key="resi_5_9_full",
        label_class=HistoricalLabelClass.POSITIVE,
        proposal_form=ProposalForm.BACKLAND,
        units_proposed=8,
        site_area_sqm=130.0,
        archetype_key="same-archetype",
        designation_profile_json={"has_conservation_area": True},
        source_snapshot_ids_json=["snap-c"],
        raw_asset_ids_json=["raw-c"],
        valid_date=date(2026, 1, 1),
        decision_date=date(2026, 2, 1),
    )
    session = _FakeSession(
        rows_by_entity={
            HistoricalCaseLabel: [
                label_same_borough,
                label_london,
                label_excluded,
                label_archetype,
            ]
        }
    )
    result = build_comparable_case_set(
        session=session,
        assessment_run=SimpleNamespace(id=_uuid(118), comparable_case_set=None),
        site=site,
        scenario=scenario,
        as_of_date=date(2026, 4, 1),
        feature_json=feature_json,
    )
    assert result.comparable_case_set.strategy == "template_then_borough_form_archetype"
    assert result.comparable_case_set.same_borough_count == 1
    assert result.comparable_case_set.london_count == 1
    assert result.comparable_case_set.approved_count == 2
    assert result.comparable_case_set.refused_count == 1
    assert [member.fallback_path for member in result.approved_members] == [
        "same_borough_same_template",
        "archetype_same_template",
    ]
    assert [member.fallback_path for member in result.refused_members] == [
        "london_same_template",
    ]
    assert result.source_snapshot_ids == ["snap-a", "snap-b", "snap-c"]
    assert result.raw_asset_ids == ["raw-a", "raw-b", "raw-c"]
    assert "snap-d" not in result.source_snapshot_ids


def test_comparable_builder_covers_negative_iteration_arc():
    site = _make_site(site_id=15, geom_hash="site-hash", planning_links=[])
    scenario = _make_scenario(
        scenario_id=151,
        site=site,
        status=ScenarioStatus.ANALYST_CONFIRMED,
        source=ScenarioSource.ANALYST,
        geom_hash="site-hash",
        template_key="resi_5_9_full",
        proposal_form=ProposalForm.REDEVELOPMENT,
        units_assumed=6,
        route_assumed="FULL",
    )
    positive = _make_label(
        label_id=152,
        application=_make_application(
            application_id=153,
            external_ref="POS-ITER",
            borough_id="camden",
            proposal_description="Positive iteration",
            route_normalized="FULL",
            units_proposed=6,
            status="APPROVED",
            decision="APPROVED",
            source_snapshot_id="snap-pos-iter",
            geom_wkt="POINT (0 0)",
            documents=[SimpleNamespace(asset_id="raw-pos-iter")],
            raw_record_json={},
        ),
        borough_id="camden",
        template_key="resi_5_9_full",
        label_class=HistoricalLabelClass.POSITIVE,
        proposal_form=ProposalForm.REDEVELOPMENT,
        units_proposed=6,
        site_area_sqm=120.0,
        archetype_key="same-archetype",
        designation_profile_json={"has_conservation_area": True},
        source_snapshot_ids_json=["snap-pos-iter"],
        raw_asset_ids_json=["raw-pos-iter"],
        valid_date=date(2026, 1, 1),
        decision_date=date(2026, 2, 1),
    )
    negative = _make_label(
        label_id=154,
        application=_make_application(
            application_id=155,
            external_ref="NEG-ITER",
            borough_id="camden",
            proposal_description="Negative iteration",
            route_normalized="FULL",
            units_proposed=6,
            status="REFUSED",
            decision="REFUSED",
            source_snapshot_id="snap-neg-iter",
            geom_wkt="POINT (1 1)",
            documents=[SimpleNamespace(asset_id="raw-neg-iter")],
            raw_record_json={},
        ),
        borough_id="camden",
        template_key="resi_5_9_full",
        label_class=HistoricalLabelClass.NEGATIVE,
        proposal_form=ProposalForm.REDEVELOPMENT,
        units_proposed=6,
        site_area_sqm=120.0,
        archetype_key="same-archetype",
        designation_profile_json={"has_conservation_area": True},
        source_snapshot_ids_json=["snap-neg-iter"],
        raw_asset_ids_json=["raw-neg-iter"],
        valid_date=date(2026, 1, 1),
        decision_date=date(2026, 2, 1),
    )
    session = _FakeSession(rows_by_entity={HistoricalCaseLabel: [negative, positive]})
    result = build_comparable_case_set(
        session=session,
        assessment_run=SimpleNamespace(id=_uuid(156), comparable_case_set=None),
        site=site,
        scenario=scenario,
        as_of_date=date(2026, 4, 1),
        feature_json={
            "values": {
                "site_area_sqm": 120.0,
                "designation_archetype_key": "same-archetype",
            },
            "designation_profile": {"has_conservation_area": True},
        },
    )
    assert result.comparable_case_set.approved_count == 1
    assert result.comparable_case_set.refused_count == 1
    assert result.source_snapshot_ids == ["snap-neg-iter", "snap-pos-iter"]


def test_comparable_builder_skips_non_binary_label_class_rows():
    site = _make_site(site_id=17, geom_hash="site-hash", planning_links=[])
    scenario = _make_scenario(
        scenario_id=171,
        site=site,
        status=ScenarioStatus.ANALYST_CONFIRMED,
        source=ScenarioSource.ANALYST,
        geom_hash="site-hash",
        template_key="resi_5_9_full",
        proposal_form=ProposalForm.REDEVELOPMENT,
        units_assumed=6,
        route_assumed="FULL",
    )
    unknown_label = _make_label(
        label_id=172,
        application=_make_application(
            application_id=173,
            external_ref="UNK-ITER",
            borough_id="camden",
            proposal_description="Unknown label class",
            route_normalized="FULL",
            units_proposed=6,
            status="APPROVED",
            decision="APPROVED",
            source_snapshot_id="snap-unk-iter",
            geom_wkt="POINT (0 0)",
            documents=[SimpleNamespace(asset_id="raw-unk-iter")],
            raw_record_json={},
        ),
        borough_id="camden",
        template_key="resi_5_9_full",
        label_class=HistoricalLabelClass.CENSORED,
        proposal_form=ProposalForm.REDEVELOPMENT,
        units_proposed=6,
        site_area_sqm=120.0,
        archetype_key="same-archetype",
        designation_profile_json={"has_conservation_area": True},
        source_snapshot_ids_json=["snap-unk-iter"],
        raw_asset_ids_json=["raw-unk-iter"],
        valid_date=date(2026, 1, 1),
        decision_date=date(2026, 2, 1),
    )
    positive = _make_label(
        label_id=174,
        application=_make_application(
            application_id=175,
            external_ref="POS-BINARY",
            borough_id="camden",
            proposal_description="Positive label class",
            route_normalized="FULL",
            units_proposed=6,
            status="APPROVED",
            decision="APPROVED",
            source_snapshot_id="snap-pos-binary",
            geom_wkt="POINT (1 1)",
            documents=[SimpleNamespace(asset_id="raw-pos-binary")],
            raw_record_json={},
        ),
        borough_id="camden",
        template_key="resi_5_9_full",
        label_class=HistoricalLabelClass.POSITIVE,
        proposal_form=ProposalForm.REDEVELOPMENT,
        units_proposed=6,
        site_area_sqm=120.0,
        archetype_key="same-archetype",
        designation_profile_json={"has_conservation_area": True},
        source_snapshot_ids_json=["snap-pos-binary"],
        raw_asset_ids_json=["raw-pos-binary"],
        valid_date=date(2026, 1, 1),
        decision_date=date(2026, 2, 1),
    )
    session = _FakeSession(
        rows_by_entity={HistoricalCaseLabel: [unknown_label, positive]}
    )
    result = build_comparable_case_set(
        session=session,
        assessment_run=SimpleNamespace(id=_uuid(176), comparable_case_set=None),
        site=site,
        scenario=scenario,
        as_of_date=date(2026, 4, 1),
        feature_json={
            "values": {
                "site_area_sqm": 120.0,
                "designation_archetype_key": "same-archetype",
            },
            "designation_profile": {"has_conservation_area": True},
        },
    )
    assert result.comparable_case_set.approved_count == 1
    assert result.comparable_case_set.refused_count == 0
    assert result.source_snapshot_ids == ["snap-pos-binary"]


def test_assessment_run_scoring_branches_cover_hidden_storage_and_abstain(monkeypatch):
    site = _make_site(
        site_id=12,
        geom_hash="assessment-site-hash",
        geometry_revisions=[_make_revision(revision_id=121, geom_hash="assessment-site-hash")],
    )
    scenario = _make_scenario(
        scenario_id=122,
        site=site,
        status=ScenarioStatus.ANALYST_CONFIRMED,
        source=ScenarioSource.ANALYST,
        geom_hash="assessment-site-hash",
        template_key="resi_5_9_full",
        proposal_form=ProposalForm.REDEVELOPMENT,
        units_assumed=6,
        route_assumed="FULL",
    )
    site.scenarios = [scenario]
    fake_feature = SimpleNamespace(
        feature_version=FEATURE_VERSION,
        feature_hash="feature-hash",
        feature_json={"values": {"site_area_sqm": 120.0}},
        coverage_json={"source_coverage": [{"coverage_status": "COMPLETE"}]},
    )
    fake_comparables = SimpleNamespace(
        comparable_case_set=SimpleNamespace(strategy="stub"),
        approved_members=[],
        refused_members=[],
        source_snapshot_ids=[],
        raw_asset_ids=[],
    )
    fake_release = SimpleNamespace(id=_uuid(123), model_artifact_hash="model-hash")

    def _patch_common(
        *,
        extant_status,
        storage_value,
        load_artifacts: bool,
        call_score: bool = True,
        artifact_responses: dict[str, object] | None = None,
    ):
        fake_session = _FakeSession(rows_by_entity={AssessmentRun: []})
        monkeypatch.setattr(service_mod, "_load_scenario", lambda **kwargs: scenario)
        monkeypatch.setattr(service_mod, "rebuild_historical_case_labels", lambda **kwargs: None)
        monkeypatch.setattr(service_mod, "build_feature_snapshot", lambda **kwargs: fake_feature)
        monkeypatch.setattr(service_mod, "_upsert_feature_snapshot", lambda **kwargs: fake_feature)
        monkeypatch.setattr(
            service_mod,
            "evaluate_site_extant_permission",
            lambda **kwargs: ExtantPermissionRead.model_construct(
                status=ExtantPermissionStatus.NO_ACTIVE_PERMISSION_FOUND,
                eligibility_status=extant_status,
                manual_review_required=False,
                summary="PASS" if extant_status == EligibilityStatus.PASS else "ABSTAIN",
                reasons=[],
                coverage_gaps=[],
                matched_records=[],
            ),
        )
        monkeypatch.setattr(
            service_mod,
            "get_borough_baseline_pack",
            lambda **kwargs: SimpleNamespace(
                status=BaselinePackStatus.SIGNED_OFF,
                freshness_status=SourceFreshnessStatus.FRESH,
            ),
        )
        monkeypatch.setattr(
            service_mod,
            "assemble_site_evidence",
            lambda **kwargs: _empty_evidence_pack(),
        )
        monkeypatch.setattr(
            service_mod,
            "assemble_scenario_evidence",
            lambda **kwargs: _empty_evidence_pack(),
        )
        monkeypatch.setattr(
            service_mod,
            "build_comparable_case_set",
            lambda **kwargs: fake_comparables,
        )
        monkeypatch.setattr(
            service_mod,
            "resolve_active_release",
            lambda **kwargs: (fake_release, "scope-key"),
        )
        if load_artifacts:
            artifact_map = artifact_responses or {
                "model": {"artifact": "model"},
                "calibration": {"artifact": "calibration"},
                "validation": {"artifact": "validation"},
            }
            monkeypatch.setattr(
                service_mod,
                "load_release_artifact_json",
                lambda *, storage, release, artifact: artifact_map[artifact],
            )
            if call_score:
                monkeypatch.setattr(
                    service_mod,
                    "score_frozen_assessment",
                    lambda **kwargs: {
                        "approval_probability_raw": 0.73,
                        "approval_probability_display": "73%",
                        "estimate_quality": "MEDIUM",
                        "source_coverage_quality": "HIGH",
                        "geometry_quality": "HIGH",
                        "support_quality": "COMPARABLES_PRESENT",
                        "scenario_quality": "HIGH",
                        "ood_quality": "IN_DISTRIBUTION",
                        "ood_status": "IN_DISTRIBUTION",
                        "manual_review_required": False,
                        "support_summary": {"support": "ok"},
                        "validation_summary": {"validation": "ok"},
                        "explanation": {"why": "ok"},
                    },
                )
            else:
                monkeypatch.setattr(
                    service_mod,
                    "score_frozen_assessment",
                    lambda **kwargs: pytest.fail("score_frozen_assessment should not be called"),
                )
        else:
            monkeypatch.setattr(
                service_mod,
                "load_release_artifact_json",
                lambda **kwargs: pytest.fail("load_release_artifact_json should not be called"),
            )
            monkeypatch.setattr(
                service_mod,
                "score_frozen_assessment",
                lambda **kwargs: pytest.fail("score_frozen_assessment should not be called"),
            )
        captured: dict[str, object] = {}

        def _stop_after_result(**kwargs):
            captured["status"] = kwargs["score_execution_status"]
            raise _StopAfterAssessmentResult

        monkeypatch.setattr(service_mod, "_upsert_assessment_result", _stop_after_result)
        monkeypatch.setattr(service_mod, "_persist_evidence_items", lambda **kwargs: None)
        monkeypatch.setattr(service_mod, "_stable_result_payload", lambda **kwargs: {})
        monkeypatch.setattr(
            service_mod,
            "_upsert_prediction_ledger",
            lambda **kwargs: SimpleNamespace(),
        )
        monkeypatch.setattr(
            service_mod,
            "build_or_refresh_valuation_for_assessment",
            lambda **kwargs: None,
        )
        monkeypatch.setattr(service_mod, "_assessment_load_options", lambda: ())
        return fake_session, captured

    partial_session, partial_capture = _patch_common(
        extant_status=EligibilityStatus.PASS,
        storage_value=object(),
        load_artifacts=True,
        call_score=False,
        artifact_responses={
            "model": {"artifact": "model"},
            "calibration": {"artifact": "calibration"},
            "validation": None,
        },
    )
    with pytest.raises(_StopAfterAssessmentResult):
        create_or_refresh_assessment_run(
            session=partial_session,
            site_id=site.id,
            scenario_id=scenario.id,
            as_of_date=date(2026, 4, 1),
            requested_by="pytest",
            storage=object(),
        )
    assert partial_capture["status"] == "NOT_IMPLEMENTED"

    score_session, score_capture = _patch_common(
        extant_status=EligibilityStatus.PASS,
        storage_value=object(),
        load_artifacts=True,
    )
    with pytest.raises(_StopAfterAssessmentResult):
        create_or_refresh_assessment_run(
            session=score_session,
            site_id=site.id,
            scenario_id=scenario.id,
            as_of_date=date(2026, 4, 1),
            requested_by="pytest",
            storage=object(),
        )
    assert score_capture["status"] == "HIDDEN_ESTIMATE_AVAILABLE"

    storage_session, storage_capture = _patch_common(
        extant_status=EligibilityStatus.PASS,
        storage_value=None,
        load_artifacts=False,
    )
    with pytest.raises(_StopAfterAssessmentResult):
        create_or_refresh_assessment_run(
            session=storage_session,
            site_id=site.id,
            scenario_id=scenario.id,
            as_of_date=date(2026, 4, 1),
            requested_by="pytest",
            storage=None,
        )
    assert storage_capture["status"] == "STORAGE_UNAVAILABLE"

    abstain_session, abstain_capture = _patch_common(
        extant_status=EligibilityStatus.ABSTAIN,
        storage_value=object(),
        load_artifacts=False,
    )
    with pytest.raises(_StopAfterAssessmentResult):
        create_or_refresh_assessment_run(
            session=abstain_session,
            site_id=site.id,
            scenario_id=scenario.id,
            as_of_date=date(2026, 4, 1),
            requested_by="pytest",
            storage=object(),
        )
    assert abstain_capture["status"] == "ABSTAIN"


def test_assessment_run_falls_through_without_hidden_score(monkeypatch):
    site = _make_site(
        site_id=19,
        geom_hash="assessment-site-hash",
        geometry_revisions=[_make_revision(revision_id=191, geom_hash="assessment-site-hash")],
    )
    scenario = _make_scenario(
        scenario_id=192,
        site=site,
        status=ScenarioStatus.ANALYST_CONFIRMED,
        source=ScenarioSource.ANALYST,
        geom_hash="assessment-site-hash",
        template_key="resi_5_9_full",
        proposal_form=ProposalForm.REDEVELOPMENT,
        units_assumed=6,
        route_assumed="FULL",
    )
    site.scenarios = [scenario]
    fake_feature = SimpleNamespace(
        feature_version=FEATURE_VERSION,
        feature_hash="feature-hash",
        feature_json={"values": {"site_area_sqm": 120.0}},
        coverage_json={"source_coverage": [{"coverage_status": "COMPLETE"}]},
    )
    fake_comparables = SimpleNamespace(
        comparable_case_set=SimpleNamespace(strategy="stub"),
        approved_members=[],
        refused_members=[],
        source_snapshot_ids=[],
        raw_asset_ids=[],
    )
    fake_release = SimpleNamespace(id=_uuid(193), model_artifact_hash="model-hash")
    fake_session = _FakeSession(rows_by_entity={AssessmentRun: []})
    monkeypatch.setattr(service_mod, "_load_scenario", lambda **kwargs: scenario)
    monkeypatch.setattr(service_mod, "rebuild_historical_case_labels", lambda **kwargs: None)
    monkeypatch.setattr(service_mod, "build_feature_snapshot", lambda **kwargs: fake_feature)
    monkeypatch.setattr(service_mod, "_upsert_feature_snapshot", lambda **kwargs: fake_feature)
    monkeypatch.setattr(
        service_mod,
        "evaluate_site_extant_permission",
        lambda **kwargs: ExtantPermissionRead.model_construct(
            status=ExtantPermissionStatus.NO_ACTIVE_PERMISSION_FOUND,
            eligibility_status=EligibilityStatus.PASS,
            manual_review_required=False,
            summary="PASS",
            reasons=[],
            coverage_gaps=[],
            matched_records=[],
        ),
    )
    monkeypatch.setattr(
        service_mod,
        "get_borough_baseline_pack",
        lambda **kwargs: SimpleNamespace(
            status=BaselinePackStatus.SIGNED_OFF,
            freshness_status=SourceFreshnessStatus.FRESH,
        ),
    )
    monkeypatch.setattr(
        service_mod,
        "assemble_site_evidence",
        lambda **kwargs: _empty_evidence_pack(),
    )
    monkeypatch.setattr(
        service_mod,
        "assemble_scenario_evidence",
        lambda **kwargs: _empty_evidence_pack(),
    )
    monkeypatch.setattr(
        service_mod,
        "build_comparable_case_set",
        lambda **kwargs: fake_comparables,
    )
    monkeypatch.setattr(
        service_mod,
        "resolve_active_release",
        lambda **kwargs: (fake_release, "scope-key"),
    )
    monkeypatch.setattr(
        service_mod,
        "load_release_artifact_json",
        lambda *, storage, release, artifact: (
            {"artifact": artifact} if artifact != "validation" else None
        ),
    )
    monkeypatch.setattr(
        service_mod,
        "score_frozen_assessment",
        lambda **kwargs: pytest.fail("score_frozen_assessment should not be called"),
    )
    captured: dict[str, object] = {}

    def _stop_after_result(**kwargs):
        captured["status"] = kwargs["score_execution_status"]
        raise _StopAfterAssessmentResult

    monkeypatch.setattr(service_mod, "_upsert_assessment_result", _stop_after_result)
    monkeypatch.setattr(service_mod, "_persist_evidence_items", lambda **kwargs: None)
    monkeypatch.setattr(service_mod, "_stable_result_payload", lambda **kwargs: {})
    monkeypatch.setattr(
        service_mod,
        "_upsert_prediction_ledger",
        lambda **kwargs: SimpleNamespace(),
    )
    monkeypatch.setattr(
        service_mod,
        "build_or_refresh_valuation_for_assessment",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(service_mod, "_assessment_load_options", lambda: ())

    with pytest.raises(_StopAfterAssessmentResult):
        create_or_refresh_assessment_run(
            session=fake_session,
            site_id=site.id,
            scenario_id=scenario.id,
            as_of_date=date(2026, 4, 1),
            requested_by="pytest",
            storage=object(),
        )

    assert captured["status"] == "NOT_IMPLEMENTED"


def test_verify_assessment_replay_enters_scoring_branch(monkeypatch):
    feature_snapshot = SimpleNamespace(
        feature_hash="feature-hash",
        feature_json={"values": {"site_area_sqm": 120.0}},
        coverage_json={"source_coverage": [{"coverage_status": "COMPLETE"}]},
    )
    result = SimpleNamespace(
        model_release_id=_uuid(200),
        release_scope_key="scope-key",
        estimate_status=EstimateStatus.ESTIMATE_AVAILABLE,
        eligibility_status=EligibilityStatus.PASS,
        review_status=ReviewStatus.NOT_REQUIRED,
        approval_probability_raw=0.73,
        approval_probability_display="73%",
        estimate_quality=EstimateQuality.MEDIUM,
        source_coverage_quality="HIGH",
        geometry_quality="HIGH",
        support_quality="COMPARABLES_PRESENT",
        scenario_quality="HIGH",
        ood_quality="IN_DISTRIBUTION",
        ood_status="IN_DISTRIBUTION",
        manual_review_required=False,
        result_json={
            "explanation": {"why": "ok"},
            "support_summary": {"support": "ok"},
            "validation_summary": {"validation": "ok"},
        },
    )
    comparable_case_set = SimpleNamespace(
        strategy="stub",
        members=[
            SimpleNamespace(
                planning_application_id=_uuid(201),
                similarity_score=13.0,
                rank=1,
                fallback_path="same_borough_same_template",
                match_json={"match": "approved"},
                outcome=ComparableOutcome.APPROVED,
            ),
            SimpleNamespace(
                planning_application_id=_uuid(202),
                similarity_score=11.0,
                rank=1,
                fallback_path="london_same_template",
                match_json={"match": "refused"},
                outcome=ComparableOutcome.REFUSED,
            ),
        ],
    )
    assessment_run = SimpleNamespace(
        id=_uuid(203),
        site_id=_uuid(204),
        scenario_id=_uuid(205),
        as_of_date=date(2026, 4, 1),
        feature_snapshot=feature_snapshot,
        result=result,
        prediction_ledger=SimpleNamespace(
            site_geom_hash="site-hash",
            result_payload_hash="payload-hash",
        ),
        site=SimpleNamespace(id=_uuid(204), geom_hash="site-hash", manual_review_required=False),
        scenario=SimpleNamespace(
            id=_uuid(205),
            red_line_geom_hash="site-hash",
            template_key="resi_5_9_full",
            template_version="v1",
            proposal_form=ProposalForm.REDEVELOPMENT,
            units_assumed=6,
            route_assumed="FULL",
            net_developable_area_pct=0.7,
            manual_review_required=False,
        ),
        evidence_items=[],
        comparable_case_set=comparable_case_set,
        valuation_runs=[],
    )
    fake_release = SimpleNamespace(id=result.model_release_id)
    monkeypatch.setattr(
        service_mod,
        "load_release_artifact_json",
        lambda *, storage, release, artifact: {"artifact": artifact},
    )
    monkeypatch.setattr(
        service_mod,
        "score_frozen_assessment",
        lambda **kwargs: {
            "approval_probability_raw": 0.73,
            "approval_probability_display": "73%",
            "estimate_quality": "MEDIUM",
            "source_coverage_quality": "HIGH",
            "geometry_quality": "HIGH",
            "support_quality": "COMPARABLES_PRESENT",
            "scenario_quality": "HIGH",
            "ood_quality": "IN_DISTRIBUTION",
            "ood_status": "IN_DISTRIBUTION",
            "manual_review_required": False,
            "support_summary": {"support": "ok"},
            "validation_summary": {"validation": "ok"},
            "explanation": {"why": "ok"},
        },
    )
    monkeypatch.setattr(service_mod, "frozen_valuation_run", lambda *_args, **_kwargs: None)
    payload_capture: dict[str, object] = {}

    def _stop_after_payload(**kwargs):
        payload_capture.update(kwargs)
        raise _StopAfterReplayPayload

    monkeypatch.setattr(service_mod, "_build_stable_result_payload", _stop_after_payload)
    fake_session = _FakeSession(get_map={(ModelRelease, fake_release.id): fake_release})

    with pytest.raises(_StopAfterReplayPayload):
        verify_assessment_replay(
            session=fake_session,
            assessment_run=assessment_run,
            storage=object(),
        )

    assert payload_capture["site_id"] == assessment_run.site_id
    assert payload_capture["scenario_id"] == assessment_run.scenario_id
    assert payload_capture["note_text"]

    payload_capture_missing_validation: dict[str, object] = {}

    def _stop_after_payload_missing_validation(**kwargs):
        payload_capture_missing_validation.update(kwargs)
        raise _StopAfterReplayPayload

    monkeypatch.setattr(
        service_mod,
        "load_release_artifact_json",
        lambda *, storage, release, artifact: {"artifact": artifact}
        if artifact == "model"
        else None,
    )
    monkeypatch.setattr(
        service_mod,
        "score_frozen_assessment",
        lambda **kwargs: pytest.fail("score_frozen_assessment should not be called"),
    )
    monkeypatch.setattr(
        service_mod,
        "_build_stable_result_payload",
        _stop_after_payload_missing_validation,
    )

    with pytest.raises(_StopAfterReplayPayload):
        verify_assessment_replay(
            session=fake_session,
            assessment_run=assessment_run,
            storage=object(),
        )

    assert payload_capture_missing_validation["site_id"] == assessment_run.site_id
