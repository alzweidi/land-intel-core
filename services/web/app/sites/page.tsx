import Link from 'next/link';

import { Badge, PageHeader, Panel } from '@/components/ui';
import { siteRows } from '@/lib/mock-data';

export default function SitesPage() {
  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Sites"
        title="Confirmed site registry shell"
        summary="The site registry will later contain frozen geometries, planning context, and linked listing evidence. This pass keeps the surface obvious and inert."
        actions={
          <Link className="button button--ghost" href="/sites/site-001">
            Open site detail stub
          </Link>
        }
      />

      <section className="stat-grid">
        <div className="stat-card">
          <Badge tone="accent">Geometries</Badge>
          <div className="stat-value">3</div>
          <p className="stat-detail">Placeholder records only.</p>
        </div>
        <div className="stat-card">
          <Badge tone="warning">Manual review</Badge>
          <div className="stat-value">1</div>
          <p className="stat-detail">Low-confidence shell state.</p>
        </div>
        <div className="stat-card">
          <Badge tone="success">Ready</Badge>
          <div className="stat-value">2</div>
          <p className="stat-detail">Static site detail routes exist.</p>
        </div>
      </section>

      <Panel eyebrow="Registry" title="Site rows">
        <div className="table-wrap">
          <table className="table-shell">
            <thead>
              <tr>
                <th>Site</th>
                <th>Borough</th>
                <th>Geometry</th>
                <th>Permission state</th>
                <th>Scenario</th>
              </tr>
            </thead>
            <tbody>
              {siteRows.map((row) => (
                <tr key={row.id}>
                  <td>
                    <div className="table-primary">
                      <Link href={`/sites/${row.id}`}>{row.name}</Link>
                    </div>
                    <div className="table-secondary">{row.id}</div>
                  </td>
                  <td>{row.borough}</td>
                  <td>
                    <Badge tone={row.geom === 'HIGH' ? 'success' : row.geom === 'LOW' ? 'warning' : 'accent'}>
                      {row.geom}
                    </Badge>
                  </td>
                  <td>{row.permission}</td>
                  <td>{row.scenario}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
