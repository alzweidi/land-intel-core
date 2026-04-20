/** @vitest-environment node */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { NextRequest } from 'next/server';

import { GET } from '@/app/api/[...path]/route';

describe('API proxy route', () => {
  const fetchMock = vi.fn();
  const originalEnv = {
    BACKEND_API_ORIGIN: process.env.BACKEND_API_ORIGIN,
    INTERNAL_API_BASE_URL: process.env.INTERNAL_API_BASE_URL,
    NEXT_PUBLIC_API_BASE_URL: process.env.NEXT_PUBLIC_API_BASE_URL,
    NEXT_PUBLIC_APP_ENV: process.env.NEXT_PUBLIC_APP_ENV,
    APP_ENV: process.env.APP_ENV,
    BACKEND_BASIC_AUTH_USER: process.env.BACKEND_BASIC_AUTH_USER,
    BACKEND_BASIC_AUTH_PASSWORD: process.env.BACKEND_BASIC_AUTH_PASSWORD
  };

  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock);
    fetchMock.mockReset();
    process.env.BACKEND_API_ORIGIN = 'http://api:8000';
    delete process.env.INTERNAL_API_BASE_URL;
    delete process.env.NEXT_PUBLIC_API_BASE_URL;
    process.env.NEXT_PUBLIC_APP_ENV = 'test';
    delete process.env.APP_ENV;
    delete process.env.BACKEND_BASIC_AUTH_USER;
    delete process.env.BACKEND_BASIC_AUTH_PASSWORD;
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    for (const [key, value] of Object.entries(originalEnv)) {
      if (value === undefined) {
        delete process.env[key];
      } else {
        process.env[key] = value;
      }
    }
  });

  it('rewrites upstream redirects onto the app origin', async () => {
    fetchMock.mockResolvedValue(
      new Response(null, {
        status: 307,
        headers: {
          location: 'http://api:8000/api/opportunities/'
        }
      })
    );

    const request = new NextRequest('http://localhost:3000/api/opportunities');
    const response = await GET(request, {
      params: Promise.resolve({ path: ['opportunities'] })
    });

    expect(response.status).toBe(307);
    expect(response.headers.get('location')).toBe('http://localhost:3000/api/opportunities/');
    expect(response.headers.get('cache-control')).toBe('no-store');
  });

  it('ignores spoofed forwarded origin headers when rewriting redirects', async () => {
    fetchMock.mockResolvedValue(
      new Response(null, {
        status: 307,
        headers: {
          location: 'http://api:8000/api/opportunities/'
        }
      })
    );

    const request = new NextRequest('http://localhost:3000/api/opportunities', {
      headers: {
        'x-forwarded-host': 'evil.example',
        'x-forwarded-proto': 'https'
      }
    });
    const response = await GET(request, {
      params: Promise.resolve({ path: ['opportunities'] })
    });

    expect(response.status).toBe(307);
    expect(response.headers.get('location')).toBe('http://localhost:3000/api/opportunities/');
  });

  it('follows same-origin upstream redirects internally for collection endpoints', async () => {
    fetchMock
      .mockResolvedValueOnce(
        new Response(null, {
          status: 307,
          headers: {
            location: 'http://api:8000/api/opportunities/'
          }
        })
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ items: [{ site_id: 'site-1' }] }), {
          status: 200,
          headers: {
            'content-type': 'application/json'
          }
        })
      );

    const request = new NextRequest('http://localhost:3000/api/opportunities');
    const response = await GET(request, {
      params: Promise.resolve({ path: ['opportunities'] })
    });

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[1]?.[0]?.toString()).toBe('http://api:8000/api/opportunities/');
    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({
      items: [{ site_id: 'site-1' }]
    });
  });
});
