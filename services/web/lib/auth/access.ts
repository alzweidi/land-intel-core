import { roleIsAtLeast } from './session';
import type { AppRole } from './types';

export function getDefaultLandingPath(role: AppRole): string {
  if (role === 'admin') {
    return '/admin/health';
  }

  if (role === 'reviewer') {
    return '/review-queue';
  }

  return '/listings';
}

export function canAccessPath(role: AppRole, pathname: string): boolean {
  if (pathname.startsWith('/admin')) {
    return role === 'admin';
  }

  if (pathname.startsWith('/review-queue')) {
    return roleIsAtLeast(role, 'reviewer');
  }

  return true;
}
