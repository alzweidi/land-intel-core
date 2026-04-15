import { Badge, PageHeader, Panel } from '@/components/ui';
import { reviewRows } from '@/lib/mock-data';

export default function ReviewQueuePage() {
  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Review queue"
        title="Manual review shell"
        summary="This queue will later hold cases that require analyst attention. It currently shows the row structure and bucket names only."
      />

      <Panel eyebrow="Queue" title="Review buckets">
        <div className="card-stack">
          {reviewRows.map((row) => (
            <article className="mini-card" key={row.item}>
              <div className="mini-card__top">
                <div>
                  <div className="table-primary">{row.item}</div>
                  <div className="table-secondary">{row.reason}</div>
                </div>
                <Badge tone={row.priority === 'High' ? 'danger' : row.priority === 'Medium' ? 'warning' : 'accent'}>
                  {row.priority}
                </Badge>
              </div>
              <div className="mini-card__footer">{row.bucket}</div>
            </article>
          ))}
        </div>
      </Panel>
    </div>
  );
}
