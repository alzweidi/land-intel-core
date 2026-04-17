from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from landintel.domain.enums import (
    EligibilityStatus,
    ExtantPermissionStatus,
    SourceCoverageStatus,
)
from landintel.domain.models import (
    AuditEvent,
    BrownfieldSiteState,
    PlanningApplication,
    SiteCandidate,
)
from landintel.domain.schemas import (
    ExtantPermissionMatchRead,
    ExtantPermissionRead,
    SiteWarningRead,
)
from landintel.geospatial.geometry import load_wkt_geometry

from .constants import (
    ACTIVE_PERMISSION_DECISION_TYPES,
    ACTIVE_PERMISSION_STATUSES,
    MANDATORY_EXTANT_SOURCE_FAMILIES,
    NON_EXCLUSIONARY_STATUSES,
)
from .enrich import (
    list_brownfield_states_for_site,
    list_latest_coverage_snapshots,
    match_generic_geometry,
)
from .site_context_snapshots import planning_application_snapshot


def evaluate_site_extant_permission(
    *,
    session: Session,
    site: SiteCandidate,
) -> ExtantPermissionRead:
    coverage_rows = list_latest_coverage_snapshots(session=session, borough_id=site.borough_id)
    coverage_by_family = {row.source_family: row for row in coverage_rows}
    coverage_gaps = _coverage_gaps(coverage_by_family)

    site_geometry = load_wkt_geometry(site.geom_27700)
    site_area = float(site.site_area_sqm or 0.0)
    active_material_matches: list[ExtantPermissionMatchRead] = []
    active_nonmaterial_matches: list[ExtantPermissionMatchRead] = []
    non_exclusionary_matches: list[ExtantPermissionMatchRead] = []
    supplemental_active_matches: list[ExtantPermissionMatchRead] = []
    reasons: list[str] = []

    for link in site.planning_links:
        application = link.planning_application
        application_snapshot = planning_application_snapshot(link)
        overlap_sqm = _planning_overlap_sqm(site_geometry=site_geometry, application=application)
        material = _is_material_overlap(
            overlap_pct=link.overlap_pct,
            overlap_sqm=overlap_sqm,
            raw_record_json=application_snapshot.get(
                "raw_record_json",
                application.raw_record_json,
            ),
            link_type=link.link_type,
        )
        match = ExtantPermissionMatchRead(
            source_kind="planning_application",
            source_system=application_snapshot.get("source_system", application.source_system),
            source_label=application_snapshot.get("external_ref", application.external_ref),
            source_url=application_snapshot.get("source_url", application.source_url),
            source_snapshot_id=(
                getattr(link, "source_snapshot_id", None)
                or application_snapshot.get("source_snapshot_id")
                or application.source_snapshot_id
            ),
            planning_application_id=application.id,
            overlap_pct=link.overlap_pct,
            overlap_sqm=overlap_sqm,
            distance_m=link.distance_m,
            material=material,
            detail=_planning_detail(
                application=application,
                application_snapshot=application_snapshot,
                material=material,
            ),
        )

        if _is_active_residential_permission(
            application,
            application_snapshot=application_snapshot,
        ):
            if application_snapshot.get("source_system", application.source_system) == "PLD":
                supplemental_active_matches.append(match)
            elif material:
                active_material_matches.append(match)
            else:
                active_nonmaterial_matches.append(match)
            continue

        if _is_non_exclusionary_permission(
            application,
            application_snapshot=application_snapshot,
        ):
            non_exclusionary_matches.append(match)

    brownfield_states = list_brownfield_states_for_site(session=session, site=site)
    for state in brownfield_states:
        match = _brownfield_match(site_geometry=site_geometry, site_area_sqm=site_area, state=state)
        if match is None:
            continue
        if _is_active_brownfield_exclusion(state) and match.material:
            active_material_matches.append(match)
            continue
        if _is_active_brownfield_exclusion(state):
            active_nonmaterial_matches.append(match)
            continue
        non_exclusionary_matches.append(match)

    if active_material_matches:
        reasons.append("Material overlap with active extant permission evidence was identified.")
        return ExtantPermissionRead(
            status=ExtantPermissionStatus.ACTIVE_EXTANT_PERMISSION_FOUND,
            eligibility_status=EligibilityStatus.FAIL,
            manual_review_required=False,
            summary=(
                "Active extant permission evidence materially overlaps the current "
                "site geometry."
            ),
            reasons=reasons,
            coverage_gaps=coverage_gaps,
            matched_records=(
                active_material_matches
                + active_nonmaterial_matches
                + non_exclusionary_matches
            ),
        )

    mandatory_incomplete = [
        gap for gap in coverage_gaps if gap.code.startswith("MANDATORY_SOURCE_")
    ]
    if active_nonmaterial_matches:
        reasons.append("Active permission evidence was found, but overlap is not clearly material.")
        return ExtantPermissionRead(
            status=ExtantPermissionStatus.NON_MATERIAL_OVERLAP_MANUAL_REVIEW,
            eligibility_status=EligibilityStatus.ABSTAIN,
            manual_review_required=True,
            summary=(
                "Potentially active permission evidence was found, but material "
                "overlap is not confirmed."
            ),
            reasons=reasons,
            coverage_gaps=coverage_gaps,
            matched_records=active_nonmaterial_matches + non_exclusionary_matches,
        )

    if mandatory_incomplete:
        reasons.append(
            "Mandatory source coverage is incomplete, so a clean "
            "no-active-permission conclusion is not defensible."
        )
        return ExtantPermissionRead(
            status=ExtantPermissionStatus.UNRESOLVED_MISSING_MANDATORY_SOURCE,
            eligibility_status=EligibilityStatus.ABSTAIN,
            manual_review_required=True,
            summary=(
                "Mandatory source coverage is incomplete, so extant permission "
                "screening must abstain."
            ),
            reasons=reasons,
            coverage_gaps=coverage_gaps,
            matched_records=non_exclusionary_matches,
        )

    if supplemental_active_matches:
        reasons.append(
            "Supplemental PLD evidence suggests an active permission state that is "
            "not confirmed by the authoritative borough record."
        )
        return ExtantPermissionRead(
            status=ExtantPermissionStatus.CONTRADICTORY_SOURCE_MANUAL_REVIEW,
            eligibility_status=EligibilityStatus.ABSTAIN,
            manual_review_required=True,
            summary=(
                "Supplemental and authoritative sources are contradictory; "
                "analyst review is required."
            ),
            reasons=reasons,
            coverage_gaps=coverage_gaps,
            matched_records=supplemental_active_matches + non_exclusionary_matches,
        )

    if non_exclusionary_matches:
        reasons.append(
            "Historic or non-exclusionary planning evidence was found but no active "
            "extant residential permission is currently identified."
        )

    return ExtantPermissionRead(
        status=ExtantPermissionStatus.NO_ACTIVE_PERMISSION_FOUND,
        eligibility_status=EligibilityStatus.PASS,
        manual_review_required=False,
        summary=(
            "No active extant residential permission was found in the currently "
            "loaded authoritative source coverage."
        ),
        reasons=reasons,
        coverage_gaps=coverage_gaps,
        matched_records=non_exclusionary_matches,
    )


def audit_extant_permission_check(
    *,
    session: Session,
    site: SiteCandidate,
    requested_by: str | None,
    result: ExtantPermissionRead,
) -> None:
    session.add(
        AuditEvent(
            action="extant_permission_checked",
            entity_type="site_candidate",
            entity_id=str(site.id),
            before_json=None,
            after_json={
                "requested_by": requested_by,
                "status": result.status.value,
                "eligibility_status": result.eligibility_status.value,
                "manual_review_required": result.manual_review_required,
                "matched_records": [
                    item.model_dump(mode="json") for item in result.matched_records
                ],
                "coverage_gaps": [item.model_dump(mode="json") for item in result.coverage_gaps],
            },
        )
    )


def _coverage_gaps(coverage_by_family: dict[str, Any]) -> list[SiteWarningRead]:
    warnings: list[SiteWarningRead] = []
    for source_family in MANDATORY_EXTANT_SOURCE_FAMILIES:
        row = coverage_by_family.get(source_family)
        if row is None:
            warnings.append(
                SiteWarningRead(
                    code=f"MANDATORY_SOURCE_{source_family.upper()}_MISSING",
                    message=(
                        f"Mandatory source family '{source_family}' has no recorded "
                        "coverage for the controlling borough."
                    ),
                )
            )
            continue
        if row.coverage_status != SourceCoverageStatus.COMPLETE:
            warnings.append(
                SiteWarningRead(
                    code=f"MANDATORY_SOURCE_{source_family.upper()}_{row.coverage_status.value}",
                    message=(
                        f"Mandatory source family '{source_family}' is "
                        f"{row.coverage_status.value.lower()}. "
                        f"{row.gap_reason or 'Coverage is incomplete.'}"
                    ),
                )
            )
    return warnings


def _planning_overlap_sqm(*, site_geometry, application: PlanningApplication) -> float | None:
    if not application.site_geom_27700:
        return None
    application_geometry = load_wkt_geometry(application.site_geom_27700)
    if not site_geometry.intersects(application_geometry):
        return None
    intersection = site_geometry.intersection(application_geometry)
    if intersection.is_empty:
        return None
    return float(intersection.area)


def _is_material_overlap(
    *,
    overlap_pct: float | None,
    overlap_sqm: float | None,
    raw_record_json: dict[str, Any] | None,
    link_type: str,
) -> bool:
    if overlap_pct is not None and overlap_pct >= 0.10:
        return True
    if overlap_sqm is not None and overlap_sqm >= 100.0:
        return True
    if raw_record_json and bool(raw_record_json.get("material_access_control")):
        return True
    return link_type == "POINT_WITHIN_SITE" and bool(
        raw_record_json and raw_record_json.get("material_core_envelope")
    )


def _is_active_residential_permission(
    application: PlanningApplication,
    *,
    application_snapshot: dict[str, Any] | None = None,
) -> bool:
    snapshot = application_snapshot if isinstance(application_snapshot, dict) else {}
    route_normalized = str(
        snapshot.get("route_normalized") or application.route_normalized or ""
    )
    decision_type = str(snapshot.get("decision_type") or application.decision_type or "")
    status = str(snapshot.get("status") or application.status or "")
    raw_record_json = dict(snapshot.get("raw_record_json") or application.raw_record_json or {})

    if route_normalized not in {"FULL", "OUTLINE", "PIP", "PRIOR_APPROVAL"}:
        return False
    if decision_type not in ACTIVE_PERMISSION_DECISION_TYPES:
        return False
    if status not in ACTIVE_PERMISSION_STATUSES:
        return False
    if not _is_residential(raw_record_json):
        return False
    expiry_date = _parse_date_from_record(raw_record_json, "expiry_date")
    if expiry_date is not None and expiry_date < date.today():
        return False
    return bool(raw_record_json.get("active_extant", True))


def _is_non_exclusionary_permission(
    application: PlanningApplication,
    *,
    application_snapshot: dict[str, Any] | None = None,
) -> bool:
    snapshot = application_snapshot if isinstance(application_snapshot, dict) else {}
    status = str(snapshot.get("status") or application.status or "")
    raw_record_json = dict(snapshot.get("raw_record_json") or application.raw_record_json or {})
    if status in NON_EXCLUSIONARY_STATUSES:
        return True
    if bool(raw_record_json.get("lapsed")):
        return True
    expiry_date = _parse_date_from_record(raw_record_json, "expiry_date")
    return expiry_date is not None and expiry_date < date.today()


def _is_residential(raw_record_json: dict[str, Any] | None) -> bool:
    if not raw_record_json:
        return True
    dwelling_use = str(raw_record_json.get("dwelling_use") or "C3").upper()
    return dwelling_use.startswith("C3") or "RESI" in dwelling_use


def _is_active_brownfield_exclusion(state: BrownfieldSiteState) -> bool:
    part = state.part.upper()
    if part == "PART_1":
        return False
    effective_to = state.effective_to
    if effective_to is not None and effective_to < date.today():
        return False
    pip_active = (state.pip_status or "").upper() == "ACTIVE"
    tdc_active = (state.tdc_status or "").upper() == "ACTIVE"
    return pip_active or tdc_active


def _brownfield_match(
    *,
    site_geometry,
    site_area_sqm: float,
    state: BrownfieldSiteState,
) -> ExtantPermissionMatchRead | None:
    match = match_generic_geometry(
        site_geometry=site_geometry,
        site_area_sqm=site_area_sqm,
        feature_wkt=state.geom_27700,
        near_distance_m=0.0,
    )
    if match is None:
        return None
    return ExtantPermissionMatchRead(
        source_kind="brownfield_state",
        source_system="BROWNFIELD",
        source_label=state.external_ref,
        source_url=state.source_url,
        source_snapshot_id=state.source_snapshot_id,
        brownfield_state_id=state.id,
        overlap_pct=match.overlap_pct,
        overlap_sqm=match.overlap_sqm,
        distance_m=match.distance_m,
        material=bool(match.overlap_pct and match.overlap_pct >= 0.10)
        or bool(match.overlap_sqm and match.overlap_sqm >= 100.0),
        detail=(
            "Brownfield Part 2 entry with active PiP/TDC evidence."
            if _is_active_brownfield_exclusion(state)
            else "Brownfield Part 1 or inactive brownfield entry; informative but not exclusionary."
        ),
    )


def _planning_detail(
    *,
    application: PlanningApplication,
    application_snapshot: dict[str, Any] | None = None,
    material: bool,
) -> str:
    snapshot = application_snapshot if isinstance(application_snapshot, dict) else {}
    route_or_type = (
        snapshot.get("route_normalized")
        or application.route_normalized
        or snapshot.get("application_type")
        or application.application_type.lower()
    )
    external_ref = snapshot.get("external_ref") or application.external_ref
    if _is_active_residential_permission(application, application_snapshot=snapshot):
        prefix = "Material" if material else "Potential"
        return (
            f"{prefix} active "
            f"{route_or_type} "
            f"permission recorded under {external_ref}."
        )
    if _is_non_exclusionary_permission(application, application_snapshot=snapshot):
        return (
            f"Historic or non-active planning record {external_ref} "
            "remains relevant evidence."
        )
    return f"Planning record {external_ref} was linked to the site."


def _parse_date_from_record(raw_record_json: dict[str, Any] | None, key: str) -> date | None:
    if not raw_record_json:
        return None
    value = raw_record_json.get(key)
    if not value:
        return None
    return date.fromisoformat(str(value))
