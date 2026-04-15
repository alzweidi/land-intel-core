"""Phase 7A valuation engine and ranking foundation schema."""

import json
from datetime import UTC, date, datetime

import sqlalchemy as sa
from alembic import op
from landintel.domain.enums import (
    JobType,
    MarketLandCompSourceType,
    ProposalForm,
    ValuationQuality,
    ValuationRunState,
)
from landintel.valuation.assumptions import (
    DEFAULT_VALUATION_ASSUMPTION_SET_ID,
    DEFAULT_VALUATION_ASSUMPTION_VERSION,
    default_assumption_payload,
)
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260415_000008"
down_revision = "20260415_000007"
branch_labels = None
depends_on = None

SEEDED_AT = datetime(2026, 4, 15, 12, 0, tzinfo=UTC)


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        proposal_form_ref = postgresql.ENUM(
            ProposalForm,
            name="proposal_form",
            create_type=False,
        )
        valuation_run_state = postgresql.ENUM(
            ValuationRunState,
            name="valuation_run_state",
        )
        valuation_quality = postgresql.ENUM(
            ValuationQuality,
            name="valuation_quality",
        )
        market_land_comp_source_type = postgresql.ENUM(
            MarketLandCompSourceType,
            name="market_land_comp_source_type",
        )
        valuation_run_state_ref = postgresql.ENUM(
            ValuationRunState,
            name="valuation_run_state",
            create_type=False,
        )
        valuation_quality_ref = postgresql.ENUM(
            ValuationQuality,
            name="valuation_quality",
            create_type=False,
        )
        market_land_comp_source_type_ref = postgresql.ENUM(
            MarketLandCompSourceType,
            name="market_land_comp_source_type",
            create_type=False,
        )
    else:
        proposal_form_ref = sa.Enum(ProposalForm, name="proposal_form")
        valuation_run_state = sa.Enum(ValuationRunState, name="valuation_run_state")
        valuation_quality = sa.Enum(ValuationQuality, name="valuation_quality")
        market_land_comp_source_type = sa.Enum(
            MarketLandCompSourceType,
            name="market_land_comp_source_type",
        )
        valuation_run_state_ref = valuation_run_state
        valuation_quality_ref = valuation_quality
        market_land_comp_source_type_ref = market_land_comp_source_type

    if is_postgres:
        for job_type in (
            JobType.VALUATION_DATA_REFRESH.value,
            JobType.VALUATION_RUN_BUILD.value,
        ):
            op.execute(f"ALTER TYPE job_type ADD VALUE IF NOT EXISTS '{job_type}'")

    valuation_run_state.create(bind, checkfirst=True)
    valuation_quality.create(bind, checkfirst=True)
    market_land_comp_source_type.create(bind, checkfirst=True)

    op.create_table(
        "market_sale_comp",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("transaction_ref", sa.String(length=120), nullable=False),
        sa.Column("borough_id", sa.String(length=100), nullable=True),
        sa.Column("source_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("raw_asset_id", sa.Uuid(), nullable=False),
        sa.Column("sale_date", sa.Date(), nullable=False),
        sa.Column("price_gbp", sa.BigInteger(), nullable=False),
        sa.Column("property_type", sa.String(length=50), nullable=False),
        sa.Column("tenure", sa.String(length=50), nullable=True),
        sa.Column("postcode_district", sa.String(length=16), nullable=True),
        sa.Column("address_text", sa.Text(), nullable=True),
        sa.Column("floor_area_sqm", sa.Float(), nullable=True),
        sa.Column("rebased_price_per_sqm_hint", sa.Float(), nullable=True),
        sa.Column("raw_record_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["borough_id"], ["lpa_boundary.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["source_snapshot_id"],
            ["source_snapshot.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["raw_asset_id"], ["raw_asset.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("transaction_ref"),
    )
    op.create_index(
        "ix_market_sale_comp_borough_sale_date",
        "market_sale_comp",
        ["borough_id", "sale_date"],
    )
    op.create_index(
        "ix_market_sale_comp_postcode_district",
        "market_sale_comp",
        ["postcode_district"],
    )

    op.create_table(
        "market_index_series",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("borough_id", sa.String(length=100), nullable=True),
        sa.Column("index_key", sa.String(length=50), nullable=False),
        sa.Column("period_month", sa.Date(), nullable=False),
        sa.Column("index_value", sa.Float(), nullable=False),
        sa.Column("source_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("raw_asset_id", sa.Uuid(), nullable=False),
        sa.Column("raw_record_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["borough_id"], ["lpa_boundary.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["source_snapshot_id"],
            ["source_snapshot.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["raw_asset_id"], ["raw_asset.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("borough_id", "index_key", "period_month"),
    )
    op.create_index(
        "ix_market_index_series_borough_period",
        "market_index_series",
        ["borough_id", "period_month"],
    )

    op.create_table(
        "market_land_comp",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("comp_ref", sa.String(length=120), nullable=False),
        sa.Column("borough_id", sa.String(length=100), nullable=True),
        sa.Column("template_key", sa.String(length=100), nullable=True),
        sa.Column("proposal_form", proposal_form_ref, nullable=True),
        sa.Column("comp_source_type", market_land_comp_source_type_ref, nullable=False),
        sa.Column("evidence_date", sa.Date(), nullable=True),
        sa.Column("unit_count", sa.Integer(), nullable=True),
        sa.Column("site_area_sqm", sa.Float(), nullable=True),
        sa.Column("post_permission_value_low", sa.Float(), nullable=True),
        sa.Column("post_permission_value_mid", sa.Float(), nullable=True),
        sa.Column("post_permission_value_high", sa.Float(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("source_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("raw_asset_id", sa.Uuid(), nullable=False),
        sa.Column("raw_record_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["borough_id"], ["lpa_boundary.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["source_snapshot_id"],
            ["source_snapshot.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["raw_asset_id"], ["raw_asset.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("comp_ref"),
    )
    op.create_index(
        "ix_market_land_comp_borough_template_date",
        "market_land_comp",
        ["borough_id", "template_key", "evidence_date"],
    )
    op.create_index(
        "ix_market_land_comp_source_type",
        "market_land_comp",
        ["comp_source_type"],
    )

    op.create_table(
        "valuation_assumption_set",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("version", sa.String(length=100), nullable=False),
        sa.Column("cost_json", sa.JSON(), nullable=False),
        sa.Column("policy_burden_json", sa.JSON(), nullable=False),
        sa.Column("discount_json", sa.JSON(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("version"),
    )
    op.create_index(
        "ix_valuation_assumption_set_effective_from",
        "valuation_assumption_set",
        ["effective_from"],
    )

    op.create_table(
        "valuation_run",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("assessment_run_id", sa.Uuid(), nullable=False),
        sa.Column("valuation_assumption_set_id", sa.Uuid(), nullable=False),
        sa.Column("state", valuation_run_state_ref, nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["assessment_run_id"],
            ["assessment_run.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["valuation_assumption_set_id"],
            ["valuation_assumption_set.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("assessment_run_id", "valuation_assumption_set_id"),
    )
    op.create_index(
        "ix_valuation_run_assessment_id",
        "valuation_run",
        ["assessment_run_id"],
    )
    op.create_index(
        "ix_valuation_run_assessment_assumptions",
        "valuation_run",
        ["assessment_run_id", "valuation_assumption_set_id"],
    )

    op.create_table(
        "valuation_result",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("valuation_run_id", sa.Uuid(), nullable=False),
        sa.Column("post_permission_value_low", sa.Float(), nullable=True),
        sa.Column("post_permission_value_mid", sa.Float(), nullable=True),
        sa.Column("post_permission_value_high", sa.Float(), nullable=True),
        sa.Column("uplift_low", sa.Float(), nullable=True),
        sa.Column("uplift_mid", sa.Float(), nullable=True),
        sa.Column("uplift_high", sa.Float(), nullable=True),
        sa.Column("expected_uplift_mid", sa.Float(), nullable=True),
        sa.Column("valuation_quality", valuation_quality_ref, nullable=False),
        sa.Column("manual_review_required", sa.Boolean(), nullable=False),
        sa.Column("basis_json", sa.JSON(), nullable=False),
        sa.Column("sense_check_json", sa.JSON(), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["valuation_run_id"],
            ["valuation_run.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("valuation_run_id"),
    )
    op.create_index(
        "ix_valuation_result_run_id",
        "valuation_result",
        ["valuation_run_id"],
    )

    op.add_column(
        "prediction_ledger",
        sa.Column("valuation_run_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_prediction_ledger_valuation_run",
        "prediction_ledger",
        "valuation_run",
        ["valuation_run_id"],
        ["id"],
        ondelete="SET NULL",
    )

    payload = default_assumption_payload()
    op.bulk_insert(
        sa.table(
            "valuation_assumption_set",
            sa.column("id", sa.Uuid()),
            sa.column("version", sa.String()),
            sa.column("cost_json", sa.JSON()),
            sa.column("policy_burden_json", sa.JSON()),
            sa.column("discount_json", sa.JSON()),
            sa.column("effective_from", sa.Date()),
            sa.column("created_at", sa.DateTime(timezone=True)),
        ),
        [
            {
                "id": DEFAULT_VALUATION_ASSUMPTION_SET_ID,
                "version": DEFAULT_VALUATION_ASSUMPTION_VERSION,
                "cost_json": json.loads(json.dumps(payload["cost_json"])),
                "policy_burden_json": json.loads(
                    json.dumps(payload["policy_burden_json"])
                ),
                "discount_json": json.loads(json.dumps(payload["discount_json"])),
                "effective_from": date(2026, 4, 15),
                "created_at": SEEDED_AT,
            }
        ],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_prediction_ledger_valuation_run",
        "prediction_ledger",
        type_="foreignkey",
    )
    op.drop_column("prediction_ledger", "valuation_run_id")

    op.drop_index("ix_valuation_result_run_id", table_name="valuation_result")
    op.drop_table("valuation_result")

    op.drop_index(
        "ix_valuation_run_assessment_assumptions",
        table_name="valuation_run",
    )
    op.drop_index("ix_valuation_run_assessment_id", table_name="valuation_run")
    op.drop_table("valuation_run")

    op.drop_index(
        "ix_valuation_assumption_set_effective_from",
        table_name="valuation_assumption_set",
    )
    op.drop_table("valuation_assumption_set")

    op.drop_index(
        "ix_market_land_comp_source_type",
        table_name="market_land_comp",
    )
    op.drop_index(
        "ix_market_land_comp_borough_template_date",
        table_name="market_land_comp",
    )
    op.drop_table("market_land_comp")

    op.drop_index(
        "ix_market_index_series_borough_period",
        table_name="market_index_series",
    )
    op.drop_table("market_index_series")

    op.drop_index(
        "ix_market_sale_comp_postcode_district",
        table_name="market_sale_comp",
    )
    op.drop_index(
        "ix_market_sale_comp_borough_sale_date",
        table_name="market_sale_comp",
    )
    op.drop_table("market_sale_comp")

    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        op.execute("DROP TYPE IF EXISTS market_land_comp_source_type")
        op.execute("DROP TYPE IF EXISTS valuation_quality")
        op.execute("DROP TYPE IF EXISTS valuation_run_state")
