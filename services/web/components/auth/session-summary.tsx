'use client';

import { Badge } from '@/components/ui';
import type { AuthContext } from '@/lib/auth/types';

export function SessionSummary({
  auth,
  onLogout
}: {
  auth: AuthContext;
  onLogout: () => Promise<void>;
}) {
  if (!auth.session || !auth.user || !auth.role) {
    return null;
  }

  return (
    <div className="auth-session">
      <div className="auth-session__meta">
        <div className="auth-session__eyebrow">Current session</div>
        <div className="auth-session__name">{auth.user.name}</div>
        <div className="auth-session__email">{auth.user.email}</div>
      </div>

      <div className="auth-session__chips">
        <Badge tone={auth.role === 'admin' ? 'accent' : auth.role === 'reviewer' ? 'warning' : 'neutral'}>
          {auth.role}
        </Badge>
        <Badge tone="success">Signed in</Badge>
        <Badge tone="neutral">Hidden only</Badge>
      </div>

      <form action={onLogout}>
        <button className="button button--ghost auth-session__logout" type="submit">
          Sign out
        </button>
      </form>
    </div>
  );
}
