import Link from 'next/link';

import { Badge, PageHeader, Panel, StatCard } from '@/components/ui';
import { getAuthContext } from '@/lib/auth/server';
import { getClusters } from '@/lib/landintel-api';
import { getClusterLabel } from '@/lib/presentation';

export const dynamic = 'force-dynamic';

function displayCount(count: number): string {
  return new Intl.NumberFormat('en-GB').format(count);
}

export default async function ListingClustersPage() {
  const auth = await getAuthContext();
  const role = auth.role ?? 'analyst';
  const result = await getClusters();

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
        <StatCard tone="accent" label="Clusters" value={displayCount(result.items.length)} detail="Current duplicate groups in the review queue" />
        <StatCard tone="warning" label="Review" value="Needed" detail="Cluster scores are advisory only" />
        <StatCard tone="success" label="Mode" value={result.apiAvailable ? 'Live API' : 'Fallback'} detail="Live data is preferred whenever the API is reachable" />
        <StatCard tone="neutral" label="Merge rule" value="Disabled" detail="Nothing merges permanently in this review surface" />
      </section>

      <Panel eyebrow="Cluster list" title="Duplicate opportunity groups">
        <div className="table-wrap">
          <table className="table-shell">
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
                  <td>
                    <div className="table-primary">
                      <Link href={`/listing-clusters/${cluster.id}`}>{cluster.cluster_key}</Link>
                    </div>
                    <div className="table-secondary">{cluster.id}</div>
                  </td>
                  <td>{getClusterLabel(cluster.canonical_headline, cluster.cluster_key, cluster.id)}</td>
                  <td>{cluster.borough}</td>
                  <td>
                    <Badge tone={cluster.cluster_status === 'ACTIVE' ? 'success' : cluster.cluster_status === 'REVIEW' ? 'warning' : 'neutral'}>
                      {cluster.cluster_status}
                    </Badge>
                    <div className="table-secondary">{cluster.coverage_note}</div>
                  </td>
                  <td>{cluster.member_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
