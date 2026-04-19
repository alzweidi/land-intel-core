import Link from 'next/link';

import { Badge, DefinitionList, PageHeader, Panel, StatCard, TableShell } from '@/components/ui';
import { getAuthContext } from '@/lib/auth/server';
import { getListingSources, getListings } from '@/lib/landintel-api';
import { getListingLabel, getSourceLabel } from '@/lib/presentation';

export const dynamic = 'force-dynamic';

type SearchParams = Record<string, string | string[] | undefined> | undefined;

function firstValue(value: string | string[] | undefined): string {
  if (Array.isArray(value)) {
    return value[0] ?? '';
  }

  return value ?? '';
}

function displayCount(count: number): string {
  return new Intl.NumberFormat('en-GB').format(count);
}

export default async function ListingsPage({ searchParams }: { searchParams?: SearchParams }) {
  const auth = await getAuthContext();
  const role = auth.role ?? 'analyst';
  const params = (await Promise.resolve(searchParams ?? {})) as Record<string, string | string[] | undefined>;
  const filters = {
    q: firstValue(params.q),
    source: firstValue(params.source),
    status: firstValue(params.status),
    type: firstValue(params.type),
    cluster: firstValue(params.cluster)
  };

  const [listingResult, sourceResult] = await Promise.all([getListings(filters), getListingSources()]);
  const sourceItems = sourceResult.items;

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Listings"
        title="Listing intake ledger"
        summary="Search live London listing intake, inspect immutable snapshot rows, and move quickly into cluster review. Listing text remains market evidence only, never planning truth."
        actions={
          <div className="page-actions__group">
            <Link className="button button--solid" href="/listing-clusters">
              View clusters
            </Link>
            {role === 'admin' ? (
              <Link className="button button--ghost" href="/admin/source-runs">
                Run connector
              </Link>
            ) : null}
          </div>
        }
      />

      <section className="stat-grid">
        <StatCard
          tone="accent"
          label="Listings"
          value={displayCount(listingResult.items.length)}
          detail={listingResult.apiAvailable ? 'Live API rows in the current query' : 'Local fallback rows in the current query'}
        />
        <StatCard tone="success" label="Sources" value={displayCount(sourceItems.length)} detail={sourceResult.apiAvailable ? 'Live source metadata for listing filters' : 'Source filters unavailable until /api/listings/sources responds'} />
        <StatCard tone="warning" label="Query" value={filters.q ? 'Filtered' : 'All rows'} detail="GET form filters the visible list" />
        <StatCard tone="neutral" label="Compliance" value="Enforced" detail="Public-page runs remain blocked unless approved" />
      </section>

      <div className="split-grid">
        <Panel
          eyebrow="Filters"
          title="Search listings"
          note="Deep-linkable GET filters keep review states shareable."
        >
          <form className="toolbar-form" method="get">
            <label className="field">
              <span>Search</span>
              <input name="q" defaultValue={filters.q} placeholder="Headline, URL, borough, source" />
            </label>
            <label className="field">
              <span>Source key</span>
              <select name="source" defaultValue={filters.source}>
                <option value="">All sources</option>
                {sourceItems.map((source) => (
                  <option key={source.source_key} value={source.source_key}>
                    {source.source_key}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Status</span>
              <select name="status" defaultValue={filters.status}>
                <option value="">Any</option>
                <option value="LIVE">LIVE</option>
                <option value="UNDER OFFER">UNDER OFFER</option>
                <option value="SOLD">SOLD</option>
                <option value="WITHDRAWN">WITHDRAWN</option>
              </select>
            </label>
            <label className="field">
              <span>Listing type</span>
              <select name="type" defaultValue={filters.type}>
                <option value="">Any</option>
                <option value="LAND">LAND</option>
                <option value="AUCTION">AUCTION</option>
                <option value="BROKER_DROP">BROKER_DROP</option>
              </select>
            </label>
            <label className="field">
              <span>Cluster key</span>
              <input name="cluster" defaultValue={filters.cluster} placeholder="riverside-yard" />
            </label>
            <div className="toolbar-form__actions">
              <button className="button button--solid" type="submit">
                Apply filters
              </button>
              <Link className="button button--ghost" href="/listings">
                Reset
              </Link>
            </div>
          </form>
        </Panel>

        <Panel eyebrow="Source posture" title="Approved source modes">
          {sourceItems.length > 0 ? (
            <DefinitionList
              items={sourceItems.slice(0, 6).map((source) => ({
                label: source.source_key,
                value: `${source.compliance_mode} · ${source.refresh_policy}`
              }))}
            />
          ) : (
            <p className="empty-note">No live source metadata was returned. Listing rows can still render, but source filters and posture are unavailable.</p>
          )}
        </Panel>
      </div>

      <TableShell
        title="Listing rows"
        note="Each row is an immutable listing record. Cluster links are a review aid, not a site decision."
      >
        <div className="dense-table">
          <table className="table-shell table-shell--responsive">
            <thead>
              <tr>
                <th>Listing</th>
                <th>Source</th>
                <th>Status</th>
                <th>Cluster</th>
                <th>Coverage</th>
              </tr>
            </thead>
            <tbody>
              {listingResult.items.map((item) => (
                <tr key={item.id}>
                  <td data-label="Listing">
                    <div className="table-primary">
                      <Link href={`/listings/${item.id}`}>{getListingLabel(item)}</Link>
                    </div>
                    <div className="table-secondary">{item.canonical_url}</div>
                  </td>
                  <td data-label="Source">
                    <div className="table-primary">{getSourceLabel(item.source_name, item.source_key)}</div>
                    <div className="table-secondary">
                      {item.source_key
                        ? `${item.source_key} · ${item.borough || 'Unknown borough'}`
                        : item.borough || 'Unknown borough'}
                    </div>
                  </td>
                  <td data-label="Status">
                    <Badge tone={item.latest_status === 'LIVE' ? 'success' : item.latest_status === 'UNDER OFFER' ? 'warning' : 'neutral'}>
                      {item.latest_status}
                    </Badge>
                    <div className="table-secondary">{item.parse_status}</div>
                  </td>
                  <td data-label="Cluster">
                    {item.cluster_id ? (
                      <Link className="inline-link" href={`/listing-clusters/${item.cluster_id}`}>
                        {item.cluster_key ?? item.cluster_id}
                      </Link>
                    ) : (
                      <span className="table-secondary">Unclustered</span>
                    )}
                  </td>
                  <td data-label="Coverage">{item.coverage_note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </TableShell>

      <section className="split-grid">
        <Panel eyebrow="Source approval" title="Connector guardrails">
          {sourceItems.length > 0 ? (
            <DefinitionList
              items={sourceItems.map((source) => ({
                label: source.source_key,
                value: `${source.compliance_mode} · ${source.refresh_policy}`
              }))}
            />
          ) : (
            <p className="empty-note">No live listing-source metadata was returned for this environment.</p>
          )}
        </Panel>
        <Panel eyebrow="Notes" title="Analyst reminders">
          <ul className="checklist">
            <li>Manual URL intake always remains available.</li>
            <li>CSV broker drops can be imported without portal scraping.</li>
            <li>Public-page runs stay blocked unless the source is approved.</li>
            <li>Snapshot rows are immutable and never overwritten.</li>
          </ul>
        </Panel>
      </section>
    </div>
  );
}
