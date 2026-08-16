import type { LoginCredentials, LoginResponse } from '../types/auth';
import { mockUser, mockTokens } from '../mocks/userData';
import { simulateDelay } from './axiosInstance';

/**
 * Authentication Service
 *
 * Handles login, logout, and token management.
 * Currently uses mock data; when Django backend is ready, replace
 * the mock implementations with real Axios calls.
 */

/**
 * Log in with email and password.
 *
 * Mock: Accepts any email that looks valid + any password with 4+ characters.
 * Real: POST /api/v1/auth/login/ with credentials.
 */
export const login = async (credentials: LoginCredentials): Promise<LoginResponse> => {
  // Simulate network delay
  await simulateDelay(800);

  // --- Mock validation ---
  // In production, the Django backend would validate credentials
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  if (!emailRegex.test(credentials.email)) {
    throw new Error('Please enter a valid email address.');
  }
  if (credentials.password.length < 4) {
    throw new Error('Invalid credentials. Please try again.');
  }

  // --- Mock success response ---
  // When backend is ready, replace with:
  // const response = await axiosInstance.post('/auth/login/', credentials);
  // return response.data;
  return {
    access: mockTokens.access,
    refresh: mockTokens.refresh,
    user: mockUser,
  };
};

/**
 * Log out the current user.
 *
 * Mock: Just clears local storage.
 * Real: POST /api/v1/auth/logout/ to invalidate the refresh token.
 */
export const logout = async (): Promise<void> => {
  await simulateDelay(200);

  // When backend is ready, replace with:
  // await axiosInstance.post('/auth/logout/', { refresh: localStorage.getItem('refresh_token') });
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
};

/**
 * Get current user profile.
 *
 * Mock: Returns the mock user.
 * Real: GET /api/v1/auth/me/
 */
export const getCurrentUser = async (): Promise<LoginResponse['user']> => {
  await simulateDelay(300);

  // When backend is ready, replace with:
  // const response = await axiosInstance.get('/auth/me/');
  // return response.data;
  return mockUser;
};
