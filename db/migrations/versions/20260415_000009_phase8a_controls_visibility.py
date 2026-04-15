"""Phase 8A controls, visibility gating, overrides, incidents, and audit exports."""

import sqlalchemy as sa
from alembic import op
from landintel.domain.enums import (
    AppRoleName,
    AssessmentOverrideStatus,
    AssessmentOverrideType,
    AuditExportStatus,
    IncidentStatus,
    IncidentType,
    VisibilityMode,
)
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260415_000009"
down_revision = "20260415_000008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        visibility_mode = postgresql.ENUM(VisibilityMode, name="visibility_mode")
        assessment_override_type = postgresql.ENUM(
            AssessmentOverrideType,
            name="assessment_override_type",
        )
        assessment_override_status = postgresql.ENUM(
            AssessmentOverrideStatus,
            name="assessment_override_status",
        )
        incident_type = postgresql.ENUM(IncidentType, name="incident_type")
        incident_status = postgresql.ENUM(IncidentStatus, name="incident_status")
        audit_export_status = postgresql.ENUM(
            AuditExportStatus,
            name="audit_export_status",
        )
        visibility_mode_ref = postgresql.ENUM(
            VisibilityMode,
            name="visibility_mode",
            create_type=False,
        )
        assessment_override_type_ref = postgresql.ENUM(
            AssessmentOverrideType,
            name="assessment_override_type",
            create_type=False,
        )
        assessment_override_status_ref = postgresql.ENUM(
            AssessmentOverrideStatus,
            name="assessment_override_status",
            create_type=False,
        )
        incident_type_ref = postgresql.ENUM(
            IncidentType,
            name="incident_type",
            create_type=False,
        )
        incident_status_ref = postgresql.ENUM(
            IncidentStatus,
            name="incident_status",
            create_type=False,
        )
        audit_export_status_ref = postgresql.ENUM(
            AuditExportStatus,
            name="audit_export_status",
            create_type=False,
        )
        app_role_name_ref = postgresql.ENUM(
            AppRoleName,
            name="app_role_name",
            create_type=False,
        )
    else:
        visibility_mode = sa.Enum(VisibilityMode, name="visibility_mode")
        assessment_override_type = sa.Enum(
            AssessmentOverrideType,
            name="assessment_override_type",
        )
        assessment_override_status = sa.Enum(
            AssessmentOverrideStatus,
            name="assessment_override_status",
        )
        incident_type = sa.Enum(IncidentType, name="incident_type")
        incident_status = sa.Enum(IncidentStatus, name="incident_status")
        audit_export_status = sa.Enum(AuditExportStatus, name="audit_export_status")
        visibility_mode_ref = visibility_mode
        assessment_override_type_ref = assessment_override_type
        assessment_override_status_ref = assessment_override_status
        incident_type_ref = incident_type
        incident_status_ref = incident_status
        audit_export_status_ref = audit_export_status
        app_role_name_ref = sa.Enum(AppRoleName, name="app_role_name")

    visibility_mode.create(bind, checkfirst=True)
    assessment_override_type.create(bind, checkfirst=True)
    assessment_override_status.create(bind, checkfirst=True)
    incident_type.create(bind, checkfirst=True)
    incident_status.create(bind, checkfirst=True)
    audit_export_status.create(bind, checkfirst=True)

    op.add_column(
        "active_release_scope",
        sa.Column(
            "visibility_mode",
            visibility_mode_ref,
            nullable=False,
            server_default=VisibilityMode.HIDDEN_ONLY.value,
        ),
    )
    op.add_column(
        "active_release_scope",
        sa.Column("visibility_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "active_release_scope",
        sa.Column("visible_enabled_by", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "active_release_scope",
        sa.Column("visible_enabled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "active_release_scope",
        sa.Column("visibility_updated_by", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "active_release_scope",
        sa.Column("visibility_updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.add_column(
        "prediction_ledger",
        sa.Column("model_artifact_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "prediction_ledger",
        sa.Column("validation_artifact_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "prediction_ledger",
        sa.Column(
            "replay_verification_status",
            sa.String(length=32),
            nullable=False,
            server_default="VERIFIED",
        ),
    )
    op.add_column(
        "prediction_ledger",
        sa.Column("replay_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "prediction_ledger",
        sa.Column("replay_verification_note", sa.Text(), nullable=True),
    )

    op.create_table(
        "assessment_override",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("assessment_run_id", sa.Uuid(), nullable=False),
        sa.Column("assessment_result_id", sa.Uuid(), nullable=True),
        sa.Column("valuation_run_id", sa.Uuid(), nullable=True),
        sa.Column("override_type", assessment_override_type_ref, nullable=False),
        sa.Column("status", assessment_override_status_ref, nullable=False),
        sa.Column("actor_name", sa.String(length=255), nullable=False),
        sa.Column("actor_role", app_role_name_ref, nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("override_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("supersedes_id", sa.Uuid(), nullable=True),
        sa.Column("resolved_by", sa.String(length=255), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["assessment_run_id"],
            ["assessment_run.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["assessment_result_id"],
            ["assessment_result.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["valuation_run_id"],
            ["valuation_run.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_id"],
            ["assessment_override.id"],
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_assessment_override_run_type_status",
        "assessment_override",
        ["assessment_run_id", "override_type", "status"],
    )
    op.create_index(
        "ix_assessment_override_actor_created",
        "assessment_override",
        ["actor_name", "created_at"],
    )

    op.create_table(
        "incident_record",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("active_release_scope_id", sa.Uuid(), nullable=True),
        sa.Column("model_release_id", sa.Uuid(), nullable=True),
        sa.Column("scope_key", sa.String(length=255), nullable=False),
        sa.Column("template_key", sa.String(length=100), nullable=False),
        sa.Column("borough_id", sa.String(length=100), nullable=True),
        sa.Column("incident_type", incident_type_ref, nullable=False),
        sa.Column("status", incident_status_ref, nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("previous_visibility_mode", visibility_mode_ref, nullable=True),
        sa.Column("applied_visibility_mode", visibility_mode_ref, nullable=False),
        sa.Column("supersedes_id", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("resolved_by", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["active_release_scope_id"],
            ["active_release_scope.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["model_release_id"],
            ["model_release.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_id"],
            ["incident_record.id"],
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_incident_record_scope_status",
        "incident_record",
        ["scope_key", "status"],
    )
    op.create_index("ix_incident_record_created_at", "incident_record", ["created_at"])

    op.create_table(
        "audit_export",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("assessment_run_id", sa.Uuid(), nullable=False),
        sa.Column("assessment_result_id", sa.Uuid(), nullable=True),
        sa.Column("valuation_run_id", sa.Uuid(), nullable=True),
        sa.Column("prediction_ledger_id", sa.Uuid(), nullable=True),
        sa.Column("model_release_id", sa.Uuid(), nullable=True),
        sa.Column("status", audit_export_status_ref, nullable=False),
        sa.Column("manifest_path", sa.Text(), nullable=True),
        sa.Column("manifest_hash", sa.String(length=64), nullable=True),
        sa.Column("manifest_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("requested_by", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["assessment_run_id"],
            ["assessment_run.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["assessment_result_id"],
            ["assessment_result.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["valuation_run_id"],
            ["valuation_run.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["prediction_ledger_id"],
            ["prediction_ledger.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["model_release_id"],
            ["model_release.id"],
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_audit_export_run_created",
        "audit_export",
        ["assessment_run_id", "created_at"],
    )
    op.create_index(
        "ix_prediction_ledger_scope_created",
        "prediction_ledger",
        ["release_scope_key", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_prediction_ledger_scope_created", table_name="prediction_ledger")
    op.drop_index("ix_audit_export_run_created", table_name="audit_export")
    op.drop_table("audit_export")
    op.drop_index("ix_incident_record_created_at", table_name="incident_record")
    op.drop_index("ix_incident_record_scope_status", table_name="incident_record")
    op.drop_table("incident_record")
    op.drop_index(
        "ix_assessment_override_actor_created",
        table_name="assessment_override",
    )
    op.drop_index(
        "ix_assessment_override_run_type_status",
        table_name="assessment_override",
    )
    op.drop_table("assessment_override")

    op.drop_column("prediction_ledger", "replay_verification_note")
    op.drop_column("prediction_ledger", "replay_verified_at")
    op.drop_column("prediction_ledger", "replay_verification_status")
    op.drop_column("prediction_ledger", "validation_artifact_hash")
    op.drop_column("prediction_ledger", "model_artifact_hash")

    op.drop_column("active_release_scope", "visibility_updated_at")
    op.drop_column("active_release_scope", "visibility_updated_by")
    op.drop_column("active_release_scope", "visible_enabled_at")
    op.drop_column("active_release_scope", "visible_enabled_by")
    op.drop_column("active_release_scope", "visibility_reason")
    op.drop_column("active_release_scope", "visibility_mode")

    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    if not is_postgres:
        op.execute("DROP TYPE IF EXISTS audit_export_status")
        op.execute("DROP TYPE IF EXISTS incident_status")
        op.execute("DROP TYPE IF EXISTS incident_type")
        op.execute("DROP TYPE IF EXISTS assessment_override_status")
        op.execute("DROP TYPE IF EXISTS assessment_override_type")
        op.execute("DROP TYPE IF EXISTS visibility_mode")
