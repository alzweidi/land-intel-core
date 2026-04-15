import Link from 'next/link';

import { Badge, DefinitionList, PageHeader, Panel, StatCard } from '@/components/ui';
import { SiteMap } from '@/components/site-map';
import { getSites } from '@/lib/landintel-api';

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

export default async function SitesPage({ searchParams }: { searchParams?: SearchParams }) {
  const params = (await Promise.resolve(searchParams ?? {})) as Record<string, string | string[] | undefined>;
  const filters = {
    q: firstValue(params.q),
    borough: firstValue(params.borough),
    confidence: firstValue(params.confidence) as 'HIGH' | 'MEDIUM' | 'LOW' | 'INSUFFICIENT' | ''
  };

  const result = await getSites(filters);
  const items = result.items;
  const selectedSiteId = firstValue(params.selected) || items[0]?.site_id;
  const selectedSite = items.find((item) => item.site_id === selectedSiteId) ?? items[0] ?? null;
  const warningSummary = summarizeWarnings(items);
  const highCount = items.filter((item) => item.geometry_confidence === 'HIGH').length;
  const reviewCount = items.filter((item) => item.review_flags.length > 0).length;

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Phase 2"
        title="Site candidates"
        summary="Confirmed site records are now visible as auditable candidates. The map and detail records stay explicit about geometry confidence, borough assignment, and what is only indicative evidence."
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
        <StatCard tone="warning" label="Manual review" value={String(reviewCount)} detail="Warnings stay visible when a site needs analyst attention" />
        <StatCard tone="neutral" label="Warnings" value={String(warningSummary.length)} detail="Unique caveats across the visible candidate set" />
      </section>

      <div className="split-grid">
        <Panel
          eyebrow="Map"
          title="Candidate map"
          note="MapLibre shows site evidence only. It is a working map, not a declaration of legal boundary truth."
        >
          <SiteMap sites={items} selectedSiteId={selectedSiteId} />
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

          <div className="table-wrap">
            <table className="table-shell">
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
                    <td>
                      <div className="table-primary">
                        <Link href={`/sites/${item.site_id}`}>{item.display_name}</Link>
                      </div>
                      <div className="table-secondary">{item.cluster_key}</div>
                    </td>
                    <td>
                      <div className="table-primary">{item.borough_name}</div>
                      <div className="table-secondary">{item.controlling_lpa_name}</div>
                    </td>
                    <td>
                      <Badge tone={confidenceTone(item.geometry_confidence)}>{item.geometry_source_type}</Badge>
                      <div className="table-secondary">{item.geometry_confidence}</div>
                      <div className="table-secondary">{item.site_area_sqm === null ? 'Area pending' : `${item.site_area_sqm.toLocaleString('en-GB')} sqm`}</div>
                    </td>
                    <td>
                      <div className="table-primary">{item.current_listing_headline}</div>
                      <div className="table-secondary">{item.current_price_gbp === null ? 'Price pending' : `£${item.current_price_gbp.toLocaleString('en-GB')}`}</div>
                    </td>
                    <td>
                      <div className="table-secondary">{item.review_flags.join(', ') || 'No manual flags'}</div>
                      <div className="table-secondary">{item.warnings[0] ?? 'No warnings recorded'}</div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      </div>

      <div className="split-grid">
        <Panel eyebrow="Focused site" title="Current selection">
          {selectedSite ? (
            <DefinitionList
              items={[
                { label: 'Display name', value: selectedSite.display_name },
                { label: 'Listing', value: selectedSite.current_listing_headline },
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
