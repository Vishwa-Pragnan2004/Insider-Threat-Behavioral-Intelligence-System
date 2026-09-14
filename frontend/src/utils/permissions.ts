/**
 * Permission helpers
 *
 * One place for "may this user do X?" so the sidebar, route guards and pages
 * agree. Superadmins hold every permission implicitly.
 */
import type { User } from '../types/auth';

export function hasPermission(user: User | null | undefined, permission: string): boolean {
  return !!user && (user.is_superadmin || user.permissions.includes(permission));
}

/** Role dashboards, in the order they appear in the sidebar. */
export const DASHBOARD_ROUTES = [
  { permission: 'dashboard:analyst', path: '/dashboards/analyst' },
  { permission: 'dashboard:soc', path: '/dashboards/soc' },
  { permission: 'dashboard:manager', path: '/dashboards/manager' },
] as const;
