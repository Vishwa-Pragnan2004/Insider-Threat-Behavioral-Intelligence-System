/**
 * User & role administration types.
 *
 * Mirror backend/app/modules/users/presentation/router.py.
 */

export type RoleName =
  | 'ADMIN'
  | 'SECURITY_ANALYST'
  | 'SOC_ENGINEER'
  | 'SECURITY_MANAGER'
  | 'INVESTIGATOR'
  | 'VIEWER';

/** GET /api/v1/users, GET /api/v1/users/{id} */
export interface ManagedUser {
  id: string;
  username: string;
  email: string;
  full_name: string;
  roles: RoleName[];
  permissions: string[];
  is_active: boolean;
  is_superadmin: boolean;
  created_at: string;
  last_login_at: string | null;
}

export interface UserListResponse {
  users: ManagedUser[];
  total: number;
  offset: number;
  limit: number;
}

export interface UserListParams {
  search?: string;
  role?: RoleName;
  is_active?: boolean;
  offset?: number;
  limit?: number;
}

/** GET /api/v1/users/roles */
export interface RoleInfo {
  name: RoleName;
  permissions: string[];
}

// ─── Access requests ─────────────────────────────────────────

/** Roles a person may ask for themselves; ADMIN is only ever granted. */
export type RequestableRole = Exclude<RoleName, 'ADMIN'>;

export type AccessRequestStatus = 'PENDING' | 'APPROVED' | 'REJECTED';

/** POST /api/v1/auth/access-requests (public) */
export interface AccessRequestCreate {
  username: string;
  email: string;
  full_name: string;
  password: string;
  requested_role: RequestableRole;
  reason: string;
}

export interface AccessRequestSubmitted {
  id: string;
  status: 'PENDING';
  message: string;
}

/** GET /api/v1/users/access-requests */
export interface AccessRequest {
  id: string;
  user_id: string;
  username: string;
  email: string;
  full_name: string;
  requested_role: RequestableRole;
  reason: string;
  status: AccessRequestStatus;
  created_at: string;
  decided_at: string | null;
  /** Username of the administrator who decided. */
  decided_by: string | null;
  decision_note: string | null;
  /** Empty until approved. */
  granted_roles: RoleName[];
}

export interface AccessRequestListResponse {
  requests: AccessRequest[];
  total: number;
  pending: number;
}
