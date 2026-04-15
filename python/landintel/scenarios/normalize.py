from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from landintel.domain.enums import EligibilityStatus, ScenarioSource, ScenarioStatus
from landintel.domain.models import (
    AuditEvent,
    ScenarioReview,
    SiteCandidate,
    SiteConstraintFact,
    SiteGeometryRevision,
    SitePlanningLink,
    SitePolicyFact,
    SiteScenario,
)
from landintel.domain.schemas import ScenarioConfirmRequest
from landintel.planning.extant_permission import evaluate_site_extant_permission

from .suggest import refresh_scenario_evidence


class ScenarioNormalizeError(ValueError):
    pass


def confirm_or_update_scenario(
    *,
    session: Session,
    scenario_id: uuid.UUID,
    request: ScenarioConfirmRequest,
) -> SiteScenario:
    scenario = _load_scenario(session=session, scenario_id=scenario_id)
    site = scenario.site
    current_revision = _current_geometry_revision(site)
    if current_revision is None:
        raise ScenarioNormalizeError("No current site geometry revision is available.")

    action = request.action.upper().strip()
    before_payload = _scenario_payload(scenario)

    if action == "REJECT":
        scenario.status = ScenarioStatus.REJECTED
        scenario.manual_review_required = False
        scenario.is_current = False
        scenario.is_headline = False
        _append_warning_code(scenario, "SCENARIO_REJECTED")
        _add_review(
            session=session,
            scenario=scenario,
            review_status=ScenarioStatus.REJECTED,
            reviewed_by=request.requested_by,
            review_notes=request.review_notes,
        )
        _recompute_headline(site)
        _record_scenario_audit(
            session=session,
            action="scenario_rejected",
            scenario=scenario,
            before_json=before_payload,
        )
        session.flush()
        return scenario

    edits_present = _edits_present(request)
    target = scenario
    if edits_present:
        scenario.is_current = False
        scenario.is_headline = False
        target = _superseding_scenario(
            session=session,
            source=scenario,
            current_revision=current_revision,
            request=request,
        )
    else:
        target.site_geometry_revision_id = current_revision.id
        target.red_line_geom_hash = current_revision.geom_hash
        target.stale_reason = None
        target.scenario_source = ScenarioSource.ANALYST
        target.is_current = True
        _apply_request_fields(target=target, request=request)

    extant_permission = evaluate_site_extant_permission(session=session, site=site)
    if extant_permission.eligibility_status == EligibilityStatus.FAIL:
        target.status = ScenarioStatus.OUT_OF_SCOPE
        target.manual_review_required = True
        target.stale_reason = (
            "Current extant-permission state is exclusionary, so the scenario is out of scope."
        )
        _append_warning_code(target, "OUT_OF_SCOPE_EXTANT_PERMISSION")
    else:
        target.status = ScenarioStatus.ANALYST_CONFIRMED
        target.manual_review_required = False
        target.stale_reason = None
        _remove_warning_code(target, "SCENARIO_STALE_GEOMETRY")

    _add_review(
        session=session,
        scenario=target,
        review_status=target.status,
        reviewed_by=request.requested_by,
        review_notes=request.review_notes,
    )
    _recompute_headline(site, preferred=target)
    refresh_scenario_evidence(session=session, scenario=target)
    _record_scenario_audit(
        session=session,
        action=(
            "scenario_superseded_and_confirmed" if edits_present else "scenario_confirmed"
        ),
        scenario=target,
        before_json=before_payload,
    )
    session.flush()
    return target


def mark_site_scenarios_stale_for_geometry_change(
    *,
    session: Session,
    site: SiteCandidate,
    requested_by: str | None,
) -> int:
    changed = 0
    for scenario in site.scenarios:
        if not scenario.is_current or scenario.status == ScenarioStatus.REJECTED:
            continue
        if scenario.red_line_geom_hash == site.geom_hash:
            continue
        before_payload = _scenario_payload(scenario)
        scenario.manual_review_required = True
        scenario.stale_reason = (
            f"Site geometry changed to {site.geom_hash[:12]} and scenario review is required."
        )
        if scenario.status in {
            ScenarioStatus.AUTO_CONFIRMED,
            ScenarioStatus.ANALYST_CONFIRMED,
        }:
            scenario.status = ScenarioStatus.ANALYST_REQUIRED
        _append_warning_code(scenario, "SCENARIO_STALE_GEOMETRY")
        _add_review(
            session=session,
            scenario=scenario,
            review_status=scenario.status,
            reviewed_by=requested_by or "system",
            review_notes="Site geometry changed; scenario marked stale.",
        )
        _record_scenario_audit(
            session=session,
            action="scenario_marked_stale",
            scenario=scenario,
            before_json=before_payload,
        )
        changed += 1

    if changed:
        _recompute_headline(site)
    session.flush()
    return changed


def refresh_site_scenarios_after_rulepack_change(
    *,
    session: Session,
    site: SiteCandidate,
    requested_by: str | None,
) -> int:
    changed = 0
    for scenario in site.scenarios:
        if not scenario.is_current or scenario.status == ScenarioStatus.REJECTED:
            continue
        before_payload = _scenario_payload(scenario)
        scenario.manual_review_required = True
        scenario.stale_reason = "Borough rulepack changed and scenario review is required."
        if scenario.status == ScenarioStatus.AUTO_CONFIRMED:
            scenario.status = ScenarioStatus.ANALYST_REQUIRED
        _append_warning_code(scenario, "RULEPACK_REFRESH_REQUIRED")
        _add_review(
            session=session,
            scenario=scenario,
            review_status=scenario.status,
            reviewed_by=requested_by or "system",
            review_notes="Borough rulepack changed; scenario marked for refresh.",
        )
        _record_scenario_audit(
            session=session,
            action="scenario_rulepack_refresh_required",
            scenario=scenario,
            before_json=before_payload,
        )
        changed += 1
    session.flush()
    return changed


def _load_scenario(*, session: Session, scenario_id: uuid.UUID) -> SiteScenario:
    stmt = (
        select(SiteScenario)
        .where(SiteScenario.id == scenario_id)
        .options(
            selectinload(SiteScenario.reviews),
            selectinload(SiteScenario.site).selectinload(SiteCandidate.geometry_revisions),
            selectinload(SiteScenario.site).selectinload(SiteCandidate.scenarios).selectinload(
                SiteScenario.reviews
            ),
            selectinload(SiteScenario.site)
            .selectinload(SiteCandidate.planning_links)
            .selectinload(SitePlanningLink.planning_application),
            selectinload(SiteScenario.site).selectinload(SiteCandidate.policy_facts).selectinload(
                SitePolicyFact.policy_area
            ),
            selectinload(SiteScenario.site)
            .selectinload(SiteCandidate.constraint_facts)
            .selectinload(SiteConstraintFact.constraint_feature),
        )
    )
    scenario = session.execute(stmt).scalar_one_or_none()
    if scenario is None:
        raise ScenarioNormalizeError(f"Scenario '{scenario_id}' was not found.")
    return scenario


def _current_geometry_revision(site: SiteCandidate) -> SiteGeometryRevision | None:
    if not site.geometry_revisions:
        return None
    current = next(
        (row for row in site.geometry_revisions if row.geom_hash == site.geom_hash),
        None,
    )
    return current or site.geometry_revisions[0]


def _superseding_scenario(
    *,
    session: Session,
    source: SiteScenario,
    current_revision: SiteGeometryRevision,
    request: ScenarioConfirmRequest,
) -> SiteScenario:
    scenario = SiteScenario(
        id=uuid.uuid4(),
        site_id=source.site_id,
        template_key=source.template_key,
        template_version=source.template_version,
        proposal_form=source.proposal_form,
        units_assumed=source.units_assumed,
        route_assumed=source.route_assumed,
        height_band_assumed=source.height_band_assumed,
        net_developable_area_pct=source.net_developable_area_pct,
        housing_mix_assumed_json=dict(source.housing_mix_assumed_json),
        parking_assumption=source.parking_assumption,
        affordable_housing_assumption=source.affordable_housing_assumption,
        access_assumption=source.access_assumption,
        site_geometry_revision_id=current_revision.id,
        red_line_geom_hash=current_revision.geom_hash,
        scenario_source=ScenarioSource.ANALYST,
        status=ScenarioStatus.ANALYST_REQUIRED,
        supersedes_id=source.id,
        is_current=True,
        heuristic_rank=source.heuristic_rank,
        manual_review_required=True,
        stale_reason=None,
        rationale_json=dict(source.rationale_json or {}),
        evidence_json=dict(source.evidence_json or {}),
        created_by=request.requested_by or "analyst",
    )
    _apply_request_fields(target=scenario, request=request)
    session.add(scenario)
    session.flush()
    return scenario


def _apply_request_fields(*, target: SiteScenario, request: ScenarioConfirmRequest) -> None:
    if request.proposal_form is not None:
        target.proposal_form = request.proposal_form
    if request.units_assumed is not None:
        target.units_assumed = request.units_assumed
    if request.route_assumed is not None:
        target.route_assumed = request.route_assumed
    if request.height_band_assumed is not None:
        target.height_band_assumed = request.height_band_assumed
    if request.net_developable_area_pct is not None:
        target.net_developable_area_pct = request.net_developable_area_pct
    if request.housing_mix_assumed_json is not None:
        target.housing_mix_assumed_json = dict(request.housing_mix_assumed_json)
    if request.parking_assumption is not None:
        target.parking_assumption = request.parking_assumption
    if request.affordable_housing_assumption is not None:
        target.affordable_housing_assumption = request.affordable_housing_assumption
    if request.access_assumption is not None:
        target.access_assumption = request.access_assumption


def _edits_present(request: ScenarioConfirmRequest) -> bool:
    return any(
        value is not None
        for value in (
            request.proposal_form,
            request.units_assumed,
            request.route_assumed,
            request.height_band_assumed,
            request.net_developable_area_pct,
            request.housing_mix_assumed_json,
            request.parking_assumption,
            request.affordable_housing_assumption,
            request.access_assumption,
        )
    )


def _recompute_headline(site: SiteCandidate, preferred: SiteScenario | None = None) -> None:
    for scenario in site.scenarios:
        scenario.is_headline = False

    active = [
        row
        for row in site.scenarios
        if row.is_current and row.status != ScenarioStatus.REJECTED
    ]
    if preferred is not None and preferred in active:
        preferred.is_headline = True
        return

    confirmed = next(
        (
            row
            for row in active
            if row.status == ScenarioStatus.ANALYST_CONFIRMED and not row.stale_reason
        ),
        None,
    )
    if confirmed is not None:
        confirmed.is_headline = True
        return

    auto_confirmed = next(
        (
            row
            for row in active
            if row.status == ScenarioStatus.AUTO_CONFIRMED and not row.stale_reason
        ),
        None,
    )
    if auto_confirmed is not None:
        auto_confirmed.is_headline = True
        return

    ordered = sorted(
        active,
        key=lambda row: (
            row.heuristic_rank if row.heuristic_rank is not None else 999,
            row.updated_at,
            str(row.id),
        ),
    )
    if ordered:
        ordered[0].is_headline = True


def _append_warning_code(scenario: SiteScenario, code: str) -> None:
    rationale = dict(scenario.rationale_json or {})
    warning_codes = list(rationale.get("warning_codes") or [])
    if code not in warning_codes:
        warning_codes.append(code)
    rationale["warning_codes"] = warning_codes
    scenario.rationale_json = rationale


def _remove_warning_code(scenario: SiteScenario, code: str) -> None:
    rationale = dict(scenario.rationale_json or {})
    rationale["warning_codes"] = [
        item for item in list(rationale.get("warning_codes") or []) if item != code
    ]
    scenario.rationale_json = rationale


def _add_review(
    *,
    session: Session,
    scenario: SiteScenario,
    review_status: ScenarioStatus,
    reviewed_by: str | None,
    review_notes: str | None,
) -> None:
    session.add(
        ScenarioReview(
            scenario_id=scenario.id,
            review_status=review_status,
            review_notes=review_notes,
            reviewed_by=reviewed_by or "analyst",
        )
    )


def _record_scenario_audit(
    *,
    session: Session,
    action: str,
    scenario: SiteScenario,
    before_json: dict[str, Any] | None,
) -> None:
    session.add(
        AuditEvent(
            action=action,
            entity_type="site_scenario",
            entity_id=str(scenario.id),
            before_json=before_json,
            after_json=_scenario_payload(scenario),
        )
    )


def _scenario_payload(scenario: SiteScenario) -> dict[str, Any]:
    return {
        "scenario_id": str(scenario.id),
        "site_id": str(scenario.site_id),
        "template_key": scenario.template_key,
        "template_version": scenario.template_version,
        "proposal_form": scenario.proposal_form.value,
        "units_assumed": scenario.units_assumed,
        "route_assumed": scenario.route_assumed,
        "height_band_assumed": scenario.height_band_assumed,
        "net_developable_area_pct": scenario.net_developable_area_pct,
        "red_line_geom_hash": scenario.red_line_geom_hash,
        "scenario_source": scenario.scenario_source.value,
        "status": scenario.status.value,
        "is_current": scenario.is_current,
        "is_headline": scenario.is_headline,
        "manual_review_required": scenario.manual_review_required,
        "stale_reason": scenario.stale_reason,
    }
