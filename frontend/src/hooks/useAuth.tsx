import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import type { User, AuthState, LoginCredentials } from '../types/auth';
import * as authService from '../api/authService';

/**
 * Authentication Hook & Context
 *
 * Provides authentication state and actions (login, logout) to all
 * components via React Context. Uses localStorage to persist the
 * login state across page refreshes.
 *
 * Usage:
 *   const { user, isAuthenticated, login, logout } = useAuth();
 */

// ─── Context Definition ────────────────────────────────────────

interface AuthContextType extends AuthState {
  login: (credentials: LoginCredentials) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

// ─── Auth Provider Component ───────────────────────────────────

interface AuthProviderProps {
  children: ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps) {
  const [user, setUser] = useState<User | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true); // True while checking stored auth

  // Check for existing auth on mount (page refresh persistence)
  useEffect(() => {
    const storedToken = localStorage.getItem('access_token');
    const storedUser = localStorage.getItem('user');

    if (storedToken && storedUser) {
      try {
        setAccessToken(storedToken);
        setUser(JSON.parse(storedUser));
      } catch {
        // If stored data is corrupted, clear it
        localStorage.removeItem('access_token');
        localStorage.removeItem('user');
      }
    }
    setIsLoading(false);
  }, []);

  // Login: call auth service, store tokens, update state
  const login = useCallback(async (credentials: LoginCredentials) => {
    const response = await authService.login(credentials);

    // Persist to localStorage
    localStorage.setItem('access_token', response.access);
    localStorage.setItem('refresh_token', response.refresh);
    localStorage.setItem('user', JSON.stringify(response.user));

    // Update React state
    setAccessToken(response.access);
    setUser(response.user);
  }, []);

  // Logout: clear everything
  const logout = useCallback(async () => {
    await authService.logout();
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('user');
    setAccessToken(null);
    setUser(null);
  }, []);

  const value: AuthContextType = {
    user,
    accessToken,
    isAuthenticated: !!user && !!accessToken,
    isLoading,
    login,
    logout,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// ─── Hook ──────────────────────────────────────────────────────

/**
 * Custom hook to access authentication state and actions.
 * Must be used inside an <AuthProvider>.
 */
export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
