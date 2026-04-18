import { beforeEach, describe, expect, it, vi } from 'vitest';

import { createAssessment, getAssessment, getSites } from '@/lib/landintel-api';

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
});
