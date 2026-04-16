"use client";

import Link from 'next/link';
import { usePathname } from 'next/navigation';

import { navGroups } from '@/lib/navigation';
import type { AppRole } from '@/lib/auth/types';

function isActivePath(pathname: string, href: string): boolean {
  if (href === '/') {
    return pathname === '/';
  }

  return pathname === href || pathname.startsWith(`${href}/`);
}

const roleOrder: Record<AppRole, number> = {
  analyst: 0,
  reviewer: 1,
  admin: 2
};

export function SidebarNav({ role, onNavigate }: { role: AppRole; onNavigate?: () => void }) {
  const pathname = usePathname();

  return (
    <nav className="sidebar-nav" aria-label="Primary">
      {navGroups.map((group) => (
        <div key={group.title} className="nav-group">
          <div className="nav-group__title">{group.title}</div>
          <div className="nav-group__items">
            {group.items
              .filter((item) => !item.requiredRole || roleOrder[role] >= roleOrder[item.requiredRole])
              .map((item) => {
              const active = isActivePath(pathname, item.href);
              return (
                <Link
                  className={active ? 'nav-link nav-link--active' : 'nav-link'}
                  href={item.href}
                  key={item.href}
                  onClick={onNavigate}
                  aria-current={active ? 'page' : undefined}
                >
                  <span className="nav-link__title">{item.label}</span>
                  <span className="nav-link__desc">{item.description}</span>
                </Link>
              );
            })}
          </div>
        </div>
      ))}
    </nav>
  );
}
