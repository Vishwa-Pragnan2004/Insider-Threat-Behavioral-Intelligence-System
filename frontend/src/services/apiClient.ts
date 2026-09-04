/**
 * ITBIS — Canonical Axios API Client
 *
 * Single Axios instance for all authenticated API communication.
 * - Attaches JWT access token to every request
 * - Handles 401 with automatic refresh-token rotation
 * - Single shared refresh promise prevents concurrent refresh races
 * - On refresh failure, calls the auth reset callback so the app can log out
 */

import axios from 'axios';

// ─── Token storage keys ───────────────────────────────────────
export const TOKEN_KEYS = {
  access: 'itbis_access_token',
  refresh: 'itbis_refresh_token',
} as const;

// ─── Auth reset callback type ────────────────────────────────
// Called when a refresh fails — the auth context uses this to log out
let _onAuthReset: (() => void) | null = null;

export function setAuthResetHandler(handler: () => void): void {
  _onAuthReset = handler;
}

// ─── Axios instance ─────────────────────────────────────────
export const apiClient = axios.create({
  baseURL: '/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30_000,
});

// ─── Refresh promise guard ──────────────────────────────────
let _refreshPromise: Promise<string | null> | null = null;

/**
 * Attempt token refresh. Returns the new access token on success,
 * null on failure. Only one refresh runs at a time.
 */
async function _doRefresh(): Promise<string | null> {
  const refreshToken = localStorage.getItem(TOKEN_KEYS.refresh);
  if (!refreshToken) return null;

  try {
    const response = await axios.post<{
      access_token: string;
      refresh_token: string;
      token_type: string;
      expires_in: number;
    }>('/api/v1/auth/refresh', { refresh_token: refreshToken });

    const { access_token, refresh_token } = response.data;
    localStorage.setItem(TOKEN_KEYS.access, access_token);
    localStorage.setItem(TOKEN_KEYS.refresh, refresh_token);
    return access_token;
  } catch {
    return null;
  }
}

function _getAccessToken(): string | null {
  return localStorage.getItem(TOKEN_KEYS.access);
}

// ─── Request interceptor ───────────────────────────────────
apiClient.interceptors.request.use(
  (config) => {
    const token = _getAccessToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// ─── Response interceptor ───────────────────────────────────
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    // Only handle 401 for authenticated requests, and only once
    if (
      error.response?.status !== 401 ||
      originalRequest._retry ||
      originalRequest.url?.includes('/auth/')
    ) {
      return Promise.reject(error);
    }

    originalRequest._retry = true;

    // Coalesce concurrent 401s into a single refresh
    if (!_refreshPromise) {
      _refreshPromise = _doRefresh().finally(() => {
        _refreshPromise = null;
      });
    }

    const newToken = await _refreshPromise;

    if (newToken) {
      // Retry original request with new token
      originalRequest.headers.Authorization = `Bearer ${newToken}`;
      return apiClient(originalRequest);
    }

    // Refresh failed — reset auth state and reject
    if (_onAuthReset) _onAuthReset();
    return Promise.reject(error);
  }
);

export default apiClient;
