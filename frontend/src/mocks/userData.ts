import type { User } from '../types/auth';

/**
 * Mock User Data
 *
 * Simulates the user that would be returned by Django REST Framework
 * after successful JWT authentication.
 */
export const mockUser: User = {
  id: 1,
  email: 'sarah.chen@freshtrack.io',
  first_name: 'Sarah',
  last_name: 'Chen',
  role: 'admin',
  avatar_url: null,
  is_active: true,
  date_joined: '2025-03-15T09:00:00Z',
};

/**
 * Mock JWT tokens.
 * In production, these would come from Django's TokenObtainPairView.
 */
export const mockTokens = {
  access: 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.mock-access-token',
  refresh: 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.mock-refresh-token',
};
