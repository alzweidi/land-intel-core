"""Phase 5A historical labels and assessment foundation schema."""

import sqlalchemy as sa
from alembic import op
from landintel.domain.enums import (
    AssessmentRunState,
    ComparableOutcome,
    EligibilityStatus,
    EstimateQuality,
    EstimateStatus,
    EvidenceImportance,
    EvidencePolarity,
    GeomConfidence,
    GoldSetReviewStatus,
    HistoricalLabelClass,
    HistoricalLabelDecision,
    JobType,
    ProposalForm,
    ReviewStatus,
    SourceClass,
    VerifiedStatus,
)
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260415_000006"
down_revision = "20260415_000005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        proposal_form_ref = postgresql.ENUM(
            ProposalForm,
            name="proposal_form",
            create_type=False,
        )
        geom_confidence_ref = postgresql.ENUM(
            GeomConfidence,
            name="geom_confidence",
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
        assessment_run_state = postgresql.ENUM(
            AssessmentRunState,
            name="assessment_run_state",
        )
        estimate_status = postgresql.ENUM(EstimateStatus, name="estimate_status")
        review_status = postgresql.ENUM(ReviewStatus, name="review_status")
        estimate_quality = postgresql.ENUM(EstimateQuality, name="estimate_quality")
        historical_label_class = postgresql.ENUM(
            HistoricalLabelClass,
            name="historical_label_class",
        )
        historical_label_decision = postgresql.ENUM(
            HistoricalLabelDecision,
            name="historical_label_decision",
        )
        comparable_outcome = postgresql.ENUM(
            ComparableOutcome,
            name="comparable_outcome",
        )
        gold_set_review_status = postgresql.ENUM(
            GoldSetReviewStatus,
            name="gold_set_review_status",
        )
        evidence_polarity = postgresql.ENUM(EvidencePolarity, name="evidence_polarity")
        verified_status = postgresql.ENUM(VerifiedStatus, name="verified_status")
        eligibility_status = postgresql.ENUM(EligibilityStatus, name="eligibility_status")

        assessment_run_state_ref = postgresql.ENUM(
            AssessmentRunState,
            name="assessment_run_state",
            create_type=False,
        )
        estimate_status_ref = postgresql.ENUM(
            EstimateStatus,
            name="estimate_status",
            create_type=False,
        )
        review_status_ref = postgresql.ENUM(
            ReviewStatus,
            name="review_status",
            create_type=False,
        )
        estimate_quality_ref = postgresql.ENUM(
            EstimateQuality,
            name="estimate_quality",
            create_type=False,
        )
        historical_label_class_ref = postgresql.ENUM(
            HistoricalLabelClass,
            name="historical_label_class",
            create_type=False,
        )
        historical_label_decision_ref = postgresql.ENUM(
            HistoricalLabelDecision,
            name="historical_label_decision",
            create_type=False,
        )
        comparable_outcome_ref = postgresql.ENUM(
            ComparableOutcome,
            name="comparable_outcome",
            create_type=False,
        )
        gold_set_review_status_ref = postgresql.ENUM(
            GoldSetReviewStatus,
            name="gold_set_review_status",
            create_type=False,
        )
        evidence_polarity_ref = postgresql.ENUM(
            EvidencePolarity,
            name="evidence_polarity",
            create_type=False,
        )
        verified_status_ref = postgresql.ENUM(
            VerifiedStatus,
            name="verified_status",
            create_type=False,
        )
        eligibility_status_ref = postgresql.ENUM(
            EligibilityStatus,
            name="eligibility_status",
            create_type=False,
        )
    else:
        proposal_form_ref = sa.Enum(ProposalForm, name="proposal_form")
        geom_confidence_ref = sa.Enum(GeomConfidence, name="geom_confidence")
        source_class_ref = sa.Enum(SourceClass, name="source_class")
        evidence_importance_ref = sa.Enum(EvidenceImportance, name="evidence_importance")
        assessment_run_state = sa.Enum(AssessmentRunState, name="assessment_run_state")
        estimate_status = sa.Enum(EstimateStatus, name="estimate_status")
        review_status = sa.Enum(ReviewStatus, name="review_status")
        estimate_quality = sa.Enum(EstimateQuality, name="estimate_quality")
        historical_label_class = sa.Enum(
            HistoricalLabelClass,
            name="historical_label_class",
        )
        historical_label_decision = sa.Enum(
            HistoricalLabelDecision,
            name="historical_label_decision",
        )
        comparable_outcome = sa.Enum(ComparableOutcome, name="comparable_outcome")
        gold_set_review_status = sa.Enum(
            GoldSetReviewStatus,
            name="gold_set_review_status",
        )
        evidence_polarity = sa.Enum(EvidencePolarity, name="evidence_polarity")
        verified_status = sa.Enum(VerifiedStatus, name="verified_status")
        eligibility_status = sa.Enum(EligibilityStatus, name="eligibility_status")

        assessment_run_state_ref = assessment_run_state
        estimate_status_ref = estimate_status
        review_status_ref = review_status
        estimate_quality_ref = estimate_quality
        historical_label_class_ref = historical_label_class
        historical_label_decision_ref = historical_label_decision
        comparable_outcome_ref = comparable_outcome
        gold_set_review_status_ref = gold_set_review_status
        evidence_polarity_ref = evidence_polarity
        verified_status_ref = verified_status
        eligibility_status_ref = eligibility_status

    if is_postgres:
        for job_type in (
            JobType.HISTORICAL_LABEL_REBUILD.value,
            JobType.ASSESSMENT_FEATURE_SNAPSHOT_BUILD.value,
            JobType.COMPARABLE_RETRIEVAL_BUILD.value,
            JobType.REPLAY_VERIFICATION_BATCH.value,
            JobType.GOLD_SET_REFRESH.value,
        ):
            op.execute(f"ALTER TYPE job_type ADD VALUE IF NOT EXISTS '{job_type}'")

    assessment_run_state.create(bind, checkfirst=True)
    estimate_status.create(bind, checkfirst=True)
    review_status.create(bind, checkfirst=True)
    estimate_quality.create(bind, checkfirst=True)
    historical_label_class.create(bind, checkfirst=True)
    historical_label_decision.create(bind, checkfirst=True)
    comparable_outcome.create(bind, checkfirst=True)
    gold_set_review_status.create(bind, checkfirst=True)
    evidence_polarity.create(bind, checkfirst=True)
    verified_status.create(bind, checkfirst=True)
    eligibility_status.create(bind, checkfirst=True)

    op.create_table(
        "historical_case_label",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "planning_application_id",
            sa.Uuid(),
            sa.ForeignKey("planning_application.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("borough_id", sa.String(length=100), nullable=True),
        sa.Column("template_key", sa.String(length=100), nullable=True),
        sa.Column("proposal_form", proposal_form_ref, nullable=True),
        sa.Column("route_normalized", sa.String(length=100), nullable=True),
        sa.Column("units_proposed", sa.Integer(), nullable=True),
        sa.Column("site_area_sqm", sa.Float(), nullable=True),
        sa.Column("label_version", sa.String(length=100), nullable=False),
        sa.Column("label_class", historical_label_class_ref, nullable=False),
        sa.Column("label_decision", historical_label_decision_ref, nullable=False),
        sa.Column("label_reason", sa.Text(), nullable=True),
        sa.Column("valid_date", sa.Date(), nullable=True),
        sa.Column("first_substantive_decision_date", sa.Date(), nullable=True),
        sa.Column("label_window_end", sa.Date(), nullable=True),
        sa.Column("source_priority_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("archetype_key", sa.String(length=255), nullable=True),
        sa.Column(
            "designation_profile_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "provenance_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "source_snapshot_ids_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "raw_asset_ids_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column("review_status", gold_set_review_status_ref, nullable=False),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("reviewed_by", sa.String(length=255), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "notable_policy_issues_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column("extant_permission_outcome", sa.String(length=100), nullable=True),
        sa.Column("site_geometry_confidence", geom_confidence_ref, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("planning_application_id", "label_version"),
    )
    op.create_index(
        "ix_historical_case_label_borough_template_class",
        "historical_case_label",
        ["borough_id", "template_key", "label_class"],
    )
    op.create_index(
        "ix_historical_case_label_review_status",
        "historical_case_label",
        ["review_status"],
    )
    op.create_index(
        "ix_historical_case_label_decision_date",
        "historical_case_label",
        ["first_substantive_decision_date"],
    )
    op.create_index(
        "ix_historical_case_label_valid_date",
        "historical_case_label",
        ["valid_date"],
    )

    op.create_table(
        "assessment_run",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "site_id",
            sa.Uuid(),
            sa.ForeignKey("site_candidate.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "scenario_id",
            sa.Uuid(),
            sa.ForeignKey("site_scenario.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("state", assessment_run_state_ref, nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("requested_by", sa.String(length=255), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index("ix_assessment_run_state", "assessment_run", ["state"])
    op.create_index(
        "ix_assessment_run_site_as_of_date",
        "assessment_run",
        ["site_id", "as_of_date"],
    )
    op.create_index(
        "ix_assessment_run_scenario_as_of_date",
        "assessment_run",
        ["scenario_id", "as_of_date"],
    )

    op.create_table(
        "assessment_feature_snapshot",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "assessment_run_id",
            sa.Uuid(),
            sa.ForeignKey("assessment_run.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("feature_version", sa.String(length=100), nullable=False),
        sa.Column("feature_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "feature_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "coverage_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("assessment_run_id"),
    )
    op.create_index(
        "ix_assessment_feature_snapshot_run_id",
        "assessment_feature_snapshot",
        ["assessment_run_id"],
    )

    op.create_table(
        "assessment_result",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "assessment_run_id",
            sa.Uuid(),
            sa.ForeignKey("assessment_run.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("model_release_id", sa.Uuid(), nullable=True),
        sa.Column("eligibility_status", eligibility_status_ref, nullable=False),
        sa.Column("estimate_status", estimate_status_ref, nullable=False),
        sa.Column("review_status", review_status_ref, nullable=False),
        sa.Column("approval_probability_raw", sa.Float(), nullable=True),
        sa.Column("approval_probability_display", sa.String(length=32), nullable=True),
        sa.Column("estimate_quality", estimate_quality_ref, nullable=True),
        sa.Column("source_coverage_quality", sa.String(length=32), nullable=True),
        sa.Column("geometry_quality", sa.String(length=32), nullable=True),
        sa.Column("support_quality", sa.String(length=32), nullable=True),
        sa.Column("ood_status", sa.String(length=32), nullable=True),
        sa.Column("manual_review_required", sa.Boolean(), nullable=False),
        sa.Column(
            "result_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("assessment_run_id"),
    )
    op.create_index("ix_assessment_result_run_id", "assessment_result", ["assessment_run_id"])

    op.create_table(
        "comparable_case_set",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "assessment_run_id",
            sa.Uuid(),
            sa.ForeignKey("assessment_run.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("strategy", sa.String(length=100), nullable=False),
        sa.Column("same_borough_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("london_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("approved_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("refused_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("assessment_run_id"),
    )
    op.create_index(
        "ix_comparable_case_set_run_id",
        "comparable_case_set",
        ["assessment_run_id"],
    )

    op.create_table(
        "comparable_case_member",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "comparable_case_set_id",
            sa.Uuid(),
            sa.ForeignKey("comparable_case_set.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "planning_application_id",
            sa.Uuid(),
            sa.ForeignKey("planning_application.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("similarity_score", sa.Float(), nullable=False),
        sa.Column("outcome", comparable_outcome_ref, nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("fallback_path", sa.String(length=100), nullable=False),
        sa.Column(
            "match_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_comparable_case_member_set_outcome_rank",
        "comparable_case_member",
        ["comparable_case_set_id", "outcome", "rank"],
    )

    op.create_table(
        "evidence_item",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "assessment_run_id",
            sa.Uuid(),
            sa.ForeignKey("assessment_run.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("polarity", evidence_polarity_ref, nullable=False),
        sa.Column("topic", sa.String(length=100), nullable=False),
        sa.Column("claim_text", sa.Text(), nullable=False),
        sa.Column("importance", evidence_importance_ref, nullable=False),
        sa.Column("source_class", source_class_ref, nullable=False),
        sa.Column("source_label", sa.String(length=255), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("source_snapshot_id", sa.Uuid(), nullable=True),
        sa.Column("raw_asset_id", sa.Uuid(), nullable=True),
        sa.Column("excerpt_text", sa.Text(), nullable=True),
        sa.Column("verified_status", verified_status_ref, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_evidence_item_run_polarity",
        "evidence_item",
        ["assessment_run_id", "polarity"],
    )

    op.create_table(
        "prediction_ledger",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "assessment_run_id",
            sa.Uuid(),
            sa.ForeignKey("assessment_run.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("site_geom_hash", sa.String(length=64), nullable=False),
        sa.Column("feature_hash", sa.String(length=64), nullable=False),
        sa.Column("model_release_id", sa.Uuid(), nullable=True),
        sa.Column("calibration_hash", sa.String(length=64), nullable=True),
        sa.Column(
            "source_snapshot_ids_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "raw_asset_ids_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column("result_payload_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "response_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("assessment_run_id"),
    )
    op.create_index("ix_prediction_ledger_run_id", "prediction_ledger", ["assessment_run_id"])

    if is_postgres:
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_planning_application_proposal_description_fts
            ON planning_application
            USING GIN (to_tsvector('english', coalesce(proposal_description, '')))
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        assessment_run_state = postgresql.ENUM(
            AssessmentRunState,
            name="assessment_run_state",
        )
        estimate_status = postgresql.ENUM(EstimateStatus, name="estimate_status")
        review_status = postgresql.ENUM(ReviewStatus, name="review_status")
        estimate_quality = postgresql.ENUM(EstimateQuality, name="estimate_quality")
        historical_label_class = postgresql.ENUM(
            HistoricalLabelClass,
            name="historical_label_class",
        )
        historical_label_decision = postgresql.ENUM(
            HistoricalLabelDecision,
            name="historical_label_decision",
        )
        comparable_outcome = postgresql.ENUM(
            ComparableOutcome,
            name="comparable_outcome",
        )
        gold_set_review_status = postgresql.ENUM(
            GoldSetReviewStatus,
            name="gold_set_review_status",
        )
        evidence_polarity = postgresql.ENUM(EvidencePolarity, name="evidence_polarity")
        verified_status = postgresql.ENUM(VerifiedStatus, name="verified_status")
        eligibility_status = postgresql.ENUM(EligibilityStatus, name="eligibility_status")
    else:
        assessment_run_state = sa.Enum(AssessmentRunState, name="assessment_run_state")
        estimate_status = sa.Enum(EstimateStatus, name="estimate_status")
        review_status = sa.Enum(ReviewStatus, name="review_status")
        estimate_quality = sa.Enum(EstimateQuality, name="estimate_quality")
        historical_label_class = sa.Enum(
            HistoricalLabelClass,
            name="historical_label_class",
        )
        historical_label_decision = sa.Enum(
            HistoricalLabelDecision,
            name="historical_label_decision",
        )
        comparable_outcome = sa.Enum(ComparableOutcome, name="comparable_outcome")
        gold_set_review_status = sa.Enum(
            GoldSetReviewStatus,
            name="gold_set_review_status",
        )
        evidence_polarity = sa.Enum(EvidencePolarity, name="evidence_polarity")
        verified_status = sa.Enum(VerifiedStatus, name="verified_status")
        eligibility_status = sa.Enum(EligibilityStatus, name="eligibility_status")

    if is_postgres:
        op.execute("DROP INDEX IF EXISTS ix_planning_application_proposal_description_fts")

    op.drop_index("ix_prediction_ledger_run_id", table_name="prediction_ledger")
    op.drop_table("prediction_ledger")
    op.drop_index("ix_evidence_item_run_polarity", table_name="evidence_item")
    op.drop_table("evidence_item")
    op.drop_index(
        "ix_comparable_case_member_set_outcome_rank",
        table_name="comparable_case_member",
    )
    op.drop_table("comparable_case_member")
    op.drop_index("ix_comparable_case_set_run_id", table_name="comparable_case_set")
    op.drop_table("comparable_case_set")
    op.drop_index("ix_assessment_result_run_id", table_name="assessment_result")
    op.drop_table("assessment_result")
    op.drop_index(
        "ix_assessment_feature_snapshot_run_id",
        table_name="assessment_feature_snapshot",
    )
    op.drop_table("assessment_feature_snapshot")
    op.drop_index("ix_assessment_run_scenario_as_of_date", table_name="assessment_run")
    op.drop_index("ix_assessment_run_site_as_of_date", table_name="assessment_run")
    op.drop_index("ix_assessment_run_state", table_name="assessment_run")
    op.drop_table("assessment_run")
    op.drop_index(
        "ix_historical_case_label_valid_date",
        table_name="historical_case_label",
    )
    op.drop_index(
        "ix_historical_case_label_decision_date",
        table_name="historical_case_label",
    )
    op.drop_index(
        "ix_historical_case_label_review_status",
        table_name="historical_case_label",
    )
    op.drop_index(
        "ix_historical_case_label_borough_template_class",
        table_name="historical_case_label",
    )
    op.drop_table("historical_case_label")

    assessment_run_state.drop(bind, checkfirst=True)
    estimate_status.drop(bind, checkfirst=True)
    review_status.drop(bind, checkfirst=True)
    estimate_quality.drop(bind, checkfirst=True)
    historical_label_class.drop(bind, checkfirst=True)
    historical_label_decision.drop(bind, checkfirst=True)
    comparable_outcome.drop(bind, checkfirst=True)
    gold_set_review_status.drop(bind, checkfirst=True)
    evidence_polarity.drop(bind, checkfirst=True)
    verified_status.drop(bind, checkfirst=True)
    eligibility_status.drop(bind, checkfirst=True)
