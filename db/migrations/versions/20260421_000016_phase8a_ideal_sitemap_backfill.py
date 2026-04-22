"""Backfill sitemap discovery config for the live Ideal Land source on existing databases."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260421_000016_phase8a_ideal_sitemap_backfill"
down_revision = "20260421_000015_phase8a_bidwells_source"
branch_labels = None
depends_on = None

IDEAL_SOURCE_NAME = "ideal_land_current_sites"
IDEAL_SITEMAP_URLS = ["https://idealland.co.uk/sitemap.xml"]


def _listing_source_table() -> sa.Table:
    return sa.table(
        "listing_source",
        sa.column("name", sa.String(length=255)),
        sa.column("refresh_policy_json", sa.JSON()),
    )


def _backfill_ideal_land_sitemap(bind) -> None:
    listing_source = _listing_source_table()
    existing = bind.execute(
        sa.select(listing_source.c.refresh_policy_json).where(
            listing_source.c.name == IDEAL_SOURCE_NAME
        )
    ).scalar_one_or_none()
    if existing is None:
        return

    refresh_policy = dict(existing or {})
    refresh_policy["sitemap_urls"] = IDEAL_SITEMAP_URLS
    bind.execute(
        sa.update(listing_source)
        .where(listing_source.c.name == IDEAL_SOURCE_NAME)
        .values(refresh_policy_json=refresh_policy)
    )


def upgrade() -> None:
    bind = op.get_bind()
    _backfill_ideal_land_sitemap(bind)


def downgrade() -> None:
    bind = op.get_bind()
    listing_source = _listing_source_table()
    existing = bind.execute(
        sa.select(listing_source.c.refresh_policy_json).where(
            listing_source.c.name == IDEAL_SOURCE_NAME
        )
    ).scalar_one_or_none()
    if existing is None:
        return

    refresh_policy = dict(existing or {})
    refresh_policy.pop("sitemap_urls", None)
    bind.execute(
        sa.update(listing_source)
        .where(listing_source.c.name == IDEAL_SOURCE_NAME)
        .values(refresh_policy_json=refresh_policy)
    )
