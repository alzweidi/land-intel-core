import type { ReactNode } from 'react';

import { Badge } from '@/components/ui';
import { SidebarNav } from '@/components/sidebar-nav';

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true">
            LI
          </div>
          <div className="brand-copy">
            <div className="brand-name">Land Intel</div>
            <div className="brand-subtitle">London-first internal shell</div>
          </div>
        </div>

        <div className="sidebar-ribbon">
          <Badge tone="accent">Phase 0 only</Badge>
          <span className="shell-note">No scoring, no enrichment, no geometry logic.</span>
        </div>

        <SidebarNav />

        <div className="sidebar-footer">
          <div className="sidebar-footer__label">Deployment posture</div>
          <div className="sidebar-footer__value">Next.js + TypeScript + Netlify-ready</div>
        </div>
      </aside>

      <div className="app-main">
        <div className="topbar">
          <div>
            <div className="topbar-kicker">Internal analyst shell</div>
            <div className="topbar-title">Runnable frontend scaffold</div>
          </div>
          <div className="topbar-badges">
            <Badge tone="success">Bootable</Badge>
            <Badge tone="warning">Stubbed data only</Badge>
          </div>
        </div>

        <main className="app-content">{children}</main>
      </div>
    </div>
  );
}
