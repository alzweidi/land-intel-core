'use client';

import { useMemo, useState } from 'react';

import {
  reviewGoldSetCase,
  type GeometryConfidence,
  type HistoricalLabelCase
} from '@/lib/landintel-api';

import { Badge, DefinitionList, Panel } from './ui';

type GoldSetReviewPanelProps = {
  initialCase: HistoricalLabelCase | null;
};

const REVIEW_STATUSES = ['PENDING', 'CONFIRMED', 'EXCLUDED'] as const;
const GEOMETRY_CONFIDENCES: Array<GeometryConfidence | ''> = ['', 'HIGH', 'MEDIUM', 'LOW', 'INSUFFICIENT'];

function statusTone(status: string): 'neutral' | 'accent' | 'success' | 'warning' | 'danger' {
  if (status === 'CONFIRMED') {
    return 'success';
  }

  if (status === 'EXCLUDED') {
    return 'danger';
  }

  return 'warning';
}

export function GoldSetReviewPanel({ initialCase }: GoldSetReviewPanelProps) {
  const [selectedCase, setSelectedCase] = useState(initialCase);
  const [reviewStatus, setReviewStatus] = useState(initialCase?.review_status ?? 'PENDING');
  const [reviewNotes, setReviewNotes] = useState(initialCase?.review_notes ?? '');
  const [notablePolicyIssues, setNotablePolicyIssues] = useState(
    initialCase?.notable_policy_issues_json.join(', ') ?? ''
  );
  const [extantOutcome, setExtantOutcome] = useState(initialCase?.extant_permission_outcome ?? '');
  const [geometryConfidence, setGeometryConfidence] = useState<GeometryConfidence | ''>(
    initialCase?.site_geometry_confidence ?? ''
  );
  const [message, setMessage] = useState(
    initialCase ? 'Review and confirm the historical label inputs here.' : 'Select a historical case to review.'
  );
  const [loading, setLoading] = useState(false);

  const documentLinks = useMemo(
    () => selectedCase?.planning_application.documents ?? [],
    [selectedCase]
  );
  const provenanceSourceFamily =
    typeof selectedCase?.provenance_json.source_family === 'string'
      ? selectedCase.provenance_json.source_family
      : 'Unknown source';

  async function handleSubmit() {
    if (!selectedCase) {
      setMessage('Select a historical case before submitting a review.');
      return;
    }

    setLoading(true);
    const response = await reviewGoldSetCase(selectedCase.id, {
      review_status: reviewStatus,
      review_notes: reviewNotes,
      notable_policy_issues: notablePolicyIssues
        .split(',')
        .map((value) => value.trim())
        .filter(Boolean),
      extant_permission_outcome: extantOutcome || undefined,
      site_geometry_confidence: geometryConfidence || undefined,
      reviewed_by: 'web-ui'
    });

    if (!response.item) {
      setMessage('Review submission failed.');
      setLoading(false);
      return;
    }

    setSelectedCase(response.item);
    setReviewStatus(response.item.review_status);
    setReviewNotes(response.item.review_notes ?? '');
    setNotablePolicyIssues(response.item.notable_policy_issues_json.join(', '));
    setExtantOutcome(response.item.extant_permission_outcome ?? '');
    setGeometryConfidence(response.item.site_geometry_confidence ?? '');
    setMessage(`Case ${response.item.planning_application.external_ref} reviewed.`);
    setLoading(false);
  }

  if (!selectedCase) {
    return (
      <Panel eyebrow="Gold-set review" title="Case detail unavailable">
        <p className="empty-note">No historical case is selected.</p>
      </Panel>
    );
  }

  return (
    <Panel
      eyebrow="Gold-set review"
      title={selectedCase.planning_application.external_ref}
      note={<Badge tone={statusTone(reviewStatus)}>{reviewStatus}</Badge>}
    >
      <DefinitionList
        items={[
          { label: 'Label class', value: selectedCase.label_class },
          { label: 'Label decision', value: selectedCase.label_decision },
          { label: 'Template', value: selectedCase.template_key ?? 'Unmapped' },
          { label: 'Units', value: selectedCase.units_proposed ?? 'Unknown' },
          { label: 'Source priority', value: selectedCase.source_priority_used },
          { label: 'Source snapshots', value: selectedCase.source_snapshot_ids_json.length },
          { label: 'Raw assets', value: selectedCase.raw_asset_ids_json.length }
        ]}
      />

      <div className="card-stack" style={{ marginTop: 16 }}>
        <article className="mini-card">
          <div className="table-primary">Proposal</div>
          <div className="table-secondary">{selectedCase.planning_application.proposal_description}</div>
        </article>
        <article className="mini-card">
          <div className="table-primary">Provenance</div>
          <div className="table-secondary">
            {provenanceSourceFamily} · {selectedCase.planning_application.source_system}
          </div>
        </article>
      </div>

      <div className="form-stack" style={{ display: 'grid', gap: 12, marginTop: 16 }}>
        <label className="field">
          <span className="field__label">Review status</span>
          <select onChange={(event) => setReviewStatus(event.target.value)} value={reviewStatus}>
            {REVIEW_STATUSES.map((status) => (
              <option key={status} value={status}>
                {status}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span className="field__label">Review notes</span>
          <textarea
            onChange={(event) => setReviewNotes(event.target.value)}
            rows={4}
            value={reviewNotes}
          />
        </label>
        <label className="field">
          <span className="field__label">Notable policy issues</span>
          <input
            onChange={(event) => setNotablePolicyIssues(event.target.value)}
            placeholder="Comma-separated notes"
            type="text"
            value={notablePolicyIssues}
          />
        </label>
        <label className="field">
          <span className="field__label">Extant-permission outcome</span>
          <input
            onChange={(event) => setExtantOutcome(event.target.value)}
            placeholder="Optional reviewer note"
            type="text"
            value={extantOutcome}
          />
        </label>
        <label className="field">
          <span className="field__label">Site geometry confidence</span>
          <select
            onChange={(event) => setGeometryConfidence(event.target.value as GeometryConfidence | '')}
            value={geometryConfidence}
          >
            {GEOMETRY_CONFIDENCES.map((value) => (
              <option key={value || 'blank'} value={value}>
                {value || 'Unset'}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="button-row" style={{ display: 'flex', gap: 12, marginTop: 16, flexWrap: 'wrap' }}>
        <button
          className="button button--solid"
          disabled={loading}
          onClick={() => void handleSubmit()}
          type="button"
        >
          {loading ? 'Saving review...' : 'Save review'}
        </button>
      </div>

      <p className="table-secondary" style={{ marginTop: 12 }}>
        {message}
      </p>

      <div className="card-stack" style={{ marginTop: 20 }}>
        <article className="mini-card">
          <div className="table-primary">Raw source URL</div>
          <div className="table-secondary">
            {selectedCase.planning_application.source_url ? (
              <a href={selectedCase.planning_application.source_url} rel="noreferrer" target="_blank">
                {selectedCase.planning_application.source_url}
              </a>
            ) : (
              'No source URL stored'
            )}
          </div>
        </article>
        {documentLinks.map((document) => (
          <article className="mini-card" key={document.id}>
            <div className="table-primary">{document.doc_type}</div>
            <div className="table-secondary">
              <a href={document.doc_url} rel="noreferrer" target="_blank">
                {document.doc_url}
              </a>
            </div>
          </article>
        ))}
      </div>
    </Panel>
  );
}
