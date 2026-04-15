from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from landintel.assessments.comparables import build_comparable_case_set
from landintel.domain.enums import (
    AssessmentRunState,
    EstimateStatus,
    EvidenceImportance,
    EvidencePolarity,
    ReviewStatus,
    ScenarioStatus,
    SourceClass,
    VerifiedStatus,
)
from landintel.domain.models import (
    AssessmentFeatureSnapshot,
    AssessmentResult,
    AssessmentRun,
    AuditEvent,
    ComparableCaseMember,
    ComparableCaseSet,
    EvidenceItem,
    PlanningApplication,
    PlanningApplicationDocument,
    PredictionLedger,
    SiteCandidate,
    SiteConstraintFact,
    SitePlanningLink,
    SitePolicyFact,
    SiteScenario,
)
from landintel.domain.schemas import EvidenceItemRead, EvidencePackRead
from landintel.evidence.assemble import assemble_scenario_evidence, assemble_site_evidence
from landintel.features.build import build_feature_snapshot, canonical_json_hash
from landintel.planning.enrich import get_borough_baseline_pack
from landintel.planning.extant_permission import evaluate_site_extant_permission
from landintel.planning.historical_labels import rebuild_historical_case_labels
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

ASSESSMENT_NAMESPACE = uuid.UUID("6f8c2b84-0ef7-4c40-891f-f1d54ef4f7ef")
PRE_SCORE_MODEL_SENTINEL = "PHASE5A_PRE_SCORE"
PRE_SCORE_NOTE = (
    "Assessment scoring, calibration, and probability remain intentionally disabled in Phase 5A. "
    "This run freezes features, evidence, comparables, and replay metadata only."
)


class AssessmentBuildError(ValueError):
    pass


def create_or_refresh_assessment_run(
    *,
    session: Session,
    site_id: uuid.UUID,
    scenario_id: uuid.UUID,
    as_of_date: date,
    requested_by: str | None,
) -> AssessmentRun:
    scenario = _load_scenario(session=session, scenario_id=scenario_id)
    site = scenario.site
    if site.id != site_id:
        raise AssessmentBuildError("Scenario does not belong to the requested site.")
    if scenario.status not in {ScenarioStatus.AUTO_CONFIRMED, ScenarioStatus.ANALYST_CONFIRMED}:
        raise AssessmentBuildError(
            "Assessment runs require a current confirmed scenario in Phase 5A."
        )
    if not scenario.is_current:
        raise AssessmentBuildError("Scenario is superseded and cannot anchor a new assessment run.")
    if scenario.red_line_geom_hash != site.geom_hash:
        raise AssessmentBuildError(
            "Scenario red-line geometry is stale. Reconfirm the scenario before assessment."
        )
    if as_of_date > date.today():
        raise AssessmentBuildError("Assessment as_of_date cannot be in the future.")

    rebuild_historical_case_labels(session=session, requested_by=requested_by or "assessment-run")

    idempotency_key = _assessment_idempotency_key(
        site=site,
        scenario=scenario,
        as_of_date=as_of_date,
    )
    existing = session.execute(
        select(AssessmentRun)
        .where(AssessmentRun.idempotency_key == idempotency_key)
        .options(*_assessment_load_options())
    ).scalar_one_or_none()
    if existing is not None and existing.state == AssessmentRunState.READY:
        return existing

    run = existing or AssessmentRun(
        id=uuid.uuid5(ASSESSMENT_NAMESPACE, idempotency_key),
        site_id=site.id,
        scenario_id=scenario.id,
        as_of_date=as_of_date,
        idempotency_key=idempotency_key,
        requested_by=requested_by,
    )
    if existing is None:
        session.add(run)
    run.requested_by = requested_by
    run.state = AssessmentRunState.PENDING
    run.error_text = None
    run.started_at = datetime.now(UTC)
    run.finished_at = None
    session.flush()

    try:
        run.state = AssessmentRunState.BUILDING_FEATURES
        feature_result = build_feature_snapshot(
            session=session,
            site=site,
            scenario=scenario,
            as_of_date=as_of_date,
        )
        feature_snapshot = _upsert_feature_snapshot(
            session=session,
            run=run,
            feature_result=feature_result,
        )

        extant_permission = evaluate_site_extant_permission(session=session, site=site)
        baseline_pack = get_borough_baseline_pack(session=session, borough_id=site.borough_id)
        site_evidence = assemble_site_evidence(
            session=session,
            site=site,
            extant_permission=extant_permission,
        )
        scenario_evidence = assemble_scenario_evidence(
            session=session,
            site=site,
            scenario=scenario,
            site_evidence=site_evidence,
            extant_permission=extant_permission,
            baseline_pack=baseline_pack,
        )
        assessment_evidence = _build_assessment_evidence(
            scenario_evidence=scenario_evidence,
            as_of_date=as_of_date,
        )
        _persist_evidence_items(
            session=session,
            run=run,
            evidence=assessment_evidence,
        )

        run.state = AssessmentRunState.BUILDING_COMPARABLES
        comparable_result = build_comparable_case_set(
            session=session,
            assessment_run=run,
            site=site,
            scenario=scenario,
            as_of_date=as_of_date,
            feature_json=feature_snapshot.feature_json,
        )

        result = _upsert_assessment_result(
            session=session,
            run=run,
            scenario=scenario,
            extant_permission=extant_permission,
            comparable_count=(
                len(comparable_result.approved_members) + len(comparable_result.refused_members)
            ),
            coverage_json=feature_snapshot.coverage_json,
        )
        stable_payload = _stable_result_payload(
            run=run,
            site=site,
            scenario=scenario,
            feature_snapshot=feature_snapshot,
            result=result,
            evidence=assessment_evidence,
            comparable_result=comparable_result,
        )
        ledger = _upsert_prediction_ledger(
            session=session,
            run=run,
            feature_snapshot=feature_snapshot,
            comparable_result=comparable_result,
            evidence=assessment_evidence,
            stable_payload=stable_payload,
        )
        run.state = AssessmentRunState.READY
        run.finished_at = datetime.now(UTC)
        run.error_text = None
        session.add(
            AuditEvent(
                action="assessment_run_built",
                entity_type="assessment_run",
                entity_id=str(run.id),
                before_json=None,
                after_json={
                    "site_id": str(site.id),
                    "scenario_id": str(scenario.id),
                    "as_of_date": as_of_date.isoformat(),
                    "feature_hash": feature_snapshot.feature_hash,
                    "result_payload_hash": ledger.result_payload_hash,
                    "idempotency_key": idempotency_key,
                },
            )
        )
        session.flush()
        return run
    except Exception as exc:
        run.state = AssessmentRunState.FAILED
        run.finished_at = datetime.now(UTC)
        run.error_text = str(exc)
        session.flush()
        raise


def build_assessment_artifacts_for_run(
    *,
    session: Session,
    assessment_run_id: uuid.UUID,
    requested_by: str | None,
) -> AssessmentRun:
    run = session.execute(
        select(AssessmentRun)
        .where(AssessmentRun.id == assessment_run_id)
        .options(*_assessment_load_options())
    ).scalar_one_or_none()
    if run is None:
        raise AssessmentBuildError(f"Assessment run '{assessment_run_id}' was not found.")
    return create_or_refresh_assessment_run(
        session=session,
        site_id=run.site_id,
        scenario_id=run.scenario_id,
        as_of_date=run.as_of_date,
        requested_by=requested_by or run.requested_by,
    )


def verify_assessment_replay(
    *,
    session: Session,
    assessment_run: AssessmentRun,
) -> dict[str, object]:
    if (
        assessment_run.feature_snapshot is None
        or assessment_run.result is None
        or assessment_run.prediction_ledger is None
    ):
        raise AssessmentBuildError("Assessment run is incomplete and cannot be replay-verified.")

    evidence = _pack_from_rows(assessment_run.evidence_items)
    comparable_payload = _stable_comparable_payload(assessment_run)
    stable_payload = _build_stable_result_payload(
        site_id=assessment_run.site_id,
        scenario_id=assessment_run.scenario_id,
        as_of_date=assessment_run.as_of_date,
        red_line_geom_hash=assessment_run.scenario.red_line_geom_hash,
        feature_snapshot=assessment_run.feature_snapshot,
        result=assessment_run.result,
        evidence=evidence,
        comparables=comparable_payload,
    )
    payload_hash = canonical_json_hash(stable_payload)
    return {
        "assessment_run_id": str(assessment_run.id),
        "feature_hash_matches": (
            canonical_json_hash(assessment_run.feature_snapshot.feature_json)
            == assessment_run.feature_snapshot.feature_hash
        ),
        "payload_hash_matches": payload_hash
        == assessment_run.prediction_ledger.result_payload_hash,
        "feature_hash": assessment_run.feature_snapshot.feature_hash,
        "recomputed_payload_hash": payload_hash,
        "stored_payload_hash": assessment_run.prediction_ledger.result_payload_hash,
    }


def replay_verify_all_assessments(session: Session) -> dict[str, object]:
    runs = (
        session.execute(
            select(AssessmentRun)
            .where(AssessmentRun.state == AssessmentRunState.READY)
            .options(*_assessment_load_options())
            .order_by(AssessmentRun.created_at.asc())
        )
        .scalars()
        .all()
    )
    checks = [verify_assessment_replay(session=session, assessment_run=run) for run in runs]
    failures = [
        check
        for check in checks
        if not check["feature_hash_matches"] or not check["payload_hash_matches"]
    ]
    return {
        "total": len(checks),
        "failed": len(failures),
        "checks": checks,
    }


def _load_scenario(*, session: Session, scenario_id: uuid.UUID) -> SiteScenario:
    scenario = session.execute(
        select(SiteScenario)
        .where(SiteScenario.id == scenario_id)
        .options(
            selectinload(SiteScenario.site)
            .selectinload(SiteCandidate.planning_links)
            .selectinload(SitePlanningLink.planning_application)
            .selectinload(PlanningApplication.documents)
            .selectinload(PlanningApplicationDocument.asset),
            selectinload(SiteScenario.site)
            .selectinload(SiteCandidate.policy_facts)
            .selectinload(SitePolicyFact.policy_area),
            selectinload(SiteScenario.site)
            .selectinload(SiteCandidate.constraint_facts)
            .selectinload(SiteConstraintFact.constraint_feature),
            selectinload(SiteScenario.site).selectinload(SiteCandidate.geometry_revisions),
            selectinload(SiteScenario.site).selectinload(SiteCandidate.scenarios),
            selectinload(SiteScenario.reviews),
            selectinload(SiteScenario.geometry_revision),
        )
    ).scalar_one_or_none()
    if scenario is None:
        raise AssessmentBuildError(f"Scenario '{scenario_id}' was not found.")
    return scenario


def _assessment_idempotency_key(
    *,
    site: SiteCandidate,
    scenario: SiteScenario,
    as_of_date: date,
) -> str:
    return canonical_json_hash(
        {
            "site_id": str(site.id),
            "scenario_id": str(scenario.id),
            "as_of_date": as_of_date.isoformat(),
            "red_line_geom_hash": scenario.red_line_geom_hash,
            "template_key": scenario.template_key,
            "template_version": scenario.template_version,
        }
    )


def _upsert_feature_snapshot(
    *,
    session: Session,
    run: AssessmentRun,
    feature_result,
) -> AssessmentFeatureSnapshot:
    row = run.feature_snapshot or AssessmentFeatureSnapshot(assessment_run_id=run.id)
    row.feature_version = feature_result.feature_version
    row.feature_hash = feature_result.feature_hash
    row.feature_json = feature_result.feature_json
    row.coverage_json = feature_result.coverage_json
    session.add(row)
    session.flush()
    return row


def _build_assessment_evidence(
    *,
    scenario_evidence: EvidencePackRead,
    as_of_date: date,
) -> EvidencePackRead:
    unknown_items = list(scenario_evidence.unknown)
    unknown_items.append(
        EvidenceItemRead(
            polarity=EvidencePolarity.UNKNOWN,
            claim_text=PRE_SCORE_NOTE,
            topic="assessment_state",
            importance=EvidenceImportance.HIGH,
            source_class=SourceClass.ANALYST_DERIVED,
            source_label="Phase 5A assessment foundation",
            source_url=None,
            source_snapshot_id=None,
            raw_asset_id=None,
            excerpt_text=f"Frozen as_of_date {as_of_date.isoformat()}",
            verified_status=VerifiedStatus.VERIFIED,
        )
    )
    return EvidencePackRead(
        for_=list(scenario_evidence.for_),
        against=list(scenario_evidence.against),
        unknown=unknown_items,
    )


def _persist_evidence_items(
    *,
    session: Session,
    run: AssessmentRun,
    evidence: EvidencePackRead,
) -> None:
    run.evidence_items.clear()
    for item in [*evidence.for_, *evidence.against, *evidence.unknown]:
        run.evidence_items.append(
            EvidenceItem(
                assessment_run_id=run.id,
                polarity=item.polarity,
                topic=item.topic,
                claim_text=item.claim_text,
                importance=item.importance,
                source_class=item.source_class,
                source_label=item.source_label,
                source_url=item.source_url,
                source_snapshot_id=item.source_snapshot_id,
                raw_asset_id=item.raw_asset_id,
                excerpt_text=item.excerpt_text,
                verified_status=item.verified_status,
            )
        )
    session.flush()


def _upsert_assessment_result(
    *,
    session: Session,
    run: AssessmentRun,
    scenario: SiteScenario,
    extant_permission,
    comparable_count: int,
    coverage_json: dict[str, object],
) -> AssessmentResult:
    coverage_rows = list(coverage_json.get("source_coverage") or [])
    coverage_gap_count = sum(
        1
        for row in coverage_rows
        if str(row.get("coverage_status") or "UNKNOWN").upper() != "COMPLETE"
    )
    manual_review_required = bool(
        extant_permission.manual_review_required
        or scenario.manual_review_required
        or coverage_gap_count > 0
        or run.site.manual_review_required
    )
    review_status = ReviewStatus.REQUIRED if manual_review_required else ReviewStatus.NOT_REQUIRED
    result = run.result or AssessmentResult(assessment_run_id=run.id)
    result.eligibility_status = extant_permission.eligibility_status
    result.estimate_status = EstimateStatus.NONE
    result.review_status = review_status
    result.approval_probability_raw = None
    result.approval_probability_display = None
    result.estimate_quality = None
    result.source_coverage_quality = "GAPPED" if coverage_gap_count > 0 else "SUFFICIENT"
    result.geometry_quality = run.site.geom_confidence.value
    result.support_quality = "COMPARABLES_PRESENT" if comparable_count > 0 else "SPARSE"
    result.ood_status = None
    result.manual_review_required = manual_review_required
    result.result_json = {
        "phase": "Phase 5A",
        "score_execution_status": "NOT_IMPLEMENTED",
        "estimate_status": EstimateStatus.NONE.value,
        "model_release_sentinel": PRE_SCORE_MODEL_SENTINEL,
        "coverage_gap_count": coverage_gap_count,
        "comparable_count": comparable_count,
        "note": PRE_SCORE_NOTE,
    }
    result.published_at = None
    session.add(result)
    session.flush()
    return result


def _stable_result_payload(
    *,
    run: AssessmentRun,
    site: SiteCandidate,
    scenario: SiteScenario,
    feature_snapshot: AssessmentFeatureSnapshot,
    result: AssessmentResult,
    evidence: EvidencePackRead,
    comparable_result,
) -> dict[str, object]:
    return _build_stable_result_payload(
        site_id=site.id,
        scenario_id=scenario.id,
        as_of_date=run.as_of_date,
        red_line_geom_hash=scenario.red_line_geom_hash,
        feature_snapshot=feature_snapshot,
        result=result,
        evidence=evidence,
        comparables={
            "strategy": comparable_result.comparable_case_set.strategy,
            "approved": _serialize_comparable_members(comparable_result.approved_members),
            "refused": _serialize_comparable_members(comparable_result.refused_members),
        },
    )


def _upsert_prediction_ledger(
    *,
    session: Session,
    run: AssessmentRun,
    feature_snapshot: AssessmentFeatureSnapshot,
    comparable_result,
    evidence: EvidencePackRead,
    stable_payload: dict[str, object],
) -> PredictionLedger:
    source_snapshot_ids = set(feature_snapshot.coverage_json.get("source_snapshot_ids") or [])
    raw_asset_ids = set(feature_snapshot.coverage_json.get("raw_asset_ids") or [])
    for item in [*evidence.for_, *evidence.against, *evidence.unknown]:
        if item.source_snapshot_id is not None:
            source_snapshot_ids.add(str(item.source_snapshot_id))
        if item.raw_asset_id is not None:
            raw_asset_ids.add(str(item.raw_asset_id))
    source_snapshot_ids.update(comparable_result.source_snapshot_ids)
    raw_asset_ids.update(comparable_result.raw_asset_ids)

    ledger = run.prediction_ledger or PredictionLedger(assessment_run_id=run.id)
    ledger.site_geom_hash = run.scenario.red_line_geom_hash
    ledger.feature_hash = feature_snapshot.feature_hash
    ledger.model_release_id = None
    ledger.calibration_hash = None
    ledger.source_snapshot_ids_json = sorted(source_snapshot_ids)
    ledger.raw_asset_ids_json = sorted(raw_asset_ids)
    ledger.result_payload_hash = canonical_json_hash(stable_payload)
    ledger.response_json = stable_payload
    session.add(ledger)
    session.flush()
    return ledger


def _pack_from_rows(rows: list[EvidenceItem]) -> EvidencePackRead:
    return EvidencePackRead(
        for_=[_row_to_read(row) for row in rows if row.polarity == EvidencePolarity.FOR],
        against=[_row_to_read(row) for row in rows if row.polarity == EvidencePolarity.AGAINST],
        unknown=[_row_to_read(row) for row in rows if row.polarity == EvidencePolarity.UNKNOWN],
    )


def _row_to_read(row: EvidenceItem) -> EvidenceItemRead:
    return EvidenceItemRead(
        polarity=row.polarity,
        claim_text=row.claim_text,
        topic=row.topic,
        importance=row.importance,
        source_class=row.source_class,
        source_label=row.source_label,
        source_url=row.source_url,
        source_snapshot_id=row.source_snapshot_id,
        raw_asset_id=row.raw_asset_id,
        excerpt_text=row.excerpt_text,
        verified_status=row.verified_status,
    )


def _stable_comparable_payload(run: AssessmentRun) -> dict[str, object]:
    comparable_case_set = run.comparable_case_set
    if comparable_case_set is None:
        return {"strategy": None, "approved": [], "refused": []}
    return {
        "strategy": comparable_case_set.strategy,
        "approved": _serialize_comparable_members(
            [member for member in comparable_case_set.members if member.outcome.value == "APPROVED"]
        ),
        "refused": _serialize_comparable_members(
            [member for member in comparable_case_set.members if member.outcome.value == "REFUSED"]
        ),
    }


def _build_stable_result_payload(
    *,
    site_id: uuid.UUID,
    scenario_id: uuid.UUID,
    as_of_date: date,
    red_line_geom_hash: str | None,
    feature_snapshot: AssessmentFeatureSnapshot,
    result: AssessmentResult,
    evidence: EvidencePackRead,
    comparables: dict[str, object],
) -> dict[str, object]:
    return {
        "site_id": str(site_id),
        "scenario_id": str(scenario_id),
        "as_of_date": as_of_date.isoformat(),
        "red_line_geom_hash": red_line_geom_hash,
        "feature_hash": feature_snapshot.feature_hash,
        "feature_version": feature_snapshot.feature_version,
        "estimate_status": result.estimate_status.value,
        "eligibility_status": result.eligibility_status.value,
        "review_status": result.review_status.value,
        "manual_review_required": result.manual_review_required,
        "pre_score_note": PRE_SCORE_NOTE,
        "model_release_sentinel": PRE_SCORE_MODEL_SENTINEL,
        "result_json": result.result_json,
        "evidence": evidence.model_dump(by_alias=True, mode="json"),
        "comparables": comparables,
    }


def _serialize_comparable_members(
    members: list[ComparableCaseMember],
) -> list[dict[str, object]]:
    sorted_members = sorted(
        members,
        key=lambda member: (member.rank, str(member.planning_application_id)),
    )
    return [
        {
            "planning_application_id": str(member.planning_application_id),
            "similarity_score": member.similarity_score,
            "rank": member.rank,
            "fallback_path": member.fallback_path,
            "match_json": member.match_json,
        }
        for member in sorted_members
    ]


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
        .selectinload(ComparableCaseMember.planning_application),
        selectinload(AssessmentRun.prediction_ledger),
    )
