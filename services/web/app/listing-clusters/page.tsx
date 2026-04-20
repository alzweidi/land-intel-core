import Link from 'next/link';

import { Badge, PageHeader, Panel, StatCard } from '@/components/ui';
import { getAuthContext } from '@/lib/auth/server';
import { getClusters, getReadbackState } from '@/lib/landintel-api';
import { getClusterLabel } from '@/lib/presentation';

export const dynamic = 'force-dynamic';

function displayCount(count: number): string {
  return new Intl.NumberFormat('en-GB').format(count);
}

export default async function ListingClustersPage() {
  const auth = await getAuthContext();
  const role = auth.role ?? 'analyst';
  const result = await getClusters();
  const clusterState = getReadbackState(result.apiAvailable, result.items.length);

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Clusters"
        title="Cluster review queue"
        summary="Review deterministic duplicate groups built from source listing IDs, canonical URLs, address similarity, brochure hashes, and nearby coordinates. No irreversible merge behavior."
        actions={
          <div className="page-actions__group">
            <Link className="button button--solid" href="/listings">
              Back to listings
            </Link>
            {role === 'admin' ? (
              <Link className="button button--ghost" href="/admin/source-runs">
                Connector runs
              </Link>
            ) : null}
          </div>
        }
      />

      <section className="stat-grid">
        <StatCard
          tone="accent"
          label="Clusters"
          value={displayCount(result.items.length)}
          detail={
            clusterState === 'LIVE'
              ? 'Current duplicate groups in the live review queue'
              : clusterState === 'EMPTY'
                ? 'Live API returned zero cluster groups'
                : 'Fallback cluster rows are being shown'
          }
        />
        <StatCard tone="warning" label="Review" value="Needed" detail="Cluster scores are advisory only" />
        <StatCard tone="success" label="Mode" value={clusterState === 'FALLBACK' ? 'Fallback' : 'Live API'} detail="Live data is preferred whenever the API is reachable" />
        <StatCard tone="neutral" label="Merge rule" value="Disabled" detail="Nothing merges permanently in this review surface" />
      </section>

      <Panel
        eyebrow="Automation"
        title="Cluster to site progression"
        note="Eligible live land clusters are promoted into site refresh jobs automatically. This surface remains a review aid and never overwrites prior evidence."
      >
        <p className="empty-note">
          Automated runs can create listing rows, rebuild clusters, enqueue site builds, and then hand off to scenario suggestion. If the live API returns zero clusters here, the system is telling you there is nothing eligible yet rather than fabricating review items.
        </p>
      </Panel>

      <Panel eyebrow="Cluster list" title="Duplicate opportunity groups">
        {result.items.length > 0 ? (
          <div className="table-wrap">
            <table className="table-shell table-shell--responsive cluster-table">
              <thead>
                <tr>
                  <th>Cluster</th>
                  <th>Headline</th>
                  <th>Borough</th>
                  <th>Status</th>
                  <th>Members</th>
                </tr>
              </thead>
              <tbody>
                {result.items.map((cluster) => (
                  <tr key={cluster.id}>
                    <td data-label="Cluster">
                      <div className="table-primary">
                        <Link href={`/listing-clusters/${cluster.id}`}>{cluster.cluster_key}</Link>
                      </div>
                      <div className="table-secondary">{cluster.id}</div>
                    </td>
                    <td data-label="Headline">
                      {getClusterLabel(cluster.canonical_headline, cluster.cluster_key, cluster.id)}
                    </td>
                    <td data-label="Borough">{cluster.borough}</td>
                    <td data-label="Status">
                      <Badge tone={cluster.cluster_status === 'ACTIVE' ? 'success' : cluster.cluster_status === 'REVIEW' ? 'warning' : 'neutral'}>
                        {cluster.cluster_status}
                      </Badge>
                      <div className="table-secondary">{cluster.coverage_note}</div>
                    </td>
                    <td data-label="Members">{cluster.member_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="empty-note">
            {clusterState === 'EMPTY'
              ? 'Live API returned zero listing clusters. Run an approved automated source or wait for the cluster rebuild job to finish.'
              : 'No live cluster rows were returned, so the page is not inventing fixture review groups.'}
          </p>
        )}
      </Panel>
    </div>
  );
}
