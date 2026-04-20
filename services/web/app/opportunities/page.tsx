import Link from 'next/link';

import { Badge, PageHeader, Panel, StatCard, TableShell } from '@/components/ui';
import { getAuthContext, readSessionTokenFromCookies } from '@/lib/auth/server';
import { getOpportunities, getReadbackState } from '@/lib/landintel-api';

export const dynamic = 'force-dynamic';

function currency(value: number | null): string {
  if (value === null) {
    return 'Unavailable';
  }

  return `£${Math.round(value).toLocaleString('en-GB')}`;
}

function bandTone(value: string): 'neutral' | 'accent' | 'success' | 'warning' | 'danger' {
  if (value === 'Band A') {
    return 'success';
  }
  if (value === 'Band B') {
    return 'accent';
  }
  if (value === 'Band C') {
    return 'warning';
  }
  if (value === 'Band D' || value === 'Hold') {
    return 'danger';
  }
  return 'neutral';
}

function valuationTone(value: string | null): 'neutral' | 'accent' | 'success' | 'warning' | 'danger' {
  if (value === 'HIGH') {
    return 'success';
  }
  if (value === 'MEDIUM') {
    return 'accent';
  }
  if (value === 'LOW') {
    return 'warning';
  }
  return 'neutral';
}

function readbackLabel(state: 'LIVE' | 'EMPTY' | 'FALLBACK'): string {
  if (state === 'LIVE') {
    return 'Live';
  }

  if (state === 'EMPTY') {
    return 'Empty';
  }

  return 'Hold/manual review';
}

function readbackTone(state: 'LIVE' | 'EMPTY' | 'FALLBACK'): 'success' | 'warning' | 'danger' {
  if (state === 'LIVE') {
    return 'success';
  }

  if (state === 'EMPTY') {
    return 'warning';
  }

  return 'danger';
}

export default async function OpportunitiesPage({
  searchParams
}: {
  searchParams?: Promise<Record<string, string | string[] | undefined>> | Record<string, string | string[] | undefined>;
}) {
  const query = (await Promise.resolve(searchParams ?? {})) as Record<
    string,
    string | string[] | undefined
  >;
  const auth = await getAuthContext();
  const sessionToken = await readSessionTokenFromCookies();
  const role = auth.role ?? 'analyst';
  const includeHidden =
    (role === 'reviewer' || role === 'admin') &&
    typeof query.includeHidden === 'string' &&
    query.includeHidden === 'true';

  const borough = typeof query.borough === 'string' ? query.borough : '';
  const probabilityBand =
    typeof query.probability_band === 'string' ? query.probability_band : '';
  const valuationQuality =
    typeof query.valuation_quality === 'string' ? query.valuation_quality : '';
  const manualReviewRequired =
    typeof query.manual_review_required === 'string'
      ? query.manual_review_required === 'true'
      : undefined;

  const result = await getOpportunities({
    borough: borough || undefined,
    probability_band: probabilityBand as 'Band A' | 'Band B' | 'Band C' | 'Band D' | 'Hold' | '',
    valuation_quality: valuationQuality as 'HIGH' | 'MEDIUM' | 'LOW' | '',
    manual_review_required: manualReviewRequired,
    hidden_mode: includeHidden,
    viewer_role: role,
    sessionToken: sessionToken ?? undefined
  });

  const items = result.items;
  const queueState = getReadbackState(result.apiAvailable, items.length);
  const bandACount = items.filter((item) => item.probability_band === 'Band A').length;
  const holdCount = items.filter((item) => item.probability_band === 'Hold').length;
  const lowQualityCount = items.filter((item) => item.valuation_quality === 'LOW').length;
  const reviewCount = items.filter((item) => item.manual_review_required).length;

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Opportunities"
        title="Planning-first opportunity queue"
        summary="This queue always ranks planning state first, then economics and urgency inside each band. Hidden probability remains internal and is only included here when the current role explicitly requests hidden mode."
        actions={
          <div className="page-actions__group">
            <Link className="button button--ghost" href="/assessments">
              Assessments
            </Link>
            {role === 'admin' ? (
              <Link className="button button--ghost" href="/admin/model-releases">
                Model releases
              </Link>
            ) : null}
          </div>
        }
        badges={
          <div className="status-strip">
            <Badge tone={includeHidden ? 'danger' : 'warning'}>
              {includeHidden ? 'Hidden/internal queue' : 'Standard redacted queue'}
            </Badge>
            <Badge tone={readbackTone(queueState)}>{readbackLabel(queueState)}</Badge>
            <Badge tone="accent">{role}</Badge>
          </div>
        }
      />

      <section className="stat-grid">
        <StatCard tone="success" label="Band A" value={String(bandACount)} detail="Strongest planning band in the current filtered queue" />
        <StatCard tone="danger" label="Hold" value={String(holdCount)} detail="Cases that are not honestly rankable yet" />
        <StatCard tone="warning" label="Low quality" value={String(lowQualityCount)} detail="Low valuation quality forces manual review" />
        <StatCard tone="accent" label="Manual review" value={String(reviewCount)} detail="Flags remain visible even when a row is ranked" />
      </section>

      <Panel eyebrow="Filters" title="Queue filters" note={includeHidden ? 'Hidden/internal view' : 'Standard redacted view'}>
        <form className="toolbar-form" method="get">
          <label className="field">
            <span>Borough</span>
            <input defaultValue={borough} name="borough" placeholder="camden" type="text" />
          </label>
          <label className="field">
            <span>Probability band</span>
            <select defaultValue={probabilityBand} name="probability_band">
              <option value="">All</option>
              <option value="Band A">Band A</option>
              <option value="Band B">Band B</option>
              <option value="Band C">Band C</option>
              <option value="Band D">Band D</option>
              <option value="Hold">Hold</option>
            </select>
          </label>
          <label className="field">
            <span>Valuation quality</span>
            <select defaultValue={valuationQuality} name="valuation_quality">
              <option value="">All</option>
              <option value="HIGH">HIGH</option>
              <option value="MEDIUM">MEDIUM</option>
              <option value="LOW">LOW</option>
            </select>
          </label>
          <label className="field">
            <span>Manual review</span>
            <select
              defaultValue={
                manualReviewRequired === undefined ? '' : manualReviewRequired ? 'true' : 'false'
              }
              name="manual_review_required"
            >
              <option value="">All</option>
              <option value="true">Required</option>
              <option value="false">Not required</option>
            </select>
          </label>
          {(role === 'reviewer' || role === 'admin') ? (
            <label className="field">
              <span>Hidden mode</span>
              <select defaultValue={includeHidden ? 'true' : 'false'} name="includeHidden">
                <option value="false">Standard redacted</option>
                <option value="true">Hidden/internal</option>
              </select>
            </label>
          ) : (
            <input name="includeHidden" type="hidden" value="false" />
          )}
          <div className="toolbar-form__actions">
            <button className="button button--solid" type="submit">
              Apply filters
            </button>
            <Link className="button button--ghost" href="/opportunities">
              Reset
            </Link>
          </div>
        </form>
      </Panel>

      <TableShell
        title="Opportunity rows"
        note="Planning band always takes precedence over economics. Economics never leapfrog a stronger planning state."
      >
        {items.length > 0 ? (
          <div className="dense-table">
            <table className="table-shell table-shell--responsive">
              <thead>
                <tr>
                  <th>Site</th>
                  <th>Planning band</th>
                  <th>Valuation</th>
                  <th>Expected uplift</th>
                  <th>Asking price</th>
                  <th>Review / links</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.site_id}>
                    <td data-label="Site">
                      <div className="table-primary">
                        <Link href={`/sites/${item.site_id}`}>
                          {item.display_name || item.site_summary?.display_name || item.site_id}
                        </Link>
                      </div>
                      <div className="table-secondary">
                        {item.borough_name ?? item.borough_id ?? 'Unknown borough'}
                      </div>
                      <div className="table-secondary">{item.ranking_reason}</div>
                    </td>
                    <td data-label="Planning band">
                      <Badge tone={bandTone(item.probability_band)}>{item.probability_band}</Badge>
                      <div className="table-secondary">{item.hold_reason ?? 'Rankable'}</div>
                      <div className="table-secondary">
                        {item.hidden_mode_only ? 'Hidden-only support' : 'Standard queue'}
                      </div>
                    </td>
                    <td data-label="Valuation">
                      <Badge tone={valuationTone(item.valuation_quality)}>{item.valuation_quality ?? 'Unknown'}</Badge>
                      <div className="table-secondary">
                        Post-permission {currency(item.post_permission_value_mid)}
                      </div>
                      <div className="table-secondary">
                        Quality gates stay visible when uplift is incomplete.
                      </div>
                    </td>
                    <td data-label="Expected uplift">
                      <div className="table-primary">
                        {includeHidden ? currency(item.expected_uplift_mid) : 'Hidden'}
                      </div>
                      <div className="table-secondary">Uplift {currency(item.uplift_mid)}</div>
                    </td>
                    <td data-label="Asking price">
                      <div className="table-primary">{currency(item.asking_price_gbp)}</div>
                      <div className="table-secondary">
                        {item.asking_price_basis_type ?? 'Basis unavailable'}
                      </div>
                    </td>
                    <td data-label="Review / links">
                      <Badge tone={item.manual_review_required ? 'warning' : 'success'}>
                        {item.manual_review_required ? 'Review required' : 'No review flag'}
                      </Badge>
                      <div className="table-secondary">
                        Same-borough support {item.same_borough_support_count}
                      </div>
                      {item.assessment_id ? (
                        <div className="table-secondary">
                          <Link
                            className="inline-link"
                            href={
                              includeHidden
                                ? `/assessments/${item.assessment_id}?mode=hidden`
                                : `/assessments/${item.assessment_id}`
                            }
                          >
                            Open assessment
                          </Link>
                        </div>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="empty-note">
            {queueState === 'EMPTY'
              ? 'No live opportunity rows matched the current filters.'
              : 'The opportunity queue is held because live data is unavailable.'}
          </p>
        )}
      </TableShell>
    </div>
  );
}
