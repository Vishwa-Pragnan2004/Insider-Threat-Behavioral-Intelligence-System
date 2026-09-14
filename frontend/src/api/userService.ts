/**
 * User & role administration service.
 */
import axios from 'axios';
import { apiClient } from '../services/apiClient';
import type {
  AccessRequest,
  AccessRequestListResponse,
  AccessRequestStatus,
  ManagedUser,
  RoleInfo,
  RoleName,
  UserListParams,
  UserListResponse,
} from '../types/users';

export async function listUsers(params: UserListParams = {}): Promise<UserListResponse> {
  const { data } = await apiClient.get<UserListResponse>('/users', { params });
  return data;
}

export interface CreateUserRequest {
  username: string;
  email: string;
  full_name: string;
  password: string;
  roles: RoleName[];
}

/** 409 on a duplicate username/email; 422 on a weak password or unknown role. */
export async function createUser(body: CreateUserRequest): Promise<ManagedUser> {
  const { data } = await apiClient.post<ManagedUser>('/users', body);
  return data;
}

export async function listRoles(): Promise<RoleInfo[]> {
  const { data } = await apiClient.get<RoleInfo[]>('/users/roles');
  return data;
}

export async function setUserRoles(userId: string, roles: RoleName[]): Promise<ManagedUser> {
  const { data } = await apiClient.put<ManagedUser>(`/users/${userId}/roles`, { roles });
  return data;
}

export async function disableUser(userId: string): Promise<ManagedUser> {
  const { data } = await apiClient.post<ManagedUser>(`/users/${userId}/disable`);
  return data;
}

export async function enableUser(userId: string): Promise<ManagedUser> {
  const { data } = await apiClient.post<ManagedUser>(`/users/${userId}/enable`);
  return data;
}

/** The backend's own explanation (e.g. "You can't disable your own account."), if it gave one. */
export function apiErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
      return detail.map((item) => item?.msg ?? String(item)).join('; ');
    }
    return error.message;
  }
  return error instanceof Error ? error.message : 'Something went wrong.';
}

// ─── Access requests ─────────────────────────────────────────

/** Newest first. Omit status for all requests. Needs users:read. */
export async function listAccessRequests(
  status?: AccessRequestStatus,
): Promise<AccessRequestListResponse> {
  const { data } = await apiClient.get<AccessRequestListResponse>('/users/access-requests', {
    params: status ? { status } : {},
  });
  return data;
}

/** 409 if the request was already decided. Needs users:update. */
export async function approveAccessRequest(id: string, roles: RoleName[]): Promise<AccessRequest> {
  const { data } = await apiClient.post<AccessRequest>(`/users/access-requests/${id}/approve`, { roles });
  return data;
}

/** 409 if the request was already decided. Needs users:update. */
export async function rejectAccessRequest(id: string, note?: string): Promise<AccessRequest> {
  const { data } = await apiClient.post<AccessRequest>(
    `/users/access-requests/${id}/reject`,
    note ? { note } : {},
  );
  return data;
}
