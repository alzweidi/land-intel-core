"use client";

import { useState } from 'react';

import { Badge } from '@/components/ui';
import { phase1ASources } from '@/lib/phase1a-data';
import { runConnector, runCsvImport, runManualUrlIntake } from '@/lib/landintel-api';

type ActionKey = 'manual' | 'csv' | 'connector';

function prettyJson(value: unknown): string {
  if (typeof value === 'string') {
    return value;
  }

  return JSON.stringify(value, null, 2);
}

function ResponseBlock({ payload, error }: { payload: unknown; error: string | null }) {
  return (
    <div className="response-block" aria-live="polite">
      <div className="response-block__head">
        <Badge tone={error ? 'danger' : 'success'}>{error ? 'Request failed' : 'Request result'}</Badge>
      </div>
      <pre className="code-block">{error ?? prettyJson(payload)}</pre>
    </div>
  );
}

export function ListingRunPanel() {
  const [manualUrl, setManualUrl] = useState('https://example.com/listings/land-at-riverside-yard');
  const [csvText, setCsvText] = useState('source_listing_id,headline,borough,guide_price_gbp\nbroker-drop-17,Rear Yard off Albion Street,Lambeth,875000');
  const [sourceKey, setSourceKey] = useState('approved_public_page');
  const [coverageNote, setCoverageNote] = useState('Internal analyst run');
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [pending, setPending] = useState<ActionKey | null>(null);
  const [response, setResponse] = useState<unknown | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function execute(action: ActionKey) {
    setPending(action);
    setError(null);

    try {
      let payload: unknown | null = null;

      if (action === 'manual') {
        payload = await runManualUrlIntake({
          url: manualUrl,
          coverage_note: coverageNote
        });
      } else if (action === 'csv') {
        payload = await runCsvImport({
          file: csvFile,
          csv_text: csvText,
          coverage_note: coverageNote
        });
      } else {
        payload = await runConnector(sourceKey, {
          coverage_note: coverageNote
        });
      }

      setResponse(payload);
      if (!payload) {
        setError('API unavailable or returned a non-JSON response. The UI keeps working with fixture data.');
      }
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : 'Unexpected request failure';
      setError(message);
    } finally {
      setPending(null);
    }
  }

  return (
    <div className="connector-grid">
      <section className="connector-card">
        <div className="connector-card__head">
          <Badge tone="accent">Manual URL</Badge>
          <span className="connector-card__hint">One URL, one immutable source snapshot.</span>
        </div>
        <label className="field">
          <span>Listing URL</span>
          <input value={manualUrl} onChange={(event) => setManualUrl(event.target.value)} type="url" />
        </label>
        <button className="button button--solid" disabled={pending !== null} onClick={() => void execute('manual')} type="button">
          {pending === 'manual' ? 'Submitting…' : 'Post /api/listings/intake/url'}
        </button>
      </section>

      <section className="connector-card">
        <div className="connector-card__head">
          <Badge tone="warning">CSV / broker drop</Badge>
          <span className="connector-card__hint">File upload or pasted CSV text.</span>
        </div>
        <label className="field">
          <span>CSV file</span>
          <input onChange={(event) => setCsvFile(event.target.files?.[0] ?? null)} type="file" accept=".csv,text/csv" />
        </label>
        <label className="field">
          <span>CSV text</span>
          <textarea value={csvText} onChange={(event) => setCsvText(event.target.value)} rows={5} />
        </label>
        <button className="button button--ghost" disabled={pending !== null} onClick={() => void execute('csv')} type="button">
          {pending === 'csv' ? 'Submitting…' : 'Post /api/listings/import/csv'}
        </button>
      </section>

      <section className="connector-card">
        <div className="connector-card__head">
          <Badge tone="success">Approved public page</Badge>
          <span className="connector-card__hint">Blocked unless source compliance mode allows it.</span>
        </div>
        <label className="field">
          <span>Source key</span>
          <input value={sourceKey} onChange={(event) => setSourceKey(event.target.value)} list="phase1a-sources" />
          <datalist id="phase1a-sources">
            {phase1ASources.map((source) => (
              <option key={source.source_key} value={source.source_key} />
            ))}
          </datalist>
        </label>
        <button className="button button--ghost" disabled={pending !== null} onClick={() => void execute('connector')} type="button">
          {pending === 'connector' ? 'Submitting…' : 'Post /api/listings/connectors/{source_key}/run'}
        </button>
      </section>

      <section className="connector-card connector-card--full">
        <div className="connector-card__head">
          <Badge tone="neutral">Request note</Badge>
          <span className="connector-card__hint">Used in all three submissions.</span>
        </div>
        <label className="field">
          <span>Coverage note</span>
          <input value={coverageNote} onChange={(event) => setCoverageNote(event.target.value)} />
        </label>
      </section>

      <section className="connector-card connector-card--full">
        <div className="connector-card__head">
          <Badge tone={error ? 'danger' : 'accent'}>Result</Badge>
          <span className="connector-card__hint">The response is rendered verbatim for easy debugging.</span>
        </div>
        <ResponseBlock payload={response} error={error} />
      </section>
    </div>
  );
}
