import Link from 'next/link';

import { Badge, PageHeader, Panel, StatCard, SurfaceCard } from '@/components/ui';
import { surfaceCatalog } from '@/lib/navigation';

export default function HomePage() {
  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Phase 7A"
        title="London land intelligence control room"
        summary="Listings, sites, planning context, scenarios, frozen assessments, hidden-only scoring, and planning-first valuation/ranking are now live for internal use. The shell stays explicit about what is operational versus what remains deferred."
        actions={
          <div className="page-actions__group">
            <Link className="button button--solid" href="/listings">
              Open listings
            </Link>
            <Link className="button button--ghost" href="/opportunities">
              Open opportunities
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
        <StatCard tone="accent" label="Phase" value="7A" detail="Hidden scoring plus valuation and ranking live for internal use" />
        <StatCard tone="success" label="Sources" value="3+" detail="Listings plus fixture-scale planning and policy families" />
        <StatCard tone="warning" label="Snapshots" value="Immutable" detail="No in-place overwrite of raw assets or source snapshots" />
        <StatCard tone="neutral" label="Assessment" value="Hidden + value" detail="Replay-safe features, hidden internal score output, valuation, and planning-first ranking" />
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
        title="What Phase 7A deliberately does not do"
        note="Hidden logistic scoring, valuation, and ranking are live internally, but visible rollout, overrides, kill switches, and broader dashboards remain deferred."
      >
        <ul className="checklist">
          <li>No standard-analyst visible probability rollout.</li>
          <li>No Phase 8 overrides control plane, kill switches, or dashboard rollout.</li>
          <li>No parcel-only scoring or valuation path.</li>
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
