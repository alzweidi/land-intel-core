import { cookies } from 'next/headers';
import { NextRequest, NextResponse } from 'next/server';

import {
  AUTH_COOKIE_NAME,
  authenticateLocalUser,
  buildSessionForCandidate,
  encodeSessionCookie,
  getAppOrigin,
  getSessionTtlSeconds,
} from '@/lib/auth';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

function sanitizeNextPath(value: string | null): string {
  if (!value || !value.startsWith('/')) {
    return '/listings';
  }
  if (value.startsWith('//')) {
    return '/listings';
  }
  return value;
}

export async function POST(request: NextRequest): Promise<NextResponse> {
  const formData = await request.formData();
  const email = String(formData.get('email') ?? '').trim();
  const password = String(formData.get('password') ?? '');
  const nextPath = sanitizeNextPath(
    typeof formData.get('next') === 'string' ? String(formData.get('next')) : null
  );

  const candidate = await authenticateLocalUser(email, password);
  if (!candidate) {
    const redirectUrl = new URL('/login', getAppOrigin(request));
    redirectUrl.searchParams.set('error', 'invalid_credentials');
    redirectUrl.searchParams.set('next', nextPath);
    return NextResponse.redirect(redirectUrl, { status: 303 });
  }

  const session = await buildSessionForCandidate(candidate);
  const encoded = await encodeSessionCookie(session);
  const cookieStore = await cookies();
  cookieStore.set(AUTH_COOKIE_NAME, encoded, {
    httpOnly: true,
    maxAge: getSessionTtlSeconds(),
    path: '/',
    sameSite: 'lax',
    secure: process.env.LANDINTEL_WEB_AUTH_COOKIE_SECURE === 'true'
      ? true
      : process.env.LANDINTEL_WEB_AUTH_COOKIE_SECURE === 'false'
        ? false
        : process.env.NODE_ENV === 'production',
  });

  return NextResponse.redirect(new URL(nextPath, getAppOrigin(request)), { status: 303 });
}
