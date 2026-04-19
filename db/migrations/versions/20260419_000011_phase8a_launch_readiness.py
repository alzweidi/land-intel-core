"""Phase 8A launch-readiness backfills for automated source refresh."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260419_000011_phase8a_launch_readiness"
down_revision = "20260417_000010_phase8a_lineage_integrity"
branch_labels = None
depends_on = None


def _listing_source_table() -> sa.Table:
    return sa.table(
        "listing_source",
        sa.column("id", sa.Uuid()),
        sa.column("name", sa.String(length=255)),
        sa.column("refresh_policy_json", sa.JSON()),
    )


def _job_run_table() -> sa.Table:
    return sa.table(
        "job_run",
        sa.column("id", sa.Uuid()),
        sa.column("job_type", sa.String(length=255)),
        sa.column("status", sa.String(length=255)),
        sa.column("payload_json", sa.JSON()),
    )


def _backfill_example_public_page_interval(bind) -> None:
    listing_source = _listing_source_table()
    seeded_source = bind.execute(
        sa.select(
            listing_source.c.id,
            listing_source.c.refresh_policy_json,
        ).where(listing_source.c.name == "example_public_page")
    ).mappings().first()
    if seeded_source is not None:
        refresh_policy = dict(seeded_source["refresh_policy_json"] or {})
        if refresh_policy.get("interval_hours") is None:
            refresh_policy["interval_hours"] = 24
            bind.execute(
                sa.update(listing_source)
                .where(listing_source.c.id == seeded_source["id"])
                .values(refresh_policy_json=refresh_policy)
            )


def _backfill_listing_source_run_dedupe_keys(bind) -> None:
    job_run = _job_run_table()
    active_runs = bind.execute(
        sa.select(
            job_run.c.id,
            job_run.c.payload_json,
        ).where(
            sa.cast(job_run.c.job_type, sa.String()) == "LISTING_SOURCE_RUN",
            sa.cast(job_run.c.status, sa.String()).in_(("QUEUED", "RUNNING")),
        )
    ).mappings()
    for run in active_runs:
        payload = dict(run["payload_json"] or {})
        source_name = str(payload.get("source_name") or "").strip()
        if not source_name:
            continue
        dedupe_key = f"source:{source_name}"
        if payload.get("dedupe_key") == dedupe_key:
            continue
        payload["dedupe_key"] = dedupe_key
        bind.execute(
            sa.update(job_run)
            .where(job_run.c.id == run["id"])
            .values(payload_json=payload)
        )


def upgrade() -> None:
    bind = op.get_bind()
    _backfill_example_public_page_interval(bind)
    _backfill_listing_source_run_dedupe_keys(bind)


def downgrade() -> None:
    """Keep backfilled data in place on downgrade."""
