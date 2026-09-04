/**
 * ITBIS — Alert Types
 * Aligned with backend app/modules/alerts/application/dtos.py
 */

export type { AlertSeverity, AlertStatus } from './index';
export type { RiskLevel } from './index';

export interface AlertDeviation {
  feature: string;
  value: number;
  baseline_mean: number;
  baseline_std: number;
  zscore: number;
}

export interface Alert {
  id: string;
  idempotency_key: string;
  anomaly_result_id: string;
  user_id: string;
  source_dataset: string;
  window: string;
  window_start: string;
  window_end: string;
  model_version: string;
  feature_version: string;
  title: string;
  description: string;
  risk_score: number;
  risk_level: string;
  severity: string;
  status: string;
  assigned_to: string | null;
  investigation_id: string | null;
  top_behavioral_deviations: AlertDeviation[];
  created_at: string;
  updated_at: string;
}

export interface AlertListResponse {
  alerts: Alert[];
  count: number;
  total: number;
  skip: number;
  limit: number;
}

export interface AlertListParams {
  status?: string;
  severity?: string;
  user_id?: string;
  assigned_to?: string;
  risk_level?: string;
  source_dataset?: string;
  investigation_id?: string;
  start?: string;
  end?: string;
  skip?: number;
  limit?: number;
}

export interface AlertAssignRequest {
  user_id: string;
}

export interface AlertStatusUpdateRequest {
  status: string;
}

export interface AlertGenerateRequest {
  start?: string;
  end?: string;
  user_id?: string;
  risk_level?: string;
  source_dataset?: string;
  limit?: number;
}

export interface AlertGenerateResponse {
  created: number;
  skipped_duplicates: number;
  skipped_below_threshold: number;
  total_processed: number;
}
