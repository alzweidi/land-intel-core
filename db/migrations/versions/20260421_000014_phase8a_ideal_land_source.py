"""Seed the first live parcel-grade public-page source for the acquisition target."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from landintel.domain.enums import ComplianceMode, ConnectorType

revision = "20260421_000014_phase8a_ideal_land_source"
down_revision = "20260420_000013_phase8a_live_source_fit"
branch_labels = None
depends_on = None

IDEAL_SOURCE_ID = uuid.UUID("8f9a52fe-328f-49a2-a0d0-0ac3194690e6")
IDEAL_SOURCE_NAME = "ideal_land_current_sites"
IDEAL_SOURCE_REFRESH_POLICY = {
    "interval_hours": 24,
    "seed_urls": ["https://idealland.co.uk/properties"],
    "sitemap_urls": ["https://idealland.co.uk/sitemap.xml"],
    "listing_link_selector": "a[href^='/properties/']",
    "listing_url_patterns": [r"^https://idealland\.co\.uk/properties/.+"],
    "page_extract_mode": "ideal_land_v1",
    "max_listings": 200,
    "source_fit_policy": {
        "required_statuses": ["Available"],
        "allowed_property_types": ["Backland", "Development Site"],
        "required_planning_statuses": ["Subject to Planning"],
        "required_listing_types": ["LAND", "REDEVELOPMENT_SITE"],
        "require_address_text": True,
        "excluded_text_contains_any": [
            "acquired",
            "full planning",
            "planning permission",
            "pp has been granted",
            "pp for",
            "former school",
            "office",
            "mixed use",
            "hmo",
        ],
    },
    "compliance_basis": {
        "reviewed_at": "2026-04-21",
        "basis": (
            "Public detail pages are listed in the site's sitemap and allowed by "
            "robots.txt; the automation path remains generic/config-driven rather "
            "than a bespoke portal scraper."
        ),
        "scope": "Public property index and public property detail pages only.",
    },
}


def _listing_source_table() -> sa.Table:
    return sa.table(
        "listing_source",
        sa.column("id", sa.Uuid()),
        sa.column("name", sa.String(length=255)),
        sa.column("connector_type", sa.Enum(ConnectorType, name="connector_type")),
        sa.column("compliance_mode", sa.Enum(ComplianceMode, name="compliance_mode")),
        sa.column("refresh_policy_json", sa.JSON()),
        sa.column("active", sa.Boolean()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )


def _upsert_ideal_land_source(bind) -> None:
    listing_source = _listing_source_table()
    existing = bind.execute(
        sa.select(
            listing_source.c.id,
            listing_source.c.refresh_policy_json,
        ).where(listing_source.c.name == IDEAL_SOURCE_NAME)
    ).mappings().first()
    if existing is None:
        bind.execute(
            sa.insert(listing_source).values(
                id=IDEAL_SOURCE_ID,
                name=IDEAL_SOURCE_NAME,
                connector_type=ConnectorType.PUBLIC_PAGE.value,
                compliance_mode=ComplianceMode.COMPLIANT_AUTOMATED.value,
                refresh_policy_json=IDEAL_SOURCE_REFRESH_POLICY,
                active=True,
                created_at=datetime.now(UTC),
            )
        )
        return

    refresh_policy = dict(existing["refresh_policy_json"] or {})
    refresh_policy.update(IDEAL_SOURCE_REFRESH_POLICY)
    bind.execute(
        sa.update(listing_source)
        .where(listing_source.c.name == IDEAL_SOURCE_NAME)
        .values(
            connector_type=ConnectorType.PUBLIC_PAGE.value,
            compliance_mode=ComplianceMode.COMPLIANT_AUTOMATED.value,
            refresh_policy_json=refresh_policy,
            active=True,
        )
    )


def upgrade() -> None:
    bind = op.get_bind()
    _upsert_ideal_land_source(bind)


def downgrade() -> None:
    bind = op.get_bind()
    listing_source = _listing_source_table()
    bind.execute(sa.delete(listing_source).where(listing_source.c.name == IDEAL_SOURCE_NAME))
