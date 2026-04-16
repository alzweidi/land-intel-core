'use client';

import { usePathname } from 'next/navigation';
import type { ReactNode } from 'react';

import { Badge, DefinitionList, Panel, StatusChip } from '@/components/ui';
import { SidebarNav } from '@/components/sidebar-nav';
import { getRouteMeta } from '@/lib/navigation';
import type { AuthContext } from '@/lib/auth/types';

export function AppShell({
  children,
  auth,
  onLogout
}: {
  children: ReactNode;
  auth: AuthContext;
  onLogout: () => Promise<void>;
}) {
  const pathname = usePathname();
  const routeMeta = getRouteMeta(pathname);
  const role = auth.role ?? 'analyst';
  const user = auth.user;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true">
            LI
          </div>
          <div className="brand-copy">
            <div className="brand-name">Land Intel</div>
            <div className="brand-subtitle">Private London-first analyst workspace</div>
          </div>
        </div>

        <div className="sidebar-ribbon">
          <div className="pill-row">
            <Badge tone={role === 'admin' ? 'accent' : role === 'reviewer' ? 'warning' : 'neutral'}>
              {role}
            </Badge>
            <Badge tone="success">Signed in</Badge>
            <Badge tone="warning">Visible probability off</Badge>
          </div>
          <span className="shell-note">
            Listings, sites, scenarios, assessments, opportunities, review, and control-plane
            surfaces all run against the same local API. Hidden scoring stays non-speaking unless a
            scoped internal view is explicitly requested and permitted.
          </span>
        </div>

        <Panel
          eyebrow="Session"
          title="Current operator"
          compact
          note={<StatusChip value={role} tone="success" prefix="Role" />}
        >
          <DefinitionList
            compact
            items={[
              { label: 'Name', value: user?.name ?? 'Unavailable' },
              { label: 'Email', value: user?.email ?? 'Unavailable' },
              { label: 'Session', value: 'Signed cookie session' },
              { label: 'Expires', value: auth.session?.expiresAt ?? 'Unavailable' }
            ]}
          />
          <form action={onLogout} className="workspace-auth-shell__actions">
            <button className="button button--ghost" type="submit">
              Sign out
            </button>
          </form>
        </Panel>

        <SidebarNav role={role} />

        <div className="sidebar-footer">
          <div className="sidebar-footer__label">Workspace posture</div>
          <div className="sidebar-footer__value">Hidden-only by default</div>
          <div className="sidebar-footer__meta">
            Release visibility, incidents, overrides, and replay checks remain active safety rails.
          </div>
        </div>
      </aside>

      <div className="app-main">
        <div className="topbar">
          <div className="topbar__copy">
            <div className="topbar-kicker">{routeMeta.group}</div>
            <div className="topbar-title">{routeMeta.label}</div>
            <div className="topbar-summary">{routeMeta.description}</div>
          </div>
          <div className="topbar-badges">
            <StatusChip value={role} tone="success" prefix="Role" />
            <Badge tone="accent">Local live-data shell</Badge>
            <Badge tone="warning">Visible probability blocked</Badge>
          </div>
        </div>

        <main className="app-content">{children}</main>
      </div>
    </div>
  );
}
