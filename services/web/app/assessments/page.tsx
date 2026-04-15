import Link from 'next/link';

import { AssessmentRunBuilder } from '@/components/assessment-run-builder';
import { Badge, PageHeader, Panel, StatCard } from '@/components/ui';
import { getAssessments } from '@/lib/landintel-api';

export const dynamic = 'force-dynamic';

function toneForReview(value: string): 'neutral' | 'accent' | 'success' | 'warning' | 'danger' {
  if (value === 'NOT_REQUIRED') {
    return 'success';
  }

  if (value === 'REQUIRED') {
    return 'warning';
  }

  return 'accent';
}

export default async function AssessmentsPage({
  searchParams
}: {
  searchParams?: Record<string, string | string[] | undefined>;
}) {
  const siteId = typeof searchParams?.siteId === 'string' ? searchParams.siteId : '';
  const scenarioId = typeof searchParams?.scenarioId === 'string' ? searchParams.scenarioId : '';
  const result = await getAssessments({
    site_id: siteId || undefined,
    scenario_id: scenarioId || undefined
  });
  const items = result.items;
  const manualReviewCount = items.filter((item) => item.manual_review_required).length;
  const readyCount = items.filter((item) => item.state === 'READY').length;

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Phase 5A"
        title="Frozen pre-score assessments"
        summary="Assessment runs now freeze point-in-time features, provenance, evidence, comparables, and replay metadata. Probability, scoring, valuation, and ranking remain unavailable."
        actions={
          <div className="page-actions__group">
            <Link className="button button--ghost" href="/sites">
              Back to sites
            </Link>
            <Link className="button button--ghost" href="/review-queue">
              Open gold-set review
            </Link>
          </div>
        }
      />

      <section className="stat-grid">
        <StatCard tone="accent" label="Runs" value={String(items.length)} detail="Frozen artifacts available for replay-safe inspection" />
        <StatCard tone="success" label="Ready" value={String(readyCount)} detail="Assessment runs completed without model execution" />
        <StatCard tone="warning" label="Manual review" value={String(manualReviewCount)} detail="Coverage gaps and analyst-required states stay visible" />
        <StatCard tone="danger" label="Probability" value="Hidden" detail="Phase 5A never computes visible or hidden probability" />
      </section>

      <AssessmentRunBuilder initialScenarioId={scenarioId} initialSiteId={siteId} />

      <Panel
        eyebrow="Runs"
        title="Assessment history"
        note={result.apiAvailable ? 'Live API' : 'API unavailable, showing current query result only'}
      >
        {items.length === 0 ? (
          <p className="empty-note">
            No assessment runs exist yet. Create one from a confirmed scenario using the form above or from site detail.
          </p>
        ) : (
          <div className="table-wrap">
            <table className="table-shell">
              <thead>
                <tr>
                  <th>Assessment</th>
                  <th>Site</th>
                  <th>Scenario</th>
                  <th>As of</th>
                  <th>Estimate</th>
                  <th>Review</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <div className="table-primary">
                        <Link href={`/assessments/${item.id}`}>{item.id}</Link>
                      </div>
                      <div className="table-secondary">{item.state}</div>
                    </td>
                    <td>
                      <div className="table-primary">
                        {item.site_summary?.display_name ?? item.site_id}
                      </div>
                      <div className="table-secondary">{item.site_summary?.borough_name ?? 'Unknown borough'}</div>
                    </td>
                    <td>
                      <div className="table-primary">
                        {item.scenario_summary?.template_key ?? item.scenario_id}
                      </div>
                      <div className="table-secondary">
                        {item.scenario_summary
                          ? `${item.scenario_summary.units_assumed} units · ${item.scenario_summary.proposal_form}`
                          : 'Scenario summary unavailable'}
                      </div>
                    </td>
                    <td>{item.as_of_date}</td>
                    <td>
                      <Badge tone="danger">{item.estimate_status}</Badge>
                    </td>
                    <td>
                      <Badge tone={toneForReview(item.review_status)}>{item.review_status}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}
