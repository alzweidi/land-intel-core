import { Badge, PageHeader, Panel } from '@/components/ui';
import { listingRows } from '@/lib/mock-data';

export default function ListingsPage() {
  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Listings"
        title="Manual intake and source registry"
        summary="This shell is ready for immutable listing snapshots, but currently shows only static row states and queue placeholders."
      />

      <Panel eyebrow="Queue" title="Intake run shell">
        <div className="table-wrap">
          <table className="table-shell">
            <thead>
              <tr>
                <th>Listing</th>
                <th>Borough</th>
                <th>Source</th>
                <th>Status</th>
                <th>Note</th>
              </tr>
            </thead>
            <tbody>
              {listingRows.map((row) => (
                <tr key={row.id}>
                  <td>
                    <div className="table-primary">{row.title}</div>
                    <div className="table-secondary">{row.id}</div>
                  </td>
                  <td>{row.borough}</td>
                  <td>{row.source}</td>
                  <td>
                    <Badge
                      tone={row.status === 'SUCCEEDED' ? 'success' : row.status === 'RUNNING' ? 'accent' : 'warning'}
                    >
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
