import { NextRequest } from 'next/server';

import { AUTH_SESSION_COOKIE_NAME } from '@/lib/auth/config';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';
const LOCAL_APP_ENVS = new Set(['development', 'local', 'test']);

const HOP_BY_HOP_HEADERS = new Set([
  'authorization',
  'connection',
  'content-length',
  'cookie',
  'host',
  'keep-alive',
  'proxy-authenticate',
  'proxy-authorization',
  'te',
  'trailer',
  'transfer-encoding',
  'upgrade'
]);

type RouteContext = {
  params: Promise<{
    path: string[];
  }>;
};

function getBackendOrigin(): string {
  const origin =
    process.env.BACKEND_API_ORIGIN?.trim() ||
    process.env.INTERNAL_API_BASE_URL?.trim() ||
    process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  if (!origin) {
    throw new Error('A backend API origin is required for the API proxy.');
  }
  return origin.replace(/\/+$/, '');
}

function isLocalAppEnv(): boolean {
  const appEnv = (
    process.env.NEXT_PUBLIC_APP_ENV ??
    process.env.APP_ENV ??
    'development'
  )
    .trim()
    .toLowerCase();
  return LOCAL_APP_ENVS.has(appEnv);
}

function getBasicAuthHeader(): string | null {
  const username = process.env.BACKEND_BASIC_AUTH_USER?.trim();
  const password = process.env.BACKEND_BASIC_AUTH_PASSWORD?.trim();

  if (!username || !password) {
    if (isLocalAppEnv()) {
      return null;
    }
    throw new Error(
      'BACKEND_BASIC_AUTH_USER and BACKEND_BASIC_AUTH_PASSWORD are required for the production API proxy.'
    );
  }

  return `Basic ${Buffer.from(`${username}:${password}`).toString('base64')}`;
}

function buildUpstreamUrl(request: NextRequest, segments: string[]): URL {
  const upstream = new URL(`${getBackendOrigin()}/api/${segments.join('/')}`);
  request.nextUrl.searchParams.forEach((value, key) => {
    upstream.searchParams.append(key, value);
  });
  return upstream;
}

function getAppOrigin(request: NextRequest): string {
  const forwardedHost = request.headers
    .get('x-forwarded-host')
    ?.split(',')[0]
    ?.trim();
  const host = forwardedHost || request.headers.get('host')?.trim() || request.nextUrl.host;
  const forwardedProto = request.headers
    .get('x-forwarded-proto')
    ?.split(',')[0]
    ?.trim();
  const protocol = forwardedProto || request.nextUrl.protocol.replace(/:$/, '');
  return `${protocol}://${host}`;
}

function buildUpstreamHeaders(request: NextRequest): Headers {
  const headers = new Headers();
  request.headers.forEach((value, key) => {
    if (!HOP_BY_HOP_HEADERS.has(key.toLowerCase())) {
      headers.set(key, value);
    }
  });
  const basicAuthHeader = getBasicAuthHeader();
  if (basicAuthHeader) {
    headers.set('authorization', basicAuthHeader);
  }
  const sessionToken =
    request.cookies.get(AUTH_SESSION_COOKIE_NAME)?.value ??
    request.cookies.get('landintel-session')?.value ??
    request.cookies.get('__Host-landintel-session')?.value;
  if (sessionToken) {
    headers.set('x-landintel-session', sessionToken);
  }
  return headers;
}

function rewriteLocationHeader(location: string, request: NextRequest): string {
  try {
    const backendOrigin = getBackendOrigin();
    const resolved = new URL(location, backendOrigin);
    if (resolved.origin !== backendOrigin) {
      return location;
    }
    return new URL(
      `${resolved.pathname}${resolved.search}${resolved.hash}`,
      getAppOrigin(request)
    ).toString();
  } catch {
    return location;
  }
}

function sanitizeResponseHeaders(headers: Headers, request: NextRequest): Headers {
  const sanitized = new Headers();
  headers.forEach((value, key) => {
    if (!HOP_BY_HOP_HEADERS.has(key.toLowerCase())) {
      if (key.toLowerCase() === 'location') {
        sanitized.set(key, rewriteLocationHeader(value, request));
      } else {
        sanitized.set(key, value);
      }
    }
  });
  sanitized.set('cache-control', 'no-store');
  return sanitized;
}

function resolveSameOriginRedirect(response: Response, upstream: URL): URL | null {
  if (![301, 302, 303, 307, 308].includes(response.status)) {
    return null;
  }
  const location = response.headers.get('location');
  if (!location) {
    return null;
  }
  const resolved = new URL(location, upstream);
  if (resolved.origin !== upstream.origin) {
    return null;
  }
  return resolved;
}

async function proxyRequest(request: NextRequest, context: RouteContext): Promise<Response> {
  try {
    const { path = [] } = await context.params;
    const upstream = buildUpstreamUrl(request, path);
    const headers = buildUpstreamHeaders(request);
    const body =
      request.method === 'GET' || request.method === 'HEAD'
        ? undefined
        : await request.arrayBuffer();

    let response = await fetch(upstream, {
      method: request.method,
      headers,
      body,
      redirect: 'manual'
    });

    const redirectTarget = resolveSameOriginRedirect(response, upstream);
    if (redirectTarget) {
      const redirectMethod = response.status === 303 ? 'GET' : request.method;
      response = await fetch(redirectTarget, {
        method: redirectMethod,
        headers,
        body: redirectMethod === 'GET' || redirectMethod === 'HEAD' ? undefined : body,
        redirect: 'manual'
      });
    }

    return new Response(response.body, {
      status: response.status,
      headers: sanitizeResponseHeaders(response.headers, request)
    });
  } catch (error) {
    const detail =
      error instanceof Error ? error.message : 'The API proxy failed before reaching the backend.';
    return Response.json(
      {
        detail,
        surface: 'web.api.proxy'
      },
      {
        status: 500,
        headers: {
          'Cache-Control': 'no-store'
        }
      }
    );
  }
}

export async function DELETE(request: NextRequest, context: RouteContext): Promise<Response> {
  return proxyRequest(request, context);
}

export async function GET(request: NextRequest, context: RouteContext): Promise<Response> {
  return proxyRequest(request, context);
}

export async function HEAD(request: NextRequest, context: RouteContext): Promise<Response> {
  return proxyRequest(request, context);
}

export async function OPTIONS(request: NextRequest, context: RouteContext): Promise<Response> {
  return proxyRequest(request, context);
}

export async function PATCH(request: NextRequest, context: RouteContext): Promise<Response> {
  return proxyRequest(request, context);
}

export async function POST(request: NextRequest, context: RouteContext): Promise<Response> {
  return proxyRequest(request, context);
}

export async function PUT(request: NextRequest, context: RouteContext): Promise<Response> {
  return proxyRequest(request, context);
}
