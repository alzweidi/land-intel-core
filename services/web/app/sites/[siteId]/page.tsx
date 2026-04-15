import Link from 'next/link';

import { Badge, DefinitionList, PageHeader, Panel } from '@/components/ui';
import { MapCanvas } from '@/components/map-canvas';

export default function SiteDetailPage({
  params
}: {
  params: { siteId: string };
}) {
  const { siteId } = params;

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Site detail"
        title={`Site shell ${siteId}`}
        summary="This page reserves space for listing summary, geometry, permission state, and raw source documents without implementing the later analysis logic."
        actions={
          <Link className="button button--ghost" href={`/sites/${siteId}/scenario-editor`}>
            Open scenario editor
          </Link>
        }
      />

      <section className="stat-grid">
        <div className="stat-card">
          <Badge tone="accent">Listing summary</Badge>
          <div className="stat-value">Stub</div>
          <p className="stat-detail">Source snapshot metadata will live here later.</p>
        </div>
        <div className="stat-card">
          <Badge tone="warning">Geometry</Badge>
          <div className="stat-value">MEDIUM</div>
          <p className="stat-detail">Canonical spatial support remains reserved for later work.</p>
        </div>
        <div className="stat-card">
          <Badge tone="success">Permission</Badge>
          <div className="stat-value">Not checked</div>
          <p className="stat-detail">Extant-permission logic is not part of this task.</p>
        </div>
      </section>

      <div className="split-grid">
        <Panel eyebrow="Context" title="Core record">
          <DefinitionList
            items={[
              { label: 'Display name', value: 'Garage court off Example Road' },
              { label: 'Borough', value: 'Hackney' },
              { label: 'Assessment geometry', value: 'Frozen later' },
              { label: 'Linked titles', value: 'Reserved placeholder' }
            ]}
          />
        </Panel>

        <Panel eyebrow="Map" title="Site geometry shell">
          <MapCanvas />
        </Panel>
      </div>

      <div className="split-grid">
        <Panel eyebrow="Permission state" title="Evidence and gating">
          <ul className="checklist">
            <li>No visible score is emitted from this scaffold.</li>
            <li>Permission-state checks are reserved for later phases.</li>
            <li>Listing claims are not treated as planning truth.</li>
          </ul>
        </Panel>

        <Panel eyebrow="Source documents" title="Raw source assets">
          <div className="mini-list">
            <div className="mini-list__row">
              <span>Source snapshot</span>
              <span>Immutable-by-convention later</span>
            </div>
            <div className="mini-list__row">
              <span>HTML asset</span>
              <span>Stored through a storage adapter later</span>
            </div>
            <div className="mini-list__row">
              <span>Brochure PDF</span>
              <span>Reserved for Phase 1</span>
            </div>
          </div>
        </Panel>
      </div>
    </div>
  );
}
