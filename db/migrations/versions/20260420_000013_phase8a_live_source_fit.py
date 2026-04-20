"""Phase 8A live-source fit remediation for truthful real-data launch."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260420_000013_phase8a_live_source_fit"
down_revision = "20260420_000012_phase8a_real_source_launch"
branch_labels = None
depends_on = None

REAL_SOURCE_NAME = "cabinet_office_surplus_property"
REAL_SOURCE_REFRESH_POLICY = {
    "interval_hours": 24,
    "feed_url": "https://data.insite.cabinetoffice.gov.uk/insite/Register.xlsx",
    "feed_format": "xlsx",
    "sheet_name": "Register",
    "row_transform": "cabinet_office_surplus_property_v1",
    "status_of_sale_values": ["On the Market"],
    "local_authority_contains_any": [
        "LONDON BOROUGH",
        "ROYAL BOROUGH",
        "CITY OF LONDON",
    ],
    "allowed_land_usage_contains_any": [
        "Surplus Land",
        "Development land",
    ],
    "allowed_listing_types": [
        "LAND",
    ],
    "max_surplus_floor_area_sqm": 0,
    "require_positive_land_area": True,
    "max_listings": 200,
}


def _listing_source_table() -> sa.Table:
    return sa.table(
        "listing_source",
        sa.column("id", sa.Uuid()),
        sa.column("name", sa.String(length=255)),
        sa.column("active", sa.Boolean()),
        sa.column("refresh_policy_json", sa.JSON()),
    )


def _deactivate_example_public_page(bind) -> None:
    listing_source = _listing_source_table()
    bind.execute(
        sa.update(listing_source)
        .where(listing_source.c.name == "example_public_page")
        .values(active=False)
    )


def _tighten_real_source_policy(bind) -> None:
    listing_source = _listing_source_table()
    existing = bind.execute(
        sa.select(
            listing_source.c.id,
            listing_source.c.refresh_policy_json,
        ).where(listing_source.c.name == REAL_SOURCE_NAME)
    ).mappings().first()
    if existing is None:
        return

    refresh_policy = dict(existing["refresh_policy_json"] or {})
    refresh_policy.update(REAL_SOURCE_REFRESH_POLICY)
    bind.execute(
        sa.update(listing_source)
        .where(listing_source.c.id == existing["id"])
        .values(refresh_policy_json=refresh_policy, active=True)
    )


def upgrade() -> None:
    bind = op.get_bind()
    _deactivate_example_public_page(bind)
    _tighten_real_source_policy(bind)


def downgrade() -> None:
    bind = op.get_bind()
    listing_source = _listing_source_table()
    bind.execute(
        sa.update(listing_source)
        .where(listing_source.c.name == "example_public_page")
        .values(active=True)
    )
