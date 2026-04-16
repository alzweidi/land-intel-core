import { cookies } from 'next/headers';
import { NextRequest, NextResponse } from 'next/server';

import { AUTH_COOKIE_NAME, getAppOrigin } from '@/lib/auth';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function POST(request: NextRequest): Promise<NextResponse> {
  const cookieStore = await cookies();
  cookieStore.delete(AUTH_COOKIE_NAME);
  return NextResponse.redirect(new URL('/login', getAppOrigin(request)), { status: 303 });
}
