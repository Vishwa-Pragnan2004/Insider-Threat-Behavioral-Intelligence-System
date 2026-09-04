/**
 * Report Service
 * All calls use the canonical apiClient with auto token attachment.
 */
import { apiClient } from '../services/apiClient';

export interface ReportParams {
  start?: string;
  end?: string;
  status?: string;
  severity?: string;
}

export async function exportAlertsCsv(params: ReportParams = {}): Promise<Blob> {
  const response = await apiClient.get('/reports/alerts/export', {
    params,
    responseType: 'blob',
  });
  return response.data;
}

export async function exportInvestigationsCsv(params: ReportParams = {}): Promise<Blob> {
  const response = await apiClient.get('/reports/investigations/export', {
    params,
    responseType: 'blob',
  });
  return response.data;
}
