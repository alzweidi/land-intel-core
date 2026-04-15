import Link from 'next/link';

import { Badge, DefinitionList, PageHeader, Panel, StatCard } from '@/components/ui';
import { getDataHealth, getModelHealth } from '@/lib/landintel-api';

export const dynamic = 'force-dynamic';

function percent(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return 'Unavailable';
  }
  return `${Math.round(value * 100)}%`;
}

function toneForStatus(value: string): 'neutral' | 'accent' | 'success' | 'warning' | 'danger' {
  if (value === 'ok') {
    return 'success';
  }
  if (value === 'warning') {
    return 'warning';
  }
  if (value === 'error') {
    return 'danger';
  }
  return 'accent';
}

export default async function AdminHealthPage() {
  const dataHealth = await getDataHealth();
  const modelHealth = await getModelHealth();
  const data = dataHealth.item;
  const model = modelHealth.item;

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Admin / health"
        title="Operational health"
        summary="Phase 8A turns the admin shell into a usable internal control panel: data freshness, model calibration, economic-health summary, and scope visibility state are now surfaced together."
        actions={
          <div className="page-actions__group">
            <Link className="button button--solid" href="/review-queue">
              Review queue
            </Link>
            <Link className="button button--ghost" href="/admin/model-releases">
              Model releases
            </Link>
          </div>
        }
      />

      <section className="stat-grid">
        <StatCard
          tone={toneForStatus(data?.status ?? 'warning')}
          label="Data health"
          value={data?.status ?? 'Unavailable'}
          detail={`Connector failures ${percent(data?.connector_failure_rate)}`}
        />
        <StatCard
          tone={toneForStatus(model?.status ?? 'warning')}
          label="Model health"
          value={model?.status ?? 'Unavailable'}
          detail={`OOD rate ${percent(model?.ood_rate)}`}
        />
        <StatCard
          tone="accent"
          label="Economic health"
          value={percent((model?.economic_health.uplift_null_rate as number | null | undefined) ?? null)}
          detail="Uplift null rate across valuation runs"
        />
        <StatCard
          tone="danger"
          label="Visibility"
          value={
            Array.isArray(model?.active_scopes)
              ? String(model.active_scopes.filter((item) => item.visibility_mode === 'VISIBLE_REVIEWER_ONLY').length)
              : '0'
          }
          detail="Reviewer-visible scopes. Hidden-only remains the default."
        />
      </section>

      <div className="split-grid">
        <Panel eyebrow="Data" title="Coverage and freshness" note={<Badge tone={toneForStatus(data?.status ?? 'warning')}>{data?.status ?? 'unknown'}</Badge>}>
          <DefinitionList
            items={[
              { label: 'Connector failure rate', value: percent(data?.connector_failure_rate) },
              { label: 'Listing parse success', value: percent(data?.listing_parse_success_rate) },
              { label: 'Extant unresolved', value: percent(data?.extant_permission_unresolved_rate) },
              {
                label: 'Baseline coverage',
                value: data?.borough_baseline_coverage
                  ? `${String(data.borough_baseline_coverage.signed_off ?? 0)} signed off / ${String(data.borough_baseline_coverage.total ?? 0)} total`
                  : 'Unavailable'
              }
            ]}
          />
          <div className="card-stack" style={{ marginTop: 16 }}>
            {data?.coverage.slice(0, 8).map((item, index) => (
              <article className="mini-card" key={`coverage-${index}`}>
                <div className="mini-card__top">
                  <div>
                    <div className="table-primary">
                      {String(item.borough_id ?? 'unknown')} · {String(item.source_family ?? 'unknown')}
                    </div>
                    <div className="table-secondary">
                      {String(item.coverage_status ?? 'UNKNOWN')} · {String(item.freshness_status ?? 'UNKNOWN')}
                    </div>
                  </div>
                  <Badge tone={item.coverage_status === 'COMPLETE' ? 'success' : 'warning'}>
                    {String(item.coverage_status ?? 'UNKNOWN')}
                  </Badge>
                </div>
                <div className="table-secondary">{String(item.gap_reason ?? item.coverage_note ?? 'No gap note')}</div>
              </article>
            )) ?? <p className="empty-note">No live coverage rows were returned.</p>}
          </div>
        </Panel>

        <Panel eyebrow="Model" title="Calibration and review health" note={<Badge tone={toneForStatus(model?.status ?? 'warning')}>{model?.status ?? 'unknown'}</Badge>}>
          <DefinitionList
            items={[
              { label: 'Brier score', value: model?.brier_score ?? 'Unavailable' },
              { label: 'Log loss', value: model?.log_loss ?? 'Unavailable' },
              { label: 'False-positive reviewer rate', value: percent(model?.false_positive_reviewer_rate) },
              { label: 'Abstain rate', value: percent(model?.abstain_rate) },
            ]}
          />
          <div className="card-stack" style={{ marginTop: 16 }}>
            {model?.template_level_performance.map((item, index) => (
              <article className="mini-card" key={`template-${index}`}>
                <div className="mini-card__top">
                  <div>
                    <div className="table-primary">{String(item.template_key ?? 'unknown')}</div>
                    <div className="table-secondary">
                      Count {String(item.count ?? 0)} · OOD {percent(item.ood_rate as number | null | undefined)}
                    </div>
                  </div>
                  <Badge tone="accent">Template</Badge>
                </div>
                <div className="table-secondary">
                  Brier {String(item.brier_score ?? 'Unavailable')} · Log loss {String(item.log_loss ?? 'Unavailable')}
                </div>
              </article>
            )) ?? <p className="empty-note">No model performance rows were returned.</p>}
          </div>
        </Panel>
      </div>

      <div className="split-grid">
        <Panel eyebrow="Economic" title="Valuation summary">
          <DefinitionList
            items={[
              {
                label: 'Uplift null rate',
                value: percent((model?.economic_health.uplift_null_rate as number | null | undefined) ?? null),
              },
              {
                label: 'Asking-price missing rate',
                value: percent((model?.economic_health.asking_price_missing_rate as number | null | undefined) ?? null),
              },
              {
                label: 'Quality distribution',
                value: JSON.stringify(model?.economic_health.valuation_quality_distribution ?? {}),
              },
              {
                label: 'Realized backtests',
                value: String(model?.economic_health.realized_backtests ?? 'Deferred'),
              },
            ]}
          />
        </Panel>

        <Panel eyebrow="Scopes" title="Visibility state and incidents">
          <div className="card-stack">
            {model?.active_scopes.map((item, index) => (
              <article className="mini-card" key={`scope-${index}`}>
                <div className="mini-card__top">
                  <div>
                    <div className="table-primary">{String(item.scope_key ?? 'unknown')}</div>
                    <div className="table-secondary">
                      {String(item.template_key ?? 'unknown')} · {String(item.model_release_id ?? 'unknown release')}
                    </div>
                  </div>
                  <Badge tone={toneForStatus(item.visibility_mode === 'DISABLED' ? 'error' : 'ok')}>
                    {String(item.visibility_mode ?? 'HIDDEN_ONLY')}
                  </Badge>
                </div>
                <div className="table-secondary">
                  {String(item.visibility_reason ?? 'No visibility note')}
                </div>
              </article>
            )) ?? <p className="empty-note">No active scopes are registered.</p>}
          </div>
        </Panel>
      </div>
    </div>
  );
}
