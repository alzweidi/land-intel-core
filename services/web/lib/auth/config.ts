import type { AppRole } from './types';

export const AUTH_SESSION_TTL_SECONDS = 60 * 60 * 12;
const DEFAULT_AUTH_SESSION_SECRET = 'landintel-local-web-session-secret';

function resolveAuthSessionSecret(): string {
  const secret =
    process.env.LANDINTEL_WEB_AUTH_SECRET ??
    process.env.AUTH_SECRET ??
    DEFAULT_AUTH_SESSION_SECRET;
  const deployLikeEnvironment = Boolean(
    process.env.LANDINTEL_WEB_PUBLIC_ORIGIN?.trim() ||
      process.env.NETLIFY === 'true' ||
      process.env.VERCEL === '1'
  );
  const appEnv = (
    process.env.NEXT_PUBLIC_APP_ENV ??
    process.env.APP_ENV ??
    (deployLikeEnvironment ? 'production' : 'development')
  )
    .trim()
    .toLowerCase();

  if (appEnv !== 'development' && appEnv !== 'test' && secret === DEFAULT_AUTH_SESSION_SECRET) {
    throw new Error(
      'LANDINTEL_WEB_AUTH_SECRET must be set to a non-default value outside local dev.'
    );
  }

  return secret;
}

export const AUTH_SESSION_SECRET = resolveAuthSessionSecret();

export function isSecureAuthCookie(): boolean {
  const override = process.env.LANDINTEL_WEB_AUTH_COOKIE_SECURE;

  if (override === 'true') {
    return true;
  }

  if (override === 'false') {
    return false;
  }

  return process.env.NODE_ENV === 'production';
}

export const AUTH_SESSION_COOKIE_NAME = isSecureAuthCookie()
  ? '__Host-landintel-session'
  : 'landintel-session';

export function getAppOrigin(request: {
  headers: Headers;
  nextUrl?: { origin: string };
}): string {
  const configuredOrigin = process.env.LANDINTEL_WEB_PUBLIC_ORIGIN?.trim();
  if (configuredOrigin) {
    return configuredOrigin.replace(/\/+$/u, '');
  }

  const forwardedHost = request.headers.get('x-forwarded-host') ?? request.headers.get('host');
  if (!forwardedHost) {
    return request.nextUrl?.origin ?? 'http://localhost:3000';
  }

  const forwardedProto =
    request.headers.get('x-forwarded-proto') ??
    (process.env.NODE_ENV === 'production' ? 'https' : 'http');

  return `${forwardedProto}://${forwardedHost}`;
}

export const AUTH_LOGIN_NEXT_PARAM = 'next';

export const AUTH_ROLE_ORDER: Record<AppRole, number> = {
  analyst: 0,
  reviewer: 1,
  admin: 2
};
