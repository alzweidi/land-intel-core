"""Add real automated tabular-feed source for the Cabinet Office surplus register."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from landintel.domain.enums import ComplianceMode, ConnectorType

revision = "20260420_000012_phase8a_real_source_launch"
down_revision = "20260419_000011_phase8a_launch_readiness"
branch_labels = None
depends_on = None

REAL_SOURCE_ID = uuid.UUID("99e25bc7-a2fd-4774-97de-a7fdb8e29c5a")
REAL_SOURCE_NAME = "cabinet_office_surplus_property"
REAL_SOURCE_REFRESH_POLICY = {
    "interval_hours": 24,
    "feed_url": "https://data.insite.cabinetoffice.gov.uk/insite/Register.xlsx",
    "feed_format": "xlsx",
    "sheet_name": "Register",
    "row_transform": "cabinet_office_surplus_property_v1",
    "status_of_sale_values": ["On the Market", "Under Offer"],
    "local_authority_contains_any": [
        "LONDON BOROUGH OF CAMDEN",
        "LONDON BOROUGH OF SOUTHWARK",
    ],
    "max_listings": 200,
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


def _ensure_tabular_feed_enum() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    context = op.get_context()
    with context.autocommit_block():
        op.execute("ALTER TYPE connector_type ADD VALUE IF NOT EXISTS 'TABULAR_FEED'")


def _upsert_real_automated_source(bind) -> None:
    listing_source = _listing_source_table()
    existing = bind.execute(
        sa.select(
            listing_source.c.id,
            listing_source.c.refresh_policy_json,
        ).where(listing_source.c.name == REAL_SOURCE_NAME)
    ).mappings().first()
    if existing is None:
        bind.execute(
            sa.insert(listing_source).values(
                id=REAL_SOURCE_ID,
                name=REAL_SOURCE_NAME,
                connector_type=ConnectorType.TABULAR_FEED.value,
                compliance_mode=ComplianceMode.COMPLIANT_AUTOMATED.value,
                refresh_policy_json=REAL_SOURCE_REFRESH_POLICY,
                active=True,
                created_at=datetime.now(UTC),
            )
        )
        return

    refresh_policy = dict(existing["refresh_policy_json"] or {})
    refresh_policy.update(REAL_SOURCE_REFRESH_POLICY)
    bind.execute(
        sa.update(listing_source)
        .where(listing_source.c.name == REAL_SOURCE_NAME)
        .values(
            connector_type=ConnectorType.TABULAR_FEED.value,
            compliance_mode=ComplianceMode.COMPLIANT_AUTOMATED.value,
            refresh_policy_json=refresh_policy,
            active=True,
        )
    )


def upgrade() -> None:
    bind = op.get_bind()
    _ensure_tabular_feed_enum()
    _upsert_real_automated_source(bind)


def downgrade() -> None:
    bind = op.get_bind()
    listing_source = _listing_source_table()
    bind.execute(sa.delete(listing_source).where(listing_source.c.name == REAL_SOURCE_NAME))
