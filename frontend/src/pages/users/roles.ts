import type { RoleName } from '../../types/users';

/** Display names and chip colours for the backend's built-in roles. */
export const ROLE_LABELS: Record<RoleName, string> = {
  ADMIN: 'Administrator',
  SECURITY_ANALYST: 'Security Analyst',
  SOC_ENGINEER: 'SOC Engineer',
  SECURITY_MANAGER: 'Security Manager',
  INVESTIGATOR: 'Investigator',
  VIEWER: 'Viewer',
};

export const ROLE_COLORS: Record<RoleName, 'error' | 'warning' | 'info' | 'success' | 'secondary' | 'default'> = {
  ADMIN: 'error',
  SECURITY_ANALYST: 'warning',
  SOC_ENGINEER: 'secondary',
  SECURITY_MANAGER: 'success',
  INVESTIGATOR: 'info',
  VIEWER: 'default',
};

export const ROLE_NAMES = Object.keys(ROLE_LABELS) as RoleName[];
