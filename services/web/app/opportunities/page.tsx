import Link from 'next/link';

import { Badge, PageHeader, Panel, StatCard } from '@/components/ui';
import { getOpportunities } from '@/lib/landintel-api';

export const dynamic = 'force-dynamic';

function formatCurrency(value: number | null): string {
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

export default async function OpportunitiesPage({
  searchParams
}: {
  searchParams?: Record<string, string | string[] | undefined>;
}) {
  const borough = typeof searchParams?.borough === 'string' ? searchParams.borough : '';
  const probabilityBand =
    typeof searchParams?.probability_band === 'string' ? searchParams.probability_band : '';
  const valuationQuality =
    typeof searchParams?.valuation_quality === 'string' ? searchParams.valuation_quality : '';
  const manualReviewRequired =
    typeof searchParams?.manual_review_required === 'string'
      ? searchParams.manual_review_required === 'true'
      : undefined;
  const auctionDeadlineDays =
    typeof searchParams?.auction_deadline_days === 'string' &&
    searchParams.auction_deadline_days.length > 0
      ? Number(searchParams.auction_deadline_days)
      : undefined;
  const minPrice =
    typeof searchParams?.min_price === 'string' && searchParams.min_price.length > 0
      ? Number(searchParams.min_price)
      : undefined;
  const maxPrice =
    typeof searchParams?.max_price === 'string' && searchParams.max_price.length > 0
      ? Number(searchParams.max_price)
      : undefined;

  const result = await getOpportunities({
    borough: borough || undefined,
    probability_band: probabilityBand as
      | 'Band A'
      | 'Band B'
      | 'Band C'
      | 'Band D'
      | 'Hold'
      | '',
    valuation_quality: valuationQuality as 'HIGH' | 'MEDIUM' | 'LOW' | '',
    manual_review_required: manualReviewRequired,
    auction_deadline_days:
      auctionDeadlineDays !== undefined && Number.isFinite(auctionDeadlineDays)
        ? auctionDeadlineDays
        : undefined,
    min_price: minPrice !== undefined && Number.isFinite(minPrice) ? minPrice : undefined,
    max_price: maxPrice !== undefined && Number.isFinite(maxPrice) ? maxPrice : undefined
  });

  const items = result.items;
  const bandACount = items.filter((item) => item.probability_band === 'Band A').length;
  const holdCount = items.filter((item) => item.probability_band === 'Hold').length;
  const lowQualityCount = items.filter((item) => item.valuation_quality === 'LOW').length;
  const reviewCount = items.filter((item) => item.manual_review_required).length;

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Phase 8A"
        title="Internal opportunity ranking"
        summary="Ranking stays planning-first: hidden planning band first, then expected uplift, valuation quality, urgency, asking-price presence, and same-borough support. Phase 8A visibility controls can block publication without mutating the frozen result."
        actions={
          <div className="page-actions__group">
            <Link className="button button--ghost" href="/assessments">
              Assessments
            </Link>
            <Link className="button button--ghost" href="/admin/model-releases">
              Model releases
            </Link>
          </div>
        }
      />

      <section className="stat-grid">
        <StatCard tone="success" label="Band A" value={String(bandACount)} detail="Highest hidden planning band with sufficient quality" />
        <StatCard tone="danger" label="Hold" value={String(holdCount)} detail="Cases that are not honestly rankable yet" />
        <StatCard tone="warning" label="Low quality" value={String(lowQualityCount)} detail="Valuation quality LOW forces manual review" />
        <StatCard tone="accent" label="Manual review" value={String(reviewCount)} detail="Planning or valuation review flags remain visible" />
      </section>

      <Panel eyebrow="Filters" title="Opportunity filters" note={result.apiAvailable ? 'Live API' : 'API unavailable'}>
        <form className="form-stack" method="get" style={{ display: 'grid', gap: 12 }}>
          <div className="split-grid">
            <label className="field">
              <span className="field__label">Borough</span>
              <input defaultValue={borough} name="borough" placeholder="camden" type="text" />
            </label>
            <label className="field">
              <span className="field__label">Probability band</span>
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
              <span className="field__label">Valuation quality</span>
              <select defaultValue={valuationQuality} name="valuation_quality">
                <option value="">All</option>
                <option value="HIGH">HIGH</option>
                <option value="MEDIUM">MEDIUM</option>
                <option value="LOW">LOW</option>
              </select>
            </label>
          </div>
          <div className="split-grid">
            <label className="field">
              <span className="field__label">Manual review</span>
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
            <label className="field">
              <span className="field__label">Auction deadline window (days)</span>
              <input
                defaultValue={auctionDeadlineDays ?? ''}
                min={0}
                name="auction_deadline_days"
                type="number"
              />
            </label>
            <label className="field">
              <span className="field__label">Min asking price</span>
              <input defaultValue={minPrice ?? ''} min={0} name="min_price" type="number" />
            </label>
            <label className="field">
              <span className="field__label">Max asking price</span>
              <input defaultValue={maxPrice ?? ''} min={0} name="max_price" type="number" />
            </label>
          </div>
          <div className="button-row" style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            <button className="button" type="submit">
              Apply filters
            </button>
            <Link className="button button--ghost" href="/opportunities">
              Reset
            </Link>
          </div>
        </form>
      </Panel>

      <Panel
        eyebrow="Ranking"
        title="Opportunity list"
        note="This surface is hidden/internal only. It must not be treated as a visible-probability analyst queue."
      >
        {items.length === 0 ? (
          <p className="empty-note">No ranked opportunities are available for the current filters.</p>
        ) : (
          <div className="table-wrap">
            <table className="table-shell">
              <thead>
                <tr>
                  <th>Site</th>
                  <th>Band</th>
                  <th>Valuation</th>
                  <th>Expected uplift</th>
                  <th>Asking price</th>
                  <th>Review</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.site_id}>
                    <td>
                      <div className="table-primary">
                        <Link href={`/sites/${item.site_id}`}>{item.display_name}</Link>
                      </div>
                      <div className="table-secondary">
                        {item.borough_name ?? item.borough_id ?? 'Unknown borough'}
                      </div>
                      <div className="table-secondary">{item.ranking_reason}</div>
                    </td>
                    <td>
                      <Badge tone={bandTone(item.probability_band)}>{item.probability_band}</Badge>
                      <div className="table-secondary">{item.hold_reason ?? 'Rankable'}</div>
                    </td>
                    <td>
                      <Badge tone={valuationTone(item.valuation_quality)}>{item.valuation_quality ?? 'Unknown'}</Badge>
                      <div className="table-secondary">
                        Post-permission {formatCurrency(item.post_permission_value_mid)}
                      </div>
                    </td>
                    <td>
                      <div className="table-primary">{formatCurrency(item.expected_uplift_mid)}</div>
                      <div className="table-secondary">
                        Uplift {formatCurrency(item.uplift_mid)}
                      </div>
                    </td>
                    <td>
                      <div className="table-primary">{formatCurrency(item.asking_price_gbp)}</div>
                      <div className="table-secondary">
                        {item.asking_price_basis_type ?? 'Basis unavailable'}
                      </div>
                    </td>
                    <td>
                      <Badge tone={item.manual_review_required ? 'warning' : 'success'}>
                        {item.manual_review_required ? 'Required' : 'Clear'}
                      </Badge>
                      <div className="table-secondary">
                        Same-borough support {item.same_borough_support_count}
                      </div>
                      {item.assessment_id ? (
                        <div className="table-secondary">
                          <Link href={`/assessments/${item.assessment_id}?mode=hidden`}>
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
        )}
      </Panel>
    </div>
  );
}
