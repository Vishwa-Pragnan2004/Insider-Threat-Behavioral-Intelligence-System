/**
 * Analyst feedback service — recording and reading verdicts on alerts.
 */
import { apiClient } from '../services/apiClient';
import type { Alert } from '../types/alert';
import type {
  AlertVerdicts,
  AnalystVerdict,
  VerdictRequest,
  VerdictStats,
} from '../types/feedback';

export interface VerdictRecorded {
  verdict: AnalystVerdict;
  alert: Alert;
}

export async function recordVerdict(
  alertId: string,
  body: VerdictRequest,
): Promise<VerdictRecorded> {
  const { data } = await apiClient.post<VerdictRecorded>(
    `/feedback/alerts/${alertId}/verdict`,
    body,
  );
  return data;
}

export async function getAlertVerdicts(alertId: string): Promise<AlertVerdicts> {
  const { data } = await apiClient.get<AlertVerdicts>(`/feedback/alerts/${alertId}/verdict`);
  return data;
}

export async function getVerdictStats(since?: string): Promise<VerdictStats> {
  const { data } = await apiClient.get<VerdictStats>('/feedback/stats', {
    params: since ? { since } : undefined,
  });
  return data;
}
