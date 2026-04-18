import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  createAuthContext,
  createClearedSessionCookie,
  createSessionCookie,
  createSessionRecord,
  decodeSessionToken,
  encodeSessionToken,
  normalizeAuthIdentifier,
  resolvePostLoginPath,
  roleIsAtLeast
} from '@/lib/auth/session';

describe('auth session utilities', () => {
  const user = {
    id: 'reviewer@example.test',
    email: 'reviewer@example.test',
    name: 'Reviewer',
    role: 'reviewer' as const
  };

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('round-trips signed session tokens', async () => {
    const session = createSessionRecord(user);

    const token = await encodeSessionToken(session);
    const decoded = await decodeSessionToken(token);

    expect(decoded).toEqual(session);
  });

  it('rejects malformed tokens and sanitizes post-login redirects', async () => {
    expect(normalizeAuthIdentifier('  Reviewer@Example.TEST  ')).toBe('reviewer@example.test');
    expect(await decodeSessionToken(null)).toBeNull();
    expect(await decodeSessionToken(undefined)).toBeNull();
    expect(await decodeSessionToken('not-a-token')).toBeNull();
    expect(resolvePostLoginPath('https://evil.test', '/listings')).toBe('/listings');
    expect(resolvePostLoginPath('//evil.test', '/listings')).toBe('/listings');
    expect(resolvePostLoginPath('', '/listings')).toBe('/listings');
    expect(resolvePostLoginPath('   ', '/listings')).toBe('/listings');
    expect(resolvePostLoginPath('sites')).toBe('/sites');
    expect(resolvePostLoginPath('/sites')).toBe('/sites');
  });

  it('builds auth context and cookie metadata', async () => {
    const session = createSessionRecord(user);
    const cookie = await createSessionCookie(user);
    const cleared = createClearedSessionCookie();

    expect(roleIsAtLeast('admin', 'reviewer')).toBe(true);
    expect(roleIsAtLeast('analyst', 'reviewer')).toBe(false);
    expect(roleIsAtLeast(null, 'analyst')).toBe(false);
    expect(createAuthContext(session)).toMatchObject({
      isAuthenticated: true,
      role: 'reviewer'
    });
    expect(createAuthContext(null)).toMatchObject({
      isAuthenticated: false,
      role: null,
      user: null,
      session: null
    });
    expect(cookie.options.httpOnly).toBe(true);
    expect(cookie.options.maxAge).toBeGreaterThan(0);
    expect(cleared.options.maxAge).toBe(0);
  });

  it('round-trips session tokens when browser base64 helpers are unavailable', async () => {
    vi.stubGlobal('btoa', undefined as never);
    vi.stubGlobal('atob', undefined as never);

    const session = createSessionRecord(user);
    const token = await encodeSessionToken(session);
    const decoded = await decodeSessionToken(token);

    expect(decoded).toEqual(session);
  });

  it('decodes signed tokens with and without base64 padding', async () => {
    const session = createSessionRecord(user);
    const payload = Buffer.from(JSON.stringify(session), 'utf8').toString('base64url');

    vi.spyOn(crypto.subtle, 'verify').mockResolvedValue(true);

    expect(await decodeSessionToken(`${payload}.AAAA`)).toEqual(session);
    expect(await decodeSessionToken(`${payload}.AAA`)).toEqual(session);
  });

  it('rejects sessions with invalid role, malformed expiry, or expired timestamps', async () => {
    const invalidRoleSession = {
      ...createSessionRecord(user),
      user: {
        ...user,
        role: 'guest'
      }
    } as never;
    const malformedExpirySession = {
      ...createSessionRecord(user),
      expiresAt: 'not-a-date'
    } as never;
    const expiredSession = {
      ...createSessionRecord(user),
      expiresAt: '2000-01-01T00:00:00.000Z'
    } as never;

    expect(await decodeSessionToken(await encodeSessionToken(invalidRoleSession))).toBeNull();
    expect(await decodeSessionToken(await encodeSessionToken(malformedExpirySession))).toBeNull();
    expect(await decodeSessionToken(await encodeSessionToken(expiredSession))).toBeNull();

    vi.spyOn(crypto.subtle, 'verify').mockResolvedValue(false);
    expect(await decodeSessionToken(await encodeSessionToken(createSessionRecord(user)))).toBeNull();
  });

  it('returns null for malformed JSON payloads when signatures validate', async () => {
    vi.spyOn(JSON, 'parse').mockImplementation(() => {
      throw new Error('boom');
    });

    const token = await encodeSessionToken(createSessionRecord(user));
    expect(await decodeSessionToken(token)).toBeNull();
  });

  it('returns null when signature verification throws', async () => {
    const token = await encodeSessionToken(createSessionRecord(user));
    vi.spyOn(crypto.subtle, 'verify').mockRejectedValue(new Error('boom'));

    await expect(decodeSessionToken(token)).resolves.toBeNull();
  });
});
