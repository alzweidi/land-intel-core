"""Phase 3A planning context, coverage, and evidence foundation schema."""

import sqlalchemy as sa
from alembic import op
from landintel.domain.enums import (
    BaselinePackStatus,
    EvidenceImportance,
    GeomConfidence,
    JobType,
    SourceClass,
    SourceCoverageStatus,
    SourceFreshnessStatus,
)
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260415_000004"
down_revision = "20260415_000003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        source_coverage_status = postgresql.ENUM(
            SourceCoverageStatus,
            name="source_coverage_status",
        )
        source_class = postgresql.ENUM(SourceClass, name="source_class")
        evidence_importance = postgresql.ENUM(
            EvidenceImportance,
            name="evidence_importance",
        )
        baseline_pack_status = postgresql.ENUM(
            BaselinePackStatus,
            name="baseline_pack_status",
        )
        source_coverage_status_ref = postgresql.ENUM(
            SourceCoverageStatus,
            name="source_coverage_status",
            create_type=False,
        )
        source_class_ref = postgresql.ENUM(
            SourceClass,
            name="source_class",
            create_type=False,
        )
        evidence_importance_ref = postgresql.ENUM(
            EvidenceImportance,
            name="evidence_importance",
            create_type=False,
        )
        baseline_pack_status_ref = postgresql.ENUM(
            BaselinePackStatus,
            name="baseline_pack_status",
            create_type=False,
        )
        geom_confidence_ref = postgresql.ENUM(
            GeomConfidence,
            name="geom_confidence",
            create_type=False,
        )
        source_freshness_status_ref = postgresql.ENUM(
            SourceFreshnessStatus,
            name="source_freshness_status",
            create_type=False,
        )
    else:
        source_coverage_status = sa.Enum(
            SourceCoverageStatus,
            name="source_coverage_status",
        )
        source_class = sa.Enum(SourceClass, name="source_class")
        evidence_importance = sa.Enum(
            EvidenceImportance,
            name="evidence_importance",
        )
        baseline_pack_status = sa.Enum(
            BaselinePackStatus,
            name="baseline_pack_status",
        )
        source_coverage_status_ref = source_coverage_status
        source_class_ref = source_class
        evidence_importance_ref = evidence_importance
        baseline_pack_status_ref = baseline_pack_status
        geom_confidence_ref = sa.Enum(GeomConfidence, name="geom_confidence")
        source_freshness_status_ref = sa.Enum(
            SourceFreshnessStatus,
            name="source_freshness_status",
        )

    if is_postgres:
        for job_type in (
            JobType.PLD_INGEST_REFRESH.value,
            JobType.BOROUGH_REGISTER_INGEST.value,
            JobType.SITE_PLANNING_ENRICH.value,
            JobType.SITE_EXTANT_PERMISSION_RECHECK.value,
            JobType.SOURCE_COVERAGE_REFRESH.value,
        ):
            op.execute(f"ALTER TYPE job_type ADD VALUE IF NOT EXISTS '{job_type}'")
        op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    source_coverage_status.create(bind, checkfirst=True)
    source_class.create(bind, checkfirst=True)
    evidence_importance.create(bind, checkfirst=True)
    baseline_pack_status.create(bind, checkfirst=True)

    op.create_table(
        "source_coverage_snapshot",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "borough_id",
            sa.String(length=100),
            sa.ForeignKey("lpa_boundary.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_family", sa.String(length=100), nullable=False),
        sa.Column("coverage_geom_27700", sa.Text(), nullable=False),
        sa.Column("coverage_status", source_coverage_status_ref, nullable=False),
        sa.Column("gap_reason", sa.Text(), nullable=True),
        sa.Column("freshness_status", source_freshness_status_ref, nullable=False),
        sa.Column("coverage_note", sa.Text(), nullable=True),
        sa.Column(
            "source_snapshot_id",
            sa.Uuid(),
            sa.ForeignKey("source_snapshot.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_source_coverage_snapshot_borough_family_captured",
        "source_coverage_snapshot",
        ["borough_id", "source_family", "captured_at"],
    )

    op.create_table(
        "planning_application",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "borough_id",
            sa.String(length=100),
            sa.ForeignKey("lpa_boundary.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source_system", sa.String(length=100), nullable=False),
        sa.Column(
            "source_snapshot_id",
            sa.Uuid(),
            sa.ForeignKey("source_snapshot.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_ref", sa.String(length=255), nullable=False),
        sa.Column("application_type", sa.String(length=100), nullable=False),
        sa.Column("proposal_description", sa.Text(), nullable=False),
        sa.Column("valid_date", sa.Date(), nullable=True),
        sa.Column("decision_date", sa.Date(), nullable=True),
        sa.Column("decision", sa.String(length=100), nullable=True),
        sa.Column("decision_type", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=100), nullable=False),
        sa.Column("route_normalized", sa.String(length=100), nullable=True),
        sa.Column("units_proposed", sa.Integer(), nullable=True),
        sa.Column("site_geom_27700", sa.Text(), nullable=True),
        sa.Column("site_geom_4326", sa.JSON(), nullable=True),
        sa.Column("site_point_27700", sa.Text(), nullable=True),
        sa.Column("site_point_4326", sa.JSON(), nullable=True),
        sa.Column("source_priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("raw_record_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_system", "external_ref"),
    )
    op.create_index("ix_planning_application_borough_id", "planning_application", ["borough_id"])
    op.create_index(
        "ix_planning_application_external_ref",
        "planning_application",
        ["external_ref"],
    )
    op.create_index("ix_planning_application_status", "planning_application", ["status"])
    op.create_index("ix_planning_application_valid_date", "planning_application", ["valid_date"])
    op.create_index(
        "ix_planning_application_decision_date",
        "planning_application",
        ["decision_date"],
    )
    op.create_index(
        "ix_planning_application_source_system_priority",
        "planning_application",
        ["source_system", "source_priority"],
    )

    op.create_table(
        "planning_application_document",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "planning_application_id",
            sa.Uuid(),
            sa.ForeignKey("planning_application.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "asset_id",
            sa.Uuid(),
            sa.ForeignKey("raw_asset.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("doc_type", sa.String(length=100), nullable=False),
        sa.Column("doc_url", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_planning_application_document_application_id",
        "planning_application_document",
        ["planning_application_id"],
    )

    op.create_table(
        "site_planning_link",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "site_id",
            sa.Uuid(),
            sa.ForeignKey("site_candidate.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "planning_application_id",
            sa.Uuid(),
            sa.ForeignKey("planning_application.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("link_type", sa.String(length=100), nullable=False),
        sa.Column("distance_m", sa.Float(), nullable=True),
        sa.Column("overlap_pct", sa.Float(), nullable=True),
        sa.Column(
            "match_confidence",
            geom_confidence_ref,
            nullable=False,
        ),
        sa.Column(
            "manual_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("site_id", "planning_application_id"),
    )
    op.create_index("ix_site_planning_link_site_id", "site_planning_link", ["site_id"])
    op.create_index(
        "ix_site_planning_link_application_id",
        "site_planning_link",
        ["planning_application_id"],
    )

    op.create_table(
        "brownfield_site_state",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "borough_id",
            sa.String(length=100),
            sa.ForeignKey("lpa_boundary.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_snapshot_id",
            sa.Uuid(),
            sa.ForeignKey("source_snapshot.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_ref", sa.String(length=255), nullable=False),
        sa.Column("geom_27700", sa.Text(), nullable=False),
        sa.Column("geom_4326", sa.JSON(), nullable=False),
        sa.Column("part", sa.String(length=50), nullable=False),
        sa.Column("pip_status", sa.String(length=100), nullable=True),
        sa.Column("tdc_status", sa.String(length=100), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("raw_record_id", sa.String(length=255), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("raw_record_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("borough_id", "external_ref"),
    )
    op.create_index("ix_brownfield_site_state_borough_id", "brownfield_site_state", ["borough_id"])
    op.create_index(
        "ix_brownfield_site_state_external_ref",
        "brownfield_site_state",
        ["external_ref"],
    )
    op.create_index(
        "ix_brownfield_site_state_effective_to",
        "brownfield_site_state",
        ["effective_to"],
    )

    op.create_table(
        "policy_area",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "borough_id",
            sa.String(length=100),
            sa.ForeignKey("lpa_boundary.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("policy_family", sa.String(length=100), nullable=False),
        sa.Column("policy_code", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("geom_27700", sa.Text(), nullable=False),
        sa.Column("geom_4326", sa.JSON(), nullable=False),
        sa.Column("legal_effective_from", sa.Date(), nullable=True),
        sa.Column("legal_effective_to", sa.Date(), nullable=True),
        sa.Column(
            "source_snapshot_id",
            sa.Uuid(),
            sa.ForeignKey("source_snapshot.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_class", source_class_ref, nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("raw_record_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("borough_id", "policy_family", "policy_code"),
    )
    op.create_index("ix_policy_area_borough_id", "policy_area", ["borough_id"])
    op.create_index("ix_policy_area_policy_code", "policy_area", ["policy_code"])
    op.create_index(
        "ix_policy_area_effective_from",
        "policy_area",
        ["legal_effective_from"],
    )
    op.create_index(
        "ix_policy_area_effective_to",
        "policy_area",
        ["legal_effective_to"],
    )

    op.create_table(
        "planning_constraint_feature",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("feature_family", sa.String(length=100), nullable=False),
        sa.Column("feature_subtype", sa.String(length=100), nullable=False),
        sa.Column("authority_level", sa.String(length=100), nullable=False),
        sa.Column("geom_27700", sa.Text(), nullable=False),
        sa.Column("geom_4326", sa.JSON(), nullable=False),
        sa.Column("legal_status", sa.String(length=100), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column(
            "source_snapshot_id",
            sa.Uuid(),
            sa.ForeignKey("source_snapshot.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_class", source_class_ref, nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("raw_record_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_planning_constraint_feature_family",
        "planning_constraint_feature",
        ["feature_family"],
    )
    op.create_index(
        "ix_planning_constraint_feature_effective_to",
        "planning_constraint_feature",
        ["effective_to"],
    )

    op.create_table(
        "site_policy_fact",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "site_id",
            sa.Uuid(),
            sa.ForeignKey("site_candidate.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "policy_area_id",
            sa.Uuid(),
            sa.ForeignKey("policy_area.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("relation_type", sa.String(length=100), nullable=False),
        sa.Column("overlap_pct", sa.Float(), nullable=True),
        sa.Column("distance_m", sa.Float(), nullable=True),
        sa.Column(
            "importance",
            evidence_importance_ref,
            nullable=False,
            server_default=EvidenceImportance.MEDIUM.value,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("site_id", "policy_area_id"),
    )
    op.create_index("ix_site_policy_fact_site_id", "site_policy_fact", ["site_id"])

    op.create_table(
        "site_constraint_fact",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "site_id",
            sa.Uuid(),
            sa.ForeignKey("site_candidate.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "constraint_feature_id",
            sa.Uuid(),
            sa.ForeignKey("planning_constraint_feature.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("overlap_pct", sa.Float(), nullable=True),
        sa.Column("distance_m", sa.Float(), nullable=True),
        sa.Column(
            "severity",
            evidence_importance_ref,
            nullable=False,
            server_default=EvidenceImportance.MEDIUM.value,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("site_id", "constraint_feature_id"),
    )
    op.create_index(
        "ix_site_constraint_fact_site_id",
        "site_constraint_fact",
        ["site_id"],
    )

    op.create_table(
        "borough_baseline_pack",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "borough_id",
            sa.String(length=100),
            sa.ForeignKey("lpa_boundary.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.String(length=100), nullable=False),
        sa.Column("status", baseline_pack_status_ref, nullable=False),
        sa.Column("signed_off_by", sa.String(length=255), nullable=True),
        sa.Column("signed_off_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pack_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column(
            "source_snapshot_id",
            sa.Uuid(),
            sa.ForeignKey("source_snapshot.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("borough_id", "version"),
    )
    op.create_index(
        "ix_borough_baseline_pack_borough_id",
        "borough_baseline_pack",
        ["borough_id"],
    )
    op.create_index(
        "ix_borough_baseline_pack_status",
        "borough_baseline_pack",
        ["status"],
    )

    op.create_table(
        "borough_rulepack",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "borough_baseline_pack_id",
            sa.Uuid(),
            sa.ForeignKey("borough_baseline_pack.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("template_key", sa.String(length=100), nullable=False),
        sa.Column("rule_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_borough_rulepack_pack_template",
        "borough_rulepack",
        ["borough_baseline_pack_id", "template_key"],
    )

    if is_postgres:
        op.execute(
            "CREATE INDEX ix_source_coverage_snapshot_coverage_geom_27700_gist "
            "ON source_coverage_snapshot USING GIST (ST_GeomFromText(coverage_geom_27700, 27700))"
        )
        op.execute(
            "CREATE INDEX ix_planning_application_site_geom_27700_gist "
            "ON planning_application USING GIST (ST_GeomFromText(site_geom_27700, 27700)) "
            "WHERE site_geom_27700 IS NOT NULL"
        )
        op.execute(
            "CREATE INDEX ix_brownfield_site_state_geom_27700_gist "
            "ON brownfield_site_state USING GIST (ST_GeomFromText(geom_27700, 27700))"
        )
        op.execute(
            "CREATE INDEX ix_policy_area_geom_27700_gist "
            "ON policy_area USING GIST (ST_GeomFromText(geom_27700, 27700))"
        )
        op.execute(
            "CREATE INDEX ix_planning_constraint_feature_geom_27700_gist "
            "ON planning_constraint_feature USING GIST (ST_GeomFromText(geom_27700, 27700))"
        )
        op.execute(
            "CREATE INDEX ix_planning_application_proposal_description_fts "
            "ON planning_application USING GIN "
            "(to_tsvector('english', coalesce(proposal_description, '')))"
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        op.execute("DROP INDEX IF EXISTS ix_planning_application_proposal_description_fts")
        op.execute("DROP INDEX IF EXISTS ix_planning_constraint_feature_geom_27700_gist")
        op.execute("DROP INDEX IF EXISTS ix_policy_area_geom_27700_gist")
        op.execute("DROP INDEX IF EXISTS ix_brownfield_site_state_geom_27700_gist")
        op.execute("DROP INDEX IF EXISTS ix_planning_application_site_geom_27700_gist")
        op.execute("DROP INDEX IF EXISTS ix_source_coverage_snapshot_coverage_geom_27700_gist")

    op.drop_index("ix_borough_rulepack_pack_template", table_name="borough_rulepack")
    op.drop_table("borough_rulepack")
    op.drop_index("ix_borough_baseline_pack_status", table_name="borough_baseline_pack")
    op.drop_index("ix_borough_baseline_pack_borough_id", table_name="borough_baseline_pack")
    op.drop_table("borough_baseline_pack")
    op.drop_index("ix_site_constraint_fact_site_id", table_name="site_constraint_fact")
    op.drop_table("site_constraint_fact")
    op.drop_index("ix_site_policy_fact_site_id", table_name="site_policy_fact")
    op.drop_table("site_policy_fact")
    op.drop_index(
        "ix_planning_constraint_feature_effective_to",
        table_name="planning_constraint_feature",
    )
    op.drop_index(
        "ix_planning_constraint_feature_family",
        table_name="planning_constraint_feature",
    )
    op.drop_table("planning_constraint_feature")
    op.drop_index("ix_policy_area_effective_to", table_name="policy_area")
    op.drop_index("ix_policy_area_effective_from", table_name="policy_area")
    op.drop_index("ix_policy_area_policy_code", table_name="policy_area")
    op.drop_index("ix_policy_area_borough_id", table_name="policy_area")
    op.drop_table("policy_area")
    op.drop_index(
        "ix_brownfield_site_state_effective_to",
        table_name="brownfield_site_state",
    )
    op.drop_index(
        "ix_brownfield_site_state_external_ref",
        table_name="brownfield_site_state",
    )
    op.drop_index("ix_brownfield_site_state_borough_id", table_name="brownfield_site_state")
    op.drop_table("brownfield_site_state")
    op.drop_index("ix_site_planning_link_application_id", table_name="site_planning_link")
    op.drop_index("ix_site_planning_link_site_id", table_name="site_planning_link")
    op.drop_table("site_planning_link")
    op.drop_index(
        "ix_planning_application_document_application_id",
        table_name="planning_application_document",
    )
    op.drop_table("planning_application_document")
    op.drop_index(
        "ix_planning_application_source_system_priority",
        table_name="planning_application",
    )
    op.drop_index("ix_planning_application_decision_date", table_name="planning_application")
    op.drop_index("ix_planning_application_valid_date", table_name="planning_application")
    op.drop_index("ix_planning_application_status", table_name="planning_application")
    op.drop_index("ix_planning_application_external_ref", table_name="planning_application")
    op.drop_index("ix_planning_application_borough_id", table_name="planning_application")
    op.drop_table("planning_application")
    op.drop_index(
        "ix_source_coverage_snapshot_borough_family_captured",
        table_name="source_coverage_snapshot",
    )
    op.drop_table("source_coverage_snapshot")

    baseline_pack_status = sa.Enum(BaselinePackStatus, name="baseline_pack_status")
    evidence_importance = sa.Enum(EvidenceImportance, name="evidence_importance")
    source_class = sa.Enum(SourceClass, name="source_class")
    source_coverage_status = sa.Enum(SourceCoverageStatus, name="source_coverage_status")

    baseline_pack_status.drop(bind, checkfirst=True)
    evidence_importance.drop(bind, checkfirst=True)
    source_class.drop(bind, checkfirst=True)
    source_coverage_status.drop(bind, checkfirst=True)
