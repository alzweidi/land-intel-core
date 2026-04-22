"""Seed a compliant automated Bidwells land-development source for live London land intake."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from landintel.domain.enums import ComplianceMode, ConnectorType

revision = "20260421_000015_phase8a_bidwells_source"
down_revision = "20260421_000014_phase8a_ideal_land_source"
branch_labels = None
depends_on = None

BIDWELLS_SOURCE_ID = uuid.UUID("3024f77d-2205-45f8-b44f-48d13d4f5503")
BIDWELLS_SOURCE_NAME = "bidwells_land_development"
BIDWELLS_SOURCE_REFRESH_POLICY = {
    "interval_hours": 24,
    "seed_urls": ["https://www.bidwells.co.uk/land-development/"],
    "sitemap_urls": ["https://www.bidwells.co.uk/land-development-sitemap.xml"],
    "listing_link_selector": "a[href^='/properties/']",
    "listing_url_patterns": [r"^https://www\.bidwells\.co\.uk/properties/.+"],
    "max_listings": 250,
    "source_fit_policy": {
        "required_listing_types": ["LAND", "REDEVELOPMENT_SITE"],
        "required_text_contains_any": ["development", "planning permission", "undeveloped land"],
        "excluded_text_contains_any": [
            "under offer",
            "sold",
            "consent",
            "consented",
            "approved plans",
            "approved planning",
            "outline planning permission",
            "full planning permission",
            "planning permission for",
            "farm",
            "woodland",
            "forest",
            "golf",
            "hotel",
            "clubhouse",
            "equestrian",
            "holiday",
            "barn",
            "cottage",
        ],
        "required_coordinate_bbox_4326": [-0.52, 51.28, 0.33, 51.7],
        "require_point_coordinates": True,
        "require_brochure_asset": True,
    },
    "compliance_basis": {
        "reviewed_at": "2026-04-21",
        "basis": (
            "Public land-development sitemap and public detail pages are allowed by "
            "robots.txt; the automation path remains generic/config-driven and "
            "limited to first-party Bidwells pages and linked brochure assets."
        ),
        "scope": (
            "Bidwells land-development index, sitemap, public detail pages, and "
            "brochure assets only."
        ),
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


def _upsert_bidwells_source(bind) -> None:
    listing_source = _listing_source_table()
    existing = bind.execute(
        sa.select(
            listing_source.c.id,
            listing_source.c.refresh_policy_json,
        ).where(listing_source.c.name == BIDWELLS_SOURCE_NAME)
    ).mappings().first()
    if existing is None:
        bind.execute(
            sa.insert(listing_source).values(
                id=BIDWELLS_SOURCE_ID,
                name=BIDWELLS_SOURCE_NAME,
                connector_type=ConnectorType.PUBLIC_PAGE.value,
                compliance_mode=ComplianceMode.COMPLIANT_AUTOMATED.value,
                refresh_policy_json=BIDWELLS_SOURCE_REFRESH_POLICY,
                active=True,
                created_at=datetime.now(UTC),
            )
        )
        return

    refresh_policy = dict(existing["refresh_policy_json"] or {})
    refresh_policy.update(BIDWELLS_SOURCE_REFRESH_POLICY)
    bind.execute(
        sa.update(listing_source)
        .where(listing_source.c.name == BIDWELLS_SOURCE_NAME)
        .values(
            connector_type=ConnectorType.PUBLIC_PAGE.value,
            compliance_mode=ComplianceMode.COMPLIANT_AUTOMATED.value,
            refresh_policy_json=refresh_policy,
            active=True,
        )
    )


def upgrade() -> None:
    bind = op.get_bind()
    _upsert_bidwells_source(bind)


def downgrade() -> None:
    bind = op.get_bind()
    listing_source = _listing_source_table()
    bind.execute(sa.delete(listing_source).where(listing_source.c.name == BIDWELLS_SOURCE_NAME))
