from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from landintel.assessments.service import HIDDEN_SCORE_NOTE, PRE_SCORE_NOTE
from landintel.domain.enums import EligibilityStatus, EstimateStatus, ReviewStatus
from landintel.domain.models import (
    AssessmentResult,
    AssessmentRun,
    ComparableCaseMember,
    ComparableCaseSet,
    EvidenceItem,
    HistoricalCaseLabel,
    PlanningApplication,
    PlanningApplicationDocument,
    PredictionLedger,
    SiteCandidate,
    SiteConstraintFact,
    SitePlanningLink,
    SitePolicyFact,
    SiteScenario,
    ValuationRun,
)
from landintel.domain.schemas import (
    AssessmentDetailRead,
    AssessmentFeatureSnapshotRead,
    AssessmentListResponse,
    AssessmentResultRead,
    AssessmentSummaryRead,
    ComparableCaseMemberRead,
    ComparableCaseSetRead,
    ComparablePlanningApplicationRead,
    HistoricalLabelCaseRead,
    HistoricalLabelListResponse,
    HistoricalLabelSummaryRead,
    PlanningApplicationDocumentRead,
    PlanningApplicationRead,
    PredictionLedgerRead,
    ValuationResultRead,
)
from landintel.features.build import FEATURE_VERSION
from landintel.planning.enrich import get_borough_baseline_pack
from landintel.planning.historical_labels import (
    get_historical_label_case,
    list_historical_label_cases,
)
from landintel.services.listings_readback import serialize_raw_asset
from landintel.services.scenarios_readback import serialize_site_scenario_summary
from landintel.services.sites_readback import serialize_site_summary
from landintel.valuation.service import latest_valuation_run


def list_assessments(
    session: Session,
    *,
    site_id: UUID | None = None,
    scenario_id: UUID | None = None,
    limit: int = 100,
    offset: int = 0,
) -> AssessmentListResponse:
    stmt = select(AssessmentRun)
    if site_id is not None:
        stmt = stmt.where(AssessmentRun.site_id == site_id)
    if scenario_id is not None:
        stmt = stmt.where(AssessmentRun.scenario_id == scenario_id)

    total = session.execute(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    ).scalar_one()
    rows = (
        session.execute(
            stmt.options(*_assessment_load_options())
            .order_by(AssessmentRun.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .unique()
        .all()
    )

    return AssessmentListResponse(
        items=[serialize_assessment_summary(session=session, run=row) for row in rows],
        total=total,
    )


def get_assessment(
    session: Session,
    *,
    assessment_id: UUID,
    include_hidden: bool = False,
) -> AssessmentDetailRead | None:
    row = session.execute(
        select(AssessmentRun)
        .where(AssessmentRun.id == assessment_id)
        .options(*_assessment_load_options())
    ).scalar_one_or_none()
    if row is None:
        return None
    return serialize_assessment_detail(session=session, run=row, include_hidden=include_hidden)


def serialize_assessment_summary(
    *,
    session: Session,
    run: AssessmentRun,
) -> AssessmentSummaryRead:
    result = run.result
    baseline_pack = (
        get_borough_baseline_pack(session=session, borough_id=run.site.borough_id)
        if run.site.borough_id
        else None
    )
    return AssessmentSummaryRead(
        id=run.id,
        site_id=run.site_id,
        scenario_id=run.scenario_id,
        as_of_date=run.as_of_date,
        state=run.state,
        idempotency_key=run.idempotency_key,
        requested_by=run.requested_by,
        started_at=run.started_at,
        finished_at=run.finished_at,
        error_text=run.error_text,
        created_at=run.created_at,
        updated_at=run.updated_at,
        estimate_status=result.estimate_status if result is not None else EstimateStatus.NONE,
        eligibility_status=(
            result.eligibility_status if result is not None else EligibilityStatus.ABSTAIN
        ),
        review_status=result.review_status if result is not None else ReviewStatus.REQUIRED,
        manual_review_required=(result.manual_review_required if result is not None else True),
        site_summary=serialize_site_summary(run.site),
        scenario_summary=serialize_site_scenario_summary(
            session=session,
            scenario=run.scenario,
            baseline_pack=baseline_pack,
            site=run.site,
        ),
    )


def serialize_assessment_detail(
    *,
    session: Session,
    run: AssessmentRun,
    include_hidden: bool = False,
) -> AssessmentDetailRead:
    summary = serialize_assessment_summary(session=session, run=run)
    labels_by_application_id = _labels_by_application_id(
        session=session,
        planning_application_ids=[
            member.planning_application_id
            for member in (run.comparable_case_set.members if run.comparable_case_set else [])
        ],
    )
    evidence = _pack_from_rows(run.evidence_items)
    return AssessmentDetailRead(
        **summary.model_dump(),
        feature_snapshot=(
            None
            if run.feature_snapshot is None
            else AssessmentFeatureSnapshotRead(
                id=run.feature_snapshot.id,
                feature_version=run.feature_snapshot.feature_version,
                feature_hash=run.feature_snapshot.feature_hash,
                feature_json=run.feature_snapshot.feature_json,
                coverage_json=run.feature_snapshot.coverage_json,
                created_at=run.feature_snapshot.created_at,
            )
        ),
        result=(
            _serialize_assessment_result(run.result, include_hidden=include_hidden)
        ),
        valuation=_serialize_valuation_result(latest_valuation_run(run)),
        evidence=evidence,
        comparable_case_set=_serialize_comparable_case_set(
            run.comparable_case_set,
            labels_by_application_id=labels_by_application_id,
        ),
        prediction_ledger=_serialize_prediction_ledger(
            run.prediction_ledger,
            include_hidden=include_hidden,
        ),
        note=_detail_note(run=run, include_hidden=include_hidden),
    )


def _serialize_assessment_result(
    result: AssessmentResult | None,
    *,
    include_hidden: bool,
) -> AssessmentResultRead | None:
    if result is None:
        return None
    hidden_score_present = result.approval_probability_raw is not None
    result_json = dict(result.result_json or {})
    if hidden_score_present and not include_hidden:
        result_json = {
            "phase": "Phase 6A",
            "score_execution_status": result_json.get("score_execution_status", "HIDDEN_ONLY"),
            "hidden_score_redacted": True,
            "note": (
                "Hidden internal score exists for this frozen run, but standard assessment "
                "reads remain non-speaking in Phase 6A."
            ),
        }
    return AssessmentResultRead(
        id=result.id,
        model_release_id=(result.model_release_id if include_hidden else None),
        release_scope_key=(result.release_scope_key if include_hidden else None),
        eligibility_status=result.eligibility_status,
        estimate_status=result.estimate_status,
        review_status=result.review_status,
        approval_probability_raw=(
            result.approval_probability_raw if include_hidden else None
        ),
        approval_probability_display=(
            result.approval_probability_display if include_hidden else None
        ),
        estimate_quality=result.estimate_quality,
        source_coverage_quality=result.source_coverage_quality,
        geometry_quality=result.geometry_quality,
        support_quality=result.support_quality,
        scenario_quality=result.scenario_quality,
        ood_quality=result.ood_quality,
        ood_status=result.ood_status,
        manual_review_required=result.manual_review_required,
        result_json=result_json,
        published_at=result.published_at,
    )


def _serialize_prediction_ledger(
    ledger: PredictionLedger | None,
    *,
    include_hidden: bool,
) -> PredictionLedgerRead | None:
    if ledger is None:
        return None
    response_json = dict(ledger.response_json or {})
    if ledger.model_release_id is not None and not include_hidden:
        response_json = {
            "response_mode": ledger.response_mode,
            "hidden_score_redacted": True,
            "result_payload_hash": ledger.result_payload_hash,
        }
    return PredictionLedgerRead(
        id=ledger.id,
        site_geom_hash=ledger.site_geom_hash,
        feature_hash=ledger.feature_hash,
        model_release_id=(ledger.model_release_id if include_hidden else None),
        release_scope_key=(ledger.release_scope_key if include_hidden else None),
        calibration_hash=(ledger.calibration_hash if include_hidden else None),
        response_mode=ledger.response_mode,
        source_snapshot_ids_json=list(ledger.source_snapshot_ids_json or []),
        raw_asset_ids_json=list(ledger.raw_asset_ids_json or []),
        result_payload_hash=ledger.result_payload_hash,
        response_json=response_json,
        created_at=ledger.created_at,
    )


def _serialize_valuation_result(valuation_run) -> ValuationResultRead | None:
    if valuation_run is None or valuation_run.result is None:
        return None
    result = valuation_run.result
    return ValuationResultRead(
        id=result.id,
        valuation_run_id=valuation_run.id,
        valuation_assumption_set_id=valuation_run.valuation_assumption_set_id,
        valuation_assumption_version=valuation_run.valuation_assumption_set.version,
        post_permission_value_low=result.post_permission_value_low,
        post_permission_value_mid=result.post_permission_value_mid,
        post_permission_value_high=result.post_permission_value_high,
        uplift_low=result.uplift_low,
        uplift_mid=result.uplift_mid,
        uplift_high=result.uplift_high,
        expected_uplift_mid=result.expected_uplift_mid,
        valuation_quality=result.valuation_quality,
        manual_review_required=result.manual_review_required,
        basis_json=dict(result.basis_json or {}),
        sense_check_json=dict(result.sense_check_json or {}),
        result_json=dict(result.result_json or {}),
        payload_hash=result.payload_hash,
        created_at=result.created_at,
    )


def _detail_note(*, run: AssessmentRun, include_hidden: bool) -> str:
    if run.result is None:
        return PRE_SCORE_NOTE
    if run.result.approval_probability_raw is not None:
        return HIDDEN_SCORE_NOTE if include_hidden else (
            "Hidden score mode is available for internal evaluation, but this view remains "
            "non-speaking in Phase 6A."
        )
    return str((run.result.result_json or {}).get("note") or PRE_SCORE_NOTE)


def list_gold_set_cases_read(
    *,
    session: Session,
    review_status=None,
    template_key: str | None = None,
) -> HistoricalLabelListResponse:
    rows = list_historical_label_cases(
        session=session,
        review_status=review_status,
        template_key=template_key,
    )
    return HistoricalLabelListResponse(
        items=[serialize_historical_label_summary(row) for row in rows],
        total=len(rows),
    )


def get_gold_set_case_read(
    *,
    session: Session,
    case_id: UUID,
) -> HistoricalLabelCaseRead | None:
    row = get_historical_label_case(session=session, case_id=case_id)
    if row is None:
        return None
    return serialize_historical_label_case(row)


def serialize_historical_label_summary(case: HistoricalCaseLabel) -> HistoricalLabelSummaryRead:
    return HistoricalLabelSummaryRead(
        id=case.id,
        planning_application_id=case.planning_application_id,
        borough_id=case.borough_id,
        template_key=case.template_key,
        proposal_form=case.proposal_form,
        route_normalized=case.route_normalized,
        units_proposed=case.units_proposed,
        site_area_sqm=case.site_area_sqm,
        label_version=case.label_version,
        label_class=case.label_class,
        label_decision=case.label_decision,
        label_reason=case.label_reason,
        valid_date=case.valid_date,
        first_substantive_decision_date=case.first_substantive_decision_date,
        label_window_end=case.label_window_end,
        source_priority_used=case.source_priority_used,
        archetype_key=case.archetype_key,
        designation_profile_json=dict(case.designation_profile_json or {}),
        provenance_json=dict(case.provenance_json or {}),
        source_snapshot_ids_json=list(case.source_snapshot_ids_json or []),
        raw_asset_ids_json=list(case.raw_asset_ids_json or []),
        review_status=case.review_status,
        review_notes=case.review_notes,
        reviewed_by=case.reviewed_by,
        reviewed_at=case.reviewed_at,
        notable_policy_issues_json=list(case.notable_policy_issues_json or []),
        extant_permission_outcome=case.extant_permission_outcome,
        site_geometry_confidence=case.site_geometry_confidence,
        created_at=case.created_at,
        updated_at=case.updated_at,
    )


def serialize_historical_label_case(case: HistoricalCaseLabel) -> HistoricalLabelCaseRead:
    return HistoricalLabelCaseRead(
        **serialize_historical_label_summary(case).model_dump(),
        planning_application=_serialize_planning_application(case.planning_application),
    )


def _serialize_planning_application(application: PlanningApplication) -> PlanningApplicationRead:
    return PlanningApplicationRead(
        id=application.id,
        borough_id=application.borough_id,
        source_system=application.source_system,
        source_snapshot_id=application.source_snapshot_id,
        external_ref=application.external_ref,
        application_type=application.application_type,
        proposal_description=application.proposal_description,
        valid_date=application.valid_date,
        decision_date=application.decision_date,
        decision=application.decision,
        decision_type=application.decision_type,
        status=application.status,
        route_normalized=application.route_normalized,
        units_proposed=application.units_proposed,
        source_priority=application.source_priority,
        source_url=application.source_url,
        site_geom_4326=application.site_geom_4326,
        site_point_4326=application.site_point_4326,
        raw_record_json=dict(application.raw_record_json or {}),
        documents=[
            PlanningApplicationDocumentRead(
                id=document.id,
                asset_id=document.asset_id,
                doc_type=document.doc_type,
                doc_url=document.doc_url,
                asset=serialize_raw_asset(document.asset),
            )
            for document in application.documents
        ],
    )


def _serialize_comparable_case_set(
    comparable_case_set: ComparableCaseSet | None,
    *,
    labels_by_application_id: dict[UUID, HistoricalCaseLabel],
) -> ComparableCaseSetRead | None:
    if comparable_case_set is None:
        return None
    approved_members = [
        _serialize_comparable_member(member, labels_by_application_id=labels_by_application_id)
        for member in comparable_case_set.members
        if member.outcome.value == "APPROVED"
    ]
    refused_members = [
        _serialize_comparable_member(member, labels_by_application_id=labels_by_application_id)
        for member in comparable_case_set.members
        if member.outcome.value == "REFUSED"
    ]
    return ComparableCaseSetRead(
        id=comparable_case_set.id,
        strategy=comparable_case_set.strategy,
        same_borough_count=comparable_case_set.same_borough_count,
        london_count=comparable_case_set.london_count,
        approved_count=comparable_case_set.approved_count,
        refused_count=comparable_case_set.refused_count,
        approved_members=approved_members,
        refused_members=refused_members,
    )


def _serialize_comparable_member(
    member: ComparableCaseMember,
    *,
    labels_by_application_id: dict[UUID, HistoricalCaseLabel],
) -> ComparableCaseMemberRead:
    label = labels_by_application_id[member.planning_application_id]
    application = member.planning_application
    return ComparableCaseMemberRead(
        id=member.id,
        planning_application_id=member.planning_application_id,
        similarity_score=member.similarity_score,
        outcome=member.outcome,
        rank=member.rank,
        fallback_path=member.fallback_path,
        match_json=dict(member.match_json or {}),
        planning_application=ComparablePlanningApplicationRead(
            id=application.id,
            external_ref=application.external_ref,
            borough_id=application.borough_id,
            proposal_description=application.proposal_description,
            valid_date=application.valid_date,
            decision_date=application.decision_date,
            decision=application.decision,
            route_normalized=application.route_normalized,
            units_proposed=application.units_proposed,
            source_system=application.source_system,
            source_url=application.source_url,
        ),
        historical_label=serialize_historical_label_summary(label),
    )


def _pack_from_rows(rows: list[EvidenceItem]):
    from landintel.assessments.service import _pack_from_rows as service_pack_from_rows

    return service_pack_from_rows(rows)


def _labels_by_application_id(
    *,
    session: Session,
    planning_application_ids: list[UUID],
) -> dict[UUID, HistoricalCaseLabel]:
    if not planning_application_ids:
        return {}
    rows = (
        session.execute(
            select(HistoricalCaseLabel)
            .where(HistoricalCaseLabel.label_version == FEATURE_VERSION)
            .where(HistoricalCaseLabel.planning_application_id.in_(planning_application_ids))
        )
        .scalars()
        .all()
    )
    return {row.planning_application_id: row for row in rows}


def _assessment_load_options():
    return (
        selectinload(AssessmentRun.site)
        .selectinload(SiteCandidate.planning_links)
        .selectinload(SitePlanningLink.planning_application)
        .selectinload(PlanningApplication.documents)
        .selectinload(PlanningApplicationDocument.asset),
        selectinload(AssessmentRun.site)
        .selectinload(SiteCandidate.policy_facts)
        .selectinload(SitePolicyFact.policy_area),
        selectinload(AssessmentRun.site)
        .selectinload(SiteCandidate.constraint_facts)
        .selectinload(SiteConstraintFact.constraint_feature),
        selectinload(AssessmentRun.site).selectinload(SiteCandidate.geometry_revisions),
        selectinload(AssessmentRun.scenario).selectinload(SiteScenario.reviews),
        selectinload(AssessmentRun.scenario).selectinload(SiteScenario.geometry_revision),
        selectinload(AssessmentRun.feature_snapshot),
        selectinload(AssessmentRun.result),
        selectinload(AssessmentRun.evidence_items),
        selectinload(AssessmentRun.comparable_case_set)
        .selectinload(ComparableCaseSet.members)
        .selectinload(ComparableCaseMember.planning_application)
        .selectinload(PlanningApplication.documents)
        .selectinload(PlanningApplicationDocument.asset),
        selectinload(AssessmentRun.prediction_ledger),
        selectinload(AssessmentRun.valuation_runs).selectinload(ValuationRun.result),
        selectinload(AssessmentRun.valuation_runs).selectinload(
            ValuationRun.valuation_assumption_set
        ),
    )
