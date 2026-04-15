"""Phase 0 bootstrap schema."""

import sqlalchemy as sa
from alembic import op
from landintel.domain.enums import AppRoleName, JobStatus, JobType, SourceFreshnessStatus

# revision identifiers, used by Alembic.
revision = "20260415_000001"
down_revision = None
branch_labels = None
depends_on = None


source_freshness_status = sa.Enum(
    SourceFreshnessStatus,
    name="source_freshness_status",
)
app_role_name = sa.Enum(AppRoleName, name="app_role_name")
job_status = sa.Enum(JobStatus, name="job_status")
job_type = sa.Enum(JobType, name="job_type")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    source_freshness_status.create(bind, checkfirst=True)
    app_role_name.create(bind, checkfirst=True)
    job_status.create(bind, checkfirst=True)
    job_type.create(bind, checkfirst=True)

    op.create_table(
        "source_snapshot",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("source_family", sa.String(length=100), nullable=False),
        sa.Column("source_name", sa.String(length=255), nullable=False),
        sa.Column("source_uri", sa.Text(), nullable=False),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("schema_hash", sa.String(length=64), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("coverage_note", sa.Text(), nullable=True),
        sa.Column("freshness_status", source_freshness_status, nullable=False),
        sa.Column("manifest_json", sa.JSON(), nullable=False),
    )
    op.create_index("ix_source_snapshot_source_uri", "source_snapshot", ["source_uri"])

    op.create_table(
        "auth_user",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("external_auth_id", sa.Uuid(), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("auth_provider", sa.String(length=50), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("external_auth_id"),
        sa.UniqueConstraint("email"),
    )

    op.create_table(
        "app_role",
        sa.Column("name", app_role_name, primary_key=True, nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
    )

    op.create_table(
        "user_role",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("auth_user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "role_name",
            app_role_name,
            sa.ForeignKey("app_role.name", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "role_name"),
    )

    op.create_table(
        "audit_event",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "actor_user_id",
            sa.Uuid(),
            sa.ForeignKey("auth_user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("entity_type", sa.String(length=100), nullable=False),
        sa.Column("entity_id", sa.String(length=255), nullable=False),
        sa.Column("before_json", sa.JSON(), nullable=True),
        sa.Column("after_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "job_run",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("job_type", job_type, nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("status", job_status, nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("worker_id", sa.String(length=255), nullable=True),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("requested_by", sa.String(length=255), nullable=True),
    )
    op.create_index("ix_job_run_status_next_run_at", "job_run", ["status", "next_run_at"])

    op.create_table(
        "raw_asset",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "source_snapshot_id",
            sa.Uuid(),
            sa.ForeignKey("source_snapshot.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("asset_type", sa.String(length=50), nullable=False),
        sa.Column("original_url", sa.Text(), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("storage_path"),
    )
    op.create_index("ix_raw_asset_source_snapshot_id", "raw_asset", ["source_snapshot_id"])

    op.bulk_insert(
        sa.table(
            "app_role",
            sa.column("name", app_role_name),
            sa.column("description", sa.String(length=255)),
        ),
        [
            {"name": AppRoleName.ANALYST.value, "description": "Review sites and run assessments."},
            {
                "name": AppRoleName.REVIEWER.value,
                "description": "Sign off cases and resolve review queues.",
            },
            {
                "name": AppRoleName.ADMIN.value,
                "description": "Manage system configuration and role changes.",
            },
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_raw_asset_source_snapshot_id", table_name="raw_asset")
    op.drop_table("raw_asset")
    op.drop_index("ix_job_run_status_next_run_at", table_name="job_run")
    op.drop_table("job_run")
    op.drop_table("audit_event")
    op.drop_table("user_role")
    op.drop_table("app_role")
    op.drop_table("auth_user")
    op.drop_index("ix_source_snapshot_source_uri", table_name="source_snapshot")
    op.drop_table("source_snapshot")

    bind = op.get_bind()
    job_type.drop(bind, checkfirst=True)
    job_status.drop(bind, checkfirst=True)
    app_role_name.drop(bind, checkfirst=True)
    source_freshness_status.drop(bind, checkfirst=True)
