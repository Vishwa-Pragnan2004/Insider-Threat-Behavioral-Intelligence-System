/**
 * Authentication Types
 *
 * Exact TypeScript representations of the FastAPI identity module
 * Pydantic schemas (backend/app/modules/identity/presentation/schemas.py).
 */

// ─── Requests ─────────────────────────────────────────────────

/** POST /api/v1/auth/login — request body */
export interface LoginCredentials {
  email: string;
  password: string;
}

// ─── Responses ────────────────────────────────────────────────

/** POST /api/v1/auth/login and POST /api/v1/auth/refresh — response */
export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

/**
 * GET /api/v1/auth/me — response
 *
 * Matches UserProfileResponse exactly from the backend.
 */
export interface User {
  id: string;
  username: string;
  email: string;
  full_name: string;
  roles: string[];
  permissions: string[];
  is_superadmin: boolean;
}

// ─── Auth Context State ───────────────────────────────────────

/** Auth state managed by the AuthProvider */
export interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
}
