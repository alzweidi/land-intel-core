import Link from 'next/link';

import { Badge, PageHeader, Panel, StatCard } from '@/components/ui';
import { readSessionTokenFromCookies } from '@/lib/auth/server';
import { ListingRunPanel } from '@/components/listing-run-panel';
import { countListingConsoleRuns } from '@/lib/listing-source-console';
import { getAdminJobs, getListingSources, getSourceSnapshots } from '@/lib/landintel-api';

export const dynamic = 'force-dynamic';

export default async function SourceRunsPage() {
  const sessionToken = await readSessionTokenFromCookies();
  const [sourceResult, jobsResult, snapshotResult] = await Promise.all([
    getListingSources(),
    getAdminJobs({ sessionToken: sessionToken ?? undefined }),
    getSourceSnapshots({ sessionToken: sessionToken ?? undefined })
  ]);
  const runCount = countListingConsoleRuns(jobsResult.items);
  const apiMode = sourceResult.apiAvailable && jobsResult.apiAvailable && snapshotResult.apiAvailable
    ? 'Live API'
    : sourceResult.apiAvailable || jobsResult.apiAvailable || snapshotResult.apiAvailable
      ? 'Partial'
      : 'Unavailable';
  const recentRuns = jobsResult.items.filter((job) => job.job_type === 'LISTING_SOURCE_RUN').slice(0, 10);
  const recentSnapshots = snapshotResult.items.slice(0, 10);

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Admin"
        title="Connector run console"
        summary="Use this surface to post a manual URL, import a broker CSV, or trigger an approved automated source. Any unapproved source must stay blocked."
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
        <StatCard tone="warning" label="Compliance" value="Required" detail="Automated runs need approval first" />
        <StatCard tone="success" label="Source types" value={new Intl.NumberFormat('en-GB').format(sourceResult.items.length)} detail={sourceResult.apiAvailable ? 'Live listing_source rows' : 'No live source metadata returned'} />
        <StatCard tone="neutral" label="Snapshots" value={new Intl.NumberFormat('en-GB').format(recentSnapshots.length)} detail={snapshotResult.apiAvailable ? 'Recent immutable source snapshots' : 'Source snapshot evidence unavailable'} />
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
          <p className="empty-note">
            {sourceResult.apiAvailable
              ? 'The live listing source catalog returned zero rows. Seed approved sources and retry.'
              : 'No live listing-source metadata was returned. Seed approved sources and retry.'}
          </p>
        )}
      </Panel>

      <div className="split-grid">
        <Panel eyebrow="Recent runs" title="Live LISTING_SOURCE_RUN jobs">
          {recentRuns.length > 0 ? (
            <div className="table-wrap">
              <table className="table-shell table-shell--responsive">
                <thead>
                  <tr>
                    <th>Job</th>
                    <th>Status</th>
                    <th>Requested by</th>
                    <th>Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {recentRuns.map((job) => (
                    <tr key={job.id}>
                      <td data-label="Job">
                        <div className="table-primary">{job.id}</div>
                        <div className="table-secondary">
                          {String(job.payload_json.source_name ?? 'unknown-source')}
                        </div>
                      </td>
                      <td data-label="Status">
                        <Badge tone={job.status === 'SUCCEEDED' ? 'success' : job.status === 'FAILED' ? 'danger' : 'warning'}>
                          {job.status}
                        </Badge>
                      </td>
                      <td data-label="Requested by">{job.requested_by ?? 'unknown'}</td>
                      <td data-label="Updated">{job.updated_at ?? 'n/a'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="empty-note">
              {jobsResult.apiAvailable
                ? 'No live LISTING_SOURCE_RUN jobs were returned yet.'
                : 'Live admin job history is unavailable in this environment.'}
            </p>
          )}
        </Panel>

        <Panel eyebrow="Recent evidence" title="Source snapshots">
          {recentSnapshots.length > 0 ? (
            <div className="table-wrap">
              <table className="table-shell table-shell--responsive">
                <thead>
                  <tr>
                    <th>Snapshot</th>
                    <th>Parse status</th>
                    <th>Acquired</th>
                    <th>Coverage note</th>
                  </tr>
                </thead>
                <tbody>
                  {recentSnapshots.map((snapshot) => (
                    <tr key={snapshot.id}>
                      <td data-label="Snapshot">
                        <div className="table-primary">{snapshot.source_name}</div>
                        <div className="table-secondary">{snapshot.id}</div>
                      </td>
                      <td data-label="Parse status">
                        <Badge tone={snapshot.parse_status === 'PARSED' ? 'success' : snapshot.parse_status === 'FAILED' ? 'danger' : 'warning'}>
                          {snapshot.parse_status}
                        </Badge>
                      </td>
                      <td data-label="Acquired">{snapshot.acquired_at ?? 'n/a'}</td>
                      <td data-label="Coverage note">{snapshot.coverage_note || snapshot.source_family}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="empty-note">
              {snapshotResult.apiAvailable
                ? 'No live source snapshots were returned yet.'
                : 'Live source snapshot evidence is unavailable in this environment.'}
            </p>
          )}
        </Panel>
      </div>
    </div>
  );
}
