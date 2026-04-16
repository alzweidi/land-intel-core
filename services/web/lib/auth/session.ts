import {
  AUTH_SESSION_COOKIE_NAME,
  AUTH_SESSION_SECRET,
  AUTH_SESSION_TTL_SECONDS,
  AUTH_ROLE_ORDER,
  isSecureAuthCookie
} from './config';
import type { AppRole, AuthContext, AuthSession, AuthUser } from './types';

const encoder = new TextEncoder();
const decoder = new TextDecoder();

type SessionCookieAttributes = {
  httpOnly: true;
  sameSite: 'lax';
  secure: boolean;
  path: string;
  maxAge: number;
};

export type SessionCookie = {
  name: string;
  value: string;
  options: SessionCookieAttributes;
};

function isAppRole(value: string): value is AppRole {
  return value === 'analyst' || value === 'reviewer' || value === 'admin';
}

function encodeBase64Url(bytes: Uint8Array): string {
  if (typeof btoa === 'function') {
    let binary = '';
    for (const byte of bytes) {
      binary += String.fromCharCode(byte);
    }
    return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/u, '');
  }

  return Buffer.from(bytes).toString('base64url');
}

function decodeBase64Url(value: string): Uint8Array {
  const normalized = value.replace(/-/g, '+').replace(/_/g, '/');
  if (typeof atob === 'function') {
    const padded = normalized + '='.repeat((4 - (normalized.length % 4 || 4)) % 4);
    const binary = atob(padded);
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index += 1) {
      bytes[index] = binary.charCodeAt(index);
    }
    return bytes;
  }

  return Buffer.from(normalized, 'base64');
}

async function importHmacKey() {
  return crypto.subtle.importKey(
    'raw',
    encoder.encode(AUTH_SESSION_SECRET),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign', 'verify']
  );
}

export function normalizeAuthIdentifier(value: string): string {
  return value.trim().toLowerCase();
}

export function resolvePostLoginPath(value: string | null | undefined, fallback = '/'): string {
  if (!value) {
    return fallback;
  }

  const trimmed = value.trim();
  if (!trimmed) {
    return fallback;
  }

  if (trimmed.startsWith('http://') || trimmed.startsWith('https://') || trimmed.startsWith('//')) {
    return fallback;
  }

  const normalized = trimmed.startsWith('/') ? trimmed : `/${trimmed}`;
  return normalized.startsWith('//') ? fallback : normalized;
}

export function roleIsAtLeast(role: AppRole | null, minimum: AppRole): boolean {
  if (!role) {
    return false;
  }

  return AUTH_ROLE_ORDER[role] >= AUTH_ROLE_ORDER[minimum];
}

export function createAuthContext(session: AuthSession | null): AuthContext {
  return {
    session,
    user: session?.user ?? null,
    role: session?.user.role ?? null,
    isAuthenticated: session !== null
  };
}

export function createSessionRecord(user: AuthUser, issuedAt = new Date()): AuthSession {
  const expiresAt = new Date(issuedAt.getTime() + AUTH_SESSION_TTL_SECONDS * 1000);

  return {
    user,
    issuedAt: issuedAt.toISOString(),
    expiresAt: expiresAt.toISOString()
  };
}

async function signPayload(payload: string): Promise<string> {
  const key = await importHmacKey();
  const signature = await crypto.subtle.sign('HMAC', key, encoder.encode(payload));
  return encodeBase64Url(new Uint8Array(signature as ArrayBuffer));
}

async function verifySignature(payload: string, signature: string): Promise<boolean> {
  const key = await importHmacKey();
  try {
    return await crypto.subtle.verify(
      'HMAC',
      key,
      decodeBase64Url(signature) as BufferSource,
      encoder.encode(payload)
    );
  } catch {
    return false;
  }
}

export async function encodeSessionToken(session: AuthSession): Promise<string> {
  const payload = encodeBase64Url(encoder.encode(JSON.stringify(session)));
  const signature = await signPayload(payload);
  return `${payload}.${signature}`;
}

export async function decodeSessionToken(token: string | null | undefined): Promise<AuthSession | null> {
  if (!token) {
    return null;
  }

  const [payload, signature] = token.split('.');
  if (!payload || !signature) {
    return null;
  }

  const verified = await verifySignature(payload, signature);
  if (!verified) {
    return null;
  }

  try {
    const session = JSON.parse(decoder.decode(decodeBase64Url(payload))) as AuthSession;
    if (!session?.user || !isAppRole(session.user.role)) {
      return null;
    }

    if (!session.expiresAt || Number.isNaN(Date.parse(session.expiresAt))) {
      return null;
    }

    if (Date.now() >= Date.parse(session.expiresAt)) {
      return null;
    }

    return session;
  } catch {
    return null;
  }
}

export async function createSessionCookie(user: AuthUser): Promise<SessionCookie> {
  const session = createSessionRecord(user);
  const value = await encodeSessionToken(session);

  return {
    name: AUTH_SESSION_COOKIE_NAME,
    value,
    options: {
      httpOnly: true,
      sameSite: 'lax',
      secure: isSecureAuthCookie(),
      path: '/',
      maxAge: AUTH_SESSION_TTL_SECONDS
    }
  };
}

export function createClearedSessionCookie(): SessionCookie {
  return {
    name: AUTH_SESSION_COOKIE_NAME,
    value: '',
    options: {
      httpOnly: true,
      sameSite: 'lax',
      secure: isSecureAuthCookie(),
      path: '/',
      maxAge: 0
    }
  };
}
