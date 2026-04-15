import Link from 'next/link';
import { notFound } from 'next/navigation';

import { Badge, DefinitionList, PageHeader, Panel } from '@/components/ui';
import { getListing } from '@/lib/landintel-api';

export const dynamic = 'force-dynamic';

type ListingPageProps = {
  params: Promise<{ listingId: string }> | { listingId: string };
};

function money(value: string): string {
  if (!value) {
    return 'Not recorded';
  }

  return `GBP ${value}`;
}

export default async function ListingDetailPage({ params }: ListingPageProps) {
  const { listingId } = await Promise.resolve(params);
  const result = await getListing(listingId);

  if (!result.item) {
    notFound();
  }

  const listing = result.item;

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Listing detail"
        title={listing.headline}
        summary="The detail view shows immutable snapshots, extracted fields, and linked documents. Nothing here should be treated as planning truth."
        actions={
          <div className="page-actions__group">
            <Link className="button button--ghost" href="/listings">
              Back to listings
            </Link>
            {listing.cluster_id ? (
              <Link className="button button--solid" href={`/listing-clusters/${listing.cluster_id}`}>
                Open cluster
              </Link>
            ) : null}
          </div>
        }
      />

      <section className="stat-grid">
        <div className="stat-card">
          <Badge tone={listing.latest_status === 'LIVE' ? 'success' : 'warning'}>{listing.latest_status}</Badge>
          <div className="stat-value">{listing.price_display}</div>
          <p className="stat-detail">{listing.coverage_note}</p>
        </div>
        <div className="stat-card">
          <Badge tone="accent">{listing.parse_status}</Badge>
          <div className="stat-value">{listing.source_key}</div>
          <p className="stat-detail">{listing.source_name}</p>
        </div>
        <div className="stat-card">
          <Badge tone="neutral">Snapshots</Badge>
          <div className="stat-value">{listing.snapshots.length}</div>
          <p className="stat-detail">Immutable history retained per connector run.</p>
        </div>
        <div className="stat-card">
          <Badge tone="neutral">Documents</Badge>
          <div className="stat-value">{listing.documents.length}</div>
          <p className="stat-detail">Brochure and map assets stay stored separately.</p>
        </div>
      </section>

      <section className="split-grid">
        <Panel eyebrow="Fields" title="Normalized listing fields">
          <DefinitionList
            items={[
              { label: 'Source listing ID', value: listing.source_listing_id },
              { label: 'Canonical URL', value: listing.canonical_url },
              { label: 'Listing type', value: listing.listing_type },
              { label: 'Borough', value: listing.borough },
              { label: 'Address', value: listing.normalized_fields.address_text || 'Not recorded' },
              { label: 'Guide price', value: money(listing.normalized_fields.guide_price_gbp) },
              { label: 'Price basis', value: listing.normalized_fields.price_basis_type },
              { label: 'Status', value: listing.normalized_fields.status },
              { label: 'Auction date', value: listing.normalized_fields.auction_date ?? 'Not recorded' },
              { label: 'Latitude', value: listing.normalized_fields.lat ?? 'Not recorded' },
              { label: 'Longitude', value: listing.normalized_fields.lon ?? 'Not recorded' }
            ]}
          />
        </Panel>
        <Panel eyebrow="Source" title="Snapshot provenance">
          <DefinitionList
            items={[
              { label: 'Source key', value: listing.source_key },
              { label: 'Source name', value: listing.source_name },
              { label: 'First seen', value: listing.first_seen_at },
              { label: 'Last seen', value: listing.last_seen_at },
              { label: 'Cluster', value: listing.cluster_key ?? 'Unclustered' },
              { label: 'API mode', value: result.apiAvailable ? 'Live API' : 'Fixture fallback' }
            ]}
          />
        </Panel>
      </section>

      <Panel eyebrow="Snapshots" title="Listing snapshots">
        <div className="card-stack">
          {listing.snapshots.map((snapshot) => (
            <article className="detail-card" key={snapshot.id}>
              <div className="detail-card__head">
                <div>
                  <div className="table-primary">{snapshot.headline}</div>
                  <div className="table-secondary">{snapshot.observed_at}</div>
                </div>
                <Badge tone={snapshot.status === 'LIVE' ? 'success' : 'warning'}>{snapshot.status}</Badge>
              </div>
              <DefinitionList
                items={[
                  { label: 'Description', value: snapshot.description_text || 'Not recorded' },
                  { label: 'Guide price', value: money(snapshot.guide_price_gbp) },
                  { label: 'Price basis', value: snapshot.price_basis_type },
                  { label: 'Address', value: snapshot.address_text },
                  { label: 'Brochure asset', value: snapshot.brochure_asset_id ?? 'Not recorded' },
                  { label: 'Map asset', value: snapshot.map_asset_id ?? 'Not recorded' }
                ]}
              />
              <details className="json-details">
                <summary>Raw normalized JSON</summary>
                <pre className="code-block">{JSON.stringify(snapshot.raw_record_json, null, 2)}</pre>
              </details>
            </article>
          ))}
        </div>
      </Panel>

      <Panel eyebrow="Documents" title="Linked documents and extraction state">
        <div className="table-wrap">
          <table className="table-shell">
            <thead>
              <tr>
                <th>Document</th>
                <th>Type</th>
                <th>Pages</th>
                <th>Extraction</th>
                <th>Asset</th>
              </tr>
            </thead>
            <tbody>
              {listing.documents.map((document) => (
                <tr key={document.id}>
                  <td>
                    <div className="table-primary">{document.filename}</div>
                    <div className="table-secondary">{document.id}</div>
                  </td>
                  <td>{document.doc_type}</td>
                  <td>{document.page_count ?? 'n/a'}</td>
                  <td>
                    <Badge tone={document.extraction_status === 'EXTRACTED' ? 'success' : document.extraction_status === 'FAILED' ? 'danger' : 'warning'}>
                      {document.extraction_status}
                    </Badge>
                    <div className="table-secondary">{document.extracted_text ?? 'No extracted text preserved'}</div>
                  </td>
                  <td>{document.asset_id}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}

