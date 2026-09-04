/**
 * ITBIS — Global TypeScript Type Definitions
 * Core types used across all frontend modules.
 */

// ─── Risk Levels (from anomaly domain) ─────────────────────────
export type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

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

// ─── User / Auth Types ──────────────────────────────────────────
export type { User } from './auth';

// ─── Alert Types (from alerts module) ─────────────────────────
export type AlertSeverity = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

export type AlertStatus =
  | 'OPEN'
  | 'ACKNOWLEDGED'
  | 'IN_PROGRESS'
  | 'RESOLVED'
  | 'FALSE_POSITIVE';

// ─── Anomaly Types (from anomaly domain) ───────────────────────
export type AnomalyPrediction = 'NORMAL' | 'ANOMALY';

// ─── Investigation Types (from investigations module) ───────────
export type InvestigationStatus = 'OPEN' | 'IN_PROGRESS' | 'RESOLVED' | 'CLOSED';

// ─── Event Types (from activity module) ───────────────────────
export type EventType =
  | 'logon' | 'logoff' | 'logon_failed'
  | 'file_read' | 'file_write' | 'file_delete' | 'file_copy'
  | 'usb_insert' | 'usb_remove' | 'usb_file_copy'
  | 'email_sent' | 'email_external'
  | 'http_request' | 'http_upload'
  | 'privilege_change'
  | 'unknown';
