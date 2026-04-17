import Link from 'next/link';

import { GoldSetReviewPanel } from '@/components/gold-set-review-panel';
import { Badge, PageHeader, Panel, StatCard } from '@/components/ui';
import { getAuthContext, readSessionTokenFromCookies } from '@/lib/auth/server';
import { getGoldSetCase, getGoldSetCases, getReviewQueue } from '@/lib/landintel-api';

export const dynamic = 'force-dynamic';

function toneForStatus(value: string): 'neutral' | 'accent' | 'success' | 'warning' | 'danger' {
  if (value === 'CONFIRMED' || value === 'COMPLETED') {
    return 'success';
  }

  if (value === 'EXCLUDED' || value === 'DISABLED') {
    return 'danger';
  }

  return 'warning';
}

export default async function ReviewQueuePage({
  searchParams
}: {
  searchParams?:
    | Promise<Record<string, string | string[] | undefined>>
    | Record<string, string | string[] | undefined>;
}) {
  const params = (await Promise.resolve(searchParams ?? {})) as Record<
    string,
    string | string[] | undefined
  >;
  const auth = await getAuthContext();
  const sessionToken = await readSessionTokenFromCookies();
  const role = auth.role ?? 'reviewer';
  const selectedCaseId = typeof params.caseId === 'string' ? params.caseId : '';
  const queue = await getReviewQueue({ sessionToken: sessionToken ?? undefined });
  const result = await getGoldSetCases({ sessionToken: sessionToken ?? undefined });
  const items = result.items;
  const selectedSummary =
    items.find((item) => item.id === selectedCaseId) ?? items[0] ?? null;
  const selectedDetail = selectedSummary
    ? await getGoldSetCase(selectedSummary.id, { sessionToken: sessionToken ?? undefined })
    : { item: null, apiAvailable: result.apiAvailable };

  const pendingCount = items.filter((item) => item.review_status === 'PENDING').length;
  const manualReviewCount = queue.item?.manual_review_cases.length ?? 0;
  const blockedCount = queue.item?.blocked_cases.length ?? 0;
  const failingBoroughCount = queue.item?.failing_boroughs.length ?? 0;

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Review queue"
        title="Review and control queue"
        summary="Manual-review cases, blocked or incident-affected assessments, failing borough/source coverage, and the gold-set workflow are grouped in one reviewer surface."
        actions={
          <div className="page-actions__group">
            <Link className="button button--ghost" href="/assessments">
              Assessments
            </Link>
            {role === 'admin' ? (
              <Link className="button button--ghost" href="/admin/health">
                Admin health
              </Link>
            ) : null}
          </div>
        }
      />

      <section className="stat-grid">
        <StatCard tone="warning" label="Manual review" value={String(manualReviewCount)} detail="Assessment cases that still need reviewer attention" />
        <StatCard tone="danger" label="Blocked" value={String(blockedCount)} detail="Cases affected by incidents, replay failures, or visibility blocking" />
        <StatCard tone="accent" label="Failing boroughs" value={String(failingBoroughCount)} detail="Coverage or freshness gaps that need operational attention" />
        <StatCard tone="warning" label="Gold-set pending" value={String(pendingCount)} detail="Historical label cases still waiting for adjudication" />
      </section>

      <div className="split-grid">
        <Panel eyebrow="Operational queue" title="Manual-review and blocked assessments">
          {queue.item ? (
            <div className="card-stack">
              {queue.item.manual_review_cases.map((item) => (
                <article className="mini-card" key={`manual-${item.assessment_id}`}>
                  <div className="mini-card__top">
                    <div>
                      <div className="table-primary">
                        <Link href={`/assessments/${item.assessment_id}?mode=hidden&role=reviewer`}>
                          {item.display_name}
                        </Link>
                      </div>
                      <div className="table-secondary">{item.review_status}</div>
                    </div>
                    <Badge tone={toneForStatus(item.review_status)}>{item.visibility_mode ?? 'HIDDEN_ONLY'}</Badge>
                  </div>
                  <div className="table-secondary">
                    {item.manual_review_required ? 'Manual review required.' : 'Display-block override or visibility control is active.'}
                  </div>
                </article>
              ))}
              {queue.item.blocked_cases.map((item) => (
                <article className="mini-card" key={`blocked-${item.assessment_id}`}>
                  <div className="mini-card__top">
                    <div>
                      <div className="table-primary">
                        <Link href={`/assessments/${item.assessment_id}?mode=hidden&role=reviewer`}>
                          {item.display_name}
                        </Link>
                      </div>
                      <div className="table-secondary">{item.visibility_mode ?? 'Unknown visibility state'}</div>
                    </div>
                    <Badge tone="danger">Blocked</Badge>
                  </div>
                  <div className="table-secondary">
                    {item.blocked_reason ?? item.display_block_reason ?? 'Blocked by safety controls.'}
                  </div>
                </article>
              ))}
              {(queue.item.manual_review_cases.length === 0 && queue.item.blocked_cases.length === 0) ? (
                <p className="empty-note">No assessment cases are currently queued for manual review or blocking follow-up.</p>
              ) : null}
            </div>
          ) : (
            <p className="empty-note">Review queue API is unavailable.</p>
          )}
        </Panel>

        <Panel eyebrow="Operational queue" title="Coverage and freshness failures">
          {queue.item && queue.item.failing_boroughs.length > 0 ? (
            <div className="card-stack">
              {queue.item.failing_boroughs.map((item, index) => (
                <article className="mini-card" key={`borough-${index}`}>
                  <div className="mini-card__top">
                    <div>
                      <div className="table-primary">
                        {String(item.borough_id ?? 'unknown')} · {String(item.source_family ?? 'unknown')}
                      </div>
                      <div className="table-secondary">
                        {String(item.coverage_status ?? 'UNKNOWN')} · {String(item.freshness_status ?? 'UNKNOWN')}
                      </div>
                    </div>
                    <Badge tone="warning">Gap</Badge>
                  </div>
                  <div className="table-secondary">
                    {String(item.gap_reason ?? item.coverage_note ?? 'No recorded gap note')}
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <p className="empty-note">No failing borough/source coverage rows are currently flagged.</p>
          )}
        </Panel>
      </div>

      <div className="split-grid">
        <Panel eyebrow="Gold-set queue" title="Historical cases">
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
