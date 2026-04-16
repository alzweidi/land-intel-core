import type { NextRequest } from 'next/server';
import { NextResponse } from 'next/server';

import {
  canAccessPath,
  getDefaultLandingPath
} from '@/lib/auth/access';
import { AUTH_SESSION_COOKIE_NAME } from '@/lib/auth/config';
import { decodeSessionToken } from '@/lib/auth/session';

const PUBLIC_PATH_PREFIXES = ['/login', '/api/auth'];
const STATIC_FILE_PATTERN = /\.(?:svg|png|jpg|jpeg|gif|webp|ico|txt|xml|map)$/i;

function isPublicPath(pathname: string): boolean {
  if (pathname.startsWith('/_next')) {
    return true;
  }
  if (STATIC_FILE_PATTERN.test(pathname)) {
    return true;
  }
  return PUBLIC_PATH_PREFIXES.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`));
}

export async function middleware(request: NextRequest): Promise<NextResponse> {
  const { pathname, search } = request.nextUrl;
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set('x-landintel-pathname', pathname);

  if (isPublicPath(pathname)) {
    return NextResponse.next({
      request: {
        headers: requestHeaders,
      },
    });
  }

  const session = await decodeSessionToken(
    request.cookies.get(AUTH_SESSION_COOKIE_NAME)?.value
  );
  if (!session) {
    const loginUrl = request.nextUrl.clone();
    loginUrl.pathname = '/login';
    loginUrl.search = '';
    loginUrl.searchParams.set('next', `${pathname}${search}`);
    return NextResponse.redirect(loginUrl);
  }

  if (!canAccessPath(session.user.role, pathname)) {
    const redirectUrl = request.nextUrl.clone();
    redirectUrl.pathname = getDefaultLandingPath(session.user.role);
    redirectUrl.search = '';
    return NextResponse.redirect(redirectUrl);
  }

  return NextResponse.next({
    request: {
      headers: requestHeaders,
    },
  });
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'],
};
