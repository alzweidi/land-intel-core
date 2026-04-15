from __future__ import annotations

import math
from typing import Any

from landintel.scoring.logreg_model import clamp_probability, sigmoid


def fit_platt_scaler(
    *,
    raw_probabilities: list[float],
    labels: list[int],
    iterations: int = 1600,
    learning_rate: float = 0.14,
    l2_lambda: float = 0.02,
) -> dict[str, Any]:
    if not raw_probabilities:
        raise ValueError("Cannot fit calibration without probability inputs.")

    logits = [
        math.log(clamp_probability(probability) / (1.0 - clamp_probability(probability)))
        for probability in raw_probabilities
    ]
    intercept = 0.0
    slope = 1.0
    current_learning_rate = learning_rate
    row_count = len(logits)

    for iteration in range(iterations):
        intercept_gradient = 0.0
        slope_gradient = 0.0
        for logit_value, label in zip(logits, labels, strict=True):
            calibrated = sigmoid(intercept + (slope * logit_value))
            error = calibrated - label
            intercept_gradient += error
            slope_gradient += error * logit_value

        intercept_gradient /= row_count
        slope_gradient = (slope_gradient / row_count) + (l2_lambda * slope)
        intercept -= current_learning_rate * intercept_gradient
        slope -= current_learning_rate * slope_gradient

        if iteration > 0 and iteration % 600 == 0:
            current_learning_rate *= 0.6

    return {
        "method": "PLATT",
        "intercept": round(intercept, 12),
        "slope": round(slope, 12),
        "iterations": iterations,
        "learning_rate": learning_rate,
        "l2_lambda": l2_lambda,
    }


def apply_calibration(
    probability: float,
    *,
    calibration_artifact: dict[str, Any] | None,
) -> float:
    if not calibration_artifact or calibration_artifact.get("method") in {None, "NONE"}:
        return clamp_probability(probability)
    logit_value = math.log(clamp_probability(probability) / (1.0 - clamp_probability(probability)))
    slope = float(calibration_artifact.get("slope", 1.0))
    intercept = float(calibration_artifact.get("intercept", 0.0))
    return clamp_probability(sigmoid(intercept + (slope * logit_value)))
