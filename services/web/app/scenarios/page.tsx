import Link from 'next/link';

import { Badge, PageHeader, Panel } from '@/components/ui';

const templateRows = [
  {
    key: 'resi_1_4_full',
    route: 'FULL',
    units: '1-4',
    note: 'Small infill or redevelopment hypothesis.'
  },
  {
    key: 'resi_5_9_full',
    route: 'FULL',
    units: '5-9',
    note: 'Mid-band residential hypothesis for compact London sites.'
  },
  {
    key: 'resi_10_49_outline',
    route: 'OUTLINE',
    units: '10-49',
    note: 'Larger outline-led residential hypothesis with explicit analyst review.'
  }
];

export default function ScenariosPage() {
  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Scenarios"
        title="Scenario template index"
        summary="The enabled v1 templates are seeded and operational. Generate, compare, and confirm scenarios from site detail; no scoring or probability is exposed here."
        actions={
          <Link className="button button--ghost" href="/sites">
            Open site registry
          </Link>
        }
      />

      <Panel eyebrow="Templates" title="Enabled v1 scenario templates">
        <div className="table-wrap">
          <table className="table-shell">
            <thead>
              <tr>
                <th>Template</th>
                <th>Units</th>
                <th>Route</th>
                <th>Status</th>
                <th>Note</th>
              </tr>
            </thead>
            <tbody>
              {templateRows.map((row) => (
                <tr key={row.key}>
                  <td className="table-primary">{row.key}</td>
                  <td>{row.units}</td>
                  <td>{row.route}</td>
                  <td>
                    <Badge tone="accent">Enabled</Badge>
                  </td>
                  <td>{row.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
