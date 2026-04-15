from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from landintel.domain.enums import EligibilityStatus, OpportunityBand, ValuationQuality

VALUATION_ORDER = {
    None: -1,
    ValuationQuality.LOW: 0,
    ValuationQuality.MEDIUM: 1,
    ValuationQuality.HIGH: 2,
}

BAND_ORDER = {
    OpportunityBand.BAND_A: 0,
    OpportunityBand.BAND_B: 1,
    OpportunityBand.BAND_C: 2,
    OpportunityBand.BAND_D: 3,
    OpportunityBand.HOLD: 4,
}

HOLD_REASON_MAP = {
    "NO_ACTIVE_HIDDEN_RELEASE": "No active hidden release is available for this scope.",
    "STORAGE_UNAVAILABLE": "Hidden scoring artifacts are unavailable in this environment.",
    "BASELINE_PACK_NOT_SIGNED_OFF": (
        "The borough baseline pack is not signed off for hidden ranking."
    ),
    "ABSTAIN": "A hard abstain condition blocks hidden ranking for this assessment.",
}


@dataclass(slots=True)
class OpportunityBandResult:
    probability_band: OpportunityBand
    hold_reason: str | None


def derive_opportunity_band(
    *,
    eligibility_status: EligibilityStatus | None,
    approval_probability_raw: float | None,
    estimate_quality: str | None,
    manual_review_required: bool,
    score_execution_status: str | None,
) -> OpportunityBandResult:
    if eligibility_status in {
        EligibilityStatus.ABSTAIN,
        EligibilityStatus.FAIL,
        EligibilityStatus.OUT_OF_SCOPE,
    }:
        return OpportunityBandResult(
            probability_band=OpportunityBand.HOLD,
            hold_reason=f"Eligibility is {eligibility_status.value}.",
        )
    if approval_probability_raw is None:
        hold_reason = HOLD_REASON_MAP.get(
            score_execution_status or "",
            "No active hidden release or raw probability is available.",
        )
        return OpportunityBandResult(
            probability_band=OpportunityBand.HOLD,
            hold_reason=hold_reason,
        )

    if (
        approval_probability_raw >= 0.70
        and estimate_quality in {"HIGH", "MEDIUM"}
        and not manual_review_required
    ):
        return OpportunityBandResult(probability_band=OpportunityBand.BAND_A, hold_reason=None)
    if 0.55 <= approval_probability_raw < 0.70 or manual_review_required:
        return OpportunityBandResult(probability_band=OpportunityBand.BAND_B, hold_reason=None)
    if 0.40 <= approval_probability_raw < 0.55:
        return OpportunityBandResult(probability_band=OpportunityBand.BAND_C, hold_reason=None)
    return OpportunityBandResult(probability_band=OpportunityBand.BAND_D, hold_reason=None)


def ranking_sort_key(
    *,
    probability_band: OpportunityBand,
    expected_uplift_mid: float | None,
    valuation_quality: ValuationQuality | None,
    auction_date: date | None,
    today: date,
    asking_price_present: bool,
    same_borough_support_count: int,
    display_name: str,
) -> tuple[object, ...]:
    urgency_days = (auction_date - today).days if auction_date is not None else 10_000
    return (
        BAND_ORDER[probability_band],
        -(expected_uplift_mid or 0.0),
        -VALUATION_ORDER[valuation_quality],
        urgency_days,
        0 if asking_price_present else 1,
        -same_borough_support_count,
        display_name.lower(),
    )
