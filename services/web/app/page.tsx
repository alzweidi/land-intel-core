import Link from 'next/link';

import { PageHeader, Panel, StatCard, SurfaceCard } from '@/components/ui';
import { homeStats } from '@/lib/mock-data';
import { surfaceCatalog } from '@/lib/navigation';

export default function HomePage() {
  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Phase 0 scaffold"
        title="London-first land intelligence control room"
        summary="This internal shell exposes the major surfaces described in the controlling spec, but keeps every domain workflow visibly stubbed."
        actions={
          <div className="page-actions__group">
            <Link className="button button--solid" href="/discovery">
              Open discovery
            </Link>
            <Link className="button button--ghost" href="/admin/health">
              View health
            </Link>
          </div>
        }
      />

      <section className="stat-grid">
        {homeStats.map((stat) => (
          <StatCard
            detail={stat.detail}
            key={stat.label}
            label={stat.label}
            tone={stat.label === 'Scoring logic' ? 'danger' : stat.label === 'Backend coupling' ? 'success' : 'neutral'}
            value={stat.value}
          />
        ))}
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
        title="What this scaffold deliberately does not do"
        note="Phase 0 is the bootstrapping pass. The later planning, scoring, and valuation systems are reserved for later phases."
      >
        <ul className="checklist">
          <li>No parcel-only scoring or visible probability logic.</li>
          <li>No geospatial business rules beyond shell placeholders.</li>
          <li>No enrichment pipelines, clustering, or scenario automation.</li>
          <li>No hidden overwrite of raw source assets.</li>
        </ul>
      </Panel>
    </div>
  );
}
