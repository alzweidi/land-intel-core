import { Badge, PageHeader, Panel } from '@/components/ui';
import { scenarioRows } from '@/lib/mock-data';

export default function ScenariosPage() {
  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Scenarios"
        title="Scenario template shell"
        summary="This page holds the route for future scenario normalization, confirmation, and comparison. For now, it only documents the enabled v1 templates."
      />

      <Panel eyebrow="Library" title="Template states">
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
              {scenarioRows.map((row) => (
                <tr key={row.key}>
                  <td className="table-primary">{row.key}</td>
                  <td>{row.units}</td>
                  <td>{row.route}</td>
                  <td>
                    <Badge tone={row.status === 'ANALYST_CONFIRMED' ? 'success' : row.status === 'ANALYST_REQUIRED' ? 'warning' : 'accent'}>
                      {row.status}
                    </Badge>
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
