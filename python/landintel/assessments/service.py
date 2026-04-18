from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from landintel.assessments.comparables import build_comparable_case_set
from landintel.domain.enums import (
    AssessmentRunState,
    BaselinePackStatus,
    EligibilityStatus,
    EstimateQuality,
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
    ModelRelease,
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
from landintel.domain.schemas import EvidenceItemRead, EvidencePackRead
from landintel.evidence.assemble import assemble_scenario_evidence, assemble_site_evidence
from landintel.features.build import build_feature_snapshot, canonical_json_hash
from landintel.planning.enrich import get_borough_baseline_pack
from landintel.planning.extant_permission import evaluate_site_extant_permission
from landintel.planning.historical_labels import rebuild_historical_case_labels
from landintel.scoring.release import (
    load_release_artifact_json,
    resolve_active_release,
)
from landintel.scoring.score import score_frozen_assessment
from landintel.storage.base import StorageAdapter
from landintel.valuation.service import (
    build_or_refresh_valuation_for_assessment,
    frozen_valuation_run,
)
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

ASSESSMENT_NAMESPACE = uuid.UUID("6f8c2b84-0ef7-4c40-891f-f1d54ef4f7ef")
PRE_SCORE_MODEL_SENTINEL = "PHASE5A_PRE_SCORE"
PRE_SCORE_NOTE = (
    "Assessment artifacts are frozen as of the requested date. Hidden scoring is only applied "
    "when an active hidden release exists, the relevant borough baseline pack is signed off, "
    "and no abstain rule blocks execution."
)
HIDDEN_SCORE_NOTE = (
    "Hidden score mode is active for this assessment. The probability remains non-speaking and "
    "internal-only in Phase 6A."
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
    storage: StorageAdapter | None = None,
) -> AssessmentRun:
    scenario = _load_scenario(session=session, scenario_id=scenario_id)
    site = scenario.site
    if site.id != site_id:
        raise AssessmentBuildError("Scenario does not belong to the requested site.")
    if scenario.status not in {ScenarioStatus.AUTO_CONFIRMED, ScenarioStatus.ANALYST_CONFIRMED}:
        raise AssessmentBuildError(
            "Assessment runs require a current confirmed scenario in Phase 6A."
        )
    if not scenario.is_current:
        raise AssessmentBuildError("Scenario is superseded and cannot anchor a new assessment run.")
    if scenario.red_line_geom_hash != site.geom_hash:
        raise AssessmentBuildError(
            "Scenario red-line geometry is stale. Reconfirm the scenario before assessment."
        )
    if as_of_date > date.today():
        raise AssessmentBuildError("Assessment as_of_date cannot be in the future.")

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

    rebuild_historical_case_labels(session=session, requested_by=requested_by or "assessment-run")

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

        extant_permission = evaluate_site_extant_permission(
            session=session,
            site=site,
            as_of_date=as_of_date,
        )
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
        comparable_payload = {
            "strategy": comparable_result.comparable_case_set.strategy,
            "approved": _serialize_comparable_members(comparable_result.approved_members),
            "refused": _serialize_comparable_members(comparable_result.refused_members),
        }

        active_release, release_scope_key = resolve_active_release(
            session=session,
            template_key=scenario.template_key,
            borough_id=site.borough_id,
        )
        scored_result = None
        score_execution_status = "NOT_IMPLEMENTED"
        note_text = PRE_SCORE_NOTE
        if (
            active_release is not None
            and storage is not None
            and extant_permission.eligibility_status.value == "PASS"
            and baseline_pack is not None
            and baseline_pack.status == BaselinePackStatus.SIGNED_OFF
        ):
            model_artifact = load_release_artifact_json(
                storage=storage,
                release=active_release,
                artifact="model",
            )
            calibration_artifact = load_release_artifact_json(
                storage=storage,
                release=active_release,
                artifact="calibration",
            )
            validation_artifact = load_release_artifact_json(
                storage=storage,
                release=active_release,
                artifact="validation",
            )
            if model_artifact and validation_artifact:
                scored_result = score_frozen_assessment(
                    model_artifact=model_artifact,
                    calibration_artifact=calibration_artifact,
                    validation_artifact=validation_artifact,
                    release_id=str(active_release.id),
                    feature_json=feature_snapshot.feature_json,
                    coverage_json=feature_snapshot.coverage_json,
                    site=site,
                    scenario=scenario,
                    evidence=assessment_evidence,
                    comparable_case_set=comparable_result.comparable_case_set,
                    comparable_payload=comparable_payload,
                )
                score_execution_status = "HIDDEN_ESTIMATE_AVAILABLE"
                note_text = HIDDEN_SCORE_NOTE
        elif active_release is None:
            score_execution_status = "NO_ACTIVE_HIDDEN_RELEASE"
        elif storage is None:
            score_execution_status = "STORAGE_UNAVAILABLE"
        elif baseline_pack is None or baseline_pack.status != BaselinePackStatus.SIGNED_OFF:
            score_execution_status = "BASELINE_PACK_NOT_SIGNED_OFF"
        # Prior guards already prove PASS is impossible here; only ABSTAIN can reach this branch.
        elif extant_permission.eligibility_status.value != "PASS":  # pragma: no branch
            score_execution_status = "ABSTAIN"

        result = _upsert_assessment_result(
            session=session,
            run=run,
            scenario=scenario,
            extant_permission=extant_permission,
            comparable_count=(
                len(comparable_result.approved_members) + len(comparable_result.refused_members)
            ),
            coverage_json=feature_snapshot.coverage_json,
            model_release=active_release,
            release_scope_key=release_scope_key,
            scored_result=scored_result,
            score_execution_status=score_execution_status,
            note_text=note_text,
        )
        valuation_run = None
        if extant_permission.eligibility_status == EligibilityStatus.PASS:
            valuation_run = build_or_refresh_valuation_for_assessment(
                session=session,
                assessment_run=run,
                requested_by=requested_by or "assessment-run",
            )
        stable_payload = _stable_result_payload(
            run=run,
            site=site,
            scenario=scenario,
            feature_snapshot=feature_snapshot,
            result=result,
            valuation_run=valuation_run,
            evidence=assessment_evidence,
            comparables=comparable_payload,
            note_text=note_text,
        )
        ledger = _upsert_prediction_ledger(
            session=session,
            run=run,
            feature_snapshot=feature_snapshot,
            comparable_result=comparable_result,
            evidence=assessment_evidence,
            stable_payload=stable_payload,
            model_release=active_release,
            valuation_run=valuation_run,
            release_scope_key=release_scope_key,
            response_mode="HIDDEN_SCORE" if scored_result else "PRE_SCORE",
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
    storage: StorageAdapter | None = None,
) -> AssessmentRun:
    run = session.execute(
        select(AssessmentRun)
        .where(AssessmentRun.id == assessment_run_id)
        .options(*_assessment_load_options())
    ).scalar_one_or_none()
    if run is None:
        raise AssessmentBuildError(f"Assessment run '{assessment_run_id}' was not found.")
    if run.state == AssessmentRunState.READY:
        return run
    return create_or_refresh_assessment_run(
        session=session,
        site_id=run.site_id,
        scenario_id=run.scenario_id,
        as_of_date=run.as_of_date,
        requested_by=requested_by or run.requested_by,
        storage=storage,
    )


def verify_assessment_replay(
    *,
    session: Session,
    assessment_run: AssessmentRun,
    storage: StorageAdapter | None = None,
) -> dict[str, object]:
    if (
        assessment_run.feature_snapshot is None
        or assessment_run.result is None
        or assessment_run.prediction_ledger is None
    ):
        raise AssessmentBuildError("Assessment run is incomplete and cannot be replay-verified.")

    evidence = _pack_from_rows(assessment_run.evidence_items)
    comparable_payload = _stable_comparable_payload(assessment_run)
    scored_fields_match = True
    if assessment_run.result.model_release_id and storage is not None:
        release = session.get(ModelRelease, assessment_run.result.model_release_id)
        if release is None:
            raise AssessmentBuildError("Stored model release could not be loaded for replay.")
        model_artifact = load_release_artifact_json(
            storage=storage,
            release=release,
            artifact="model",
        )
        validation_artifact = load_release_artifact_json(
            storage=storage,
            release=release,
            artifact="validation",
        )
        calibration_artifact = load_release_artifact_json(
            storage=storage,
            release=release,
            artifact="calibration",
        )
        if model_artifact and validation_artifact:
            replay_score = score_frozen_assessment(
                model_artifact=model_artifact,
                calibration_artifact=calibration_artifact,
                validation_artifact=validation_artifact,
                release_id=str(release.id),
                feature_json=assessment_run.feature_snapshot.feature_json,
                coverage_json=assessment_run.feature_snapshot.coverage_json,
                site=assessment_run.site,
                scenario=assessment_run.scenario,
                evidence=evidence,
                comparable_case_set=assessment_run.comparable_case_set,
                comparable_payload=comparable_payload,
            )
            stored_result_json = dict(assessment_run.result.result_json or {})
            scored_fields_match = (
                float(assessment_run.result.approval_probability_raw or 0.0)
                == float(replay_score["approval_probability_raw"])
                and (assessment_run.result.approval_probability_display or "")
                == str(replay_score["approval_probability_display"])
                and (
                    assessment_run.result.estimate_quality.value
                    if assessment_run.result.estimate_quality
                    else None
                )
                == str(replay_score["estimate_quality"])
                and (assessment_run.result.source_coverage_quality or "")
                == str(replay_score["source_coverage_quality"])
                and (assessment_run.result.geometry_quality or "")
                == str(replay_score["geometry_quality"])
                and (assessment_run.result.support_quality or "")
                == str(replay_score["support_quality"])
                and (assessment_run.result.scenario_quality or "")
                == str(replay_score["scenario_quality"])
                and (assessment_run.result.ood_quality or "") == str(replay_score["ood_quality"])
                and (assessment_run.result.ood_status or "") == str(replay_score["ood_status"])
                and assessment_run.result.manual_review_required
                == bool(replay_score["manual_review_required"])
                and dict((assessment_run.result.result_json or {}).get("explanation") or {})
                == dict(replay_score["explanation"] or {})
                and dict(stored_result_json.get("support_summary") or {})
                == dict(replay_score["support_summary"] or {})
                and dict(stored_result_json.get("validation_summary") or {})
                == dict(replay_score["validation_summary"] or {})
            )
    stable_payload = _build_stable_result_payload(
        site_id=assessment_run.site_id,
        scenario_id=assessment_run.scenario_id,
        as_of_date=assessment_run.as_of_date,
        red_line_geom_hash=_frozen_red_line_geom_hash(assessment_run=assessment_run),
        feature_snapshot=assessment_run.feature_snapshot,
        result=assessment_run.result,
        valuation_payload=(
            None
            if frozen_valuation_run(assessment_run) is None
            or frozen_valuation_run(assessment_run).result is None
            else _serialize_valuation_payload(frozen_valuation_run(assessment_run))
        ),
        evidence=evidence,
        comparables=comparable_payload,
        note_text=_note_for_result(assessment_run.result),
    )
    payload_hash = canonical_json_hash(stable_payload)
    replay_passed = (
        canonical_json_hash(assessment_run.feature_snapshot.feature_json)
        == assessment_run.feature_snapshot.feature_hash
        and payload_hash == assessment_run.prediction_ledger.result_payload_hash
        and scored_fields_match
    )
    result = {
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
        "scored_fields_match": scored_fields_match,
        "replay_passed": replay_passed,
    }
    _record_replay_verification(assessment_run=assessment_run, check=result)
    session.flush()
    return result


def replay_verify_all_assessments(
    session: Session,
    *,
    storage: StorageAdapter | None = None,
) -> dict[str, object]:
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
    checks = [
        verify_assessment_replay(session=session, assessment_run=run, storage=storage)
        for run in runs
    ]
    failures = [check for check in checks if not check["replay_passed"]]
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
    run.feature_snapshot = row
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
            source_label="Phase 6A hidden scoring foundation",
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
    model_release: ModelRelease | None,
    release_scope_key: str,
    scored_result: dict[str, object] | None,
    score_execution_status: str,
    note_text: str,
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
    if scored_result is None:
        result.model_release_id = None
        result.release_scope_key = None
        result.estimate_status = EstimateStatus.NONE
        result.review_status = review_status
        result.approval_probability_raw = None
        result.approval_probability_display = None
        result.estimate_quality = None
        result.source_coverage_quality = "LOW" if coverage_gap_count > 0 else "MEDIUM"
        result.geometry_quality = run.site.geom_confidence.value
        result.support_quality = "COMPARABLES_PRESENT" if comparable_count > 0 else "SPARSE"
        result.scenario_quality = "MEDIUM" if scenario.manual_review_required else "HIGH"
        result.ood_quality = None
        result.ood_status = None
        result.manual_review_required = manual_review_required
        result.result_json = {
            "phase": "Phase 6A",
            "score_execution_status": score_execution_status,
            "estimate_status": EstimateStatus.NONE.value,
            "model_release_sentinel": PRE_SCORE_MODEL_SENTINEL,
            "coverage_gap_count": coverage_gap_count,
            "comparable_count": comparable_count,
            "note": note_text,
            "hidden_mode_only": False,
        }
        result.published_at = None
    else:
        result.model_release_id = None if model_release is None else model_release.id
        result.release_scope_key = release_scope_key
        result.estimate_status = (
            EstimateStatus.ESTIMATE_AVAILABLE_MANUAL_REVIEW_REQUIRED
            if scored_result["manual_review_required"]
            else EstimateStatus.ESTIMATE_AVAILABLE
        )
        result.review_status = (
            ReviewStatus.REQUIRED
            if scored_result["manual_review_required"]
            else ReviewStatus.NOT_REQUIRED
        )
        result.approval_probability_raw = float(scored_result["approval_probability_raw"])
        result.approval_probability_display = str(scored_result["approval_probability_display"])
        result.estimate_quality = EstimateQuality(str(scored_result["estimate_quality"]))
        result.source_coverage_quality = str(scored_result["source_coverage_quality"])
        result.geometry_quality = str(scored_result["geometry_quality"])
        result.support_quality = str(scored_result["support_quality"])
        result.scenario_quality = str(scored_result["scenario_quality"])
        result.ood_quality = str(scored_result["ood_quality"])
        result.ood_status = str(scored_result["ood_status"])
        result.manual_review_required = bool(scored_result["manual_review_required"])
        result.result_json = {
            "phase": "Phase 6A",
            "score_execution_status": score_execution_status,
            "hidden_mode_only": True,
            "support_summary": scored_result["support_summary"],
            "validation_summary": scored_result["validation_summary"],
            "explanation": scored_result["explanation"],
            "note": note_text,
        }
        result.published_at = datetime.now(UTC)
    session.add(result)
    session.flush()
    run.result = result
    return result


def _stable_result_payload(
    *,
    run: AssessmentRun,
    site: SiteCandidate,
    scenario: SiteScenario,
    feature_snapshot: AssessmentFeatureSnapshot,
    result: AssessmentResult,
    valuation_run,
    evidence: EvidencePackRead,
    comparables: dict[str, object],
    note_text: str,
) -> dict[str, object]:
    return _build_stable_result_payload(
        site_id=site.id,
        scenario_id=scenario.id,
        as_of_date=run.as_of_date,
        red_line_geom_hash=_frozen_red_line_geom_hash(assessment_run=run),
        feature_snapshot=feature_snapshot,
        result=result,
        valuation_payload=_serialize_valuation_payload(valuation_run),
        evidence=evidence,
        comparables=comparables,
        note_text=note_text,
    )


def _upsert_prediction_ledger(
    *,
    session: Session,
    run: AssessmentRun,
    feature_snapshot: AssessmentFeatureSnapshot,
    comparable_result,
    evidence: EvidencePackRead,
    stable_payload: dict[str, object],
    model_release: ModelRelease | None,
    valuation_run,
    release_scope_key: str,
    response_mode: str,
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

    ledger = run.prediction_ledger or PredictionLedger(assessment_run=run)
    run.prediction_ledger = ledger
    ledger.site_geom_hash = _frozen_red_line_geom_hash(assessment_run=run)
    ledger.feature_hash = feature_snapshot.feature_hash
    ledger.model_release_id = (
        None
        if response_mode != "HIDDEN_SCORE" or model_release is None
        else model_release.id
    )
    ledger.release_scope_key = release_scope_key if response_mode == "HIDDEN_SCORE" else None
    ledger.calibration_hash = (
        None
        if response_mode != "HIDDEN_SCORE" or model_release is None
        else model_release.calibration_artifact_hash
    )
    ledger.model_artifact_hash = (
        None
        if response_mode != "HIDDEN_SCORE" or model_release is None
        else model_release.model_artifact_hash
    )
    ledger.validation_artifact_hash = (
        None
        if response_mode != "HIDDEN_SCORE" or model_release is None
        else model_release.validation_artifact_hash
    )
    ledger.valuation_run_id = None if valuation_run is None else valuation_run.id
    ledger.response_mode = response_mode
    ledger.source_snapshot_ids_json = sorted(source_snapshot_ids)
    ledger.raw_asset_ids_json = sorted(raw_asset_ids)
    ledger.result_payload_hash = canonical_json_hash(stable_payload)
    ledger.response_json = stable_payload
    ledger.replay_verification_status = "HASH_CAPTURED"
    ledger.replay_verified_at = None
    ledger.replay_verification_note = (
        "Stable payload hash captured; explicit replay verification has not run yet."
    )
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


def _serialize_valuation_payload(valuation_run: ValuationRun | None) -> dict[str, object] | None:
    if valuation_run is None or valuation_run.result is None:
        return None
    result = valuation_run.result
    return {
        "valuation_run_id": str(valuation_run.id),
        "valuation_assumption_set_id": str(valuation_run.valuation_assumption_set_id),
        "valuation_assumption_version": valuation_run.valuation_assumption_set.version,
        "post_permission_value_low": result.post_permission_value_low,
        "post_permission_value_mid": result.post_permission_value_mid,
        "post_permission_value_high": result.post_permission_value_high,
        "uplift_low": result.uplift_low,
        "uplift_mid": result.uplift_mid,
        "uplift_high": result.uplift_high,
        "expected_uplift_mid": result.expected_uplift_mid,
        "valuation_quality": result.valuation_quality.value,
        "manual_review_required": result.manual_review_required,
        "basis_json": result.basis_json,
        "sense_check_json": result.sense_check_json,
        "result_json": result.result_json,
        "payload_hash": result.payload_hash,
    }


def _frozen_red_line_geom_hash(*, assessment_run: AssessmentRun) -> str | None:
    if (
        assessment_run.prediction_ledger is not None
        and assessment_run.prediction_ledger.site_geom_hash
    ):
        return assessment_run.prediction_ledger.site_geom_hash
    return assessment_run.scenario.red_line_geom_hash


def _record_replay_verification(
    *,
    assessment_run: AssessmentRun,
    check: dict[str, object],
) -> None:
    ledger = assessment_run.prediction_ledger
    if ledger is None:
        return
    ledger.replay_verification_status = "VERIFIED" if check["replay_passed"] else "FAILED"
    ledger.replay_verified_at = datetime.now(UTC)
    if check["replay_passed"]:
        ledger.replay_verification_note = (
            "Replay verification passed for frozen features, scored fields, and payload."
        )
        return
    failing_checks = [
        label
        for label in (
            "feature_hash_matches",
            "payload_hash_matches",
            "scored_fields_match",
        )
        if not check[label]
    ]
    ledger.replay_verification_note = "Replay verification failed: " + ", ".join(
        failing_checks
    )


def _build_stable_result_payload(
    *,
    site_id: uuid.UUID,
    scenario_id: uuid.UUID,
    as_of_date: date,
    red_line_geom_hash: str | None,
    feature_snapshot: AssessmentFeatureSnapshot,
    result: AssessmentResult,
    valuation_payload: dict[str, object] | None,
    evidence: EvidencePackRead,
    comparables: dict[str, object],
    note_text: str,
    result_json_override: dict[str, object] | None = None,
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
        "approval_probability_raw": result.approval_probability_raw,
        "approval_probability_display": result.approval_probability_display,
        "estimate_quality": (
            None if result.estimate_quality is None else result.estimate_quality.value
        ),
        "source_coverage_quality": result.source_coverage_quality,
        "geometry_quality": result.geometry_quality,
        "support_quality": result.support_quality,
        "scenario_quality": result.scenario_quality,
        "ood_quality": result.ood_quality,
        "ood_status": result.ood_status,
        "note": note_text,
        "model_release_id": (
            None if result.model_release_id is None else str(result.model_release_id)
        ),
        "release_scope_key": result.release_scope_key,
        "model_release_sentinel": PRE_SCORE_MODEL_SENTINEL,
        "result_json": result.result_json if result_json_override is None else result_json_override,
        "valuation": valuation_payload,
        "evidence": evidence.model_dump(by_alias=True, mode="json"),
        "comparables": comparables,
    }


def _note_for_result(result: AssessmentResult) -> str:
    if result.approval_probability_raw is not None:
        return HIDDEN_SCORE_NOTE
    return str((result.result_json or {}).get("note") or PRE_SCORE_NOTE)


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
        selectinload(AssessmentRun.valuation_runs).selectinload(ValuationRun.result),
        selectinload(AssessmentRun.valuation_runs).selectinload(
            ValuationRun.valuation_assumption_set
        ),
    )
