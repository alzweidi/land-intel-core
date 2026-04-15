import Link from 'next/link';

import { Badge, DefinitionList, PageHeader, Panel, StatCard } from '@/components/ui';
import { getModelReleases } from '@/lib/landintel-api';

export const dynamic = 'force-dynamic';

function toneForStatus(value: string): 'neutral' | 'accent' | 'success' | 'warning' | 'danger' {
  if (value === 'ACTIVE') {
    return 'success';
  }

  if (value === 'VALIDATED') {
    return 'accent';
  }

  if (value === 'NOT_READY') {
    return 'warning';
  }

  if (value === 'RETIRED') {
    return 'neutral';
  }

  return 'danger';
}

export default async function AdminModelReleasesPage() {
  const result = await getModelReleases();
  const items = result.items;
  const activeCount = items.filter((item) => item.status === 'ACTIVE').length;
  const notReadyCount = items.filter((item) => item.status === 'NOT_READY').length;

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Admin / model releases"
        title="Hidden release registry"
        summary="Phase 7A keeps release selection explicit and immutable. Hidden scoring, valuation integration, and ranking still resolve only through the registry and active scope records."
        actions={
          <div className="page-actions__group">
            <Link className="button button--ghost" href="/admin/health">
              Admin health
            </Link>
            <Link className="button button--ghost" href="/assessments">
              Assessments
            </Link>
          </div>
        }
      />

      <section className="stat-grid">
        <StatCard tone="accent" label="Releases" value={String(items.length)} detail="Immutable hidden release records" />
        <StatCard tone="success" label="Active" value={String(activeCount)} detail="Currently resolved hidden scopes" />
        <StatCard tone="warning" label="Not ready" value={String(notReadyCount)} detail="Honest insufficient-data states remain visible" />
        <StatCard tone="danger" label="Visibility" value="Hidden only" detail="No standard-analyst visible probability rollout in Phase 7A" />
      </section>

      <Panel
        eyebrow="Registry"
        title="Template release status"
        note={result.apiAvailable ? 'Live API' : 'API unavailable'}
      >
        {items.length === 0 ? (
          <p className="empty-note">No model releases are registered yet.</p>
        ) : (
          <div className="card-stack">
            {items.map((item) => (
              <article className="mini-card" key={item.id}>
                <div className="mini-card__top">
                  <div>
                    <div className="table-primary">{item.template_key}</div>
                    <div className="table-secondary">{item.scope_key}</div>
                  </div>
                  <Badge tone={toneForStatus(item.status)}>{item.status}</Badge>
                </div>
                <DefinitionList
                  items={[
                    { label: 'Support', value: `${item.support_count} total / ${item.positive_count} positive / ${item.negative_count} negative` },
                    { label: 'Transform', value: item.transform_version },
                    { label: 'Feature version', value: item.feature_version },
                    { label: 'Calibration', value: item.calibration_method },
                    { label: 'Activated at', value: item.activated_at ?? 'Not active' },
                    { label: 'Reason', value: item.reason_text ?? 'Validated hidden release' }
                  ]}
                />
              </article>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}
