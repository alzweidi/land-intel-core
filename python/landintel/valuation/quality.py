from __future__ import annotations

from dataclasses import dataclass

from landintel.domain.enums import ValuationQuality

QUALITY_ORDER = {
    ValuationQuality.LOW: 0,
    ValuationQuality.MEDIUM: 1,
    ValuationQuality.HIGH: 2,
}


@dataclass(slots=True)
class ValuationQualityResult:
    valuation_quality: ValuationQuality
    manual_review_required: bool
    reasons: list[str]


def derive_valuation_quality(
    *,
    asking_price_present: bool,
    sales_comp_count: int,
    land_comp_count: int,
    policy_inputs_known: bool,
    scenario_area_stable: bool,
    divergence_material: bool,
) -> ValuationQualityResult:
    reasons: list[str] = []
    quality = ValuationQuality.HIGH

    if not asking_price_present:
        quality = _downgrade(quality, ValuationQuality.LOW)
        reasons.append("Acquisition basis is missing.")
    if sales_comp_count < 3:
        quality = _downgrade(quality, ValuationQuality.LOW)
        reasons.append("Official sales comp coverage is thin.")
    elif sales_comp_count < 5:
        quality = _downgrade(quality, ValuationQuality.MEDIUM)
        reasons.append("Official sales comp coverage is adequate but limited.")

    if land_comp_count < 1:
        quality = _downgrade(quality, ValuationQuality.MEDIUM)
        reasons.append("Permissioned land sense-check coverage is missing.")
    elif land_comp_count < 2:
        quality = _downgrade(quality, ValuationQuality.MEDIUM)
        reasons.append("Permissioned land sense-check coverage is limited.")

    if not policy_inputs_known:
        quality = _downgrade(quality, ValuationQuality.LOW)
        reasons.append("CIL or affordable-housing burden assumptions are incomplete.")
    if not scenario_area_stable:
        quality = _downgrade(quality, ValuationQuality.MEDIUM)
        reasons.append("Scenario mix or developable area assumptions remain unstable.")
    if divergence_material:
        quality = _downgrade(quality, ValuationQuality.LOW)
        reasons.append("Residual and sense-check methods diverge materially.")

    manual_review_required = quality == ValuationQuality.LOW or divergence_material
    return ValuationQualityResult(
        valuation_quality=quality,
        manual_review_required=manual_review_required,
        reasons=reasons,
    )


def evaluate_divergence(
    *,
    primary_mid: float | None,
    secondary_mid: float | None,
    threshold_pct: float,
    threshold_abs_gbp: float,
) -> bool:
    if primary_mid is None or secondary_mid is None:
        return False
    absolute_gap = abs(primary_mid - secondary_mid)
    denominator = max(abs(primary_mid), abs(secondary_mid), 1.0)
    pct_gap = absolute_gap / denominator
    return pct_gap >= threshold_pct or absolute_gap >= threshold_abs_gbp


def widen_range_for_divergence(
    *,
    primary_low: float | None,
    primary_mid: float | None,
    primary_high: float | None,
    secondary_low: float | None,
    secondary_mid: float | None,
    secondary_high: float | None,
) -> tuple[float | None, float | None, float | None]:
    mids = [value for value in [primary_mid, secondary_mid] if value is not None]
    lows = [value for value in [primary_low, secondary_low] if value is not None]
    highs = [value for value in [primary_high, secondary_high] if value is not None]
    if not mids:
        return primary_low, primary_mid, primary_high
    return (
        None if not lows else round(min(lows), 2),
        round(sum(mids) / len(mids), 2),
        None if not highs else round(max(highs), 2),
    )


def _downgrade(current: ValuationQuality, candidate: ValuationQuality) -> ValuationQuality:
    if QUALITY_ORDER[candidate] < QUALITY_ORDER[current]:
        return candidate
    return current
