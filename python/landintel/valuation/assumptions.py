from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from landintel.domain.models import ValuationAssumptionSet

DEFAULT_VALUATION_ASSUMPTION_SET_ID = uuid.UUID("7e1f7038-e211-5aa1-88d3-6056fbc4581e")
DEFAULT_VALUATION_ASSUMPTION_VERSION = "phase7a_default_v1"


def default_assumption_payload() -> dict[str, object]:
    return {
        "cost_json": {
            "build_cost_library_version": "fixture_bcis_2026_v1",
            "build_cost_per_gia_sqm": {
                "resi_1_4_full": 2425.0,
                "resi_5_9_full": 2375.0,
                "resi_10_49_outline": 2280.0,
            },
            "standard_unit_sizes_nsa_sqm": {
                "studio": 42.0,
                "1_bed": 52.0,
                "2_bed": 72.0,
                "3_bed": 94.0,
            },
            "default_mix_by_template": {
                "resi_1_4_full": {"2_bed": 0.5, "3_bed": 0.5},
                "resi_5_9_full": {"1_bed": 0.2, "2_bed": 0.55, "3_bed": 0.25},
                "resi_10_49_outline": {"1_bed": 0.25, "2_bed": 0.5, "3_bed": 0.25},
            },
            "gia_multiplier": 1.15,
            "externals_pct": 0.08,
            "professional_fees_pct": 0.1,
            "planning_surveys_legal_pct": 0.03,
            "contingency_pct": 0.05,
            "finance_pct": 0.06,
            "developer_margin_pct": 0.18,
        },
        "policy_burden_json": {
            "mayoral_cil_per_sqm": 60.0,
            "borough_cil_per_sqm": {
                "camden": 35.0,
                "southwark": 25.0,
                "default": 20.0,
            },
            "affordable_housing_trigger_units": {
                "camden": 10,
                "southwark": 10,
                "default": 10,
            },
            "affordable_housing_burden_pct_of_gdv": {
                "camden": 0.12,
                "southwark": 0.1,
                "default": 0.1,
            },
        },
        "discount_json": {
            "rebasing_index_key": "UKHPI",
            "price_per_sqm_low_pct": 0.92,
            "price_per_sqm_high_pct": 1.08,
            "market_comp_max_age_months": 36,
            "sense_check_material_divergence_pct": 0.2,
            "sense_check_material_divergence_gbp": 250000.0,
        },
    }


def ensure_default_assumption_set(session: Session) -> ValuationAssumptionSet:
    existing = session.execute(
        select(ValuationAssumptionSet).where(
            ValuationAssumptionSet.version == DEFAULT_VALUATION_ASSUMPTION_VERSION
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    payload = default_assumption_payload()
    row = ValuationAssumptionSet(
        id=DEFAULT_VALUATION_ASSUMPTION_SET_ID,
        version=DEFAULT_VALUATION_ASSUMPTION_VERSION,
        cost_json=dict(payload["cost_json"]),
        policy_burden_json=dict(payload["policy_burden_json"]),
        discount_json=dict(payload["discount_json"]),
        effective_from=date(2026, 4, 15),
    )
    session.add(row)
    session.flush()
    return row


def resolve_active_assumption_set(
    session: Session,
    *,
    as_of_date: date,
    version: str | None = None,
) -> ValuationAssumptionSet:
    if version:
        row = session.execute(
            select(ValuationAssumptionSet).where(ValuationAssumptionSet.version == version)
        ).scalar_one_or_none()
        if row is None:
            raise ValueError(f"Valuation assumption set '{version}' was not found.")
        return row

    default_row = ensure_default_assumption_set(session)
    row = session.execute(
        select(ValuationAssumptionSet)
        .where(ValuationAssumptionSet.effective_from <= as_of_date)
        .order_by(
            ValuationAssumptionSet.effective_from.desc(),
            ValuationAssumptionSet.created_at.desc(),
        )
        .limit(1)
    ).scalar_one_or_none()
    return row or default_row
