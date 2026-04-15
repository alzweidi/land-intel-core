import Link from 'next/link';

import { Badge, DefinitionList, PageHeader, Panel, StatCard } from '@/components/ui';
import { getAssessment } from '@/lib/landintel-api';

export const dynamic = 'force-dynamic';

function reviewTone(value: string): 'neutral' | 'accent' | 'success' | 'warning' | 'danger' {
  if (value === 'NOT_REQUIRED') {
    return 'success';
  }

  if (value === 'REQUIRED') {
    return 'warning';
  }

  return 'accent';
}

function formatList(items: string[]): string {
  return items.length > 0 ? items.join(', ') : 'None recorded';
}

export default async function AssessmentDetailPage({
  params,
  searchParams
}: {
  params: { assessmentId: string };
  searchParams?: Record<string, string | string[] | undefined>;
}) {
  const hiddenMode =
    typeof searchParams?.mode === 'string' && searchParams.mode.toLowerCase() === 'hidden';
  const result = await getAssessment(params.assessmentId, {
    hidden_mode: hiddenMode
  });
  const assessment = result.item;

  if (!assessment) {
    return (
      <div className="page-stack">
        <PageHeader
          eyebrow="Phase 6A"
          title="Assessment not found"
          summary={`No frozen assessment run is available for ${params.assessmentId}.`}
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
  const featureValues = (assessment.feature_snapshot?.feature_json.values ?? {}) as Record<
    string,
    unknown
  >;
  const sourceCoverage = assessment.feature_snapshot?.coverage_json.source_coverage;
  const hiddenExplanation = assessment.result?.result_json?.explanation as
    | Record<string, unknown>
    | undefined;
  const topPositiveDrivers = Array.isArray(hiddenExplanation?.top_positive_drivers)
    ? hiddenExplanation.top_positive_drivers
    : [];
  const topNegativeDrivers = Array.isArray(hiddenExplanation?.top_negative_drivers)
    ? hiddenExplanation.top_negative_drivers
    : [];
  const unknowns = Array.isArray(hiddenExplanation?.unknowns) ? hiddenExplanation.unknowns : [];

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Phase 6A"
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
                  : `/assessments/${assessment.id}?mode=hidden`
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
          tone={hiddenMode ? 'danger' : 'accent'}
          label="Estimate"
          value={assessment.estimate_status}
          detail={
            hiddenMode
              ? 'Hidden internal estimate mode. The result remains non-speaking and not for standard analyst use.'
              : 'Standard view stays redacted even when a hidden internal estimate exists.'
          }
        />
        <StatCard tone={reviewTone(assessment.review_status)} label="Review" value={assessment.review_status} detail={assessment.manual_review_required ? 'Analyst review is currently required' : 'No additional review flags are set'} />
        <StatCard tone="accent" label="Comparables" value={String((comparables?.approved_count ?? 0) + (comparables?.refused_count ?? 0))} detail="Explanation infrastructure only, not a substitute model" />
        <StatCard tone="success" label="Replay hash" value={assessment.prediction_ledger?.result_payload_hash.slice(0, 12) ?? 'Unavailable'} detail="Stable payload hash for replay verification" />
      </section>

      {hiddenMode ? (
        <Panel
          eyebrow="Hidden mode"
          title="Internal evaluation only"
          note="This surface exposes the hidden Phase 6A score path. Standard analyst workflows remain non-speaking."
        >
          <DefinitionList
            items={[
              {
                label: 'Rounded hidden probability',
                value: assessment.result?.approval_probability_display ?? 'Unavailable'
              },
              {
                label: 'Estimate quality',
                value: assessment.result?.estimate_quality ?? 'Unavailable'
              },
              {
                label: 'OOD status',
                value: assessment.result?.ood_status ?? 'Unavailable'
              },
              {
                label: 'Manual review',
                value: assessment.manual_review_required ? 'Required' : 'Not required'
              },
              {
                label: 'Model release',
                value: assessment.result?.model_release_id ?? 'No active hidden release'
              },
              {
                label: 'Release scope',
                value: assessment.result?.release_scope_key ?? 'Unavailable'
              }
            ]}
          />
        </Panel>
      ) : null}

      <div className="split-grid">
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

        <Panel eyebrow="Provenance" title="Replay-safe ledger">
          <DefinitionList
            items={[
              { label: 'Geometry hash', value: assessment.prediction_ledger?.site_geom_hash ?? 'Unavailable' },
              { label: 'Payload hash', value: assessment.prediction_ledger?.result_payload_hash ?? 'Unavailable' },
              {
                label: 'Source snapshots',
                value: formatList(assessment.prediction_ledger?.source_snapshot_ids_json ?? [])
              },
              {
                label: 'Raw assets',
                value: formatList(assessment.prediction_ledger?.raw_asset_ids_json ?? [])
              }
            ]}
          />
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
              {
                label: 'Coverage rows',
                value: Array.isArray(sourceCoverage) ? sourceCoverage.length : 0
              }
            ]}
          />
          <pre className="code-block" style={{ marginTop: 16, whiteSpace: 'pre-wrap' }}>
            {JSON.stringify(assessment.feature_snapshot?.feature_json ?? {}, null, 2)}
          </pre>
        </Panel>

        <Panel eyebrow="Result" title={hiddenMode ? 'Hidden estimate status' : 'Standard result view'}>
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

      {hiddenMode ? (
        <div className="split-grid">
          <Panel eyebrow="Drivers" title="Top positive drivers">
            <div className="card-stack">
              {topPositiveDrivers.length === 0 ? (
                <p className="empty-note">No positive driver detail is available for this hidden run.</p>
              ) : (
                topPositiveDrivers.map((item, index) => {
                  const driver = item as Record<string, unknown>;
                  return (
                    <article className="mini-card" key={`positive-${index}`}>
                      <div className="mini-card__top">
                        <div>
                          <div className="table-primary">{String(driver.label ?? driver.feature ?? 'Driver')}</div>
                          <div className="table-secondary">{String(driver.feature ?? 'Unknown feature')}</div>
                        </div>
                        <Badge tone="success">{String(driver.contribution ?? 'n/a')}</Badge>
                      </div>
                    </article>
                  );
                })
              )}
            </div>
          </Panel>

          <Panel eyebrow="Drivers" title="Top negative drivers">
            <div className="card-stack">
              {topNegativeDrivers.length === 0 ? (
                <p className="empty-note">No negative driver detail is available for this hidden run.</p>
              ) : (
                topNegativeDrivers.map((item, index) => {
                  const driver = item as Record<string, unknown>;
                  return (
                    <article className="mini-card" key={`negative-${index}`}>
                      <div className="mini-card__top">
                        <div>
                          <div className="table-primary">{String(driver.label ?? driver.feature ?? 'Driver')}</div>
                          <div className="table-secondary">{String(driver.feature ?? 'Unknown feature')}</div>
                        </div>
                        <Badge tone="danger">{String(driver.contribution ?? 'n/a')}</Badge>
                      </div>
                    </article>
                  );
                })
              )}
            </div>
          </Panel>
        </div>
      ) : null}

      {hiddenMode ? (
        <Panel eyebrow="Unknowns" title="Missing evidence and unresolved inputs">
          <div className="card-stack">
            {unknowns.length === 0 ? (
              <p className="empty-note">No missing model inputs were emitted for this hidden run.</p>
            ) : (
              unknowns.map((item, index) => {
                const unknown = item as Record<string, unknown>;
                return (
                  <article className="mini-card" key={`unknown-${index}`}>
                    <div className="table-primary">{String(unknown.label ?? unknown.feature ?? 'Unknown')}</div>
                    <div className="table-secondary">{String(unknown.feature ?? 'Unknown feature')}</div>
                  </article>
                );
              })
            )}
          </div>
        </Panel>
      ) : null}

      <div className="split-grid">
        <Panel eyebrow="Evidence FOR" title="Supporting evidence">
          <div className="card-stack">
            {evidence.for.length === 0 ? (
              <p className="empty-note">No supporting evidence was assembled for this frozen run.</p>
            ) : (
              evidence.for.map((item, index) => (
                <article className="mini-card" key={`${item.topic}-${index}`}>
                  <div className="mini-card__top">
                    <div>
                      <div className="table-primary">{item.claim_text}</div>
                      <div className="table-secondary">{item.topic}</div>
                    </div>
                    <Badge tone="success">{item.importance}</Badge>
                  </div>
                  <div className="table-secondary">
                    {item.source_url ? (
                      <a href={item.source_url} rel="noreferrer" target="_blank">
                        {item.source_label}
                      </a>
                    ) : (
                      item.source_label
                    )}
                  </div>
                </article>
              ))
            )}
          </div>
        </Panel>

        <Panel eyebrow="Evidence AGAINST" title="Constraining evidence">
          <div className="card-stack">
            {evidence.against.length === 0 ? (
              <p className="empty-note">No constraining evidence was assembled for this frozen run.</p>
            ) : (
              evidence.against.map((item, index) => (
                <article className="mini-card" key={`${item.topic}-${index}`}>
                  <div className="mini-card__top">
                    <div>
                      <div className="table-primary">{item.claim_text}</div>
                      <div className="table-secondary">{item.topic}</div>
                    </div>
                    <Badge tone="danger">{item.importance}</Badge>
                  </div>
                  <div className="table-secondary">
                    {item.source_url ? (
                      <a href={item.source_url} rel="noreferrer" target="_blank">
                        {item.source_label}
                      </a>
                    ) : (
                      item.source_label
                    )}
                  </div>
                </article>
              ))
            )}
          </div>
        </Panel>
      </div>

      <Panel eyebrow="Evidence UNKNOWN" title="Coverage and freshness caveats">
        <div className="card-stack">
          {evidence.unknown.length === 0 ? (
            <p className="empty-note">No unresolved evidence items were assembled for this run.</p>
          ) : (
            evidence.unknown.map((item, index) => (
              <article className="mini-card" key={`${item.topic}-${index}`}>
                <div className="mini-card__top">
                  <div>
                    <div className="table-primary">{item.claim_text}</div>
                    <div className="table-secondary">{item.topic}</div>
                  </div>
                  <Badge tone="warning">{item.importance}</Badge>
                </div>
                <div className="table-secondary">{item.excerpt_text ?? item.source_label}</div>
              </article>
            ))
          )}
        </div>
      </Panel>

      <div className="split-grid">
        <Panel eyebrow="Comparables" title="Approved cases">
          <div className="card-stack">
            {(comparables?.approved_members ?? []).length === 0 ? (
              <p className="empty-note">No approved comparables met the current fallback rules.</p>
            ) : (
              comparables?.approved_members.map((member) => (
                <article className="mini-card" key={member.id}>
                  <div className="mini-card__top">
                    <div>
                      <div className="table-primary">{member.planning_application.external_ref}</div>
                      <div className="table-secondary">{member.planning_application.proposal_description}</div>
                    </div>
                    <Badge tone="success">#{member.rank}</Badge>
                  </div>
                  <div className="table-secondary">
                    {member.fallback_path} · score {member.similarity_score.toFixed(2)}
                  </div>
                </article>
              ))
            )}
          </div>
        </Panel>

        <Panel eyebrow="Comparables" title="Refused cases">
          <div className="card-stack">
            {(comparables?.refused_members ?? []).length === 0 ? (
              <p className="empty-note">No refused comparables met the current fallback rules.</p>
            ) : (
              comparables?.refused_members.map((member) => (
                <article className="mini-card" key={member.id}>
                  <div className="mini-card__top">
                    <div>
                      <div className="table-primary">{member.planning_application.external_ref}</div>
                      <div className="table-secondary">{member.planning_application.proposal_description}</div>
                    </div>
                    <Badge tone="danger">#{member.rank}</Badge>
                  </div>
                  <div className="table-secondary">
                    {member.fallback_path} · score {member.similarity_score.toFixed(2)}
                  </div>
                </article>
              ))
            )}
          </div>
        </Panel>
      </div>
    </div>
  );
}
