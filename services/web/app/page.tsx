import Link from 'next/link';

import { Badge, MiniMetric, PageHeader, Panel, SectionGrid, SurfaceCard } from '@/components/ui';
import { canAccessPath } from '@/lib/auth/access';
import { getAuthContext } from '@/lib/auth/server';
import { surfaceCatalog } from '@/lib/navigation';

export default async function HomePage() {
  const auth = await getAuthContext();
  const role = auth.role ?? 'analyst';

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Dashboard"
        title="Internal land acquisition workspace"
        summary="Use the intake queue to capture listings, build sites from evidence, confirm scenarios, inspect frozen assessments, and rank opportunities. Hidden probability remains internal and non-speaking by default."
        actions={
          <div className="page-actions__group">
            <Link className="button button--solid" href="/listings">
              Open listings
            </Link>
            <Link className="button button--ghost" href="/sites">
              Open sites
            </Link>
            <Link className="button button--ghost" href="/opportunities">
              Open opportunities
            </Link>
          </div>
        }
        badges={
          <div className="status-strip">
            <Badge tone="warning">Visible probability blocked</Badge>
            <Badge tone="accent">Hidden release controls active</Badge>
            <Badge tone="success">Live local API shell</Badge>
          </div>
        }
      />

      <SectionGrid className="section-grid--three">
        <MiniMetric label="Intake" value="Listings, clusters, source runs" tone="accent" />
        <MiniMetric label="Delivery" value="Sites, scenarios, assessments" tone="success" />
        <MiniMetric label="Control" value="Opportunities, review, admin health" tone="warning" />
      </SectionGrid>

      <section className="route-grid">
        {surfaceCatalog
          .filter((surface) => canAccessPath(role, surface.href))
          .filter((surface) => surface.href !== '/discovery')
          .map((surface) => (
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
        eyebrow="Guardrails"
        title="Working rules"
        note="The UI can expose internal state clearly without broadening visible probability."
      >
        <ul className="checklist">
          <li>Listings and source snapshots remain immutable.</li>
          <li>Scenarios are hypotheses, not facts.</li>
          <li>Economics never outrank planning state.</li>
          <li>Visible probability stays blocked unless a qualifying scope is explicitly enabled.</li>
        </ul>
      </Panel>
    </div>
  );
}
