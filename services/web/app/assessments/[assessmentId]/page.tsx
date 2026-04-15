import Link from 'next/link';

import { Badge, DefinitionList, PageHeader, Panel } from '@/components/ui';

export default function AssessmentDetailPage({
  params
}: {
  params: { assessmentId: string };
}) {
  const { assessmentId } = params;

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Assessment view"
        title={`Assessment shell ${assessmentId}`}
        summary="The future assessment view will hold frozen results, evidence, comparables, and valuation. This shell keeps the shape visible and clearly unfinished."
        actions={
          <Link className="button button--ghost" href="/assessments">
            Back to runs
          </Link>
        }
      />

      <section className="stat-grid">
        <div className="stat-card">
          <Badge tone="warning">Probability</Badge>
          <div className="stat-value">Hidden</div>
          <p className="stat-detail">No visible scoring logic is present in Phase 0.</p>
        </div>
        <div className="stat-card">
          <Badge tone="accent">Valuation</Badge>
          <div className="stat-value">Hidden</div>
          <p className="stat-detail">No uplift or economics surface is calculated yet.</p>
        </div>
        <div className="stat-card">
          <Badge tone="success">Replay</Badge>
          <div className="stat-value">Prepared</div>
          <p className="stat-detail">Frozen-artifact display will be added later.</p>
        </div>
      </section>

      <div className="split-grid">
        <Panel eyebrow="Assessment" title="Core metadata">
          <DefinitionList
            items={[
              { label: 'Assessment ID', value: assessmentId },
              { label: 'Site', value: 'site-001' },
              { label: 'Scenario', value: 'resi_5_9_full' },
              { label: 'As-of date', value: '2026-04-15' }
            ]}
          />
        </Panel>

        <Panel eyebrow="Evidence" title="For / against / unknown">
          <div className="mini-list">
            <div className="mini-list__row">
              <span>For</span>
              <span>Reserved for later evidence assembly</span>
            </div>
            <div className="mini-list__row">
              <span>Against</span>
              <span>Reserved for later evidence assembly</span>
            </div>
            <div className="mini-list__row">
              <span>Unknown</span>
              <span>Reserved for later evidence assembly</span>
            </div>
          </div>
        </Panel>
      </div>
    </div>
  );
}
