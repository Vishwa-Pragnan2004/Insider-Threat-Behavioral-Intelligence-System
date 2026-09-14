/**
 * Role dashboard types.
 *
 * Mirror GET /api/v1/dashboards/{analyst,soc,manager}.
 */
import type { ActivityEvent, ActivitySummary } from './activity';

export type SeverityCounts = { LOW: number; MEDIUM: number; HIGH: number; CRITICAL: number };
export type InvestigationStatusCounts = {
  OPEN: number;
  IN_PROGRESS: number;
  RESOLVED: number;
  CLOSED: number;
};

export interface AlertBrief {
  id: string;
  title: string;
  user_id: string;
  severity: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  status: string;
  risk_score: number;
  created_at: string;
}

export interface InvestigationBrief {
  id: string;
  title: string;
  severity: string;
  status: 'OPEN' | 'IN_PROGRESS' | 'RESOLVED' | 'CLOSED';
  assigned_to: string | null;
  related_user_ids: string[];
  created_at: string;
  updated_at: string;
}

export interface UserRisk {
  user_id: string;
  latest_risk_score: number;
  max_risk_score: number;
  risk_level: string;
  anomalies: number;
  results: number;
  last_scored_at: string;
  /** 'global' means the user is still in their learning period. */
  baseline_source: 'personal' | 'global';
}

// ─── Security Analyst ─────────────────────────────────────────

export interface IncidentSummary {
  id: string;
  title: string;
  severity: string;
  status: string;
  resolution: string | null;
  closed_at: string | null;
  related_user_ids: string[];
}

export interface AnalystDashboard {
  generated_at: string;
  threat_alerts: {
    open_total: number;
    open_by_severity: SeverityCounts;
    new_last_24h: number;
    recent: AlertBrief[];
  };
  /** Sorted by max_risk_score desc, at most 10 users. */
  insider_risk: { window_days: number; users: UserRisk[] };
  investigation_queue: {
    counts_by_status: InvestigationStatusCounts;
    assigned_to_me: InvestigationBrief[];
    unassigned: InvestigationBrief[];
  };
  incident_summaries: {
    window_days: number;
    resolved: number;
    false_positives: number;
    recent: IncidentSummary[];
  };
}

// ─── SOC Operations ───────────────────────────────────────────

export interface AnomalyBrief {
  id: string;
  user_id: string;
  window_start: string;
  risk_score: number;
  risk_level: string;
  prediction: 'normal' | 'anomaly';
  baseline_source: string;
  top_deviation: string | null;
}

export interface SocDashboard {
  generated_at: string;
  /** 24h window; recent holds at most 15 events. */
  security_events: ActivitySummary & { recent: ActivityEvent[] };
  behavioral_anomalies: {
    window_days: number;
    results: number;
    anomalies: number;
    by_risk_level: SeverityCounts;
    recent: AnomalyBrief[];
  };
  active_investigations: { counts_by_status: InvestigationStatusCounts; items: InvestigationBrief[] };
  threat_intelligence: {
    window_days: number;
    note: string;
    indicators: { indicator: string; count: number; last_seen: string }[];
    external_destinations: { destination: string; count: number; users: number }[];
    pipeline: {
      scheduler_enabled: boolean;
      running: boolean;
      last_success_at: string | null;
      next_run_at: string | null;
      last_error: string | null;
    };
  };
}

// ─── Security Manager ─────────────────────────────────────────

export interface RiskTrendPoint {
  date: string;
  avg_risk_score: number | null;
  max_risk_score: number | null;
  anomalies: number;
  alerts_created: number;
}

export interface ManagerDashboard {
  generated_at: string;
  risk_posture: {
    monitored_users: number;
    baselined_users: number;
    learning_users: number;
    high_risk_users: number;
    org_risk_index: number | null;
    open_critical_alerts: number;
    open_investigations: number;
  };
  risk_trends: { days: number; series: RiskTrendPoint[] };
  insider_threat_report: {
    window_days: number;
    top_users: UserRisk[];
    alerts_by_severity: SeverityCounts;
    investigations_by_status: InvestigationStatusCounts;
  };
  compliance: {
    window_days: number;
    alerts_total: number;
    triaged_pct: number | null;
    mean_hours_to_acknowledge: number | null;
    mean_hours_to_resolve: number | null;
    critical_sla_hours: number;
    critical_within_sla_pct: number | null;
    investigations_closed_pct: number | null;
    devices_enrolled: number;
    devices_reporting_24h: number;
    agent_coverage_pct: number | null;
    admin_actions: number;
  };
}
