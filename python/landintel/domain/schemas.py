from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field

from landintel.domain.enums import (
    AssessmentRunState,
    BaselinePackStatus,
    CalibrationMethod,
    ComparableOutcome,
    ComplianceMode,
    ConnectorType,
    DocumentExtractionStatus,
    DocumentType,
    EligibilityStatus,
    EstimateQuality,
    EstimateStatus,
    EvidenceImportance,
    EvidencePolarity,
    ExtantPermissionStatus,
    GeomConfidence,
    GeomSourceType,
    GoldSetReviewStatus,
    HistoricalLabelClass,
    HistoricalLabelDecision,
    JobStatus,
    JobType,
    ListingClusterStatus,
    ListingStatus,
    ListingType,
    ModelReleaseStatus,
    PriceBasisType,
    ProposalForm,
    ReleaseChannel,
    ReviewStatus,
    ScenarioSource,
    ScenarioStatus,
    SiteStatus,
    SourceClass,
    SourceCoverageStatus,
    SourceFreshnessStatus,
    SourceParseStatus,
    VerifiedStatus,
)


class ManualUrlIntakeRequest(BaseModel):
    url: AnyHttpUrl
    source_name: str = Field(default="manual_url", min_length=1, max_length=255)
    requested_by: str | None = Field(default=None, max_length=255)


class ConnectorRunRequest(BaseModel):
    requested_by: str | None = Field(default=None, max_length=255)


class JobAcceptedResponse(BaseModel):
    job_id: UUID
    status: JobStatus
    job_type: JobType


class RawAssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    asset_type: str
    original_url: str
    storage_path: str
    mime_type: str
    content_sha256: str
    size_bytes: int
    fetched_at: datetime


class SourceSnapshotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_family: str
    source_name: str
    source_uri: str
    acquired_at: datetime
    effective_from: datetime | None
    effective_to: datetime | None
    schema_hash: str
    content_hash: str
    coverage_note: str | None
    freshness_status: SourceFreshnessStatus
    parse_status: SourceParseStatus
    parse_error_text: str | None
    manifest_json: dict[str, Any]
    raw_assets: list[RawAssetRead]


class JobRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_type: JobType
    status: JobStatus
    attempts: int
    run_at: datetime
    next_run_at: datetime
    locked_at: datetime | None
    worker_id: str | None
    error_text: str | None
    payload_json: dict[str, Any]


class ListingSourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    connector_type: ConnectorType
    compliance_mode: ComplianceMode
    refresh_policy_json: dict[str, Any]
    active: bool
    created_at: datetime


class ListingDocumentRead(BaseModel):
    id: UUID
    asset_id: UUID
    doc_type: DocumentType
    page_count: int | None
    extraction_status: DocumentExtractionStatus
    extracted_text: str | None
    asset: RawAssetRead


class ListingSnapshotRead(BaseModel):
    id: UUID
    source_snapshot_id: UUID
    observed_at: datetime
    headline: str | None
    description_text: str | None
    guide_price_gbp: int | None
    price_basis_type: PriceBasisType
    status: ListingStatus
    auction_date: date | None
    address_text: str | None
    lat: float | None
    lon: float | None
    brochure_asset: RawAssetRead | None
    map_asset: RawAssetRead | None
    raw_record_json: dict[str, Any]


class ListingSummaryRead(BaseModel):
    id: UUID
    source_id: UUID
    source_name: str
    source_listing_id: str
    canonical_url: str
    listing_type: ListingType
    first_seen_at: datetime
    last_seen_at: datetime
    latest_status: ListingStatus
    current_snapshot_id: UUID | None
    current_snapshot: ListingSnapshotRead | None
    normalized_address: str | None
    cluster_id: UUID | None = None
    cluster_status: ListingClusterStatus | None = None
    cluster_confidence: float | None = None


class ListingDetailRead(ListingSummaryRead):
    snapshots: list[ListingSnapshotRead]
    documents: list[ListingDocumentRead]
    source_snapshots: list[SourceSnapshotRead]


class ListingListResponse(BaseModel):
    items: list[ListingSummaryRead]
    total: int


class ListingClusterMemberRead(BaseModel):
    id: UUID
    listing_item_id: UUID
    confidence: float
    rules_json: dict[str, Any]
    created_at: datetime
    listing: ListingSummaryRead


class ListingClusterSummaryRead(BaseModel):
    id: UUID
    cluster_key: str
    cluster_status: ListingClusterStatus
    created_at: datetime
    member_count: int
    members: list[ListingSummaryRead]


class ListingClusterDetailRead(BaseModel):
    id: UUID
    cluster_key: str
    cluster_status: ListingClusterStatus
    created_at: datetime
    members: list[ListingClusterMemberRead]


class ListingClusterListResponse(BaseModel):
    items: list[ListingClusterSummaryRead]
    total: int


class SiteFromClusterRequest(BaseModel):
    requested_by: str | None = Field(default=None, max_length=255)


class SiteGeometryUpdateRequest(BaseModel):
    geom_4326: dict[str, Any]
    source_type: GeomSourceType = GeomSourceType.ANALYST_DRAWN
    confidence: GeomConfidence | None = None
    reason: str | None = Field(default=None, max_length=1000)
    created_by: str | None = Field(default=None, max_length=255)
    raw_asset_id: UUID | None = None


class ExtantPermissionCheckRequest(BaseModel):
    requested_by: str | None = Field(default=None, max_length=255)


class ScenarioSuggestRequest(BaseModel):
    requested_by: str | None = Field(default=None, max_length=255)
    template_keys: list[str] | None = None
    manual_seed: bool = False


class ScenarioConfirmRequest(BaseModel):
    requested_by: str | None = Field(default=None, max_length=255)
    action: str = Field(default="CONFIRM", max_length=50)
    proposal_form: ProposalForm | None = None
    units_assumed: int | None = Field(default=None, ge=1, le=999)
    route_assumed: str | None = Field(default=None, max_length=100)
    height_band_assumed: str | None = Field(default=None, max_length=100)
    net_developable_area_pct: float | None = Field(default=None, ge=0.0, le=1.0)
    housing_mix_assumed_json: dict[str, Any] | None = None
    parking_assumption: str | None = Field(default=None, max_length=1000)
    affordable_housing_assumption: str | None = Field(default=None, max_length=1000)
    access_assumption: str | None = Field(default=None, max_length=1000)
    review_notes: str | None = Field(default=None, max_length=4000)


class SiteWarningRead(BaseModel):
    code: str
    message: str


class SiteGeometryRead(BaseModel):
    geom_4326: dict[str, Any]
    geom_hash: str
    geom_source_type: GeomSourceType
    geom_confidence: GeomConfidence
    site_area_sqm: float


class SiteGeometryRevisionRead(BaseModel):
    id: UUID
    geom_hash: str
    geom_4326: dict[str, Any]
    source_type: GeomSourceType
    confidence: GeomConfidence
    site_area_sqm: float
    reason: str | None
    created_by: str | None
    created_at: datetime
    raw_asset_id: UUID | None
    warnings: list[SiteWarningRead] = Field(default_factory=list)


class SiteLpaLinkRead(BaseModel):
    lpa_id: str
    lpa_name: str
    overlap_pct: float
    overlap_sqm: float
    is_primary: bool


class SiteTitleLinkRead(BaseModel):
    title_number: str
    overlap_pct: float
    overlap_sqm: float
    confidence: GeomConfidence


class SiteMarketEventRead(BaseModel):
    id: UUID
    event_type: str
    event_at: datetime
    price_gbp: int | None
    basis_type: PriceBasisType
    listing_item_id: UUID | None
    notes: str | None


class SiteClusterSummaryRead(BaseModel):
    id: UUID
    cluster_key: str
    cluster_status: ListingClusterStatus
    member_count: int


class SiteListingSummaryRead(BaseModel):
    id: UUID
    headline: str | None
    canonical_url: str
    latest_status: ListingStatus
    guide_price_gbp: int | None
    price_basis_type: PriceBasisType
    address_text: str | None
    source_name: str


class SourceCoverageSnapshotRead(BaseModel):
    id: UUID
    borough_id: str
    source_family: str
    coverage_status: SourceCoverageStatus
    gap_reason: str | None
    freshness_status: SourceFreshnessStatus
    coverage_note: str | None
    source_snapshot_id: UUID | None
    captured_at: datetime


class PlanningApplicationDocumentRead(BaseModel):
    id: UUID
    asset_id: UUID
    doc_type: str
    doc_url: str
    asset: RawAssetRead | None = None


class PlanningApplicationRead(BaseModel):
    id: UUID
    borough_id: str | None
    source_system: str
    source_snapshot_id: UUID
    external_ref: str
    application_type: str
    proposal_description: str
    valid_date: date | None
    decision_date: date | None
    decision: str | None
    decision_type: str | None
    status: str
    route_normalized: str | None
    units_proposed: int | None
    source_priority: int
    source_url: str | None
    site_geom_4326: dict[str, Any] | None
    site_point_4326: dict[str, Any] | None
    raw_record_json: dict[str, Any]
    documents: list[PlanningApplicationDocumentRead] = Field(default_factory=list)


class SitePlanningLinkRead(BaseModel):
    id: UUID
    link_type: str
    distance_m: float | None
    overlap_pct: float | None
    match_confidence: GeomConfidence
    manual_verified: bool
    planning_application: PlanningApplicationRead


class BrownfieldSiteStateRead(BaseModel):
    id: UUID
    borough_id: str
    source_snapshot_id: UUID
    external_ref: str
    part: str
    pip_status: str | None
    tdc_status: str | None
    effective_from: date | None
    effective_to: date | None
    raw_record_id: str
    source_url: str | None


class PolicyAreaRead(BaseModel):
    id: UUID
    borough_id: str | None
    policy_family: str
    policy_code: str
    name: str
    geom_4326: dict[str, Any]
    legal_effective_from: date | None
    legal_effective_to: date | None
    source_snapshot_id: UUID
    source_class: SourceClass
    source_url: str | None


class PlanningConstraintFeatureRead(BaseModel):
    id: UUID
    feature_family: str
    feature_subtype: str
    authority_level: str
    geom_4326: dict[str, Any]
    legal_status: str | None
    effective_from: date | None
    effective_to: date | None
    source_snapshot_id: UUID
    source_class: SourceClass
    source_url: str | None


class SitePolicyFactRead(BaseModel):
    id: UUID
    relation_type: str
    overlap_pct: float | None
    distance_m: float | None
    importance: EvidenceImportance
    policy_area: PolicyAreaRead


class SiteConstraintFactRead(BaseModel):
    id: UUID
    overlap_pct: float | None
    distance_m: float | None
    severity: EvidenceImportance
    constraint_feature: PlanningConstraintFeatureRead


class BoroughRulepackRead(BaseModel):
    id: UUID
    template_key: str
    status: BaselinePackStatus
    freshness_status: SourceFreshnessStatus
    source_snapshot_id: UUID | None
    effective_from: date | None
    effective_to: date | None
    rule_json: dict[str, Any]
    citations_complete: bool = True


class BoroughBaselinePackRead(BaseModel):
    id: UUID
    borough_id: str
    version: str
    status: BaselinePackStatus
    freshness_status: SourceFreshnessStatus
    signed_off_by: str | None
    signed_off_at: datetime | None
    pack_json: dict[str, Any]
    source_snapshot_id: UUID | None
    rulepacks: list[BoroughRulepackRead] = Field(default_factory=list)


class ScenarioTemplateRead(BaseModel):
    id: UUID
    key: str
    version: str
    enabled: bool
    config_json: dict[str, Any]


class ScenarioReasonRead(BaseModel):
    code: str
    message: str
    source_label: str | None = None
    source_url: str | None = None
    source_snapshot_id: UUID | None = None
    raw_asset_id: UUID | None = None


class ScenarioReviewRead(BaseModel):
    id: UUID
    review_status: ScenarioStatus
    review_notes: str | None
    reviewed_by: str | None
    reviewed_at: datetime


class SiteScenarioSummaryRead(BaseModel):
    id: UUID
    site_id: UUID
    template_key: str
    template_version: str
    proposal_form: ProposalForm
    units_assumed: int
    route_assumed: str
    height_band_assumed: str
    net_developable_area_pct: float
    red_line_geom_hash: str
    scenario_source: ScenarioSource
    status: ScenarioStatus
    supersedes_id: UUID | None
    is_current: bool
    is_headline: bool
    heuristic_rank: int | None
    manual_review_required: bool
    stale_reason: str | None
    housing_mix_assumed_json: dict[str, Any] = Field(default_factory=dict)
    parking_assumption: str | None = None
    affordable_housing_assumption: str | None = None
    access_assumption: str | None = None
    reason_codes: list[ScenarioReasonRead] = Field(default_factory=list)
    missing_data_flags: list[str] = Field(default_factory=list)
    warning_codes: list[str] = Field(default_factory=list)


class SiteScenarioDetailRead(SiteScenarioSummaryRead):
    template: ScenarioTemplateRead | None = None
    review_history: list[ScenarioReviewRead] = Field(default_factory=list)
    evidence: EvidencePackRead
    baseline_pack: BoroughBaselinePackRead | None = None
    site_summary: SiteSummaryRead | None = None


class ScenarioExclusionRead(BaseModel):
    template_key: str
    reasons: list[ScenarioReasonRead] = Field(default_factory=list)
    missing_data_flags: list[str] = Field(default_factory=list)
    warning_codes: list[str] = Field(default_factory=list)


class SiteScenarioListResponse(BaseModel):
    items: list[SiteScenarioSummaryRead]
    total: int


class SiteScenarioSuggestResponse(BaseModel):
    site_id: UUID
    headline_scenario_id: UUID | None = None
    items: list[SiteScenarioSummaryRead]
    excluded_templates: list[ScenarioExclusionRead] = Field(default_factory=list)


class ExtantPermissionMatchRead(BaseModel):
    source_kind: str
    source_system: str
    source_label: str
    source_url: str | None
    source_snapshot_id: UUID | None
    planning_application_id: UUID | None = None
    brownfield_state_id: UUID | None = None
    overlap_pct: float | None = None
    overlap_sqm: float | None = None
    distance_m: float | None = None
    material: bool
    detail: str


class ExtantPermissionRead(BaseModel):
    status: ExtantPermissionStatus
    eligibility_status: EligibilityStatus
    manual_review_required: bool
    summary: str
    reasons: list[str] = Field(default_factory=list)
    coverage_gaps: list[SiteWarningRead] = Field(default_factory=list)
    matched_records: list[ExtantPermissionMatchRead] = Field(default_factory=list)


class EvidenceItemRead(BaseModel):
    polarity: EvidencePolarity
    claim_text: str
    topic: str
    importance: EvidenceImportance
    source_class: SourceClass
    source_label: str
    source_url: str | None
    source_snapshot_id: UUID | None
    raw_asset_id: UUID | None
    excerpt_text: str | None
    verified_status: VerifiedStatus


class EvidencePackRead(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    for_: list[EvidenceItemRead] = Field(default_factory=list, alias="for")
    against: list[EvidenceItemRead] = Field(default_factory=list)
    unknown: list[EvidenceItemRead] = Field(default_factory=list)


class SiteSummaryRead(BaseModel):
    id: UUID
    display_name: str
    borough_id: str | None
    borough_name: str | None
    site_status: SiteStatus
    manual_review_required: bool
    warnings: list[SiteWarningRead]
    current_geometry: SiteGeometryRead
    current_listing: SiteListingSummaryRead | None
    listing_cluster: SiteClusterSummaryRead


class SiteDetailRead(SiteSummaryRead):
    geometry_revisions: list[SiteGeometryRevisionRead]
    lpa_links: list[SiteLpaLinkRead]
    title_links: list[SiteTitleLinkRead]
    market_events: list[SiteMarketEventRead]
    source_documents: list[ListingDocumentRead]
    source_snapshots: list[SourceSnapshotRead]
    source_coverage: list[SourceCoverageSnapshotRead] = Field(default_factory=list)
    planning_history: list[SitePlanningLinkRead] = Field(default_factory=list)
    brownfield_states: list[BrownfieldSiteStateRead] = Field(default_factory=list)
    policy_facts: list[SitePolicyFactRead] = Field(default_factory=list)
    constraint_facts: list[SiteConstraintFactRead] = Field(default_factory=list)
    extant_permission: ExtantPermissionRead
    evidence: EvidencePackRead
    baseline_pack: BoroughBaselinePackRead | None = None
    scenarios: list[SiteScenarioSummaryRead] = Field(default_factory=list)


class SiteListResponse(BaseModel):
    items: list[SiteSummaryRead]
    total: int


class PlaceholderResponse(BaseModel):
    detail: str
    surface: str
    spec_phase: str


class AssessmentRequest(BaseModel):
    site_id: UUID
    scenario_id: UUID
    as_of_date: date
    requested_by: str | None = Field(default=None, max_length=255)
    hidden_mode: bool = False


class AssessmentFeatureSnapshotRead(BaseModel):
    id: UUID
    feature_version: str
    feature_hash: str
    feature_json: dict[str, Any]
    coverage_json: dict[str, Any]
    created_at: datetime


class AssessmentResultRead(BaseModel):
    id: UUID
    model_release_id: UUID | None = None
    release_scope_key: str | None = None
    eligibility_status: EligibilityStatus
    estimate_status: EstimateStatus
    review_status: ReviewStatus
    approval_probability_raw: float | None
    approval_probability_display: str | None
    estimate_quality: EstimateQuality | None
    source_coverage_quality: str | None
    geometry_quality: str | None
    support_quality: str | None
    scenario_quality: str | None
    ood_quality: str | None
    ood_status: str | None
    manual_review_required: bool
    result_json: dict[str, Any]
    published_at: datetime | None


class ComparablePlanningApplicationRead(BaseModel):
    id: UUID
    external_ref: str
    borough_id: str | None
    proposal_description: str
    valid_date: date | None
    decision_date: date | None
    decision: str | None
    route_normalized: str | None
    units_proposed: int | None
    source_system: str
    source_url: str | None


class HistoricalLabelSummaryRead(BaseModel):
    id: UUID
    planning_application_id: UUID
    borough_id: str | None
    template_key: str | None
    proposal_form: ProposalForm | None
    route_normalized: str | None
    units_proposed: int | None
    site_area_sqm: float | None
    label_version: str
    label_class: HistoricalLabelClass
    label_decision: HistoricalLabelDecision
    label_reason: str | None
    valid_date: date | None
    first_substantive_decision_date: date | None
    label_window_end: date | None
    source_priority_used: int
    archetype_key: str | None
    designation_profile_json: dict[str, Any]
    provenance_json: dict[str, Any]
    source_snapshot_ids_json: list[str]
    raw_asset_ids_json: list[str]
    review_status: GoldSetReviewStatus
    review_notes: str | None
    reviewed_by: str | None
    reviewed_at: datetime | None
    notable_policy_issues_json: list[str]
    extant_permission_outcome: str | None
    site_geometry_confidence: GeomConfidence | None
    created_at: datetime
    updated_at: datetime


class HistoricalLabelCaseRead(HistoricalLabelSummaryRead):
    planning_application: PlanningApplicationRead


class HistoricalLabelListResponse(BaseModel):
    items: list[HistoricalLabelSummaryRead]
    total: int


class HistoricalLabelReviewRequest(BaseModel):
    review_status: GoldSetReviewStatus
    review_notes: str | None = Field(default=None, max_length=4000)
    notable_policy_issues: list[str] = Field(default_factory=list)
    extant_permission_outcome: str | None = Field(default=None, max_length=100)
    site_geometry_confidence: GeomConfidence | None = None
    reviewed_by: str | None = Field(default=None, max_length=255)


class ComparableCaseMemberRead(BaseModel):
    id: UUID
    planning_application_id: UUID
    similarity_score: float
    outcome: ComparableOutcome
    rank: int
    fallback_path: str
    match_json: dict[str, Any]
    planning_application: ComparablePlanningApplicationRead
    historical_label: HistoricalLabelSummaryRead


class ComparableCaseSetRead(BaseModel):
    id: UUID
    strategy: str
    same_borough_count: int
    london_count: int
    approved_count: int
    refused_count: int
    approved_members: list[ComparableCaseMemberRead] = Field(default_factory=list)
    refused_members: list[ComparableCaseMemberRead] = Field(default_factory=list)


class PredictionLedgerRead(BaseModel):
    id: UUID
    site_geom_hash: str
    feature_hash: str
    model_release_id: UUID | None
    release_scope_key: str | None = None
    calibration_hash: str | None
    response_mode: str
    source_snapshot_ids_json: list[str]
    raw_asset_ids_json: list[str]
    result_payload_hash: str
    response_json: dict[str, Any]
    created_at: datetime


class AssessmentSummaryRead(BaseModel):
    id: UUID
    site_id: UUID
    scenario_id: UUID
    as_of_date: date
    state: AssessmentRunState
    idempotency_key: str
    requested_by: str | None
    started_at: datetime | None
    finished_at: datetime | None
    error_text: str | None
    created_at: datetime
    updated_at: datetime
    estimate_status: EstimateStatus
    eligibility_status: EligibilityStatus
    review_status: ReviewStatus
    manual_review_required: bool
    site_summary: SiteSummaryRead | None = None
    scenario_summary: SiteScenarioSummaryRead | None = None


class AssessmentDetailRead(AssessmentSummaryRead):
    feature_snapshot: AssessmentFeatureSnapshotRead | None = None
    result: AssessmentResultRead | None = None
    evidence: EvidencePackRead
    comparable_case_set: ComparableCaseSetRead | None = None
    prediction_ledger: PredictionLedgerRead | None = None
    note: str


class ActiveReleaseScopeRead(BaseModel):
    id: UUID
    scope_key: str
    template_key: str
    release_channel: ReleaseChannel
    borough_id: str | None
    model_release_id: UUID
    activated_by: str | None
    activated_at: datetime


class ModelReleaseSummaryRead(BaseModel):
    id: UUID
    template_key: str
    release_channel: ReleaseChannel
    scope_key: str
    scope_borough_id: str | None
    status: ModelReleaseStatus
    model_kind: str
    transform_version: str
    feature_version: str
    calibration_method: CalibrationMethod
    support_count: int
    positive_count: int
    negative_count: int
    reason_text: str | None
    activated_by: str | None
    activated_at: datetime | None
    retired_by: str | None
    retired_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ModelReleaseDetailRead(ModelReleaseSummaryRead):
    model_artifact_path: str | None
    model_artifact_hash: str | None
    calibration_artifact_path: str | None
    calibration_artifact_hash: str | None
    validation_artifact_path: str | None
    validation_artifact_hash: str | None
    model_card_path: str | None
    model_card_hash: str | None
    train_window_start: date | None
    train_window_end: date | None
    metrics_json: dict[str, Any]
    manifest_json: dict[str, Any]
    active_scopes: list[ActiveReleaseScopeRead] = Field(default_factory=list)


class ModelReleaseListResponse(BaseModel):
    items: list[ModelReleaseSummaryRead]
    total: int


class ModelReleaseRebuildRequest(BaseModel):
    requested_by: str | None = Field(default=None, max_length=255)
    template_keys: list[str] | None = None
    auto_activate_hidden: bool = False


class ModelReleaseActivateRequest(BaseModel):
    requested_by: str | None = Field(default=None, max_length=255)


class ModelReleaseRetireRequest(BaseModel):
    requested_by: str | None = Field(default=None, max_length=255)


class AssessmentListResponse(BaseModel):
    items: list[AssessmentSummaryRead]
    total: int
