import Link from 'next/link';
import { notFound } from 'next/navigation';

import { Badge, DefinitionList, PageHeader, Panel } from '@/components/ui';
import { getCluster } from '@/lib/landintel-api';

export const dynamic = 'force-dynamic';

type ClusterPageProps = {
  params: Promise<{ clusterId: string }> | { clusterId: string };
};

export default async function ListingClusterDetailPage({ params }: ClusterPageProps) {
  const { clusterId } = await Promise.resolve(params);
  const result = await getCluster(clusterId);

  if (!result.item) {
    notFound();
  }

  const cluster = result.item;

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Cluster detail"
        title={cluster.canonical_headline}
        summary="This view shows the cluster record and its source members. The confidence scores are advisory and never collapse into an irreversible merge."
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
          <p className="stat-detail">{cluster.coverage_note}</p>
        </div>
        <div className="stat-card">
          <Badge tone="accent">Members</Badge>
          <div className="stat-value">{cluster.member_count}</div>
          <p className="stat-detail">Confidence-scored duplicates only.</p>
        </div>
        <div className="stat-card">
          <Badge tone="neutral">Borough</Badge>
          <div className="stat-value">{cluster.borough}</div>
          <p className="stat-detail">London-first clustering only.</p>
        </div>
        <div className="stat-card">
          <Badge tone="neutral">API mode</Badge>
          <div className="stat-value">{result.apiAvailable ? 'Live' : 'Fallback'}</div>
          <p className="stat-detail">Page renders with fixture data if needed.</p>
        </div>
      </section>

      <section className="split-grid">
        <Panel eyebrow="Cluster metadata" title="Cluster summary">
          <DefinitionList
            items={[
              { label: 'Cluster ID', value: cluster.id },
              { label: 'Cluster key', value: cluster.cluster_key },
              { label: 'Created at', value: cluster.created_at },
              { label: 'Canonical headline', value: cluster.canonical_headline },
              { label: 'Coverage note', value: cluster.coverage_note }
            ]}
          />
        </Panel>
        <Panel eyebrow="Rules" title="Deterministic v1 logic">
          <ul className="checklist">
            <li>Source listing ID and canonical URL are primary signals.</li>
            <li>Normalized address and brochure hash can strengthen a candidate match.</li>
            <li>Headline similarity and coordinate proximity are advisory only.</li>
            <li>Nothing merges permanently in Phase 1A.</li>
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
              {cluster.members.map((member) => (
                <tr key={member.id}>
                  <td>
                    <div className="table-primary">
                      <Link href={`/listings/${member.listing_item_id}`}>{member.listing_headline}</Link>
                    </div>
                    <div className="table-secondary">{member.canonical_url}</div>
                  </td>
                  <td>{member.source_name}</td>
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

