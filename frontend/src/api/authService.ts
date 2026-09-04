/**
 * Authentication Service
 *
 * Real API calls to the FastAPI identity module.
 * All functions use the canonical apiClient which handles
 * automatic token attachment and 401-refresh.
 */

import axios from 'axios';
import type { LoginCredentials, TokenResponse, User } from '../types/auth';
import { TOKEN_KEYS } from '../services/apiClient';

// Direct axios instance for login (no token needed yet)
const _noAuthClient = axios.create({
  baseURL: '/api/v1',
  timeout: 30_000,
  headers: { 'Content-Type': 'application/json' },
});

/**
 * POST /api/v1/auth/login
 *
 * On success, caller must store the returned tokens in localStorage
 * using TOKEN_KEYS before any authenticated requests are made.
 */
export async function login(credentials: LoginCredentials): Promise<TokenResponse> {
  const response = await _noAuthClient.post<TokenResponse>('/auth/login', credentials);
  return response.data;
}

/**
 * POST /api/v1/auth/logout
 *
 * Calls the backend to revoke the refresh token.
 * Best-effort: failures are swallowed and the caller should
 * still clear local tokens.
 */
export async function logout(): Promise<void> {
  const refreshToken = localStorage.getItem(TOKEN_KEYS.refresh);
  if (!refreshToken) return;

  try {
    // Use direct axios so the 401 interceptor doesn't fire from this call
    await axios.post(
      '/api/v1/auth/logout',
      { refresh_token: refreshToken },
      {
        headers: {
          Authorization: `Bearer ${localStorage.getItem(TOKEN_KEYS.access) ?? ''}`,
          'Content-Type': 'application/json',
        },
      }
    );
  } catch {
    // best-effort: logout locally regardless
  }
}

/**
 * GET /api/v1/auth/me
 *
 * Returns the authenticated user profile.
 * apiClient attaches the access token and handles 401-refresh.
 */
export async function getCurrentUser(): Promise<User> {
  const { apiClient } = await import('../services/apiClient');
  const response = await apiClient.get<User>('/auth/me');
  return response.data;
}

export interface UpdateUserRequest {
  full_name?: string;
  email?: string;
}

/**
 * PATCH /api/v1/auth/me
 *
 * Updates the current user's profile.
 */
export async function updateCurrentUser(data: UpdateUserRequest): Promise<User> {
  const { apiClient } = await import('../services/apiClient');
  const response = await apiClient.patch<User>('/auth/me', data);
  return response.data;
}
