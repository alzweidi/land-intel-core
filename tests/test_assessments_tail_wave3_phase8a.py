from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest
from landintel.assessments import comparables as comparable_service
from landintel.assessments import service as assessment_service
from landintel.domain.enums import (
    AssessmentRunState,
    BaselinePackStatus,
    ComparableOutcome,
    EligibilityStatus,
    EstimateQuality,
    EstimateStatus,
    GoldSetReviewStatus,
    HistoricalLabelClass,
    ProposalForm,
    ReviewStatus,
    ScenarioStatus,
    ValuationQuality,
)
from landintel.domain.schemas import (
    AssessmentListResponse,
    AssessmentSummaryRead,
    EvidenceItemRead,
    EvidencePackRead,
)
from landintel.services import assessments_readback


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


def _fixed_uuid(seed: int) -> UUID:
    return UUID(f"00000000-0000-0000-0000-{seed:012d}")


def _summary_model(*, row_id: UUID) -> AssessmentSummaryRead:
    return AssessmentSummaryRead.model_construct(
        id=row_id,
        site_id=_fixed_uuid(101),
        scenario_id=_fixed_uuid(102),
        as_of_date=date(2026, 4, 18),
        state=AssessmentRunState.READY,
        idempotency_key="fixture-key",
        requested_by="pytest",
        started_at=datetime(2026, 4, 18, 9, 0, tzinfo=UTC),
        finished_at=datetime(2026, 4, 18, 9, 5, tzinfo=UTC),
        error_text=None,
        created_at=datetime(2026, 4, 18, 9, 0, tzinfo=UTC),
        updated_at=datetime(2026, 4, 18, 9, 5, tzinfo=UTC),
        estimate_status=EstimateStatus.NONE,
        eligibility_status=EligibilityStatus.PASS,
        review_status=ReviewStatus.REQUIRED,
        manual_review_required=False,
        site_summary=None,
        scenario_summary=None,
    )


def _label(
    *,
    row_id: UUID,
    planning_application_id: UUID,
    template_key: str,
    label_class: HistoricalLabelClass,
    borough_id: str | None = "camden",
    proposal_form: ProposalForm = ProposalForm.INFILL,
    units_proposed: int = 10,
    site_area_sqm: float = 120.0,
    valid_date: date | None = date(2026, 4, 1),
    first_decision_date: date | None = date(2026, 4, 2),
    review_status: GoldSetReviewStatus = GoldSetReviewStatus.CONFIRMED,
    archetype_key: str = "fixture-archetype",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=row_id,
        planning_application_id=planning_application_id,
        planning_application=SimpleNamespace(id=planning_application_id),
        template_key=template_key,
        valid_date=valid_date,
        first_substantive_decision_date=first_decision_date,
        review_status=review_status,
        label_class=label_class,
        borough_id=borough_id,
        proposal_form=proposal_form,
        units_proposed=units_proposed,
        site_area_sqm=site_area_sqm,
        archetype_key=archetype_key,
        designation_profile_json={"brownfield": True, "zones": ["a"]},
        source_snapshot_ids_json=[f"s-{row_id.hex[:4]}"],
        raw_asset_ids_json=[f"a-{row_id.hex[:4]}"],
    )


def test_assessment_service_scored_and_error_branches(monkeypatch) -> None:
    site = SimpleNamespace(
        id=_fixed_uuid(1),
        borough_id="camden",
        geom_hash="site-geom",
        geom_confidence=SimpleNamespace(value="HIGH"),
        manual_review_required=False,
    )
    scenario = SimpleNamespace(
        id=_fixed_uuid(2),
        site=site,
        status=ScenarioStatus.ANALYST_CONFIRMED,
        is_current=True,
        red_line_geom_hash="site-geom",
        template_key="resi_5_9_full",
        template_version="v1",
        proposal_form=ProposalForm.INFILL,
        units_assumed=10,
        manual_review_required=False,
        stale_reason=None,
        housing_mix_assumed_json={},
        site_geometry_revision_id=_fixed_uuid(3),
        geometry_revision=SimpleNamespace(id=_fixed_uuid(3), geom_hash="site-geom"),
        reviews=[],
    )
    feature_result = SimpleNamespace(
        feature_version="v1",
        feature_hash="feature-hash",
        feature_json={"sentinel": "feature"},
        coverage_json={"source_coverage": [], "source_snapshot_ids": [], "raw_asset_ids": []},
    )
    evidence = EvidencePackRead(
        for_=[],
        against=[],
        unknown=[
            EvidenceItemRead(
                polarity="UNKNOWN",
                claim_text="Fixture",
                topic="fixture",
                importance="HIGH",
                source_class="ANALYST_DERIVED",
                source_label="Fixture",
                source_url=None,
                source_snapshot_id=None,
                raw_asset_id=None,
                excerpt_text=None,
                verified_status="VERIFIED",
            )
        ],
    )
    comparable_result = SimpleNamespace(
        comparable_case_set=SimpleNamespace(
            id=_fixed_uuid(5),
            strategy="fixture",
            members=[],
            same_borough_count=0,
            london_count=0,
            approved_count=0,
            refused_count=0,
        ),
        approved_members=[],
        refused_members=[],
        source_snapshot_ids=["s-1"],
        raw_asset_ids=["a-1"],
    )
    scored_result = {
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
        "support_summary": {"same_borough_support_count": 1},
        "validation_summary": {"validation": "ok"},
        "explanation": {"drivers": ["fixture"]},
    }
    valuation_run = SimpleNamespace(id=_fixed_uuid(6))
    captured_result: list[object] = []
    captured_statuses: list[str] = []

    def _fake_upsert_assessment_result(
        *, run, scored_result=None, score_execution_status, **kwargs
    ):
        del kwargs
        captured_statuses.append(score_execution_status)
        result_obj = SimpleNamespace(
            estimate_status=EstimateStatus.ESTIMATE_AVAILABLE,
            eligibility_status=EligibilityStatus.PASS,
            review_status=ReviewStatus.NOT_REQUIRED,
            approval_probability_raw=0.61,
            approval_probability_display="61%",
            estimate_quality=EstimateQuality.MEDIUM,
            source_coverage_quality="HIGH",
            geometry_quality="HIGH",
            support_quality="COMPARABLES_PRESENT",
            scenario_quality="HIGH",
            ood_quality="LOW",
            ood_status="IN_SCOPE",
            manual_review_required=False,
            result_json={
                "support_summary": {"same_borough_support_count": 1},
                "validation_summary": {"validation": "ok"},
                "explanation": {"drivers": ["fixture"]},
                "note": "hidden",
            },
            model_release_id=_fixed_uuid(7),
            release_scope_key="scope-1",
            published_at=datetime(2026, 4, 18, 9, 5, tzinfo=UTC),
        )
        if scored_result is None:
            result_obj.result_json = {"score_execution_status": score_execution_status}
        captured_result.append(result_obj)
        return result_obj

    monkeypatch.setattr(assessment_service, "_load_scenario", lambda **_kwargs: scenario)
    monkeypatch.setattr(
        assessment_service,
        "rebuild_historical_case_labels",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        assessment_service,
        "build_feature_snapshot",
        lambda **_kwargs: feature_result,
    )
    monkeypatch.setattr(
        assessment_service,
        "evaluate_site_extant_permission",
        lambda **_kwargs: SimpleNamespace(
            eligibility_status=EligibilityStatus.PASS,
            manual_review_required=False,
        ),
    )
    monkeypatch.setattr(
        assessment_service,
        "get_borough_baseline_pack",
        lambda **_kwargs: SimpleNamespace(status=BaselinePackStatus.SIGNED_OFF),
    )
    monkeypatch.setattr(
        assessment_service,
        "assemble_site_evidence",
        lambda **_kwargs: evidence,
    )
    monkeypatch.setattr(
        assessment_service,
        "assemble_scenario_evidence",
        lambda **_kwargs: evidence,
    )
    monkeypatch.setattr(
        assessment_service,
        "_build_assessment_evidence",
        lambda **_kwargs: evidence,
    )
    monkeypatch.setattr(
        assessment_service,
        "_persist_evidence_items",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        assessment_service,
        "build_comparable_case_set",
        lambda **_kwargs: comparable_result,
    )
    monkeypatch.setattr(
        assessment_service,
        "resolve_active_release",
        lambda **_kwargs: (
            SimpleNamespace(
                id=_fixed_uuid(8),
                calibration_artifact_hash="cal",
                model_artifact_hash="model",
                validation_artifact_hash="val",
            ),
            "scope-1",
        ),
    )
    monkeypatch.setattr(
        assessment_service,
        "load_release_artifact_json",
        lambda **kwargs: {"artifact": kwargs["artifact"]},
    )
    monkeypatch.setattr(
        assessment_service,
        "score_frozen_assessment",
        lambda **_kwargs: scored_result,
    )
    monkeypatch.setattr(
        assessment_service,
        "_upsert_assessment_result",
        _fake_upsert_assessment_result,
    )
    monkeypatch.setattr(
        assessment_service,
        "build_or_refresh_valuation_for_assessment",
        lambda **_kwargs: valuation_run,
    )
    monkeypatch.setattr(
        assessment_service,
        "_stable_result_payload",
        lambda **_kwargs: {"sentinel": "payload"},
    )
    monkeypatch.setattr(
        assessment_service,
        "_upsert_prediction_ledger",
        lambda **kwargs: SimpleNamespace(
            result_payload_hash="payload-hash", replay_verification_status="HASH_CAPTURED"
        ),
    )
    monkeypatch.setattr(
        assessment_service,
        "canonical_json_hash",
        lambda payload: "feature-hash" if payload == {"sentinel": "feature"} else "payload-hash",
    )

    session = _QueuedSession(_QueryResult(scalar=None))
    run = assessment_service.create_or_refresh_assessment_run(
        session=session,
        site_id=site.id,
        scenario_id=scenario.id,
        as_of_date=date(2026, 4, 18),
        requested_by="pytest",
        storage=SimpleNamespace(),
    )
    assert run.state == AssessmentRunState.READY
    assert captured_statuses[0] == "HIDDEN_ESTIMATE_AVAILABLE"
    assert captured_result[0].approval_probability_raw == 0.61
    assert run.finished_at is not None

    monkeypatch.setattr(
        assessment_service,
        "resolve_active_release",
        lambda **_kwargs: (None, "scope-1"),
    )
    assessment_service.create_or_refresh_assessment_run(
        session=_QueuedSession(_QueryResult(scalar=None)),
        site_id=site.id,
        scenario_id=scenario.id,
        as_of_date=date(2026, 4, 18),
        requested_by="pytest",
        storage=SimpleNamespace(),
    )
    assert captured_statuses[-1] == "NO_ACTIVE_HIDDEN_RELEASE"

    monkeypatch.setattr(
        assessment_service,
        "resolve_active_release",
        lambda **_kwargs: (SimpleNamespace(id=_fixed_uuid(8)), "scope-1"),
    )
    monkeypatch.setattr(
        assessment_service,
        "get_borough_baseline_pack",
        lambda **_kwargs: None,
    )
    assessment_service.create_or_refresh_assessment_run(
        session=_QueuedSession(_QueryResult(scalar=None)),
        site_id=site.id,
        scenario_id=scenario.id,
        as_of_date=date(2026, 4, 18),
        requested_by="pytest",
        storage=SimpleNamespace(),
    )
    assert captured_statuses[-1] == "BASELINE_PACK_NOT_SIGNED_OFF"

    monkeypatch.setattr(
        assessment_service,
        "get_borough_baseline_pack",
        lambda **_kwargs: SimpleNamespace(status=BaselinePackStatus.SIGNED_OFF),
    )
    monkeypatch.setattr(
        assessment_service,
        "evaluate_site_extant_permission",
        lambda **_kwargs: SimpleNamespace(
            eligibility_status=EligibilityStatus.ABSTAIN,
            manual_review_required=True,
        ),
    )
    assessment_service.create_or_refresh_assessment_run(
        session=_QueuedSession(_QueryResult(scalar=None)),
        site_id=site.id,
        scenario_id=scenario.id,
        as_of_date=date(2026, 4, 18),
        requested_by="pytest",
        storage=SimpleNamespace(),
    )
    assert captured_statuses[-1] == "ABSTAIN"

    monkeypatch.setattr(
        assessment_service,
        "build_feature_snapshot",
        lambda **_kwargs: (_ for _ in ()).throw(ValueError("feature build failed")),
    )
    failing_session = _QueuedSession(_QueryResult(scalar=None))
    with pytest.raises(ValueError, match="feature build failed"):
        assessment_service.create_or_refresh_assessment_run(
            session=failing_session,
            site_id=site.id,
            scenario_id=scenario.id,
            as_of_date=date(2026, 4, 18),
            requested_by="pytest",
            storage=SimpleNamespace(),
        )
    failed_run = failing_session.added[0]
    assert failed_run.state == AssessmentRunState.FAILED
    assert failed_run.error_text == "feature build failed"
    assert failed_run.finished_at is not None

    build_artifacts_run = SimpleNamespace(
        id=_fixed_uuid(9),
        state=AssessmentRunState.PENDING,
        site_id=site.id,
        scenario_id=scenario.id,
        as_of_date=date(2026, 4, 18),
        requested_by="pytest",
    )
    delegated = {}

    def _fake_create_or_refresh_assessment_run(**kwargs):
        delegated.update(kwargs)
        return SimpleNamespace(id=_fixed_uuid(10))

    monkeypatch.setattr(
        assessment_service,
        "create_or_refresh_assessment_run",
        _fake_create_or_refresh_assessment_run,
    )
    returned = assessment_service.build_assessment_artifacts_for_run(
        session=_QueuedSession(_QueryResult(scalar=build_artifacts_run)),
        assessment_run_id=build_artifacts_run.id,
        requested_by="pytest",
    )
    assert returned.id == _fixed_uuid(10)
    assert delegated["site_id"] == site.id


def test_assessment_replay_and_load_scenario_helpers(monkeypatch) -> None:
    feature_snapshot = SimpleNamespace(
        feature_json={"sentinel": "feature"},
        feature_hash="feature-hash",
        coverage_json={"coverage": "ok"},
        feature_version="v1",
    )
    result = SimpleNamespace(
        model_release_id=_fixed_uuid(20),
        approval_probability_raw=0.61,
        approval_probability_display="61%",
        estimate_quality=ValuationQuality.MEDIUM,
        source_coverage_quality="HIGH",
        geometry_quality="HIGH",
        support_quality="COMPARABLES_PRESENT",
        scenario_quality="HIGH",
        ood_quality="LOW",
        ood_status="IN_SCOPE",
        manual_review_required=False,
        result_json={
            "support_summary": {"same_borough_support_count": 1},
            "validation_summary": {"validation": "ok"},
            "explanation": {"drivers": ["fixture"]},
        },
    )
    ledger = SimpleNamespace(
        result_payload_hash="payload-hash",
        replay_verification_status="HASH_CAPTURED",
        replay_verified_at=None,
        replay_verification_note=None,
        site_geom_hash="site-geom",
        model_release_id=_fixed_uuid(20),
    )
    run = SimpleNamespace(
        id=_fixed_uuid(21),
        site_id=_fixed_uuid(22),
        scenario_id=_fixed_uuid(23),
        as_of_date=date(2026, 4, 18),
        site=SimpleNamespace(id=_fixed_uuid(22), borough_id="camden"),
        scenario=SimpleNamespace(id=_fixed_uuid(23), red_line_geom_hash="site-geom"),
        feature_snapshot=feature_snapshot,
        result=result,
        prediction_ledger=ledger,
        evidence_items=[],
        comparable_case_set=SimpleNamespace(
            strategy="fixture",
            members=[],
        ),
    )
    release = SimpleNamespace(id=_fixed_uuid(20))
    monkeypatch.setattr(
        assessment_service,
        "_pack_from_rows",
        lambda _rows: EvidencePackRead(for_=[], against=[], unknown=[]),
    )
    monkeypatch.setattr(
        assessment_service,
        "_stable_comparable_payload",
        lambda _run: {"strategy": "fixture", "approved": [], "refused": []},
    )
    monkeypatch.setattr(
        assessment_service,
        "load_release_artifact_json",
        lambda **kwargs: {"artifact": kwargs["artifact"]},
    )
    monkeypatch.setattr(
        assessment_service,
        "score_frozen_assessment",
        lambda **_kwargs: {
            "approval_probability_raw": 0.61,
            "approval_probability_display": "61%",
            "estimate_quality": ValuationQuality.MEDIUM.value,
            "source_coverage_quality": "HIGH",
            "geometry_quality": "HIGH",
            "support_quality": "COMPARABLES_PRESENT",
            "scenario_quality": "HIGH",
            "ood_quality": "LOW",
            "ood_status": "IN_SCOPE",
            "manual_review_required": False,
            "support_summary": {"same_borough_support_count": 1},
            "validation_summary": {"validation": "ok"},
            "explanation": {"drivers": ["fixture"]},
        },
    )
    monkeypatch.setattr(
        assessment_service,
        "_build_stable_result_payload",
        lambda **_kwargs: {"sentinel": "payload"},
    )
    monkeypatch.setattr(
        assessment_service,
        "canonical_json_hash",
        lambda payload: "feature-hash" if payload == {"sentinel": "feature"} else "payload-hash",
    )
    monkeypatch.setattr(
        assessment_service,
        "_record_replay_verification",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(assessment_service, "frozen_valuation_run", lambda _run: None)

    session = _QueuedSession(get_result=release)
    replay = assessment_service.verify_assessment_replay(
        session=session,
        assessment_run=run,
        storage=SimpleNamespace(),
    )
    assert replay["replay_passed"] is True
    assert replay["payload_hash_matches"] is True

    assessment_service._record_replay_verification(
        assessment_run=SimpleNamespace(prediction_ledger=None),
        check={
            "replay_passed": True,
            "feature_hash_matches": True,
            "payload_hash_matches": True,
            "scored_fields_match": True,
        },
    )

    with pytest.raises(assessment_service.AssessmentBuildError, match="was not found"):
        assessment_service._load_scenario(
            session=_QueuedSession(_QueryResult(scalar=None)),
            scenario_id=_fixed_uuid(30),
        )


def test_assessment_readback_and_comparable_branches(monkeypatch) -> None:
    rows = [
        SimpleNamespace(id=_fixed_uuid(41), site_id=_fixed_uuid(101), scenario_id=_fixed_uuid(102))
    ]
    session = _QueuedSession(_QueryResult(scalar=1), _QueryResult(rows=rows))
    monkeypatch.setattr(
        assessments_readback,
        "serialize_assessment_summary",
        lambda **kwargs: _summary_model(row_id=kwargs["run"].id),
    )

    response = assessments_readback.list_assessments(
        session=session,
        site_id=_fixed_uuid(101),
        scenario_id=_fixed_uuid(102),
        limit=10,
        offset=0,
    )
    assert isinstance(response, AssessmentListResponse)
    assert response.total == 1
    assert response.items[0].id == _fixed_uuid(41)

    none_result = assessments_readback.get_assessment(
        session=_QueuedSession(_QueryResult(scalar=None)),
        assessment_id=_fixed_uuid(999),
    )
    assert none_result is None

    site = SimpleNamespace(
        borough_id="camden",
        planning_links=[SimpleNamespace(planning_application_id=_fixed_uuid(50))],
    )
    scenario = SimpleNamespace(
        proposal_form=ProposalForm.INFILL,
        units_assumed=10,
        template_key="resi_5_9_full",
    )
    label_rows = [
        _label(
            row_id=_fixed_uuid(51),
            planning_application_id=_fixed_uuid(50),
            template_key="resi_5_9_full",
            label_class=HistoricalLabelClass.POSITIVE,
        ),
        _label(
            row_id=_fixed_uuid(52),
            planning_application_id=_fixed_uuid(52),
            template_key="wrong-template",
            label_class=HistoricalLabelClass.POSITIVE,
        ),
        _label(
            row_id=_fixed_uuid(53),
            planning_application_id=_fixed_uuid(53),
            template_key="resi_5_9_full",
            label_class=HistoricalLabelClass.POSITIVE,
            valid_date=date(2026, 5, 1),
        ),
        _label(
            row_id=_fixed_uuid(54),
            planning_application_id=_fixed_uuid(54),
            template_key="resi_5_9_full",
            label_class=HistoricalLabelClass.POSITIVE,
            first_decision_date=date(2026, 5, 2),
        ),
        _label(
            row_id=_fixed_uuid(55),
            planning_application_id=_fixed_uuid(55),
            template_key="resi_5_9_full",
            label_class=HistoricalLabelClass.POSITIVE,
            review_status=GoldSetReviewStatus.EXCLUDED,
        ),
        _label(
            row_id=_fixed_uuid(56),
            planning_application_id=_fixed_uuid(56),
            template_key="resi_5_9_full",
            label_class=HistoricalLabelClass.POSITIVE,
        ),
        _label(
            row_id=_fixed_uuid(57),
            planning_application_id=_fixed_uuid(57),
            template_key="resi_5_9_full",
            label_class=HistoricalLabelClass.POSITIVE,
        ),
        _label(
            row_id=_fixed_uuid(58),
            planning_application_id=_fixed_uuid(58),
            template_key="resi_5_9_full",
            label_class=HistoricalLabelClass.POSITIVE,
        ),
        _label(
            row_id=_fixed_uuid(59),
            planning_application_id=_fixed_uuid(59),
            template_key="resi_5_9_full",
            label_class=HistoricalLabelClass.POSITIVE,
        ),
        _label(
            row_id=_fixed_uuid(60),
            planning_application_id=_fixed_uuid(60),
            template_key="resi_5_9_full",
            label_class=HistoricalLabelClass.NEGATIVE,
        ),
    ]
    monkeypatch.setattr(
        comparable_service,
        "_select_members",
        comparable_service._select_members,
    )
    result = comparable_service.build_comparable_case_set(
        session=_QueuedSession(_QueryResult(rows=label_rows)),
        assessment_run=SimpleNamespace(id=_fixed_uuid(70), comparable_case_set=None),
        site=site,
        scenario=scenario,
        as_of_date=date(2026, 4, 18),
        feature_json={
            "values": {
                "site_area_sqm": 120.0,
                "designation_archetype_key": "fixture-archetype",
            },
            "designation_profile": {"brownfield": True, "zones": ["a"]},
        },
    )
    assert result.approved_members
    assert result.refused_members
    assert result.comparable_case_set.approved_count == len(result.approved_members)
    assert result.comparable_case_set.refused_count == len(result.refused_members)

    many_positive_rows = [
        _label(
            row_id=_fixed_uuid(71 + idx),
            planning_application_id=_fixed_uuid(171 + idx),
            template_key="resi_5_9_full",
            label_class=HistoricalLabelClass.POSITIVE,
        )
        for idx in range(4)
    ]
    selected = comparable_service._select_members(
        site=site,
        scenario=scenario,
        site_area_sqm=120.0,
        site_archetype="fixture-archetype",
        site_designation_profile={"brownfield": True, "zones": ["a"]},
        scenario_form_value=scenario.proposal_form.value,
        rows=many_positive_rows,
        outcome=ComparableOutcome.APPROVED,
        as_of_date=date(2026, 4, 18),
    )
    assert len(selected) == 3
