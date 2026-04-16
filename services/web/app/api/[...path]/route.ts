import { NextRequest } from 'next/server';

export const dynamic = 'force-dynamic';
export const runtime = 'nodejs';

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
  const origin = process.env.BACKEND_API_ORIGIN?.trim();
  if (!origin) {
    throw new Error('BACKEND_API_ORIGIN is required for the production API proxy.');
  }
  return origin.replace(/\/+$/, '');
}

function getBasicAuthHeader(): string {
  const username = process.env.BACKEND_BASIC_AUTH_USER?.trim();
  const password = process.env.BACKEND_BASIC_AUTH_PASSWORD?.trim();

  if (!username || !password) {
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

function buildUpstreamHeaders(request: NextRequest): Headers {
  const headers = new Headers();
  request.headers.forEach((value, key) => {
    if (!HOP_BY_HOP_HEADERS.has(key.toLowerCase())) {
      headers.set(key, value);
    }
  });
  headers.set('authorization', getBasicAuthHeader());
  return headers;
}

function sanitizeResponseHeaders(headers: Headers): Headers {
  const sanitized = new Headers();
  headers.forEach((value, key) => {
    if (!HOP_BY_HOP_HEADERS.has(key.toLowerCase())) {
      sanitized.set(key, value);
    }
  });
  sanitized.set('cache-control', 'no-store');
  return sanitized;
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

    const response = await fetch(upstream, {
      method: request.method,
      headers,
      body,
      redirect: 'manual'
    });

    return new Response(response.body, {
      status: response.status,
      headers: sanitizeResponseHeaders(response.headers)
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
