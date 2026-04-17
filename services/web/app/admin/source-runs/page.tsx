import Link from 'next/link';

import { Badge, PageHeader, Panel, StatCard } from '@/components/ui';
import { readSessionTokenFromCookies } from '@/lib/auth/server';
import { ListingRunPanel } from '@/components/listing-run-panel';
import { getSourceRuns } from '@/lib/landintel-api';
import { phase1ASources } from '@/lib/phase1a-data';

export const dynamic = 'force-dynamic';

export default async function SourceRunsPage() {
  const sessionToken = await readSessionTokenFromCookies();
  const result = await getSourceRuns({ sessionToken: sessionToken ?? undefined });

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
        <StatCard tone="accent" label="Runs" value={new Intl.NumberFormat('en-GB').format(result.items.length)} detail="Manual intake, CSV, and connector triggers" />
        <StatCard tone="warning" label="Compliance" value="Required" detail="Public-page runs need approval first" />
        <StatCard tone="success" label="Source types" value={new Intl.NumberFormat('en-GB').format(phase1ASources.length)} detail="Manual, CSV, and public-page source records" />
        <StatCard tone="neutral" label="API mode" value={result.apiAvailable ? 'Live API' : 'Fallback'} detail="Live rows are preferred whenever the API is reachable" />
      </section>

      <Panel
        eyebrow="Run forms"
        title="Trigger listing acquisition"
        note="The connector forms post directly to the existing intake routes. Manual URL intake stays available even when automated portals remain blocked."
      >
        <ListingRunPanel />
      </Panel>

      <Panel eyebrow="Approval" title="Source compliance table">
        <div className="table-wrap">
          <table className="table-shell table-shell--responsive">
            <thead>
              <tr>
                <th>Source key</th>
                <th>Connector</th>
                <th>Compliance mode</th>
                <th>Active</th>
                <th>Coverage note</th>
              </tr>
            </thead>
            <tbody>
              {phase1ASources.map((source) => (
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
                  <td data-label="Coverage note">{source.coverage_note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
