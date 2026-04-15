import Link from 'next/link';

import { Badge, PageHeader, Panel } from '@/components/ui';
import { assessmentRows } from '@/lib/mock-data';

export default function AssessmentsPage() {
  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Assessments"
        title="Frozen assessment run shell"
        summary="Assessment detail pages are stubbed now so the later planning and valuation engines have a stable destination."
        actions={
          <Link className="button button--ghost" href="/assessments/assess-001">
            Open assessment detail
          </Link>
        }
      />

      <Panel eyebrow="Runs" title="Assessment history">
        <div className="table-wrap">
          <table className="table-shell">
            <thead>
              <tr>
                <th>Assessment</th>
                <th>Site</th>
                <th>Scenario</th>
                <th>Probability</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {assessmentRows.map((row) => (
                <tr key={row.id}>
                  <td>
                    <div className="table-primary">
                      <Link href={`/assessments/${row.id}`}>{row.id}</Link>
                    </div>
                    <div className="table-secondary">{row.quality}</div>
                  </td>
                  <td>{row.site}</td>
                  <td>{row.scenario}</td>
                  <td>{row.probability}</td>
                  <td>
                    <Badge tone="warning">{row.state}</Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
