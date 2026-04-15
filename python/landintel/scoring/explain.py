from __future__ import annotations

from typing import Any

from landintel.domain.schemas import EvidencePackRead
from landintel.scoring.logreg_model import explain_base_feature_contributions

FEATURE_LABELS = {
    "site_area_sqm": "Site area",
    "site_compactness": "Geometry compactness",
    "scenario_units_assumed": "Units assumed",
    "scenario_net_developable_area_pct": "Net developable area assumption",
    "onsite_positive_count": "On-site positive planning history",
    "onsite_negative_count": "On-site refused planning history",
    "prior_approval_history_count": "Prior approval history",
    "same_template_positive_500m": "Nearby same-template approvals",
    "has_site_allocation": "Site allocation context",
    "has_density_guidance": "Density guidance context",
    "has_conservation_area": "Conservation area constraint",
    "has_article4": "Article 4 constraint",
    "has_flood_zone": "Flood-zone context",
    "brownfield_part1": "Brownfield Part 1 context",
    "brownfield_part2_active": "Brownfield Part 2 context",
    "pip_active": "PiP context",
    "tdc_active": "TDC context",
    "geom_confidence": "Geometry confidence",
    "scenario_proposal_form": "Proposal form",
    "scenario_route_assumed": "Route assumption",
    "borough_id": "Borough",
    "designation_archetype_key": "Designation archetype",
}


def _feature_label(name: str) -> str:
    return FEATURE_LABELS.get(name, name.replace("_", " ").capitalize())


def generate_hidden_score_explanation(
    *,
    model_artifact: dict[str, Any],
    feature_json: dict[str, Any],
    evidence: EvidencePackRead,
    comparable_payload: dict[str, Any],
    coverage_json: dict[str, Any],
    model_release_id: str,
) -> dict[str, Any]:
    feature_values = dict(feature_json.get("values") or {})
    contributions = explain_base_feature_contributions(
        model_artifact,
        feature_values=feature_values,
    )
    positive = [
        {
            "feature": feature,
            "label": _feature_label(feature),
            "contribution": round(value, 6),
        }
        for feature, value in sorted(
            contributions.items(),
            key=lambda item: (-item[1], item[0]),
        )
        if value > 0
    ][:5]
    negative = [
        {
            "feature": feature,
            "label": _feature_label(feature),
            "contribution": round(value, 6),
        }
        for feature, value in sorted(
            contributions.items(),
            key=lambda item: (item[1], item[0]),
        )
        if value < 0
    ][:5]
    missing_unknowns = [
        {
            "feature": feature,
            "label": _feature_label(feature),
        }
        for feature, missing in sorted((feature_json.get("missing_flags") or {}).items())
        if missing
    ][:8]
    freshness_summary = [
        {
            "source_family": row.get("source_family"),
            "coverage_status": row.get("coverage_status"),
            "freshness_status": row.get("freshness_status"),
            "gap_reason": row.get("gap_reason"),
        }
        for row in list(coverage_json.get("source_coverage") or [])
    ]
    evidence_links = [
        {
            "topic": item.topic,
            "source_label": item.source_label,
            "source_url": item.source_url,
            "source_snapshot_id": (
                None if item.source_snapshot_id is None else str(item.source_snapshot_id)
            ),
            "raw_asset_id": None if item.raw_asset_id is None else str(item.raw_asset_id),
        }
        for item in [*evidence.for_, *evidence.against, *evidence.unknown]
        if item.source_url or item.source_snapshot_id or item.raw_asset_id
    ][:12]
    return {
        "target_definition": "Positive first substantive decision within 18 months of validation.",
        "top_positive_drivers": positive,
        "top_negative_drivers": negative,
        "unknowns": missing_unknowns,
        "comparable_approved_cases": list(comparable_payload.get("approved") or []),
        "comparable_refused_cases": list(comparable_payload.get("refused") or []),
        "source_freshness_summary": freshness_summary,
        "model_release_id": model_release_id,
        "evidence_links": evidence_links,
    }
