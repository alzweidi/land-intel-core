'use client';

import { useMemo, useState } from 'react';

import {
  confirmScenario,
  getScenario,
  suggestSiteScenarios,
  type ProposalForm,
  type ScenarioDetail,
  type ScenarioSummary,
  type SiteDetail
} from '@/lib/landintel-api';

import { Badge, DefinitionList, Panel } from './ui';

type SiteScenarioEditorProps = {
  site: SiteDetail;
  initialScenarios: ScenarioSummary[];
};

function statusTone(status: string): 'neutral' | 'accent' | 'success' | 'warning' | 'danger' {
  if (status === 'ANALYST_CONFIRMED' || status === 'AUTO_CONFIRMED') {
    return 'success';
  }

  if (status === 'OUT_OF_SCOPE' || status === 'REJECTED') {
    return 'danger';
  }

  if (status === 'ANALYST_REQUIRED') {
    return 'warning';
  }

  return 'accent';
}

function proposalForms(): ProposalForm[] {
  return ['INFILL', 'REDEVELOPMENT', 'BROWNFIELD_REUSE', 'BACKLAND', 'AIRSPACE'];
}

export function SiteScenarioEditor({ site, initialScenarios }: SiteScenarioEditorProps) {
  const [scenarios, setScenarios] = useState(initialScenarios);
  const [selectedId, setSelectedId] = useState(initialScenarios[0]?.id ?? '');
  const [selectedDetail, setSelectedDetail] = useState<ScenarioDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [units, setUnits] = useState(initialScenarios[0]?.units_assumed ?? 0);
  const [route, setRoute] = useState(initialScenarios[0]?.route_assumed ?? 'FULL');
  const [heightBand, setHeightBand] = useState(initialScenarios[0]?.height_band_assumed ?? 'MID_RISE');
  const [proposalForm, setProposalForm] = useState<ProposalForm>(
    initialScenarios[0]?.proposal_form ?? 'REDEVELOPMENT'
  );
  const [netPct, setNetPct] = useState(initialScenarios[0]?.net_developable_area_pct ?? 0.72);
  const [parking, setParking] = useState(initialScenarios[0]?.parking_assumption ?? '');
  const [affordable, setAffordable] = useState(
    initialScenarios[0]?.affordable_housing_assumption ?? ''
  );
  const [access, setAccess] = useState(initialScenarios[0]?.access_assumption ?? '');
  const [reviewNotes, setReviewNotes] = useState('');

  const selectedScenario = useMemo(
    () => scenarios.find((scenario) => scenario.id === selectedId) ?? scenarios[0] ?? null,
    [scenarios, selectedId]
  );

  async function loadScenarioDetail(scenarioId: string) {
    setSelectedId(scenarioId);
    setLoading(true);
    const response = await getScenario(scenarioId);
    if (!response.item) {
      setMessage('Scenario detail is unavailable.');
      setLoading(false);
      return;
    }

    const detail = response.item;
    setSelectedDetail(detail);
    setUnits(detail.units_assumed);
    setRoute(detail.route_assumed);
    setHeightBand(detail.height_band_assumed);
    setProposalForm(detail.proposal_form);
    setNetPct(detail.net_developable_area_pct);
    setParking(detail.parking_assumption ?? '');
    setAffordable(detail.affordable_housing_assumption ?? '');
    setAccess(detail.access_assumption ?? '');
    setLoading(false);
    setMessage('');
  }

  async function handleSuggest() {
    setLoading(true);
    const response = await suggestSiteScenarios(site.site_id, { requested_by: 'web-ui' });
    if (!response.item) {
      setMessage('Scenario suggestion did not return an API payload.');
      setLoading(false);
      return;
    }
    setScenarios(response.item.items);
    const nextId = response.item.headline_scenario_id ?? response.item.items[0]?.id ?? '';
    setSelectedId(nextId);
    if (nextId) {
      await loadScenarioDetail(nextId);
    }
    setMessage(
      response.item.excluded_templates.length > 0
        ? `${response.item.items.length} scenario(s) suggested, ${response.item.excluded_templates.length} template(s) excluded.`
        : `${response.item.items.length} scenario(s) suggested.`
    );
    setLoading(false);
  }

  async function handleConfirm(action: 'CONFIRM' | 'REJECT') {
    if (!selectedScenario) {
      setMessage('Select a scenario before confirming or rejecting.');
      return;
    }

    setLoading(true);
    const response = await confirmScenario(selectedScenario.id, {
      requested_by: 'web-ui',
      action,
      proposal_form: proposalForm,
      units_assumed: action === 'REJECT' ? undefined : units,
      route_assumed: action === 'REJECT' ? undefined : route,
      height_band_assumed: action === 'REJECT' ? undefined : heightBand,
      net_developable_area_pct: action === 'REJECT' ? undefined : netPct,
      parking_assumption: action === 'REJECT' ? undefined : parking,
      affordable_housing_assumption: action === 'REJECT' ? undefined : affordable,
      access_assumption: action === 'REJECT' ? undefined : access,
      review_notes: reviewNotes
    });
    if (!response.item) {
      setMessage(`Scenario ${action.toLowerCase()} request failed.`);
      setLoading(false);
      return;
    }

    const updatedDetail = response.item;
    setSelectedDetail(updatedDetail);
    setSelectedId(updatedDetail.id);
    setScenarios((current) => {
      const next = current.filter((item) => item.id !== updatedDetail.id);
      const supersededId = updatedDetail.supersedes_id;
      return [
        mapDetailToSummary(updatedDetail),
        ...next.map((item) =>
          supersededId && item.id === supersededId
            ? { ...item, is_current: false, is_headline: false }
            : item
        )
      ];
    });
    setMessage(
      action === 'REJECT'
        ? 'Scenario rejected and removed from the current headline set.'
        : 'Scenario confirmed with the edited parameters.'
    );
    setLoading(false);
  }

  return (
    <div className="page-stack">
      <Panel
        eyebrow="Scenario actions"
        title="Generate and compare scenarios"
        note="Scenarios are hypotheses. No scoring, valuation, or probability is shown in this phase."
      >
        <div className="button-row" style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <button
            className="button button--ghost"
            disabled={loading}
            onClick={() => void handleSuggest()}
            type="button"
          >
            {loading ? 'Working...' : 'Refresh suggestions'}
          </button>
          <button
            className="button button--solid"
            disabled={loading || !selectedScenario}
            onClick={() => void handleConfirm('CONFIRM')}
            type="button"
          >
            Confirm scenario
          </button>
          <button
            className="button button--ghost"
            disabled={loading || !selectedScenario}
            onClick={() => void handleConfirm('REJECT')}
            type="button"
          >
            Reject scenario
          </button>
        </div>
        <p className="table-secondary" style={{ marginTop: 12 }}>
          {message || 'Refresh suggestions to seed or update the current scenario set.'}
        </p>
      </Panel>

      <div className="split-grid">
        <Panel eyebrow="Compare" title="Current site scenarios">
          <div className="card-stack">
            {scenarios.length === 0 ? (
              <p className="empty-note">No scenarios are stored for this site yet.</p>
            ) : (
              scenarios.map((scenario) => (
                <article className="mini-card" key={scenario.id}>
                  <div className="mini-card__top">
                    <div>
                      <div className="table-primary">
                        {scenario.template_key} · {scenario.units_assumed} units
                      </div>
                      <div className="table-secondary">
                        {scenario.proposal_form} · {scenario.route_assumed} · {scenario.height_band_assumed}
                      </div>
                    </div>
                    <Badge tone={statusTone(scenario.status)}>{scenario.status}</Badge>
                  </div>
                  <div className="table-secondary">
                    {scenario.is_headline ? 'Headline scenario' : 'Supporting scenario'}
                    {scenario.stale_reason ? ` · ${scenario.stale_reason}` : ''}
                  </div>
                  <div className="button-row" style={{ display: 'flex', gap: 8, marginTop: 12 }}>
                    <button
                      className="button button--ghost"
                      onClick={() => void loadScenarioDetail(scenario.id)}
                      type="button"
                    >
                      Open
                    </button>
                  </div>
                </article>
              ))
            )}
          </div>
        </Panel>

        <Panel eyebrow="Editor" title="Analyst edits">
          {selectedScenario ? (
            <>
              <DefinitionList
                items={[
                  { label: 'Template', value: selectedScenario.template_key },
                  { label: 'Headline', value: selectedScenario.is_headline ? 'Yes' : 'No' },
                  {
                    label: 'Geometry hash',
                    value: selectedScenario.red_line_geom_hash.slice(0, 12)
                  },
                  {
                    label: 'Manual review',
                    value: selectedScenario.manual_review_required ? 'Required' : 'No'
                  }
                ]}
              />
              <div className="form-stack" style={{ display: 'grid', gap: 12, marginTop: 16 }}>
                <label className="field">
                  <span className="field__label">Proposal form</span>
                  <select value={proposalForm} onChange={(event) => setProposalForm(event.target.value as ProposalForm)}>
                    {proposalForms().map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  <span className="field__label">Units assumed</span>
                  <input type="number" min={1} max={999} value={units} onChange={(event) => setUnits(Number(event.target.value))} />
                </label>
                <label className="field">
                  <span className="field__label">Route assumed</span>
                  <input value={route} onChange={(event) => setRoute(event.target.value)} />
                </label>
                <label className="field">
                  <span className="field__label">Height band</span>
                  <input value={heightBand} onChange={(event) => setHeightBand(event.target.value)} />
                </label>
                <label className="field">
                  <span className="field__label">Net developable area %</span>
                  <input
                    type="number"
                    min={0}
                    max={1}
                    step={0.01}
                    value={netPct}
                    onChange={(event) => setNetPct(Number(event.target.value))}
                  />
                </label>
                <label className="field">
                  <span className="field__label">Parking assumption</span>
                  <textarea rows={3} value={parking} onChange={(event) => setParking(event.target.value)} />
                </label>
                <label className="field">
                  <span className="field__label">Affordable housing assumption</span>
                  <textarea rows={3} value={affordable} onChange={(event) => setAffordable(event.target.value)} />
                </label>
                <label className="field">
                  <span className="field__label">Access assumption</span>
                  <textarea rows={3} value={access} onChange={(event) => setAccess(event.target.value)} />
                </label>
                <label className="field">
                  <span className="field__label">Review notes</span>
                  <textarea rows={4} value={reviewNotes} onChange={(event) => setReviewNotes(event.target.value)} />
                </label>
              </div>
            </>
          ) : (
            <p className="empty-note">Select or generate a scenario to edit its parameters.</p>
          )}
        </Panel>
      </div>

      {selectedDetail ? (
        <div className="split-grid">
          <Panel eyebrow="Rationale" title="Reason codes and warnings">
            <div className="card-stack">
              {selectedDetail.reason_codes.map((reason) => (
                <article className="mini-card" key={`${reason.code}-${reason.message}`}>
                  <div className="mini-card__top">
                    <div>
                      <div className="table-primary">{reason.code}</div>
                      <div className="table-secondary">{reason.message}</div>
                    </div>
                    <Badge tone="accent">Reason</Badge>
                  </div>
                  {reason.source_url ? (
                    <a className="inline-link" href={reason.source_url} rel="noreferrer" target="_blank">
                      Open source
                    </a>
                  ) : null}
                </article>
              ))}
              {selectedDetail.warning_codes.map((warning) => (
                <article className="mini-card" key={warning}>
                  <div className="mini-card__top">
                    <div className="table-primary">{warning}</div>
                    <Badge tone="warning">Warning</Badge>
                  </div>
                </article>
              ))}
            </div>
          </Panel>

          <Panel eyebrow="Evidence" title="Scenario-conditioned evidence">
            <div className="card-stack">
              {['for', 'against', 'unknown'].map((bucket) => (
                <article className="mini-card" key={bucket}>
                  <div className="mini-card__top">
                    <div className="table-primary">{bucket.toUpperCase()}</div>
                    <Badge tone={bucket === 'for' ? 'success' : bucket === 'against' ? 'danger' : 'warning'}>
                      {selectedDetail.evidence?.[bucket as keyof NonNullable<ScenarioDetail['evidence']>]?.length ?? 0}
                    </Badge>
                  </div>
                  <div className="mini-list" style={{ marginTop: 12 }}>
                    {(selectedDetail.evidence?.[bucket as keyof NonNullable<ScenarioDetail['evidence']>] ?? []).map((item) => (
                      <div className="mini-list__row" key={`${bucket}-${item.claim_text}-${item.source_label}`}>
                        <div>
                          <div className="table-primary">{item.claim_text}</div>
                          <div className="table-secondary">
                            {item.topic} · {item.importance} · {item.source_label}
                          </div>
                          {item.source_url ? (
                            <a className="inline-link" href={item.source_url} rel="noreferrer" target="_blank">
                              Open source
                            </a>
                          ) : null}
                        </div>
                      </div>
                    ))}
                  </div>
                </article>
              ))}
            </div>
          </Panel>
        </div>
      ) : null}
    </div>
  );
}

function mapDetailToSummary(detail: ScenarioDetail): ScenarioSummary {
  return {
    id: detail.id,
    site_id: detail.site_id,
    template_key: detail.template_key,
    template_version: detail.template_version,
    proposal_form: detail.proposal_form,
    units_assumed: detail.units_assumed,
    route_assumed: detail.route_assumed,
    height_band_assumed: detail.height_band_assumed,
    net_developable_area_pct: detail.net_developable_area_pct,
    red_line_geom_hash: detail.red_line_geom_hash,
    scenario_source: detail.scenario_source,
    status: detail.status,
    supersedes_id: detail.supersedes_id,
    is_current: detail.is_current,
    is_headline: detail.is_headline,
    heuristic_rank: detail.heuristic_rank,
    manual_review_required: detail.manual_review_required,
    stale_reason: detail.stale_reason,
    housing_mix_assumed_json: detail.housing_mix_assumed_json,
    parking_assumption: detail.parking_assumption,
    affordable_housing_assumption: detail.affordable_housing_assumption,
    access_assumption: detail.access_assumption,
    reason_codes: detail.reason_codes,
    missing_data_flags: detail.missing_data_flags,
    warning_codes: detail.warning_codes
  };
}
