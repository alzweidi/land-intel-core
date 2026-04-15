import Link from 'next/link';

import { Badge, PageHeader, Panel, StatCard } from '@/components/ui';
import { getClusters } from '@/lib/landintel-api';

export const dynamic = 'force-dynamic';

function displayCount(count: number): string {
  return new Intl.NumberFormat('en-GB').format(count);
}

export default async function ListingClustersPage() {
  const result = await getClusters();

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Clusters"
        title="Deterministic duplicate cluster review"
        summary="Clusters are built from boring rules only: source listing IDs, canonical URLs, normalized address matches, brochure hashes, and nearby coordinates. No irreversible merge behavior."
        actions={
          <div className="page-actions__group">
            <Link className="button button--solid" href="/listings">
              Back to listings
            </Link>
            <Link className="button button--ghost" href="/admin/source-runs">
              Connector runs
            </Link>
          </div>
        }
      />

      <section className="stat-grid">
        <StatCard tone="accent" label="Clusters" value={displayCount(result.items.length)} detail="Sample fixture set or live API result" />
        <StatCard tone="warning" label="Review" value="Needed" detail="Cluster scores are advisory only" />
        <StatCard tone="success" label="API" value={result.apiAvailable ? 'Live' : 'Fallback'} detail="The page renders either way" />
        <StatCard tone="neutral" label="Merge rule" value="Off" detail="No irreversible merges in Phase 1A" />
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
                  <td>{cluster.canonical_headline}</td>
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

