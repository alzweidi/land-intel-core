import { beforeEach, describe, expect, it, vi } from 'vitest';

import { getClusters, getReadbackState, getSites } from '@/lib/landintel-api';

describe('real-data-launch readback states', () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    Object.defineProperty(globalThis, 'fetch', {
      configurable: true,
      value: fetchMock
    });
    fetchMock.mockReset();
  });

  it('preserves empty live site and cluster collections instead of falling back to fixtures', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify([]), {
        status: 200,
        headers: { 'content-type': 'application/json' }
      })
    );

    const sites = await getSites();

    expect(sites.apiAvailable).toBe(true);
    expect(sites.items).toEqual([]);
    expect(getReadbackState(sites.apiAvailable, sites.items.length)).toBe('EMPTY');

    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify([]), {
        status: 200,
        headers: { 'content-type': 'application/json' }
      })
    );

    const clusters = await getClusters();

    expect(clusters.apiAvailable).toBe(true);
    expect(clusters.items).toEqual([]);
    expect(getReadbackState(clusters.apiAvailable, clusters.items.length)).toBe('EMPTY');
  });

  it('classifies fallback readback when the live API is unavailable', async () => {
    fetchMock.mockRejectedValueOnce(new Error('offline'));

    const sites = await getSites();

    expect(sites.apiAvailable).toBe(false);
    expect(sites.items.length).toBeGreaterThan(0);
    expect(getReadbackState(sites.apiAvailable, sites.items.length)).toBe('FALLBACK');
  });
});
