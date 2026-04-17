from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from landintel.domain.enums import PriceBasisType
from landintel.domain.models import SiteCandidate, SiteScenario, ValuationAssumptionSet


@dataclass(slots=True)
class DerivedAreaSummary:
    unit_mix_counts: dict[str, int]
    nsa_sqm: float
    gia_sqm: float


@dataclass(slots=True)
class ResidualValuationSummary:
    post_permission_value_low: float | None
    post_permission_value_mid: float | None
    post_permission_value_high: float | None
    uplift_low: float | None
    uplift_mid: float | None
    uplift_high: float | None
    basis_json: dict[str, Any]
    result_json: dict[str, Any]


def canonical_payload_hash(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def derive_area_summary(
    *,
    scenario: SiteScenario,
    assumption_set: ValuationAssumptionSet,
) -> DerivedAreaSummary:
    cost_json = dict(assumption_set.cost_json or {})
    size_library = dict(cost_json.get("standard_unit_sizes_nsa_sqm") or {})
    mix_defaults = dict(cost_json.get("default_mix_by_template") or {}).get(
        scenario.template_key,
        {},
    )
    mix_payload = dict(scenario.housing_mix_assumed_json or {}) or mix_defaults
    normalized_mix = _normalize_mix_payload(mix_payload, fallback=mix_defaults)
    unit_mix_counts = _mix_to_counts(
        units_assumed=scenario.units_assumed,
        mix_payload=normalized_mix,
    )
    nsa_sqm = 0.0
    for unit_type, count in unit_mix_counts.items():
        nsa_sqm += float(size_library.get(unit_type, 72.0)) * count
    gia_multiplier = float(cost_json.get("gia_multiplier") or 1.15)
    return DerivedAreaSummary(
        unit_mix_counts=unit_mix_counts,
        nsa_sqm=round(nsa_sqm, 2),
        gia_sqm=round(nsa_sqm * gia_multiplier, 2),
    )


def build_basis_json(
    site: SiteCandidate,
    *,
    current_price_gbp: int | None = None,
    current_price_basis_type: PriceBasisType | None = None,
) -> dict[str, Any]:
    resolved_price = site.current_price_gbp if current_price_gbp is None else current_price_gbp
    resolved_basis_type = (
        site.current_price_basis_type
        if current_price_basis_type is None
        else current_price_basis_type
    )
    if resolved_price is None or resolved_basis_type == PriceBasisType.UNKNOWN:
        return {
            "basis_available": False,
            "basis_type": None,
            "basis_price_gbp": None,
            "note": "Acquisition basis is missing; uplift fields remain null.",
        }
    return {
        "basis_available": True,
        "basis_type": resolved_basis_type.value,
        "basis_price_gbp": int(resolved_price),
        "note": "Current listing basis is used as the acquisition reference.",
    }


def compute_residual_valuation(
    *,
    site: SiteCandidate,
    scenario: SiteScenario,
    assumption_set: ValuationAssumptionSet,
    price_per_sqm_low: float | None,
    price_per_sqm_mid: float | None,
    price_per_sqm_high: float | None,
    current_price_gbp: int | None = None,
    current_price_basis_type: PriceBasisType | None = None,
    borough_id: str | None = None,
) -> ResidualValuationSummary:
    area_summary = derive_area_summary(scenario=scenario, assumption_set=assumption_set)
    basis_json = build_basis_json(
        site,
        current_price_gbp=current_price_gbp,
        current_price_basis_type=current_price_basis_type,
    )
    resolved_borough_id = site.borough_id if borough_id is None else borough_id
    if (
        price_per_sqm_low is None
        or price_per_sqm_mid is None
        or price_per_sqm_high is None
        or area_summary.nsa_sqm <= 0
        or area_summary.gia_sqm <= 0
    ):
        return ResidualValuationSummary(
            post_permission_value_low=None,
            post_permission_value_mid=None,
            post_permission_value_high=None,
            uplift_low=None,
            uplift_mid=None,
            uplift_high=None,
            basis_json=basis_json,
            result_json={
                "status": "INSUFFICIENT_MARKET_DATA",
                "derived_area": {
                    "nsa_sqm": area_summary.nsa_sqm,
                    "gia_sqm": area_summary.gia_sqm,
                    "unit_mix_counts": area_summary.unit_mix_counts,
                },
            },
        )

    cost_json = dict(assumption_set.cost_json or {})
    burden_json = dict(assumption_set.policy_burden_json or {})
    build_cost_per_gia_sqm = float(
        dict(cost_json.get("build_cost_per_gia_sqm") or {}).get(
            scenario.template_key,
            2350.0,
        )
    )
    build_cost = area_summary.gia_sqm * build_cost_per_gia_sqm
    externals = build_cost * float(cost_json.get("externals_pct") or 0.08)
    fees = build_cost * float(cost_json.get("professional_fees_pct") or 0.1)
    planning_allowance = build_cost * float(cost_json.get("planning_surveys_legal_pct") or 0.03)
    contingency = build_cost * float(cost_json.get("contingency_pct") or 0.05)

    mayoral_cil = area_summary.gia_sqm * float(burden_json.get("mayoral_cil_per_sqm") or 0.0)
    borough_cil_map = dict(burden_json.get("borough_cil_per_sqm") or {})
    borough_cil = area_summary.gia_sqm * float(
        borough_cil_map.get(resolved_borough_id or "", borough_cil_map.get("default", 0.0))
    )

    affordable_threshold_map = dict(burden_json.get("affordable_housing_trigger_units") or {})
    affordable_threshold = int(
        affordable_threshold_map.get(
            resolved_borough_id or "",
            affordable_threshold_map.get("default", 10),
        )
    )
    affordable_pct_map = dict(burden_json.get("affordable_housing_burden_pct_of_gdv") or {})
    affordable_pct = float(
        affordable_pct_map.get(
            resolved_borough_id or "",
            affordable_pct_map.get("default", 0.0),
        )
    )

    def _land_value(price_per_sqm: float) -> tuple[float, dict[str, float]]:
        gdv = area_summary.nsa_sqm * price_per_sqm
        affordable_burden = (
            gdv * affordable_pct
            if scenario.units_assumed >= affordable_threshold
            else 0.0
        )
        subtotal = (
            build_cost
            + externals
            + fees
            + planning_allowance
            + contingency
            + mayoral_cil
            + borough_cil
            + affordable_burden
        )
        finance = subtotal * float(cost_json.get("finance_pct") or 0.06)
        developer_margin = gdv * float(cost_json.get("developer_margin_pct") or 0.18)
        total_costs = subtotal + finance + developer_margin
        return max(gdv - total_costs, 0.0), {
            "gdv": round(gdv, 2),
            "build_cost": round(build_cost, 2),
            "externals": round(externals, 2),
            "professional_fees": round(fees, 2),
            "planning_surveys_legal": round(planning_allowance, 2),
            "contingency": round(contingency, 2),
            "finance": round(finance, 2),
            "developer_margin": round(developer_margin, 2),
            "mayoral_cil": round(mayoral_cil, 2),
            "borough_cil": round(borough_cil, 2),
            "affordable_housing_burden": round(affordable_burden, 2),
            "total_costs": round(total_costs, 2),
        }

    low_value, low_breakdown = _land_value(price_per_sqm_low)
    mid_value, mid_breakdown = _land_value(price_per_sqm_mid)
    high_value, high_breakdown = _land_value(price_per_sqm_high)

    basis_price = basis_json["basis_price_gbp"]
    uplift_low = None if basis_price is None else round(low_value - float(basis_price), 2)
    uplift_mid = None if basis_price is None else round(mid_value - float(basis_price), 2)
    uplift_high = None if basis_price is None else round(high_value - float(basis_price), 2)

    return ResidualValuationSummary(
        post_permission_value_low=round(low_value, 2),
        post_permission_value_mid=round(mid_value, 2),
        post_permission_value_high=round(high_value, 2),
        uplift_low=uplift_low,
        uplift_mid=uplift_mid,
        uplift_high=uplift_high,
        basis_json=basis_json,
        result_json={
            "status": "READY",
            "derived_area": {
                "nsa_sqm": area_summary.nsa_sqm,
                "gia_sqm": area_summary.gia_sqm,
                "unit_mix_counts": area_summary.unit_mix_counts,
            },
            "input_price_per_sqm": {
                "low": round(price_per_sqm_low, 2),
                "mid": round(price_per_sqm_mid, 2),
                "high": round(price_per_sqm_high, 2),
            },
            "low_breakdown": low_breakdown,
            "mid_breakdown": mid_breakdown,
            "high_breakdown": high_breakdown,
            "assumption_version": assumption_set.version,
        },
    )


def _normalize_mix_payload(
    mix_payload: dict[str, Any],
    *,
    fallback: dict[str, Any],
) -> dict[str, float]:
    raw = mix_payload or fallback or {"2_bed": 1.0}
    normalized: dict[str, float] = {}
    for key, value in raw.items():
        normalized_key = _normalize_unit_type(str(key))
        normalized[normalized_key] = float(value)
    total = sum(normalized.values())
    if total <= 0:
        return {"2_bed": 1.0}
    return {key: value / total for key, value in normalized.items()}


def _normalize_unit_type(value: str) -> str:
    cleaned = value.strip().lower().replace("-", "_")
    aliases = {
        "1b": "1_bed",
        "2b": "2_bed",
        "3b": "3_bed",
        "4b": "4_bed",
        "1bed": "1_bed",
        "2bed": "2_bed",
        "3bed": "3_bed",
        "4bed": "4_bed",
    }
    return aliases.get(cleaned, cleaned)


def _mix_to_counts(*, units_assumed: int, mix_payload: dict[str, float]) -> dict[str, int]:
    weighted = sorted(
        (
            {
                "unit_type": unit_type,
                "raw_count": float(weight) * units_assumed,
            }
            for unit_type, weight in mix_payload.items()
        ),
        key=lambda item: item["unit_type"],
    )
    counts = {str(item["unit_type"]): int(float(item["raw_count"])) for item in weighted}
    allocated = sum(counts.values())
    remainders = sorted(
        weighted,
        key=lambda item: (float(item["raw_count"]) - int(float(item["raw_count"]))),
        reverse=True,
    )
    for item in remainders:
        if allocated >= units_assumed:
            break
        counts[str(item["unit_type"])] += 1
        allocated += 1
    if allocated == 0:
        counts["2_bed"] = units_assumed
    return counts
