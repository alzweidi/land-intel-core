'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';

import {
  activateModelRelease,
  manageReleaseScopeIncident,
  retireModelRelease,
  setReleaseScopeVisibility,
  type ActiveReleaseScope,
  type ModelReleaseSummary,
  type VisibilityMode,
} from '@/lib/landintel-api';

import { Badge, Panel } from './ui';

type ReleaseScopeControlsProps = {
  release: ModelReleaseSummary;
  activeScopes: ActiveReleaseScope[];
};

function modeTone(mode: VisibilityMode): 'neutral' | 'accent' | 'success' | 'warning' | 'danger' {
  if (mode === 'VISIBLE_REVIEWER_ONLY') {
    return 'success';
  }
  if (mode === 'HIDDEN_ONLY') {
    return 'accent';
  }
  return 'danger';
}

export function ReleaseScopeControls({ release, activeScopes }: ReleaseScopeControlsProps) {
  const router = useRouter();
  const [message, setMessage] = useState('Release activation and visibility changes are audited. Visible reviewer mode stays off unless explicitly enabled.');
  const [loadingKey, setLoadingKey] = useState<string | null>(null);
  const [reasonByScope, setReasonByScope] = useState<Record<string, string>>({});

  function reasonFor(scopeKey: string): string {
    return reasonByScope[scopeKey] ?? 'Admin control change recorded for the release scope.';
  }

  function setReason(scopeKey: string, value: string) {
    setReasonByScope((current) => ({ ...current, [scopeKey]: value }));
  }

  async function handleActivate() {
    setLoadingKey(`activate:${release.id}`);
    const response = await activateModelRelease(release.id, {
      requested_by: 'web-ui',
      actor_role: 'admin',
    });
    setLoadingKey(null);
    if (!response.item) {
      setMessage('Release activation failed.');
      return;
    }
    setMessage(`Release ${release.template_key} activated.`);
    router.refresh();
  }

  async function handleRetire() {
    setLoadingKey(`retire:${release.id}`);
    const response = await retireModelRelease(release.id, {
      requested_by: 'web-ui',
      actor_role: 'admin',
    });
    setLoadingKey(null);
    if (!response.item) {
      setMessage('Release retirement failed.');
      return;
    }
    setMessage(`Release ${release.template_key} retired.`);
    router.refresh();
  }

  async function handleVisibility(scopeKey: string, visibilityMode: VisibilityMode) {
    setLoadingKey(`visibility:${scopeKey}:${visibilityMode}`);
    const response = await setReleaseScopeVisibility(scopeKey, {
      requested_by: 'web-ui',
      actor_role: 'admin',
      visibility_mode: visibilityMode,
      reason: reasonFor(scopeKey),
    });
    setLoadingKey(null);
    if (!response.apiAvailable) {
      setMessage('Scope visibility update failed.');
      return;
    }
    setMessage(`Scope ${scopeKey} visibility set to ${visibilityMode}.`);
    router.refresh();
  }

  async function handleIncident(scopeKey: string, action: 'OPEN' | 'RESOLVE' | 'ROLLBACK') {
    setLoadingKey(`incident:${scopeKey}:${action}`);
    const response = await manageReleaseScopeIncident(scopeKey, {
      requested_by: 'web-ui',
      actor_role: 'admin',
      action,
      reason: reasonFor(scopeKey),
    });
    setLoadingKey(null);
    if (!response.item) {
      setMessage('Incident action failed.');
      return;
    }
    setMessage(`Scope ${scopeKey} incident action ${action} recorded.`);
    router.refresh();
  }

  return (
    <Panel
      eyebrow="Controls"
      title="Activation and visibility"
      note={<Badge tone={release.status === 'ACTIVE' ? 'success' : release.status === 'NOT_READY' ? 'warning' : 'accent'}>{release.status}</Badge>}
    >
      <div className="button-row" style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        <button
          className="button button--solid"
          disabled={loadingKey === `activate:${release.id}`}
          onClick={() => void handleActivate()}
          type="button"
        >
          {loadingKey === `activate:${release.id}` ? 'Activating...' : 'Activate release'}
        </button>
        <button className="button button--ghost" disabled={loadingKey === `retire:${release.id}`} onClick={() => void handleRetire()} type="button">
          {loadingKey === `retire:${release.id}` ? 'Retiring...' : 'Retire release'}
        </button>
      </div>

      {activeScopes.length === 0 ? (
        <p className="empty-note" style={{ marginTop: 16 }}>
          No active scopes are attached to this release yet.
        </p>
      ) : (
        <div className="card-stack" style={{ marginTop: 16 }}>
          {activeScopes.map((scope) => (
            <article className="mini-card" key={scope.id}>
              <div className="mini-card__top">
                <div>
                  <div className="table-primary">{scope.scope_key}</div>
                  <div className="table-secondary">
                    {scope.template_key} · {scope.borough_id ?? 'London-wide'}
                  </div>
                </div>
                <Badge tone={modeTone(scope.visibility_mode)}>{scope.visibility_mode}</Badge>
              </div>
              <div className="table-secondary">
                {scope.active_incident_reason ?? scope.visibility_reason ?? 'No active visibility or incident note.'}
              </div>
              <label className="field" style={{ marginTop: 12 }}>
                <span className="field__label">Reason / incident note</span>
                <textarea
                  onChange={(event) => setReason(scope.scope_key, event.target.value)}
                  rows={2}
                  value={reasonFor(scope.scope_key)}
                />
              </label>
              <div className="button-row" style={{ display: 'flex', gap: 12, marginTop: 12, flexWrap: 'wrap' }}>
                <button
                  className="button button--ghost"
                  disabled={loadingKey === `visibility:${scope.scope_key}:HIDDEN_ONLY`}
                  onClick={() => void handleVisibility(scope.scope_key, 'HIDDEN_ONLY')}
                  type="button"
                >
                  Hidden only
                </button>
                <button
                  className="button button--solid"
                  disabled={loadingKey === `visibility:${scope.scope_key}:VISIBLE_REVIEWER_ONLY`}
                  onClick={() => void handleVisibility(scope.scope_key, 'VISIBLE_REVIEWER_ONLY')}
                  type="button"
                >
                  Reviewer visible
                </button>
                <button
                  className="button button--ghost"
                  disabled={loadingKey === `visibility:${scope.scope_key}:DISABLED`}
                  onClick={() => void handleVisibility(scope.scope_key, 'DISABLED')}
                  type="button"
                >
                  Disable visibility
                </button>
                <button
                  className="button button--ghost"
                  disabled={loadingKey === `incident:${scope.scope_key}:OPEN`}
                  onClick={() => void handleIncident(scope.scope_key, 'OPEN')}
                  type="button"
                >
                  Open incident
                </button>
                <button
                  className="button button--ghost"
                  disabled={loadingKey === `incident:${scope.scope_key}:RESOLVE`}
                  onClick={() => void handleIncident(scope.scope_key, 'RESOLVE')}
                  type="button"
                >
                  Resolve incident
                </button>
                <button
                  className="button button--ghost"
                  disabled={loadingKey === `incident:${scope.scope_key}:ROLLBACK`}
                  onClick={() => void handleIncident(scope.scope_key, 'ROLLBACK')}
                  type="button"
                >
                  Roll back visibility
                </button>
              </div>
            </article>
          ))}
        </div>
      )}

      <p className="table-secondary" style={{ marginTop: 16 }}>
        {message}
      </p>
    </Panel>
  );
}
