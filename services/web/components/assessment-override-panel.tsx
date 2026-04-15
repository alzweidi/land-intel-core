'use client';

import { useRouter } from 'next/navigation';
import { useMemo, useState } from 'react';

import {
  getAssessmentAuditExport,
  overrideAssessment,
  type AssessmentOverride,
  type AuditExport,
  type VisibilityGate,
} from '@/lib/landintel-api';

import { Badge, DefinitionList, Panel } from './ui';

type AssessmentOverridePanelProps = {
  assessmentId: string;
  activeOverrides: AssessmentOverride[];
  visibility: VisibilityGate | null;
  currentAssumptionVersion: string | null;
  currentBasisType: string | null;
  manualReviewRequired: boolean;
};

const PRICE_BASIS_TYPES = ['GUIDE_PRICE', 'ASKING_PRICE', 'FIXED_PRICE', 'UNKNOWN'] as const;

function overrideTone(type: string): 'neutral' | 'accent' | 'success' | 'warning' | 'danger' {
  if (type === 'REVIEW_DISPOSITION') {
    return 'success';
  }
  if (type === 'RANKING_SUPPRESSION') {
    return 'danger';
  }
  if (type === 'VALUATION_ASSUMPTION_SET') {
    return 'accent';
  }
  return 'warning';
}

export function AssessmentOverridePanel({
  assessmentId,
  activeOverrides,
  visibility,
  currentAssumptionVersion,
  currentBasisType,
  manualReviewRequired,
}: AssessmentOverridePanelProps) {
  const router = useRouter();
  const [basisValue, setBasisValue] = useState('');
  const [basisType, setBasisType] = useState(currentBasisType ?? 'GUIDE_PRICE');
  const [basisReason, setBasisReason] = useState('Correct acquisition basis from analyst evidence.');
  const [assumptionSetId, setAssumptionSetId] = useState('');
  const [assumptionReason, setAssumptionReason] = useState('Switch to a different approved valuation assumption set.');
  const [reviewNote, setReviewNote] = useState('Reviewer sign-off after manual review.');
  const [rankingReason, setRankingReason] = useState('Suppress ranking display pending reviewer/admin sign-off.');
  const [loadingKey, setLoadingKey] = useState<string | null>(null);
  const [message, setMessage] = useState('Overrides are append-only. Original scored and valuation outputs remain preserved.');
  const [exportRecord, setExportRecord] = useState<AuditExport | null>(null);

  const activeOverrideCount = activeOverrides.length;
  const visibilitySummary = useMemo(() => {
    if (!visibility) {
      return 'No visibility gate data returned.';
    }
    if (visibility.blocked) {
      return visibility.blocked_reason_text ?? 'Visible publication is blocked.';
    }
    if (visibility.visible_probability_allowed) {
      return 'Reviewer-visible mode is active for this request context.';
    }
    if (visibility.hidden_probability_allowed) {
      return 'Hidden internal probability is available in this request context.';
    }
    return 'Standard analyst reads remain redacted/non-speaking.';
  }, [visibility]);

  async function applyBasisOverride() {
    const parsed = Number(basisValue);
    if (!Number.isFinite(parsed) || parsed <= 0) {
      setMessage('Enter a positive acquisition basis before applying the override.');
      return;
    }

    setLoadingKey('basis');
    const response = await overrideAssessment(assessmentId, {
      actor_role: 'analyst',
      override_type: 'ACQUISITION_BASIS',
      reason: basisReason,
      acquisition_basis_gbp: parsed,
      acquisition_basis_type: basisType,
      requested_by: 'web-ui',
    });
    setLoadingKey(null);

    if (!response.item) {
      setMessage('Acquisition-basis override failed.');
      return;
    }

    setMessage('Acquisition basis override saved. Original valuation remains preserved alongside the override.');
    router.refresh();
  }

  async function applyAssumptionOverride() {
    if (!assumptionSetId.trim()) {
      setMessage('Enter a valuation assumption set UUID before applying the override.');
      return;
    }

    setLoadingKey('assumption');
    const response = await overrideAssessment(assessmentId, {
      actor_role: 'analyst',
      override_type: 'VALUATION_ASSUMPTION_SET',
      reason: assumptionReason,
      valuation_assumption_set_id: assumptionSetId.trim(),
      requested_by: 'web-ui',
    });
    setLoadingKey(null);

    if (!response.item) {
      setMessage('Valuation assumption override failed. Check that the assumption set exists.');
      return;
    }

    setMessage('Valuation assumption override saved as a new immutable valuation run.');
    router.refresh();
  }

  async function resolveReviewDisposition() {
    setLoadingKey('review');
    const response = await overrideAssessment(assessmentId, {
      actor_role: 'reviewer',
      override_type: 'REVIEW_DISPOSITION',
      reason: reviewNote,
      review_resolution_note: reviewNote,
      resolve_manual_review: true,
      requested_by: 'web-ui',
    });
    setLoadingKey(null);

    if (!response.item) {
      setMessage('Review disposition override failed.');
      return;
    }

    setMessage('Review disposition override saved.');
    router.refresh();
  }

  async function suppressRanking() {
    setLoadingKey('ranking');
    const response = await overrideAssessment(assessmentId, {
      actor_role: 'admin',
      override_type: 'RANKING_SUPPRESSION',
      reason: rankingReason,
      ranking_suppressed: true,
      display_block_reason: rankingReason,
      requested_by: 'web-ui',
    });
    setLoadingKey(null);

    if (!response.item) {
      setMessage('Ranking suppression override failed.');
      return;
    }

    setMessage('Ranking suppression override saved. Original planning/valuation outputs remain unchanged.');
    router.refresh();
  }

  async function buildAuditExport() {
    setLoadingKey('export');
    const response = await getAssessmentAuditExport(assessmentId, {
      actor_role: 'reviewer',
      requested_by: 'web-ui',
    });
    setLoadingKey(null);

    if (!response.item) {
      setMessage('Audit export failed.');
      return;
    }

    setExportRecord(response.item);
    setMessage('Audit export manifest built.');
  }

  return (
    <Panel
      eyebrow="Phase 8A"
      title="Overrides and audit controls"
      note={<Badge tone={visibility?.blocked ? 'danger' : 'accent'}>{visibility?.visibility_mode ?? 'HIDDEN_ONLY'}</Badge>}
    >
      <DefinitionList
        items={[
          { label: 'Visibility gate', value: visibilitySummary },
          { label: 'Active overrides', value: String(activeOverrideCount) },
          { label: 'Current assumption version', value: currentAssumptionVersion ?? 'Unavailable' },
          { label: 'Manual review required', value: manualReviewRequired ? 'Yes' : 'No' },
        ]}
      />

      {activeOverrides.length > 0 ? (
        <div className="card-stack" style={{ marginTop: 16 }}>
          {activeOverrides.map((item) => (
            <article className="mini-card" key={item.id}>
              <div className="mini-card__top">
                <div>
                  <div className="table-primary">{item.override_type}</div>
                  <div className="table-secondary">
                    {item.actor_role} · {item.actor_name} · {item.created_at}
                  </div>
                </div>
                <Badge tone={overrideTone(item.override_type)}>{item.status}</Badge>
              </div>
              <div className="table-secondary">{item.reason}</div>
            </article>
          ))}
        </div>
      ) : null}

      <div className="split-grid" style={{ marginTop: 20 }}>
        <Panel eyebrow="Analyst" title="Valuation basis correction">
          <div className="form-stack" style={{ display: 'grid', gap: 12 }}>
            <label className="field">
              <span className="field__label">Acquisition basis GBP</span>
              <input
                min={0}
                onChange={(event) => setBasisValue(event.target.value)}
                placeholder="1250000"
                type="number"
                value={basisValue}
              />
            </label>
            <label className="field">
              <span className="field__label">Basis type</span>
              <select onChange={(event) => setBasisType(event.target.value)} value={basisType}>
                {PRICE_BASIS_TYPES.map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span className="field__label">Reason</span>
              <textarea
                onChange={(event) => setBasisReason(event.target.value)}
                rows={3}
                value={basisReason}
              />
            </label>
          </div>
          <div className="button-row" style={{ display: 'flex', gap: 12, marginTop: 16, flexWrap: 'wrap' }}>
            <button className="button" disabled={loadingKey === 'basis'} onClick={() => void applyBasisOverride()} type="button">
              {loadingKey === 'basis' ? 'Saving...' : 'Apply basis override'}
            </button>
          </div>
        </Panel>

        <Panel eyebrow="Analyst" title="Assumption set override">
          <div className="form-stack" style={{ display: 'grid', gap: 12 }}>
            <label className="field">
              <span className="field__label">Assumption set UUID</span>
              <input
                onChange={(event) => setAssumptionSetId(event.target.value)}
                placeholder="UUID"
                type="text"
                value={assumptionSetId}
              />
            </label>
            <label className="field">
              <span className="field__label">Reason</span>
              <textarea
                onChange={(event) => setAssumptionReason(event.target.value)}
                rows={3}
                value={assumptionReason}
              />
            </label>
          </div>
          <div className="button-row" style={{ display: 'flex', gap: 12, marginTop: 16, flexWrap: 'wrap' }}>
            <button
              className="button"
              disabled={loadingKey === 'assumption'}
              onClick={() => void applyAssumptionOverride()}
              type="button"
            >
              {loadingKey === 'assumption' ? 'Saving...' : 'Apply assumption override'}
            </button>
          </div>
        </Panel>
      </div>

      <div className="split-grid" style={{ marginTop: 20 }}>
        <Panel eyebrow="Reviewer" title="Review disposition">
          <label className="field">
            <span className="field__label">Resolution note</span>
            <textarea
              onChange={(event) => setReviewNote(event.target.value)}
              rows={3}
              value={reviewNote}
            />
          </label>
          <div className="button-row" style={{ display: 'flex', gap: 12, marginTop: 16, flexWrap: 'wrap' }}>
            <button className="button" disabled={loadingKey === 'review'} onClick={() => void resolveReviewDisposition()} type="button">
              {loadingKey === 'review' ? 'Saving...' : 'Resolve review requirement'}
            </button>
          </div>
        </Panel>

        <Panel eyebrow="Admin" title="Safety suppression and export">
          <label className="field">
            <span className="field__label">Suppression reason</span>
            <textarea
              onChange={(event) => setRankingReason(event.target.value)}
              rows={3}
              value={rankingReason}
            />
          </label>
          <div className="button-row" style={{ display: 'flex', gap: 12, marginTop: 16, flexWrap: 'wrap' }}>
            <button className="button button--ghost" disabled={loadingKey === 'ranking'} onClick={() => void suppressRanking()} type="button">
              {loadingKey === 'ranking' ? 'Saving...' : 'Suppress ranking display'}
            </button>
            <button className="button" disabled={loadingKey === 'export'} onClick={() => void buildAuditExport()} type="button">
              {loadingKey === 'export' ? 'Building...' : 'Build audit export'}
            </button>
          </div>
          {exportRecord ? (
            <div className="card-stack" style={{ marginTop: 16 }}>
              <article className="mini-card">
                <div className="table-primary">Audit export</div>
                <div className="table-secondary">Manifest hash {exportRecord.manifest_hash ?? 'Unavailable'}</div>
                <div className="table-secondary">{exportRecord.manifest_path ?? 'No manifest path stored'}</div>
              </article>
            </div>
          ) : null}
        </Panel>
      </div>

      <p className="table-secondary" style={{ marginTop: 16 }}>
        {message}
      </p>
    </Panel>
  );
}
