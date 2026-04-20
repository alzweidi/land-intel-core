import Link from 'next/link';

import { Badge, PageHeader, Panel, StatCard } from '@/components/ui';
import { readSessionTokenFromCookies } from '@/lib/auth/server';
import { ListingRunPanel } from '@/components/listing-run-panel';
import { countListingConsoleRuns } from '@/lib/listing-source-console';
import { getAdminJobs, getListingSources } from '@/lib/landintel-api';

export const dynamic = 'force-dynamic';

export default async function SourceRunsPage() {
  const sessionToken = await readSessionTokenFromCookies();
  const [sourceResult, jobsResult] = await Promise.all([
    getListingSources(),
    getAdminJobs({ sessionToken: sessionToken ?? undefined })
  ]);
  const runCount = countListingConsoleRuns(jobsResult.items);
  const apiMode = sourceResult.apiAvailable && jobsResult.apiAvailable
    ? 'Live API'
    : sourceResult.apiAvailable || jobsResult.apiAvailable
      ? 'Partial'
      : 'Unavailable';

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Admin"
        title="Connector run console"
        summary="Use this surface to post a manual URL, import a broker CSV, or trigger an approved public-page connector. Any unapproved source must stay blocked."
        actions={
          <div className="page-actions__group">
            <Link className="button button--solid" href="/listings">
              Open listings
            </Link>
            <Link className="button button--ghost" href="/listing-clusters">
              Open clusters
            </Link>
          </div>
        }
      />

      <section className="stat-grid">
        <StatCard tone="accent" label="Runs" value={new Intl.NumberFormat('en-GB').format(runCount)} detail="Manual intake, CSV, and connector triggers" />
        <StatCard tone="warning" label="Compliance" value="Required" detail="Public-page runs need approval first" />
        <StatCard tone="success" label="Source types" value={new Intl.NumberFormat('en-GB').format(sourceResult.items.length)} detail={sourceResult.apiAvailable ? 'Live listing_source rows' : 'No live source metadata returned'} />
        <StatCard tone="neutral" label="API mode" value={apiMode} detail="Live rows are preferred whenever the API is reachable" />
      </section>

      <Panel
        eyebrow="Run forms"
        title="Trigger listing acquisition"
        note="The connector forms post directly to the existing intake routes. Manual URL intake stays available even when automated portals remain blocked."
      >
        <ListingRunPanel sourceOptions={sourceResult.items} />
      </Panel>

      <Panel eyebrow="Approval" title="Source compliance table">
        {sourceResult.items.length > 0 ? (
          <div className="table-wrap">
            <table className="table-shell table-shell--responsive">
              <thead>
                <tr>
                  <th>Source key</th>
                  <th>Connector</th>
                  <th>Compliance mode</th>
                  <th>Active</th>
                  <th>Refresh policy</th>
                </tr>
              </thead>
              <tbody>
                {sourceResult.items.map((source) => (
                  <tr key={source.source_key}>
                    <td data-label="Source key">
                      <div className="table-primary">{source.name}</div>
                      <div className="table-secondary">{source.source_key}</div>
                    </td>
                    <td data-label="Connector">{source.connector_type}</td>
                    <td data-label="Compliance mode">
                      <Badge tone={source.compliance_mode === 'COMPLIANT_AUTOMATED' ? 'success' : source.compliance_mode === 'BLOCKED' ? 'danger' : 'warning'}>
                        {source.compliance_mode}
                      </Badge>
                    </td>
                    <td data-label="Active">{source.active ? 'Yes' : 'No'}</td>
                    <td data-label="Refresh policy">{source.refresh_policy}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="empty-note">No live listing-source metadata was returned. Seed approved sources and retry.</p>
        )}
      </Panel>
    </div>
  );
}
