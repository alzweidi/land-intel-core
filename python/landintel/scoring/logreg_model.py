from __future__ import annotations

import math
from typing import Any


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def _mean(values: list[float]) -> float:
    return 0.0 if not values else sum(values) / len(values)


def _stddev(values: list[float], mean_value: float) -> float:
    if len(values) <= 1:
        return 1.0
    variance = sum((value - mean_value) ** 2 for value in values) / len(values)
    if variance <= 0.0:
        return 1.0
    return math.sqrt(variance)


def sigmoid(value: float) -> float:
    if value >= 0:
        exp_value = math.exp(-value)
        return 1.0 / (1.0 + exp_value)
    exp_value = math.exp(value)
    return exp_value / (1.0 + exp_value)


def clamp_probability(value: float) -> float:
    return min(max(value, 1e-6), 1.0 - 1e-6)


def derive_transform_spec(
    *,
    feature_rows: list[dict[str, Any]],
    numeric_features: list[str],
    categorical_features: list[str],
    boolean_features: list[str],
) -> dict[str, Any]:
    numeric: dict[str, dict[str, Any]] = {}
    categorical: dict[str, dict[str, Any]] = {}
    boolean: dict[str, dict[str, Any]] = {}
    encoded_feature_names: list[str] = []
    encoded_feature_bases: list[str] = []

    for name in numeric_features:
        present = [
            float(value)
            for row in feature_rows
            if (value := row.get(name)) is not None
        ]
        median = _median(present)
        filled = [
            float(row.get(name) if row.get(name) is not None else median)
            for row in feature_rows
        ]
        mean_value = _mean(filled)
        std_value = _stddev(filled, mean_value)
        has_missing = any(row.get(name) is None for row in feature_rows)
        numeric[name] = {
            "median": round(median, 12),
            "mean": round(mean_value, 12),
            "std": round(std_value, 12),
            "has_missing": has_missing,
        }
        encoded_feature_names.append(name)
        encoded_feature_bases.append(name)
        if has_missing:
            encoded_feature_names.append(f"{name}__missing")
            encoded_feature_bases.append(name)

    for name in categorical_features:
        categories = sorted(
            {
                str(value)
                for row in feature_rows
                if (value := row.get(name)) not in {None, ""}
            }
        )
        has_missing = any(row.get(name) in {None, ""} for row in feature_rows)
        if has_missing:
            categories.append("__MISSING__")
        categorical[name] = {
            "categories": categories,
            "has_missing": has_missing,
        }
        for category in categories:
            encoded_feature_names.append(f"{name}={category}")
            encoded_feature_bases.append(name)

    for name in boolean_features:
        has_missing = any(row.get(name) is None for row in feature_rows)
        boolean[name] = {"has_missing": has_missing}
        encoded_feature_names.append(name)
        encoded_feature_bases.append(name)
        if has_missing:
            encoded_feature_names.append(f"{name}__missing")
            encoded_feature_bases.append(name)

    return {
        "numeric": numeric,
        "categorical": categorical,
        "boolean": boolean,
        "encoded_feature_names": encoded_feature_names,
        "encoded_feature_bases": encoded_feature_bases,
    }


def encode_feature_values(
    feature_values: dict[str, Any],
    *,
    transform_spec: dict[str, Any],
) -> list[float]:
    vector: list[float] = []

    for name, metadata in transform_spec["numeric"].items():
        raw_value = feature_values.get(name)
        missing = raw_value is None
        filled = metadata["median"] if missing else float(raw_value)
        std_value = float(metadata["std"]) or 1.0
        scaled = (filled - float(metadata["mean"])) / std_value
        vector.append(round(scaled, 12))
        if metadata["has_missing"]:
            vector.append(1.0 if missing else 0.0)

    for name, metadata in transform_spec["categorical"].items():
        raw_value = feature_values.get(name)
        normalized = "__MISSING__" if raw_value in {None, ""} else str(raw_value)
        categories = list(metadata["categories"])
        for category in categories:
            vector.append(1.0 if normalized == category else 0.0)

    for name, metadata in transform_spec["boolean"].items():
        raw_value = feature_values.get(name)
        missing = raw_value is None
        vector.append(1.0 if bool(raw_value) else 0.0)
        if metadata["has_missing"]:
            vector.append(1.0 if missing else 0.0)

    return vector


def fit_logistic_regression(
    *,
    encoded_rows: list[list[float]],
    labels: list[int],
    iterations: int = 2400,
    learning_rate: float = 0.18,
    l2_lambda: float = 0.04,
) -> dict[str, Any]:
    if not encoded_rows:
        raise ValueError("Cannot fit logistic regression with no training rows.")
    feature_count = len(encoded_rows[0])
    coefficients = [0.0] * feature_count
    intercept = 0.0
    current_learning_rate = learning_rate

    for iteration in range(iterations):
        gradient = [0.0] * feature_count
        intercept_gradient = 0.0
        row_count = len(encoded_rows)
        for row, label in zip(encoded_rows, labels, strict=True):
            linear = intercept + sum(
                coefficient * value
                for coefficient, value in zip(coefficients, row, strict=True)
            )
            probability = sigmoid(linear)
            error = probability - label
            intercept_gradient += error
            for index, value in enumerate(row):
                gradient[index] += error * value

        intercept_gradient /= row_count
        for index in range(feature_count):
            gradient[index] = (gradient[index] / row_count) + (l2_lambda * coefficients[index])

        intercept -= current_learning_rate * intercept_gradient
        for index in range(feature_count):
            coefficients[index] -= current_learning_rate * gradient[index]

        if iteration > 0 and iteration % 800 == 0:
            current_learning_rate *= 0.55

    return {
        "intercept": round(intercept, 12),
        "coefficients": [round(value, 12) for value in coefficients],
        "iterations": iterations,
        "learning_rate": learning_rate,
        "l2_lambda": l2_lambda,
    }


def predict_probability_from_vector(model_artifact: dict[str, Any], vector: list[float]) -> float:
    linear = float(model_artifact["intercept"]) + sum(
        coefficient * value
        for coefficient, value in zip(model_artifact["coefficients"], vector, strict=True)
    )
    return clamp_probability(sigmoid(linear))


def predict_probability(
    model_artifact: dict[str, Any],
    *,
    feature_values: dict[str, Any],
) -> tuple[float, list[float]]:
    vector = encode_feature_values(
        feature_values,
        transform_spec=model_artifact["transform_spec"],
    )
    return predict_probability_from_vector(model_artifact, vector), vector


def explain_base_feature_contributions(
    model_artifact: dict[str, Any],
    *,
    feature_values: dict[str, Any],
) -> dict[str, float]:
    vector = encode_feature_values(
        feature_values,
        transform_spec=model_artifact["transform_spec"],
    )
    contributions: dict[str, float] = {}
    for index, value in enumerate(vector):
        base_name = model_artifact["transform_spec"]["encoded_feature_bases"][index]
        coefficient = float(model_artifact["coefficients"][index])
        contributions[base_name] = contributions.get(base_name, 0.0) + (coefficient * value)
    return {key: round(value, 12) for key, value in contributions.items()}
