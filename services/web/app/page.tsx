import Link from 'next/link';

import { Badge, PageHeader, Panel, StatCard, SurfaceCard } from '@/components/ui';
import { surfaceCatalog } from '@/lib/navigation';

export default function HomePage() {
  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Phase 5A"
        title="London land intelligence control room"
        summary="Listings, sites, planning context, scenarios, and frozen pre-score assessments are now live. The current shell stays explicit about what is operational versus what remains deferred."
        actions={
          <div className="page-actions__group">
            <Link className="button button--solid" href="/listings">
              Open listings
            </Link>
            <Link className="button button--ghost" href="/admin/source-runs">
              Run connector
            </Link>
          </div>
        }
      />

      <section className="stat-grid">
        <StatCard tone="accent" label="Phase" value="5A" detail="Pre-score assessment foundations only" />
        <StatCard tone="success" label="Sources" value="3+" detail="Listings plus fixture-scale planning and policy families" />
        <StatCard tone="warning" label="Snapshots" value="Immutable" detail="No in-place overwrite of raw assets or source snapshots" />
        <StatCard tone="neutral" label="Assessment" value="Frozen" detail="Replay-safe features, evidence, and comparables with no score output" />
      </section>

      <section className="route-grid">
        {surfaceCatalog.map((surface) => (
          <SurfaceCard
            href={surface.href}
            key={surface.href}
            summary={surface.summary}
            tag={surface.tag}
            title={surface.title}
          />
        ))}
      </section>

      <Panel
        eyebrow="Spec guardrails"
        title="What Phase 5A deliberately does not do"
        note="Frozen assessment artifacts are live. Model training, scoring, valuation, ranking, and overrides remain deferred."
      >
        <ul className="checklist">
          <li>No model training, calibration, OOD logic, or hidden-score mode.</li>
          <li>No probability, valuation, uplift, or ranking output.</li>
          <li>No future-leaking feature construction or forbidden label shortcuts.</li>
          <li>No unapproved public-page connector execution.</li>
          <li>No hidden overwrite of raw source assets or snapshots.</li>
        </ul>
      </Panel>

      <Panel eyebrow="Source policy" title="Connector approval rule">
        <div className="pill-row">
          <Badge tone="success">Manual URL always allowed</Badge>
          <Badge tone="warning">CSV import stays manual</Badge>
          <Badge tone="danger">Public pages stay blocked unless approved</Badge>
        </div>
      </Panel>
    </div>
  );
}
