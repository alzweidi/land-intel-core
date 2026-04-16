import type { Metadata } from 'next';
import type { ReactNode } from 'react';
import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';
import { Cormorant_Garamond, IBM_Plex_Mono, IBM_Plex_Sans } from 'next/font/google';
import 'maplibre-gl/dist/maplibre-gl.css';

import { AppShell } from '../components/app-shell';
import { AUTH_SESSION_COOKIE_NAME } from '@/lib/auth/config';
import { getAuthContext } from '@/lib/auth/server';
import './globals.css';

const display = Cormorant_Garamond({
  subsets: ['latin'],
  variable: '--font-display'
});

const body = IBM_Plex_Sans({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  variable: '--font-body'
});

const mono = IBM_Plex_Mono({
  subsets: ['latin'],
  weight: ['400', '500', '600'],
  variable: '--font-mono'
});

export const metadata: Metadata = {
  title: {
    default: 'Land Intel',
    template: '%s · Land Intel'
  },
  description: 'Internal London-first land intelligence workspace with listings, sites, scenarios, assessments, and operations.'
};

export default async function RootLayout({
  children
}: Readonly<{
  children: ReactNode;
}>) {
  const auth = await getAuthContext();

  async function logoutAction() {
    'use server';

    const cookieStore = await cookies();
    cookieStore.set(AUTH_SESSION_COOKIE_NAME, '', {
      httpOnly: true,
      sameSite: 'lax',
      secure: process.env.NODE_ENV === 'production',
      path: '/',
      maxAge: 0
    });
    redirect('/login');
  }

  return (
    <html
      lang="en"
      className={`${display.variable} ${body.variable} ${mono.variable}`}
      suppressHydrationWarning
    >
      <body className={auth.session ? 'site-body site-body--authenticated' : 'site-body site-body--public'}>
        {auth.isAuthenticated ? (
          <AppShell auth={auth} onLogout={logoutAction}>
            {children}
          </AppShell>
        ) : (
          children
        )}
      </body>
    </html>
  );
}
