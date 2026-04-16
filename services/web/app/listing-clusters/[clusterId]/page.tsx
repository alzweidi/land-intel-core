import Link from 'next/link';
import { notFound } from 'next/navigation';

import { Badge, DefinitionList, PageHeader, Panel } from '@/components/ui';
import { getCluster, getListings } from '@/lib/landintel-api';
import { getClusterLabel, getListingLabel, getSourceLabel } from '@/lib/presentation';

export const dynamic = 'force-dynamic';

type ClusterPageProps = {
  params: Promise<{ clusterId: string }> | { clusterId: string };
};

export default async function ListingClusterDetailPage({ params }: ClusterPageProps) {
  const { clusterId } = await Promise.resolve(params);
  const [result, listingResult] = await Promise.all([
    getCluster(clusterId),
    getListings({ cluster: clusterId })
  ]);

  if (!result.item) {
    notFound();
  }

  const cluster = result.item;
  const fallbackMembers = listingResult.items.map((item, index) => ({
    id: item.cluster_id ? `${item.cluster_id}:${item.id}` : `${clusterId}:${index}`,
    listing_item_id: item.id,
    listing_headline: getListingLabel(item),
    source_name: getSourceLabel(item.source_name, item.source_key),
    canonical_url: item.canonical_url,
    confidence: 1,
    latest_status: item.latest_status,
    created_at: item.last_seen_at
  }));
  const members =
    cluster.members.length > 0 &&
    cluster.members.some((member) => member.listing_item_id || member.listing_headline || member.canonical_url)
      ? cluster.members
      : fallbackMembers;
  const canonicalHeadline = getClusterLabel(cluster.canonical_headline, cluster.cluster_key, cluster.id);
  const borough =
    cluster.borough && cluster.borough !== 'Unknown'
      ? cluster.borough
      : listingResult.items.find((item) => item.borough)?.borough ?? 'Unknown';
  const memberCount = members.length > 0 ? members.length : cluster.member_count;
  const coverageNote =
    cluster.coverage_note ||
    listingResult.items.find((item) => item.coverage_note)?.coverage_note ||
    'Coverage details unavailable.';

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Cluster detail"
        title={canonicalHeadline}
        summary="Inspect the cluster record, member listings, and the deterministic rules that grouped them. Confidence is advisory only and never collapses into an irreversible merge."
        actions={
          <div className="page-actions__group">
            <Link className="button button--ghost" href="/listing-clusters">
              Back to clusters
            </Link>
            <Link className="button button--solid" href="/listings">
              Open listings
            </Link>
          </div>
        }
      />

      <section className="stat-grid">
        <div className="stat-card">
          <Badge tone={cluster.cluster_status === 'ACTIVE' ? 'success' : 'warning'}>{cluster.cluster_status}</Badge>
          <div className="stat-value">{cluster.cluster_key}</div>
          <p className="stat-detail">{coverageNote}</p>
        </div>
        <div className="stat-card">
          <Badge tone="accent">Members</Badge>
          <div className="stat-value">{memberCount}</div>
          <p className="stat-detail">Confidence-scored duplicates only.</p>
        </div>
        <div className="stat-card">
          <Badge tone="neutral">Borough</Badge>
          <div className="stat-value">{borough}</div>
          <p className="stat-detail">London-first clustering only.</p>
        </div>
        <div className="stat-card">
          <Badge tone="neutral">API mode</Badge>
          <div className="stat-value">{result.apiAvailable ? 'Live API' : 'Fallback'}</div>
          <p className="stat-detail">Live data is preferred whenever the API is reachable.</p>
        </div>
      </section>

      <section className="split-grid">
        <Panel eyebrow="Cluster metadata" title="Cluster summary">
          <DefinitionList
            items={[
              { label: 'Cluster ID', value: cluster.id },
              { label: 'Cluster key', value: cluster.cluster_key },
              { label: 'Created at', value: cluster.created_at },
              { label: 'Canonical headline', value: canonicalHeadline },
              { label: 'Coverage note', value: coverageNote }
            ]}
          />
        </Panel>
        <Panel eyebrow="Rules" title="Current grouping logic">
          <ul className="checklist">
            <li>Source listing ID and canonical URL are primary signals.</li>
            <li>Normalized address and brochure hash can strengthen a candidate match.</li>
            <li>Headline similarity and coordinate proximity are advisory only.</li>
            <li>Nothing merges permanently in this surface.</li>
          </ul>
        </Panel>
      </section>

      <Panel eyebrow="Members" title="Cluster members">
        <div className="table-wrap">
          <table className="table-shell">
            <thead>
              <tr>
                <th>Listing</th>
                <th>Source</th>
                <th>Confidence</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {members.map((member) => (
                <tr key={member.id}>
                  <td>
                    <div className="table-primary">
                      <Link href={`/listings/${member.listing_item_id}`}>
                        {getListingLabel({
                          id: member.listing_item_id,
                          headline: member.listing_headline,
                          canonical_url: member.canonical_url
                        })}
                      </Link>
                    </div>
                    <div className="table-secondary">{member.canonical_url}</div>
                  </td>
                  <td>{getSourceLabel(member.source_name, null)}</td>
                  <td>
                    <Badge tone={member.confidence >= 0.95 ? 'success' : member.confidence >= 0.9 ? 'warning' : 'neutral'}>
                      {(member.confidence * 100).toFixed(0)}%
                    </Badge>
                  </td>
                  <td>{member.latest_status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
