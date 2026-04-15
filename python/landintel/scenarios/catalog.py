from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from landintel.domain.models import ScenarioTemplate

SCENARIO_TEMPLATE_DEFINITIONS: Sequence[dict[str, object]] = (
    {
        "key": "resi_1_4_full",
        "version": "v1",
        "enabled": True,
        "config_json": {
            "description": "small residential scheme",
            "units_range": {"min": 1, "max": 4},
            "default_route": "FULL",
            "default_height_band": "LOW_RISE",
            "default_net_developable_area_pct": 0.68,
            "default_housing_mix": {"1b": 0.25, "2b": 0.5, "3b": 0.25},
            "default_parking_assumption": (
                "Small-site car-lite assumption subject to borough rulepack and site access."
            ),
            "default_affordable_housing_assumption": (
                "Below major threshold unless borough rulepack states a lower trigger."
            ),
            "default_access_assumption": (
                "Existing street frontage or analyst-confirmed legal access is required."
            ),
            "default_proposal_form": "INFILL",
            "allowed_proposal_forms": [
                "INFILL",
                "REDEVELOPMENT",
                "BACKLAND",
                "BROWNFIELD_REUSE",
            ],
            "site_area_sqm_range": {"min": 140, "max": 1600},
            "target_sqm_per_home": 240,
        },
    },
    {
        "key": "resi_5_9_full",
        "version": "v1",
        "enabled": True,
        "config_json": {
            "description": "small-medium residential scheme",
            "units_range": {"min": 5, "max": 9},
            "default_route": "FULL",
            "default_height_band": "MID_RISE",
            "default_net_developable_area_pct": 0.72,
            "default_housing_mix": {"1b": 0.2, "2b": 0.45, "3b": 0.35},
            "default_parking_assumption": (
                "Car-lite assumption with parking stress and frontage checks required."
            ),
            "default_affordable_housing_assumption": (
                "Usually below major threshold but borough-specific small-site policy "
                "still applies."
            ),
            "default_access_assumption": (
                "Two-way frontage/access must be defensible or analyst-reviewed."
            ),
            "default_proposal_form": "REDEVELOPMENT",
            "allowed_proposal_forms": [
                "INFILL",
                "REDEVELOPMENT",
                "BACKLAND",
                "BROWNFIELD_REUSE",
            ],
            "site_area_sqm_range": {"min": 700, "max": 3200},
            "target_sqm_per_home": 180,
        },
    },
    {
        "key": "resi_10_49_outline",
        "version": "v1",
        "enabled": True,
        "config_json": {
            "description": "medium residential scheme",
            "units_range": {"min": 10, "max": 49},
            "default_route": "OUTLINE",
            "default_height_band": "MID_BLOCK",
            "default_net_developable_area_pct": 0.78,
            "default_housing_mix": {"1b": 0.15, "2b": 0.45, "3b": 0.3, "4b": 0.1},
            "default_parking_assumption": (
                "Likely car-lite or disabled-bays-only, subject to PTAL and borough parking rules."
            ),
            "default_affordable_housing_assumption": (
                "Major residential threshold assumed; borough affordable-housing policy applies."
            ),
            "default_access_assumption": (
                "Multiple frontage and servicing assumptions require analyst confirmation."
            ),
            "default_proposal_form": "BROWNFIELD_REUSE",
            "allowed_proposal_forms": [
                "REDEVELOPMENT",
                "BROWNFIELD_REUSE",
            ],
            "site_area_sqm_range": {"min": 1800, "max": 14000},
            "target_sqm_per_home": 115,
        },
    },
)


def template_definition_map() -> dict[str, dict[str, object]]:
    return {
        str(template["key"]): dict(template)
        for template in SCENARIO_TEMPLATE_DEFINITIONS
    }


def scenario_template_id(*, key: str, version: str) -> uuid.UUID:
    return uuid.uuid5(
        uuid.UUID("8c4d3814-5384-43d8-9a59-7f49a06ea472"),
        f"scenario-template:{key}:{version}",
    )


def ensure_scenario_templates_seeded(session: Session) -> list[ScenarioTemplate]:
    existing = session.execute(select(ScenarioTemplate)).scalars().all()
    existing_by_key = {(row.key, row.version): row for row in existing} if existing else {}

    for template in SCENARIO_TEMPLATE_DEFINITIONS:
        key = str(template["key"])
        version = str(template["version"])
        row = existing_by_key.get((key, version))
        if row is None:
            row = ScenarioTemplate(
                id=scenario_template_id(key=key, version=version),
                key=key,
                version=version,
            )
            session.add(row)
            existing_by_key[(key, version)] = row

        row.enabled = bool(template.get("enabled", True))
        row.config_json = dict(template.get("config_json") or {})

    session.flush()
    return list(existing_by_key.values())


def get_enabled_scenario_templates(
    session: Session,
    *,
    template_keys: Sequence[str] | None = None,
) -> list[ScenarioTemplate]:
    ensure_scenario_templates_seeded(session)
    stmt = select(ScenarioTemplate).where(ScenarioTemplate.enabled.is_(True))
    if template_keys:
        stmt = stmt.where(ScenarioTemplate.key.in_(list(template_keys)))
    return session.execute(stmt.order_by(ScenarioTemplate.key.asc())).scalars().all()
