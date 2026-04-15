from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from landintel.domain.enums import (
    EvidenceImportance,
    GeomConfidence,
    SourceCoverageStatus,
)
from landintel.domain.models import (
    AuditEvent,
    BoroughBaselinePack,
    BrownfieldSiteState,
    PlanningApplication,
    PlanningApplicationDocument,
    PlanningConstraintFeature,
    PolicyArea,
    SiteCandidate,
    SiteConstraintFact,
    SitePlanningLink,
    SitePolicyFact,
    SourceCoverageSnapshot,
)
from landintel.geospatial.geometry import (
    derive_site_status,
    load_wkt_geometry,
)

from .constants import (
    CONSTRAINT_LINK_DISTANCE_M,
    MANDATORY_EXTANT_SOURCE_FAMILIES,
    PLANNING_LINK_DISTANCE_M,
)

PLANNING_ENRICH_NAMESPACE = uuid.UUID("1afc65a3-c765-41d6-9054-842ffb4cc728")


@dataclass(slots=True)
class SpatialMatch:
    link_type: str
    distance_m: float | None
    overlap_pct: float | None
    overlap_sqm: float | None
    confidence: GeomConfidence


def refresh_site_planning_context(
    *,
    session: Session,
    site: SiteCandidate,
    requested_by: str | None,
) -> None:
    before_payload = {
        "site_id": str(site.id),
        "planning_links": len(site.planning_links),
        "policy_facts": len(site.policy_facts),
        "constraint_facts": len(site.constraint_facts),
        "borough_id": site.borough_id,
    }
    site_geometry = load_wkt_geometry(site.geom_27700)
    site_area = float(site.site_area_sqm or 0.0)

    session.execute(delete(SitePlanningLink).where(SitePlanningLink.site_id == site.id))
    session.execute(delete(SitePolicyFact).where(SitePolicyFact.site_id == site.id))
    session.execute(delete(SiteConstraintFact).where(SiteConstraintFact.site_id == site.id))
    session.flush()

    planning_apps = session.execute(
        select(PlanningApplication).options(
            selectinload(PlanningApplication.documents).selectinload(
                PlanningApplicationDocument.asset
            )
        )
    ).scalars().all()
    for app in planning_apps:
        match = match_planning_application(
            site_geometry=site_geometry,
            site_area_sqm=site_area,
            application=app,
        )
        if match is None:
            continue
        session.add(
            SitePlanningLink(
                id=uuid.uuid5(
                    PLANNING_ENRICH_NAMESPACE,
                    f"site-planning:{site.id}:{app.id}",
                ),
                site_id=site.id,
                planning_application_id=app.id,
                link_type=match.link_type,
                distance_m=match.distance_m,
                overlap_pct=match.overlap_pct,
                match_confidence=match.confidence,
                manual_verified=False,
            )
        )

    policy_areas = session.execute(select(PolicyArea)).scalars().all()
    for area in policy_areas:
        match = match_generic_geometry(
            site_geometry=site_geometry,
            site_area_sqm=site_area,
            feature_wkt=area.geom_27700,
            near_distance_m=0.0,
        )
        if match is None:
            continue
        session.add(
            SitePolicyFact(
                id=uuid.uuid5(
                    PLANNING_ENRICH_NAMESPACE,
                    f"site-policy:{site.id}:{area.id}",
                ),
                site_id=site.id,
                policy_area_id=area.id,
                relation_type=match.link_type,
                overlap_pct=match.overlap_pct,
                distance_m=match.distance_m,
                importance=_importance_from_record(
                    area.raw_record_json,
                    default=EvidenceImportance.MEDIUM,
                ),
            )
        )

    constraint_features = session.execute(select(PlanningConstraintFeature)).scalars().all()
    for feature in constraint_features:
        match = match_generic_geometry(
            site_geometry=site_geometry,
            site_area_sqm=site_area,
            feature_wkt=feature.geom_27700,
            near_distance_m=CONSTRAINT_LINK_DISTANCE_M,
        )
        if match is None:
            continue
        session.add(
            SiteConstraintFact(
                id=uuid.uuid5(
                    PLANNING_ENRICH_NAMESPACE,
                    f"site-constraint:{site.id}:{feature.id}",
                ),
                site_id=site.id,
                constraint_feature_id=feature.id,
                overlap_pct=match.overlap_pct,
                distance_m=match.distance_m,
                severity=_importance_from_record(
                    feature.raw_record_json,
                    default=EvidenceImportance.MEDIUM,
                ),
            )
        )

    session.flush()
    session.refresh(site)

    coverage_warnings = coverage_warning_dicts(
        coverage_rows=list_latest_coverage_snapshots(session=session, borough_id=site.borough_id)
    )
    planning_warnings = []
    if (
        site.borough_id
        and get_borough_baseline_pack(session=session, borough_id=site.borough_id) is None
    ):
        planning_warnings.append(
            {
                "code": "BASELINE_PACK_MISSING",
                "message": (
                    "No borough baseline pack is loaded for the controlling borough."
                ),
            }
        )

    existing = dict(site.warning_json or {})
    geometry_warnings = list(existing.get("geometry", []))
    lpa_warnings = list(existing.get("lpa", []))
    title_warnings = list(existing.get("title", []))
    site.warning_json = {
        **{
            key: value
            for key, value in existing.items()
            if key not in {"geometry", "lpa", "title", "coverage", "planning"}
        },
        "geometry": geometry_warnings,
        "lpa": lpa_warnings,
        "title": title_warnings,
        "coverage": coverage_warnings,
        "planning": planning_warnings,
    }
    base_manual_review_required = bool(
        site.geom_confidence in {GeomConfidence.LOW, GeomConfidence.INSUFFICIENT}
        or any(item["code"] == "CROSS_LPA_MATERIAL" for item in lpa_warnings)
    )
    site.manual_review_required = bool(
        base_manual_review_required
        or any(item["code"].startswith("MANDATORY_SOURCE_") for item in coverage_warnings)
        or bool(planning_warnings)
    )
    site.site_status = derive_site_status(
        geom_confidence=site.geom_confidence,
        manual_review_required=site.manual_review_required,
    )

    session.add(
        AuditEvent(
            action="site_planning_enriched",
            entity_type="site_candidate",
            entity_id=str(site.id),
            before_json=before_payload,
            after_json={
                "site_id": str(site.id),
                "planning_links": len(site.planning_links),
                "policy_facts": len(site.policy_facts),
                "constraint_facts": len(site.constraint_facts),
                "requested_by": requested_by,
            },
        )
    )


def list_latest_coverage_snapshots(
    *,
    session: Session,
    borough_id: str | None,
) -> list[SourceCoverageSnapshot]:
    if borough_id is None:
        return []
    rows = session.execute(
        select(SourceCoverageSnapshot)
        .where(SourceCoverageSnapshot.borough_id == borough_id)
        .order_by(SourceCoverageSnapshot.captured_at.desc())
    ).scalars().all()
    latest: dict[str, SourceCoverageSnapshot] = {}
    for row in rows:
        latest.setdefault(row.source_family, row)
    return list(latest.values())


def get_borough_baseline_pack(
    *,
    session: Session,
    borough_id: str | None,
) -> BoroughBaselinePack | None:
    if borough_id is None:
        return None
    return session.execute(
        select(BoroughBaselinePack)
        .where(BoroughBaselinePack.borough_id == borough_id)
        .options(selectinload(BoroughBaselinePack.rulepacks))
        .order_by(BoroughBaselinePack.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def list_brownfield_states_for_site(
    *,
    session: Session,
    site: SiteCandidate,
) -> list[BrownfieldSiteState]:
    site_geometry = load_wkt_geometry(site.geom_27700)
    rows = session.execute(
        select(BrownfieldSiteState).order_by(BrownfieldSiteState.created_at.desc())
    ).scalars().all()
    return [
        row
        for row in rows
        if _intersects_geometry(site_geometry, row.geom_27700)
    ]


def match_planning_application(
    *,
    site_geometry,
    site_area_sqm: float,
    application: PlanningApplication,
) -> SpatialMatch | None:
    geometry_match = match_generic_geometry(
        site_geometry=site_geometry,
        site_area_sqm=site_area_sqm,
        feature_wkt=application.site_geom_27700,
        near_distance_m=0.0,
    )
    if geometry_match is not None:
        return geometry_match

    return match_generic_geometry(
        site_geometry=site_geometry,
        site_area_sqm=site_area_sqm,
        feature_wkt=application.site_point_27700,
        near_distance_m=PLANNING_LINK_DISTANCE_M,
    )


def match_generic_geometry(
    *,
    site_geometry,
    site_area_sqm: float,
    feature_wkt: str | None,
    near_distance_m: float,
) -> SpatialMatch | None:
    if not feature_wkt:
        return None

    feature_geometry = load_wkt_geometry(feature_wkt)
    if feature_geometry.geom_type in {"Polygon", "MultiPolygon"}:
        if not site_geometry.intersects(feature_geometry):
            return None
        intersection = site_geometry.intersection(feature_geometry)
        overlap_sqm = float(intersection.area) if not intersection.is_empty else 0.0
        overlap_pct = (overlap_sqm / site_area_sqm) if site_area_sqm > 0 else None
        return SpatialMatch(
            link_type="POLYGON_INTERSECTS",
            distance_m=0.0,
            overlap_pct=overlap_pct,
            overlap_sqm=overlap_sqm,
            confidence=GeomConfidence.HIGH,
        )

    if feature_geometry.within(site_geometry) or site_geometry.intersects(feature_geometry):
        return SpatialMatch(
            link_type="POINT_WITHIN_SITE",
            distance_m=0.0,
            overlap_pct=None,
            overlap_sqm=None,
            confidence=GeomConfidence.MEDIUM,
        )

    distance_m = float(site_geometry.distance(feature_geometry))
    if distance_m > near_distance_m:
        return None
    return SpatialMatch(
        link_type="POINT_NEAR_SITE",
        distance_m=distance_m,
        overlap_pct=None,
        overlap_sqm=None,
        confidence=GeomConfidence.LOW,
    )


def coverage_warning_dicts(
    *,
    coverage_rows: list[SourceCoverageSnapshot],
) -> list[dict[str, str]]:
    warnings: list[dict[str, str]] = []
    by_family = {row.source_family: row for row in coverage_rows}
    for source_family in MANDATORY_EXTANT_SOURCE_FAMILIES:
        row = by_family.get(source_family)
        if row is None:
            warnings.append(
                {
                    "code": f"MANDATORY_SOURCE_{source_family.upper()}_MISSING",
                    "message": (
                        f"Mandatory source family '{source_family}' has no recorded "
                        "coverage for the controlling borough."
                    ),
                }
            )
            continue
        if row.coverage_status != SourceCoverageStatus.COMPLETE:
            gap_reason = row.gap_reason or "Coverage is incomplete."
            warnings.append(
                {
                    "code": f"MANDATORY_SOURCE_{source_family.upper()}_{row.coverage_status.value}",
                    "message": (
                        f"Mandatory source family '{source_family}' is "
                        f"{row.coverage_status.value.lower()}: {gap_reason}"
                    ),
                }
            )
    return warnings


def _intersects_geometry(site_geometry, feature_wkt: str) -> bool:
    try:
        feature_geometry = load_wkt_geometry(feature_wkt)
    except Exception:
        return False
    return site_geometry.intersects(feature_geometry)


def _importance_from_record(
    raw_record_json: dict[str, Any] | None,
    *,
    default: EvidenceImportance,
) -> EvidenceImportance:
    if not raw_record_json:
        return default
    value = raw_record_json.get("importance") or raw_record_json.get("severity")
    if value is None:
        return default
    return EvidenceImportance(str(value).upper())
