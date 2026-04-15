import { MapCanvas } from '@/components/map-canvas';
import { Badge, PageHeader, Panel } from '@/components/ui';
import { discoveryRows } from '@/lib/mock-data';

export default function DiscoveryPage() {
  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Discovery"
        title="Map and list shell"
        summary="Placeholder discovery workspace for browsing current site candidates. The map is intentionally non-interactive until later phases."
      />

      <div className="split-grid">
        <Panel eyebrow="Map view" title="Static discovery map">
          <MapCanvas />
        </Panel>

        <Panel eyebrow="List view" title="Candidate list shell" note="Filter chips are present, but no live query state yet.">
          <div className="pill-row">
            <Badge tone="accent">Borough</Badge>
            <Badge tone="neutral">Status</Badge>
            <Badge tone="neutral">Price</Badge>
            <Badge tone="neutral">Scenario</Badge>
            <Badge tone="neutral">Review state</Badge>
          </div>

          <div className="list-shell">
            {discoveryRows.map((row) => (
              <article className="list-row" key={row.id}>
                <div>
                  <div className="list-row__title">{row.name}</div>
                  <div className="list-row__meta">
                    {row.borough} · {row.source}
                  </div>
                </div>
                <div className="list-row__right">
                  <Badge tone="warning">{row.state}</Badge>
                  <span className="list-row__note">{row.note}</span>
                </div>
              </article>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  );
}
