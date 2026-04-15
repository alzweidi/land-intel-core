from __future__ import annotations

from typing import Any

from landintel.domain.models import ComparableCaseSet, SiteCandidate, SiteScenario
from landintel.domain.schemas import EvidencePackRead
from landintel.scoring.calibration import apply_calibration
from landintel.scoring.explain import generate_hidden_score_explanation
from landintel.scoring.logreg_model import encode_feature_values, predict_probability_from_vector
from landintel.scoring.quality import (
    derive_geometry_quality,
    derive_ood_status,
    derive_scenario_quality,
    derive_source_coverage_quality,
    derive_support_quality,
    final_estimate_quality,
    round_display_probability,
)


def score_frozen_assessment(
    *,
    model_artifact: dict[str, Any],
    calibration_artifact: dict[str, Any] | None,
    validation_artifact: dict[str, Any],
    release_id: str,
    feature_json: dict[str, Any],
    coverage_json: dict[str, Any],
    site: SiteCandidate,
    scenario: SiteScenario,
    evidence: EvidencePackRead,
    comparable_case_set: ComparableCaseSet | None,
    comparable_payload: dict[str, Any],
) -> dict[str, Any]:
    feature_values = dict(feature_json.get("values") or {})
    vector = encode_feature_values(
        feature_values,
        transform_spec=model_artifact["transform_spec"],
    )
    raw_probability = predict_probability_from_vector(model_artifact, vector)
    calibrated_probability = apply_calibration(
        raw_probability,
        calibration_artifact=calibration_artifact,
    )

    support_summary = dict(model_artifact.get("training_support") or {})
    training_vectors = list(support_summary.get("training_vectors") or [])
    nearest_distance = None
    if training_vectors:
        nearest_distance = min(
            sum((left - right) ** 2 for left, right in zip(vector, other, strict=True)) ** 0.5
            for other in training_vectors
        )
    same_template_support_count = int(support_summary.get("same_template_support_count") or 0)
    same_borough_support_count = int(
        dict(support_summary.get("borough_counts") or {}).get(site.borough_id or "unknown", 0)
    )
    comparable_count = (
        0
        if comparable_case_set is None
        else comparable_case_set.approved_count + comparable_case_set.refused_count
    )

    source_coverage_quality = derive_source_coverage_quality(coverage_json)
    geometry_quality = derive_geometry_quality(site.geom_confidence)
    scenario_quality = derive_scenario_quality(scenario=scenario, site=site)
    support_quality = derive_support_quality(
        support_count=same_template_support_count,
        same_borough_support_count=same_borough_support_count,
        comparable_count=comparable_count,
    )
    ood_status, ood_quality = derive_ood_status(
        nearest_distance=nearest_distance,
        same_template_support_count=same_template_support_count,
        same_borough_support_count=same_borough_support_count,
        distance_thresholds=dict(support_summary.get("distance_thresholds") or {}),
    )
    estimate_quality = final_estimate_quality(
        quality_components=[
            source_coverage_quality,
            geometry_quality,
            support_quality,
            scenario_quality,
            ood_quality,
        ]
    )
    manual_review_required = bool(
        site.manual_review_required
        or scenario.manual_review_required
        or estimate_quality.value == "LOW"
        or ood_status != "IN_SUPPORT"
    )
    explanation = generate_hidden_score_explanation(
        model_artifact=model_artifact,
        feature_json=feature_json,
        evidence=evidence,
        comparable_payload=comparable_payload,
        coverage_json=coverage_json,
        model_release_id=release_id,
    )
    return {
        "approval_probability_raw": round(calibrated_probability, 8),
        "approval_probability_display": round_display_probability(calibrated_probability),
        "estimate_quality": estimate_quality.value,
        "source_coverage_quality": source_coverage_quality,
        "geometry_quality": geometry_quality,
        "support_quality": support_quality,
        "scenario_quality": scenario_quality,
        "ood_quality": ood_quality,
        "ood_status": ood_status,
        "manual_review_required": manual_review_required,
        "support_summary": {
            "same_template_support_count": same_template_support_count,
            "same_borough_support_count": same_borough_support_count,
            "nearest_support_distance": (
                None if nearest_distance is None else round(nearest_distance, 6)
            ),
        },
        "validation_summary": {
            "status": validation_artifact.get("status"),
            "metrics": dict(validation_artifact.get("metrics") or {}),
        },
        "explanation": explanation,
    }
