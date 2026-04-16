import { cookies } from 'next/headers';

import { AUTH_SESSION_COOKIE_NAME } from './config';
import { createAuthContext, decodeSessionToken, createClearedSessionCookie } from './session';
import type { AuthContext, AuthSession } from './types';

export async function readSessionFromCookies(): Promise<AuthSession | null> {
  const cookieStore = await cookies();
  const token = cookieStore.get(AUTH_SESSION_COOKIE_NAME)?.value ?? null;
  return decodeSessionToken(token);
}

export async function getAuthContext(): Promise<AuthContext> {
  const session = await readSessionFromCookies();
  return createAuthContext(session);
}

export function getClearedSessionCookie() {
  return createClearedSessionCookie();
}
