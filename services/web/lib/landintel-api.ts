import {
  getPhase1AClusterById,
  getPhase1AListingById,
  phase1AListings,
  phase1ARuns,
  phase1ASources,
  type Phase1AClusterDetail,
  type Phase1AClusterSummary,
  type Phase1ADocument,
  type Phase1AListingDetail,
  type Phase1AListingSnapshot,
  type Phase1AListingSummary,
  type Phase1ARunRecord,
  type Phase1ASource
} from '@/lib/phase1a-data';
import {
  applyLocalSiteGeometry,
  getPhase2SiteById,
  phase2SiteSummaries
} from '@/lib/phase2-data';

const API_BASE_URL =
  typeof window === 'undefined'
    ? process.env.INTERNAL_API_BASE_URL ??
      process.env.NEXT_PUBLIC_API_BASE_URL ??
      'http://localhost:8000'
    : '';
const REQUEST_TIMEOUT_MS = 2500;

type QueryValue = string | number | boolean | null | undefined;

type ListingsQuery = {
  q?: string;
  source?: string;
  status?: string;
  type?: string;
  cluster?: string;
};

export type GeometrySourceType =
  | 'SOURCE_POLYGON'
  | 'SOURCE_MAP_DIGITISED'
  | 'TITLE_UNION'
  | 'ANALYST_DRAWN'
  | 'APPROXIMATE_BBOX'
  | 'POINT_ONLY';

export type GeometryConfidence = 'HIGH' | 'MEDIUM' | 'LOW' | 'INSUFFICIENT';

export type GeometryPolygon = {
  type: 'Polygon';
  coordinates: number[][][];
};

export type GeometryPoint = {
  type: 'Point';
  coordinates: [number, number];
};

export type GeometryMultiPolygon = {
  type: 'MultiPolygon';
  coordinates: number[][][][];
};

export type GeometryShape = GeometryPoint | GeometryPolygon | GeometryMultiPolygon;

export type GeometryFeature = {
  type: 'Feature';
  geometry: GeometryShape;
  properties: Record<string, unknown>;
};

export type SiteDocument = {
  id: string;
  label: string;
  doc_type: 'source_snapshot' | 'raw_asset' | 'html_snapshot' | 'brochure_pdf';
  href: string;
  asset_id: string | null;
  mime_type: string;
  extraction_status: string | null;
  note: string;
};

export type SiteTitleLink = {
  title_ref: string;
  title_number: string;
  address_text: string;
  overlap_sqm: number | null;
  overlap_pct: number | null;
  confidence: GeometryConfidence;
  is_primary: boolean;
  indicative_only: boolean;
  evidence_note: string;
};

export type SiteLpaLink = {
  lpa_code: string;
  lpa_name: string;
  overlap_sqm: number | null;
  overlap_pct: number | null;
  controlling: boolean;
  manual_clip_required: boolean;
  cross_lpa_flag: boolean;
  note: string;
};

export type SiteMarketEvent = {
  event_id: string;
  event_type: string;
  event_at: string;
  price_gbp: number | null;
  price_basis_type: string | null;
  note: string;
  source_listing_id: string | null;
};

export type SiteRevision = {
  revision_id: string;
  created_at: string;
  created_by: string;
  geom_source_type: GeometrySourceType;
  geom_confidence: GeometryConfidence;
  geom_hash: string;
  site_area_sqm: number | null;
  note: string;
  is_current: boolean;
  geometry_geojson_4326: GeometryFeature;
};

export type SiteSummary = {
  site_id: string;
  display_name: string;
  cluster_id: string;
  cluster_key: string;
  borough_name: string;
  controlling_lpa_name: string;
  geometry_source_type: GeometrySourceType;
  geometry_confidence: GeometryConfidence;
  site_area_sqm: number | null;
  current_listing_id: string;
  current_listing_headline: string;
  current_price_gbp: number | null;
  current_price_basis_type: string | null;
  warnings: string[];
  review_flags: string[];
  revision_count: number;
  document_count: number;
  title_link_count: number;
  lpa_link_count: number;
  geometry_geojson_4326: GeometryFeature;
  centroid_4326: {
    lat: number;
    lon: number;
  };
};

export type SiteDetail = SiteSummary & {
  address_text: string;
  summary: string;
  description_text: string;
  source_snapshot_id: string;
  source_snapshot_url: string | null;
  current_listing: {
    id: string;
    headline: string;
    source_key: string;
    canonical_url: string;
    latest_status: string;
    parse_status: string;
    price_display: string;
    observed_at: string;
  };
  revision_history: SiteRevision[];
  title_links: SiteTitleLink[];
  lpa_links: SiteLpaLink[];
  documents: SiteDocument[];
  market_events: SiteMarketEvent[];
  source_snapshots?: Array<{
    id: string;
    source_family: string;
    source_name: string;
    source_uri: string;
    acquired_at: string;
  }>;
  geometry_editor_guidance: string;
  last_updated_at: string;
  source_coverage?: SourceCoverageRecord[];
  planning_history?: PlanningHistoryRecord[];
  brownfield_states?: BrownfieldStateRecord[];
  policy_facts?: PolicyFactRecord[];
  constraint_facts?: ConstraintFactRecord[];
  extant_permission?: ExtantPermissionRecord | null;
  evidence?: EvidencePack | null;
  baseline_pack?: BaselinePackRecord | null;
  scenarios?: ScenarioSummary[];
};

export type SourceCoverageRecord = {
  id: string;
  borough_id: string;
  source_family: string;
  coverage_status: string;
  gap_reason: string | null;
  freshness_status: string;
  coverage_note: string | null;
  source_snapshot_id: string | null;
  captured_at: string;
};

export type PlanningDocument = {
  id: string;
  doc_type: string;
  doc_url: string;
  asset_id: string | null;
};

export type PlanningHistoryRecord = {
  id: string;
  link_type: string;
  distance_m: number | null;
  overlap_pct: number | null;
  match_confidence: GeometryConfidence;
  manual_verified: boolean;
  planning_application: {
    id: string;
    borough_id: string | null;
    source_system: string;
    source_snapshot_id: string;
    external_ref: string;
    application_type: string;
    proposal_description: string;
    valid_date: string | null;
    decision_date: string | null;
    decision: string | null;
    decision_type: string | null;
    status: string;
    route_normalized: string | null;
    units_proposed: number | null;
    source_priority: number;
    source_url: string | null;
    site_geom_4326: GeometryFeature | null;
    site_point_4326: GeometryFeature | null;
    documents: PlanningDocument[];
  };
};

export type BrownfieldStateRecord = {
  id: string;
  borough_id: string;
  source_snapshot_id: string;
  external_ref: string;
  part: string;
  pip_status: string | null;
  tdc_status: string | null;
  effective_from: string | null;
  effective_to: string | null;
  raw_record_id: string;
  source_url: string | null;
};

export type PolicyFactRecord = {
  id: string;
  relation_type: string;
  overlap_pct: number | null;
  distance_m: number | null;
  importance: string;
  policy_area: {
    id: string;
    borough_id: string | null;
    policy_family: string;
    policy_code: string;
    name: string;
    geom_4326: GeometryFeature;
    source_class: string;
    source_url: string | null;
  };
};

export type ConstraintFactRecord = {
  id: string;
  overlap_pct: number | null;
  distance_m: number | null;
  severity: string;
  constraint_feature: {
    id: string;
    feature_family: string;
    feature_subtype: string;
    authority_level: string;
    geom_4326: GeometryFeature;
    legal_status: string | null;
    source_class: string;
    source_url: string | null;
  };
};

export type ExtantPermissionRecord = {
  status: string;
  eligibility_status: string;
  manual_review_required: boolean;
  summary: string;
  reasons: string[];
  coverage_gaps: Array<{ code: string; message: string }>;
  matched_records: Array<{
    source_kind: string;
    source_system: string;
    source_label: string;
    source_url: string | null;
    source_snapshot_id: string | null;
    planning_application_id: string | null;
    brownfield_state_id: string | null;
    overlap_pct: number | null;
    overlap_sqm: number | null;
    distance_m: number | null;
    material: boolean;
    detail: string;
  }>;
};

export type EvidenceItem = {
  polarity: 'FOR' | 'AGAINST' | 'UNKNOWN';
  claim_text: string;
  topic: string;
  importance: string;
  source_class: string;
  source_label: string;
  source_url: string | null;
  source_snapshot_id: string | null;
  raw_asset_id: string | null;
  excerpt_text: string | null;
  verified_status: string;
};

export type EvidencePack = {
  for: EvidenceItem[];
  against: EvidenceItem[];
  unknown: EvidenceItem[];
};

export type BaselinePackRecord = {
  id: string;
  borough_id: string;
  version: string;
  status: string;
  freshness_status: string;
  signed_off_by: string | null;
  signed_off_at: string | null;
  pack_json: Record<string, unknown>;
  source_snapshot_id: string | null;
  rulepacks: Array<{
    id: string;
    template_key: string;
    status: string;
    freshness_status: string;
    source_snapshot_id: string | null;
    citations_complete: boolean;
    effective_from: string | null;
    effective_to: string | null;
    rule_json: Record<string, unknown>;
  }>;
};

export type ScenarioStatus =
  | 'SUGGESTED'
  | 'AUTO_CONFIRMED'
  | 'ANALYST_CONFIRMED'
  | 'ANALYST_REQUIRED'
  | 'REJECTED'
  | 'OUT_OF_SCOPE';

export type ScenarioSource = 'AUTO' | 'ANALYST' | 'IMPORTED';

export type ProposalForm =
  | 'INFILL'
  | 'REDEVELOPMENT'
  | 'BROWNFIELD_REUSE'
  | 'BACKLAND'
  | 'AIRSPACE';

export type ScenarioReason = {
  code: string;
  message: string;
  source_label: string | null;
  source_url: string | null;
  source_snapshot_id: string | null;
  raw_asset_id: string | null;
};

export type ScenarioReview = {
  id: string;
  review_status: ScenarioStatus;
  review_notes: string | null;
  reviewed_by: string | null;
  reviewed_at: string;
};

export type ScenarioSummary = {
  id: string;
  site_id: string;
  template_key: string;
  template_version: string;
  proposal_form: ProposalForm;
  units_assumed: number;
  route_assumed: string;
  height_band_assumed: string;
  net_developable_area_pct: number;
  red_line_geom_hash: string;
  scenario_source: ScenarioSource;
  status: ScenarioStatus;
  supersedes_id: string | null;
  is_current: boolean;
  is_headline: boolean;
  heuristic_rank: number | null;
  manual_review_required: boolean;
  stale_reason: string | null;
  housing_mix_assumed_json: Record<string, unknown>;
  parking_assumption: string | null;
  affordable_housing_assumption: string | null;
  access_assumption: string | null;
  reason_codes: ScenarioReason[];
  missing_data_flags: string[];
  warning_codes: string[];
};

export type ScenarioDetail = ScenarioSummary & {
  template: {
    id: string;
    key: string;
    version: string;
    enabled: boolean;
    config_json: Record<string, unknown>;
  } | null;
  review_history: ScenarioReview[];
  evidence: EvidencePack | null;
  baseline_pack: BaselinePackRecord | null;
  site_summary: SiteSummary | null;
};

export type ScenarioExclusion = {
  template_key: string;
  reasons: ScenarioReason[];
  missing_data_flags: string[];
  warning_codes: string[];
};

export type ScenarioSuggestResponse = {
  site_id: string;
  headline_scenario_id: string | null;
  items: ScenarioSummary[];
  excluded_templates: ScenarioExclusion[];
};

export type ScenarioSuggestInput = {
  requested_by?: string;
  template_keys?: string[];
  manual_seed?: boolean;
};

export type ScenarioConfirmInput = {
  requested_by?: string;
  action?: 'CONFIRM' | 'REJECT';
  proposal_form?: ProposalForm;
  units_assumed?: number;
  route_assumed?: string;
  height_band_assumed?: string;
  net_developable_area_pct?: number;
  housing_mix_assumed_json?: Record<string, unknown>;
  parking_assumption?: string;
  affordable_housing_assumption?: string;
  access_assumption?: string;
  review_notes?: string;
};

export type SitesQuery = {
  q?: string;
  borough?: string;
  confidence?: GeometryConfidence | '';
  cluster?: string;
};

export type SiteGeometrySaveInput = {
  geometry_geojson_4326: GeometryFeature;
  geom_source_type: GeometrySourceType;
  geom_confidence: GeometryConfidence;
  revision_note?: string;
};

export type AssessmentQuery = {
  site_id?: string;
  scenario_id?: string;
};

export type AppRole = 'analyst' | 'reviewer' | 'admin';

export type VisibilityMode = 'DISABLED' | 'HIDDEN_ONLY' | 'VISIBLE_REVIEWER_ONLY';

export type AssessmentOverrideType =
  | 'ACQUISITION_BASIS'
  | 'VALUATION_ASSUMPTION_SET'
  | 'REVIEW_DISPOSITION'
  | 'RANKING_SUPPRESSION';

export type AssessmentOverrideStatus = 'ACTIVE' | 'RESOLVED' | 'SUPERSEDED';

export type IncidentStatus = 'OPEN' | 'RESOLVED';

export type AuditExportStatus = 'READY' | 'FAILED';

export type OpportunitiesQuery = {
  borough?: string;
  probability_band?: 'Band A' | 'Band B' | 'Band C' | 'Band D' | 'Hold' | '';
  valuation_quality?: 'HIGH' | 'MEDIUM' | 'LOW' | '';
  manual_review_required?: boolean;
  auction_deadline_days?: number;
  min_price?: number;
  max_price?: number;
};

export type AssessmentFeatureSnapshot = {
  id: string;
  feature_version: string;
  feature_hash: string;
  feature_json: Record<string, unknown>;
  coverage_json: Record<string, unknown>;
  created_at: string;
};

export type AssessmentResultJson = {
  explanation?: Record<string, unknown> | null;
  score_execution_reason?: string | null;
};

export type AssessmentResult = {
  id: string;
  model_release_id: string | null;
  release_scope_key: string | null;
  eligibility_status: string;
  estimate_status: string;
  review_status: string;
  approval_probability_raw: number | null;
  approval_probability_display: string | null;
  estimate_quality: string | null;
  source_coverage_quality: string | null;
  geometry_quality: string | null;
  support_quality: string | null;
  scenario_quality: string | null;
  ood_quality: string | null;
  ood_status: string | null;
  manual_review_required: boolean;
  result_json: AssessmentResultJson;
  published_at: string | null;
};

export type ValuationResult = {
  id: string;
  valuation_run_id: string;
  valuation_assumption_set_id: string;
  valuation_assumption_version: string;
  post_permission_value_low: number | null;
  post_permission_value_mid: number | null;
  post_permission_value_high: number | null;
  uplift_low: number | null;
  uplift_mid: number | null;
  uplift_high: number | null;
  expected_uplift_mid: number | null;
  valuation_quality: 'HIGH' | 'MEDIUM' | 'LOW';
  manual_review_required: boolean;
  basis_json: Record<string, unknown>;
  sense_check_json: Record<string, unknown>;
  result_json: Record<string, unknown>;
  payload_hash: string;
  created_at: string;
};

export type ComparablePlanningApplication = {
  id: string;
  external_ref: string;
  borough_id: string | null;
  proposal_description: string;
  valid_date: string | null;
  decision_date: string | null;
  decision: string | null;
  route_normalized: string | null;
  units_proposed: number | null;
  source_system: string;
  source_url: string | null;
};

export type HistoricalLabelSummary = {
  id: string;
  planning_application_id: string;
  borough_id: string | null;
  template_key: string | null;
  proposal_form: ProposalForm | null;
  route_normalized: string | null;
  units_proposed: number | null;
  site_area_sqm: number | null;
  label_version: string;
  label_class: string;
  label_decision: string;
  label_reason: string | null;
  valid_date: string | null;
  first_substantive_decision_date: string | null;
  label_window_end: string | null;
  source_priority_used: number;
  archetype_key: string | null;
  designation_profile_json: Record<string, unknown>;
  provenance_json: Record<string, unknown>;
  source_snapshot_ids_json: string[];
  raw_asset_ids_json: string[];
  review_status: string;
  review_notes: string | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  notable_policy_issues_json: string[];
  extant_permission_outcome: string | null;
  site_geometry_confidence: GeometryConfidence | null;
  created_at: string;
  updated_at: string;
};

export type GoldSetPlanningApplication = {
  id: string;
  borough_id: string | null;
  source_system: string;
  source_snapshot_id: string;
  external_ref: string;
  application_type: string;
  proposal_description: string;
  valid_date: string | null;
  decision_date: string | null;
  decision: string | null;
  decision_type: string | null;
  status: string;
  route_normalized: string | null;
  units_proposed: number | null;
  source_priority: number;
  source_url: string | null;
  site_geom_4326: GeometryFeature | null;
  site_point_4326: GeometryFeature | null;
  documents: PlanningDocument[];
  raw_record_json: Record<string, unknown>;
};

export type HistoricalLabelCase = HistoricalLabelSummary & {
  planning_application: GoldSetPlanningApplication;
};

export type ComparableCaseMember = {
  id: string;
  planning_application_id: string;
  similarity_score: number;
  outcome: 'APPROVED' | 'REFUSED';
  rank: number;
  fallback_path: string;
  match_json: Record<string, unknown>;
  planning_application: ComparablePlanningApplication;
  historical_label: HistoricalLabelSummary;
};

export type ComparableCaseSet = {
  id: string;
  strategy: string;
  same_borough_count: number;
  london_count: number;
  approved_count: number;
  refused_count: number;
  approved_members: ComparableCaseMember[];
  refused_members: ComparableCaseMember[];
};

export type PredictionLedger = {
  id: string;
  site_geom_hash: string;
  feature_hash: string;
  model_release_id: string | null;
  release_scope_key: string | null;
  calibration_hash: string | null;
  model_artifact_hash: string | null;
  validation_artifact_hash: string | null;
  response_mode: string;
  source_snapshot_ids_json: string[];
  raw_asset_ids_json: string[];
  result_payload_hash: string;
  response_json: Record<string, unknown>;
  replay_verification_status: string;
  replay_verified_at: string | null;
  replay_verification_note: string | null;
  created_at: string;
};

export type AssessmentOverride = {
  id: string;
  override_type: AssessmentOverrideType;
  status: AssessmentOverrideStatus;
  actor_name: string;
  actor_role: AppRole;
  reason: string;
  override_json: Record<string, unknown>;
  supersedes_id: string | null;
  resolved_by: string | null;
  resolved_at: string | null;
  created_at: string;
};

export type VisibilityGate = {
  scope_key: string | null;
  visibility_mode: VisibilityMode;
  exposure_mode: string;
  viewer_role: AppRole;
  visible_probability_allowed: boolean;
  hidden_probability_allowed: boolean;
  blocked: boolean;
  blocked_reason_codes: string[];
  blocked_reason_text: string | null;
  active_incident_id: string | null;
  active_incident_reason: string | null;
  replay_verified: boolean | null;
  payload_hash_matches: boolean | null;
  artifact_hashes_match: boolean | null;
  scope_release_matches_result: boolean | null;
};

export type AssessmentOverrideSummary = {
  active_overrides: AssessmentOverride[];
  effective_review_status: string | null;
  effective_manual_review_required: boolean | null;
  ranking_suppressed: boolean;
  display_block_reason: string | null;
  effective_valuation: ValuationResult | null;
};

export type IncidentRecord = {
  id: string;
  scope_key: string;
  template_key: string;
  borough_id: string | null;
  incident_type: string;
  status: IncidentStatus;
  reason: string;
  previous_visibility_mode: VisibilityMode | null;
  applied_visibility_mode: VisibilityMode;
  created_by: string;
  resolved_by: string | null;
  created_at: string;
  resolved_at: string | null;
};

export type AuditExport = {
  id: string;
  assessment_run_id: string;
  assessment_result_id: string | null;
  valuation_run_id: string | null;
  prediction_ledger_id: string | null;
  model_release_id: string | null;
  status: AuditExportStatus;
  manifest_path: string | null;
  manifest_hash: string | null;
  manifest_json: Record<string, unknown>;
  requested_by: string;
  created_at: string;
};

export type AssessmentSummary = {
  id: string;
  site_id: string;
  scenario_id: string;
  as_of_date: string;
  state: string;
  idempotency_key: string;
  requested_by: string | null;
  started_at: string | null;
  finished_at: string | null;
  error_text: string | null;
  created_at: string;
  updated_at: string;
  estimate_status: string;
  eligibility_status: string;
  review_status: string;
  manual_review_required: boolean;
  site_summary: SiteSummary | null;
  scenario_summary: ScenarioSummary | null;
};

export type AssessmentDetail = AssessmentSummary & {
  feature_snapshot: AssessmentFeatureSnapshot | null;
  result: AssessmentResult | null;
  valuation: ValuationResult | null;
  override_summary: AssessmentOverrideSummary | null;
  visibility: VisibilityGate | null;
  evidence: EvidencePack | null;
  comparable_case_set: ComparableCaseSet | null;
  prediction_ledger: PredictionLedger | null;
  note: string;
};

export type OpportunitySummary = {
  site_id: string;
  display_name: string;
  borough_id: string | null;
  borough_name: string | null;
  assessment_id: string | null;
  scenario_id: string | null;
  probability_band: 'Band A' | 'Band B' | 'Band C' | 'Band D' | 'Hold';
  hold_reason: string | null;
  ranking_reason: string;
  hidden_mode_only: boolean;
  visibility: VisibilityGate | null;
  display_block_reason: string | null;
  eligibility_status: string | null;
  estimate_status: string | null;
  manual_review_required: boolean;
  valuation_quality: 'HIGH' | 'MEDIUM' | 'LOW' | null;
  asking_price_gbp: number | null;
  asking_price_basis_type: string | null;
  auction_date: string | null;
  post_permission_value_mid: number | null;
  uplift_mid: number | null;
  expected_uplift_mid: number | null;
  same_borough_support_count: number;
  site_summary: SiteSummary | null;
  scenario_summary: ScenarioSummary | null;
};

export type OpportunityDetail = OpportunitySummary & {
  assessment: AssessmentDetail | null;
  valuation: ValuationResult | null;
  ranking_factors: Record<string, unknown>;
};

export type AssessmentCreateInput = {
  site_id: string;
  scenario_id: string;
  as_of_date: string;
  requested_by?: string;
  hidden_mode?: boolean;
  viewer_role?: AppRole;
};

export type ActiveReleaseScope = {
  id: string;
  scope_key: string;
  template_key: string;
  release_channel: string;
  borough_id: string | null;
  model_release_id: string;
  activated_by: string | null;
  activated_at: string;
  visibility_mode: VisibilityMode;
  visibility_reason: string | null;
  visible_enabled_by: string | null;
  visible_enabled_at: string | null;
  visibility_updated_by: string | null;
  visibility_updated_at: string | null;
  open_incident_count: number;
  active_incident_reason: string | null;
};

export type ModelReleaseSummary = {
  id: string;
  template_key: string;
  release_channel: string;
  scope_key: string;
  scope_borough_id: string | null;
  status: string;
  model_kind: string;
  transform_version: string;
  feature_version: string;
  calibration_method: string;
  support_count: number;
  positive_count: number;
  negative_count: number;
  reason_text: string | null;
  active_scope_count: number;
  active_scope_visibility_modes: VisibilityMode[];
  activated_by: string | null;
  activated_at: string | null;
  retired_by: string | null;
  retired_at: string | null;
  created_at: string;
  updated_at: string;
};

export type ModelReleaseDetail = ModelReleaseSummary & {
  model_artifact_path: string | null;
  model_artifact_hash: string | null;
  calibration_artifact_path: string | null;
  calibration_artifact_hash: string | null;
  validation_artifact_path: string | null;
  validation_artifact_hash: string | null;
  model_card_path: string | null;
  model_card_hash: string | null;
  train_window_start: string | null;
  train_window_end: string | null;
  metrics_json: Record<string, unknown>;
  manifest_json: Record<string, unknown>;
  active_scopes: ActiveReleaseScope[];
};

export type HistoricalLabelReviewInput = {
  review_status: string;
  review_notes?: string;
  notable_policy_issues?: string[];
  extant_permission_outcome?: string;
  site_geometry_confidence?: GeometryConfidence;
  reviewed_by?: string;
};

export type AssessmentOverrideInput = {
  requested_by?: string;
  actor_role: AppRole;
  override_type: AssessmentOverrideType;
  reason: string;
  acquisition_basis_gbp?: number;
  acquisition_basis_type?: string;
  valuation_assumption_set_id?: string;
  review_resolution_note?: string;
  resolve_manual_review?: boolean;
  ranking_suppressed?: boolean;
  display_block_reason?: string;
};

export type ReleaseScopeVisibilityInput = {
  requested_by?: string;
  actor_role: AppRole;
  visibility_mode: VisibilityMode;
  reason: string;
};

export type IncidentActionInput = {
  requested_by?: string;
  actor_role: AppRole;
  action: 'OPEN' | 'RESOLVE' | 'ROLLBACK';
  reason: string;
};

export type ReviewQueueResponse = {
  manual_review_cases: Array<{
    assessment_id: string;
    site_id: string;
    display_name: string;
    review_status: string;
    manual_review_required: boolean;
    visibility_mode: VisibilityMode | null;
  }>;
  blocked_cases: Array<{
    assessment_id: string;
    site_id: string;
    display_name: string;
    blocked_reason: string | null;
    visibility_mode: VisibilityMode | null;
    display_block_reason: string | null;
  }>;
  recent_cases: Array<{
    assessment_id: string;
    display_name: string;
    updated_at: string;
    estimate_status: string;
    manual_review_required: boolean;
  }>;
  failing_boroughs: Array<Record<string, unknown>>;
};

export type DataHealthResponse = {
  status: string;
  connector_failure_rate: number | null;
  listing_parse_success_rate: number | null;
  geometry_confidence_distribution: Record<string, number>;
  extant_permission_unresolved_rate: number | null;
  borough_baseline_coverage: Record<string, unknown>;
  coverage: Array<Record<string, unknown>>;
  baseline_packs: Array<Record<string, unknown>>;
  valuation_metrics: {
    total: number;
    uplift_null_rate: number | null;
    asking_price_missing_rate: number | null;
    valuation_quality_distribution: Record<string, number>;
  };
};

export type ModelHealthResponse = {
  status: string;
  calibration_by_probability_band: Array<Record<string, unknown>>;
  brier_score: number | null;
  log_loss: number | null;
  manual_review_agreement_by_band: Array<Record<string, unknown>>;
  false_positive_reviewer_rate: number | null;
  abstain_rate: number | null;
  ood_rate: number | null;
  template_level_performance: Array<Record<string, unknown>>;
  economic_health: Record<string, unknown>;
  releases: Array<Record<string, unknown>>;
  active_scopes: Array<Record<string, unknown>>;
};

type ApiCollectionResponse<T> =
  | T[]
  | {
      items?: T[];
      results?: T[];
      data?: T[];
      listings?: T[];
      clusters?: T[];
      runs?: T[];
      sources?: T[];
    }
  | null;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function pickCollection<T>(value: ApiCollectionResponse<T>): T[] {
  if (Array.isArray(value)) {
    return value;
  }

  if (!value || !isRecord(value)) {
    return [];
  }

  const maybeCollections = [
    value.items,
    value.results,
    value.data,
    value.listings,
    value.clusters,
    value.runs,
    value.sources
  ];

  for (const item of maybeCollections) {
    if (Array.isArray(item)) {
      return item as T[];
    }
  }

  return [];
}

function toStringValue(value: unknown, fallback = ''): string {
  if (typeof value === 'string') {
    return value;
  }

  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }

  return fallback;
}

function toNumberValue(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value;
  }

  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }

  return null;
}

function buildQueryString(params: Record<string, QueryValue>): string {
  const query = new URLSearchParams();

  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === '') {
      continue;
    }

    query.set(key, String(value));
  }

  const output = query.toString();
  return output ? `?${output}` : '';
}

type ApiRequestInit = RequestInit & {
  sessionToken?: string;
};

async function requestJson(path: string, init?: ApiRequestInit): Promise<unknown | null> {
  const controller = new AbortController();
  const timeout = globalThis.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  try {
    const requestInit = { ...(init ?? {}) } as ApiRequestInit;
    delete requestInit.sessionToken;
    delete requestInit.headers;

    const headers = new Headers(init?.headers ?? {});
    headers.set('Accept', 'application/json');
    if (init?.sessionToken) {
      headers.set('x-landintel-session', init.sessionToken);
    }
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...requestInit,
      cache: 'no-store',
      headers,
      signal: controller.signal
    });

    if (!response.ok) {
      return null;
    }

    const contentType = response.headers.get('content-type') ?? '';
    if (!contentType.includes('application/json')) {
      return null;
    }

    return (await response.json()) as unknown;
  } catch {
    return null;
  } finally {
    clearTimeout(timeout);
  }
}

function mapListingSummary(value: unknown): Phase1AListingSummary {
  if (!isRecord(value)) {
    throw new Error('Invalid listing summary');
  }

  const currentSnapshot =
    getRecord(value, 'current_snapshot') ?? getRecord(value, 'currentSnapshot');
  const rawRecordJson = getRecord(currentSnapshot ?? {}, 'raw_record_json');

  return {
    id: toStringValue(value.id),
    source_id: toStringValue(value.source_id ?? value.sourceId),
    source_key: toStringValue(value.source_key ?? value.sourceKey),
    source_name: toStringValue(value.source_name ?? value.sourceName),
    source_listing_id: toStringValue(value.source_listing_id ?? value.sourceListingId),
    canonical_url: toStringValue(value.canonical_url ?? value.canonicalUrl),
    listing_type: toStringValue(value.listing_type ?? value.listingType, 'UNKNOWN'),
    headline: toStringValue(
      value.headline ??
        value.title ??
        currentSnapshot?.headline ??
        rawRecordJson?.headline
    ),
    borough: toStringValue(
      value.borough ??
        rawRecordJson?.borough,
      'Unknown'
    ),
    latest_status: toStringValue(
      value.latest_status ?? value.status ?? currentSnapshot?.status,
      'UNKNOWN'
    ),
    parse_status: (toStringValue(value.parse_status ?? value.parseStatus, 'PARTIAL') as Phase1AListingSummary['parse_status']),
    cluster_id: value.cluster_id === null || value.cluster_id === undefined ? null : toStringValue(value.cluster_id),
    cluster_key: value.cluster_key === null || value.cluster_key === undefined ? null : toStringValue(value.cluster_key),
    first_seen_at: toStringValue(value.first_seen_at ?? value.firstSeenAt),
    last_seen_at: toStringValue(value.last_seen_at ?? value.lastSeenAt),
    price_display: toStringValue(
      value.price_display ??
        value.priceDisplay ??
        currentSnapshot?.guide_price_gbp,
      'No price recorded'
    ),
    coverage_note: toStringValue(value.coverage_note ?? value.coverageNote, '')
  };
}

function getRecord(value: Record<string, unknown>, key: string): Record<string, unknown> | null {
  const candidate = value[key];
  return isRecord(candidate) ? candidate : null;
}

function mapSnapshot(value: unknown): Phase1AListingSnapshot {
  if (!isRecord(value)) {
    throw new Error('Invalid snapshot');
  }

  return {
    id: toStringValue(value.id),
    observed_at: toStringValue(value.observed_at ?? value.observedAt),
    headline: toStringValue(value.headline ?? value.title),
    description_text: toStringValue(value.description_text ?? value.descriptionText),
    guide_price_gbp: toStringValue(value.guide_price_gbp ?? value.guidePriceGbp),
    price_basis_type: toStringValue(value.price_basis_type ?? value.priceBasisType),
    status: toStringValue(value.status),
    auction_date: value.auction_date === null || value.auction_date === undefined ? null : toStringValue(value.auction_date),
    address_text: toStringValue(value.address_text ?? value.addressText),
    lat: toNumberValue(value.lat),
    lon: toNumberValue(value.lon),
    brochure_asset_id: value.brochure_asset_id === null || value.brochure_asset_id === undefined ? null : toStringValue(value.brochure_asset_id),
    map_asset_id: value.map_asset_id === null || value.map_asset_id === undefined ? null : toStringValue(value.map_asset_id),
    raw_record_json: isRecord(value.raw_record_json) ? value.raw_record_json : {}
  };
}

function mapDocument(value: unknown): Phase1ADocument {
  if (!isRecord(value)) {
    throw new Error('Invalid document');
  }

  return {
    id: toStringValue(value.id),
    doc_type: toStringValue(value.doc_type ?? value.docType, 'html_snapshot') as Phase1ADocument['doc_type'],
    filename: toStringValue(value.filename ?? value.name, 'asset'),
    page_count: value.page_count === null || value.page_count === undefined ? null : toNumberValue(value.page_count),
    extraction_status: (toStringValue(value.extraction_status ?? value.extractionStatus, 'PENDING') as Phase1ADocument['extraction_status']),
    extracted_text: value.extracted_text === null || value.extracted_text === undefined ? null : toStringValue(value.extracted_text),
    asset_id: toStringValue(value.asset_id ?? value.assetId)
  };
}

function mapClusterSummary(value: unknown): Phase1AClusterSummary {
  if (!isRecord(value)) {
    throw new Error('Invalid cluster');
  }

  const members = pickCollection(value.members as ApiCollectionResponse<unknown>);
  const firstMember = members.find((member) => isRecord(member));
  const listing = firstMember ? getRecord(firstMember, 'listing') : null;
  const currentSnapshot = listing ? getRecord(listing, 'current_snapshot') : null;

  return {
    id: toStringValue(value.id),
    cluster_key: toStringValue(value.cluster_key ?? value.clusterKey),
    cluster_status: (toStringValue(value.cluster_status ?? value.clusterStatus, 'REVIEW') as Phase1AClusterSummary['cluster_status']),
    created_at: toStringValue(value.created_at ?? value.createdAt),
    member_count: toNumberValue(value.member_count ?? value.memberCount) ?? members.length,
    canonical_headline: toStringValue(
      value.canonical_headline ??
        value.display_name ??
        value.headline ??
        value.title ??
        listing?.headline ??
        currentSnapshot?.headline,
      'Untitled cluster'
    ),
    borough: toStringValue(value.borough ?? listing?.borough, 'Unknown'),
    coverage_note: toStringValue(value.coverage_note ?? value.coverageNote, '')
  };
}

function mapRun(value: unknown): Phase1ARunRecord {
  if (!isRecord(value)) {
    throw new Error('Invalid run record');
  }

  return {
    id: toStringValue(value.id),
    source_key: toStringValue(value.source_key ?? value.sourceKey),
    source_name: toStringValue(value.source_name ?? value.sourceName),
    connector_type: toStringValue(value.connector_type ?? value.connectorType, 'manual_url') as Phase1ARunRecord['connector_type'],
    status: (toStringValue(value.status, 'QUEUED') as Phase1ARunRecord['status']),
    coverage_note: toStringValue(value.coverage_note ?? value.coverageNote, ''),
    parse_status: toStringValue(value.parse_status ?? value.parseStatus, 'PENDING'),
    created_at: toStringValue(value.created_at ?? value.createdAt),
    updated_at: toStringValue(value.updated_at ?? value.updatedAt)
  };
}

async function queryApiCollection<T>(
  path: string,
  mapper: (value: unknown) => T,
  options: { sessionToken?: string } = {}
): Promise<{ items: T[]; apiAvailable: boolean }> {
  const payload = await requestJson(path, { sessionToken: options.sessionToken });
  const items = pickCollection<T>(payload as ApiCollectionResponse<T>);
  return {
    items: items.map(mapper),
    apiAvailable: payload !== null
  };
}

function filterListings(items: Phase1AListingSummary[], query: ListingsQuery): Phase1AListingSummary[] {
  const normalizedQuery = query.q?.trim().toLowerCase();
  return items.filter((item) => {
    if (query.source && item.source_key !== query.source) {
      return false;
    }

    if (query.status && item.latest_status !== query.status) {
      return false;
    }

    if (query.type && item.listing_type !== query.type) {
      return false;
    }

    if (query.cluster && item.cluster_key !== query.cluster && item.cluster_id !== query.cluster) {
      return false;
    }

    if (!normalizedQuery) {
      return true;
    }

    const haystack = [
      item.headline,
      item.canonical_url,
      item.source_name,
      item.borough,
      item.coverage_note,
      item.source_listing_id
    ]
      .join(' ')
      .toLowerCase();

    return haystack.includes(normalizedQuery);
  });
}

export async function getListingSources(): Promise<{ items: Phase1ASource[]; apiAvailable: boolean }> {
  const fallback = { items: phase1ASources, apiAvailable: false };
  const result = await queryApiCollection('/api/listings/sources', (value) => value as Phase1ASource);
  return result.items.length > 0 ? result : fallback;
}

export async function getListings(query: ListingsQuery = {}): Promise<{ items: Phase1AListingSummary[]; apiAvailable: boolean }> {
  const url = `/api/listings${buildQueryString(query)}`;
  const result = await queryApiCollection(url, mapListingSummary);
  const base = result.items.length > 0 ? result.items : phase1AListings;
  return {
    items: filterListings(base, query),
    apiAvailable: result.apiAvailable
  };
}

export async function getListing(listingId: string): Promise<{ item: Phase1AListingDetail | null; apiAvailable: boolean }> {
  const payload = await requestJson(`/api/listings/${encodeURIComponent(listingId)}`);
  if (payload) {
    const record = isRecord(payload) && isRecord(payload.data) ? payload.data : payload;
    if (isRecord(record)) {
      const snapshots = pickCollection<Phase1AListingSnapshot>(record.snapshots as ApiCollectionResponse<Phase1AListingSnapshot>);
      const documents = pickCollection<Phase1ADocument>(record.documents as ApiCollectionResponse<Phase1ADocument>);
      const normalizedFields = getRecord(record, 'normalized_fields');
      const mappedListing = mapListingSummary(record);
      return {
        apiAvailable: true,
        item: {
          ...mappedListing,
          snapshots: snapshots.map(mapSnapshot),
          documents: documents.map(mapDocument),
          normalized_fields: {
            headline: toStringValue(normalizedFields?.headline ?? record.headline ?? record.title, mappedListing.headline),
            description_text: toStringValue(normalizedFields?.description_text ?? record.description_text ?? record.descriptionText),
            guide_price_gbp: toStringValue(normalizedFields?.guide_price_gbp ?? record.guide_price_gbp ?? ''),
            price_basis_type: toStringValue(normalizedFields?.price_basis_type ?? record.price_basis_type ?? 'UNKNOWN'),
            status: toStringValue(normalizedFields?.status ?? record.status ?? mappedListing.latest_status),
            auction_date:
              normalizedFields?.auction_date === null || normalizedFields?.auction_date === undefined
                ? null
                : toStringValue(normalizedFields?.auction_date),
            address_text: toStringValue(normalizedFields?.address_text ?? record.address_text ?? ''),
            lat: toNumberValue(normalizedFields?.lat ?? record.lat),
            lon: toNumberValue(normalizedFields?.lon ?? record.lon)
          },
          raw_record_json: isRecord(record.raw_record_json) ? record.raw_record_json : {}
        }
      };
    }
  }

  return {
    apiAvailable: false,
    item: getPhase1AListingById(listingId)
  };
}

export async function getClusters(): Promise<{ items: Phase1AClusterSummary[]; apiAvailable: boolean }> {
  const result = await queryApiCollection('/api/listing-clusters', mapClusterSummary);
  return {
    items: result.items.length > 0 ? result.items : phase1AClusters.map((cluster) => stripClusterMembers(cluster)),
    apiAvailable: result.apiAvailable
  };
}

const phase1AClusters: Phase1AClusterDetail[] = [
  getPhase1AClusterById('cluster-riverside-yard')!,
  getPhase1AClusterById('cluster-albion-street')!
];

function stripClusterMembers(cluster: Phase1AClusterDetail): Phase1AClusterSummary {
  const { members, ...summary } = cluster;
  void members;
  return summary;
}

export async function getCluster(clusterId: string): Promise<{ item: Phase1AClusterDetail | null; apiAvailable: boolean }> {
  const payload = await requestJson(`/api/listing-clusters/${encodeURIComponent(clusterId)}`);
  if (payload) {
    const record = isRecord(payload) && isRecord(payload.data) ? payload.data : payload;
    if (isRecord(record)) {
      const cluster = mapClusterSummary(record);
      const members = pickCollection(record.members as ApiCollectionResponse<unknown>).map((member) => {
        if (!isRecord(member)) {
          throw new Error('Invalid cluster member');
        }

        const listing = getRecord(member, 'listing');
        const currentSnapshot = listing ? getRecord(listing, 'current_snapshot') : null;

        return {
          id: toStringValue(member.id),
          listing_item_id: toStringValue(
            member.listing_item_id ?? member.listingItemId ?? listing?.id
          ),
          listing_headline: toStringValue(
            member.listing_headline ??
              member.listingHeadline ??
              listing?.headline ??
              currentSnapshot?.headline
          ),
          source_name: toStringValue(
            member.source_name ?? member.sourceName ?? listing?.source_name
          ),
          canonical_url: toStringValue(
            member.canonical_url ?? member.canonicalUrl ?? listing?.canonical_url
          ),
          confidence: toNumberValue(member.confidence) ?? 0,
          latest_status: toStringValue(
            member.latest_status ?? member.latestStatus ?? listing?.latest_status ?? currentSnapshot?.status
          ),
          created_at: toStringValue(member.created_at ?? member.createdAt)
        };
      });

      return {
        apiAvailable: true,
        item: {
          ...cluster,
          members
        }
      };
    }
  }

  return {
    apiAvailable: false,
    item: getPhase1AClusterById(clusterId)
  };
}

export async function getSourceRuns(
  options: { sessionToken?: string } = {}
): Promise<{ items: Phase1ARunRecord[]; apiAvailable: boolean }> {
  const result = await queryApiCollection('/api/listings/runs', mapRun, options);
  return {
    items: result.items.length > 0 ? result.items : phase1ARuns,
    apiAvailable: result.apiAvailable
  };
}

export async function runManualUrlIntake(input: { url: string; coverage_note?: string }): Promise<unknown | null> {
  return requestJson('/api/listings/intake/url', {
    body: JSON.stringify({
      url: input.url,
      coverage_note: input.coverage_note
    }),
    headers: {
      'Content-Type': 'application/json'
    },
    method: 'POST'
  });
}

export async function runCsvImport(input: { file?: File | null; csv_text?: string; coverage_note?: string }): Promise<unknown | null> {
  if (input.file) {
    const formData = new FormData();
    formData.set('file', input.file);
    if (input.coverage_note) {
      formData.set('coverage_note', input.coverage_note);
    }
    return requestJson('/api/listings/import/csv', {
      body: formData,
      method: 'POST'
    });
  }

  return requestJson('/api/listings/import/csv', {
    body: JSON.stringify({
      csv_text: input.csv_text ?? '',
      coverage_note: input.coverage_note
    }),
    headers: {
      'Content-Type': 'application/json'
    },
    method: 'POST'
  });
}

export async function runConnector(sourceKey: string, input: { coverage_note?: string }): Promise<unknown | null> {
  return requestJson(`/api/listings/connectors/${encodeURIComponent(sourceKey)}/run`, {
    body: JSON.stringify({
      coverage_note: input.coverage_note
    }),
    headers: {
      'Content-Type': 'application/json'
    },
    method: 'POST'
  });
}

function mapSiteDocument(value: unknown): SiteDocument {
  if (!isRecord(value)) {
    throw new Error('Invalid site document');
  }

  const asset = getRecord(value, 'asset');
  const assetUrl = toStringValue(asset?.original_url ?? asset?.storage_path, '#');
  const mimeType = toStringValue(asset?.mime_type ?? value.mime_type, 'application/octet-stream');
  return {
    id: toStringValue(value.id),
    label: toStringValue(value.label ?? value.filename ?? value.title ?? value.doc_type, 'Document'),
    doc_type: (
      toStringValue(value.doc_type ?? value.docType, 'raw_asset') === 'BROCHURE'
        ? 'brochure_pdf'
        : toStringValue(value.doc_type ?? value.docType, 'raw_asset') === 'MAP'
          ? 'raw_asset'
          : 'html_snapshot'
    ) as SiteDocument['doc_type'],
    href: toStringValue(value.href ?? value.url, assetUrl),
    asset_id:
      value.asset_id === null || value.asset_id === undefined
        ? null
        : toStringValue(value.asset_id),
    mime_type: mimeType,
    extraction_status: value.extraction_status === null || value.extraction_status === undefined
      ? null
      : toStringValue(value.extraction_status),
    note: toStringValue(value.note ?? asset?.storage_path ?? '', '')
  };
}

function mapLpaLink(value: unknown): SiteLpaLink {
  if (!isRecord(value)) {
    throw new Error('Invalid LPA link');
  }

  return {
    lpa_code: toStringValue(value.lpa_code ?? value.lpaCode ?? value.lpa_id),
    lpa_name: toStringValue(value.lpa_name ?? value.lpaName),
    overlap_sqm: toNumberValue(value.overlap_sqm ?? value.overlapSqm),
    overlap_pct: toNumberValue(value.overlap_pct ?? value.overlapPct),
    controlling: Boolean(value.controlling ?? value.is_controlling ?? value.is_primary ?? false),
    manual_clip_required: Boolean(
      value.manual_clip_required ?? value.manualClipRequired ?? false
    ),
    cross_lpa_flag: Boolean(value.cross_lpa_flag ?? value.crossLpaFlag ?? false),
    note: toStringValue(value.note ?? '', '')
  };
}

function mapTitleLink(value: unknown): SiteTitleLink {
  if (!isRecord(value)) {
    throw new Error('Invalid title link');
  }

  return {
    title_ref: toStringValue(value.title_ref ?? value.titleRef ?? value.title_number ?? value.titleNumber),
    title_number: toStringValue(value.title_number ?? value.titleNumber),
    address_text: toStringValue(value.address_text ?? value.addressText, ''),
    overlap_sqm: toNumberValue(value.overlap_sqm ?? value.overlapSqm),
    overlap_pct: toNumberValue(value.overlap_pct ?? value.overlapPct),
    confidence: toStringValue(value.confidence, 'LOW') as SiteTitleLink['confidence'],
    is_primary: Boolean(value.is_primary ?? value.isPrimary ?? false),
    indicative_only: Boolean(value.indicative_only ?? value.indicativeOnly ?? true),
    evidence_note: toStringValue(
      value.evidence_note ?? value.evidenceNote,
      'Indicative HMLR INSPIRE title overlap only.'
    )
  };
}

function mapMarketEvent(value: unknown): SiteMarketEvent {
  if (!isRecord(value)) {
    throw new Error('Invalid site market event');
  }

  return {
    event_id: toStringValue(value.event_id ?? value.eventId),
    event_type: toStringValue(value.event_type ?? value.eventType, 'SITE_CREATED'),
    event_at: toStringValue(value.event_at ?? value.eventAt),
    price_gbp: value.price_gbp === null || value.price_gbp === undefined ? null : toNumberValue(value.price_gbp),
    price_basis_type:
      value.price_basis_type === null || value.price_basis_type === undefined
        ? null
        : toStringValue(value.price_basis_type),
    note: toStringValue(value.note ?? '', ''),
    source_listing_id:
      value.source_listing_id === null || value.source_listing_id === undefined
        ? null
        : toStringValue(value.source_listing_id)
  };
}

function mapSourceCoverageRecord(value: unknown): SourceCoverageRecord {
  if (!isRecord(value)) {
    throw new Error('Invalid source coverage record');
  }

  return {
    id: toStringValue(value.id),
    borough_id: toStringValue(value.borough_id ?? value.boroughId),
    source_family: toStringValue(value.source_family ?? value.sourceFamily),
    coverage_status: toStringValue(value.coverage_status ?? value.coverageStatus),
    gap_reason:
      value.gap_reason === null || value.gap_reason === undefined
        ? null
        : toStringValue(value.gap_reason),
    freshness_status: toStringValue(value.freshness_status ?? value.freshnessStatus),
    coverage_note:
      value.coverage_note === null || value.coverage_note === undefined
        ? null
        : toStringValue(value.coverage_note),
    source_snapshot_id:
      value.source_snapshot_id === null || value.source_snapshot_id === undefined
        ? null
        : toStringValue(value.source_snapshot_id),
    captured_at: toStringValue(value.captured_at ?? value.capturedAt)
  };
}

function mapPlanningDocument(value: unknown): PlanningDocument {
  if (!isRecord(value)) {
    throw new Error('Invalid planning document');
  }

  return {
    id: toStringValue(value.id),
    doc_type: toStringValue(value.doc_type ?? value.docType, 'document'),
    doc_url: toStringValue(value.doc_url ?? value.docUrl, '#'),
    asset_id:
      value.asset_id === null || value.asset_id === undefined ? null : toStringValue(value.asset_id)
  };
}

function mapPlanningApplicationRecord(
  value: unknown
): PlanningHistoryRecord['planning_application'] {
  if (!isRecord(value)) {
    throw new Error('Invalid planning application');
  }

  const siteGeom = isRecord(value.site_geom_4326) ? mapGeometryFeature(value.site_geom_4326) : null;
  const sitePoint = isRecord(value.site_point_4326)
    ? mapGeometryFeature(value.site_point_4326)
    : null;

  return {
    id: toStringValue(value.id),
    borough_id:
      value.borough_id === null || value.borough_id === undefined
        ? null
        : toStringValue(value.borough_id),
    source_system: toStringValue(value.source_system ?? value.sourceSystem),
    source_snapshot_id: toStringValue(value.source_snapshot_id ?? value.sourceSnapshotId),
    external_ref: toStringValue(value.external_ref ?? value.externalRef),
    application_type: toStringValue(value.application_type ?? value.applicationType),
    proposal_description: toStringValue(
      value.proposal_description ?? value.proposalDescription
    ),
    valid_date:
      value.valid_date === null || value.valid_date === undefined
        ? null
        : toStringValue(value.valid_date),
    decision_date:
      value.decision_date === null || value.decision_date === undefined
        ? null
        : toStringValue(value.decision_date),
    decision:
      value.decision === null || value.decision === undefined
        ? null
        : toStringValue(value.decision),
    decision_type:
      value.decision_type === null || value.decision_type === undefined
        ? null
        : toStringValue(value.decision_type),
    status: toStringValue(value.status, 'UNKNOWN'),
    route_normalized:
      value.route_normalized === null || value.route_normalized === undefined
        ? null
        : toStringValue(value.route_normalized),
    units_proposed:
      value.units_proposed === null || value.units_proposed === undefined
        ? null
        : toNumberValue(value.units_proposed),
    source_priority: toNumberValue(value.source_priority) ?? 0,
    source_url:
      value.source_url === null || value.source_url === undefined
        ? null
        : toStringValue(value.source_url),
    site_geom_4326: siteGeom,
    site_point_4326: sitePoint,
    documents: pickCollection(value.documents as ApiCollectionResponse<unknown>).map(
      mapPlanningDocument
    )
  };
}

function mapPlanningHistoryRecord(value: unknown): PlanningHistoryRecord {
  if (!isRecord(value)) {
    throw new Error('Invalid planning history record');
  }

  return {
    id: toStringValue(value.id),
    link_type: toStringValue(value.link_type ?? value.linkType, 'UNSPECIFIED'),
    distance_m:
      value.distance_m === null || value.distance_m === undefined
        ? null
        : toNumberValue(value.distance_m),
    overlap_pct:
      value.overlap_pct === null || value.overlap_pct === undefined
        ? null
        : toNumberValue(value.overlap_pct),
    match_confidence: toStringValue(
      value.match_confidence ?? value.matchConfidence,
      'LOW'
    ) as GeometryConfidence,
    manual_verified: Boolean(value.manual_verified ?? value.manualVerified ?? false),
    planning_application: mapPlanningApplicationRecord(
      value.planning_application ?? value.planningApplication
    )
  };
}

function mapBrownfieldStateRecord(value: unknown): BrownfieldStateRecord {
  if (!isRecord(value)) {
    throw new Error('Invalid brownfield state');
  }

  return {
    id: toStringValue(value.id),
    borough_id: toStringValue(value.borough_id ?? value.boroughId),
    source_snapshot_id: toStringValue(value.source_snapshot_id ?? value.sourceSnapshotId),
    external_ref: toStringValue(value.external_ref ?? value.externalRef),
    part: toStringValue(value.part),
    pip_status:
      value.pip_status === null || value.pip_status === undefined ? null : toStringValue(value.pip_status),
    tdc_status:
      value.tdc_status === null || value.tdc_status === undefined ? null : toStringValue(value.tdc_status),
    effective_from:
      value.effective_from === null || value.effective_from === undefined
        ? null
        : toStringValue(value.effective_from),
    effective_to:
      value.effective_to === null || value.effective_to === undefined
        ? null
        : toStringValue(value.effective_to),
    raw_record_id: toStringValue(value.raw_record_id ?? value.rawRecordId),
    source_url:
      value.source_url === null || value.source_url === undefined ? null : toStringValue(value.source_url)
  };
}

function mapPolicyFactRecord(value: unknown): PolicyFactRecord {
  if (!isRecord(value)) {
    throw new Error('Invalid policy fact');
  }

  const policyArea = getRecord(value, 'policy_area');
  return {
    id: toStringValue(value.id),
    relation_type: toStringValue(value.relation_type ?? value.relationType),
    overlap_pct:
      value.overlap_pct === null || value.overlap_pct === undefined
        ? null
        : toNumberValue(value.overlap_pct),
    distance_m:
      value.distance_m === null || value.distance_m === undefined
        ? null
        : toNumberValue(value.distance_m),
    importance: toStringValue(value.importance, 'MEDIUM'),
    policy_area: {
      id: toStringValue(policyArea?.id),
      borough_id:
        policyArea?.borough_id === null || policyArea?.borough_id === undefined
          ? null
          : toStringValue(policyArea.borough_id),
      policy_family: toStringValue(policyArea?.policy_family ?? policyArea?.policyFamily),
      policy_code: toStringValue(policyArea?.policy_code ?? policyArea?.policyCode),
      name: toStringValue(policyArea?.name),
      geom_4326: mapGeometryFeature(
        policyArea?.geom_4326 ?? { type: 'Point', coordinates: [0, 0] }
      ),
      source_class: toStringValue(policyArea?.source_class ?? policyArea?.sourceClass),
      source_url:
        policyArea?.source_url === null || policyArea?.source_url === undefined
          ? null
          : toStringValue(policyArea.source_url)
    }
  };
}

function mapConstraintFactRecord(value: unknown): ConstraintFactRecord {
  if (!isRecord(value)) {
    throw new Error('Invalid constraint fact');
  }

  const feature = getRecord(value, 'constraint_feature');
  return {
    id: toStringValue(value.id),
    overlap_pct:
      value.overlap_pct === null || value.overlap_pct === undefined
        ? null
        : toNumberValue(value.overlap_pct),
    distance_m:
      value.distance_m === null || value.distance_m === undefined
        ? null
        : toNumberValue(value.distance_m),
    severity: toStringValue(value.severity, 'MEDIUM'),
    constraint_feature: {
      id: toStringValue(feature?.id),
      feature_family: toStringValue(feature?.feature_family ?? feature?.featureFamily),
      feature_subtype: toStringValue(feature?.feature_subtype ?? feature?.featureSubtype),
      authority_level: toStringValue(feature?.authority_level ?? feature?.authorityLevel),
      geom_4326: mapGeometryFeature(feature?.geom_4326 ?? { type: 'Point', coordinates: [0, 0] }),
      legal_status:
        feature?.legal_status === null || feature?.legal_status === undefined
          ? null
          : toStringValue(feature.legal_status),
      source_class: toStringValue(feature?.source_class ?? feature?.sourceClass),
      source_url:
        feature?.source_url === null || feature?.source_url === undefined
          ? null
          : toStringValue(feature.source_url)
    }
  };
}

function mapExtantPermission(value: unknown): ExtantPermissionRecord | null {
  if (!isRecord(value)) {
    return null;
  }

  return {
    status: toStringValue(value.status),
    eligibility_status: toStringValue(value.eligibility_status ?? value.eligibilityStatus),
    manual_review_required: Boolean(
      value.manual_review_required ?? value.manualReviewRequired ?? false
    ),
    summary: toStringValue(value.summary),
    reasons: pickCollection(value.reasons as ApiCollectionResponse<unknown>).map((item) =>
      toStringValue(item)
    ),
    coverage_gaps: pickCollection(value.coverage_gaps as ApiCollectionResponse<unknown>).map(
      (item) => ({
        code: isRecord(item) ? toStringValue(item.code) : '',
        message: isRecord(item) ? toStringValue(item.message) : toStringValue(item)
      })
    ),
    matched_records: pickCollection(value.matched_records as ApiCollectionResponse<unknown>).map(
      (item) => ({
        source_kind: isRecord(item) ? toStringValue(item.source_kind) : '',
        source_system: isRecord(item) ? toStringValue(item.source_system) : '',
        source_label: isRecord(item) ? toStringValue(item.source_label) : '',
        source_url:
          isRecord(item) && item.source_url !== null && item.source_url !== undefined
            ? toStringValue(item.source_url)
            : null,
        source_snapshot_id:
          isRecord(item) && item.source_snapshot_id !== null && item.source_snapshot_id !== undefined
            ? toStringValue(item.source_snapshot_id)
            : null,
        planning_application_id:
          isRecord(item) && item.planning_application_id !== null && item.planning_application_id !== undefined
            ? toStringValue(item.planning_application_id)
            : null,
        brownfield_state_id:
          isRecord(item) && item.brownfield_state_id !== null && item.brownfield_state_id !== undefined
            ? toStringValue(item.brownfield_state_id)
            : null,
        overlap_pct: isRecord(item) ? toNumberValue(item.overlap_pct) : null,
        overlap_sqm: isRecord(item) ? toNumberValue(item.overlap_sqm) : null,
        distance_m: isRecord(item) ? toNumberValue(item.distance_m) : null,
        material: isRecord(item) ? Boolean(item.material) : false,
        detail: isRecord(item) ? toStringValue(item.detail) : ''
      })
    )
  };
}

function mapEvidenceItem(value: unknown): EvidenceItem {
  if (!isRecord(value)) {
    throw new Error('Invalid evidence item');
  }

  return {
    polarity: toStringValue(value.polarity, 'UNKNOWN') as EvidenceItem['polarity'],
    claim_text: toStringValue(value.claim_text ?? value.claimText),
    topic: toStringValue(value.topic),
    importance: toStringValue(value.importance, 'MEDIUM'),
    source_class: toStringValue(value.source_class ?? value.sourceClass),
    source_label: toStringValue(value.source_label ?? value.sourceLabel),
    source_url:
      value.source_url === null || value.source_url === undefined ? null : toStringValue(value.source_url),
    source_snapshot_id:
      value.source_snapshot_id === null || value.source_snapshot_id === undefined
        ? null
        : toStringValue(value.source_snapshot_id),
    raw_asset_id:
      value.raw_asset_id === null || value.raw_asset_id === undefined
        ? null
        : toStringValue(value.raw_asset_id),
    excerpt_text:
      value.excerpt_text === null || value.excerpt_text === undefined
        ? null
        : toStringValue(value.excerpt_text),
    verified_status: toStringValue(value.verified_status ?? value.verifiedStatus)
  };
}

function mapEvidencePack(value: unknown): EvidencePack | null {
  if (!isRecord(value)) {
    return null;
  }

  return {
    for: pickCollection(value.for as ApiCollectionResponse<unknown>).map(mapEvidenceItem),
    against: pickCollection(value.against as ApiCollectionResponse<unknown>).map(mapEvidenceItem),
    unknown: pickCollection(value.unknown as ApiCollectionResponse<unknown>).map(mapEvidenceItem)
  };
}

function mapBaselinePack(value: unknown): BaselinePackRecord | null {
  if (!isRecord(value)) {
    return null;
  }

  return {
    id: toStringValue(value.id),
    borough_id: toStringValue(value.borough_id ?? value.boroughId),
    version: toStringValue(value.version),
    status: toStringValue(value.status),
    freshness_status: toStringValue(value.freshness_status ?? value.freshnessStatus),
    signed_off_by:
      value.signed_off_by === null || value.signed_off_by === undefined
        ? null
        : toStringValue(value.signed_off_by),
    signed_off_at:
      value.signed_off_at === null || value.signed_off_at === undefined
        ? null
        : toStringValue(value.signed_off_at),
    pack_json: isRecord(value.pack_json) ? value.pack_json : {},
    source_snapshot_id:
      value.source_snapshot_id === null || value.source_snapshot_id === undefined
        ? null
        : toStringValue(value.source_snapshot_id),
    rulepacks: pickCollection(value.rulepacks as ApiCollectionResponse<unknown>).map((item) => ({
      id: isRecord(item) ? toStringValue(item.id) : '',
      template_key: isRecord(item) ? toStringValue(item.template_key ?? item.templateKey) : '',
      status: isRecord(item) ? toStringValue(item.status, 'DRAFT') : 'DRAFT',
      freshness_status: isRecord(item) ? toStringValue(item.freshness_status ?? item.freshnessStatus, 'UNKNOWN') : 'UNKNOWN',
      source_snapshot_id:
        isRecord(item) && item.source_snapshot_id !== null && item.source_snapshot_id !== undefined
          ? toStringValue(item.source_snapshot_id)
          : null,
      citations_complete: isRecord(item) ? Boolean(item.citations_complete ?? item.citationsComplete) : false,
      effective_from:
        isRecord(item) && item.effective_from !== null && item.effective_from !== undefined
          ? toStringValue(item.effective_from)
          : null,
      effective_to:
        isRecord(item) && item.effective_to !== null && item.effective_to !== undefined
          ? toStringValue(item.effective_to)
          : null,
      rule_json: isRecord(item) && isRecord(item.rule_json) ? item.rule_json : {}
    }))
  };
}

function mapScenarioReason(value: unknown): ScenarioReason {
  if (!isRecord(value)) {
    throw new Error('Invalid scenario reason');
  }

  return {
    code: toStringValue(value.code),
    message: toStringValue(value.message),
    source_label:
      value.source_label === null || value.source_label === undefined
        ? null
        : toStringValue(value.source_label),
    source_url:
      value.source_url === null || value.source_url === undefined
        ? null
        : toStringValue(value.source_url),
    source_snapshot_id:
      value.source_snapshot_id === null || value.source_snapshot_id === undefined
        ? null
        : toStringValue(value.source_snapshot_id),
    raw_asset_id:
      value.raw_asset_id === null || value.raw_asset_id === undefined
        ? null
        : toStringValue(value.raw_asset_id)
  };
}

function mapScenarioSummary(value: unknown): ScenarioSummary {
  if (!isRecord(value)) {
    throw new Error('Invalid scenario summary');
  }

  return {
    id: toStringValue(value.id),
    site_id: toStringValue(value.site_id ?? value.siteId),
    template_key: toStringValue(value.template_key ?? value.templateKey),
    template_version: toStringValue(value.template_version ?? value.templateVersion),
    proposal_form: toStringValue(value.proposal_form ?? value.proposalForm, 'REDEVELOPMENT') as ProposalForm,
    units_assumed: toNumberValue(value.units_assumed ?? value.unitsAssumed) ?? 0,
    route_assumed: toStringValue(value.route_assumed ?? value.routeAssumed),
    height_band_assumed: toStringValue(value.height_band_assumed ?? value.heightBandAssumed),
    net_developable_area_pct: toNumberValue(value.net_developable_area_pct ?? value.netDevelopableAreaPct) ?? 0,
    red_line_geom_hash: toStringValue(value.red_line_geom_hash ?? value.redLineGeomHash),
    scenario_source: toStringValue(value.scenario_source ?? value.scenarioSource, 'AUTO') as ScenarioSource,
    status: toStringValue(value.status, 'ANALYST_REQUIRED') as ScenarioStatus,
    supersedes_id:
      value.supersedes_id === null || value.supersedes_id === undefined
        ? null
        : toStringValue(value.supersedes_id),
    is_current: Boolean(value.is_current ?? value.isCurrent),
    is_headline: Boolean(value.is_headline ?? value.isHeadline),
    heuristic_rank:
      value.heuristic_rank === null || value.heuristic_rank === undefined
        ? null
        : toNumberValue(value.heuristic_rank),
    manual_review_required: Boolean(value.manual_review_required ?? value.manualReviewRequired),
    stale_reason:
      value.stale_reason === null || value.stale_reason === undefined
        ? null
        : toStringValue(value.stale_reason),
    housing_mix_assumed_json: isRecord(value.housing_mix_assumed_json) ? value.housing_mix_assumed_json : {},
    parking_assumption:
      value.parking_assumption === null || value.parking_assumption === undefined
        ? null
        : toStringValue(value.parking_assumption),
    affordable_housing_assumption:
      value.affordable_housing_assumption === null || value.affordable_housing_assumption === undefined
        ? null
        : toStringValue(value.affordable_housing_assumption),
    access_assumption:
      value.access_assumption === null || value.access_assumption === undefined
        ? null
        : toStringValue(value.access_assumption),
    reason_codes: pickCollection(value.reason_codes as ApiCollectionResponse<unknown>).map(mapScenarioReason),
    missing_data_flags: pickCollection(value.missing_data_flags as ApiCollectionResponse<unknown>).map((item) => toStringValue(item)),
    warning_codes: pickCollection(value.warning_codes as ApiCollectionResponse<unknown>).map((item) => toStringValue(item))
  };
}

function mapScenarioReview(value: unknown): ScenarioReview {
  if (!isRecord(value)) {
    throw new Error('Invalid scenario review');
  }

  return {
    id: toStringValue(value.id),
    review_status: toStringValue(value.review_status ?? value.reviewStatus, 'ANALYST_REQUIRED') as ScenarioStatus,
    review_notes:
      value.review_notes === null || value.review_notes === undefined
        ? null
        : toStringValue(value.review_notes),
    reviewed_by:
      value.reviewed_by === null || value.reviewed_by === undefined
        ? null
        : toStringValue(value.reviewed_by),
    reviewed_at: toStringValue(value.reviewed_at ?? value.reviewedAt)
  };
}

function mapScenarioDetail(value: unknown): ScenarioDetail {
  if (!isRecord(value)) {
    throw new Error('Invalid scenario detail');
  }

  const templateRecord = getRecord(value, 'template');
  const siteSummaryRecord = getRecord(value, 'site_summary');
  return {
    ...mapScenarioSummary(value),
    template: templateRecord
      ? {
          id: toStringValue(templateRecord.id),
          key: toStringValue(templateRecord.key),
          version: toStringValue(templateRecord.version),
          enabled: Boolean(templateRecord.enabled),
          config_json: isRecord(templateRecord.config_json) ? templateRecord.config_json : {}
        }
      : null,
    review_history: pickCollection(value.review_history as ApiCollectionResponse<unknown>).map(mapScenarioReview),
    evidence: mapEvidencePack(value.evidence),
    baseline_pack: mapBaselinePack(value.baseline_pack),
    site_summary: siteSummaryRecord ? mapSiteSummary(siteSummaryRecord) : null
  };
}

function mapScenarioSuggestResponse(value: unknown): ScenarioSuggestResponse | null {
  if (!isRecord(value)) {
    return null;
  }

  return {
    site_id: toStringValue(value.site_id ?? value.siteId),
    headline_scenario_id:
      value.headline_scenario_id === null || value.headline_scenario_id === undefined
        ? null
        : toStringValue(value.headline_scenario_id),
    items: pickCollection(value.items as ApiCollectionResponse<unknown>).map(mapScenarioSummary),
    excluded_templates: pickCollection(value.excluded_templates as ApiCollectionResponse<unknown>).map((item) => ({
      template_key: isRecord(item) ? toStringValue(item.template_key ?? item.templateKey) : '',
      reasons: isRecord(item)
        ? pickCollection(item.reasons as ApiCollectionResponse<unknown>).map(mapScenarioReason)
        : [],
      missing_data_flags: isRecord(item)
        ? pickCollection(item.missing_data_flags as ApiCollectionResponse<unknown>).map((entry) => toStringValue(entry))
        : [],
      warning_codes: isRecord(item)
        ? pickCollection(item.warning_codes as ApiCollectionResponse<unknown>).map((entry) => toStringValue(entry))
        : []
    }))
  };
}

function mapAssessmentFeatureSnapshot(value: unknown): AssessmentFeatureSnapshot | null {
  if (!isRecord(value)) {
    return null;
  }

  return {
    id: toStringValue(value.id),
    feature_version: toStringValue(value.feature_version ?? value.featureVersion),
    feature_hash: toStringValue(value.feature_hash ?? value.featureHash),
    feature_json: isRecord(value.feature_json) ? value.feature_json : {},
    coverage_json: isRecord(value.coverage_json) ? value.coverage_json : {},
    created_at: toStringValue(value.created_at ?? value.createdAt)
  };
}

function mapAssessmentResult(value: unknown): AssessmentResult | null {
  if (!isRecord(value)) {
    return null;
  }

  return {
    id: toStringValue(value.id),
    model_release_id:
      value.model_release_id === null || value.model_release_id === undefined
        ? null
        : toStringValue(value.model_release_id),
    release_scope_key:
      value.release_scope_key === null || value.release_scope_key === undefined
        ? null
        : toStringValue(value.release_scope_key),
    eligibility_status: toStringValue(value.eligibility_status ?? value.eligibilityStatus),
    estimate_status: toStringValue(value.estimate_status ?? value.estimateStatus, 'NONE'),
    review_status: toStringValue(value.review_status ?? value.reviewStatus),
    approval_probability_raw:
      value.approval_probability_raw === null || value.approval_probability_raw === undefined
        ? null
        : toNumberValue(value.approval_probability_raw),
    approval_probability_display:
      value.approval_probability_display === null || value.approval_probability_display === undefined
        ? null
        : toStringValue(value.approval_probability_display),
    estimate_quality:
      value.estimate_quality === null || value.estimate_quality === undefined
        ? null
        : toStringValue(value.estimate_quality),
    source_coverage_quality:
      value.source_coverage_quality === null || value.source_coverage_quality === undefined
        ? null
        : toStringValue(value.source_coverage_quality),
    geometry_quality:
      value.geometry_quality === null || value.geometry_quality === undefined
        ? null
        : toStringValue(value.geometry_quality),
    support_quality:
      value.support_quality === null || value.support_quality === undefined
        ? null
        : toStringValue(value.support_quality),
    scenario_quality:
      value.scenario_quality === null || value.scenario_quality === undefined
        ? null
        : toStringValue(value.scenario_quality),
    ood_quality:
      value.ood_quality === null || value.ood_quality === undefined
        ? null
        : toStringValue(value.ood_quality),
    ood_status:
      value.ood_status === null || value.ood_status === undefined
        ? null
        : toStringValue(value.ood_status),
    manual_review_required: Boolean(value.manual_review_required ?? value.manualReviewRequired),
    result_json: isRecord(value.result_json) ? value.result_json : {},
    published_at:
      value.published_at === null || value.published_at === undefined
        ? null
        : toStringValue(value.published_at)
  };
}

function mapValuationResult(value: unknown): ValuationResult | null {
  if (!isRecord(value)) {
    return null;
  }

  return {
    id: toStringValue(value.id),
    valuation_run_id: toStringValue(value.valuation_run_id ?? value.valuationRunId),
    valuation_assumption_set_id: toStringValue(
      value.valuation_assumption_set_id ?? value.valuationAssumptionSetId
    ),
    valuation_assumption_version: toStringValue(
      value.valuation_assumption_version ?? value.valuationAssumptionVersion
    ),
    post_permission_value_low:
      value.post_permission_value_low === null || value.post_permission_value_low === undefined
        ? null
        : toNumberValue(value.post_permission_value_low),
    post_permission_value_mid:
      value.post_permission_value_mid === null || value.post_permission_value_mid === undefined
        ? null
        : toNumberValue(value.post_permission_value_mid),
    post_permission_value_high:
      value.post_permission_value_high === null || value.post_permission_value_high === undefined
        ? null
        : toNumberValue(value.post_permission_value_high),
    uplift_low:
      value.uplift_low === null || value.uplift_low === undefined
        ? null
        : toNumberValue(value.uplift_low),
    uplift_mid:
      value.uplift_mid === null || value.uplift_mid === undefined
        ? null
        : toNumberValue(value.uplift_mid),
    uplift_high:
      value.uplift_high === null || value.uplift_high === undefined
        ? null
        : toNumberValue(value.uplift_high),
    expected_uplift_mid:
      value.expected_uplift_mid === null || value.expected_uplift_mid === undefined
        ? null
        : toNumberValue(value.expected_uplift_mid),
    valuation_quality: toStringValue(
      value.valuation_quality ?? value.valuationQuality,
      'LOW'
    ) as ValuationResult['valuation_quality'],
    manual_review_required: Boolean(value.manual_review_required ?? value.manualReviewRequired),
    basis_json: isRecord(value.basis_json) ? value.basis_json : {},
    sense_check_json: isRecord(value.sense_check_json) ? value.sense_check_json : {},
    result_json: isRecord(value.result_json) ? value.result_json : {},
    payload_hash: toStringValue(value.payload_hash ?? value.payloadHash),
    created_at: toStringValue(value.created_at ?? value.createdAt)
  };
}

function mapAssessmentOverride(value: unknown): AssessmentOverride {
  if (!isRecord(value)) {
    throw new Error('Invalid assessment override');
  }

  return {
    id: toStringValue(value.id),
    override_type: toStringValue(value.override_type ?? value.overrideType) as AssessmentOverrideType,
    status: toStringValue(value.status, 'ACTIVE') as AssessmentOverrideStatus,
    actor_name: toStringValue(value.actor_name ?? value.actorName),
    actor_role: toStringValue(value.actor_role ?? value.actorRole, 'analyst') as AppRole,
    reason: toStringValue(value.reason),
    override_json: isRecord(value.override_json) ? value.override_json : {},
    supersedes_id:
      value.supersedes_id === null || value.supersedes_id === undefined
        ? null
        : toStringValue(value.supersedes_id),
    resolved_by:
      value.resolved_by === null || value.resolved_by === undefined
        ? null
        : toStringValue(value.resolved_by),
    resolved_at:
      value.resolved_at === null || value.resolved_at === undefined
        ? null
        : toStringValue(value.resolved_at),
    created_at: toStringValue(value.created_at ?? value.createdAt)
  };
}

function mapVisibilityGate(value: unknown): VisibilityGate | null {
  if (!isRecord(value)) {
    return null;
  }

  return {
    scope_key:
      value.scope_key === null || value.scope_key === undefined ? null : toStringValue(value.scope_key),
    visibility_mode: toStringValue(
      value.visibility_mode ?? value.visibilityMode,
      'HIDDEN_ONLY'
    ) as VisibilityMode,
    exposure_mode: toStringValue(value.exposure_mode ?? value.exposureMode),
    viewer_role: toStringValue(value.viewer_role ?? value.viewerRole, 'analyst') as AppRole,
    visible_probability_allowed: Boolean(
      value.visible_probability_allowed ?? value.visibleProbabilityAllowed ?? false
    ),
    hidden_probability_allowed: Boolean(
      value.hidden_probability_allowed ?? value.hiddenProbabilityAllowed ?? false
    ),
    blocked: Boolean(value.blocked ?? false),
    blocked_reason_codes: pickCollection(
      value.blocked_reason_codes as ApiCollectionResponse<unknown>
    ).map((item) => toStringValue(item)),
    blocked_reason_text:
      value.blocked_reason_text === null || value.blocked_reason_text === undefined
        ? null
        : toStringValue(value.blocked_reason_text),
    active_incident_id:
      value.active_incident_id === null || value.active_incident_id === undefined
        ? null
        : toStringValue(value.active_incident_id),
    active_incident_reason:
      value.active_incident_reason === null || value.active_incident_reason === undefined
        ? null
        : toStringValue(value.active_incident_reason),
    replay_verified:
      value.replay_verified === null || value.replay_verified === undefined
        ? null
        : Boolean(value.replay_verified),
    payload_hash_matches:
      value.payload_hash_matches === null ||
      value.payload_hash_matches === undefined
        ? value.payloadHashMatches === null || value.payloadHashMatches === undefined
          ? null
          : Boolean(value.payloadHashMatches)
        : Boolean(value.payload_hash_matches),
    artifact_hashes_match:
      value.artifact_hashes_match === null ||
      value.artifact_hashes_match === undefined
        ? value.artifactHashesMatch === null || value.artifactHashesMatch === undefined
          ? null
          : Boolean(value.artifactHashesMatch)
        : Boolean(value.artifact_hashes_match),
    scope_release_matches_result:
      value.scope_release_matches_result === null ||
      value.scope_release_matches_result === undefined
        ? value.scopeReleaseMatchesResult === null ||
            value.scopeReleaseMatchesResult === undefined
          ? null
          : Boolean(value.scopeReleaseMatchesResult)
        : Boolean(value.scope_release_matches_result)
  };
}

function mapAssessmentOverrideSummary(value: unknown): AssessmentOverrideSummary | null {
  if (!isRecord(value)) {
    return null;
  }

  return {
    active_overrides: pickCollection(value.active_overrides as ApiCollectionResponse<unknown>).map(
      mapAssessmentOverride
    ),
    effective_review_status:
      value.effective_review_status === null || value.effective_review_status === undefined
        ? null
        : toStringValue(value.effective_review_status),
    effective_manual_review_required:
      value.effective_manual_review_required === null ||
      value.effective_manual_review_required === undefined
        ? null
        : Boolean(value.effective_manual_review_required),
    ranking_suppressed: Boolean(value.ranking_suppressed ?? false),
    display_block_reason:
      value.display_block_reason === null || value.display_block_reason === undefined
        ? null
        : toStringValue(value.display_block_reason),
    effective_valuation: mapValuationResult(value.effective_valuation)
  };
}

function mapIncidentRecord(value: unknown): IncidentRecord | null {
  if (!isRecord(value)) {
    return null;
  }

  return {
    id: toStringValue(value.id),
    scope_key: toStringValue(value.scope_key ?? value.scopeKey),
    template_key: toStringValue(value.template_key ?? value.templateKey),
    borough_id:
      value.borough_id === null || value.borough_id === undefined
        ? null
        : toStringValue(value.borough_id),
    incident_type: toStringValue(value.incident_type ?? value.incidentType),
    status: toStringValue(value.status, 'OPEN') as IncidentStatus,
    reason: toStringValue(value.reason),
    previous_visibility_mode:
      value.previous_visibility_mode === null || value.previous_visibility_mode === undefined
        ? null
        : (toStringValue(value.previous_visibility_mode) as VisibilityMode),
    applied_visibility_mode: toStringValue(
      value.applied_visibility_mode ?? value.appliedVisibilityMode,
      'DISABLED'
    ) as VisibilityMode,
    created_by: toStringValue(value.created_by ?? value.createdBy),
    resolved_by:
      value.resolved_by === null || value.resolved_by === undefined
        ? null
        : toStringValue(value.resolved_by),
    created_at: toStringValue(value.created_at ?? value.createdAt),
    resolved_at:
      value.resolved_at === null || value.resolved_at === undefined
        ? null
        : toStringValue(value.resolved_at)
  };
}

function mapAuditExport(value: unknown): AuditExport | null {
  if (!isRecord(value)) {
    return null;
  }

  return {
    id: toStringValue(value.id),
    assessment_run_id: toStringValue(value.assessment_run_id ?? value.assessmentRunId),
    assessment_result_id:
      value.assessment_result_id === null || value.assessment_result_id === undefined
        ? null
        : toStringValue(value.assessment_result_id),
    valuation_run_id:
      value.valuation_run_id === null || value.valuation_run_id === undefined
        ? null
        : toStringValue(value.valuation_run_id),
    prediction_ledger_id:
      value.prediction_ledger_id === null || value.prediction_ledger_id === undefined
        ? null
        : toStringValue(value.prediction_ledger_id),
    model_release_id:
      value.model_release_id === null || value.model_release_id === undefined
        ? null
        : toStringValue(value.model_release_id),
    status: toStringValue(value.status, 'READY') as AuditExportStatus,
    manifest_path:
      value.manifest_path === null || value.manifest_path === undefined
        ? null
        : toStringValue(value.manifest_path),
    manifest_hash:
      value.manifest_hash === null || value.manifest_hash === undefined
        ? null
        : toStringValue(value.manifest_hash),
    manifest_json: isRecord(value.manifest_json) ? value.manifest_json : {},
    requested_by: toStringValue(value.requested_by ?? value.requestedBy),
    created_at: toStringValue(value.created_at ?? value.createdAt)
  };
}

function mapComparablePlanningApplication(value: unknown): ComparablePlanningApplication {
  if (!isRecord(value)) {
    throw new Error('Invalid comparable planning application');
  }

  return {
    id: toStringValue(value.id),
    external_ref: toStringValue(value.external_ref ?? value.externalRef),
    borough_id:
      value.borough_id === null || value.borough_id === undefined
        ? null
        : toStringValue(value.borough_id),
    proposal_description: toStringValue(value.proposal_description ?? value.proposalDescription),
    valid_date:
      value.valid_date === null || value.valid_date === undefined ? null : toStringValue(value.valid_date),
    decision_date:
      value.decision_date === null || value.decision_date === undefined
        ? null
        : toStringValue(value.decision_date),
    decision:
      value.decision === null || value.decision === undefined ? null : toStringValue(value.decision),
    route_normalized:
      value.route_normalized === null || value.route_normalized === undefined
        ? null
        : toStringValue(value.route_normalized),
    units_proposed:
      value.units_proposed === null || value.units_proposed === undefined
        ? null
        : toNumberValue(value.units_proposed),
    source_system: toStringValue(value.source_system ?? value.sourceSystem),
    source_url:
      value.source_url === null || value.source_url === undefined ? null : toStringValue(value.source_url)
  };
}

function mapHistoricalLabelSummary(value: unknown): HistoricalLabelSummary {
  if (!isRecord(value)) {
    throw new Error('Invalid historical label summary');
  }

  return {
    id: toStringValue(value.id),
    planning_application_id: toStringValue(value.planning_application_id ?? value.planningApplicationId),
    borough_id:
      value.borough_id === null || value.borough_id === undefined ? null : toStringValue(value.borough_id),
    template_key:
      value.template_key === null || value.template_key === undefined
        ? null
        : toStringValue(value.template_key),
    proposal_form:
      value.proposal_form === null || value.proposal_form === undefined
        ? null
        : (toStringValue(value.proposal_form) as ProposalForm),
    route_normalized:
      value.route_normalized === null || value.route_normalized === undefined
        ? null
        : toStringValue(value.route_normalized),
    units_proposed:
      value.units_proposed === null || value.units_proposed === undefined
        ? null
        : toNumberValue(value.units_proposed),
    site_area_sqm:
      value.site_area_sqm === null || value.site_area_sqm === undefined
        ? null
        : toNumberValue(value.site_area_sqm),
    label_version: toStringValue(value.label_version ?? value.labelVersion),
    label_class: toStringValue(value.label_class ?? value.labelClass),
    label_decision: toStringValue(value.label_decision ?? value.labelDecision),
    label_reason:
      value.label_reason === null || value.label_reason === undefined
        ? null
        : toStringValue(value.label_reason),
    valid_date:
      value.valid_date === null || value.valid_date === undefined ? null : toStringValue(value.valid_date),
    first_substantive_decision_date:
      value.first_substantive_decision_date === null || value.first_substantive_decision_date === undefined
        ? null
        : toStringValue(value.first_substantive_decision_date),
    label_window_end:
      value.label_window_end === null || value.label_window_end === undefined
        ? null
        : toStringValue(value.label_window_end),
    source_priority_used: toNumberValue(value.source_priority_used ?? value.sourcePriorityUsed) ?? 0,
    archetype_key:
      value.archetype_key === null || value.archetype_key === undefined
        ? null
        : toStringValue(value.archetype_key),
    designation_profile_json: isRecord(value.designation_profile_json) ? value.designation_profile_json : {},
    provenance_json: isRecord(value.provenance_json) ? value.provenance_json : {},
    source_snapshot_ids_json: pickCollection(value.source_snapshot_ids_json as ApiCollectionResponse<unknown>).map(
      (item) => toStringValue(item)
    ),
    raw_asset_ids_json: pickCollection(value.raw_asset_ids_json as ApiCollectionResponse<unknown>).map((item) =>
      toStringValue(item)
    ),
    review_status: toStringValue(value.review_status ?? value.reviewStatus),
    review_notes:
      value.review_notes === null || value.review_notes === undefined
        ? null
        : toStringValue(value.review_notes),
    reviewed_by:
      value.reviewed_by === null || value.reviewed_by === undefined
        ? null
        : toStringValue(value.reviewed_by),
    reviewed_at:
      value.reviewed_at === null || value.reviewed_at === undefined
        ? null
        : toStringValue(value.reviewed_at),
    notable_policy_issues_json: pickCollection(
      value.notable_policy_issues_json as ApiCollectionResponse<unknown>
    ).map((item) => toStringValue(item)),
    extant_permission_outcome:
      value.extant_permission_outcome === null || value.extant_permission_outcome === undefined
        ? null
        : toStringValue(value.extant_permission_outcome),
    site_geometry_confidence:
      value.site_geometry_confidence === null || value.site_geometry_confidence === undefined
        ? null
        : (toStringValue(value.site_geometry_confidence) as GeometryConfidence),
    created_at: toStringValue(value.created_at ?? value.createdAt),
    updated_at: toStringValue(value.updated_at ?? value.updatedAt)
  };
}

function mapGoldSetPlanningApplication(value: unknown): GoldSetPlanningApplication {
  if (!isRecord(value)) {
    throw new Error('Invalid gold-set planning application');
  }

  return {
    id: toStringValue(value.id),
    borough_id:
      value.borough_id === null || value.borough_id === undefined ? null : toStringValue(value.borough_id),
    source_system: toStringValue(value.source_system ?? value.sourceSystem),
    source_snapshot_id: toStringValue(value.source_snapshot_id ?? value.sourceSnapshotId),
    external_ref: toStringValue(value.external_ref ?? value.externalRef),
    application_type: toStringValue(value.application_type ?? value.applicationType),
    proposal_description: toStringValue(value.proposal_description ?? value.proposalDescription),
    valid_date:
      value.valid_date === null || value.valid_date === undefined ? null : toStringValue(value.valid_date),
    decision_date:
      value.decision_date === null || value.decision_date === undefined
        ? null
        : toStringValue(value.decision_date),
    decision:
      value.decision === null || value.decision === undefined ? null : toStringValue(value.decision),
    decision_type:
      value.decision_type === null || value.decision_type === undefined
        ? null
        : toStringValue(value.decision_type),
    status: toStringValue(value.status),
    route_normalized:
      value.route_normalized === null || value.route_normalized === undefined
        ? null
        : toStringValue(value.route_normalized),
    units_proposed:
      value.units_proposed === null || value.units_proposed === undefined
        ? null
        : toNumberValue(value.units_proposed),
    source_priority: toNumberValue(value.source_priority ?? value.sourcePriority) ?? 0,
    source_url:
      value.source_url === null || value.source_url === undefined ? null : toStringValue(value.source_url),
    site_geom_4326:
      value.site_geom_4326 === null || value.site_geom_4326 === undefined
        ? null
        : mapGeometryFeature(value.site_geom_4326),
    site_point_4326:
      value.site_point_4326 === null || value.site_point_4326 === undefined
        ? null
        : mapGeometryFeature(value.site_point_4326),
    documents: pickCollection(value.documents as ApiCollectionResponse<unknown>).map((item) => ({
      id: isRecord(item) ? toStringValue(item.id) : '',
      doc_type: isRecord(item) ? toStringValue(item.doc_type ?? item.docType) : '',
      doc_url: isRecord(item) ? toStringValue(item.doc_url ?? item.docUrl) : '',
      asset_id:
        isRecord(item) && item.asset_id !== null && item.asset_id !== undefined
          ? toStringValue(item.asset_id)
          : null
    })),
    raw_record_json: isRecord(value.raw_record_json) ? value.raw_record_json : {}
  };
}

function mapHistoricalLabelCase(value: unknown): HistoricalLabelCase {
  if (!isRecord(value)) {
    throw new Error('Invalid historical label case');
  }

  const planningApplication = getRecord(value, 'planning_application');
  return {
    ...mapHistoricalLabelSummary(value),
    planning_application: planningApplication
      ? mapGoldSetPlanningApplication(planningApplication)
      : {
          id: '',
          borough_id: null,
          source_system: '',
          source_snapshot_id: '',
          external_ref: '',
          application_type: '',
          proposal_description: '',
          valid_date: null,
          decision_date: null,
          decision: null,
          decision_type: null,
          status: '',
          route_normalized: null,
          units_proposed: null,
          source_priority: 0,
          source_url: null,
          site_geom_4326: null,
          site_point_4326: null,
          documents: [],
          raw_record_json: {}
        }
  };
}

function mapComparableCaseMember(value: unknown): ComparableCaseMember {
  if (!isRecord(value)) {
    throw new Error('Invalid comparable case member');
  }

  const planningApplication = getRecord(value, 'planning_application');
  const historicalLabel = getRecord(value, 'historical_label');
  return {
    id: toStringValue(value.id),
    planning_application_id: toStringValue(value.planning_application_id ?? value.planningApplicationId),
    similarity_score: toNumberValue(value.similarity_score ?? value.similarityScore) ?? 0,
    outcome: toStringValue(value.outcome, 'APPROVED') as ComparableCaseMember['outcome'],
    rank: toNumberValue(value.rank) ?? 0,
    fallback_path: toStringValue(value.fallback_path ?? value.fallbackPath),
    match_json: isRecord(value.match_json) ? value.match_json : {},
    planning_application: planningApplication
      ? mapComparablePlanningApplication(planningApplication)
      : {
          id: '',
          external_ref: '',
          borough_id: null,
          proposal_description: '',
          valid_date: null,
          decision_date: null,
          decision: null,
          route_normalized: null,
          units_proposed: null,
          source_system: '',
          source_url: null
        },
    historical_label: historicalLabel
      ? mapHistoricalLabelSummary(historicalLabel)
      : mapHistoricalLabelSummary({})
  };
}

function mapComparableCaseSet(value: unknown): ComparableCaseSet | null {
  if (!isRecord(value)) {
    return null;
  }

  return {
    id: toStringValue(value.id),
    strategy: toStringValue(value.strategy),
    same_borough_count: toNumberValue(value.same_borough_count ?? value.sameBoroughCount) ?? 0,
    london_count: toNumberValue(value.london_count ?? value.londonCount) ?? 0,
    approved_count: toNumberValue(value.approved_count ?? value.approvedCount) ?? 0,
    refused_count: toNumberValue(value.refused_count ?? value.refusedCount) ?? 0,
    approved_members: pickCollection(value.approved_members as ApiCollectionResponse<unknown>).map(
      mapComparableCaseMember
    ),
    refused_members: pickCollection(value.refused_members as ApiCollectionResponse<unknown>).map(
      mapComparableCaseMember
    )
  };
}

function mapPredictionLedger(value: unknown): PredictionLedger | null {
  if (!isRecord(value)) {
    return null;
  }

  return {
    id: toStringValue(value.id),
    site_geom_hash: toStringValue(value.site_geom_hash ?? value.siteGeomHash),
    feature_hash: toStringValue(value.feature_hash ?? value.featureHash),
    model_release_id:
      value.model_release_id === null || value.model_release_id === undefined
        ? null
        : toStringValue(value.model_release_id),
    release_scope_key:
      value.release_scope_key === null || value.release_scope_key === undefined
        ? null
        : toStringValue(value.release_scope_key),
    calibration_hash:
      value.calibration_hash === null || value.calibration_hash === undefined
        ? null
        : toStringValue(value.calibration_hash),
    model_artifact_hash:
      value.model_artifact_hash === null || value.model_artifact_hash === undefined
        ? null
        : toStringValue(value.model_artifact_hash),
    validation_artifact_hash:
      value.validation_artifact_hash === null || value.validation_artifact_hash === undefined
        ? null
        : toStringValue(value.validation_artifact_hash),
    response_mode: toStringValue(value.response_mode ?? value.responseMode),
    source_snapshot_ids_json: pickCollection(
      value.source_snapshot_ids_json as ApiCollectionResponse<unknown>
    ).map((item) => toStringValue(item)),
    raw_asset_ids_json: pickCollection(value.raw_asset_ids_json as ApiCollectionResponse<unknown>).map(
      (item) => toStringValue(item)
    ),
    result_payload_hash: toStringValue(value.result_payload_hash ?? value.resultPayloadHash),
    response_json: isRecord(value.response_json) ? value.response_json : {},
    replay_verification_status: toStringValue(
      value.replay_verification_status ?? value.replayVerificationStatus,
      'UNKNOWN'
    ),
    replay_verified_at:
      value.replay_verified_at === null || value.replay_verified_at === undefined
        ? null
        : toStringValue(value.replay_verified_at),
    replay_verification_note:
      value.replay_verification_note === null || value.replay_verification_note === undefined
        ? null
        : toStringValue(value.replay_verification_note),
    created_at: toStringValue(value.created_at ?? value.createdAt)
  };
}

function mapAssessmentSummary(value: unknown): AssessmentSummary {
  if (!isRecord(value)) {
    throw new Error('Invalid assessment summary');
  }

  const siteSummary = getRecord(value, 'site_summary');
  const scenarioSummary = getRecord(value, 'scenario_summary');

  return {
    id: toStringValue(value.id),
    site_id: toStringValue(value.site_id ?? value.siteId),
    scenario_id: toStringValue(value.scenario_id ?? value.scenarioId),
    as_of_date: toStringValue(value.as_of_date ?? value.asOfDate),
    state: toStringValue(value.state),
    idempotency_key: toStringValue(value.idempotency_key ?? value.idempotencyKey),
    requested_by:
      value.requested_by === null || value.requested_by === undefined
        ? null
        : toStringValue(value.requested_by),
    started_at:
      value.started_at === null || value.started_at === undefined
        ? null
        : toStringValue(value.started_at),
    finished_at:
      value.finished_at === null || value.finished_at === undefined
        ? null
        : toStringValue(value.finished_at),
    error_text:
      value.error_text === null || value.error_text === undefined
        ? null
        : toStringValue(value.error_text),
    created_at: toStringValue(value.created_at ?? value.createdAt),
    updated_at: toStringValue(value.updated_at ?? value.updatedAt),
    estimate_status: toStringValue(value.estimate_status ?? value.estimateStatus, 'NONE'),
    eligibility_status: toStringValue(value.eligibility_status ?? value.eligibilityStatus),
    review_status: toStringValue(value.review_status ?? value.reviewStatus),
    manual_review_required: Boolean(value.manual_review_required ?? value.manualReviewRequired),
    site_summary: siteSummary ? mapSiteSummary(siteSummary) : null,
    scenario_summary: scenarioSummary ? mapScenarioSummary(scenarioSummary) : null
  };
}

function mapAssessmentDetail(value: unknown): AssessmentDetail | null {
  if (!isRecord(value)) {
    return null;
  }

  return {
    ...mapAssessmentSummary(value),
    feature_snapshot: mapAssessmentFeatureSnapshot(value.feature_snapshot ?? value.featureSnapshot),
    result: mapAssessmentResult(value.result),
    valuation: mapValuationResult(value.valuation),
    override_summary: mapAssessmentOverrideSummary(value.override_summary ?? value.overrideSummary),
    visibility: mapVisibilityGate(value.visibility),
    evidence: mapEvidencePack(value.evidence),
    comparable_case_set: mapComparableCaseSet(value.comparable_case_set ?? value.comparableCaseSet),
    prediction_ledger: mapPredictionLedger(value.prediction_ledger ?? value.predictionLedger),
    note: toStringValue(value.note)
  };
}

function mapOpportunitySummary(value: unknown): OpportunitySummary {
  if (!isRecord(value)) {
    throw new Error('Invalid opportunity summary');
  }

  const siteSummary = getRecord(value, 'site_summary');
  const scenarioSummary = getRecord(value, 'scenario_summary');

  return {
    site_id: toStringValue(value.site_id ?? value.siteId),
    display_name: toStringValue(value.display_name ?? value.displayName, 'Untitled site'),
    borough_id:
      value.borough_id === null || value.borough_id === undefined
        ? null
        : toStringValue(value.borough_id),
    borough_name:
      value.borough_name === null || value.borough_name === undefined
        ? null
        : toStringValue(value.borough_name),
    assessment_id:
      value.assessment_id === null || value.assessment_id === undefined
        ? null
        : toStringValue(value.assessment_id),
    scenario_id:
      value.scenario_id === null || value.scenario_id === undefined
        ? null
        : toStringValue(value.scenario_id),
    probability_band: toStringValue(
      value.probability_band ?? value.probabilityBand,
      'Hold'
    ) as OpportunitySummary['probability_band'],
    hold_reason:
      value.hold_reason === null || value.hold_reason === undefined
        ? null
        : toStringValue(value.hold_reason),
    ranking_reason: toStringValue(value.ranking_reason ?? value.rankingReason),
    hidden_mode_only: Boolean(value.hidden_mode_only ?? value.hiddenModeOnly ?? true),
    visibility: mapVisibilityGate(value.visibility),
    display_block_reason:
      value.display_block_reason === null || value.display_block_reason === undefined
        ? null
        : toStringValue(value.display_block_reason),
    eligibility_status:
      value.eligibility_status === null || value.eligibility_status === undefined
        ? null
        : toStringValue(value.eligibility_status),
    estimate_status:
      value.estimate_status === null || value.estimate_status === undefined
        ? null
        : toStringValue(value.estimate_status),
    manual_review_required: Boolean(value.manual_review_required ?? value.manualReviewRequired),
    valuation_quality:
      value.valuation_quality === null || value.valuation_quality === undefined
        ? null
        : (toStringValue(value.valuation_quality) as OpportunitySummary['valuation_quality']),
    asking_price_gbp:
      value.asking_price_gbp === null || value.asking_price_gbp === undefined
        ? null
        : toNumberValue(value.asking_price_gbp),
    asking_price_basis_type:
      value.asking_price_basis_type === null || value.asking_price_basis_type === undefined
        ? null
        : toStringValue(value.asking_price_basis_type),
    auction_date:
      value.auction_date === null || value.auction_date === undefined
        ? null
        : toStringValue(value.auction_date),
    post_permission_value_mid:
      value.post_permission_value_mid === null || value.post_permission_value_mid === undefined
        ? null
        : toNumberValue(value.post_permission_value_mid),
    uplift_mid:
      value.uplift_mid === null || value.uplift_mid === undefined
        ? null
        : toNumberValue(value.uplift_mid),
    expected_uplift_mid:
      value.expected_uplift_mid === null || value.expected_uplift_mid === undefined
        ? null
        : toNumberValue(value.expected_uplift_mid),
    same_borough_support_count:
      toNumberValue(value.same_borough_support_count ?? value.sameBoroughSupportCount) ?? 0,
    site_summary: siteSummary ? mapSiteSummary(siteSummary) : null,
    scenario_summary: scenarioSummary ? mapScenarioSummary(scenarioSummary) : null
  };
}

function mapOpportunityDetail(value: unknown): OpportunityDetail | null {
  if (!isRecord(value)) {
    return null;
  }

  return {
    ...mapOpportunitySummary(value),
    assessment: mapAssessmentDetail(value.assessment),
    valuation: mapValuationResult(value.valuation),
    ranking_factors: isRecord(value.ranking_factors ?? value.rankingFactors)
      ? ((value.ranking_factors ?? value.rankingFactors) as Record<string, unknown>)
      : {}
  };
}

function mapActiveReleaseScope(value: unknown): ActiveReleaseScope {
  if (!isRecord(value)) {
    throw new Error('Invalid active release scope');
  }

  return {
    id: toStringValue(value.id),
    scope_key: toStringValue(value.scope_key ?? value.scopeKey),
    template_key: toStringValue(value.template_key ?? value.templateKey),
    release_channel: toStringValue(value.release_channel ?? value.releaseChannel),
    borough_id:
      value.borough_id === null || value.borough_id === undefined
        ? null
        : toStringValue(value.borough_id),
    model_release_id: toStringValue(value.model_release_id ?? value.modelReleaseId),
    activated_by:
      value.activated_by === null || value.activated_by === undefined
        ? null
        : toStringValue(value.activated_by),
    activated_at: toStringValue(value.activated_at ?? value.activatedAt),
    visibility_mode: toStringValue(
      value.visibility_mode ?? value.visibilityMode,
      'HIDDEN_ONLY'
    ) as VisibilityMode,
    visibility_reason:
      value.visibility_reason === null || value.visibility_reason === undefined
        ? null
        : toStringValue(value.visibility_reason),
    visible_enabled_by:
      value.visible_enabled_by === null || value.visible_enabled_by === undefined
        ? null
        : toStringValue(value.visible_enabled_by),
    visible_enabled_at:
      value.visible_enabled_at === null || value.visible_enabled_at === undefined
        ? null
        : toStringValue(value.visible_enabled_at),
    visibility_updated_by:
      value.visibility_updated_by === null || value.visibility_updated_by === undefined
        ? null
        : toStringValue(value.visibility_updated_by),
    visibility_updated_at:
      value.visibility_updated_at === null || value.visibility_updated_at === undefined
        ? null
        : toStringValue(value.visibility_updated_at),
    open_incident_count: toNumberValue(value.open_incident_count ?? value.openIncidentCount) ?? 0,
    active_incident_reason:
      value.active_incident_reason === null || value.active_incident_reason === undefined
        ? null
        : toStringValue(value.active_incident_reason)
  };
}

function mapModelReleaseSummary(value: unknown): ModelReleaseSummary {
  if (!isRecord(value)) {
    throw new Error('Invalid model release summary');
  }

  return {
    id: toStringValue(value.id),
    template_key: toStringValue(value.template_key ?? value.templateKey),
    release_channel: toStringValue(value.release_channel ?? value.releaseChannel),
    scope_key: toStringValue(value.scope_key ?? value.scopeKey),
    scope_borough_id:
      value.scope_borough_id === null || value.scope_borough_id === undefined
        ? null
        : toStringValue(value.scope_borough_id),
    status: toStringValue(value.status),
    model_kind: toStringValue(value.model_kind ?? value.modelKind),
    transform_version: toStringValue(value.transform_version ?? value.transformVersion),
    feature_version: toStringValue(value.feature_version ?? value.featureVersion),
    calibration_method: toStringValue(value.calibration_method ?? value.calibrationMethod),
    support_count: toNumberValue(value.support_count ?? value.supportCount) ?? 0,
    positive_count: toNumberValue(value.positive_count ?? value.positiveCount) ?? 0,
    negative_count: toNumberValue(value.negative_count ?? value.negativeCount) ?? 0,
    reason_text:
      value.reason_text === null || value.reason_text === undefined
        ? null
        : toStringValue(value.reason_text),
    active_scope_count: toNumberValue(value.active_scope_count ?? value.activeScopeCount) ?? 0,
    active_scope_visibility_modes: pickCollection(
      value.active_scope_visibility_modes as ApiCollectionResponse<unknown>
    ).map((item) => toStringValue(item) as VisibilityMode),
    activated_by:
      value.activated_by === null || value.activated_by === undefined
        ? null
        : toStringValue(value.activated_by),
    activated_at:
      value.activated_at === null || value.activated_at === undefined
        ? null
        : toStringValue(value.activated_at),
    retired_by:
      value.retired_by === null || value.retired_by === undefined
        ? null
        : toStringValue(value.retired_by),
    retired_at:
      value.retired_at === null || value.retired_at === undefined
        ? null
        : toStringValue(value.retired_at),
    created_at: toStringValue(value.created_at ?? value.createdAt),
    updated_at: toStringValue(value.updated_at ?? value.updatedAt)
  };
}

function mapModelReleaseDetail(value: unknown): ModelReleaseDetail | null {
  if (!isRecord(value)) {
    return null;
  }

  return {
    ...mapModelReleaseSummary(value),
    model_artifact_path:
      value.model_artifact_path === null || value.model_artifact_path === undefined
        ? null
        : toStringValue(value.model_artifact_path),
    model_artifact_hash:
      value.model_artifact_hash === null || value.model_artifact_hash === undefined
        ? null
        : toStringValue(value.model_artifact_hash),
    calibration_artifact_path:
      value.calibration_artifact_path === null || value.calibration_artifact_path === undefined
        ? null
        : toStringValue(value.calibration_artifact_path),
    calibration_artifact_hash:
      value.calibration_artifact_hash === null || value.calibration_artifact_hash === undefined
        ? null
        : toStringValue(value.calibration_artifact_hash),
    validation_artifact_path:
      value.validation_artifact_path === null || value.validation_artifact_path === undefined
        ? null
        : toStringValue(value.validation_artifact_path),
    validation_artifact_hash:
      value.validation_artifact_hash === null || value.validation_artifact_hash === undefined
        ? null
        : toStringValue(value.validation_artifact_hash),
    model_card_path:
      value.model_card_path === null || value.model_card_path === undefined
        ? null
        : toStringValue(value.model_card_path),
    model_card_hash:
      value.model_card_hash === null || value.model_card_hash === undefined
        ? null
        : toStringValue(value.model_card_hash),
    train_window_start:
      value.train_window_start === null || value.train_window_start === undefined
        ? null
        : toStringValue(value.train_window_start),
    train_window_end:
      value.train_window_end === null || value.train_window_end === undefined
        ? null
        : toStringValue(value.train_window_end),
    metrics_json: isRecord(value.metrics_json) ? value.metrics_json : {},
    manifest_json: isRecord(value.manifest_json) ? value.manifest_json : {},
    active_scopes: pickCollection(value.active_scopes as ApiCollectionResponse<unknown>).map(
      mapActiveReleaseScope
    )
  };
}

function mapGeometryFeature(value: unknown): GeometryFeature {
  if (!isRecord(value)) {
    throw new Error('Invalid geometry feature');
  }

  const geometry = isRecord(value.geometry) ? value.geometry : value;
  if (!geometry) {
    throw new Error('Missing geometry');
  }

  const geometryType = toStringValue(geometry.type);
  if (geometryType === 'Point') {
    return {
      type: 'Feature',
      geometry: {
        type: 'Point',
        coordinates: Array.isArray(geometry.coordinates)
          ? (geometry.coordinates as [number, number])
          : [0, 0]
      },
      properties: isRecord(value.properties) ? value.properties : {}
    };
  }

  if (geometryType === 'MultiPolygon') {
    return {
      type: 'Feature',
      geometry: {
        type: 'MultiPolygon',
        coordinates: Array.isArray(geometry.coordinates) ? (geometry.coordinates as number[][][][]) : []
      },
      properties: isRecord(value.properties) ? value.properties : {}
    };
  }

  return {
    type: 'Feature',
    geometry: {
      type: 'Polygon',
      coordinates: Array.isArray(geometry.coordinates) ? (geometry.coordinates as number[][][]) : []
    },
    properties: isRecord(value.properties) ? value.properties : {}
  };
}

function mapSiteSummary(value: unknown): SiteSummary {
  if (!isRecord(value)) {
    throw new Error('Invalid site summary');
  }

  const currentGeometry = getRecord(value, 'current_geometry');
  const featurePayload =
    value.geometry_geojson_4326 ??
    currentGeometry?.geom_4326 ??
    currentGeometry?.geometry_geojson_4326;
  const feature = isRecord(featurePayload) ? mapGeometryFeature(featurePayload) : null;
  const warnings = extractWarningMessages(value.warnings);
  const reviewFlags = extractReviewFlags(value, warnings);
  const geometrySourceType = toStringValue(
    value.geometry_source_type ?? value.geometrySourceType ?? currentGeometry?.geom_source_type,
    'POINT_ONLY'
  ) as SiteSummary['geometry_source_type'];
  const geometryConfidence = toStringValue(
    value.geometry_confidence ?? value.geometryConfidence ?? currentGeometry?.geom_confidence,
    'INSUFFICIENT'
  ) as SiteSummary['geometry_confidence'];
  const currentListing = getRecord(value, 'current_listing');
  const listingCluster = getRecord(value, 'listing_cluster');
  const siteArea = toNumberValue(
    value.site_area_sqm ?? value.siteAreaSqm ?? currentGeometry?.site_area_sqm
  );
  const centroid = feature ? centroidFromFeature(feature) : { lat: 0, lon: 0 };

  return {
    site_id: toStringValue(value.site_id ?? value.siteId ?? value.id),
    display_name: toStringValue(value.display_name ?? value.displayName, 'Untitled site'),
    cluster_id: toStringValue(
      value.cluster_id ?? value.clusterId ?? listingCluster?.id,
      ''
    ),
    cluster_key: toStringValue(
      value.cluster_key ?? value.clusterKey ?? listingCluster?.cluster_key,
      ''
    ),
    borough_name: toStringValue(value.borough_name ?? value.boroughName, 'Unknown'),
    controlling_lpa_name: toStringValue(
      value.controlling_lpa_name ??
        value.controllingLpaName ??
        value.borough_name ??
        value.boroughName,
      'Unknown'
    ),
    geometry_source_type: geometrySourceType,
    geometry_confidence: geometryConfidence,
    site_area_sqm: siteArea,
    current_listing_id: toStringValue(
      value.current_listing_id ?? value.currentListingId ?? currentListing?.id,
      ''
    ),
    current_listing_headline: toStringValue(
      value.current_listing_headline ??
        value.currentListingHeadline ??
        currentListing?.headline,
      ''
    ),
    current_price_gbp:
      value.current_price_gbp === null || value.current_price_gbp === undefined
        ? toNumberValue(currentListing?.guide_price_gbp)
        : toNumberValue(value.current_price_gbp),
    current_price_basis_type:
      value.current_price_basis_type === null || value.current_price_basis_type === undefined
        ? toStringValue(currentListing?.price_basis_type, '')
        : toStringValue(value.current_price_basis_type),
    warnings,
    review_flags: reviewFlags,
    revision_count: toNumberValue(value.revision_count ?? value.revisionCount) ?? 0,
    document_count: toNumberValue(value.document_count ?? value.documentCount) ?? 0,
    title_link_count: toNumberValue(value.title_link_count ?? value.titleLinkCount) ?? 0,
    lpa_link_count: toNumberValue(value.lpa_link_count ?? value.lpaLinkCount) ?? 0,
    geometry_geojson_4326:
      feature ?? {
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [0, 0] },
        properties: {}
      },
    centroid_4326: isRecord(value.centroid_4326)
      ? {
          lat: toNumberValue(value.centroid_4326.lat) ?? centroid.lat,
          lon: toNumberValue(value.centroid_4326.lon) ?? centroid.lon
        }
      : centroid
  };
}

function mapSiteDetail(value: unknown): SiteDetail {
  if (!isRecord(value)) {
    throw new Error('Invalid site detail');
  }

  const summary = mapSiteSummary(value);
  const currentListing = getRecord(value, 'current_listing');
  const revisions = pickCollection(
    (value.geometry_revisions ?? value.revision_history) as ApiCollectionResponse<unknown>
  ).map((revision, index) => mapGeometryRevision(revision, summary.geometry_geojson_4326, summary, index));
  const sourceSnapshots = pickCollection(
    value.source_snapshots as ApiCollectionResponse<unknown>
  );
  const sourceSnapshot = isRecord(sourceSnapshots[0]) ? sourceSnapshots[0] : null;
  const documents = pickCollection(
    (value.source_documents ?? value.documents) as ApiCollectionResponse<unknown>
  ).map(mapSiteDocument);
  const titleLinks = pickCollection(value.title_links as ApiCollectionResponse<unknown>).map(
    (link, index) => mapTitleLinkWithContext(link, index)
  );
  const lpaLinksRaw = pickCollection(value.lpa_links as ApiCollectionResponse<unknown>);
  const sourceCoverage = pickCollection(
    value.source_coverage as ApiCollectionResponse<unknown>
  ).map(mapSourceCoverageRecord);
  const planningHistory = pickCollection(
    value.planning_history as ApiCollectionResponse<unknown>
  ).map(mapPlanningHistoryRecord);
  const brownfieldStates = pickCollection(
    value.brownfield_states as ApiCollectionResponse<unknown>
  ).map(mapBrownfieldStateRecord);
  const policyFacts = pickCollection(
    value.policy_facts as ApiCollectionResponse<unknown>
  ).map(mapPolicyFactRecord);
  const constraintFacts = pickCollection(
    value.constraint_facts as ApiCollectionResponse<unknown>
  ).map(mapConstraintFactRecord);
  const extantPermission = mapExtantPermission(value.extant_permission);
  const evidence = mapEvidencePack(value.evidence);
  const baselinePack = mapBaselinePack(value.baseline_pack);
  const scenarios = pickCollection(value.scenarios as ApiCollectionResponse<unknown>).map(mapScenarioSummary);
  const materialCrossLpa = summary.review_flags.includes('CROSS_LPA_MATERIAL');

  return {
    ...summary,
    revision_count: revisions.length,
    document_count: documents.length,
    title_link_count: titleLinks.length,
    lpa_link_count: lpaLinksRaw.length,
    address_text: toStringValue(
      value.address_text ?? value.addressText ?? currentListing?.address_text,
      ''
    ),
    summary: toStringValue(
      value.summary,
      summary.site_area_sqm === null
        ? `${summary.display_name} · area pending`
        : `${summary.display_name} · ${summary.site_area_sqm.toLocaleString('en-GB')} sqm`
    ),
    description_text: toStringValue(value.description_text ?? value.descriptionText, ''),
    source_snapshot_id: toStringValue(
      value.source_snapshot_id ?? value.sourceSnapshotId ?? sourceSnapshot?.id,
      ''
    ),
    source_snapshot_url: sourceSnapshot
      ? toStringValue(sourceSnapshot.source_uri)
      : null,
    current_listing: currentListing
      ? {
        id: toStringValue(currentListing.id),
        headline: toStringValue(currentListing.headline ?? currentListing.title, ''),
        source_key: toStringValue(
          currentListing.source_key ?? currentListing.sourceKey ?? currentListing.source_name,
          ''
        ),
        canonical_url: toStringValue(currentListing.canonical_url ?? currentListing.canonicalUrl, ''),
        latest_status: toStringValue(currentListing.latest_status ?? currentListing.status, ''),
        parse_status: toStringValue(
          currentListing.parse_status ?? currentListing.parseStatus,
          'PARSED'
        ),
        price_display: formatPriceDisplay(
          toNumberValue(currentListing.guide_price_gbp),
          toStringValue(currentListing.price_basis_type)
        ),
        observed_at: toStringValue(
          currentListing.observed_at ?? currentListing.observedAt ?? sourceSnapshot?.acquired_at,
          ''
        )
      }
      : {
          id: '',
          headline: '',
          source_key: '',
          canonical_url: '',
          latest_status: '',
          parse_status: '',
          price_display: '',
          observed_at: ''
        },
    revision_history: revisions,
    title_links: titleLinks,
    lpa_links: lpaLinksRaw.map((link) =>
      mapLpaLinkWithContext(link, materialCrossLpa, lpaLinksRaw.length > 1)
    ),
    documents,
    market_events: pickCollection(value.market_events as ApiCollectionResponse<unknown>).map(mapMarketEvent),
    source_snapshots: sourceSnapshots
      .filter((snapshot): snapshot is Record<string, unknown> => isRecord(snapshot))
      .map((snapshot) => ({
        id: toStringValue(snapshot.id),
        source_family: toStringValue(snapshot.source_family ?? snapshot.sourceFamily),
        source_name: toStringValue(snapshot.source_name ?? snapshot.sourceName),
        source_uri: toStringValue(snapshot.source_uri ?? snapshot.sourceUri),
        acquired_at: toStringValue(snapshot.acquired_at ?? snapshot.acquiredAt)
      })),
    geometry_editor_guidance: toStringValue(
      value.geometry_editor_guidance ?? value.geometryEditorGuidance,
      'Draw conservatively, save explicit revisions, and treat indicative geometry as evidence only.'
    ),
    last_updated_at: toStringValue(
      value.last_updated_at ?? value.lastUpdatedAt ?? revisions[0]?.created_at,
      ''
    ),
    source_coverage: sourceCoverage,
    planning_history: planningHistory,
    brownfield_states: brownfieldStates,
    policy_facts: policyFacts,
    constraint_facts: constraintFacts,
    extant_permission: extantPermission,
    evidence,
    baseline_pack: baselinePack,
    scenarios
  };
}

function mapGeometryRevision(
  value: unknown,
  currentGeometry: GeometryFeature,
  summary: SiteSummary,
  index: number
): SiteDetail['revision_history'][number] {
  if (!isRecord(value)) {
    throw new Error('Invalid geometry revision');
  }

  const geometryPayload = value.geom_4326 ?? value.geometry_geojson_4326 ?? currentGeometry;
  return {
    revision_id: toStringValue(value.revision_id ?? value.revisionId ?? value.id),
    created_at: toStringValue(value.created_at ?? value.createdAt),
    created_by: toStringValue(value.created_by ?? value.createdBy, ''),
    geom_source_type: toStringValue(
      value.geom_source_type ?? value.geomSourceType ?? value.source_type,
      summary.geometry_source_type
    ) as SiteDetail['revision_history'][number]['geom_source_type'],
    geom_confidence: toStringValue(
      value.geom_confidence ?? value.geomConfidence ?? value.confidence,
      summary.geometry_confidence
    ) as SiteDetail['revision_history'][number]['geom_confidence'],
    geom_hash: toStringValue(value.geom_hash ?? value.geomHash, ''),
    site_area_sqm:
      value.site_area_sqm === null || value.site_area_sqm === undefined
        ? toNumberValue(summary.site_area_sqm)
        : toNumberValue(value.site_area_sqm),
    note: toStringValue(value.note ?? value.reason ?? '', ''),
    is_current: Boolean(value.is_current ?? value.isCurrent ?? index === 0),
    geometry_geojson_4326: mapGeometryFeature(geometryPayload)
  };
}

function mapTitleLinkWithContext(value: unknown, index: number): SiteTitleLink {
  const mapped = mapTitleLink(value);
  return {
    ...mapped,
    is_primary: mapped.is_primary || index === 0
  };
}

function mapLpaLinkWithContext(
  value: unknown,
  materialCrossLpa: boolean,
  crossLpaFlag: boolean
): SiteLpaLink {
  const mapped = mapLpaLink(value);
  return {
    ...mapped,
    controlling: mapped.controlling,
    manual_clip_required: mapped.manual_clip_required || materialCrossLpa,
    cross_lpa_flag: mapped.cross_lpa_flag || crossLpaFlag,
    note:
      mapped.note ||
      (materialCrossLpa
        ? 'Material cross-LPA overlap requires manual clipping or analyst confirmation.'
        : crossLpaFlag
          ? 'Cross-LPA overlap is present but not currently material.'
          : 'Controlling borough assignment.')
  };
}

function extractWarningMessages(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value
    .map((warning) => {
      if (isRecord(warning)) {
        return toStringValue(warning.message ?? warning.code);
      }
      return toStringValue(warning);
    })
    .filter((warning) => warning.length > 0);
}

function extractWarningCodes(record: Record<string, unknown>): string[] {
  const warningItems = Array.isArray(record.warnings) ? record.warnings : [];
  return warningItems
    .map((warning) => (isRecord(warning) ? toStringValue(warning.code) : ''))
    .filter((warning) => warning.length > 0);
}

function extractReviewFlags(record: Record<string, unknown>, warnings: string[]): string[] {
  const flags = new Set<string>();
  if (Boolean(record.manual_review_required)) {
    flags.add('MANUAL_REVIEW_REQUIRED');
  }

  for (const code of extractWarningCodes(record)) {
    flags.add(code);
  }

  if (warnings.length === 0 && flags.size === 0 && toStringValue(record.site_status) === 'ACTIVE') {
    return [];
  }

  return Array.from(flags);
}

function centroidFromFeature(feature: GeometryFeature): { lat: number; lon: number } {
  const geometry = feature.geometry;
  if (geometry.type === 'Point') {
    return { lon: geometry.coordinates[0], lat: geometry.coordinates[1] };
  }

  const points =
    geometry.type === 'Polygon'
      ? geometry.coordinates.flat()
      : geometry.coordinates.flatMap((polygon) => polygon.flat());
  if (points.length === 0) {
    return { lat: 0, lon: 0 };
  }

  const [lonSum, latSum] = points.reduce<[number, number]>(
    (acc, point) => [acc[0] + point[0], acc[1] + point[1]],
    [0, 0]
  );
  return { lon: lonSum / points.length, lat: latSum / points.length };
}

function formatPriceDisplay(price: number | null, basisType: string): string {
  if (price === null) {
    return 'Price pending';
  }
  const formatted = `£${price.toLocaleString('en-GB')}`;
  return basisType ? `${basisType} · ${formatted}` : formatted;
}

function filterSites(items: SiteSummary[], query: SitesQuery): SiteSummary[] {
  const normalizedQuery = query.q?.trim().toLowerCase();

  return items.filter((item) => {
    if (query.borough && item.borough_name !== query.borough) {
      return false;
    }

    if (query.confidence && item.geometry_confidence !== query.confidence) {
      return false;
    }

    if (query.cluster && item.cluster_id !== query.cluster && item.cluster_key !== query.cluster) {
      return false;
    }

    if (!normalizedQuery) {
      return true;
    }

    const haystack = [
      item.display_name,
      item.borough_name,
      item.controlling_lpa_name,
      item.cluster_key,
      item.current_listing_headline,
      item.current_listing_id,
      item.warnings.join(' '),
      item.review_flags.join(' ')
    ]
      .join(' ')
      .toLowerCase();

    return haystack.includes(normalizedQuery);
  });
}

export async function getSites(query: SitesQuery = {}): Promise<{ items: SiteSummary[]; apiAvailable: boolean }> {
  const result = await queryApiCollection(`/api/sites${buildQueryString(query)}`, mapSiteSummary);
  const base = result.items.length > 0 ? result.items : phase2SiteSummaries;
  return {
    items: filterSites(base, query),
    apiAvailable: result.apiAvailable
  };
}

export async function getSite(siteId: string): Promise<{ item: SiteDetail | null; apiAvailable: boolean }> {
  const payload = await requestJson(`/api/sites/${encodeURIComponent(siteId)}`);
  if (payload) {
    const record = isRecord(payload) && isRecord(payload.data) ? payload.data : payload;
    if (isRecord(record)) {
      return {
        apiAvailable: true,
        item: mapSiteDetail(record)
      };
    }
  }

  return {
    apiAvailable: false,
    item: getPhase2SiteById(siteId)
  };
}

export async function saveSiteGeometry(
  siteId: string,
  input: SiteGeometrySaveInput
): Promise<{ item: SiteDetail | null; apiAvailable: boolean }> {
  const payload = await requestJson(`/api/sites/${encodeURIComponent(siteId)}/geometry`, {
    body: JSON.stringify({
      geom_4326: input.geometry_geojson_4326.geometry,
      source_type: input.geom_source_type,
      confidence: input.geom_confidence,
      reason: input.revision_note,
      created_by: 'web-ui'
    }),
    headers: {
      'Content-Type': 'application/json'
    },
    method: 'POST'
  });

  if (payload) {
    const record = isRecord(payload) && isRecord(payload.data) ? payload.data : payload;
    if (isRecord(record)) {
      return {
        apiAvailable: true,
        item: mapSiteDetail(record)
      };
    }
  }

  return {
    apiAvailable: false,
    item: applyLocalSiteGeometry(siteId, input)
  };
}

export async function getSiteScenarios(
  siteId: string
): Promise<{ items: ScenarioSummary[]; apiAvailable: boolean }> {
  const result = await queryApiCollection(
    `/api/sites/${encodeURIComponent(siteId)}/scenarios`,
    mapScenarioSummary
  );
  return {
    items: result.items,
    apiAvailable: result.apiAvailable
  };
}

export async function suggestSiteScenarios(
  siteId: string,
  input: ScenarioSuggestInput = {}
): Promise<{ item: ScenarioSuggestResponse | null; apiAvailable: boolean }> {
  const payload = await requestJson(`/api/sites/${encodeURIComponent(siteId)}/scenarios/suggest`, {
    body: JSON.stringify({
      requested_by: input.requested_by ?? 'web-ui',
      template_keys: input.template_keys,
      manual_seed: input.manual_seed ?? false
    }),
    headers: {
      'Content-Type': 'application/json'
    },
    method: 'POST'
  });

  return {
    apiAvailable: payload !== null,
    item: payload ? mapScenarioSuggestResponse(payload) : null
  };
}

export async function getScenario(
  scenarioId: string
): Promise<{ item: ScenarioDetail | null; apiAvailable: boolean }> {
  const payload = await requestJson(`/api/scenarios/${encodeURIComponent(scenarioId)}`);
  if (payload && isRecord(payload)) {
    return {
      apiAvailable: true,
      item: mapScenarioDetail(payload)
    };
  }

  return {
    apiAvailable: false,
    item: null
  };
}

export async function confirmScenario(
  scenarioId: string,
  input: ScenarioConfirmInput
): Promise<{ item: ScenarioDetail | null; apiAvailable: boolean }> {
  const payload = await requestJson(`/api/scenarios/${encodeURIComponent(scenarioId)}/confirm`, {
    body: JSON.stringify({
      requested_by: input.requested_by ?? 'web-ui',
      action: input.action ?? 'CONFIRM',
      proposal_form: input.proposal_form,
      units_assumed: input.units_assumed,
      route_assumed: input.route_assumed,
      height_band_assumed: input.height_band_assumed,
      net_developable_area_pct: input.net_developable_area_pct,
      housing_mix_assumed_json: input.housing_mix_assumed_json,
      parking_assumption: input.parking_assumption,
      affordable_housing_assumption: input.affordable_housing_assumption,
      access_assumption: input.access_assumption,
      review_notes: input.review_notes
    }),
    headers: {
      'Content-Type': 'application/json'
    },
    method: 'POST'
  });

  if (payload && isRecord(payload)) {
    return {
      apiAvailable: true,
      item: mapScenarioDetail(payload)
    };
  }

  return {
    apiAvailable: false,
    item: null
  };
}

export async function getAssessments(
  query: AssessmentQuery = {}
): Promise<{ items: AssessmentSummary[]; apiAvailable: boolean }> {
  const result = await queryApiCollection(
    `/api/assessments${buildQueryString(query)}`,
    mapAssessmentSummary
  );
  return {
    items: result.items,
    apiAvailable: result.apiAvailable
  };
}

export async function getAssessment(
  assessmentId: string,
  options: { hidden_mode?: boolean; viewer_role?: AppRole; sessionToken?: string } = {}
): Promise<{ item: AssessmentDetail | null; apiAvailable: boolean }> {
  const payload = await requestJson(
    `/api/assessments/${encodeURIComponent(assessmentId)}${buildQueryString({
      hidden_mode: options.hidden_mode ? true : undefined,
      viewer_role: options.viewer_role
    })}`,
    { sessionToken: options.sessionToken }
  );
  return {
    apiAvailable: payload !== null,
    item: payload ? mapAssessmentDetail(payload) : null
  };
}

export async function createAssessment(
  input: AssessmentCreateInput
): Promise<{ item: AssessmentDetail | null; apiAvailable: boolean }> {
  const payload = await requestJson('/api/assessments', {
    body: JSON.stringify({
      site_id: input.site_id,
      scenario_id: input.scenario_id,
      as_of_date: input.as_of_date,
      requested_by: input.requested_by ?? 'web-ui',
      hidden_mode: input.hidden_mode ?? false,
      viewer_role:
        input.viewer_role ?? (input.hidden_mode ? 'reviewer' : 'analyst')
    }),
    headers: {
      'Content-Type': 'application/json'
    },
    method: 'POST'
  });

  return {
    apiAvailable: payload !== null,
    item: payload ? mapAssessmentDetail(payload) : null
  };
}

export async function getOpportunities(
  query: OpportunitiesQuery & {
    hidden_mode?: boolean;
    viewer_role?: AppRole;
    sessionToken?: string;
  } = {}
): Promise<{ items: OpportunitySummary[]; total: number; apiAvailable: boolean }> {
  const { sessionToken, ...queryValues } = query;
  const payload = await requestJson(`/api/opportunities/${buildQueryString(queryValues)}`, {
    sessionToken
  });
  if (payload && isRecord(payload)) {
    const items = pickCollection(payload.items as ApiCollectionResponse<unknown>).map(
      mapOpportunitySummary
    );
    return {
      items,
      total: toNumberValue(payload.total) ?? items.length,
      apiAvailable: true
    };
  }

  return {
    items: [],
    total: 0,
    apiAvailable: false
  };
}

export async function getOpportunity(
  siteId: string,
  options: { hidden_mode?: boolean; viewer_role?: AppRole; sessionToken?: string } = {}
): Promise<{ item: OpportunityDetail | null; apiAvailable: boolean }> {
  const payload = await requestJson(
    `/api/opportunities/${encodeURIComponent(siteId)}${buildQueryString({
      hidden_mode: options.hidden_mode ? true : undefined,
      viewer_role: options.viewer_role
    })}`,
    { sessionToken: options.sessionToken }
  );
  return {
    apiAvailable: payload !== null,
    item: payload ? mapOpportunityDetail(payload) : null
  };
}

export async function getGoldSetCases(query: {
  review_status?: string;
  template_key?: string;
  sessionToken?: string;
} = {}): Promise<{ items: HistoricalLabelSummary[]; apiAvailable: boolean }> {
  const { sessionToken, ...queryValues } = query;
  const result = await queryApiCollection(
    `/api/admin/gold-set/cases${buildQueryString(queryValues)}`,
    mapHistoricalLabelSummary,
    { sessionToken }
  );
  return {
    items: result.items,
    apiAvailable: result.apiAvailable
  };
}

export async function getGoldSetCase(
  caseId: string,
  options: { sessionToken?: string } = {}
): Promise<{ item: HistoricalLabelCase | null; apiAvailable: boolean }> {
  const payload = await requestJson(`/api/admin/gold-set/cases/${encodeURIComponent(caseId)}`, {
    sessionToken: options.sessionToken
  });
  return {
    apiAvailable: payload !== null,
    item: payload ? mapHistoricalLabelCase(payload) : null
  };
}

export async function getModelReleases(query: {
  template_key?: string;
  sessionToken?: string;
} = {}): Promise<{ items: ModelReleaseSummary[]; apiAvailable: boolean }> {
  const { sessionToken, ...queryValues } = query;
  const result = await queryApiCollection(
    `/api/admin/model-releases${buildQueryString(queryValues)}`,
    mapModelReleaseSummary,
    { sessionToken }
  );
  return {
    items: result.items,
    apiAvailable: result.apiAvailable
  };
}

export async function getModelRelease(
  releaseId: string,
  options: { sessionToken?: string } = {}
): Promise<{ item: ModelReleaseDetail | null; apiAvailable: boolean }> {
  const payload = await requestJson(`/api/admin/model-releases/${encodeURIComponent(releaseId)}`, {
    sessionToken: options.sessionToken
  });
  return {
    apiAvailable: payload !== null,
    item: payload ? mapModelReleaseDetail(payload) : null
  };
}

export async function reviewGoldSetCase(
  caseId: string,
  input: HistoricalLabelReviewInput
): Promise<{ item: HistoricalLabelCase | null; apiAvailable: boolean }> {
  const payload = await requestJson(`/api/admin/gold-set/cases/${encodeURIComponent(caseId)}/review`, {
    body: JSON.stringify({
      review_status: input.review_status,
      review_notes: input.review_notes ?? null,
      notable_policy_issues: input.notable_policy_issues ?? [],
      extant_permission_outcome: input.extant_permission_outcome ?? null,
      site_geometry_confidence: input.site_geometry_confidence ?? null,
      reviewed_by: input.reviewed_by ?? 'web-ui'
    }),
    headers: {
      'Content-Type': 'application/json'
    },
    method: 'POST'
  });

  return {
    apiAvailable: payload !== null,
    item: payload ? mapHistoricalLabelCase(payload) : null
  };
}

export async function overrideAssessment(
  assessmentId: string,
  input: AssessmentOverrideInput
): Promise<{ item: AssessmentDetail | null; apiAvailable: boolean }> {
  const payload = await requestJson(`/api/assessments/${encodeURIComponent(assessmentId)}/override`, {
    body: JSON.stringify({
      requested_by: input.requested_by ?? 'web-ui',
      actor_role: input.actor_role,
      override_type: input.override_type,
      reason: input.reason,
      acquisition_basis_gbp: input.acquisition_basis_gbp,
      acquisition_basis_type: input.acquisition_basis_type,
      valuation_assumption_set_id: input.valuation_assumption_set_id,
      review_resolution_note: input.review_resolution_note,
      resolve_manual_review: input.resolve_manual_review,
      ranking_suppressed: input.ranking_suppressed,
      display_block_reason: input.display_block_reason
    }),
    headers: {
      'Content-Type': 'application/json'
    },
    method: 'POST'
  });

  return {
    apiAvailable: payload !== null,
    item: payload ? mapAssessmentDetail(payload) : null
  };
}

export async function getAssessmentAuditExport(
  assessmentId: string,
  options: { requested_by?: string; actor_role?: AppRole } = {}
): Promise<{ item: AuditExport | null; apiAvailable: boolean }> {
  const payload = await requestJson(
    `/api/assessments/${encodeURIComponent(assessmentId)}/audit-export${buildQueryString({
      requested_by: options.requested_by ?? 'web-ui',
      actor_role: options.actor_role ?? 'reviewer'
    })}`
  );
  return {
    apiAvailable: payload !== null,
    item: payload ? mapAuditExport(payload) : null
  };
}

export async function getReviewQueue(
  options: { sessionToken?: string } = {}
): Promise<{ item: ReviewQueueResponse | null; apiAvailable: boolean }> {
  const payload = await requestJson('/api/admin/review-queue', {
    sessionToken: options.sessionToken
  });
  if (!payload || !isRecord(payload)) {
    return { item: null, apiAvailable: false };
  }
  return {
    apiAvailable: true,
    item: {
      manual_review_cases: pickCollection(payload.manual_review_cases as ApiCollectionResponse<unknown>).map(
        (item) => ({
          assessment_id: isRecord(item) ? toStringValue(item.assessment_id) : '',
          site_id: isRecord(item) ? toStringValue(item.site_id) : '',
          display_name: isRecord(item) ? toStringValue(item.display_name) : '',
          review_status: isRecord(item) ? toStringValue(item.review_status) : '',
          manual_review_required: isRecord(item) ? Boolean(item.manual_review_required) : false,
          visibility_mode:
            isRecord(item) && item.visibility_mode !== null && item.visibility_mode !== undefined
              ? (toStringValue(item.visibility_mode) as VisibilityMode)
              : null
        })
      ),
      blocked_cases: pickCollection(payload.blocked_cases as ApiCollectionResponse<unknown>).map(
        (item) => ({
          assessment_id: isRecord(item) ? toStringValue(item.assessment_id) : '',
          site_id: isRecord(item) ? toStringValue(item.site_id) : '',
          display_name: isRecord(item) ? toStringValue(item.display_name) : '',
          blocked_reason:
            isRecord(item) && item.blocked_reason !== null && item.blocked_reason !== undefined
              ? toStringValue(item.blocked_reason)
              : null,
          visibility_mode:
            isRecord(item) && item.visibility_mode !== null && item.visibility_mode !== undefined
              ? (toStringValue(item.visibility_mode) as VisibilityMode)
              : null,
          display_block_reason:
            isRecord(item) &&
            item.display_block_reason !== null &&
            item.display_block_reason !== undefined
              ? toStringValue(item.display_block_reason)
              : null
        })
      ),
      recent_cases: pickCollection(payload.recent_cases as ApiCollectionResponse<unknown>).map((item) => ({
        assessment_id: isRecord(item) ? toStringValue(item.assessment_id) : '',
        display_name: isRecord(item) ? toStringValue(item.display_name) : '',
        updated_at: isRecord(item) ? toStringValue(item.updated_at) : '',
        estimate_status: isRecord(item) ? toStringValue(item.estimate_status) : '',
        manual_review_required: isRecord(item) ? Boolean(item.manual_review_required) : false
      })),
      failing_boroughs: pickCollection(payload.failing_boroughs as ApiCollectionResponse<unknown>).map(
        (item) => (isRecord(item) ? item : {})
      )
    }
  };
}

export async function getDataHealth(
  options: { sessionToken?: string } = {}
): Promise<{ item: DataHealthResponse | null; apiAvailable: boolean }> {
  const payload = await requestJson('/api/health/data', {
    sessionToken: options.sessionToken
  });
  if (!payload || !isRecord(payload)) {
    return { item: null, apiAvailable: false };
  }
  return {
    item: {
      status: toStringValue(payload.status, 'unknown'),
      connector_failure_rate: toNumberValue(payload.connector_failure_rate),
      listing_parse_success_rate: toNumberValue(payload.listing_parse_success_rate),
      geometry_confidence_distribution: isRecord(payload.geometry_confidence_distribution)
        ? Object.fromEntries(
            Object.entries(payload.geometry_confidence_distribution).map(([key, value]) => [
              key,
              toNumberValue(value) ?? 0
            ])
          )
        : {},
      extant_permission_unresolved_rate: toNumberValue(payload.extant_permission_unresolved_rate),
      borough_baseline_coverage: isRecord(payload.borough_baseline_coverage)
        ? payload.borough_baseline_coverage
        : {},
      coverage: pickCollection(payload.coverage as ApiCollectionResponse<unknown>).map((item) =>
        isRecord(item) ? item : {}
      ),
      baseline_packs: pickCollection(payload.baseline_packs as ApiCollectionResponse<unknown>).map(
        (item) => (isRecord(item) ? item : {})
      ),
      valuation_metrics: {
        total: toNumberValue(
          isRecord(payload.valuation_metrics) ? payload.valuation_metrics.total : null
        ) ?? 0,
        uplift_null_rate: toNumberValue(
          isRecord(payload.valuation_metrics) ? payload.valuation_metrics.uplift_null_rate : null
        ),
        asking_price_missing_rate: toNumberValue(
          isRecord(payload.valuation_metrics)
            ? payload.valuation_metrics.asking_price_missing_rate
            : null
        ),
        valuation_quality_distribution:
          isRecord(payload.valuation_metrics) &&
          isRecord(payload.valuation_metrics.valuation_quality_distribution)
            ? Object.fromEntries(
                Object.entries(payload.valuation_metrics.valuation_quality_distribution).map(
                  ([key, value]) => [key, toNumberValue(value) ?? 0]
                )
              )
            : {}
      }
    },
    apiAvailable: true
  };
}

export async function getModelHealth(
  options: { sessionToken?: string } = {}
): Promise<{ item: ModelHealthResponse | null; apiAvailable: boolean }> {
  const payload = await requestJson('/api/health/model', {
    sessionToken: options.sessionToken
  });
  if (!payload || !isRecord(payload)) {
    return { item: null, apiAvailable: false };
  }
  return {
    item: {
      status: toStringValue(payload.status, 'unknown'),
      calibration_by_probability_band: pickCollection(
        payload.calibration_by_probability_band as ApiCollectionResponse<unknown>
      ).map((item) => (isRecord(item) ? item : {})),
      brier_score: toNumberValue(payload.brier_score),
      log_loss: toNumberValue(payload.log_loss),
      manual_review_agreement_by_band: pickCollection(
        payload.manual_review_agreement_by_band as ApiCollectionResponse<unknown>
      ).map((item) => (isRecord(item) ? item : {})),
      false_positive_reviewer_rate: toNumberValue(payload.false_positive_reviewer_rate),
      abstain_rate: toNumberValue(payload.abstain_rate),
      ood_rate: toNumberValue(payload.ood_rate),
      template_level_performance: pickCollection(
        payload.template_level_performance as ApiCollectionResponse<unknown>
      ).map((item) => (isRecord(item) ? item : {})),
      economic_health: isRecord(payload.economic_health) ? payload.economic_health : {},
      releases: pickCollection(payload.releases as ApiCollectionResponse<unknown>).map((item) =>
        isRecord(item) ? item : {}
      ),
      active_scopes: pickCollection(payload.active_scopes as ApiCollectionResponse<unknown>).map(
        (item) => (isRecord(item) ? item : {})
      )
    },
    apiAvailable: true
  };
}

export async function setReleaseScopeVisibility(
  scopeKey: string,
  input: ReleaseScopeVisibilityInput
): Promise<{ items: ModelReleaseSummary[]; apiAvailable: boolean }> {
  const payload = await requestJson(
    `/api/admin/release-scopes/${encodeURIComponent(scopeKey)}/visibility`,
    {
      body: JSON.stringify({
        requested_by: input.requested_by ?? 'web-ui',
        actor_role: input.actor_role,
        visibility_mode: input.visibility_mode,
        reason: input.reason
      }),
      headers: {
        'Content-Type': 'application/json'
      },
      method: 'POST'
    }
  );

  const items = payload && isRecord(payload)
    ? pickCollection(payload.items as ApiCollectionResponse<unknown>).map(mapModelReleaseSummary)
    : [];
  return {
    items,
    apiAvailable: payload !== null
  };
}

export async function manageReleaseScopeIncident(
  scopeKey: string,
  input: IncidentActionInput
): Promise<{ item: IncidentRecord | null; apiAvailable: boolean }> {
  const payload = await requestJson(
    `/api/admin/release-scopes/${encodeURIComponent(scopeKey)}/incident`,
    {
      body: JSON.stringify({
        requested_by: input.requested_by ?? 'web-ui',
        actor_role: input.actor_role,
        action: input.action,
        reason: input.reason
      }),
      headers: {
        'Content-Type': 'application/json'
      },
      method: 'POST'
    }
  );
  return {
    item: payload ? mapIncidentRecord(payload) : null,
    apiAvailable: payload !== null
  };
}

export async function activateModelRelease(
  releaseId: string,
  options: { requested_by?: string; actor_role?: AppRole } = {}
): Promise<{ item: ModelReleaseDetail | null; apiAvailable: boolean }> {
  const payload = await requestJson(`/api/admin/model-releases/${encodeURIComponent(releaseId)}/activate`, {
    body: JSON.stringify({
      requested_by: options.requested_by ?? 'web-ui',
      actor_role: options.actor_role ?? 'admin'
    }),
    headers: {
      'Content-Type': 'application/json'
    },
    method: 'POST'
  });
  return {
    item: payload ? mapModelReleaseDetail(payload) : null,
    apiAvailable: payload !== null
  };
}

export async function retireModelRelease(
  releaseId: string,
  options: { requested_by?: string; actor_role?: AppRole } = {}
): Promise<{ item: ModelReleaseDetail | null; apiAvailable: boolean }> {
  const payload = await requestJson(`/api/admin/model-releases/${encodeURIComponent(releaseId)}/retire`, {
    body: JSON.stringify({
      requested_by: options.requested_by ?? 'web-ui',
      actor_role: options.actor_role ?? 'admin'
    }),
    headers: {
      'Content-Type': 'application/json'
    },
    method: 'POST'
  });
  return {
    item: payload ? mapModelReleaseDetail(payload) : null,
    apiAvailable: payload !== null
  };
}
