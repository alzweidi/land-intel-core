"""Seed a compliant automated Savills development-land source for pilot-borough live intake."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from landintel.domain.enums import ComplianceMode, ConnectorType

revision = "20260421_000017_phase8a_savills_source"
down_revision = "20260421_000016_phase8a_ideal_sitemap_backfill"
branch_labels = None
depends_on = None

SAVILLS_SOURCE_ID = uuid.UUID("e54970a2-186a-4471-a512-8f328e675c55")
SAVILLS_SOURCE_NAME = "savills_development_land"
SAVILLS_SOURCE_REFRESH_POLICY = {
    "interval_hours": 24,
    "seed_urls": [
        "https://search.savills.com/com/en/list/commercial/property-for-sale/development-land/england/camden-borough",
        "https://search.savills.com/com/en/list/commercial/property-for-sale/development-land/england/islington-borough",
        "https://search.savills.com/com/en/list/commercial/property-for-sale/development-land/england/southwark-borough",
    ],
    "listing_link_selector": "a[href*='/property-detail/']",
    "listing_url_patterns": [r"^https://search\.savills\.com/com/en/property-detail/.+"],
    "max_listings": 150,
    "source_fit_policy": {
        "required_listing_types": ["LAND", "REDEVELOPMENT_SITE"],
        "required_listing_statuses": ["LIVE", "AUCTION"],
        "required_lpa_ids": ["camden", "islington", "southwark"],
        "required_text_contains_any": ["development land", "vacant possession", "site"],
        "excluded_text_contains_any": [
            "under offer",
            "sold",
            "let agreed",
            "investment opportunity",
            "commercial investment",
            "office building",
            "hotel",
        ],
        "required_coordinate_bbox_4326": [-0.52, 51.28, 0.33, 51.7],
        "require_point_coordinates": True,
        "require_address_text": True,
        "require_map_asset": False,
    },
    "compliance_basis": {
        "reviewed_at": "2026-04-21",
        "basis": (
            "Public first-party borough development-land index pages and public detail pages "
            "are allowed by robots.txt; the automation path remains generic/config-driven and "
            "limited to first-party Savills search pages for the pilot boroughs."
        ),
        "scope": (
            "Savills public development-land borough listing pages for Camden, Islington, "
            "and Southwark plus linked public detail pages only."
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


def _upsert_savills_source(bind) -> None:
    listing_source = _listing_source_table()
    existing = bind.execute(
        sa.select(
            listing_source.c.id,
            listing_source.c.refresh_policy_json,
        ).where(listing_source.c.name == SAVILLS_SOURCE_NAME)
    ).mappings().first()
    if existing is None:
        bind.execute(
            sa.insert(listing_source).values(
                id=SAVILLS_SOURCE_ID,
                name=SAVILLS_SOURCE_NAME,
                connector_type=ConnectorType.PUBLIC_PAGE.value,
                compliance_mode=ComplianceMode.COMPLIANT_AUTOMATED.value,
                refresh_policy_json=SAVILLS_SOURCE_REFRESH_POLICY,
                active=True,
                created_at=datetime.now(UTC),
            )
        )
        return

    refresh_policy = dict(existing["refresh_policy_json"] or {})
    refresh_policy.update(SAVILLS_SOURCE_REFRESH_POLICY)
    bind.execute(
        sa.update(listing_source)
        .where(listing_source.c.name == SAVILLS_SOURCE_NAME)
        .values(
            connector_type=ConnectorType.PUBLIC_PAGE.value,
            compliance_mode=ComplianceMode.COMPLIANT_AUTOMATED.value,
            refresh_policy_json=refresh_policy,
            active=True,
        )
    )


def upgrade() -> None:
    bind = op.get_bind()
    _upsert_savills_source(bind)


def downgrade() -> None:
    bind = op.get_bind()
    listing_source = _listing_source_table()
    bind.execute(sa.delete(listing_source).where(listing_source.c.name == SAVILLS_SOURCE_NAME))
