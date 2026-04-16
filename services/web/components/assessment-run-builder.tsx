'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';

import { createAssessment } from '@/lib/landintel-api';

import { Panel } from './ui';

type AssessmentRunBuilderProps = {
  initialSiteId?: string;
  initialScenarioId?: string;
  initialAsOfDate?: string;
};

function todayIsoDate(): string {
  return new Date().toISOString().slice(0, 10);
}

export function AssessmentRunBuilder({
  initialSiteId = '',
  initialScenarioId = '',
  initialAsOfDate
}: AssessmentRunBuilderProps) {
  const router = useRouter();
  const [siteId, setSiteId] = useState(initialSiteId);
  const [scenarioId, setScenarioId] = useState(initialScenarioId);
  const [asOfDate, setAsOfDate] = useState(initialAsOfDate ?? todayIsoDate());
  const [message, setMessage] = useState(
    'A confirmed scenario is required. The run freezes PIT artifacts, may execute a hidden internal score if an active hidden release exists, can build an immutable valuation result, and respects the current visibility and override controls.'
  );
  const [loading, setLoading] = useState(false);

  async function handleSubmit() {
    if (!siteId || !scenarioId || !asOfDate) {
      setMessage('Enter a site ID, confirmed scenario ID, and as-of date.');
      return;
    }

    setLoading(true);
    const response = await createAssessment({
      site_id: siteId.trim(),
      scenario_id: scenarioId.trim(),
      as_of_date: asOfDate,
      requested_by: 'web-ui',
      hidden_mode: false
    });

    if (!response.item) {
      setMessage('Assessment creation failed. Check that the scenario is current and confirmed.');
      setLoading(false);
      return;
    }

    setMessage(
      `Assessment ${response.item.id} created. Standard reads remain non-speaking unless hidden mode is opened explicitly.`
    );
    router.push(`/assessments/${response.item.id}`);
    router.refresh();
  }

  return (
    <Panel
      eyebrow="Assessment run"
      title="Create frozen assessment artifact"
      note="Hidden internal scoring and valuation may run here, but standard analyst reads still stay non-speaking unless a scope is explicitly and honestly enabled."
    >
      <div className="form-stack" style={{ display: 'grid', gap: 12 }}>
        <label className="field">
          <span className="field__label">Site ID</span>
          <input
            onChange={(event) => setSiteId(event.target.value)}
            placeholder="UUID"
            type="text"
            value={siteId}
          />
        </label>
        <label className="field">
          <span className="field__label">Confirmed scenario ID</span>
          <input
            onChange={(event) => setScenarioId(event.target.value)}
            placeholder="UUID"
            type="text"
            value={scenarioId}
          />
        </label>
        <label className="field">
          <span className="field__label">As-of date</span>
          <input onChange={(event) => setAsOfDate(event.target.value)} type="date" value={asOfDate} />
        </label>
      </div>

      <div className="button-row" style={{ display: 'flex', gap: 12, marginTop: 16, flexWrap: 'wrap' }}>
        <button
          className="button button--solid"
          disabled={loading}
          onClick={() => void handleSubmit()}
          type="button"
        >
          {loading ? 'Freezing run...' : 'Create assessment'}
        </button>
      </div>

      <p className="table-secondary" style={{ marginTop: 12 }}>
        {message}
      </p>
    </Panel>
  );
}
