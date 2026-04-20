"use client";

import { useEffect, useState } from 'react';

import { Badge } from '@/components/ui';
import type { Phase1ASource } from '@/lib/phase1a-data';
import { selectDefaultAutomatedSourceKey } from '@/lib/listing-source-console';
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

export function ListingRunPanel({ sourceOptions }: { sourceOptions: Phase1ASource[] }) {
  const [manualUrl, setManualUrl] = useState('https://example.com/listings/land-at-riverside-yard');
  const [sourceKey, setSourceKey] = useState(selectDefaultAutomatedSourceKey(sourceOptions));
  const [coverageNote, setCoverageNote] = useState('Internal analyst run');
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [pending, setPending] = useState<ActionKey | null>(null);
  const [response, setResponse] = useState<unknown | null>(null);
  const [error, setError] = useState<string | null>(null);
  const hasAutomatedSources = sourceOptions.some(
    (source) => source.active && source.compliance_mode === 'COMPLIANT_AUTOMATED'
  );

  useEffect(() => {
    setSourceKey(selectDefaultAutomatedSourceKey(sourceOptions));
  }, [sourceOptions]);

  async function execute(action: ActionKey) {
    if (action === 'csv' && !csvFile) {
      setError('Select a CSV file before submitting the import.');
      return;
    }

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
          file: csvFile as File,
          coverage_note: coverageNote
        });
      } else {
        payload = await runConnector(sourceKey, {
          coverage_note: coverageNote
        });
      }

      setResponse(payload);
      if (!payload) {
        setError('API unavailable or returned a non-JSON response.');
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
          <span className="connector-card__hint">File upload only.</span>
        </div>
        <label className="field">
          <span>CSV file</span>
          <input onChange={(event) => setCsvFile(event.target.files?.[0] ?? null)} type="file" accept=".csv,text/csv" />
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
          <input
            disabled={!hasAutomatedSources}
            value={sourceKey}
            onChange={(event) => setSourceKey(event.target.value)}
            list="phase1a-sources"
          />
          <datalist id="phase1a-sources">
            {sourceOptions.map((source) => (
              <option key={source.source_key} value={source.source_key} />
            ))}
          </datalist>
        </label>
        <button
          className="button button--ghost"
          disabled={pending !== null || !hasAutomatedSources}
          onClick={() => void execute('connector')}
          type="button"
        >
          {pending === 'connector' ? 'Submitting…' : 'Post /api/listings/connectors/{source_key}/run'}
        </button>
        {!hasAutomatedSources ? (
          <p className="empty-note">No active compliant automated source is currently available.</p>
        ) : null}
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
