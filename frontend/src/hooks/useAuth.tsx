/**
 * Authentication Hook & Context
 *
 * Provides authentication state and actions to all components.
 *
 * Startup flow:
 *   1. If itbis_access_token exists, call GET /auth/me to verify the token
 *   2. If /me succeeds → set authenticated user
 *   3. If /me fails (401) → apiClient interceptor tries refresh automatically
 *      - If refresh succeeds → interceptor retries /me and this useEffect sees success
 *      - If refresh fails → interceptor calls onAuthReset → clear state
 *   4. If no token exists → finish loading immediately (unauthenticated)
 *
 * Login flow:
 *   1. POST /auth/login → receive tokens
 *   2. Store tokens in localStorage
 *   3. Fetch user via GET /auth/me
 *   4. Set authenticated state
 *
 * Logout flow:
 *   1. POST /auth/logout (best-effort)
 *   2. Clear tokens from localStorage
 *   3. Clear user state
 */

import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  useRef,
  type ReactNode,
} from 'react';
import type { User, LoginCredentials, AuthState } from '../types/auth';
import * as authService from '../api/authService';
import { TOKEN_KEYS, setAuthResetHandler } from '../services/apiClient';

// ─── Context ─────────────────────────────────────────────────

interface AuthContextType extends AuthState {
  login: (credentials: LoginCredentials) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

// ─── Provider ────────────────────────────────────────────────

interface AuthProviderProps {
  children: ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const isResetRef = useRef(false);

  // Register the reset handler so the Axios interceptor can trigger logout
  useEffect(() => {
    setAuthResetHandler(() => {
      if (!isResetRef.current) {
        isResetRef.current = true;
        _clearAuth();
      }
    });
  }, []);

  const _clearAuth = useCallback(() => {
    localStorage.removeItem(TOKEN_KEYS.access);
    localStorage.removeItem(TOKEN_KEYS.refresh);
    setUser(null);
    setIsLoading(false);
  }, []);

  // ─── Startup: verify stored token ───────────────────────────
  useEffect(() => {
    const storedToken = localStorage.getItem(TOKEN_KEYS.access);

    if (!storedToken) {
      setIsLoading(false);
      return;
    }

    authService
      .getCurrentUser()
      .then((u) => setUser(u))
      .catch(() => {
        // Token invalid and refresh failed or no refresh token — stay unauthenticated
        _clearAuth();
      })
      .finally(() => {
        if (!isResetRef.current) setIsLoading(false);
      });
  }, [_clearAuth]);

  // ─── Login ──────────────────────────────────────────────────
  const login = useCallback(async (credentials: LoginCredentials) => {
    setIsLoading(true);
    try {
      const tokens = await authService.login(credentials);
      localStorage.setItem(TOKEN_KEYS.access, tokens.access_token);
      localStorage.setItem(TOKEN_KEYS.refresh, tokens.refresh_token);
      const u = await authService.getCurrentUser();
      setUser(u);
    } finally {
      setIsLoading(false);
    }
  }, []);

  // ─── Logout ─────────────────────────────────────────────────
  const logout = useCallback(async () => {
    setIsLoading(true);
    try {
      await authService.logout();
    } finally {
      localStorage.removeItem(TOKEN_KEYS.access);
      localStorage.removeItem(TOKEN_KEYS.refresh);
      setUser(null);
      setIsLoading(false);
    }
  }, []);

  // ─── Reset handler calls this after logout to finish loading ─
  const finishReset = useCallback(() => {
    isResetRef.current = false;
    setIsLoading(false);
  }, []);

  // Re-enable loading state after reset completes
  useEffect(() => {
    if (isResetRef.current) {
      finishReset();
    }
  }, [user, finishReset]);

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: !!user,
        isLoading,
        login,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

// ─── Hook ─────────────────────────────────────────────────────

export function useAuth(): AuthContextType {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider');
  return ctx;
}
