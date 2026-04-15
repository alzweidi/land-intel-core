import Link from 'next/link';

import { Badge, DefinitionList, PageHeader, Panel, StatCard } from '@/components/ui';
import { getListingSources, getListings } from '@/lib/landintel-api';
import { phase1ASources } from '@/lib/phase1a-data';

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
  const params = (await Promise.resolve(searchParams ?? {})) as Record<string, string | string[] | undefined>;
  const filters = {
    q: firstValue(params.q),
    source: firstValue(params.source),
    status: firstValue(params.status),
    type: firstValue(params.type),
    cluster: firstValue(params.cluster)
  };

  const [listingResult, sourceResult] = await Promise.all([getListings(filters), getListingSources()]);
  const sourceItems = sourceResult.items.length > 0 ? sourceResult.items : phase1ASources;

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Phase 1A"
        title="Listing search and immutable snapshot ledger"
        summary="This surface is wired for live listings, source approval checks, and deterministic clustering. It stays deliberately plain so the audit trail remains obvious."
        actions={
          <div className="page-actions__group">
            <Link className="button button--solid" href="/listing-clusters">
              View clusters
            </Link>
            <Link className="button button--ghost" href="/admin/source-runs">
              Run connector
            </Link>
          </div>
        }
      />

      <section className="stat-grid">
        <StatCard
          tone="accent"
          label="Listings"
          value={displayCount(listingResult.items.length)}
          detail={listingResult.apiAvailable ? 'Loaded from the API route' : 'Loaded from fixture fallback'}
        />
        <StatCard tone="success" label="Sources" value={displayCount(sourceItems.length)} detail="Manual, CSV, and approved public sources" />
        <StatCard tone="warning" label="Query" value={filters.q ? 'Filtered' : 'All rows'} detail="GET form filters the visible list" />
        <StatCard tone="neutral" label="Compliance" value="Enforced" detail="Public-page runs remain blocked unless approved" />
      </section>

      <Panel
        eyebrow="Search"
        title="Filter listings"
        note="The form uses a normal GET request so analysts can deep-link to a particular search state."
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

      <Panel
        eyebrow="Listings"
        title="Listing rows"
        note="Each row is an immutable source listing, not a site decision. The current cluster key is shown only as a review aid."
      >
        <div className="table-wrap">
          <table className="table-shell">
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
                  <td>
                    <div className="table-primary">
                      <Link href={`/listings/${item.id}`}>{item.headline}</Link>
                    </div>
                    <div className="table-secondary">{item.canonical_url}</div>
                  </td>
                  <td>
                    <div className="table-primary">{item.source_name}</div>
                    <div className="table-secondary">
                      {item.source_key} · {item.borough}
                    </div>
                  </td>
                  <td>
                    <Badge tone={item.latest_status === 'LIVE' ? 'success' : item.latest_status === 'UNDER OFFER' ? 'warning' : 'neutral'}>
                      {item.latest_status}
                    </Badge>
                    <div className="table-secondary">{item.parse_status}</div>
                  </td>
                  <td>
                    {item.cluster_id ? (
                      <Link className="inline-link" href={`/listing-clusters/${item.cluster_id}`}>
                        {item.cluster_key ?? item.cluster_id}
                      </Link>
                    ) : (
                      <span className="table-secondary">Unclustered</span>
                    )}
                  </td>
                  <td>{item.coverage_note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      <section className="split-grid">
        <Panel eyebrow="Source approval" title="Approved connector modes">
          <DefinitionList
            items={sourceItems.map((source) => ({
              label: source.source_key,
              value: `${source.compliance_mode} · ${source.coverage_note}`
            }))}
          />
        </Panel>
        <Panel eyebrow="Notes" title="Phase 1A guardrails">
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

