/**
 * Analyst feedback — what an alert turned out to be.
 *
 * A verdict is not the same thing as an alert's status. The status says
 * where the alert sits in the queue; the verdict says what the person
 * actually did, and it is the only thing the system learns from.
 */

export type Verdict =
  | 'CONFIRMED_THREAT'
  | 'POLICY_VIOLATION'
  | 'BENIGN'
  | 'INCONCLUSIVE';

export interface VerdictEvidence {
  source: string;
  severity: string;
  risk_score: number | null;
  priority: number | null;
  model_version: string;
  feature_version: string;
  detectors: string[];
  categories: string[];
}

export interface AnalystVerdict {
  id: string;
  alert_id: string;
  subject_user_id: string;
  subject_day: string;
  verdict: Verdict;
  rationale: string;
  decided_by: string;
  decided_at: string;
  is_current: boolean;
  training_label: boolean | null;
  evidence: VerdictEvidence;
}

export interface AlertVerdicts {
  current: AnalystVerdict | null;
  history: AnalystVerdict[];
}

export interface VerdictRequest {
  verdict: Verdict;
  rationale: string;
}

export interface VerdictStats {
  total: number;
  counts: Record<string, number>;
  /** Share of decisively judged alerts that were real. Null until one exists. */
  precision: number | null;
  trainable: number;
  threats: number;
  benign: number;
}
