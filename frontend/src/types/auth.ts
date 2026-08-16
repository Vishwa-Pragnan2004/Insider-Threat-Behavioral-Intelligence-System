/**
 * Authentication Types
 *
 * These interfaces match the expected Django REST Framework
 * authentication API contracts (TokenObtainPair, User serializer).
 */

/** Credentials sent to POST /api/v1/auth/login/ */
export interface LoginCredentials {
  email: string;
  password: string;
}

/** Response from POST /api/v1/auth/login/ */
export interface LoginResponse {
  access: string;   // JWT access token
  refresh: string;  // JWT refresh token
  user: User;
}

/** User profile — from GET /api/v1/auth/me/ */
export interface User {
  id: number;
  email: string;
  first_name: string;
  last_name: string;
  role: UserRole;
  avatar_url: string | null;
  is_active: boolean;
  date_joined: string;  // ISO 8601
}

/** User roles matching Django's group-based permissions */
export type UserRole = 'admin' | 'manager' | 'analyst' | 'viewer';

/** Auth state stored in the app */
export interface AuthState {
  user: User | null;
  accessToken: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
}
