from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from landintel.domain.enums import GoldSetReviewStatus, HistoricalLabelClass
from landintel.domain.models import HistoricalCaseLabel, PlanningApplication
from landintel.domain.schemas import EvidencePackRead
from landintel.features.build import (
    FEATURE_VERSION,
    build_historical_feature_snapshot,
    canonical_json_hash,
)
from landintel.scoring.calibration import apply_calibration, fit_platt_scaler
from landintel.scoring.explain import generate_hidden_score_explanation
from landintel.scoring.logreg_model import (
    derive_transform_spec,
    encode_feature_values,
    fit_logistic_regression,
    predict_probability_from_vector,
)

SCORING_TRANSFORM_VERSION = "phase6a_hidden_logreg_v1"
MODEL_KIND = "REGULARIZED_LOGISTIC_REGRESSION"
MIN_SUPPORT_COUNT = 7
MIN_CLASS_COUNT = 3
NUMERIC_FEATURES = [
    "site_area_sqm",
    "site_compactness",
    "scenario_units_assumed",
    "scenario_net_developable_area_pct",
    "onsite_positive_count",
    "onsite_negative_count",
    "prior_approval_history_count",
    "onsite_max_units_approved",
    "onsite_max_units_refused",
    "adjacent_approved_0_50m",
    "adjacent_refused_0_50m",
    "local_precedent_approved_50_250m",
    "local_precedent_refused_50_250m",
    "local_context_approved_250_500m",
    "local_context_refused_250_500m",
    "same_template_positive_500m",
    "policy_area_count",
    "constraint_profile_count",
    "active_extant_permission_count",
]
CATEGORICAL_FEATURES = [
    "borough_id",
    "geom_confidence",
    "geom_source_type",
    "scenario_proposal_form",
    "scenario_route_assumed",
    "designation_archetype_key",
]
BOOLEAN_FEATURES = [
    "access_assumption_present",
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
]
FORBIDDEN_FEATURES = {
    "borough_template_positive_rate",
    "borough_template_case_count",
    "borough_template_median_days_to_decision",
    "current_price_gbp",
    "asking_price_present",
    "asking_price_basis_complete",
}


@dataclass(slots=True)
class HistoricalTrainingRow:
    case: HistoricalCaseLabel
    label: int
    feature_hash: str
    feature_json: dict[str, Any]
    source_snapshot_ids: list[str]
    raw_asset_ids: list[str]


def load_training_rows(
    *,
    session: Session,
    template_key: str,
) -> list[HistoricalTrainingRow]:
    rows = (
        session.execute(
            select(HistoricalCaseLabel)
            .where(HistoricalCaseLabel.label_version == FEATURE_VERSION)
            .where(HistoricalCaseLabel.template_key == template_key)
            .where(
                HistoricalCaseLabel.label_class.in_(
                    [HistoricalLabelClass.POSITIVE, HistoricalLabelClass.NEGATIVE]
                )
            )
            .where(HistoricalCaseLabel.review_status != GoldSetReviewStatus.EXCLUDED)
            .options(
                selectinload(HistoricalCaseLabel.planning_application).selectinload(
                    PlanningApplication.documents
                )
            )
            .order_by(
                HistoricalCaseLabel.valid_date.asc().nullslast(),
                HistoricalCaseLabel.first_substantive_decision_date.asc().nullslast(),
                HistoricalCaseLabel.id.asc(),
            )
        )
        .scalars()
        .all()
    )
    output: list[HistoricalTrainingRow] = []
    for row in rows:
        feature_result = build_historical_feature_snapshot(session=session, historical_label=row)
        output.append(
            HistoricalTrainingRow(
                case=row,
                label=1 if row.label_class == HistoricalLabelClass.POSITIVE else 0,
                feature_hash=feature_result.feature_hash,
                feature_json=feature_result.feature_json,
                source_snapshot_ids=feature_result.source_snapshot_ids,
                raw_asset_ids=feature_result.raw_asset_ids,
            )
        )
    return output


def training_readiness(
    *,
    rows: list[HistoricalTrainingRow],
) -> list[str]:
    reasons: list[str] = []
    positives = sum(row.label for row in rows)
    negatives = len(rows) - positives
    if len(rows) < MIN_SUPPORT_COUNT:
        reasons.append(
            f"Support count {len(rows)} is below the hidden-release minimum of {MIN_SUPPORT_COUNT}."
        )
    if positives < MIN_CLASS_COUNT:
        reasons.append(
            f"Positive support count {positives} is below the minimum of {MIN_CLASS_COUNT}."
        )
    if negatives < MIN_CLASS_COUNT:
        reasons.append(
            f"Negative support count {negatives} is below the minimum of {MIN_CLASS_COUNT}."
        )
    return reasons


def _feature_rows(rows: list[HistoricalTrainingRow]) -> list[dict[str, Any]]:
    return [dict(row.feature_json.get("values") or {}) for row in rows]


def _label_values(rows: list[HistoricalTrainingRow]) -> list[int]:
    return [row.label for row in rows]


def _ensure_feature_guard(feature_rows: list[dict[str, Any]]) -> dict[str, Any]:
    used = set(NUMERIC_FEATURES) | set(CATEGORICAL_FEATURES) | set(BOOLEAN_FEATURES)
    forbidden_used = sorted(used & FORBIDDEN_FEATURES)
    return {
        "forbidden_features_present": forbidden_used,
        "forbidden_features_clean": not forbidden_used,
    }


def _train_once(
    rows: list[HistoricalTrainingRow],
) -> tuple[dict[str, Any], dict[str, Any], list[list[float]]]:
    feature_rows = _feature_rows(rows)
    transform_spec = derive_transform_spec(
        feature_rows=feature_rows,
        numeric_features=NUMERIC_FEATURES,
        categorical_features=CATEGORICAL_FEATURES,
        boolean_features=BOOLEAN_FEATURES,
    )
    encoded_rows = [
        encode_feature_values(feature_row, transform_spec=transform_spec)
        for feature_row in feature_rows
    ]
    labels = _label_values(rows)
    model_core = fit_logistic_regression(encoded_rows=encoded_rows, labels=labels)
    model_artifact = {
        "model_kind": MODEL_KIND,
        "feature_version": FEATURE_VERSION,
        "transform_version": SCORING_TRANSFORM_VERSION,
        "transform_spec": transform_spec,
        **model_core,
    }
    raw_probabilities = [
        predict_probability_from_vector(model_artifact, encoded_row) for encoded_row in encoded_rows
    ]
    calibration_artifact = fit_platt_scaler(raw_probabilities=raw_probabilities, labels=labels)
    return model_artifact, calibration_artifact, encoded_rows


def _nearest_neighbor_distance(row: list[float], others: list[list[float]]) -> float | None:
    if not others:
        return None
    return min(
        sum((left - right) ** 2 for left, right in zip(row, other, strict=True)) ** 0.5
        for other in others
    )


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * percentile)))
    return ordered[index]


def _calibration_by_band(probabilities: list[float], labels: list[int]) -> list[dict[str, Any]]:
    buckets: dict[int, list[tuple[float, int]]] = {}
    for probability, label in zip(probabilities, labels, strict=True):
        band = int(round((probability * 100.0) / 5.0) * 5)
        buckets.setdefault(band, []).append((probability, label))
    summary: list[dict[str, Any]] = []
    for band in sorted(buckets):
        items = buckets[band]
        summary.append(
            {
                "band": f"{band}%",
                "count": len(items),
                "mean_probability_pct": round(
                    sum(probability for probability, _ in items) / len(items) * 100.0,
                    2,
                ),
                "observed_positive_rate_pct": round(
                    sum(label for _, label in items) / len(items) * 100.0,
                    2,
                ),
            }
        )
    return summary


def _log_loss(probabilities: list[float], labels: list[int]) -> float:
    losses = []
    for probability, label in zip(probabilities, labels, strict=True):
        clipped = min(max(probability, 1e-6), 1.0 - 1e-6)
        if label == 1:
            losses.append(-math.log(clipped))
        else:
            losses.append(-math.log(1.0 - clipped))
    return round(sum(losses) / len(losses), 6)


def _brier_score(probabilities: list[float], labels: list[int]) -> float:
    squared = [
        (probability - label) ** 2
        for probability, label in zip(probabilities, labels, strict=True)
    ]
    return round(sum(squared) / len(squared), 6)


def _cross_validated_probabilities(rows: list[HistoricalTrainingRow]) -> list[float]:
    probabilities: list[float] = []
    for holdout_index, _ in enumerate(rows):
        train_rows = [row for index, row in enumerate(rows) if index != holdout_index]
        test_row = rows[holdout_index]
        model_artifact, calibration_artifact, _ = _train_once(train_rows)
        test_vector = encode_feature_values(
            dict(test_row.feature_json.get("values") or {}),
            transform_spec=model_artifact["transform_spec"],
        )
        raw_probability = predict_probability_from_vector(model_artifact, test_vector)
        probabilities.append(
            apply_calibration(
                raw_probability,
                calibration_artifact=calibration_artifact,
            )
        )
    return probabilities


def build_training_manifest(
    *,
    template_key: str,
    rows: list[HistoricalTrainingRow],
) -> dict[str, Any]:
    reasons = training_readiness(rows=rows)
    feature_rows = _feature_rows(rows)
    labels = _label_values(rows)
    leakage_checks = _ensure_feature_guard(feature_rows)
    leakage_checks["feature_as_of_matches_validation_date"] = all(
        row.case.valid_date is None
        or row.feature_json.get("as_of_date") == row.case.valid_date.isoformat()
        for row in rows
    )
    leakage_checks["no_current_decision_in_pit_window"] = all(
        row.case.first_substantive_decision_date is None
        or row.case.valid_date is None
        or row.case.first_substantive_decision_date >= row.case.valid_date
        for row in rows
    )

    support_counts = {
        "total": len(rows),
        "positive": sum(labels),
        "negative": len(labels) - sum(labels),
        "borough_counts": dict(
            sorted(Counter(row.case.borough_id or "unknown" for row in rows).items())
        ),
    }

    if reasons:
        payload_hash = canonical_json_hash(
            {
                "template_key": template_key,
                "support_counts": support_counts,
                "feature_hashes": [row.feature_hash for row in rows],
                "transform_version": SCORING_TRANSFORM_VERSION,
                "status": "NOT_READY",
            }
        )
        return {
            "status": "NOT_READY",
            "template_key": template_key,
            "feature_version": FEATURE_VERSION,
            "transform_version": SCORING_TRANSFORM_VERSION,
            "support_counts": support_counts,
            "not_ready_reasons": reasons,
            "leakage_checks": leakage_checks,
            "source_snapshot_ids": sorted(
                {
                    source_id
                    for row in rows
                    for source_id in row.source_snapshot_ids
                }
            ),
            "raw_asset_ids": sorted(
                {
                    asset_id
                    for row in rows
                    for asset_id in row.raw_asset_ids
                }
            ),
            "feature_hashes": [row.feature_hash for row in rows],
            "payload_hash": payload_hash,
            "rows": [
                {
                    "case_id": str(row.case.id),
                    "planning_application_id": str(row.case.planning_application_id),
                    "feature_hash": row.feature_hash,
                    "label": row.label,
                }
                for row in rows
            ],
        }

    model_artifact, calibration_artifact, encoded_rows = _train_once(rows)
    calibrated_probabilities = [
        apply_calibration(
            predict_probability_from_vector(model_artifact, encoded_row),
            calibration_artifact=calibration_artifact,
        )
        for encoded_row in encoded_rows
    ]
    cross_validated = _cross_validated_probabilities(rows)
    nearest_distances = [
        _nearest_neighbor_distance(
            encoded_row,
            [other for index, other in enumerate(encoded_rows) if index != row_index],
        )
        for row_index, encoded_row in enumerate(encoded_rows)
    ]
    distance_values = [value for value in nearest_distances if value is not None]
    training_support = {
        "same_template_support_count": len(rows),
        "borough_counts": support_counts["borough_counts"],
        "training_vectors": encoded_rows,
        "training_case_ids": [str(row.case.id) for row in rows],
        "distance_thresholds": {
            "medium": round(_percentile(distance_values, 0.75), 6),
            "high": round(_percentile(distance_values, 0.9), 6),
        },
    }
    model_artifact["training_support"] = training_support
    explanation_probe = generate_hidden_score_explanation(
        model_artifact=model_artifact,
        feature_json=rows[0].feature_json,
        evidence=EvidencePackRead(for_=[], against=[], unknown=[]),
        comparable_payload={"approved": [], "refused": []},
        coverage_json={"source_coverage": []},
        model_release_id="validation-probe",
    )
    validation = {
        "status": "VALIDATED",
        "template_key": template_key,
        "feature_version": FEATURE_VERSION,
        "transform_version": SCORING_TRANSFORM_VERSION,
        "support_counts": support_counts,
        "metrics": {
            "brier_score": _brier_score(cross_validated, labels),
            "log_loss": _log_loss(cross_validated, labels),
            "calibration_by_band": _calibration_by_band(cross_validated, labels),
            "mean_calibrated_probability_pct": round(
                sum(calibrated_probabilities) / len(calibrated_probabilities) * 100.0,
                2,
            ),
        },
        "leakage_checks": leakage_checks,
        "explanation_completeness": {
            "has_positive_or_negative_drivers": bool(
                explanation_probe["top_positive_drivers"]
                or explanation_probe["top_negative_drivers"]
            ),
            "missing_unknowns_emitted": isinstance(explanation_probe["unknowns"], list),
        },
        "rows": [
            {
                "case_id": str(row.case.id),
                "planning_application_id": str(row.case.planning_application_id),
                "feature_hash": row.feature_hash,
                "label": row.label,
                "valid_date": (
                    None if row.case.valid_date is None else row.case.valid_date.isoformat()
                ),
            }
            for row in rows
        ],
    }
    return {
        "status": "VALIDATED",
        "template_key": template_key,
        "feature_version": FEATURE_VERSION,
        "transform_version": SCORING_TRANSFORM_VERSION,
        "support_counts": support_counts,
        "model_artifact": model_artifact,
        "calibration_artifact": calibration_artifact,
        "validation": validation,
        "source_snapshot_ids": sorted(
            {
                source_id
                for row in rows
                for source_id in row.source_snapshot_ids
            }
        ),
        "raw_asset_ids": sorted(
            {
                asset_id
                for row in rows
                for asset_id in row.raw_asset_ids
            }
        ),
        "feature_hashes": [row.feature_hash for row in rows],
        "train_window_start": min(
            (row.case.valid_date for row in rows if row.case.valid_date is not None),
            default=None,
        ),
        "train_window_end": max(
            (row.case.valid_date for row in rows if row.case.valid_date is not None),
            default=None,
        ),
        "payload_hash": canonical_json_hash(
            {
                "template_key": template_key,
                "support_counts": support_counts,
                "feature_hashes": [row.feature_hash for row in rows],
                "transform_version": SCORING_TRANSFORM_VERSION,
            }
        ),
    }


def build_model_card_markdown(manifest: dict[str, Any]) -> str:
    support = manifest.get("support_counts") or {}
    status = str(manifest.get("status") or "UNKNOWN")
    lines = [
        "# Hidden model release",
        "",
        f"- Template: `{manifest.get('template_key')}`",
        f"- Status: `{status}`",
        f"- Feature version: `{manifest.get('feature_version')}`",
        f"- Transform version: `{manifest.get('transform_version')}`",
        f"- Support count: `{support.get('total', 0)}`",
        f"- Positive count: `{support.get('positive', 0)}`",
        f"- Negative count: `{support.get('negative', 0)}`",
    ]
    if status == "NOT_READY":
        lines.extend(
            [
                "",
                "## Not ready reasons",
                *[f"- {reason}" for reason in list(manifest.get("not_ready_reasons") or [])],
            ]
        )
    else:
        metrics = (manifest.get("validation") or {}).get("metrics") or {}
        lines.extend(
            [
                "",
                "## Validation",
                f"- Brier score: `{metrics.get('brier_score')}`",
                f"- Log loss: `{metrics.get('log_loss')}`",
                (
                    "- Mean calibrated probability pct: "
                    f"`{metrics.get('mean_calibrated_probability_pct')}`"
                ),
            ]
        )
    return "\n".join(lines) + "\n"
