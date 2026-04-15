from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from landintel.domain.enums import (
    BaselinePackStatus,
    EligibilityStatus,
    ExtantPermissionStatus,
    GeomConfidence,
    ScenarioSource,
    ScenarioStatus,
    SourceFreshnessStatus,
)
from landintel.domain.models import (
    BoroughBaselinePack,
    BoroughRulepack,
    ListingItem,
    PlanningApplication,
    PlanningApplicationDocument,
    SiteCandidate,
    SiteConstraintFact,
    SiteGeometryRevision,
    SitePlanningLink,
    SitePolicyFact,
    SiteScenario,
)
from landintel.domain.schemas import (
    ScenarioExclusionRead,
    ScenarioReasonRead,
    SiteScenarioSuggestResponse,
)
from landintel.evidence.assemble import assemble_scenario_evidence, assemble_site_evidence
from landintel.planning.enrich import get_borough_baseline_pack
from landintel.planning.extant_permission import evaluate_site_extant_permission

from .catalog import get_enabled_scenario_templates

SCENARIO_NAMESPACE = uuid.UUID("5b564c6e-5131-47cc-b387-76acfc8e5247")


@dataclass(slots=True)
class CandidateSupport:
    application: PlanningApplication | None
    strong: bool


@dataclass(slots=True)
class ScenarioCandidate:
    template_key: str
    template_version: str
    proposal_form: str
    units_assumed: int
    route_assumed: str
    height_band_assumed: str
    net_developable_area_pct: float
    housing_mix_assumed_json: dict[str, Any]
    parking_assumption: str | None
    affordable_housing_assumption: str | None
    access_assumption: str | None
    heuristic_rank: int
    score: int
    status: ScenarioStatus
    manual_review_required: bool
    reason_codes: list[ScenarioReasonRead]
    missing_data_flags: list[str]
    warning_codes: list[str]
    support: CandidateSupport


def suggest_scenarios_for_site(
    *,
    session: Session,
    site_id: uuid.UUID,
    requested_by: str | None,
    template_keys: list[str] | None = None,
    manual_seed: bool = False,
) -> SiteScenarioSuggestResponse:
    site = _load_site(session=session, site_id=site_id)
    return refresh_site_scenarios(
        session=session,
        site=site,
        requested_by=requested_by,
        template_keys=template_keys,
        manual_seed=manual_seed,
    )


def refresh_site_scenarios(
    *,
    session: Session,
    site: SiteCandidate,
    requested_by: str | None,
    template_keys: list[str] | None = None,
    manual_seed: bool = False,
) -> SiteScenarioSuggestResponse:
    templates = get_enabled_scenario_templates(session, template_keys=template_keys)
    baseline_pack = get_borough_baseline_pack(session=session, borough_id=site.borough_id)
    extant_permission = evaluate_site_extant_permission(session=session, site=site)
    site_evidence = assemble_site_evidence(
        session=session,
        site=site,
        extant_permission=extant_permission,
    )
    current_revision = _current_geometry_revision(site)

    if current_revision is None:
        return SiteScenarioSuggestResponse(
            site_id=site.id,
            headline_scenario_id=None,
            items=[],
            excluded_templates=[
                ScenarioExclusionRead(
                    template_key=template.key,
                    reasons=[
                        ScenarioReasonRead(
                            code="NO_GEOMETRY_REVISION",
                            message="No current site geometry revision is available to freeze.",
                        )
                    ],
                    missing_data_flags=["NO_GEOMETRY_REVISION"],
                    warning_codes=["ANALYST_CONFIRMATION_REQUIRED"],
                )
                for template in templates
            ],
        )

    persisted: list[SiteScenario] = []
    exclusions: list[ScenarioExclusionRead] = []
    for template in templates:
        candidate, exclusion = _evaluate_template_candidate(
            session=session,
            site=site,
            baseline_pack=baseline_pack,
            template=template,
            extant_permission=extant_permission,
            manual_seed=manual_seed,
        )
        if exclusion is not None:
            exclusions.append(exclusion)
            continue
        if candidate is None:
            continue
        scenario = _persist_candidate(
            session=session,
            site=site,
            current_revision=current_revision,
            candidate=candidate,
            requested_by=requested_by,
            site_evidence=site_evidence,
            baseline_pack=baseline_pack,
            extant_permission=extant_permission,
        )
        persisted.append(scenario)

    persisted.sort(
        key=lambda item: (
            item.heuristic_rank if item.heuristic_rank is not None else 999,
            item.updated_at,
            str(item.id),
        )
    )
    headline_id = _assign_headline_scenario(session=session, site=site, new_scenarios=persisted)
    _mark_stale_current_auto_scenarios(
        session=session,
        site=site,
        keep_ids={scenario.id for scenario in persisted},
    )
    session.flush()

    from landintel.services.scenarios_readback import (
        serialize_site_scenario_summary,
    )

    items = [
        serialize_site_scenario_summary(
            session=session,
            scenario=scenario,
            baseline_pack=baseline_pack,
            site=site,
        )
        for scenario in persisted
    ]
    return SiteScenarioSuggestResponse(
        site_id=site.id,
        headline_scenario_id=headline_id,
        items=items,
        excluded_templates=exclusions,
    )


def refresh_scenario_evidence(
    *,
    session: Session,
    scenario: SiteScenario,
) -> None:
    site = scenario.site
    extant_permission = evaluate_site_extant_permission(session=session, site=site)
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
    )
    scenario.evidence_json = scenario_evidence.model_dump(by_alias=True, mode="json")


def _load_site(*, session: Session, site_id: uuid.UUID) -> SiteCandidate:
    stmt = (
        select(SiteCandidate)
        .where(SiteCandidate.id == site_id)
        .options(
            selectinload(SiteCandidate.borough),
            selectinload(SiteCandidate.current_listing).selectinload(ListingItem.source),
            selectinload(SiteCandidate.geometry_revisions),
            selectinload(SiteCandidate.planning_links)
            .selectinload(SitePlanningLink.planning_application)
            .selectinload(PlanningApplication.documents)
            .selectinload(PlanningApplicationDocument.asset),
            selectinload(SiteCandidate.policy_facts).selectinload(SitePolicyFact.policy_area),
            selectinload(SiteCandidate.constraint_facts).selectinload(
                SiteConstraintFact.constraint_feature
            ),
            selectinload(SiteCandidate.scenarios).selectinload(SiteScenario.reviews),
        )
    )
    site = session.execute(stmt).scalar_one()
    return site


def _current_geometry_revision(site: SiteCandidate) -> SiteGeometryRevision | None:
    if not site.geometry_revisions:
        return None
    current = next(
        (row for row in site.geometry_revisions if row.geom_hash == site.geom_hash),
        None,
    )
    return current or site.geometry_revisions[0]


def _evaluate_template_candidate(
    *,
    session: Session,
    site: SiteCandidate,
    baseline_pack: BoroughBaselinePack | None,
    template,
    extant_permission,
    manual_seed: bool,
) -> tuple[ScenarioCandidate | None, ScenarioExclusionRead | None]:
    template_key = str(template.key)
    template_config = dict(template.config_json or {})
    rulepack = _rulepack_for_template(baseline_pack=baseline_pack, template_key=template_key)
    rule_json = dict(rulepack.rule_json or {}) if rulepack is not None else {}
    scenario_rules = dict(rule_json.get("scenario_rules") or {})

    reasons: list[ScenarioReasonRead] = []
    missing_data_flags: list[str] = []
    warning_codes: list[str] = []

    if rulepack is None:
        return None, ScenarioExclusionRead(
            template_key=template_key,
            reasons=[
                ScenarioReasonRead(
                    code="RULEPACK_MISSING",
                    message=(
                        "No borough rulepack is loaded for this template in the "
                        "controlling borough."
                    ),
                )
            ],
            missing_data_flags=["RULEPACK_MISSING"],
            warning_codes=["ANALYST_CONFIRMATION_REQUIRED"],
        )

    citations = list(rule_json.get("citations") or [])
    if not _citations_complete(citations):
        return None, ScenarioExclusionRead(
            template_key=template_key,
            reasons=[
                ScenarioReasonRead(
                    code="RULEPACK_CITATIONS_MISSING",
                    message="Rulepack citations are incomplete, so the template stays blocked.",
                )
            ],
            missing_data_flags=["RULEPACK_CITATIONS_MISSING"],
            warning_codes=["ANALYST_CONFIRMATION_REQUIRED"],
        )

    if extant_permission.status == ExtantPermissionStatus.ACTIVE_EXTANT_PERMISSION_FOUND:
        return None, ScenarioExclusionRead(
            template_key=template_key,
            reasons=[
                ScenarioReasonRead(
                    code="ACTIVE_EXTANT_PERMISSION_FOUND",
                    message=(
                        "Material active extant permission evidence is exclusionary for new "
                        "scenario suggestion in this phase."
                    ),
                )
            ],
            missing_data_flags=[],
            warning_codes=["OUT_OF_SCOPE"],
        )

    if site.site_area_sqm <= 0:
        return None, ScenarioExclusionRead(
            template_key=template_key,
            reasons=[
                ScenarioReasonRead(
                    code="SITE_AREA_UNAVAILABLE",
                    message="No usable site area is available for deterministic template sizing.",
                )
            ],
            missing_data_flags=["SITE_AREA_UNAVAILABLE"],
            warning_codes=["ANALYST_CONFIRMATION_REQUIRED"],
        )

    site_area_range = dict(
        scenario_rules.get("site_area_sqm_range")
        or template_config.get("site_area_sqm_range")
        or {}
    )
    min_site_area = float(site_area_range.get("min", 0))
    max_site_area = float(site_area_range.get("max", 999999))
    if not manual_seed and not (min_site_area <= site.site_area_sqm <= max_site_area):
        return None, ScenarioExclusionRead(
            template_key=template_key,
            reasons=[
                ScenarioReasonRead(
                    code="SITE_AREA_OUTSIDE_TEMPLATE_RANGE",
                    message=(
                        f"Site area {round(site.site_area_sqm, 1)} sqm falls outside the "
                        f"{template_key} operating range."
                    ),
                    source_label=f"{site.display_name} geometry",
                )
            ],
            missing_data_flags=[],
            warning_codes=[],
        )

    units_range = dict(
        scenario_rules.get("units_range") or template_config.get("units_range") or {}
    )
    min_units = int(units_range.get("min", 1))
    max_units = int(units_range.get("max", min_units))
    default_net_pct = float(
        scenario_rules.get("default_net_developable_area_pct")
        or template_config.get("default_net_developable_area_pct")
        or 0.7
    )
    target_sqm_per_home = float(template_config.get("target_sqm_per_home") or 180.0)
    capacity_units = max(
        min_units,
        min(
            max_units,
            math.floor((site.site_area_sqm * default_net_pct) / max(target_sqm_per_home, 1.0)),
        ),
    )

    preferred_route = str(
        scenario_rules.get("preferred_route") or template_config.get("default_route") or "FULL"
    )
    allowed_routes = list(scenario_rules.get("allowed_routes") or [preferred_route])
    if preferred_route not in allowed_routes:
        allowed_routes.append(preferred_route)

    proposal_form = str(
        template_config.get("default_proposal_form")
        or (scenario_rules.get("allowed_proposal_forms") or ["REDEVELOPMENT"])[0]
    )
    height_band = str(
        scenario_rules.get("default_height_band")
        or template_config.get("default_height_band")
        or "MID_RISE"
    )
    support = _nearest_historical_support(
        site=site,
        min_units=min_units,
        max_units=max_units,
        route_assumed=preferred_route,
    )
    if support.application is not None and support.application.units_proposed is not None:
        capacity_units = max(
            min_units,
            min(max_units, int(support.application.units_proposed)),
        )
        reasons.append(
            ScenarioReasonRead(
                code="NEAREST_HISTORICAL_UNITS_SUPPORT",
                message=(
                    f"Nearest historical residential application supports {capacity_units} units."
                ),
                source_label=support.application.external_ref,
                source_url=support.application.source_url,
                source_snapshot_id=support.application.source_snapshot_id,
                raw_asset_id=(
                    support.application.documents[0].asset_id
                    if support.application.documents
                    else None
                ),
            )
        )
    else:
        reasons.append(
            ScenarioReasonRead(
                code="AREA_CAPACITY_HEURISTIC",
                message=(
                    f"Area-based capacity heuristic suggests {capacity_units} units "
                    f"inside the {template_key} range."
                ),
                source_label="site geometry",
            )
        )

    reasons.append(
        ScenarioReasonRead(
            code="RULEPACK_ROUTE_ALLOWED",
            message=f"Rulepack route assumption is {preferred_route}.",
            source_label=f"{site.borough_id or 'borough'} rulepack",
        )
    )
    reasons.append(
        ScenarioReasonRead(
            code="SITE_AREA_FITS_TEMPLATE",
            message=(
                f"Site area {round(site.site_area_sqm, 1)} sqm fits the {template_key} "
                "operating band."
            ),
            source_label="site geometry",
        )
    )

    if site.geom_confidence not in {GeomConfidence.HIGH, GeomConfidence.MEDIUM}:
        missing_data_flags.append("GEOMETRY_CONFIDENCE_BELOW_MEDIUM")
        warning_codes.append("ANALYST_CONFIRMATION_REQUIRED")

    if baseline_pack is None:
        missing_data_flags.append("BASELINE_PACK_MISSING")
    elif baseline_pack.status != BaselinePackStatus.PILOT_READY:
        warning_codes.append("RULEPACK_NOT_PILOT_READY")

    if extant_permission.eligibility_status == EligibilityStatus.ABSTAIN:
        missing_data_flags.append("EXTANT_PERMISSION_ABSTAIN")
        warning_codes.append("ANALYST_CONFIRMATION_REQUIRED")

    if extant_permission.coverage_gaps:
        missing_data_flags.extend(
            _dedupe(
                gap.code
                for gap in extant_permission.coverage_gaps
                if gap.code.startswith("MANDATORY_SOURCE_")
            )
        )
        warning_codes.append("SOURCE_COVERAGE_GAP")

    if support.strong:
        reasons.append(
            ScenarioReasonRead(
                code="STRONG_HISTORICAL_SUPPORT",
                message=(
                    "Nearest historical support is strong enough for conservative "
                    "scenario ranking."
                ),
                source_label=support.application.external_ref if support.application else None,
                source_url=support.application.source_url if support.application else None,
                source_snapshot_id=(
                    support.application.source_snapshot_id if support.application else None
                ),
                raw_asset_id=(
                    support.application.documents[0].asset_id
                    if support.application and support.application.documents
                    else None
                ),
            )
        )
    else:
        missing_data_flags.append("NEAREST_HISTORICAL_SUPPORT_NOT_STRONG")
        warning_codes.append("ANALYST_CONFIRMATION_REQUIRED")

    if rulepack.freshness_status == SourceFreshnessStatus.STALE:
        warning_codes.append("RULEPACK_STALE")
    if baseline_pack is not None and baseline_pack.freshness_status == SourceFreshnessStatus.STALE:
        warning_codes.append("BASELINE_PACK_STALE")

    score = 0
    score += 4 if min_site_area <= site.site_area_sqm <= max_site_area else -4
    score += 3 if support.application is not None else 0
    score += 2 if support.strong else 0
    score += 1 if site.geom_confidence == GeomConfidence.HIGH else 0
    score -= len(missing_data_flags)
    score -= sum(1 for code in warning_codes if "STALE" in code)

    heuristic_rank = 100 - score
    auto_confirm, auto_confirm_reasons = _auto_confirm_allowed(
        site=site,
        template_key=template_key,
        preferred_route=preferred_route,
        support=support,
        extant_permission=extant_permission,
        missing_data_flags=missing_data_flags,
        warning_codes=warning_codes,
    )
    for code, message in auto_confirm_reasons:
        reasons.append(
            ScenarioReasonRead(
                code=code,
                message=message,
                source_label=f"{site.borough_id or 'borough'} rulepack",
            )
        )

    status = ScenarioStatus.AUTO_CONFIRMED if auto_confirm else ScenarioStatus.ANALYST_REQUIRED
    manual_review_required = status != ScenarioStatus.AUTO_CONFIRMED
    if manual_review_required and "ANALYST_CONFIRMATION_REQUIRED" not in warning_codes:
        warning_codes.append("ANALYST_CONFIRMATION_REQUIRED")

    return (
        ScenarioCandidate(
            template_key=template_key,
            template_version=str(template.version),
            proposal_form=proposal_form,
            units_assumed=capacity_units,
            route_assumed=preferred_route,
            height_band_assumed=height_band,
            net_developable_area_pct=default_net_pct,
            housing_mix_assumed_json=dict(template_config.get("default_housing_mix") or {}),
            parking_assumption=str(
                scenario_rules.get("parking_assumption")
                or template_config.get("default_parking_assumption")
                or ""
            )
            or None,
            affordable_housing_assumption=str(
                scenario_rules.get("affordable_housing_assumption")
                or template_config.get("default_affordable_housing_assumption")
                or ""
            )
            or None,
            access_assumption=str(
                scenario_rules.get("access_assumption")
                or template_config.get("default_access_assumption")
                or ""
            )
            or None,
            heuristic_rank=heuristic_rank,
            score=score,
            status=status,
            manual_review_required=manual_review_required,
            reason_codes=reasons,
            missing_data_flags=_dedupe(missing_data_flags),
            warning_codes=_dedupe(warning_codes),
            support=support,
        ),
        None,
    )


def _persist_candidate(
    *,
    session: Session,
    site: SiteCandidate,
    current_revision: SiteGeometryRevision,
    candidate: ScenarioCandidate,
    requested_by: str | None,
    site_evidence,
    baseline_pack: BoroughBaselinePack | None,
    extant_permission,
) -> SiteScenario:
    scenario_id = uuid.uuid5(
        SCENARIO_NAMESPACE,
        (
            "site-scenario:"
            f"{site.id}:{candidate.template_key}:{candidate.template_version}:"
            f"{current_revision.id}:{candidate.units_assumed}:{candidate.route_assumed}:"
            f"{candidate.proposal_form}"
        ),
    )
    scenario = session.get(SiteScenario, scenario_id)
    if scenario is None:
        scenario = SiteScenario(
            id=scenario_id,
            site_id=site.id,
            created_by=requested_by or "system",
        )
        session.add(scenario)

    scenario.site_id = site.id
    scenario.template_key = candidate.template_key
    scenario.template_version = candidate.template_version
    scenario.proposal_form = candidate.proposal_form
    scenario.units_assumed = candidate.units_assumed
    scenario.route_assumed = candidate.route_assumed
    scenario.height_band_assumed = candidate.height_band_assumed
    scenario.net_developable_area_pct = candidate.net_developable_area_pct
    scenario.housing_mix_assumed_json = dict(candidate.housing_mix_assumed_json)
    scenario.parking_assumption = candidate.parking_assumption
    scenario.affordable_housing_assumption = candidate.affordable_housing_assumption
    scenario.access_assumption = candidate.access_assumption
    scenario.site_geometry_revision_id = current_revision.id
    scenario.red_line_geom_hash = current_revision.geom_hash
    scenario.scenario_source = ScenarioSource.AUTO
    scenario.status = candidate.status
    scenario.is_current = True
    scenario.heuristic_rank = candidate.heuristic_rank
    scenario.manual_review_required = candidate.manual_review_required
    scenario.stale_reason = None
    scenario.rationale_json = {
        "reason_codes": [item.model_dump(mode="json") for item in candidate.reason_codes],
        "missing_data_flags": list(candidate.missing_data_flags),
        "warning_codes": list(candidate.warning_codes),
        "supporting_application_id": (
            str(candidate.support.application.id)
            if candidate.support.application is not None
            else None
        ),
    }
    scenario_evidence = assemble_scenario_evidence(
        session=session,
        site=site,
        scenario=scenario,
        site_evidence=site_evidence,
        extant_permission=extant_permission,
        baseline_pack=baseline_pack,
    )
    scenario.evidence_json = scenario_evidence.model_dump(by_alias=True, mode="json")
    return scenario


def _assign_headline_scenario(
    *,
    session: Session,
    site: SiteCandidate,
    new_scenarios: list[SiteScenario],
) -> uuid.UUID | None:
    current_scenarios = [
        row
        for row in site.scenarios
        if row.is_current and row.status != ScenarioStatus.REJECTED
    ]
    for scenario in current_scenarios:
        scenario.is_headline = False

    preferred = next(
        (
            row
            for row in current_scenarios
            if row.status in {ScenarioStatus.ANALYST_CONFIRMED, ScenarioStatus.AUTO_CONFIRMED}
            and not row.stale_reason
        ),
        None,
    )
    if preferred is None:
        ordered = sorted(
            current_scenarios,
            key=lambda row: (
                row.heuristic_rank if row.heuristic_rank is not None else 999,
                row.status != ScenarioStatus.AUTO_CONFIRMED,
                row.updated_at,
                str(row.id),
            ),
        )
        preferred = ordered[0] if ordered else None

    if preferred is None and new_scenarios:
        preferred = new_scenarios[0]
    if preferred is None:
        return None
    preferred.is_headline = True
    session.flush()
    return preferred.id


def _mark_stale_current_auto_scenarios(
    *,
    session: Session,
    site: SiteCandidate,
    keep_ids: set[uuid.UUID],
) -> None:
    for scenario in site.scenarios:
        if scenario.scenario_source != ScenarioSource.AUTO:
            continue
        if not scenario.is_current:
            continue
        if scenario.id in keep_ids:
            continue
        scenario.is_current = False
        scenario.is_headline = False
    session.flush()


def _rulepack_for_template(
    *,
    baseline_pack: BoroughBaselinePack | None,
    template_key: str,
) -> BoroughRulepack | None:
    if baseline_pack is None:
        return None
    return next(
        (row for row in baseline_pack.rulepacks if row.template_key == template_key),
        None,
    )


def _nearest_historical_support(
    *,
    site: SiteCandidate,
    min_units: int,
    max_units: int,
    route_assumed: str,
) -> CandidateSupport:
    candidates: list[tuple[int, PlanningApplication]] = []
    for link in site.planning_links:
        app = link.planning_application
        if app.source_system == "PLD":
            continue
        if app.units_proposed is None:
            continue
        distance_penalty = int(link.distance_m or 0)
        fit_penalty = 0
        if not (min_units <= app.units_proposed <= max_units):
            fit_penalty += 20
        if app.route_normalized and app.route_normalized != route_assumed:
            fit_penalty += 10
        if not _is_residential_history(app):
            fit_penalty += 50
        candidates.append((distance_penalty + fit_penalty, app))

    if not candidates:
        return CandidateSupport(application=None, strong=False)
    candidates.sort(key=lambda item: (item[0], item[1].decision_date or item[1].valid_date))
    application = candidates[0][1]
    strong = (
        _historical_status_is_strong(application)
        and application.route_normalized == route_assumed
        and application.units_proposed is not None
        and min_units <= application.units_proposed <= max_units
    )
    return CandidateSupport(application=application, strong=strong)


def _auto_confirm_allowed(
    *,
    site: SiteCandidate,
    template_key: str,
    preferred_route: str,
    support: CandidateSupport,
    extant_permission,
    missing_data_flags: list[str],
    warning_codes: list[str],
) -> tuple[bool, list[tuple[str, str]]]:
    reasons: list[tuple[str, str]] = []
    if site.geom_confidence not in {GeomConfidence.HIGH, GeomConfidence.MEDIUM}:
        reasons.append(
            (
                "AUTO_CONFIRM_BLOCKED_GEOMETRY",
                "Geometry confidence is below MEDIUM.",
            )
        )
    if extant_permission.eligibility_status != EligibilityStatus.PASS:
        reasons.append(
            (
                "AUTO_CONFIRM_BLOCKED_EXTANT",
                "Extant-permission screening did not return a clean PASS result.",
            )
        )
    if missing_data_flags:
        reasons.append(
            (
                "AUTO_CONFIRM_BLOCKED_MISSING_DATA",
                "Missing-data flags remain unresolved for this scenario.",
            )
        )
    if any(code.endswith("STALE") for code in warning_codes):
        reasons.append(
            (
                "AUTO_CONFIRM_BLOCKED_STALE_SOURCE",
                "Source freshness is stale for a critical input.",
            )
        )
    if not support.strong:
        reasons.append(
            (
                "AUTO_CONFIRM_BLOCKED_HISTORICAL_SUPPORT",
                "Nearest historical support is not strong enough for conservative auto-confirm.",
            )
        )
    if preferred_route not in {"FULL", "OUTLINE"}:
        reasons.append(
            (
                "AUTO_CONFIRM_BLOCKED_ROUTE",
                f"Route {preferred_route} is outside the enabled v1 templates for {template_key}.",
            )
        )
    return (len(reasons) == 0, reasons)


def _is_residential_history(application: PlanningApplication) -> bool:
    decision_type = (application.decision_type or "").upper()
    proposal = application.proposal_description.lower()
    return "RESIDENTIAL" in decision_type or "dwelling" in proposal or "flat" in proposal


def _historical_status_is_strong(application: PlanningApplication) -> bool:
    return (
        (application.decision or "").upper() == "APPROVED"
        and (application.status or "").upper() == "APPROVED"
        and (application.source_system or "").upper() != "PLD"
    )


def _citations_complete(citations: list[dict[str, Any]]) -> bool:
    if not citations:
        return False
    for citation in citations:
        if not citation.get("label") or not citation.get("source_family"):
            return False
    return True


def _dedupe(values) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result
