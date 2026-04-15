import Link from 'next/link';

import { GoldSetReviewPanel } from '@/components/gold-set-review-panel';
import { Badge, PageHeader, Panel, StatCard } from '@/components/ui';
import { getGoldSetCase, getGoldSetCases } from '@/lib/landintel-api';

export const dynamic = 'force-dynamic';

function toneForStatus(value: string): 'neutral' | 'accent' | 'success' | 'warning' | 'danger' {
  if (value === 'CONFIRMED') {
    return 'success';
  }

  if (value === 'EXCLUDED') {
    return 'danger';
  }

  return 'warning';
}

export default async function ReviewQueuePage({
  searchParams
}: {
  searchParams?: Record<string, string | string[] | undefined>;
}) {
  const selectedCaseId = typeof searchParams?.caseId === 'string' ? searchParams.caseId : '';
  const result = await getGoldSetCases();
  const items = result.items;
  const selectedSummary =
    items.find((item) => item.id === selectedCaseId) ?? items[0] ?? null;
  const selectedDetail = selectedSummary
    ? await getGoldSetCase(selectedSummary.id)
    : { item: null, apiAvailable: result.apiAvailable };

  const pendingCount = items.filter((item) => item.review_status === 'PENDING').length;
  const confirmedCount = items.filter((item) => item.review_status === 'CONFIRMED').length;
  const excludedCount = items.filter((item) => item.review_status === 'EXCLUDED').length;

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Phase 5A"
        title="Gold-set review queue"
        summary="Historical label adjudication stays lightweight here: inspect the normalized label inputs, confirm or exclude cases, and record policy and geometry notes with provenance."
        actions={
          <div className="page-actions__group">
            <Link className="button button--ghost" href="/assessments">
              Assessments
            </Link>
            <Link className="button button--ghost" href="/admin/health">
              Admin health
            </Link>
          </div>
        }
      />

      <section className="stat-grid">
        <StatCard tone="warning" label="Pending" value={String(pendingCount)} detail="Cases needing reviewer attention" />
        <StatCard tone="success" label="Confirmed" value={String(confirmedCount)} detail="Historical labels signed off by a reviewer" />
        <StatCard tone="danger" label="Excluded" value={String(excludedCount)} detail="Censored or excluded cases kept with explicit reasons" />
        <StatCard tone="accent" label="API" value={result.apiAvailable ? 'Live' : 'Offline'} detail="Queue reads from the live admin endpoints when available" />
      </section>

      <div className="split-grid">
        <Panel eyebrow="Queue" title="Historical cases">
          {items.length === 0 ? (
            <p className="empty-note">No historical label cases are available yet.</p>
          ) : (
            <div className="card-stack">
              {items.map((item) => (
                <article className="mini-card" key={item.id}>
                  <div className="mini-card__top">
                    <div>
                      <div className="table-primary">
                        <Link href={`/review-queue?caseId=${item.id}`}>
                          {item.template_key ?? 'Unmapped'} · {item.units_proposed ?? 'Unknown'} units
                        </Link>
                      </div>
                      <div className="table-secondary">
                        {item.label_class} · {item.label_decision}
                      </div>
                    </div>
                    <Badge tone={toneForStatus(item.review_status)}>{item.review_status}</Badge>
                  </div>
                  <div className="table-secondary">
                    {item.first_substantive_decision_date ?? item.valid_date ?? 'No date'} ·{' '}
                    {item.borough_id ?? 'Unknown borough'}
                  </div>
                </article>
              ))}
            </div>
          )}
        </Panel>

        <GoldSetReviewPanel
          initialCase={selectedDetail.item}
          key={selectedSummary?.id ?? 'empty'}
        />
      </div>
    </div>
  );
}
