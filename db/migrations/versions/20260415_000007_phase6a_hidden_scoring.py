"""Phase 6A hidden scoring release registry and assessment extensions."""

import sqlalchemy as sa
from alembic import op
from landintel.domain.enums import CalibrationMethod, ModelReleaseStatus, ReleaseChannel
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260415_000007"
down_revision = "20260415_000006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        release_channel = postgresql.ENUM(ReleaseChannel, name="release_channel")
        model_release_status = postgresql.ENUM(
            ModelReleaseStatus,
            name="model_release_status",
        )
        calibration_method = postgresql.ENUM(
            CalibrationMethod,
            name="calibration_method",
        )
        release_channel_ref = postgresql.ENUM(
            ReleaseChannel,
            name="release_channel",
            create_type=False,
        )
        model_release_status_ref = postgresql.ENUM(
            ModelReleaseStatus,
            name="model_release_status",
            create_type=False,
        )
        calibration_method_ref = postgresql.ENUM(
            CalibrationMethod,
            name="calibration_method",
            create_type=False,
        )
    else:
        release_channel = sa.Enum(ReleaseChannel, name="release_channel")
        model_release_status = sa.Enum(ModelReleaseStatus, name="model_release_status")
        calibration_method = sa.Enum(CalibrationMethod, name="calibration_method")
        release_channel_ref = release_channel
        model_release_status_ref = model_release_status
        calibration_method_ref = calibration_method

    release_channel.create(bind, checkfirst=True)
    model_release_status.create(bind, checkfirst=True)
    calibration_method.create(bind, checkfirst=True)

    op.create_table(
        "model_release",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("template_key", sa.String(length=100), nullable=False),
        sa.Column("release_channel", release_channel_ref, nullable=False),
        sa.Column("scope_key", sa.String(length=255), nullable=False),
        sa.Column("scope_borough_id", sa.String(length=100), nullable=True),
        sa.Column("status", model_release_status_ref, nullable=False),
        sa.Column("model_kind", sa.String(length=100), nullable=False),
        sa.Column("transform_version", sa.String(length=100), nullable=False),
        sa.Column("feature_version", sa.String(length=100), nullable=False),
        sa.Column("calibration_method", calibration_method_ref, nullable=False),
        sa.Column("model_artifact_path", sa.Text(), nullable=True),
        sa.Column("model_artifact_hash", sa.String(length=64), nullable=True),
        sa.Column("calibration_artifact_path", sa.Text(), nullable=True),
        sa.Column("calibration_artifact_hash", sa.String(length=64), nullable=True),
        sa.Column("validation_artifact_path", sa.Text(), nullable=True),
        sa.Column("validation_artifact_hash", sa.String(length=64), nullable=True),
        sa.Column("model_card_path", sa.Text(), nullable=True),
        sa.Column("model_card_hash", sa.String(length=64), nullable=True),
        sa.Column("train_window_start", sa.Date(), nullable=True),
        sa.Column("train_window_end", sa.Date(), nullable=True),
        sa.Column("support_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("positive_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("negative_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metrics_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("manifest_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("reason_text", sa.Text(), nullable=True),
        sa.Column("supersedes_release_id", sa.Uuid(), nullable=True),
        sa.Column("activated_by", sa.String(length=255), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_by", sa.String(length=255), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["supersedes_release_id"],
            ["model_release.id"],
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_model_release_template_channel_status",
        "model_release",
        ["template_key", "release_channel", "status"],
    )
    op.create_index("ix_model_release_scope_key", "model_release", ["scope_key"])

    op.create_table(
        "active_release_scope",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("scope_key", sa.String(length=255), nullable=False),
        sa.Column("template_key", sa.String(length=100), nullable=False),
        sa.Column("release_channel", release_channel_ref, nullable=False),
        sa.Column("borough_id", sa.String(length=100), nullable=True),
        sa.Column("model_release_id", sa.Uuid(), nullable=False),
        sa.Column("activated_by", sa.String(length=255), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["model_release_id"],
            ["model_release.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("scope_key"),
    )
    op.create_index(
        "ix_active_release_scope_template_channel",
        "active_release_scope",
        ["template_key", "release_channel"],
    )

    op.add_column(
        "assessment_result",
        sa.Column("release_scope_key", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "assessment_result",
        sa.Column("scenario_quality", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "assessment_result",
        sa.Column("ood_quality", sa.String(length=32), nullable=True),
    )
    op.create_foreign_key(
        "fk_assessment_result_model_release",
        "assessment_result",
        "model_release",
        ["model_release_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_assessment_result_release_scope_key",
        "assessment_result",
        ["release_scope_key"],
    )

    op.add_column(
        "prediction_ledger",
        sa.Column("release_scope_key", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "prediction_ledger",
        sa.Column(
            "response_mode",
            sa.String(length=32),
            nullable=False,
            server_default="PRE_SCORE",
        ),
    )
    op.create_foreign_key(
        "fk_prediction_ledger_model_release",
        "prediction_ledger",
        "model_release",
        ["model_release_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_prediction_ledger_release_scope_key",
        "prediction_ledger",
        ["release_scope_key"],
    )


def downgrade() -> None:
    op.drop_index("ix_prediction_ledger_release_scope_key", table_name="prediction_ledger")
    op.drop_constraint(
        "fk_prediction_ledger_model_release",
        "prediction_ledger",
        type_="foreignkey",
    )
    op.drop_column("prediction_ledger", "response_mode")
    op.drop_column("prediction_ledger", "release_scope_key")

    op.drop_index("ix_assessment_result_release_scope_key", table_name="assessment_result")
    op.drop_constraint(
        "fk_assessment_result_model_release",
        "assessment_result",
        type_="foreignkey",
    )
    op.drop_column("assessment_result", "ood_quality")
    op.drop_column("assessment_result", "scenario_quality")
    op.drop_column("assessment_result", "release_scope_key")

    op.drop_index(
        "ix_active_release_scope_template_channel",
        table_name="active_release_scope",
    )
    op.drop_table("active_release_scope")

    op.drop_index("ix_model_release_scope_key", table_name="model_release")
    op.drop_index(
        "ix_model_release_template_channel_status",
        table_name="model_release",
    )
    op.drop_table("model_release")

    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    if not is_postgres:
        op.execute("DROP TYPE IF EXISTS calibration_method")
        op.execute("DROP TYPE IF EXISTS model_release_status")
        op.execute("DROP TYPE IF EXISTS release_channel")
