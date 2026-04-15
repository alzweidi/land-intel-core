"""Phase 4A scenario engine foundation schema."""

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from landintel.domain.enums import (
    BaselinePackStatus,
    JobType,
    ProposalForm,
    ScenarioSource,
    ScenarioStatus,
    SourceFreshnessStatus,
)
from landintel.scenarios.catalog import SCENARIO_TEMPLATE_DEFINITIONS
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260415_000005"
down_revision = "20260415_000004"
branch_labels = None
depends_on = None

SCENARIO_NAMESPACE = uuid.UUID("9b24d765-3d61-45cf-994f-7cbeb18d6bf0")


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        baseline_pack_status_ref = postgresql.ENUM(
            BaselinePackStatus,
            name="baseline_pack_status",
            create_type=False,
        )
        source_freshness_status_ref = postgresql.ENUM(
            SourceFreshnessStatus,
            name="source_freshness_status",
            create_type=False,
        )
        scenario_source = postgresql.ENUM(ScenarioSource, name="scenario_source")
        scenario_status = postgresql.ENUM(ScenarioStatus, name="scenario_status")
        proposal_form = postgresql.ENUM(ProposalForm, name="proposal_form")
        scenario_source_ref = postgresql.ENUM(
            ScenarioSource,
            name="scenario_source",
            create_type=False,
        )
        scenario_status_ref = postgresql.ENUM(
            ScenarioStatus,
            name="scenario_status",
            create_type=False,
        )
        proposal_form_ref = postgresql.ENUM(
            ProposalForm,
            name="proposal_form",
            create_type=False,
        )
    else:
        baseline_pack_status_ref = sa.Enum(
            BaselinePackStatus,
            name="baseline_pack_status",
        )
        source_freshness_status_ref = sa.Enum(
            SourceFreshnessStatus,
            name="source_freshness_status",
        )
        scenario_source = sa.Enum(ScenarioSource, name="scenario_source")
        scenario_status = sa.Enum(ScenarioStatus, name="scenario_status")
        proposal_form = sa.Enum(ProposalForm, name="proposal_form")
        scenario_source_ref = scenario_source
        scenario_status_ref = scenario_status
        proposal_form_ref = proposal_form

    if is_postgres:
        for job_type in (
            JobType.SITE_SCENARIO_SUGGEST_REFRESH.value,
            JobType.SITE_SCENARIO_GEOMETRY_REFRESH.value,
            JobType.BOROUGH_RULEPACK_SCENARIO_REFRESH.value,
            JobType.SCENARIO_EVIDENCE_REFRESH.value,
        ):
            op.execute(f"ALTER TYPE job_type ADD VALUE IF NOT EXISTS '{job_type}'")

    scenario_source.create(bind, checkfirst=True)
    scenario_status.create(bind, checkfirst=True)
    proposal_form.create(bind, checkfirst=True)

    op.add_column(
        "borough_baseline_pack",
        sa.Column(
            "freshness_status",
            source_freshness_status_ref,
            nullable=False,
            server_default=SourceFreshnessStatus.UNKNOWN.value,
        ),
    )
    op.execute(
        """
        UPDATE borough_baseline_pack
        SET freshness_status = COALESCE(
            (
                SELECT source_snapshot.freshness_status
                FROM source_snapshot
                WHERE source_snapshot.id = borough_baseline_pack.source_snapshot_id
            ),
            'UNKNOWN'
        )
        """
    )
    if is_postgres:
        op.alter_column("borough_baseline_pack", "freshness_status", server_default=None)

    op.add_column(
        "borough_rulepack",
        sa.Column(
            "status",
            baseline_pack_status_ref,
            nullable=False,
            server_default=BaselinePackStatus.DRAFT.value,
        ),
    )
    op.add_column(
        "borough_rulepack",
        sa.Column(
            "freshness_status",
            source_freshness_status_ref,
            nullable=False,
            server_default=SourceFreshnessStatus.UNKNOWN.value,
        ),
    )
    op.add_column(
        "borough_rulepack",
        sa.Column(
            "source_snapshot_id",
            sa.Uuid(),
            sa.ForeignKey("source_snapshot.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "borough_rulepack",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.execute(
        """
        UPDATE borough_rulepack
        SET status = COALESCE(
                (
                    SELECT borough_baseline_pack.status
                    FROM borough_baseline_pack
                    WHERE borough_baseline_pack.id = borough_rulepack.borough_baseline_pack_id
                ),
                'DRAFT'
            ),
            freshness_status = COALESCE(
                (
                    SELECT borough_baseline_pack.freshness_status
                    FROM borough_baseline_pack
                    WHERE borough_baseline_pack.id = borough_rulepack.borough_baseline_pack_id
                ),
                'UNKNOWN'
            ),
            source_snapshot_id = (
                SELECT borough_baseline_pack.source_snapshot_id
                FROM borough_baseline_pack
                WHERE borough_baseline_pack.id = borough_rulepack.borough_baseline_pack_id
            ),
            updated_at = CURRENT_TIMESTAMP
        """
    )
    if is_postgres:
        op.alter_column("borough_rulepack", "status", server_default=None)
        op.alter_column("borough_rulepack", "freshness_status", server_default=None)
        op.alter_column("borough_rulepack", "updated_at", server_default=None)
    op.create_index(
        "ix_borough_baseline_pack_freshness",
        "borough_baseline_pack",
        ["freshness_status"],
    )
    op.create_index("ix_borough_rulepack_status", "borough_rulepack", ["status"])
    op.create_index(
        "ix_borough_rulepack_freshness",
        "borough_rulepack",
        ["freshness_status"],
    )

    op.create_table(
        "scenario_template",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("version", sa.String(length=50), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("config_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("key", "version"),
    )
    op.create_index("ix_scenario_template_enabled", "scenario_template", ["enabled"])
    op.create_index("ix_scenario_template_key", "scenario_template", ["key"])

    op.create_table(
        "site_scenario",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "site_id",
            sa.Uuid(),
            sa.ForeignKey("site_candidate.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("template_key", sa.String(length=100), nullable=False),
        sa.Column("template_version", sa.String(length=50), nullable=False),
        sa.Column("proposal_form", proposal_form_ref, nullable=False),
        sa.Column("units_assumed", sa.Integer(), nullable=False),
        sa.Column("route_assumed", sa.String(length=100), nullable=False),
        sa.Column("height_band_assumed", sa.String(length=100), nullable=False),
        sa.Column("net_developable_area_pct", sa.Float(), nullable=False),
        sa.Column(
            "housing_mix_assumed_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("parking_assumption", sa.Text(), nullable=True),
        sa.Column("affordable_housing_assumption", sa.Text(), nullable=True),
        sa.Column("access_assumption", sa.Text(), nullable=True),
        sa.Column(
            "site_geometry_revision_id",
            sa.Uuid(),
            sa.ForeignKey("site_geometry_revision.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("red_line_geom_hash", sa.String(length=64), nullable=False),
        sa.Column("scenario_source", scenario_source_ref, nullable=False),
        sa.Column("status", scenario_status_ref, nullable=False),
        sa.Column(
            "supersedes_id",
            sa.Uuid(),
            sa.ForeignKey("site_scenario.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_headline", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("heuristic_rank", sa.Integer(), nullable=True),
        sa.Column(
            "manual_review_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("stale_reason", sa.Text(), nullable=True),
        sa.Column("rationale_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("evidence_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_site_scenario_site_id", "site_scenario", ["site_id"])
    op.create_index("ix_site_scenario_status", "site_scenario", ["status"])
    op.create_index("ix_site_scenario_template_key", "site_scenario", ["template_key"])
    op.create_index(
        "ix_site_scenario_site_current",
        "site_scenario",
        ["site_id", "is_current"],
    )
    op.create_index(
        "ix_site_scenario_site_headline",
        "site_scenario",
        ["site_id", "is_headline"],
    )
    op.create_index(
        "ix_site_scenario_geometry_revision_id",
        "site_scenario",
        ["site_geometry_revision_id"],
    )

    op.create_table(
        "scenario_review",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "scenario_id",
            sa.Uuid(),
            sa.ForeignKey("site_scenario.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("review_status", scenario_status_ref, nullable=False),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("reviewed_by", sa.String(length=255), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_scenario_review_scenario_id", "scenario_review", ["scenario_id"])
    op.create_index("ix_scenario_review_reviewed_at", "scenario_review", ["reviewed_at"])

    template_table = sa.table(
        "scenario_template",
        sa.column("id", sa.Uuid()),
        sa.column("key", sa.String()),
        sa.column("version", sa.String()),
        sa.column("enabled", sa.Boolean()),
        sa.column("config_json", sa.JSON()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    now = datetime.now(UTC)
    op.bulk_insert(
        template_table,
        [
            {
                "id": uuid.uuid5(
                    SCENARIO_NAMESPACE,
                    f"{template['key']}:{template['version']}",
                ),
                "key": template["key"],
                "version": template["version"],
                "enabled": template["enabled"],
                "config_json": template["config_json"],
                "created_at": now,
                "updated_at": now,
            }
            for template in SCENARIO_TEMPLATE_DEFINITIONS
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_scenario_review_reviewed_at", table_name="scenario_review")
    op.drop_index("ix_scenario_review_scenario_id", table_name="scenario_review")
    op.drop_table("scenario_review")

    op.drop_index("ix_site_scenario_geometry_revision_id", table_name="site_scenario")
    op.drop_index("ix_site_scenario_site_headline", table_name="site_scenario")
    op.drop_index("ix_site_scenario_site_current", table_name="site_scenario")
    op.drop_index("ix_site_scenario_template_key", table_name="site_scenario")
    op.drop_index("ix_site_scenario_status", table_name="site_scenario")
    op.drop_index("ix_site_scenario_site_id", table_name="site_scenario")
    op.drop_table("site_scenario")

    op.drop_index("ix_scenario_template_key", table_name="scenario_template")
    op.drop_index("ix_scenario_template_enabled", table_name="scenario_template")
    op.drop_table("scenario_template")

    op.drop_index("ix_borough_rulepack_freshness", table_name="borough_rulepack")
    op.drop_index("ix_borough_rulepack_status", table_name="borough_rulepack")
    op.drop_index("ix_borough_baseline_pack_freshness", table_name="borough_baseline_pack")
    op.drop_column("borough_rulepack", "updated_at")
    op.drop_column("borough_rulepack", "source_snapshot_id")
    op.drop_column("borough_rulepack", "freshness_status")
    op.drop_column("borough_rulepack", "status")
    op.drop_column("borough_baseline_pack", "freshness_status")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        postgresql.ENUM(ProposalForm, name="proposal_form").drop(bind, checkfirst=True)
        postgresql.ENUM(ScenarioStatus, name="scenario_status").drop(bind, checkfirst=True)
        postgresql.ENUM(ScenarioSource, name="scenario_source").drop(bind, checkfirst=True)
    else:
        sa.Enum(ProposalForm, name="proposal_form").drop(bind, checkfirst=True)
        sa.Enum(ScenarioStatus, name="scenario_status").drop(bind, checkfirst=True)
        sa.Enum(ScenarioSource, name="scenario_source").drop(bind, checkfirst=True)
