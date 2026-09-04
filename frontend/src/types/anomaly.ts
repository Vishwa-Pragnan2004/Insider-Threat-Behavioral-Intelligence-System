/**
 * ITBIS — Anomaly Types
 * Aligned with backend app/modules/anomaly/application/dtos.py
 */

export type { RiskLevel, AnomalyPrediction } from './index';

export interface BehavioralDeviation {
  feature: string;
  value: number;
  baseline_mean: number;
  baseline_std: number;
  zscore: number;
}

export interface AnomalyResult {
  id: string;
  user_id: string;
  source_dataset: string;
  window: string;
  window_start: string;
  window_end: string;
  model_version: string;
  feature_version: string;
  prediction: string;
  raw_anomaly_score: number;
  risk_score: number;
  risk_level: string;
  baseline_source: string;
  top_behavioral_deviations: BehavioralDeviation[];
  created_at: string;
}

export interface AnomalyResultListResponse {
  results: AnomalyResult[];
  count: number;
}

export interface AnomalyDetectRequest {
  user_id?: string | null;
  start: string;
  end: string;
  source_dataset?: string;
  window?: string;
}

export interface AnomalyDetectResponse {
  results: AnomalyResult[];
  count: number;
  risk_levels: Record<string, number>;
}

export interface ModelInfoResponse {
  artifact_path: string;
  model_version: string;
  feature_version: string;
  feature_columns: string[];
  z_feature_columns: string[];
  model_features: string[];
  n_features: number;
  score_low: number;
  score_high: number;
  phase4_feature_compatible: boolean;
}
