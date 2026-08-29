/**
 * ITBIS — Global TypeScript Type Definitions
 * Core types used across all frontend modules.
 */

// ─── Risk Levels ──────────────────────────────────────────────
export type RiskLevel = 'info' | 'low' | 'medium' | 'high' | 'critical';

// ─── Health / System Types ────────────────────────────────────
export interface HealthResponse {
  status: 'ok' | 'degraded' | 'error';
  service: string;
  version: string;
  environment: string;
  uptime_seconds: number;
}

export interface ServiceCheck {
  status: 'ok' | 'error';
  note?: string;
  latency_ms?: number;
}

export interface ReadinessResponse {
  status: 'ok' | 'degraded';
  service: string;
  version: string;
  checks: Record<string, ServiceCheck>;
}

export interface AppInfo {
  service: string;
  version: string;
  environment: string;
  description: string;
  api_version: string;
  modules: string[];
}

// ─── API Response Wrappers ────────────────────────────────────
export interface ApiResponse<T> {
  data: T;
  message?: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface ApiError {
  detail: string;
  code?: string;
  field?: string;
}

// ─── User / Auth Types (Placeholder — Phase 1) ───────────────
export interface User {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
}

export type UserRole =
  | 'superadmin'
  | 'security_manager'
  | 'soc_analyst'
  | 'soc_engineer'
  | 'viewer';

// ─── Event Types (Placeholder — Phase 3) ─────────────────────
export type EventType =
  | 'logon' | 'logoff' | 'logon_failed'
  | 'file_read' | 'file_write' | 'file_delete' | 'file_copy'
  | 'usb_insert' | 'usb_remove' | 'usb_file_copy'
  | 'email_sent' | 'email_external'
  | 'http_request' | 'http_upload'
  | 'privilege_change'
  | 'unknown';

// ─── Alert Types (Placeholder — Phase 8) ─────────────────────
export type AlertStatus = 'open' | 'acknowledged' | 'investigating' | 'resolved' | 'false_positive';
export type AlertSeverity = RiskLevel;
