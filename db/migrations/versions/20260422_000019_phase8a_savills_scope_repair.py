"""Repair the Savills pilot-borough scope policy on existing databases."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260422_000019_phase8a_savills_scope_repair"
down_revision = "20260421_000018_phase8a_savills_fit_backfill"
branch_labels = None
depends_on = None

SAVILLS_SOURCE_NAME = "savills_development_land"
SAVILLS_REQUIRED_STATUSES = ["LIVE", "AUCTION"]
SAVILLS_REQUIRED_LPA_IDS = ["camden", "islington", "southwark"]
SAVILLS_REQUIRE_MAP_ASSET = False


def _listing_source_table() -> sa.Table:
    return sa.table(
        "listing_source",
        sa.column("name", sa.String(length=255)),
        sa.column("refresh_policy_json", sa.JSON()),
    )


def _repair_savills_scope(bind) -> None:
    listing_source = _listing_source_table()
    existing = bind.execute(
        sa.select(listing_source.c.refresh_policy_json).where(
            listing_source.c.name == SAVILLS_SOURCE_NAME
        )
    ).scalar_one_or_none()
    if existing is None:
        return

    refresh_policy = dict(existing or {})
    source_fit = dict(refresh_policy.get("source_fit_policy") or {})
    source_fit["required_listing_statuses"] = SAVILLS_REQUIRED_STATUSES
    source_fit["required_lpa_ids"] = SAVILLS_REQUIRED_LPA_IDS
    source_fit["require_map_asset"] = SAVILLS_REQUIRE_MAP_ASSET
    refresh_policy["source_fit_policy"] = source_fit
    bind.execute(
        sa.update(listing_source)
        .where(listing_source.c.name == SAVILLS_SOURCE_NAME)
        .values(refresh_policy_json=refresh_policy)
    )


def upgrade() -> None:
    bind = op.get_bind()
    _repair_savills_scope(bind)


def downgrade() -> None:
    bind = op.get_bind()
    _repair_savills_scope(bind)
