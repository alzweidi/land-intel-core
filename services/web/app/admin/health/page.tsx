import Link from 'next/link';

import { Badge, DefinitionList, PageHeader, Panel } from '@/components/ui';
import { adminChecks } from '@/lib/mock-data';

export default function AdminHealthPage() {
  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Admin / health"
        title="Operational health shell"
        summary="The admin health route is a placeholder control surface for jobs, auth, and service checks. It is designed to be obviously unfinished."
        actions={
          <Link className="button button--solid" href="/admin/source-runs">
            Open source runs
          </Link>
        }
      />

      <section className="stat-grid">
        <div className="stat-card">
          <Badge tone="accent">Jobs</Badge>
          <div className="stat-value">Queued later</div>
          <p className="stat-detail">Postgres-backed polling is reserved for backend implementation.</p>
        </div>
        <div className="stat-card">
          <Badge tone="success">Auth</Badge>
          <div className="stat-value">Supabase-ready</div>
          <p className="stat-detail">Frontend env vars are scaffolded for later auth wiring.</p>
        </div>
        <div className="stat-card">
          <Badge tone="warning">Metrics</Badge>
          <div className="stat-value">Stubbed</div>
          <p className="stat-detail">No live health telemetry is implemented here.</p>
        </div>
      </section>

      <div className="split-grid">
        <Panel eyebrow="Checks" title="Service states">
          <div className="card-stack">
            {adminChecks.map((check) => (
              <article className="mini-card" key={check.name}>
                <div className="mini-card__top">
                  <div>
                    <div className="table-primary">{check.name}</div>
                    <div className="table-secondary">{check.detail}</div>
                  </div>
                  <Badge tone={check.state === 'Supabase-ready' ? 'success' : 'warning'}>{check.state}</Badge>
                </div>
              </article>
            ))}
          </div>
        </Panel>

        <Panel eyebrow="Roles" title="Auth and access model">
          <DefinitionList
            items={[
              { label: 'Analyst', value: 'Review, edit, and assess surfaces later' },
              { label: 'Reviewer', value: 'Manual-review and sign-off later' },
              { label: 'Admin', value: 'Role and environment control later' }
            ]}
          />
        </Panel>
      </div>
    </div>
  );
}
