"use client";

import Link from 'next/link';
import { usePathname } from 'next/navigation';

import { navGroups } from '@/lib/navigation';

function isActivePath(pathname: string, href: string): boolean {
  if (href === '/') {
    return pathname === '/';
  }

  return pathname === href || pathname.startsWith(`${href}/`);
}

export function SidebarNav() {
  const pathname = usePathname();

  return (
    <nav className="sidebar-nav" aria-label="Primary">
      {navGroups.map((group) => (
        <div key={group.title} className="nav-group">
          <div className="nav-group__title">{group.title}</div>
          <div className="nav-group__items">
            {group.items.map((item) => {
              const active = isActivePath(pathname, item.href);

              return (
                <Link
                  className={active ? 'nav-link nav-link--active' : 'nav-link'}
                  href={item.href}
                  key={item.href}
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
