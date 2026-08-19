/**
 * ITBIS — Axios API Client
 * Centralised HTTP client with interceptors and error handling.
 */

import axios, { AxiosError, AxiosResponse, InternalAxiosRequestConfig } from 'axios';
import type { ApiError } from '@/types';

// ─── Axios Instance ───────────────────────────────────────────
export const apiClient = axios.create({
  baseURL: '/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30_000,
});

// ─── Request Interceptor ──────────────────────────────────────
// Attach JWT access token to every request (Phase 1 will populate this)
apiClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = localStorage.getItem('itbis_access_token');
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// ─── Response Interceptor ─────────────────────────────────────
apiClient.interceptors.response.use(
  (response: AxiosResponse) => response,
  async (error: AxiosError<ApiError>) => {
    if (error.response?.status === 401) {
      // TODO (Phase 1): Attempt token refresh; redirect to login on failure
      localStorage.removeItem('itbis_access_token');
    }
    return Promise.reject(error);
  }
);

export default apiClient;
