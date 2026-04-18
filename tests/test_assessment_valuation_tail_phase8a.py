from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from landintel.assessments import comparables as comparable_service
from landintel.assessments import service as assessment_service
from landintel.domain.enums import (
    AssessmentRunState,
    ComparableOutcome,
    EligibilityStatus,
    EstimateQuality,
    EstimateStatus,
    EvidenceImportance,
    EvidencePolarity,
    GoldSetReviewStatus,
    HistoricalLabelClass,
    PriceBasisType,
    ProposalForm,
    ReviewStatus,
    ScenarioStatus,
    SourceClass,
    ValuationQuality,
    VerifiedStatus,
)
from landintel.domain.models import AssessmentResult, SiteScenario
from landintel.domain.schemas import EvidenceItemRead, EvidencePackRead
from landintel.valuation import service as valuation_service

from tests.test_assessments_phase5a import _build_confirmed_camden_scenario


class _QueryResult:
    def __init__(self, *, rows=None, scalar=None):
        self._rows = list(rows or [])
        self._scalar = scalar

    def scalars(self):
        return self

    def all(self):
        return self._rows

    def scalar_one_or_none(self):
        return self._scalar


class _QueuedSession:
    def __init__(self, *responses, get_result=None):
        self._responses = list(responses)
        self.added = []
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


def _fixed_uuid(seed: int) -> UUID:
    return UUID(f"00000000-0000-0000-0000-{seed:012d}")


def _enum_member(enum_cls, *preferred: str):
    members = list(enum_cls)
    lowered = {member.name.lower(): member for member in members}
    for name in preferred:
        if name.lower() in lowered:
            return lowered[name.lower()]
    return members[0]


def _evidence_pack() -> EvidencePackRead:
    return EvidencePackRead(
        for_=[],
        against=[],
        unknown=[
            EvidenceItemRead(
                polarity=EvidencePolarity.UNKNOWN,
                claim_text="Unknown evidence",
                topic="fixture",
                importance=EvidenceImportance.MEDIUM,
                source_class=SourceClass.ANALYST_DERIVED,
                source_label="Fixture",
                source_url=None,
                source_snapshot_id=None,
                raw_asset_id=None,
                excerpt_text=None,
                verified_status=VerifiedStatus.VERIFIED,
            )
        ],
    )


def test_create_or_refresh_assessment_run_validation_branches(
    client,
    drain_jobs,
    db_session,
    seed_listing_sources,
    seed_planning_data,
) -> None:
    del seed_listing_sources
    del seed_planning_data
    _, confirmed = _build_confirmed_camden_scenario(client, drain_jobs)
    scenario = db_session.get(SiteScenario, UUID(confirmed["id"]))
    assert scenario is not None
    site = scenario.site

    original_status = scenario.status
    original_is_current = scenario.is_current
    original_geom_hash = scenario.red_line_geom_hash

    with pytest.raises(assessment_service.AssessmentBuildError, match="does not belong"):
        assessment_service.create_or_refresh_assessment_run(
            session=db_session,
            site_id=uuid4(),
            scenario_id=scenario.id,
            as_of_date=date.today(),
            requested_by="pytest",
        )

    scenario.status = ScenarioStatus.SUGGESTED
    db_session.flush()
    with pytest.raises(assessment_service.AssessmentBuildError, match="confirmed scenario"):
        assessment_service.create_or_refresh_assessment_run(
            session=db_session,
            site_id=site.id,
            scenario_id=scenario.id,
            as_of_date=date.today(),
            requested_by="pytest",
        )

    scenario.status = original_status
    scenario.is_current = False
    db_session.flush()
    with pytest.raises(assessment_service.AssessmentBuildError, match="superseded"):
        assessment_service.create_or_refresh_assessment_run(
            session=db_session,
            site_id=site.id,
            scenario_id=scenario.id,
            as_of_date=date.today(),
            requested_by="pytest",
        )

    scenario.is_current = original_is_current
    scenario.red_line_geom_hash = "stale-geometry"
    db_session.flush()
    with pytest.raises(assessment_service.AssessmentBuildError, match="stale"):
        assessment_service.create_or_refresh_assessment_run(
            session=db_session,
            site_id=site.id,
            scenario_id=scenario.id,
            as_of_date=date.today(),
            requested_by="pytest",
        )

    scenario.red_line_geom_hash = original_geom_hash
    db_session.flush()
    with pytest.raises(assessment_service.AssessmentBuildError, match="future"):
        assessment_service.create_or_refresh_assessment_run(
            session=db_session,
            site_id=site.id,
            scenario_id=scenario.id,
            as_of_date=date.today() + timedelta(days=1),
            requested_by="pytest",
        )


def test_assessment_service_guard_and_helper_branches() -> None:
    missing_session = _QueuedSession(_QueryResult(scalar=None))
    with pytest.raises(assessment_service.AssessmentBuildError, match="not found"):
        assessment_service.build_assessment_artifacts_for_run(
            session=missing_session,
            assessment_run_id=_fixed_uuid(1),
            requested_by="pytest",
        )

    ready_run = SimpleNamespace(state=AssessmentRunState.READY)
    ready_session = _QueuedSession(_QueryResult(scalar=ready_run))
    assert (
        assessment_service.build_assessment_artifacts_for_run(
            session=ready_session,
            assessment_run_id=_fixed_uuid(2),
            requested_by="pytest",
        )
        is ready_run
    )

    with pytest.raises(assessment_service.AssessmentBuildError, match="incomplete"):
        assessment_service.verify_assessment_replay(
            session=_QueuedSession(),
            assessment_run=SimpleNamespace(
                feature_snapshot=None,
                result=None,
                prediction_ledger=None,
            ),
        )

    replay_run = SimpleNamespace(
        id=_fixed_uuid(3),
        feature_snapshot=SimpleNamespace(
            feature_json={"values": {}},
            feature_hash="feature-hash",
            coverage_json={},
            feature_version="v1",
        ),
        result=SimpleNamespace(model_release_id=_fixed_uuid(4)),
        prediction_ledger=SimpleNamespace(result_payload_hash="payload-hash"),
        evidence_items=[],
        comparable_case_set=None,
        valuation_runs=[],
        site=SimpleNamespace(),
        scenario=SimpleNamespace(red_line_geom_hash="geom-hash"),
    )
    with pytest.raises(assessment_service.AssessmentBuildError, match="could not be loaded"):
        assessment_service.verify_assessment_replay(
            session=_QueuedSession(get_result=None),
            assessment_run=replay_run,
            storage=object(),
        )

    evidence = assessment_service._build_assessment_evidence(
        scenario_evidence=_evidence_pack(),
        as_of_date=date(2026, 4, 18),
    )
    assert evidence.unknown[-1].claim_text == assessment_service.PRE_SCORE_NOTE

    run = SimpleNamespace(id=_fixed_uuid(5), evidence_items=[])
    persist_session = _QueuedSession()
    assessment_service._persist_evidence_items(
        session=persist_session,
        run=run,
        evidence=evidence,
    )
    assert len(run.evidence_items) == 2

    no_case_payload = assessment_service._stable_comparable_payload(
        SimpleNamespace(comparable_case_set=None)
    )
    assert no_case_payload == {"strategy": None, "approved": [], "refused": []}

    members = [
        SimpleNamespace(
            planning_application_id=_fixed_uuid(7),
            similarity_score=0.4,
            rank=2,
            fallback_path="later",
            match_json={"kind": "late"},
            outcome=ComparableOutcome.REFUSED,
        ),
        SimpleNamespace(
            planning_application_id=_fixed_uuid(6),
            similarity_score=0.9,
            rank=1,
            fallback_path="first",
            match_json={"kind": "first"},
            outcome=ComparableOutcome.APPROVED,
        ),
    ]
    comparable_payload = assessment_service._stable_comparable_payload(
        SimpleNamespace(comparable_case_set=SimpleNamespace(strategy="fixture", members=members))
    )
    assert comparable_payload["approved"][0]["planning_application_id"] == str(_fixed_uuid(6))
    assert comparable_payload["refused"][0]["planning_application_id"] == str(_fixed_uuid(7))

    assert assessment_service._serialize_valuation_payload(None) is None
    assert assessment_service._serialize_valuation_payload(SimpleNamespace(result=None)) is None

    valuation_payload = assessment_service._serialize_valuation_payload(
        SimpleNamespace(
            id=_fixed_uuid(8),
            valuation_assumption_set_id=_fixed_uuid(9),
            valuation_assumption_set=SimpleNamespace(version="v1"),
            result=SimpleNamespace(
                post_permission_value_low=90.0,
                post_permission_value_mid=100.0,
                post_permission_value_high=110.0,
                uplift_low=10.0,
                uplift_mid=20.0,
                uplift_high=30.0,
                expected_uplift_mid=12.0,
                valuation_quality=ValuationQuality.MEDIUM,
                manual_review_required=False,
                basis_json={"basis_price_gbp": 80.0},
                sense_check_json={"divergence_material": False},
                result_json={"quality_reasons": []},
                payload_hash="valuation-hash",
            ),
        )
    )
    assert valuation_payload is not None
    assert valuation_payload["valuation_assumption_version"] == "v1"

    assert (
        assessment_service._frozen_red_line_geom_hash(
            assessment_run=SimpleNamespace(
                prediction_ledger=SimpleNamespace(site_geom_hash="ledger-geom"),
                scenario=SimpleNamespace(red_line_geom_hash="scenario-geom"),
            )
        )
        == "ledger-geom"
    )
    assert (
        assessment_service._frozen_red_line_geom_hash(
            assessment_run=SimpleNamespace(
                prediction_ledger=None,
                scenario=SimpleNamespace(red_line_geom_hash="scenario-geom"),
            )
        )
        == "scenario-geom"
    )

    ledger = SimpleNamespace(
        replay_verification_status=None,
        replay_verified_at=None,
        replay_verification_note=None,
    )
    run_with_ledger = SimpleNamespace(prediction_ledger=ledger)
    assessment_service._record_replay_verification(
        assessment_run=run_with_ledger,
        check={
            "replay_passed": True,
            "feature_hash_matches": True,
            "payload_hash_matches": True,
            "scored_fields_match": True,
        },
    )
    assert ledger.replay_verification_status == "VERIFIED"
    assessment_service._record_replay_verification(
        assessment_run=run_with_ledger,
        check={
            "replay_passed": False,
            "feature_hash_matches": False,
            "payload_hash_matches": True,
            "scored_fields_match": False,
        },
    )
    assert ledger.replay_verification_status == "FAILED"
    assert "feature_hash_matches" in ledger.replay_verification_note

    hidden_note = assessment_service._note_for_result(
        SimpleNamespace(approval_probability_raw=0.51, result_json={})
    )
    assert hidden_note == assessment_service.HIDDEN_SCORE_NOTE
    assert (
        assessment_service._note_for_result(
            SimpleNamespace(
                approval_probability_raw=None,
                result_json={"note": "fixture-note"},
            )
        )
        == "fixture-note"
    )

    stable_payload = assessment_service._build_stable_result_payload(
        site_id=_fixed_uuid(10),
        scenario_id=_fixed_uuid(11),
        as_of_date=date(2026, 4, 18),
        red_line_geom_hash="geom-hash",
        feature_snapshot=SimpleNamespace(feature_hash="feature-hash", feature_version="v1"),
        result=SimpleNamespace(
            estimate_status=EstimateStatus.NONE,
            eligibility_status=EligibilityStatus.PASS,
            review_status=ReviewStatus.REQUIRED,
            manual_review_required=True,
            approval_probability_raw=None,
            approval_probability_display=None,
            estimate_quality=None,
            source_coverage_quality="LOW",
            geometry_quality="HIGH",
            support_quality="SPARSE",
            scenario_quality="MEDIUM",
            ood_quality=None,
            ood_status=None,
            model_release_id=None,
            release_scope_key=None,
            result_json={"original": True},
        ),
        valuation_payload=None,
        evidence=evidence,
        comparables={"approved": [], "refused": [], "strategy": "fixture"},
        note_text="fixture note",
        result_json_override={"overridden": True},
    )
    assert stable_payload["result_json"] == {"overridden": True}

    pre_score_run = SimpleNamespace(
        id=_fixed_uuid(12),
        site=SimpleNamespace(
            manual_review_required=False,
            geom_confidence=SimpleNamespace(value="HIGH"),
        ),
        result=None,
    )
    pre_score_session = _QueuedSession()
    pre_score_result = assessment_service._upsert_assessment_result(
        session=pre_score_session,
        run=pre_score_run,
        scenario=SimpleNamespace(manual_review_required=False),
        extant_permission=SimpleNamespace(
            eligibility_status=EligibilityStatus.PASS,
            manual_review_required=False,
        ),
        comparable_count=0,
        coverage_json={"source_coverage": []},
        model_release=None,
        release_scope_key="scope",
        scored_result=None,
        score_execution_status="NO_ACTIVE_HIDDEN_RELEASE",
        note_text="fixture note",
    )
    assert isinstance(pre_score_result, AssessmentResult)
    assert pre_score_result.estimate_status == EstimateStatus.NONE
    assert pre_score_result.published_at is None

    scored_run = SimpleNamespace(
        id=_fixed_uuid(13),
        site=SimpleNamespace(
            manual_review_required=False,
            geom_confidence=SimpleNamespace(value="HIGH"),
        ),
        result=None,
    )
    scored_result = assessment_service._upsert_assessment_result(
        session=_QueuedSession(),
        run=scored_run,
        scenario=SimpleNamespace(manual_review_required=False),
        extant_permission=SimpleNamespace(
            eligibility_status=EligibilityStatus.PASS,
            manual_review_required=False,
        ),
        comparable_count=2,
        coverage_json={"source_coverage": []},
        model_release=SimpleNamespace(id=_fixed_uuid(14)),
        release_scope_key="scope",
        scored_result={
            "manual_review_required": False,
            "approval_probability_raw": 0.61,
            "approval_probability_display": "61%",
            "estimate_quality": EstimateQuality.MEDIUM.value,
            "source_coverage_quality": "HIGH",
            "geometry_quality": "HIGH",
            "support_quality": "COMPARABLES_PRESENT",
            "scenario_quality": "HIGH",
            "ood_quality": "LOW",
            "ood_status": "IN_SCOPE",
            "support_summary": {"same_borough_support_count": 2},
            "validation_summary": {"kind": "fixture"},
            "explanation": {"drivers": ["policy"]},
        },
        score_execution_status="HIDDEN_ESTIMATE_AVAILABLE",
        note_text="fixture hidden note",
    )
    assert scored_result.model_release_id == _fixed_uuid(14)
    assert scored_result.approval_probability_raw == 0.61


def test_valuation_helper_branches_and_ready_short_circuit() -> None:
    with pytest.raises(valuation_service.ValuationBuildError, match="frozen features"):
        valuation_service.build_or_refresh_valuation_for_assessment(
            session=_QueuedSession(),
            assessment_run=SimpleNamespace(feature_snapshot=None, result=None),
            requested_by="pytest",
        )

    assumption_set = SimpleNamespace(
        id=_fixed_uuid(20),
        version="v1",
        cost_json={},
        policy_burden_json={},
        discount_json={},
    )
    ready_existing = SimpleNamespace(
        valuation_assumption_set_id=assumption_set.id,
        state=SimpleNamespace(value="READY"),
        result=SimpleNamespace(),
    )
    assessment_run = SimpleNamespace(
        id=_fixed_uuid(21),
        scenario_id=_fixed_uuid(22),
        as_of_date=date(2026, 4, 18),
        feature_snapshot=SimpleNamespace(
            feature_hash="feature-hash",
            feature_json={
                "values": {
                    "current_price_gbp": 100000,
                    "current_price_basis_type": PriceBasisType.GUIDE_PRICE.value,
                }
            },
        ),
        result=SimpleNamespace(approval_probability_raw=0.5),
        valuation_runs=[ready_existing],
        prediction_ledger=None,
        scenario=SimpleNamespace(red_line_geom_hash="scenario-geom", template_key="resi"),
        site=SimpleNamespace(borough_id="camden"),
    )
    assert (
        valuation_service.build_or_refresh_valuation_for_assessment_with_assumption_set(
            session=_QueuedSession(),
            assessment_run=assessment_run,
            valuation_assumption_set=assumption_set,
            requested_by="pytest",
        )
        is ready_existing
    )

    older_run = SimpleNamespace(
        id=_fixed_uuid(23), created_at=datetime(2026, 4, 18, 10, tzinfo=UTC)
    )
    newer_run = SimpleNamespace(
        id=_fixed_uuid(24), created_at=datetime(2026, 4, 18, 11, tzinfo=UTC)
    )
    assert (
        valuation_service.latest_valuation_run(
            SimpleNamespace(valuation_runs=[older_run, newer_run])
        )
        is newer_run
    )
    assert valuation_service.latest_valuation_run(SimpleNamespace(valuation_runs=[])) is None

    fallback_run = SimpleNamespace(id=_fixed_uuid(25))
    assert (
        valuation_service.frozen_valuation_run(
            SimpleNamespace(
                prediction_ledger=SimpleNamespace(
                    valuation_run_id=fallback_run.id,
                    valuation_run=None,
                ),
                valuation_runs=[fallback_run],
            )
        )
        is fallback_run
    )
    ledger_run = SimpleNamespace(id=_fixed_uuid(26))
    assert (
        valuation_service.frozen_valuation_run(
            SimpleNamespace(
                prediction_ledger=SimpleNamespace(
                    valuation_run_id=_fixed_uuid(27),
                    valuation_run=ledger_run,
                ),
                valuation_runs=[],
            )
        )
        is ledger_run
    )
    assert (
        valuation_service.frozen_valuation_run(
            SimpleNamespace(prediction_ledger=None, valuation_runs=[])
        )
        is None
    )

    existing_run = SimpleNamespace(valuation_assumption_set_id=assumption_set.id)
    assert (
        valuation_service._get_or_create_run(
            session=_QueuedSession(),
            assessment_run=SimpleNamespace(id=_fixed_uuid(28), valuation_runs=[existing_run]),
            assumption_set=assumption_set,
            input_hash="hash",
        )
        is existing_run
    )

    create_session = _QueuedSession()
    created = valuation_service._get_or_create_run(
        session=create_session,
        assessment_run=SimpleNamespace(id=_fixed_uuid(29), valuation_runs=[]),
        assumption_set=assumption_set,
        input_hash="hash",
    )
    assert created.assessment_run_id == _fixed_uuid(29)
    assert create_session.flushed == 1

    with_ledger_hash = valuation_service._valuation_input_hash(
        assessment_run=SimpleNamespace(
            id=_fixed_uuid(30),
            scenario_id=_fixed_uuid(31),
            feature_snapshot=SimpleNamespace(
                feature_hash="feature-hash",
                feature_json={
                    "values": {
                        "current_price_gbp": 100000,
                        "current_price_basis_type": PriceBasisType.GUIDE_PRICE.value,
                    }
                },
            ),
            prediction_ledger=SimpleNamespace(site_geom_hash="ledger-geom"),
            scenario=SimpleNamespace(red_line_geom_hash="scenario-geom"),
            result=SimpleNamespace(approval_probability_raw=0.3),
        ),
        assumption_set=assumption_set,
    )
    without_ledger_hash = valuation_service._valuation_input_hash(
        assessment_run=SimpleNamespace(
            id=_fixed_uuid(30),
            scenario_id=_fixed_uuid(31),
            feature_snapshot=SimpleNamespace(
                feature_hash="feature-hash",
                feature_json={
                    "values": {
                        "current_price_gbp": 100000,
                        "current_price_basis_type": PriceBasisType.GUIDE_PRICE.value,
                    }
                },
            ),
            prediction_ledger=None,
            scenario=SimpleNamespace(red_line_geom_hash="scenario-geom"),
            result=SimpleNamespace(approval_probability_raw=0.3),
        ),
        assumption_set=assumption_set,
    )
    assert with_ledger_hash != without_ledger_hash

    assert valuation_service._frozen_basis_inputs(
        SimpleNamespace(
            feature_snapshot=SimpleNamespace(
                feature_json={
                    "values": {
                        "current_price_gbp": "bad",
                        "current_price_basis_type": "bad-type",
                    }
                }
            )
        )
    ) == (None, PriceBasisType.UNKNOWN)

    assert valuation_service._frozen_basis_inputs(
        SimpleNamespace(
            feature_snapshot=SimpleNamespace(
                feature_json={
                    "values": {
                        "current_price_gbp": 125000,
                        "current_price_basis_type": PriceBasisType.ASKING_PRICE.value,
                    }
                }
            )
        )
    ) == (125000, PriceBasisType.ASKING_PRICE)

    frozen_context = valuation_service._frozen_assessment_context(
        SimpleNamespace(
            feature_snapshot=SimpleNamespace(feature_json={"values": {}}),
            site=SimpleNamespace(borough_id="camden"),
            scenario=SimpleNamespace(
                template_key="resi_5_9_full",
                proposal_form=ProposalForm.INFILL,
                manual_review_required=True,
                stale_reason="geometry-changed",
            ),
        )
    )
    assert frozen_context["borough_id"] == "camden"
    assert frozen_context["scenario_template_key"] == "resi_5_9_full"
    assert frozen_context["scenario_manual_review_required"] is True
    assert frozen_context["scenario_is_stale"] is True

    explicit_context = valuation_service._frozen_assessment_context(
        SimpleNamespace(
            feature_snapshot=SimpleNamespace(
                feature_json={
                    "values": {
                        "borough_id": "hackney",
                        "scenario_template_key": "custom-template",
                        "scenario_proposal_form": ProposalForm.BACKLAND,
                        "scenario_manual_review_required": False,
                        "scenario_is_stale": False,
                    }
                }
            ),
            site=SimpleNamespace(borough_id="camden"),
            scenario=SimpleNamespace(
                template_key="resi_5_9_full",
                proposal_form=ProposalForm.INFILL,
                manual_review_required=True,
                stale_reason="geometry-changed",
            ),
        )
    )
    assert explicit_context["borough_id"] == "hackney"
    assert explicit_context["scenario_template_key"] == "custom-template"
    assert explicit_context["scenario_proposal_form"] == ProposalForm.BACKLAND

    frozen_scenario = valuation_service._frozen_scenario_for_valuation(
        SimpleNamespace(
            feature_snapshot=SimpleNamespace(feature_json={"values": {}}),
            scenario=SimpleNamespace(
                template_key="resi_10_49_outline",
                units_assumed=12,
                housing_mix_assumed_json={"market": 12},
            ),
        )
    )
    assert frozen_scenario.template_key == "resi_10_49_outline"
    assert frozen_scenario.units_assumed == 12

    explicit_frozen_scenario = valuation_service._frozen_scenario_for_valuation(
        SimpleNamespace(
            feature_snapshot=SimpleNamespace(
                feature_json={
                    "values": {
                        "scenario_template_key": "explicit-template",
                        "scenario_units_assumed": 20,
                        "scenario_housing_mix_assumed_json": {"affordable": 5},
                    }
                }
            ),
            scenario=SimpleNamespace(
                template_key="ignored",
                units_assumed=1,
                housing_mix_assumed_json={},
            ),
        )
    )
    assert explicit_frozen_scenario.template_key == "explicit-template"
    assert explicit_frozen_scenario.units_assumed == 20
    assert explicit_frozen_scenario.housing_mix_assumed_json == {"affordable": 5}


def test_comparables_selection_and_filtering_branches() -> None:
    assert (
        comparable_service._designation_similarity(
            left="urban",
            right="urban",
            left_profile={},
            right_profile={},
        )
        == 1.0
    )
    assert (
        comparable_service._designation_similarity(
            left="",
            right="",
            left_profile={},
            right_profile={},
        )
        == 0.0
    )
    overlap = comparable_service._designation_similarity(
        left="",
        right="",
        left_profile={"brownfield": True, "zones": ["a", "b"]},
        right_profile={"brownfield": True, "zones": ["b"]},
    )
    assert overlap == pytest.approx(2 / 3)

    site = SimpleNamespace(
        borough_id="camden",
        planning_links=[SimpleNamespace(planning_application_id=_fixed_uuid(40))],
    )
    scenario = SimpleNamespace(
        proposal_form=ProposalForm.INFILL,
        units_assumed=10,
        template_key="resi_5_9_full",
    )
    label_for_json = SimpleNamespace(
        borough_id="camden",
        proposal_form=ProposalForm.INFILL,
        template_key="resi_5_9_full",
        units_proposed=None,
        site_area_sqm=None,
        archetype_key=None,
        designation_profile_json={},
        first_substantive_decision_date=None,
        valid_date=None,
    )
    match_json = comparable_service._match_json(
        site=site,
        scenario=scenario,
        site_area_sqm=100.0,
        site_archetype="urban",
        site_designation_profile={},
        label=label_for_json,
        as_of_date=date(2026, 4, 18),
        similarity_score=0.5,
    )
    assert match_json["units_delta"] is None
    assert match_json["site_area_delta_sqm"] is None
    assert match_json["decision_date"] is None

    zero_area_score = comparable_service._similarity_score(
        site=site,
        scenario=scenario,
        site_area_sqm=100.0,
        site_archetype="urban",
        site_designation_profile={"brownfield": True},
        label=SimpleNamespace(
            units_proposed=10,
            site_area_sqm=0,
            borough_id="southwark",
            proposal_form=None,
            archetype_key="other",
            designation_profile_json={},
            first_substantive_decision_date=None,
            valid_date=None,
        ),
        as_of_date=date(2026, 4, 18),
    )
    assert 0.0 <= zero_area_score <= 100.0

    positive_status = _enum_member(
        GoldSetReviewStatus,
        "confirmed",
        "approved",
        "current",
        "completed",
    )
    rows = [
        SimpleNamespace(
            id=_fixed_uuid(41),
            planning_application_id=_fixed_uuid(40),
            planning_application=SimpleNamespace(id=_fixed_uuid(40)),
            template_key="resi_5_9_full",
            valid_date=date(2026, 4, 1),
            first_substantive_decision_date=None,
            review_status=positive_status,
            label_class=HistoricalLabelClass.POSITIVE,
            borough_id="camden",
            proposal_form=ProposalForm.INFILL,
            units_proposed=10,
            site_area_sqm=100.0,
            archetype_key="urban",
            designation_profile_json={"brownfield": True},
            source_snapshot_ids_json=["s-linked"],
            raw_asset_ids_json=["a-linked"],
        ),
        SimpleNamespace(
            id=_fixed_uuid(42),
            planning_application_id=_fixed_uuid(42),
            planning_application=SimpleNamespace(id=_fixed_uuid(42)),
            template_key="other-template",
            valid_date=date(2026, 4, 1),
            first_substantive_decision_date=None,
            review_status=positive_status,
            label_class=HistoricalLabelClass.POSITIVE,
            borough_id="camden",
            proposal_form=ProposalForm.INFILL,
            units_proposed=10,
            site_area_sqm=100.0,
            archetype_key="urban",
            designation_profile_json={"brownfield": True},
            source_snapshot_ids_json=["s-other"],
            raw_asset_ids_json=["a-other"],
        ),
        SimpleNamespace(
            id=_fixed_uuid(43),
            planning_application_id=_fixed_uuid(43),
            planning_application=SimpleNamespace(id=_fixed_uuid(43)),
            template_key="resi_5_9_full",
            valid_date=date(2026, 4, 19),
            first_substantive_decision_date=None,
            review_status=positive_status,
            label_class=HistoricalLabelClass.POSITIVE,
            borough_id="camden",
            proposal_form=ProposalForm.INFILL,
            units_proposed=10,
            site_area_sqm=100.0,
            archetype_key="urban",
            designation_profile_json={"brownfield": True},
            source_snapshot_ids_json=["s-future"],
            raw_asset_ids_json=["a-future"],
        ),
        SimpleNamespace(
            id=_fixed_uuid(44),
            planning_application_id=_fixed_uuid(44),
            planning_application=SimpleNamespace(id=_fixed_uuid(44)),
            template_key="resi_5_9_full",
            valid_date=date(2026, 4, 1),
            first_substantive_decision_date=None,
            review_status=GoldSetReviewStatus.EXCLUDED,
            label_class=HistoricalLabelClass.POSITIVE,
            borough_id="camden",
            proposal_form=ProposalForm.INFILL,
            units_proposed=10,
            site_area_sqm=100.0,
            archetype_key="urban",
            designation_profile_json={"brownfield": True},
            source_snapshot_ids_json=["s-excluded"],
            raw_asset_ids_json=["a-excluded"],
        ),
        SimpleNamespace(
            id=_fixed_uuid(45),
            planning_application_id=_fixed_uuid(45),
            planning_application=SimpleNamespace(id=_fixed_uuid(45)),
            template_key="resi_5_9_full",
            valid_date=date(2026, 4, 1),
            first_substantive_decision_date=date(2026, 4, 2),
            review_status=positive_status,
            label_class=HistoricalLabelClass.POSITIVE,
            borough_id="camden",
            proposal_form=ProposalForm.INFILL,
            units_proposed=9,
            site_area_sqm=95.0,
            archetype_key="urban",
            designation_profile_json={"brownfield": True},
            source_snapshot_ids_json=["s-approved"],
            raw_asset_ids_json=["a-approved"],
        ),
        SimpleNamespace(
            id=_fixed_uuid(46),
            planning_application_id=_fixed_uuid(46),
            planning_application=SimpleNamespace(id=_fixed_uuid(46)),
            template_key="resi_5_9_full",
            valid_date=date(2026, 4, 1),
            first_substantive_decision_date=None,
            review_status=positive_status,
            label_class=HistoricalLabelClass.POSITIVE,
            borough_id="hackney",
            proposal_form=ProposalForm.INFILL,
            units_proposed=11,
            site_area_sqm=100.0,
            archetype_key="tower",
            designation_profile_json={"flood": ["2"]},
            source_snapshot_ids_json=["s-london"],
            raw_asset_ids_json=["a-london"],
        ),
        SimpleNamespace(
            id=_fixed_uuid(47),
            planning_application_id=_fixed_uuid(47),
            planning_application=SimpleNamespace(id=_fixed_uuid(47)),
            template_key="resi_5_9_full",
            valid_date=date(2026, 4, 1),
            first_substantive_decision_date=None,
            review_status=positive_status,
            label_class=HistoricalLabelClass.NEGATIVE,
            borough_id="brent",
            proposal_form=ProposalForm.BACKLAND,
            units_proposed=12,
            site_area_sqm=102.0,
            archetype_key="urban",
            designation_profile_json={"brownfield": True, "flood": ["2"]},
            source_snapshot_ids_json=["s-refused"],
            raw_asset_ids_json=["a-refused"],
        ),
    ]
    result = comparable_service.build_comparable_case_set(
        session=_QueuedSession(_QueryResult(rows=rows)),
        assessment_run=SimpleNamespace(id=_fixed_uuid(48), comparable_case_set=None),
        site=site,
        scenario=scenario,
        as_of_date=date(2026, 4, 18),
        feature_json={
            "values": {
                "site_area_sqm": 100.0,
                "designation_archetype_key": "urban",
            },
            "designation_profile": {"brownfield": True, "flood": ["2"]},
        },
    )
    assert result.comparable_case_set.approved_count == 2
    assert result.comparable_case_set.refused_count == 1
    assert result.comparable_case_set.same_borough_count == 1
    assert result.comparable_case_set.london_count == 1
    assert result.approved_members[0].fallback_path == "same_borough_same_template"
    assert result.approved_members[1].fallback_path == "london_same_template"
    assert result.refused_members[0].fallback_path == "archetype_same_template"
    assert result.source_snapshot_ids == ["s-approved", "s-london", "s-refused"]
    assert result.raw_asset_ids == ["a-approved", "a-london", "a-refused"]
