import Link from 'next/link';

import { Badge, DefinitionList, PageHeader, Panel, StatCard } from '@/components/ui';
import { ReleaseScopeControls } from '@/components/release-scope-controls';
import { readSessionTokenFromCookies } from '@/lib/auth/server';
import { getModelRelease, getModelReleases } from '@/lib/landintel-api';

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
  const sessionToken = await readSessionTokenFromCookies();
  const result = await getModelReleases({ sessionToken: sessionToken ?? undefined });
  const items = result.items;
  const details = await Promise.all(
    items.map(async (item) => {
      const detail = await getModelRelease(item.id, { sessionToken: sessionToken ?? undefined });
      return detail.item;
    })
  );

  const activeCount = items.filter((item) => item.status === 'ACTIVE').length;
  const notReadyCount = items.filter((item) => item.status === 'NOT_READY').length;
  const visibleCount = details.flatMap((item) => item?.active_scopes ?? []).filter((scope) => scope.visibility_mode === 'VISIBLE_REVIEWER_ONLY').length;

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Admin / model releases"
        title="Release registry and visibility"
        summary="Inspect hidden releases, scope-level visibility gating, incident controls, and rollback posture. Hidden-only remains the safe default."
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
        <StatCard tone="accent" label="Releases" value={String(items.length)} detail="Immutable model release records" />
        <StatCard tone="success" label="Active" value={String(activeCount)} detail="Active hidden release scopes" />
        <StatCard tone="warning" label="Not ready" value={String(notReadyCount)} detail="Honest insufficient-data states remain visible" />
        <StatCard tone="danger" label="Reviewer visible" value={String(visibleCount)} detail="Visible probability stays off unless an admin explicitly enables a signed-off scope" />
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
            {items.map((item, index) => {
              const detail = details[index];
              const activeScopes = detail?.active_scopes ?? [];
              return (
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
                      { label: 'Active scope count', value: item.active_scope_count },
                      { label: 'Visibility modes', value: item.active_scope_visibility_modes.length > 0 ? item.active_scope_visibility_modes.join(', ') : 'None active' },
                      { label: 'Activated at', value: item.activated_at ?? 'Not active' },
                      { label: 'Reason', value: item.reason_text ?? 'Validated hidden release' }
                    ]}
                  />
                  {detail ? (
                    <ReleaseScopeControls
                      activeScopes={activeScopes}
                      release={item}
                    />
                  ) : null}
                </article>
              );
            })}
          </div>
        )}
      </Panel>
    </div>
  );
}
