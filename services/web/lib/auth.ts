import {
  AUTH_SESSION_COOKIE_NAME,
  AUTH_SESSION_TTL_SECONDS,
  getAppOrigin,
  isSecureAuthCookie
} from './auth/config';
import {
  canAccessPath as canAccessPathForRole,
  getDefaultLandingPath as getDefaultLandingPathForRole
} from './auth/access';
import { getLocalAuthExamples, authenticateLocalCredentials } from './auth/local-adapter';
import { readSessionFromCookies } from './auth/server';
import {
  createSessionCookie,
  decodeSessionToken,
  encodeSessionToken
} from './auth/session';
import type { AppRole, AuthSession, AuthUser, LoginExample } from './auth/types';

export type { AppRole, AuthSession, AuthUser, LoginExample } from './auth/types';

export const AUTH_COOKIE_NAME = AUTH_SESSION_COOKIE_NAME;
export { getAppOrigin, isSecureAuthCookie };

export type LegacyAuthSession = {
  email: string;
  name: string;
  role: AppRole;
  provider: 'local-demo';
  exp: number;
};

function toLegacySession(session: AuthSession | null): LegacyAuthSession | null {
  if (!session?.user) {
    return null;
  }

  return {
    email: session.user.email,
    name: session.user.name,
    role: session.user.role,
    provider: 'local-demo',
    exp: Math.floor(Date.parse(session.expiresAt) / 1000)
  };
}

function fromLegacySession(session: LegacyAuthSession): AuthSession {
  const expiresAt = new Date(session.exp * 1000);
  const issuedAt = new Date(expiresAt.getTime() - AUTH_SESSION_TTL_SECONDS * 1000);

  return {
    user: {
      id: session.email,
      email: session.email,
      name: session.name,
      role: session.role
    },
    issuedAt: issuedAt.toISOString(),
    expiresAt: expiresAt.toISOString()
  };
}

export async function getAuthSession(): Promise<LegacyAuthSession | null> {
  return toLegacySession(await readSessionFromCookies());
}

export function getSessionTtlSeconds(): number {
  return AUTH_SESSION_TTL_SECONDS;
}

export function getDefaultLandingPath(role: AppRole): string {
  return getDefaultLandingPathForRole(role);
}

export function canAccessPath(role: AppRole, pathname: string): boolean {
  return canAccessPathForRole(role, pathname);
}

export async function decodeSessionCookie(
  value: string | null | undefined
): Promise<LegacyAuthSession | null> {
  return toLegacySession(await decodeSessionToken(value));
}

export function getLoginHints(): LoginExample[] {
  return getLocalAuthExamples();
}

export async function authenticateLocalUser(
  email: string,
  password: string
): Promise<{ email: string; name: string; role: AppRole } | null> {
  const user = await authenticateLocalCredentials({ identifier: email, password });
  if (!user) {
    return null;
  }

  return {
    email: user.email,
    name: user.name,
    role: user.role
  };
}

export async function buildSessionForCandidate(candidate: {
  email: string;
  name: string;
  role: AppRole;
}): Promise<LegacyAuthSession> {
  const user: AuthUser = {
    id: candidate.email,
    email: candidate.email,
    name: candidate.name,
    role: candidate.role
  };
  const cookie = await createSessionCookie(user);
  const session = await decodeSessionToken(cookie.value);
  return toLegacySession(session)!;
}

export async function encodeSessionCookie(session: LegacyAuthSession): Promise<string> {
  return encodeSessionToken(fromLegacySession(session));
}

export async function authenticateWithIdentifier(
  identifier: string,
  password: string
): Promise<AuthUser | null> {
  return authenticateLocalCredentials({ identifier, password });
}
