"""Widen Alembic version identifiers before long Phase 8A revisions.

Revision ID: 20260416_000009a_alembic_len
Revises: 20260415_000009
Create Date: 2026-04-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260416_000009a_alembic_len"
down_revision = "20260415_000009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("alembic_version") as batch_op:
        batch_op.alter_column(
            "version_num",
            existing_type=sa.String(length=32),
            type_=sa.String(length=255),
            existing_nullable=False,
        )


def downgrade() -> None:
    """Keep the widened Alembic version column in place on downgrade."""
