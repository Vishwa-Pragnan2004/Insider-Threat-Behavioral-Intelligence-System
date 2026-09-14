/**
 * ITBIS — Insider Risk & Detection Types
 * Mirror GET /api/v1/detections/* and /api/v1/risk/*.
 */

export type DetectionEngine = 'behavioral' | 'access' | 'data_exfiltration' | 'privilege_abuse';

export interface DetectionCategory {
  category: string;
  label: string;
  engine: DetectionEngine;
  risk_component: string;
}

export interface Finding {
  id: string;
  user_id: string;
  day: string;
  category: string;
  category_label: string;
  engine: string;
  detector: string;
  /** 0–100 */
  severity: number;
  title: string;
  description: string;
  evidence: Record<string, unknown>;
  event_ids: string[];
  detector_version: string;
}

export interface FindingList {
  findings: Finding[];
  total: number;
  skip: number;
  limit: number;
}

export interface FindingListParams {
  user_id?: string;
  category?: string;
  engine?: string;
  start?: string;
  end?: string;
  min_severity?: number;
  skip?: number;
  limit?: number;
}

export type RiskBandLevel = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

export interface RiskModelComponent {
  component: string;
  label: string;
  weight: number;
}

export interface RiskModel {
  version: string;
  components: RiskModelComponent[];
  bands: { level: RiskBandLevel; min_score: number; max_score: number }[];
  alert_min_priority: number;
}

export type RiskComponentKey =
  | 'behavioral_anomalies'
  | 'privilege_misuse'
  | 'data_access_violations'
  | 'access_pattern_deviations'
  | 'historical_security_events';

export interface RiskSignal {
  label: string;
  component: string;
  component_label: string;
  category: string | null;
  severity: number;
  current_weight: number;
  /** YYYY-MM-DD */
  day: string;
  reference: string | null;
}

export interface EmployeeRisk {
  user_id: string;
  day: string;
  score: number;
  level: string;
  priority: number;
  trend: number | null;
  dominant_component: string | null;
  components: Record<string, number>;
  top_signals: RiskSignal[];
}

export interface EmployeeRiskList {
  since: string;
  employees: EmployeeRisk[];
}

export interface EmployeeRiskListParams {
  days?: number;
  limit?: number;
  min_priority?: number;
}

export interface EmployeeRiskDetail {
  user_id: string;
  latest: EmployeeRisk | null;
  /** Oldest first. */
  series: EmployeeRisk[];
  findings: Finding[];
}
