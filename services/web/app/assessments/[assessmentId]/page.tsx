import Link from 'next/link';

import { AssessmentOverridePanel } from '@/components/assessment-override-panel';
import {
  Badge,
  Callout,
  DefinitionList,
  EvidenceList,
  PageHeader,
  Panel,
  ProvenanceList,
  StatCard,
  TableShell
} from '@/components/ui';
import { getAuthContext } from '@/lib/auth/server';
import { getAssessment, type AppRole } from '@/lib/landintel-api';

export const dynamic = 'force-dynamic';

function currency(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return 'Unavailable';
  }

  return `£${Math.round(value).toLocaleString('en-GB')}`;
}

function toneForVisibility(
  mode: string | null | undefined
): 'neutral' | 'accent' | 'success' | 'warning' | 'danger' {
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

function toneForEstimate(value: string | null | undefined): 'neutral' | 'accent' | 'success' | 'warning' | 'danger' {
  if (value === 'PASS' || value === 'HIDDEN_ESTIMATE_AVAILABLE') {
    return 'success';
  }
  if (value === 'ABSTAIN' || value === 'NONE') {
    return 'warning';
  }
  if (value === 'FAIL') {
    return 'danger';
  }
  return 'accent';
}

function canSeeHidden(role: AppRole): boolean {
  return role === 'reviewer' || role === 'admin';
}

function firstValue(value: string | string[] | undefined): string {
  if (Array.isArray(value)) {
    return value[0] ?? '';
  }

  return value ?? '';
}

export default async function AssessmentDetailPage({
  params,
  searchParams
}: {
  params: Promise<{ assessmentId: string }> | { assessmentId: string };
  searchParams?: Promise<Record<string, string | string[] | undefined>> | Record<string, string | string[] | undefined>;
}) {
  const { assessmentId } = await Promise.resolve(params);
  const query = (await Promise.resolve(searchParams ?? {})) as Record<
    string,
    string | string[] | undefined
  >;
  const auth = await getAuthContext();
  const role = (auth.role ?? 'analyst') as AppRole;
  const requestedHidden = firstValue(query.mode).toLowerCase() === 'hidden';
  const hiddenMode = requestedHidden && canSeeHidden(role);

  const result = await getAssessment(assessmentId, {
    hidden_mode: hiddenMode,
    viewer_role: role
  });
  const assessment = result.item;

  if (!assessment) {
    return (
      <div className="page-stack">
        <PageHeader
          eyebrow="Assessments"
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
  const explanation = assessment.result?.result_json?.explanation as Record<string, unknown> | undefined;
  const topPositiveDrivers = Array.isArray(explanation?.top_positive_drivers)
    ? explanation.top_positive_drivers
    : [];
  const topNegativeDrivers = Array.isArray(explanation?.top_negative_drivers)
    ? explanation.top_negative_drivers
    : [];
  const unknowns = Array.isArray(explanation?.unknowns) ? explanation.unknowns : [];
  const overrideSummary = assessment.override_summary;
  const effectiveValuation = overrideSummary?.effective_valuation ?? assessment.valuation;
  const blocked = assessment.visibility?.blocked ?? false;
  const visibilityMode = assessment.visibility?.visibility_mode ?? 'HIDDEN_ONLY';
  const exposureMode = assessment.visibility?.exposure_mode ?? 'REDACTED';
  const probabilityReason =
    blocked
      ? assessment.visibility?.blocked_reason_text ?? 'Visible or hidden publication is blocked for this scope.'
      : assessment.result?.approval_probability_display
        ? hiddenMode
          ? 'Hidden/internal estimate available for this request context.'
          : 'Standard analyst view remains non-speaking/redacted.'
        : assessment.result?.estimate_status === 'NONE'
          ? 'Scoring is not honestly available for this run.'
          : assessment.result?.result_json?.score_execution_reason ?? 'No probability was published.';

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Assessment detail"
        title={
          assessment.site_summary?.display_name
            ? `${assessment.site_summary.display_name} assessment`
            : `Assessment ${assessment.id}`
        }
        summary={
          assessment.note ||
          (assessment.scenario_summary
            ? `${assessment.scenario_summary.template_key} · ${assessment.scenario_summary.units_assumed} units`
            : 'Frozen assessment run')
        }
        actions={
          <div className="page-actions__group">
            <Link className="button button--ghost" href="/assessments">
              Back to assessments
            </Link>
            <Link className="button button--ghost" href={`/sites/${assessment.site_id}`}>
              Open site
            </Link>
            {canSeeHidden(role) ? (
              <Link
                className="button button--ghost"
                href={hiddenMode ? `/assessments/${assessment.id}` : `/assessments/${assessment.id}?mode=hidden`}
              >
                {hiddenMode ? 'Open standard view' : 'Open hidden evaluation'}
              </Link>
            ) : null}
          </div>
        }
        badges={
          <div className="status-strip">
            <Badge tone={toneForEstimate(assessment.result?.estimate_status)}>{assessment.result?.estimate_status ?? 'NONE'}</Badge>
            <Badge tone={toneForReview(overrideSummary?.effective_review_status ?? assessment.review_status)}>
              {overrideSummary?.effective_review_status ?? assessment.review_status}
            </Badge>
            <Badge tone={toneForVisibility(visibilityMode)}>{exposureMode}</Badge>
          </div>
        }
      />

      {!hiddenMode && requestedHidden && !canSeeHidden(role) ? (
        <Callout title="Hidden mode blocked" tone="warning">
          Your current role cannot open hidden/internal probability readback. This page is showing
          the standard redacted view instead.
        </Callout>
      ) : null}

      <section className="stat-grid">
        <StatCard
          tone={toneForEstimate(assessment.result?.estimate_status)}
          label="Eligibility"
          value={assessment.eligibility_status}
          detail={assessment.result?.estimate_status ?? 'Pre-score only'}
        />
        <StatCard
          tone={hiddenMode && assessment.result?.approval_probability_display ? 'danger' : 'accent'}
          label="Probability"
          value={
            hiddenMode
              ? assessment.result?.approval_probability_display ?? 'Unavailable'
              : 'Redacted'
          }
          detail={probabilityReason}
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
          detail={`Post-permission mid ${currency(effectiveValuation?.post_permission_value_mid)}`}
        />
        <StatCard
          tone={assessment.visibility?.replay_verified ? 'success' : 'danger'}
          label="Replay"
          value={assessment.prediction_ledger?.replay_verification_status ?? 'Unknown'}
          detail={assessment.prediction_ledger?.result_payload_hash.slice(0, 12) ?? 'No payload hash'}
        />
      </section>

      <div className="detail-layout">
        <div className="detail-main">
          <div className="split-grid">
            <Panel eyebrow="Overview" title="Scenario statement">
              <DefinitionList
                items={[
                  {
                    label: 'Site',
                    value: assessment.site_summary?.display_name ?? assessment.site_id
                  },
                  {
                    label: 'Scenario',
                    value: assessment.scenario_summary
                      ? `${assessment.scenario_summary.template_key} · ${assessment.scenario_summary.units_assumed} units`
                      : assessment.scenario_id
                  },
                  {
                    label: 'Proposal form',
                    value: assessment.scenario_summary?.proposal_form ?? 'Unavailable'
                  },
                  { label: 'As of date', value: assessment.as_of_date },
                  { label: 'Feature version', value: assessment.feature_snapshot?.feature_version ?? 'Unavailable' },
                  { label: 'Feature hash', value: assessment.feature_snapshot?.feature_hash ?? 'Unavailable' }
                ]}
              />
            </Panel>

            <Panel eyebrow="Eligibility" title="Gate state">
              <DefinitionList
                items={[
                  { label: 'Eligibility', value: assessment.eligibility_status },
                  { label: 'Estimate status', value: assessment.result?.estimate_status ?? 'NONE' },
                  {
                    label: 'Manual review required',
                    value:
                      (overrideSummary?.effective_manual_review_required ??
                        assessment.manual_review_required)
                        ? 'Yes'
                        : 'No'
                  },
                  {
                    label: 'Review status',
                    value: overrideSummary?.effective_review_status ?? assessment.review_status
                  },
                  { label: 'Viewer role', value: role }
                ]}
              />
            </Panel>
          </div>

          <div className="split-grid">
            <Panel eyebrow="Probability and quality" title="Estimate posture">
              <DefinitionList
                items={[
                  {
                    label: 'Display probability',
                    value:
                      hiddenMode
                        ? assessment.result?.approval_probability_display ?? 'Unavailable'
                        : 'Redacted'
                  },
                  {
                    label: 'Raw probability',
                    value:
                      hiddenMode && assessment.result?.approval_probability_raw !== null
                        ? assessment.result?.approval_probability_raw?.toFixed(6) ?? 'Unavailable'
                        : 'Hidden'
                  },
                  { label: 'Estimate quality', value: assessment.result?.estimate_quality ?? 'Unavailable' },
                  { label: 'OOD status', value: assessment.result?.ood_status ?? 'Unavailable' },
                  { label: 'Coverage quality', value: assessment.result?.source_coverage_quality ?? 'Unavailable' },
                  { label: 'Geometry quality', value: assessment.result?.geometry_quality ?? 'Unavailable' },
                  { label: 'Support quality', value: assessment.result?.support_quality ?? 'Unavailable' },
                  { label: 'Scenario quality', value: assessment.result?.scenario_quality ?? 'Unavailable' },
                  { label: 'OOD quality', value: assessment.result?.ood_quality ?? 'Unavailable' }
                ]}
              />
            </Panel>

            <Panel eyebrow="Valuation" title="Residual outcome">
              <DefinitionList
                items={[
                  { label: 'Post-permission low', value: currency(effectiveValuation?.post_permission_value_low) },
                  { label: 'Post-permission mid', value: currency(effectiveValuation?.post_permission_value_mid) },
                  { label: 'Post-permission high', value: currency(effectiveValuation?.post_permission_value_high) },
                  { label: 'Uplift mid', value: currency(effectiveValuation?.uplift_mid) },
                  { label: 'Expected uplift mid', value: currency(effectiveValuation?.expected_uplift_mid) },
                  { label: 'Basis type', value: typeof effectiveValuation?.basis_json?.basis_type === 'string' ? effectiveValuation.basis_json.basis_type : 'Unavailable' },
                  { label: 'Assumption version', value: effectiveValuation?.valuation_assumption_version ?? 'Unavailable' }
                ]}
              />
            </Panel>
          </div>

          <div className="split-grid">
            <Panel eyebrow="Evidence for" title="Supportive evidence">
              <EvidenceList
                items={evidence.for.map((item) => ({
                  label: item.topic,
                  note: item.claim_text,
                  tone: 'success',
                  meta: (
                    <span className="table-secondary">
                      {item.source_label} · {item.verified_status}
                    </span>
                  )
                }))}
                emptyLabel="No supportive evidence was returned for this run."
              />
            </Panel>

            <Panel eyebrow="Evidence against" title="Weakening evidence">
              <EvidenceList
                items={evidence.against.map((item) => ({
                  label: item.topic,
                  note: item.claim_text,
                  tone: 'danger',
                  meta: (
                    <span className="table-secondary">
                      {item.source_label} · {item.verified_status}
                    </span>
                  )
                }))}
                emptyLabel="No weakening evidence was returned for this run."
              />
            </Panel>
          </div>

          <Panel eyebrow="Unknowns" title="Coverage gaps and missing evidence">
            <EvidenceList
              items={[
                ...evidence.unknown.map((item) => ({
                  label: item.topic,
                  note: item.claim_text,
                  tone: 'warning' as const,
                  meta: (
                    <span className="table-secondary">
                      {item.source_label} · {item.verified_status}
                    </span>
                  )
                })),
                ...unknowns.map((item, index) => ({
                  label: `Unknown ${index + 1}`,
                  note: String(item),
                  tone: 'warning' as const,
                  meta: <span className="table-secondary">Model explanation</span>
                }))
              ]}
              emptyLabel="No unknown or gap evidence was returned for this run."
            />
          </Panel>

          <div className="split-grid">
            <Panel eyebrow="Drivers" title="Top positive drivers">
              <EvidenceList
                emptyLabel="No positive drivers were recorded."
                items={topPositiveDrivers.map((item, index) => ({
                  label: `Positive ${index + 1}`,
                  note: typeof item === 'string' ? item : JSON.stringify(item),
                  tone: 'success'
                }))}
              />
            </Panel>

            <Panel eyebrow="Drivers" title="Top negative drivers">
              <EvidenceList
                emptyLabel="No negative drivers were recorded."
                items={topNegativeDrivers.map((item, index) => ({
                  label: `Negative ${index + 1}`,
                  note: typeof item === 'string' ? item : JSON.stringify(item),
                  tone: 'danger'
                }))}
              />
            </Panel>
          </div>

          <div className="split-grid">
            <TableShell
              title="Comparable approved cases"
              note="Explanation infrastructure only. Similarity uses governed interpretable dimensions."
            >
              <div className="dense-table">
                <table className="table-shell">
                  <thead>
                    <tr>
                      <th>Reference</th>
                      <th>Similarity</th>
                      <th>Fallback</th>
                      <th>Decision</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(comparables?.approved_members ?? []).map((item) => (
                      <tr key={item.id}>
                        <td>
                          <div className="table-primary">{item.planning_application.external_ref}</div>
                          <div className="table-secondary">
                            {item.planning_application.proposal_description}
                          </div>
                        </td>
                        <td>
                          <div className="table-primary">{item.similarity_score.toFixed(3)}</div>
                          <div className="table-secondary">Rank {item.rank}</div>
                        </td>
                        <td>{item.fallback_path}</td>
                        <td>{item.planning_application.decision ?? 'Unavailable'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </TableShell>

            <TableShell
              title="Comparable refused cases"
              note="Refused cases remain visible so the analyst can inspect contrary support."
            >
              <div className="dense-table">
                <table className="table-shell">
                  <thead>
                    <tr>
                      <th>Reference</th>
                      <th>Similarity</th>
                      <th>Fallback</th>
                      <th>Decision</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(comparables?.refused_members ?? []).map((item) => (
                      <tr key={item.id}>
                        <td>
                          <div className="table-primary">{item.planning_application.external_ref}</div>
                          <div className="table-secondary">
                            {item.planning_application.proposal_description}
                          </div>
                        </td>
                        <td>
                          <div className="table-primary">{item.similarity_score.toFixed(3)}</div>
                          <div className="table-secondary">Rank {item.rank}</div>
                        </td>
                        <td>{item.fallback_path}</td>
                        <td>{item.planning_application.decision ?? 'Unavailable'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </TableShell>
          </div>
        </div>

        <div className="detail-rail">
          <Panel eyebrow="Visibility" title="Release and gate state" compact>
            <DefinitionList
              compact
              items={[
                { label: 'Visibility mode', value: visibilityMode },
                { label: 'Exposure mode', value: exposureMode },
                { label: 'Blocked', value: blocked ? 'Yes' : 'No' },
                {
                  label: 'Blocked reason',
                  value: assessment.visibility?.blocked_reason_text ?? 'None'
                },
                {
                  label: 'Replay verified',
                  value: assessment.visibility?.replay_verified ? 'Yes' : 'No'
                }
              ]}
            />
          </Panel>

          <Panel eyebrow="Provenance" title="Ledger and artifacts" compact>
            <ProvenanceList
              items={[
                {
                  label: 'Feature hash',
                  value: assessment.prediction_ledger?.feature_hash ?? 'Unavailable'
                },
                {
                  label: 'Payload hash',
                  value: assessment.prediction_ledger?.result_payload_hash ?? 'Unavailable'
                },
                {
                  label: 'Model artifact hash',
                  value: assessment.prediction_ledger?.model_artifact_hash ?? 'Unavailable'
                },
                {
                  label: 'Validation artifact hash',
                  value: assessment.prediction_ledger?.validation_artifact_hash ?? 'Unavailable'
                }
              ]}
            />
          </Panel>

          <Panel eyebrow="Frozen payload" title="Raw snapshots" compact>
            <div className="details-block">
              <details className="json-details">
                <summary>Feature payload</summary>
                <pre className="code-block">
                  {JSON.stringify(assessment.feature_snapshot?.feature_json ?? {}, null, 2)}
                </pre>
              </details>
              <details className="json-details">
                <summary>Result payload</summary>
                <pre className="code-block">
                  {JSON.stringify(assessment.result?.result_json ?? {}, null, 2)}
                </pre>
              </details>
              <details className="json-details">
                <summary>Valuation payload</summary>
                <pre className="code-block">
                  {JSON.stringify(effectiveValuation?.result_json ?? {}, null, 2)}
                </pre>
              </details>
            </div>
          </Panel>
        </div>
      </div>

      <AssessmentOverridePanel
        activeOverrides={overrideSummary?.active_overrides ?? []}
        assessmentId={assessment.id}
        currentAssumptionVersion={effectiveValuation?.valuation_assumption_version ?? null}
        currentBasisType={
          typeof effectiveValuation?.basis_json?.basis_type === 'string'
            ? effectiveValuation.basis_json.basis_type
            : null
        }
        currentRole={role}
        manualReviewRequired={
          overrideSummary?.effective_manual_review_required ?? assessment.manual_review_required
        }
        visibility={assessment.visibility}
      />
    </div>
  );
}
