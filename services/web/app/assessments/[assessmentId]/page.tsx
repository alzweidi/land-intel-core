import Link from 'next/link';

import { AssessmentOverridePanel } from '@/components/assessment-override-panel';
import { Badge, DefinitionList, PageHeader, Panel, StatCard } from '@/components/ui';
import { getAssessment, type AppRole } from '@/lib/landintel-api';

export const dynamic = 'force-dynamic';

function formatList(items: string[]): string {
  return items.length > 0 ? items.join(', ') : 'None recorded';
}

function formatCurrency(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return 'Unavailable';
  }

  return `£${Math.round(value).toLocaleString('en-GB')}`;
}

function toneForVisibility(mode: string | null | undefined): 'neutral' | 'accent' | 'success' | 'warning' | 'danger' {
  if (mode === 'VISIBLE_REVIEWER_ONLY') {
    return 'success';
  }
  if (mode === 'HIDDEN_ONLY') {
    return 'accent';
  }
  if (mode === 'DISABLED') {
    return 'danger';
  }
  return 'neutral';
}

function toneForReview(value: string): 'neutral' | 'accent' | 'success' | 'warning' | 'danger' {
  if (value === 'NOT_REQUIRED' || value === 'COMPLETED') {
    return 'success';
  }
  if (value === 'REQUIRED') {
    return 'warning';
  }
  return 'accent';
}

function parseViewerRole(
  searchParams?: Record<string, string | string[] | undefined>,
  hiddenMode?: boolean
): AppRole {
  if (typeof searchParams?.role === 'string') {
    if (searchParams.role === 'admin' || searchParams.role === 'reviewer' || searchParams.role === 'analyst') {
      return searchParams.role;
    }
  }
  return hiddenMode ? 'reviewer' : 'analyst';
}

export default async function AssessmentDetailPage({
  params,
  searchParams
}: {
  params: Promise<{ assessmentId: string }> | { assessmentId: string };
  searchParams?: Record<string, string | string[] | undefined>;
}) {
  const { assessmentId } = await Promise.resolve(params);
  const hiddenMode =
    typeof searchParams?.mode === 'string' && searchParams.mode.toLowerCase() === 'hidden';
  const viewerRole = parseViewerRole(searchParams, hiddenMode);
  const result = await getAssessment(assessmentId, {
    hidden_mode: hiddenMode,
    viewer_role: viewerRole,
  });
  const assessment = result.item;

  if (!assessment) {
    return (
      <div className="page-stack">
        <PageHeader
          eyebrow="Phase 8A"
          title="Assessment not found"
          summary={`No frozen assessment run is available for ${assessmentId}.`}
          actions={
            <Link className="button button--ghost" href="/assessments">
              Back to assessments
            </Link>
          }
        />
      </div>
    );
  }

  const evidence = assessment.evidence ?? { for: [], against: [], unknown: [] };
  const comparables = assessment.comparable_case_set;
  const featureValues = (assessment.feature_snapshot?.feature_json.values ?? {}) as Record<string, unknown>;
  const sourceCoverage = assessment.feature_snapshot?.coverage_json.source_coverage;
  const hiddenExplanation = assessment.result?.result_json?.explanation as Record<string, unknown> | undefined;
  const topPositiveDrivers = Array.isArray(hiddenExplanation?.top_positive_drivers)
    ? hiddenExplanation.top_positive_drivers
    : [];
  const topNegativeDrivers = Array.isArray(hiddenExplanation?.top_negative_drivers)
    ? hiddenExplanation.top_negative_drivers
    : [];
  const unknowns = Array.isArray(hiddenExplanation?.unknowns) ? hiddenExplanation.unknowns : [];
  const overrideSummary = assessment.override_summary;
  const effectiveValuation = overrideSummary?.effective_valuation ?? assessment.valuation;
  const visibleModeBadge = assessment.visibility?.visibility_mode ?? 'HIDDEN_ONLY';
  const exposureMode = assessment.visibility?.exposure_mode ?? 'REDACTED';
  const blocked = assessment.visibility?.blocked ?? false;
  const redactionNote = blocked
    ? assessment.visibility?.blocked_reason_text ?? 'Visible publication is blocked.'
    : exposureMode === 'VISIBLE_REVIEWER_ONLY'
      ? 'Reviewer-visible rounded probability is allowed for this scope.'
      : hiddenMode
        ? 'Hidden internal evaluation mode is active for this view.'
        : 'Standard analyst view remains non-speaking/redacted.';

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Phase 8A"
        title={`Assessment ${assessment.id}`}
        summary={assessment.note}
        actions={
          <div className="page-actions__group">
            <Link className="button button--ghost" href="/assessments">
              Back to assessments
            </Link>
            <Link
              className="button button--ghost"
              href={
                hiddenMode
                  ? `/assessments/${assessment.id}`
                  : `/assessments/${assessment.id}?mode=hidden&role=reviewer`
              }
            >
              {hiddenMode ? 'Open standard view' : 'Open hidden evaluation mode'}
            </Link>
            <Link className="button button--ghost" href="/admin/model-releases">
              Model releases
            </Link>
            {assessment.site_summary ? (
              <Link className="button button--ghost" href={`/sites/${assessment.site_summary.site_id}`}>
                Open site detail
              </Link>
            ) : null}
          </div>
        }
      />

      <section className="stat-grid">
        <StatCard
          tone={blocked ? 'danger' : hiddenMode ? 'danger' : 'accent'}
          label="Visibility"
          value={visibleModeBadge}
          detail={redactionNote}
        />
        <StatCard
          tone={toneForReview(overrideSummary?.effective_review_status ?? assessment.review_status)}
          label="Review"
          value={overrideSummary?.effective_review_status ?? assessment.review_status}
          detail={
            overrideSummary?.effective_manual_review_required ?? assessment.manual_review_required
              ? 'Manual review remains required or was explicitly resolved via override.'
              : 'No manual review requirement is currently active.'
          }
        />
        <StatCard
          tone="accent"
          label="Comparables"
          value={String((comparables?.approved_count ?? 0) + (comparables?.refused_count ?? 0))}
          detail="Explanation infrastructure only, not a substitute model"
        />
        <StatCard
          tone={
            effectiveValuation?.valuation_quality === 'HIGH'
              ? 'success'
              : effectiveValuation?.valuation_quality === 'MEDIUM'
                ? 'accent'
                : 'warning'
          }
          label="Valuation"
          value={effectiveValuation?.valuation_quality ?? 'Unavailable'}
          detail={
            overrideSummary?.effective_valuation
              ? 'An active override changes the effective valuation shown here.'
              : 'Original immutable valuation run.'
          }
        />
        <StatCard
          tone={assessment.visibility?.replay_verified ? 'success' : 'danger'}
          label="Replay"
          value={assessment.prediction_ledger?.replay_verification_status ?? 'Unknown'}
          detail={assessment.prediction_ledger?.result_payload_hash.slice(0, 12) ?? 'No payload hash'}
        />
      </section>

      <div className="split-grid">
        <Panel
          eyebrow="Visibility gate"
          title="Exposure and blocking state"
          note={<Badge tone={toneForVisibility(visibleModeBadge)}>{exposureMode}</Badge>}
        >
          <DefinitionList
            items={[
              { label: 'Viewer role', value: viewerRole },
              { label: 'Scope key', value: assessment.visibility?.scope_key ?? 'Unavailable' },
              { label: 'Blocked', value: blocked ? 'Yes' : 'No' },
              { label: 'Blocked reason', value: assessment.visibility?.blocked_reason_text ?? 'None' },
              { label: 'Replay verified', value: assessment.visibility?.replay_verified ? 'Yes' : 'No' },
              { label: 'Artifact hashes match', value: assessment.visibility?.artifact_hashes_match ? 'Yes' : 'No' },
              { label: 'Scope/release match', value: assessment.visibility?.scope_release_matches_result ? 'Yes' : 'No' },
            ]}
          />
        </Panel>

        <Panel eyebrow="Run" title="Frozen metadata">
          <DefinitionList
            items={[
              { label: 'Site', value: assessment.site_summary?.display_name ?? assessment.site_id },
              {
                label: 'Scenario',
                value: assessment.scenario_summary
                  ? `${assessment.scenario_summary.template_key} · ${assessment.scenario_summary.units_assumed} units`
                  : assessment.scenario_id
              },
              { label: 'As-of date', value: assessment.as_of_date },
              { label: 'Eligibility', value: assessment.eligibility_status },
              { label: 'Feature version', value: assessment.feature_snapshot?.feature_version ?? 'Unavailable' },
              { label: 'Feature hash', value: assessment.feature_snapshot?.feature_hash ?? 'Unavailable' }
            ]}
          />
        </Panel>
      </div>

      <AssessmentOverridePanel
        assessmentId={assessment.id}
        activeOverrides={overrideSummary?.active_overrides ?? []}
        visibility={assessment.visibility}
        currentAssumptionVersion={effectiveValuation?.valuation_assumption_version ?? null}
        currentBasisType={
          typeof effectiveValuation?.basis_json?.basis_type === 'string'
            ? effectiveValuation.basis_json.basis_type
            : null
        }
        manualReviewRequired={
          overrideSummary?.effective_manual_review_required ?? assessment.manual_review_required
        }
      />

      <div className="split-grid">
        <Panel eyebrow="Original" title="Original frozen result">
          <DefinitionList
            items={[
              { label: 'Estimate status', value: assessment.result?.estimate_status ?? 'NONE' },
              { label: 'Display probability', value: assessment.result?.approval_probability_display ?? 'Redacted' },
              { label: 'Estimate quality', value: assessment.result?.estimate_quality ?? 'Unavailable' },
              { label: 'Review status', value: assessment.review_status },
              { label: 'Expected uplift', value: formatCurrency(assessment.valuation?.expected_uplift_mid) },
              { label: 'Valuation quality', value: assessment.valuation?.valuation_quality ?? 'Unavailable' },
            ]}
          />
        </Panel>

        <Panel eyebrow="Effective" title="Override-adjusted readback">
          <DefinitionList
            items={[
              { label: 'Review status', value: overrideSummary?.effective_review_status ?? assessment.review_status },
              {
                label: 'Manual review required',
                value:
                  (overrideSummary?.effective_manual_review_required ?? assessment.manual_review_required)
                    ? 'Yes'
                    : 'No'
              },
              { label: 'Expected uplift', value: formatCurrency(effectiveValuation?.expected_uplift_mid) },
              { label: 'Uplift mid', value: formatCurrency(effectiveValuation?.uplift_mid) },
              { label: 'Valuation quality', value: effectiveValuation?.valuation_quality ?? 'Unavailable' },
              { label: 'Ranking suppression', value: overrideSummary?.ranking_suppressed ? 'Yes' : 'No' },
            ]}
          />
        </Panel>
      </div>

      <div className="split-grid">
        <Panel eyebrow="Provenance" title="Replay-safe ledger">
          <DefinitionList
            items={[
              { label: 'Geometry hash', value: assessment.prediction_ledger?.site_geom_hash ?? 'Unavailable' },
              { label: 'Payload hash', value: assessment.prediction_ledger?.result_payload_hash ?? 'Unavailable' },
              { label: 'Model artifact hash', value: assessment.prediction_ledger?.model_artifact_hash ?? 'Unavailable' },
              { label: 'Validation artifact hash', value: assessment.prediction_ledger?.validation_artifact_hash ?? 'Unavailable' },
              { label: 'Source snapshots', value: formatList(assessment.prediction_ledger?.source_snapshot_ids_json ?? []) },
              { label: 'Raw assets', value: formatList(assessment.prediction_ledger?.raw_asset_ids_json ?? []) }
            ]}
          />
        </Panel>

        <Panel eyebrow="Valuation" title="Residual valuation summary">
          <DefinitionList
            items={[
              { label: 'Post-permission low', value: formatCurrency(effectiveValuation?.post_permission_value_low) },
              { label: 'Post-permission mid', value: formatCurrency(effectiveValuation?.post_permission_value_mid) },
              { label: 'Post-permission high', value: formatCurrency(effectiveValuation?.post_permission_value_high) },
              { label: 'Uplift mid', value: formatCurrency(effectiveValuation?.uplift_mid) },
              { label: 'Expected uplift mid', value: formatCurrency(effectiveValuation?.expected_uplift_mid) },
              { label: 'Valuation quality', value: effectiveValuation?.valuation_quality ?? 'Unavailable' },
              { label: 'Basis type', value: typeof effectiveValuation?.basis_json?.basis_type === 'string' ? effectiveValuation.basis_json.basis_type : 'Unavailable' },
              { label: 'Assumption version', value: effectiveValuation?.valuation_assumption_version ?? 'Unavailable' },
            ]}
          />
          <pre className="code-block" style={{ marginTop: 16, whiteSpace: 'pre-wrap' }}>
            {JSON.stringify(effectiveValuation?.sense_check_json ?? {}, null, 2)}
          </pre>
        </Panel>
      </div>

      <div className="split-grid">
        <Panel eyebrow="Features" title="Frozen feature summary">
          <DefinitionList
            items={[
              {
                label: 'Site area',
                value:
                  typeof featureValues?.site_area_sqm === 'number'
                    ? `${featureValues.site_area_sqm.toLocaleString('en-GB')} sqm`
                    : 'Unknown'
              },
              {
                label: 'Units assumed',
                value:
                  typeof featureValues?.scenario_units_assumed === 'number'
                    ? featureValues.scenario_units_assumed
                    : assessment.scenario_summary?.units_assumed ?? 'Unknown'
              },
              {
                label: 'Proposal form',
                value:
                  typeof featureValues?.scenario_proposal_form === 'string'
                    ? featureValues.scenario_proposal_form
                    : assessment.scenario_summary?.proposal_form ?? 'Unknown'
              },
              { label: 'Coverage rows', value: Array.isArray(sourceCoverage) ? sourceCoverage.length : 0 }
            ]}
          />
          <pre className="code-block" style={{ marginTop: 16, whiteSpace: 'pre-wrap' }}>
            {JSON.stringify(assessment.feature_snapshot?.feature_json ?? {}, null, 2)}
          </pre>
        </Panel>

        <Panel eyebrow="Result payload" title={hiddenMode ? 'Hidden/internal result view' : 'Standard result view'}>
          <DefinitionList
            items={[
              { label: 'Estimate status', value: assessment.result?.estimate_status ?? 'NONE' },
              { label: 'Coverage quality', value: assessment.result?.source_coverage_quality ?? 'Unknown' },
              { label: 'Geometry quality', value: assessment.result?.geometry_quality ?? 'Unknown' },
              { label: 'Support quality', value: assessment.result?.support_quality ?? 'Unknown' },
              { label: 'Scenario quality', value: assessment.result?.scenario_quality ?? 'Unknown' },
              { label: 'OOD quality', value: assessment.result?.ood_quality ?? 'Unknown' }
            ]}
          />
          <pre className="code-block" style={{ marginTop: 16, whiteSpace: 'pre-wrap' }}>
            {JSON.stringify(assessment.result?.result_json ?? {}, null, 2)}
          </pre>
        </Panel>
      </div>

      <div className="split-grid">
        <Panel eyebrow="Drivers" title="Top positive drivers">
          {topPositiveDrivers.length === 0 ? (
            <p className="empty-note">No positive driver explanation is available.</p>
          ) : (
            <div className="card-stack">
              {topPositiveDrivers.map((item, index) => (
                <article className="mini-card" key={`positive-${index}`}>
                  <div className="table-primary">
                    {typeof item === 'object' && item !== null && 'feature' in item ? String((item as { feature: unknown }).feature) : 'Driver'}
                  </div>
                  <div className="table-secondary">{JSON.stringify(item)}</div>
                </article>
              ))}
            </div>
          )}
        </Panel>

        <Panel eyebrow="Drivers" title="Top negative drivers">
          {topNegativeDrivers.length === 0 ? (
            <p className="empty-note">No negative driver explanation is available.</p>
          ) : (
            <div className="card-stack">
              {topNegativeDrivers.map((item, index) => (
                <article className="mini-card" key={`negative-${index}`}>
                  <div className="table-primary">
                    {typeof item === 'object' && item !== null && 'feature' in item ? String((item as { feature: unknown }).feature) : 'Driver'}
                  </div>
                  <div className="table-secondary">{JSON.stringify(item)}</div>
                </article>
              ))}
            </div>
          )}
        </Panel>
      </div>

      <div className="split-grid">
        <Panel eyebrow="Unknowns" title="Missing evidence and unknowns">
          {unknowns.length === 0 ? (
            <p className="empty-note">No unknown-driver list is available.</p>
          ) : (
            <div className="card-stack">
              {unknowns.map((item, index) => (
                <article className="mini-card" key={`unknown-${index}`}>
                  <div className="table-secondary">{JSON.stringify(item)}</div>
                </article>
              ))}
            </div>
          )}
        </Panel>

        <Panel eyebrow="Comparables" title="Comparable set">
          <DefinitionList
            items={[
              { label: 'Approved', value: comparables?.approved_count ?? 0 },
              { label: 'Refused', value: comparables?.refused_count ?? 0 },
              { label: 'Same-borough support', value: comparables?.same_borough_count ?? 0 },
              { label: 'London-wide support', value: comparables?.london_count ?? 0 },
            ]}
          />
        </Panel>
      </div>

      <div className="split-grid">
        <Panel eyebrow="Evidence" title="Evidence FOR">
          <div className="card-stack">
            {evidence.for.slice(0, 6).map((item, index) => (
              <article className="mini-card" key={`for-${index}`}>
                <div className="table-primary">{item.topic}</div>
                <div className="table-secondary">{item.claim_text}</div>
              </article>
            ))}
          </div>
        </Panel>

        <Panel eyebrow="Evidence" title="Evidence AGAINST / UNKNOWN">
          <div className="card-stack">
            {[...evidence.against.slice(0, 3), ...evidence.unknown.slice(0, 3)].map((item, index) => (
              <article className="mini-card" key={`mixed-${index}`}>
                <div className="table-primary">{item.topic}</div>
                <div className="table-secondary">{item.claim_text}</div>
              </article>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  );
}
