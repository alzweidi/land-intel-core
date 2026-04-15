import Link from 'next/link';

import { Badge, PageHeader, Panel, StatCard, SurfaceCard } from '@/components/ui';
import { surfaceCatalog } from '@/lib/navigation';

export default function HomePage() {
  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Phase 6A"
        title="London land intelligence control room"
        summary="Listings, sites, planning context, scenarios, frozen assessments, and hidden-only scoring are now live. The shell stays explicit about what is operational versus what remains deferred."
        actions={
          <div className="page-actions__group">
            <Link className="button button--solid" href="/listings">
              Open listings
            </Link>
            <Link className="button button--ghost" href="/admin/source-runs">
              Run connector
            </Link>
            <Link className="button button--ghost" href="/admin/model-releases">
              Model releases
            </Link>
          </div>
        }
      />

      <section className="stat-grid">
        <StatCard tone="accent" label="Phase" value="6A" detail="Hidden-only scoring foundations live" />
        <StatCard tone="success" label="Sources" value="3+" detail="Listings plus fixture-scale planning and policy families" />
        <StatCard tone="warning" label="Snapshots" value="Immutable" detail="No in-place overwrite of raw assets or source snapshots" />
        <StatCard tone="neutral" label="Assessment" value="Hidden" detail="Replay-safe features, evidence, comparables, and hidden internal score output" />
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
        title="What Phase 6A deliberately does not do"
        note="Hidden logistic scoring is live, but visible rollout, valuation, ranking, overrides, and control-plane dashboards remain deferred."
      >
        <ul className="checklist">
          <li>No standard-analyst visible probability rollout.</li>
          <li>No valuation, uplift, or ranking output.</li>
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
