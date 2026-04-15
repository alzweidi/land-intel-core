import Link from 'next/link';

import { Badge, PageHeader, Panel, StatCard, SurfaceCard } from '@/components/ui';
import { surfaceCatalog } from '@/lib/navigation';

export default function HomePage() {
  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Phase 1A"
        title="Listing ingestion and clustering control room"
        summary="This shell now centers the live listings layer: intake, immutable snapshots, clustering, and the minimal admin surfaces needed to run approved connectors."
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
        <StatCard tone="accent" label="Phase" value="1A" detail="Listings and clustering only" />
        <StatCard tone="success" label="Sources" value="3" detail="Manual, CSV, and approved public-page" />
        <StatCard tone="warning" label="Snapshots" value="Immutable" detail="No in-place overwrite of raw assets" />
        <StatCard tone="neutral" label="Clustering" value="Deterministic" detail="Rules are boring and documented" />
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
        title="What Phase 1A deliberately does not do"
        note="Listings, sites, planning context, and scenario foundations are live. Assessment, scoring, valuation, and ranking surfaces remain stubbed."
      >
        <ul className="checklist">
          <li>No site geometry or title linkage.</li>
          <li>No assessment execution, scoring, valuation, or ranking.</li>
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
