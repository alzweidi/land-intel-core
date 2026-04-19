import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  createAssessment,
  getAdminJobs,
  getListings,
  getAssessment,
  getListingSources,
  getSites,
  runConnector,
  runCsvImport
} from '@/lib/landintel-api';

describe('landintel-api', () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    Object.defineProperty(globalThis, 'fetch', {
      configurable: true,
      value: fetchMock
    });
    fetchMock.mockReset();
  });

  it('falls back to local site data when the API is unavailable', async () => {
    fetchMock.mockRejectedValueOnce(new Error('offline'));

    const result = await getSites();

    expect(result.apiAvailable).toBe(false);
    expect(result.items.length).toBeGreaterThan(0);
  });

  it('passes hidden-mode query parameters and session headers when loading an assessment', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: 'unavailable' }), {
        status: 503,
        headers: { 'content-type': 'application/json' }
      })
    );

    const result = await getAssessment('assessment-1', {
      hidden_mode: true,
      viewer_role: 'reviewer',
      sessionToken: 'signed-session'
    });

    expect(result).toEqual({ apiAvailable: false, item: null });
    expect(fetchMock).toHaveBeenCalledTimes(1);

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain('/api/assessments/assessment-1?hidden_mode=true&viewer_role=reviewer');
    expect(new Headers(init.headers).get('x-landintel-session')).toBe('signed-session');
    expect(init.cache).toBe('no-store');
  });

  it('posts reviewer defaults when creating a hidden assessment', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: 'failed' }), {
        status: 500,
        headers: { 'content-type': 'application/json' }
      })
    );

    await createAssessment({
      site_id: 'site-1',
      scenario_id: 'scenario-1',
      as_of_date: '2026-04-15',
      hidden_mode: true
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(String(init.body));

    expect(body).toMatchObject({
      site_id: 'site-1',
      scenario_id: 'scenario-1',
      as_of_date: '2026-04-15',
      requested_by: 'web-ui',
      hidden_mode: true,
      viewer_role: 'reviewer'
    });
  });

  it('maps live listing sources without fixture fallback', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify([
          {
            id: 'source-1',
            name: 'example_public_page',
            connector_type: 'PUBLIC_PAGE',
            compliance_mode: 'COMPLIANT_AUTOMATED',
            active: true,
            refresh_policy_json: { interval_hours: 24 }
          }
        ]),
        {
          status: 200,
          headers: { 'content-type': 'application/json' }
        }
      )
    );

    const result = await getListingSources();

    expect(result.apiAvailable).toBe(true);
    expect(result.items).toEqual([
      {
        id: 'source-1',
        source_key: 'example_public_page',
        name: 'example_public_page',
        connector_type: 'public_page',
        compliance_mode: 'COMPLIANT_AUTOMATED',
        active: true,
        refresh_policy: 'Every 24h',
        coverage_note: 'Every 24h'
      }
    ]);
  });

  it('treats empty live listing collections as fixture fallback rows', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify([]), {
        status: 200,
        headers: { 'content-type': 'application/json' }
      })
    );

    const result = await getListings();

    expect(result.apiAvailable).toBe(false);
    expect(result.items.length).toBeGreaterThan(0);
  });

  it('loads admin jobs from the live admin endpoint', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify([
          {
            id: 'job-1',
            job_type: 'LISTING_SOURCE_RUN',
            status: 'QUEUED',
            requested_by: 'scheduler'
          }
        ]),
        {
          status: 200,
          headers: { 'content-type': 'application/json' }
        }
      )
    );

    const result = await getAdminJobs({ sessionToken: 'signed-session' });

    expect(result.apiAvailable).toBe(true);
    expect(result.items[0]).toMatchObject({
      id: 'job-1',
      job_type: 'LISTING_SOURCE_RUN',
      status: 'QUEUED',
      requested_by: 'scheduler'
    });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain('/api/admin/jobs');
    expect(new Headers(init.headers).get('x-landintel-session')).toBe('signed-session');
  });

  it('normalizes legacy connector source keys before posting', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { 'content-type': 'application/json' }
      })
    );

    await runConnector('approved_public_page', { coverage_note: 'pytest' });

    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain('/api/listings/connectors/example_public_page/run');
  });

  it('requires a file for CSV import submissions', async () => {
    await expect(
      runCsvImport({
        file: null as never
      })
    ).rejects.toThrow('CSV file is required.');
  });
});
