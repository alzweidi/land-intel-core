from __future__ import annotations

import hashlib
import json
import math
import statistics
from dataclasses import dataclass
from datetime import date
from types import SimpleNamespace
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from landintel.domain.enums import (
    GeomConfidence,
    GeomSourceType,
    HistoricalLabelClass,
    PriceBasisType,
    ProposalForm,
    ScenarioSource,
    ScenarioStatus,
)
from landintel.domain.models import (
    BrownfieldSiteState,
    HistoricalCaseLabel,
    PlanningApplication,
    PlanningConstraintFeature,
    PolicyArea,
    SiteCandidate,
    SiteScenario,
    SourceCoverageSnapshot,
)
from landintel.geospatial.geometry import load_wkt_geometry
from landintel.planning.enrich import match_generic_geometry
from landintel.planning.site_context_snapshots import (
    constraint_snapshot,
    planning_application_snapshot,
    policy_area_snapshot,
)

FEATURE_VERSION = "phase5a_v1"
DEFAULT_TEMPLATE_NET_DEVELOPABLE_AREA_PCT = {
    "resi_1_4_full": 0.68,
    "resi_5_9_full": 0.72,
    "resi_10_49_outline": 0.78,
}
NEARBY_DISTANCE_WINDOWS = (
    ("adjacent", 0.0, 50.0),
    ("local_precedent", 50.0, 250.0),
    ("local_context", 250.0, 500.0),
)
POINT_MATCH_DISTANCE_M = 20.0


@dataclass(slots=True)
class FeatureBuildResult:
    feature_version: str
    feature_hash: str
    feature_json: dict[str, Any]
    coverage_json: dict[str, Any]
    source_snapshot_ids: list[str]
    raw_asset_ids: list[str]


def canonical_json_hash(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_designation_profile_for_geometry(
    *,
    session: Session,
    geometry,
    area_sqm: float,
    as_of_date: date,
) -> tuple[dict[str, Any], set[str]]:
    source_snapshot_ids: set[str] = set()
    policy_families: set[str] = set()
    constraint_families: set[str] = set()

    profile: dict[str, Any] = {
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
    }

    policies = session.execute(select(PolicyArea)).scalars().all()
    for row in policies:
        if not _active_on_date(
            effective_from=row.legal_effective_from,
            effective_to=row.legal_effective_to,
            as_of_date=as_of_date,
        ):
            continue
        match = match_generic_geometry(
            site_geometry=geometry,
            site_area_sqm=area_sqm,
            feature_wkt=row.geom_27700,
            near_distance_m=0.0,
        )
        if match is None:
            continue
        policy_families.add(row.policy_family)
        source_snapshot_ids.add(str(row.source_snapshot_id))

    constraints = session.execute(select(PlanningConstraintFeature)).scalars().all()
    for row in constraints:
        if not _active_on_date(
            effective_from=row.effective_from,
            effective_to=row.effective_to,
            as_of_date=as_of_date,
        ):
            continue
        match = match_generic_geometry(
            site_geometry=geometry,
            site_area_sqm=area_sqm,
            feature_wkt=row.geom_27700,
            near_distance_m=POINT_MATCH_DISTANCE_M,
        )
        if match is None:
            continue
        constraint_families.add(f"{row.feature_family}:{row.feature_subtype}")
        source_snapshot_ids.add(str(row.source_snapshot_id))
        if row.feature_family == "heritage" and row.feature_subtype == "conservation_area":
            profile["has_conservation_area"] = True
        if row.feature_family == "article4":
            profile["has_article4"] = True
        if row.feature_family == "flood":
            profile["has_flood_zone"] = True
        if row.feature_family == "heritage" and row.feature_subtype == "listed_building":
            profile["has_listed_building_nearby"] = True

    _apply_brownfield_designations(
        session=session,
        geometry=geometry,
        area_sqm=area_sqm,
        as_of_date=as_of_date,
        profile=profile,
        source_snapshot_ids=source_snapshot_ids,
    )

    profile["policy_families"] = sorted(policy_families)
    profile["constraint_families"] = sorted(constraint_families)
    profile["has_site_allocation"] = "SITE_ALLOCATION" in policy_families
    profile["has_density_guidance"] = "DENSITY_GUIDANCE" in policy_families
    return profile, source_snapshot_ids


def build_designation_profile_for_site_context(
    *,
    session: Session,
    site: SiteCandidate,
    geometry,
    area_sqm: float,
    as_of_date: date,
) -> tuple[dict[str, Any], set[str]]:
    profile, source_snapshot_ids = build_designation_profile_for_geometry(
        session=session,
        geometry=geometry,
        area_sqm=area_sqm,
        as_of_date=as_of_date,
    )
    if not hasattr(site, "policy_facts") or not hasattr(site, "constraint_facts"):
        return profile, source_snapshot_ids

    policy_families: set[str] = set()
    constraint_families: set[str] = set()
    source_snapshot_ids = set()
    profile.update(
        {
            "policy_families": [],
            "constraint_families": [],
            "has_site_allocation": False,
            "has_density_guidance": False,
            "has_conservation_area": False,
            "has_article4": False,
            "has_flood_zone": False,
            "has_listed_building_nearby": False,
        }
    )
    _apply_brownfield_designations(
        session=session,
        geometry=geometry,
        area_sqm=area_sqm,
        as_of_date=as_of_date,
        profile=profile,
        source_snapshot_ids=source_snapshot_ids,
    )

    for fact in site.policy_facts:
        snapshot = policy_area_snapshot(fact)
        if not _active_on_date(
            effective_from=_parse_snapshot_date(snapshot.get("legal_effective_from")),
            effective_to=_parse_snapshot_date(snapshot.get("legal_effective_to")),
            as_of_date=as_of_date,
        ):
            continue
        policy_family = str(snapshot.get("policy_family") or fact.policy_area.policy_family)
        policy_families.add(policy_family)
        source_snapshot_ids.add(
            str(
                getattr(fact, "source_snapshot_id", None)
                or snapshot.get("source_snapshot_id")
                or fact.policy_area.source_snapshot_id
            )
        )

    for fact in site.constraint_facts:
        snapshot = constraint_snapshot(fact)
        if not _active_on_date(
            effective_from=_parse_snapshot_date(snapshot.get("effective_from")),
            effective_to=_parse_snapshot_date(snapshot.get("effective_to")),
            as_of_date=as_of_date,
        ):
            continue
        feature_family = str(
            snapshot.get("feature_family") or fact.constraint_feature.feature_family
        )
        feature_subtype = str(
            snapshot.get("feature_subtype") or fact.constraint_feature.feature_subtype
        )
        constraint_families.add(f"{feature_family}:{feature_subtype}")
        source_snapshot_ids.add(
            str(
                getattr(fact, "source_snapshot_id", None)
                or snapshot.get("source_snapshot_id")
                or fact.constraint_feature.source_snapshot_id
            )
        )
        if feature_family == "heritage" and feature_subtype == "conservation_area":
            profile["has_conservation_area"] = True
        if feature_family == "article4":
            profile["has_article4"] = True
        if feature_family == "flood":
            profile["has_flood_zone"] = True
        if feature_family == "heritage" and feature_subtype == "listed_building":
            profile["has_listed_building_nearby"] = True

    profile["policy_families"] = sorted(policy_families)
    profile["constraint_families"] = sorted(constraint_families)
    profile["has_site_allocation"] = "SITE_ALLOCATION" in policy_families
    profile["has_density_guidance"] = "DENSITY_GUIDANCE" in policy_families
    return profile, source_snapshot_ids


def _apply_brownfield_designations(
    *,
    session: Session,
    geometry,
    area_sqm: float,
    as_of_date: date,
    profile: dict[str, Any],
    source_snapshot_ids: set[str],
) -> None:
    brownfield_rows = session.execute(select(BrownfieldSiteState)).scalars().all()
    for row in brownfield_rows:
        if not _active_on_date(
            effective_from=row.effective_from,
            effective_to=row.effective_to,
            as_of_date=as_of_date,
        ):
            continue
        match = match_generic_geometry(
            site_geometry=geometry,
            site_area_sqm=area_sqm,
            feature_wkt=row.geom_27700,
            near_distance_m=0.0,
        )
        if match is None:
            continue
        source_snapshot_ids.add(str(row.source_snapshot_id))
        if row.part == "PART_1":
            profile["brownfield_part1"] = True
        if row.part == "PART_2":
            profile["brownfield_part2_active"] = True
        if (row.pip_status or "").upper() == "ACTIVE":
            profile["pip_active"] = True
        if (row.tdc_status or "").upper() == "ACTIVE":
            profile["tdc_active"] = True


def derive_archetype_key(
    *,
    template_key: str,
    proposal_form: ProposalForm | str | None,
    designation_profile: dict[str, Any],
) -> str:
    proposal = (
        proposal_form.value
        if isinstance(proposal_form, ProposalForm)
        else (proposal_form or "UNKNOWN")
    )
    heritage_bucket = (
        "heritage"
        if designation_profile.get("has_conservation_area")
        or designation_profile.get("has_listed_building_nearby")
        else "standard"
    )
    brownfield_bucket = (
        "brownfield"
        if designation_profile.get("brownfield_part2_active")
        or designation_profile.get("brownfield_part1")
        else "standard"
    )
    flood_bucket = "flood" if designation_profile.get("has_flood_zone") else "dry"
    return ":".join(
        [template_key or "unknown", proposal, heritage_bucket, brownfield_bucket, flood_bucket]
    )


def planning_application_geometry(application: PlanningApplication):
    if application.site_geom_27700:
        return load_wkt_geometry(application.site_geom_27700)
    if application.site_point_27700:
        return load_wkt_geometry(application.site_point_27700)
    return None


def planning_application_area_sqm(application: PlanningApplication) -> float:
    geometry = planning_application_geometry(application)
    if geometry is None:
        return 0.0
    if geometry.geom_type in {"Polygon", "MultiPolygon"}:
        return float(geometry.area)
    return 1.0


def build_feature_snapshot(
    *,
    session: Session,
    site: SiteCandidate,
    scenario: SiteScenario,
    as_of_date: date,
) -> FeatureBuildResult:
    site_geometry = load_wkt_geometry(site.geom_27700)
    site_area_sqm = float(site.site_area_sqm or 0.0)
    site_perimeter_m = float(site_geometry.length)
    site_compactness = (
        float(4.0 * math.pi * site_area_sqm / (site_perimeter_m**2))
        if site_area_sqm > 0 and site_perimeter_m > 0
        else None
    )

    all_source_snapshot_ids: set[str] = set()
    all_raw_asset_ids: set[str] = set()
    values: dict[str, Any] = {}
    missing_flags: dict[str, bool] = {}
    provenance: dict[str, dict[str, Any]] = {}
    families: dict[str, list[str]] = {}

    def add_feature(
        *,
        family: str,
        name: str,
        value: Any,
        source_snapshot_ids: set[str] | None = None,
        raw_asset_ids: set[str] | None = None,
        analyst_override: bool = False,
        notes: str | None = None,
    ) -> None:
        values[name] = value
        missing_flags[name] = value is None
        families.setdefault(family, []).append(name)
        source_ids_sorted = sorted(source_snapshot_ids or set())
        raw_ids_sorted = sorted(raw_asset_ids or set())
        all_source_snapshot_ids.update(source_ids_sorted)
        all_raw_asset_ids.update(raw_ids_sorted)
        provenance[name] = {
            "source_snapshot_ids": source_ids_sorted,
            "raw_asset_ids": raw_ids_sorted,
            "transform_version": FEATURE_VERSION,
            "analyst_override": analyst_override,
            "notes": notes,
        }

    designation_profile, designation_source_ids = build_designation_profile_for_site_context(
        session=session,
        site=site,
        geometry=site_geometry,
        area_sqm=site_area_sqm,
        as_of_date=as_of_date,
    )

    latest_coverage = _latest_coverage_rows(session=session, borough_id=site.borough_id)
    coverage_json = {
        "borough_id": site.borough_id,
        "as_of_date": as_of_date.isoformat(),
        "source_coverage": [
            {
                "source_family": row.source_family,
                "coverage_status": row.coverage_status.value,
                "freshness_status": row.freshness_status.value,
                "gap_reason": row.gap_reason,
                "source_snapshot_id": (
                    None if row.source_snapshot_id is None else str(row.source_snapshot_id)
                ),
            }
            for row in latest_coverage
        ],
    }

    add_feature(
        family="site_geometry_and_morphology",
        name="site_area_sqm",
        value=round(site_area_sqm, 3),
        analyst_override=site.geom_source_type == GeomSourceType.ANALYST_DRAWN,
        notes="Frozen site geometry area in EPSG:27700.",
    )
    add_feature(
        family="site_geometry_and_morphology",
        name="site_perimeter_m",
        value=round(site_perimeter_m, 3),
        analyst_override=site.geom_source_type == GeomSourceType.ANALYST_DRAWN,
    )
    add_feature(
        family="site_geometry_and_morphology",
        name="site_compactness",
        value=None if site_compactness is None else round(site_compactness, 6),
    )
    add_feature(
        family="site_geometry_and_morphology",
        name="geom_confidence",
        value=site.geom_confidence.value,
    )
    add_feature(
        family="site_geometry_and_morphology",
        name="geom_source_type",
        value=site.geom_source_type.value,
    )
    add_feature(
        family="site_geometry_and_morphology",
        name="scenario_units_assumed",
        value=scenario.units_assumed,
        analyst_override=scenario.scenario_source == ScenarioSource.ANALYST,
    )
    add_feature(
        family="site_geometry_and_morphology",
        name="scenario_net_developable_area_pct",
        value=round(scenario.net_developable_area_pct, 4),
        analyst_override=scenario.scenario_source == ScenarioSource.ANALYST,
    )

    add_feature(
        family="location_and_access",
        name="borough_id",
        value=site.borough_id,
    )
    add_feature(
        family="location_and_access",
        name="scenario_proposal_form",
        value=scenario.proposal_form.value,
        analyst_override=scenario.scenario_source == ScenarioSource.ANALYST,
    )
    add_feature(
        family="location_and_access",
        name="scenario_route_assumed",
        value=scenario.route_assumed,
        analyst_override=scenario.scenario_source == ScenarioSource.ANALYST,
    )
    add_feature(
        family="location_and_access",
        name="scenario_template_key",
        value=scenario.template_key,
        analyst_override=scenario.scenario_source == ScenarioSource.ANALYST,
    )
    add_feature(
        family="location_and_access",
        name="scenario_housing_mix_assumed_json",
        value=dict(getattr(scenario, "housing_mix_assumed_json", None) or {}),
        analyst_override=scenario.scenario_source == ScenarioSource.ANALYST,
    )
    add_feature(
        family="location_and_access",
        name="site_manual_review_required",
        value=bool(getattr(site, "manual_review_required", False)),
    )
    add_feature(
        family="location_and_access",
        name="scenario_manual_review_required",
        value=bool(getattr(scenario, "manual_review_required", False)),
        analyst_override=scenario.scenario_source == ScenarioSource.ANALYST,
    )
    add_feature(
        family="location_and_access",
        name="scenario_status",
        value=getattr(scenario, "status", ScenarioStatus.AUTO_CONFIRMED).value,
        analyst_override=scenario.scenario_source == ScenarioSource.ANALYST,
    )
    add_feature(
        family="location_and_access",
        name="scenario_is_stale",
        value=bool(getattr(scenario, "stale_reason", None)),
        analyst_override=scenario.scenario_source == ScenarioSource.ANALYST,
    )
    add_feature(
        family="location_and_access",
        name="access_assumption_present",
        value=bool((scenario.access_assumption or "").strip()),
        analyst_override=scenario.scenario_source == ScenarioSource.ANALYST,
    )
    add_feature(
        family="location_and_access",
        name="ptal_bucket",
        value=None,
        notes="PTAL is not onboarded in Phase 5A fixture data.",
    )
    add_feature(
        family="location_and_access",
        name="distance_to_station_m",
        value=None,
        notes="Station-distance source family is not onboarded in Phase 5A fixture data.",
    )

    label_rows = (
        session.execute(
            select(HistoricalCaseLabel).where(HistoricalCaseLabel.label_version == FEATURE_VERSION)
        )
        .scalars()
        .all()
    )
    label_by_application_id = {row.planning_application_id: row for row in label_rows}

    on_site_positive = 0
    on_site_negative = 0
    on_site_withdrawn = 0
    on_site_prior_approval = 0
    on_site_units_positive: list[int] = []
    on_site_units_negative: list[int] = []
    on_site_source_ids: set[str] = set()
    on_site_raw_ids: set[str] = set()
    active_extant_count = 0

    for link in site.planning_links:
        application = link.planning_application
        application_snapshot = planning_application_snapshot(link)
        if not _known_by_as_of_snapshot(
            application=application,
            snapshot=application_snapshot,
            as_of_date=as_of_date,
        ):
            continue
        source_snapshot_id = (
            getattr(link, "source_snapshot_id", None)
            or application_snapshot.get("source_snapshot_id")
            or application.source_snapshot_id
        )
        on_site_source_ids.add(str(source_snapshot_id))
        on_site_raw_ids.update(_planning_application_snapshot_raw_asset_ids(application_snapshot))
        route_normalized = str(
            application_snapshot.get("route_normalized") or application.route_normalized or ""
        )
        if route_normalized == "PRIOR_APPROVAL":
            on_site_prior_approval += 1
        label = label_by_application_id.get(application.id)
        units_proposed = application_snapshot.get("units_proposed")
        if not isinstance(units_proposed, int):
            units_proposed = application.units_proposed
        if (
            label
            and label.first_substantive_decision_date
            and label.first_substantive_decision_date <= as_of_date
        ):
            if label.label_class == HistoricalLabelClass.POSITIVE:
                on_site_positive += 1
                if units_proposed is not None:
                    on_site_units_positive.append(units_proposed)
            elif label.label_class == HistoricalLabelClass.NEGATIVE:
                on_site_negative += 1
                if units_proposed is not None:
                    on_site_units_negative.append(units_proposed)
        decision = str(application_snapshot.get("decision") or application.decision or "")
        if (
            decision.strip().upper() == "WITHDRAWN"
            and _decision_on_or_before_snapshot(
                application=application,
                snapshot=application_snapshot,
                as_of_date=as_of_date,
            )
        ):
            on_site_withdrawn += 1
        raw_record_json = application_snapshot.get("raw_record_json")
        if not isinstance(raw_record_json, dict):
            raw_record_json = dict(application.raw_record_json or {})
        if bool(
            raw_record_json.get("active_extant")
        ) and _decision_on_or_before_snapshot(
            application=application,
            snapshot=application_snapshot,
            as_of_date=as_of_date,
        ):
            active_extant_count += 1

    add_feature(
        family="planning_history_on_site",
        name="onsite_positive_count",
        value=on_site_positive,
        source_snapshot_ids=on_site_source_ids,
        raw_asset_ids=on_site_raw_ids,
    )
    add_feature(
        family="planning_history_on_site",
        name="onsite_negative_count",
        value=on_site_negative,
        source_snapshot_ids=on_site_source_ids,
        raw_asset_ids=on_site_raw_ids,
    )
    add_feature(
        family="planning_history_on_site",
        name="onsite_withdrawn_count",
        value=on_site_withdrawn,
        source_snapshot_ids=on_site_source_ids,
        raw_asset_ids=on_site_raw_ids,
    )
    add_feature(
        family="planning_history_on_site",
        name="prior_approval_history_count",
        value=on_site_prior_approval,
        source_snapshot_ids=on_site_source_ids,
        raw_asset_ids=on_site_raw_ids,
    )
    add_feature(
        family="planning_history_on_site",
        name="onsite_max_units_approved",
        value=max(on_site_units_positive) if on_site_units_positive else None,
        source_snapshot_ids=on_site_source_ids,
        raw_asset_ids=on_site_raw_ids,
    )
    add_feature(
        family="planning_history_on_site",
        name="onsite_max_units_refused",
        value=max(on_site_units_negative) if on_site_units_negative else None,
        source_snapshot_ids=on_site_source_ids,
        raw_asset_ids=on_site_raw_ids,
    )

    nearby_counts: dict[str, int] = {
        "adjacent_approved_0_50m": 0,
        "adjacent_refused_0_50m": 0,
        "local_precedent_approved_50_250m": 0,
        "local_precedent_refused_50_250m": 0,
        "local_context_approved_250_500m": 0,
        "local_context_refused_250_500m": 0,
        "same_template_positive_500m": 0,
    }
    nearby_source_ids: set[str] = set()
    nearby_raw_ids: set[str] = set()
    all_applications = session.execute(select(PlanningApplication)).scalars().all()
    linked_application_ids = {link.planning_application_id for link in site.planning_links}
    for application in all_applications:
        if application.id in linked_application_ids:
            continue
        if not _known_by_as_of(application=application, as_of_date=as_of_date):
            continue
        geometry = planning_application_geometry(application)
        if geometry is None:
            continue
        distance_m = float(site_geometry.distance(geometry))
        if distance_m > 500.0:
            continue
        label = label_by_application_id.get(application.id)
        if not (
            label
            and label.first_substantive_decision_date
            and label.first_substantive_decision_date <= as_of_date
        ):
            continue
        nearby_source_ids.add(str(application.source_snapshot_id))
        nearby_raw_ids.update(_planning_application_raw_asset_ids(application))
        if (
            label.label_class == HistoricalLabelClass.POSITIVE
            and label.template_key == scenario.template_key
        ):
            nearby_counts["same_template_positive_500m"] += 1
        for window_name, min_distance, max_distance in NEARBY_DISTANCE_WINDOWS:
            if distance_m < min_distance or distance_m > max_distance:
                continue
            key_prefix = {
                "adjacent": "adjacent",
                "local_precedent": "local_precedent",
                "local_context": "local_context",
            }[window_name]
            if label.label_class == HistoricalLabelClass.POSITIVE:
                nearby_counts[
                    f"{key_prefix}_approved_{int(min_distance)}_{int(max_distance)}m"
                ] += 1
            elif label.label_class == HistoricalLabelClass.NEGATIVE:
                nearby_counts[f"{key_prefix}_refused_{int(min_distance)}_{int(max_distance)}m"] += 1

    for name, value in nearby_counts.items():
        add_feature(
            family="nearby_planning_history",
            name=name,
            value=value,
            source_snapshot_ids=nearby_source_ids,
            raw_asset_ids=nearby_raw_ids,
        )

    for key in (
        "has_site_allocation",
        "has_density_guidance",
        "has_conservation_area",
        "has_article4",
        "has_flood_zone",
        "has_listed_building_nearby",
        "brownfield_part1",
        "brownfield_part2_active",
        "pip_active",
        "tdc_active",
    ):
        family = (
            "policy_and_designation_context"
            if key.startswith("has_")
            and "flood" not in key
            and "listed" not in key
            and "article4" not in key
            and "conservation" not in key
            else "environmental_and_heritage_context"
            if key.startswith("has_")
            else "permission_state_context"
        )
        add_feature(
            family=family,
            name=key,
            value=bool(designation_profile.get(key)),
            source_snapshot_ids=designation_source_ids,
        )

    add_feature(
        family="policy_and_designation_context",
        name="policy_area_count",
        value=len(designation_profile.get("policy_families") or []),
        source_snapshot_ids=designation_source_ids,
    )
    add_feature(
        family="environmental_and_heritage_context",
        name="constraint_profile_count",
        value=len(designation_profile.get("constraint_families") or []),
        source_snapshot_ids=designation_source_ids,
    )
    add_feature(
        family="permission_state_context",
        name="active_extant_permission_count",
        value=active_extant_count,
        source_snapshot_ids=on_site_source_ids,
        raw_asset_ids=on_site_raw_ids,
    )

    borough_template_labels = [
        row
        for row in label_rows
        if row.template_key == scenario.template_key
        and row.borough_id == site.borough_id
        and row.first_substantive_decision_date
        and row.first_substantive_decision_date <= as_of_date
        and row.label_class in {HistoricalLabelClass.POSITIVE, HistoricalLabelClass.NEGATIVE}
    ]
    borough_source_ids: set[str] = set()
    for row in borough_template_labels:
        borough_source_ids.update(row.source_snapshot_ids_json or [])
        all_raw_asset_ids.update(row.raw_asset_ids_json or [])
    borough_positive = sum(
        1 for row in borough_template_labels if row.label_class == HistoricalLabelClass.POSITIVE
    )
    borough_total = len(borough_template_labels)
    approval_rate = None if borough_total == 0 else round(borough_positive / borough_total, 4)
    decision_durations = [
        (row.first_substantive_decision_date - row.valid_date).days
        for row in borough_template_labels
        if row.valid_date and row.first_substantive_decision_date
    ]
    median_days = None if not decision_durations else int(statistics.median(decision_durations))

    add_feature(
        family="borough_and_market_context",
        name="borough_template_positive_rate",
        value=approval_rate,
        source_snapshot_ids=borough_source_ids,
    )
    add_feature(
        family="borough_and_market_context",
        name="borough_template_case_count",
        value=borough_total,
        source_snapshot_ids=borough_source_ids,
    )
    add_feature(
        family="borough_and_market_context",
        name="borough_template_median_days_to_decision",
        value=median_days,
        source_snapshot_ids=borough_source_ids,
    )
    add_feature(
        family="borough_and_market_context",
        name="asking_price_present",
        value=site.current_price_gbp is not None,
    )
    add_feature(
        family="borough_and_market_context",
        name="asking_price_basis_complete",
        value=site.current_price_basis_type != PriceBasisType.UNKNOWN,
    )
    add_feature(
        family="borough_and_market_context",
        name="current_price_gbp",
        value=site.current_price_gbp,
    )
    add_feature(
        family="borough_and_market_context",
        name="current_price_basis_type",
        value=(
            None
            if site.current_price_basis_type in {None, PriceBasisType.UNKNOWN}
            else site.current_price_basis_type.value
        ),
    )
    add_feature(
        family="borough_and_market_context",
        name="designation_archetype_key",
        value=derive_archetype_key(
            template_key=scenario.template_key,
            proposal_form=scenario.proposal_form,
            designation_profile=designation_profile,
        ),
        source_snapshot_ids=designation_source_ids,
    )

    feature_json = {
        "as_of_date": as_of_date.isoformat(),
        "transform_version": FEATURE_VERSION,
        "values": values,
        "missing_flags": missing_flags,
        "provenance": provenance,
        "families": families,
        "designation_profile": designation_profile,
    }
    coverage_json["missing_feature_count"] = sum(1 for missing in missing_flags.values() if missing)
    coverage_json["source_snapshot_ids"] = sorted(all_source_snapshot_ids)
    coverage_json["raw_asset_ids"] = sorted(all_raw_asset_ids)

    return FeatureBuildResult(
        feature_version=FEATURE_VERSION,
        feature_hash=canonical_json_hash(feature_json),
        feature_json=feature_json,
        coverage_json=coverage_json,
        source_snapshot_ids=sorted(all_source_snapshot_ids),
        raw_asset_ids=sorted(all_raw_asset_ids),
    )


def build_historical_feature_snapshot(
    *,
    session: Session,
    historical_label: HistoricalCaseLabel,
) -> FeatureBuildResult:
    application = historical_label.planning_application
    geometry_wkt = application.site_geom_27700 or application.site_point_27700
    if not geometry_wkt:
        raise ValueError(
            f"Historical case '{historical_label.id}' does not have a site geometry or point."
        )

    area_sqm = historical_label.site_area_sqm or planning_application_area_sqm(application)
    geometry = planning_application_geometry(application)
    if geometry is None:
        raise ValueError(
            f"Historical case '{historical_label.id}' does not have a usable planning geometry."
        )

    geom_type = (
        GeomSourceType.SOURCE_POLYGON
        if geometry.geom_type in {"Polygon", "MultiPolygon"}
        else GeomSourceType.POINT_ONLY
    )
    geom_confidence = (
        GeomConfidence.MEDIUM
        if geometry.geom_type in {"Polygon", "MultiPolygon"}
        else GeomConfidence.LOW
    )
    scenario = SimpleNamespace(
        template_key=historical_label.template_key,
        units_assumed=historical_label.units_proposed or 0,
        housing_mix_assumed_json={},
        proposal_form=historical_label.proposal_form or ProposalForm.REDEVELOPMENT,
        scenario_source=ScenarioSource.AUTO,
        route_assumed=application.route_normalized or "FULL",
        net_developable_area_pct=DEFAULT_TEMPLATE_NET_DEVELOPABLE_AREA_PCT.get(
            historical_label.template_key or "",
            0.7,
        ),
        access_assumption=None,
    )
    site = SimpleNamespace(
        id=historical_label.id,
        geom_27700=geometry_wkt,
        site_area_sqm=area_sqm or 0.0,
        geom_source_type=geom_type,
        geom_confidence=geom_confidence,
        borough_id=historical_label.borough_id,
        current_price_gbp=None,
        current_price_basis_type=PriceBasisType.UNKNOWN,
        planning_links=[
            SimpleNamespace(
                planning_application_id=application.id,
                planning_application=application,
                overlap_pct=1.0,
                distance_m=0.0,
            )
        ],
        manual_review_required=False,
    )
    as_of_date = application.valid_date or historical_label.valid_date or application.decision_date
    if as_of_date is None:
        raise ValueError(
            f"Historical case '{historical_label.id}' does not have a stable as_of_date."
        )
    return build_feature_snapshot(
        session=session,
        site=site,
        scenario=scenario,
        as_of_date=as_of_date,
    )


def _active_on_date(
    *,
    effective_from: date | None,
    effective_to: date | None,
    as_of_date: date,
) -> bool:
    if effective_from is not None and effective_from > as_of_date:
        return False
    return not (effective_to is not None and effective_to < as_of_date)


def _parse_snapshot_date(value: object) -> date | None:
    if not isinstance(value, str) or not value:
        return None
    return date.fromisoformat(value)


def _known_by_as_of(*, application: PlanningApplication, as_of_date: date) -> bool:
    return not (application.valid_date is not None and application.valid_date > as_of_date)


def _decision_on_or_before(*, application: PlanningApplication, as_of_date: date) -> bool:
    return application.decision_date is not None and application.decision_date <= as_of_date


def _known_by_as_of_snapshot(
    *,
    application: PlanningApplication,
    snapshot: dict[str, Any],
    as_of_date: date,
) -> bool:
    valid_date = _parse_snapshot_date(snapshot.get("valid_date")) or application.valid_date
    return not (valid_date is not None and valid_date > as_of_date)


def _decision_on_or_before_snapshot(
    *,
    application: PlanningApplication,
    snapshot: dict[str, Any],
    as_of_date: date,
) -> bool:
    decision_date = _parse_snapshot_date(snapshot.get("decision_date")) or application.decision_date
    return decision_date is not None and decision_date <= as_of_date


def _planning_application_raw_asset_ids(application: PlanningApplication) -> set[str]:
    ids: set[str] = set()
    for document in application.documents:
        ids.add(str(document.asset_id))
    return ids


def _planning_application_snapshot_raw_asset_ids(snapshot: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for document in snapshot.get("documents") or []:
        if not isinstance(document, dict):
            continue
        asset_id = document.get("asset_id")
        if asset_id:
            ids.add(str(asset_id))
    return ids


def _latest_coverage_rows(
    *,
    session: Session,
    borough_id: str | None,
) -> list[SourceCoverageSnapshot]:
    if borough_id is None:
        return []
    rows = (
        session.execute(
            select(SourceCoverageSnapshot)
            .where(SourceCoverageSnapshot.borough_id == borough_id)
            .order_by(
                SourceCoverageSnapshot.source_family.asc(),
                SourceCoverageSnapshot.captured_at.desc(),
            )
        )
        .scalars()
        .all()
    )
    latest: dict[str, SourceCoverageSnapshot] = {}
    for row in rows:
        latest.setdefault(row.source_family, row)
    return list(latest.values())
