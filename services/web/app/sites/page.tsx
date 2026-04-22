import Link from 'next/link';

import { Badge, DefinitionList, PageHeader, Panel, StatCard } from '@/components/ui';
import { SiteMap } from '@/components/site-map';
import { getReadbackState, getSites } from '@/lib/landintel-api';

export const dynamic = 'force-dynamic';

type SearchParams = Record<string, string | string[] | undefined> | undefined;

function firstValue(value: string | string[] | undefined): string {
  if (Array.isArray(value)) {
    return value[0] ?? '';
  }

  return value ?? '';
}

function confidenceTone(value: string): 'neutral' | 'accent' | 'success' | 'warning' | 'danger' {
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

function summarizeWarnings(items: Array<{ warnings: string[] }>): string[] {
  return [...new Set(items.flatMap((item) => item.warnings))];
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

export default async function SitesPage({ searchParams }: { searchParams?: SearchParams }) {
  const params = (await Promise.resolve(searchParams ?? {})) as Record<string, string | string[] | undefined>;
  const filters = {
    q: firstValue(params.q),
    borough: firstValue(params.borough),
    confidence: firstValue(params.confidence) as 'HIGH' | 'MEDIUM' | 'LOW' | 'INSUFFICIENT' | ''
  };

  const result = await getSites(filters);
  const items = result.items;
  const siteState = getReadbackState(result.apiAvailable, items.length);
  const selectedSiteId = firstValue(params.selected) || items[0]?.site_id;
  const selectedSite = items.find((item) => item.site_id === selectedSiteId) ?? items[0] ?? null;
  const warningSummary = summarizeWarnings(items);
  const highCount = items.filter((item) => item.geometry_confidence === 'HIGH').length;
  const reviewCount = items.filter((item) => item.review_flags.length > 0).length;

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Sites"
        title="Site registry"
        summary="Work through confirmed site candidates with map, geometry confidence, borough assignment, planning context, and extant-permission posture in one dense review surface."
        badges={
          <div className="status-strip">
            <Badge tone={readbackTone(siteState)}>{readbackLabel(siteState)}</Badge>
          </div>
        }
        actions={
          selectedSite ? (
            <Link className="button button--ghost" href={`/sites/${selectedSite.site_id}`}>
              Open selected site
            </Link>
          ) : undefined
        }
      />

      <section className="stat-grid">
        <StatCard tone="accent" label="Sites" value={String(items.length)} detail={result.apiAvailable ? 'Loaded from the API' : 'Loaded from the local fallback dataset'} />
        <StatCard tone="success" label="High confidence" value={String(highCount)} detail="Geometry source and confidence are visible on every row" />
        <StatCard tone="warning" label="Manual review" value={String(reviewCount)} detail="Coverage gaps and other warnings stay visible when a site needs analyst attention" />
        <StatCard tone="neutral" label="Warnings" value={String(warningSummary.length)} detail="Unique caveats across the visible candidate set" />
      </section>

      <div className="split-grid split-grid--map-first">
        <Panel
          eyebrow="Map"
          title="Candidate map"
          note="MapLibre shows site evidence only. It is a working map, not a declaration of legal boundary truth."
        >
          <SiteMap height={560} sites={items} selectedSiteId={selectedSiteId} />
        </Panel>

        <Panel eyebrow="Filters" title="Candidate list">
          <form className="toolbar-form" method="get">
            <label className="field">
              <span>Search</span>
              <input name="q" defaultValue={filters.q} placeholder="Name, borough, warning text" />
            </label>
            <label className="field">
              <span>Borough</span>
              <input name="borough" defaultValue={filters.borough} placeholder="Hackney" />
            </label>
            <label className="field">
              <span>Confidence</span>
              <select name="confidence" defaultValue={filters.confidence}>
                <option value="">All</option>
                <option value="HIGH">HIGH</option>
                <option value="MEDIUM">MEDIUM</option>
                <option value="LOW">LOW</option>
                <option value="INSUFFICIENT">INSUFFICIENT</option>
              </select>
            </label>
            <div className="toolbar-form__actions">
              <button className="button button--solid" type="submit">
                Apply
              </button>
              <Link className="button button--ghost" href="/sites">
                Reset
              </Link>
            </div>
          </form>

          {items.length > 0 ? (
            <div className="table-wrap">
              <table className="table-shell table-shell--responsive site-list-table">
                <thead>
                  <tr>
                    <th>Site</th>
                    <th>Borough / LPA</th>
                    <th>Geometry</th>
                    <th>Listing</th>
                    <th>Warnings</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((item) => (
                    <tr key={item.site_id}>
                      <td data-label="Site">
                        <div className="table-primary">
                          <Link href={`/sites/${item.site_id}`}>{item.display_name}</Link>
                        </div>
                        <div className="table-secondary">{item.cluster_key}</div>
                      </td>
                      <td data-label="Borough / LPA">
                        <div className="table-primary">{item.borough_name}</div>
                        <div className="table-secondary">{item.controlling_lpa_name}</div>
                      </td>
                      <td data-label="Geometry">
                        <Badge tone={confidenceTone(item.geometry_confidence)}>{item.geometry_source_type}</Badge>
                        <div className="table-secondary">{item.geometry_confidence}</div>
                        <div className="table-secondary">{item.site_area_sqm === null ? 'Area pending' : `${item.site_area_sqm.toLocaleString('en-GB')} sqm`}</div>
                      </td>
                      <td data-label="Listing">
                        <div className="table-primary">{item.current_listing_headline}</div>
                        <div className="table-secondary">{item.current_price_gbp === null ? 'Price pending' : `£${item.current_price_gbp.toLocaleString('en-GB')}`}</div>
                        {item.current_listing_canonical_url ? (
                          <div className="table-secondary">
                            <a className="inline-link" href={item.current_listing_canonical_url} rel="noreferrer" target="_blank">
                              Open live source
                            </a>
                          </div>
                        ) : null}
                      </td>
                      <td data-label="Warnings">
                        <div className="table-secondary">{item.review_flags.join(', ') || 'No manual flags'}</div>
                        <div className="table-secondary">{item.warnings[0] ?? 'No warnings recorded'}</div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="empty-note">
              {siteState === 'EMPTY'
                ? 'No live site rows matched the current filter set.'
                : 'Live site data is unavailable, so the registry is held in fallback mode.'}
            </p>
          )}
        </Panel>
      </div>

      <div className="split-grid">
        <Panel eyebrow="Focused site" title="Current selection">
          {selectedSite ? (
            <DefinitionList
              items={[
                { label: 'Display name', value: selectedSite.display_name },
                { label: 'Listing', value: selectedSite.current_listing_headline },
                {
                  label: 'Listing URL',
                  value: selectedSite.current_listing_canonical_url ? (
                    <a
                      className="inline-link"
                      href={selectedSite.current_listing_canonical_url}
                      rel="noreferrer"
                      target="_blank"
                    >
                      Open live source
                    </a>
                  ) : 'Unavailable'
                },
                { label: 'Source', value: selectedSite.geometry_source_type },
                { label: 'Confidence', value: selectedSite.geometry_confidence },
                { label: 'Borough / LPA', value: `${selectedSite.borough_name} / ${selectedSite.controlling_lpa_name}` },
                {
                  label: 'Warnings',
                  value: selectedSite.warnings.length > 0 ? selectedSite.warnings.join(' ') : 'None'
                }
              ]}
            />
          ) : (
            <p className="empty-note">No site candidate is available in the current filter set.</p>
          )}
        </Panel>

        <Panel eyebrow="Evidence" title="Visible caveats">
          {warningSummary.length > 0 ? (
            <div className="mini-list">
              {warningSummary.map((warning) => (
                <div className="mini-list__row" key={warning}>
                  <span>{warning}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="empty-note">No warnings are visible in the current filter set.</p>
          )}
        </Panel>
      </div>
    </div>
  );
}
