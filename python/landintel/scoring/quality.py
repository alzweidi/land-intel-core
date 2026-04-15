from __future__ import annotations

import math
from typing import Any

from landintel.domain.enums import EstimateQuality, GeomConfidence, ScenarioStatus
from landintel.domain.models import SiteCandidate, SiteScenario

QUALITY_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


def round_display_probability(probability: float) -> str:
    rounded = int(math.floor((probability * 100.0) / 5.0 + 0.5) * 5)
    rounded = max(0, min(100, rounded))
    return f"{rounded}%"


def derive_source_coverage_quality(coverage_json: dict[str, Any]) -> str:
    rows = list(coverage_json.get("source_coverage") or [])
    if not rows:
        return "LOW"
    statuses = {str(row.get("coverage_status") or "UNKNOWN").upper() for row in rows}
    freshness = {str(row.get("freshness_status") or "UNKNOWN").upper() for row in rows}
    if "MISSING" in statuses:
        return "LOW"
    if "PARTIAL" in statuses or "STALE" in freshness or "UNKNOWN" in freshness:
        return "MEDIUM"
    return "HIGH"


def derive_geometry_quality(geom_confidence: GeomConfidence) -> str:
    if geom_confidence == GeomConfidence.HIGH:
        return "HIGH"
    if geom_confidence == GeomConfidence.MEDIUM:
        return "MEDIUM"
    return "LOW"


def derive_scenario_quality(*, scenario: SiteScenario, site: SiteCandidate) -> str:
    if scenario.stale_reason or scenario.status not in {
        ScenarioStatus.AUTO_CONFIRMED,
        ScenarioStatus.ANALYST_CONFIRMED,
    }:
        return "LOW"
    if scenario.manual_review_required or site.manual_review_required:
        return "MEDIUM"
    return "HIGH"


def derive_support_quality(
    *,
    support_count: int,
    same_borough_support_count: int,
    comparable_count: int,
) -> str:
    if support_count >= 10 and same_borough_support_count >= 3 and comparable_count >= 4:
        return "HIGH"
    if support_count >= 7 and comparable_count >= 2:
        return "MEDIUM"
    return "LOW"


def derive_ood_status(
    *,
    nearest_distance: float | None,
    same_template_support_count: int,
    same_borough_support_count: int,
    distance_thresholds: dict[str, float],
) -> tuple[str, str]:
    if same_template_support_count < 7:
        return "OUT_OF_DISTRIBUTION", "LOW"
    if same_borough_support_count == 0:
        return "EDGE_OF_SUPPORT", "LOW"
    if nearest_distance is None:
        return "EDGE_OF_SUPPORT", "LOW"
    if nearest_distance > float(distance_thresholds.get("high", 3.0)):
        return "OUT_OF_DISTRIBUTION", "LOW"
    if nearest_distance > float(distance_thresholds.get("medium", 1.8)):
        return "EDGE_OF_SUPPORT", "MEDIUM"
    return "IN_SUPPORT", "HIGH"


def final_estimate_quality(*, quality_components: list[str]) -> EstimateQuality:
    if not quality_components:
        return EstimateQuality.LOW
    lowest = min(quality_components, key=lambda value: QUALITY_ORDER.get(value, -1))
    if lowest == "HIGH":
        return EstimateQuality.HIGH
    if lowest == "MEDIUM":
        return EstimateQuality.MEDIUM
    return EstimateQuality.LOW
