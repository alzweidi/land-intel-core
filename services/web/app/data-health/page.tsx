import { Badge, PageHeader, Panel } from '@/components/ui';
import { healthRows } from '@/lib/mock-data';

export default function DataHealthPage() {
  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Data health"
        title="Source freshness dashboard shell"
        summary="This dashboard will later show freshness, connector failures, and borough coverage gaps. For Phase 0 it remains a readable placeholder."
      />

      <section className="stat-grid">
        <div className="stat-card">
          <Badge tone="success">Listings</Badge>
          <div className="stat-value">Freshness stub</div>
          <p className="stat-detail">Manual URL intake is the only active path in this scaffold.</p>
        </div>
        <div className="stat-card">
          <Badge tone="warning">Coverage</Badge>
          <div className="stat-value">Pending</div>
          <p className="stat-detail">Borough and policy coverage will come later.</p>
        </div>
        <div className="stat-card">
          <Badge tone="accent">Failures</Badge>
          <div className="stat-value">0 tracked</div>
          <p className="stat-detail">No connector execution exists in the frontend stub.</p>
        </div>
      </section>

      <Panel eyebrow="Families" title="Health rows">
        <div className="table-wrap">
          <table className="table-shell">
            <thead>
              <tr>
                <th>Family</th>
                <th>Freshness</th>
                <th>Coverage</th>
                <th>Gap</th>
              </tr>
            </thead>
            <tbody>
              {healthRows.map((row) => (
                <tr key={row.family}>
                  <td className="table-primary">{row.family}</td>
                  <td>{row.freshness}</td>
                  <td>
                    <Badge tone={row.coverage === 'Stubbed' ? 'warning' : 'accent'}>{row.coverage}</Badge>
                  </td>
                  <td>{row.gap}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
