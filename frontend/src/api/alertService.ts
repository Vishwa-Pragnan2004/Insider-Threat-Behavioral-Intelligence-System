/**
 * Alert Service
 * All calls use the canonical apiClient with auto token attachment.
 */
import { apiClient } from '../services/apiClient';
import type {
  Alert,
  AlertListResponse,
  AlertListParams,
  AlertAssignRequest,
  AlertStatusUpdateRequest,
  AlertGenerateRequest,
  AlertGenerateResponse,
} from '../types/alert';

export async function listAlerts(params: AlertListParams = {}): Promise<AlertListResponse> {
  const { data } = await apiClient.get<AlertListResponse>('/alerts/', { params });
  return data;
}

export async function getAlert(alertId: string): Promise<Alert> {
  const { data } = await apiClient.get<Alert>(`/alerts/${alertId}`);
  return data;
}

export async function acknowledgeAlert(alertId: string): Promise<Alert> {
  const { data } = await apiClient.post<Alert>(`/alerts/${alertId}/acknowledge`);
  return data;
}

export async function assignAlert(alertId: string, body: AlertAssignRequest): Promise<Alert> {
  const { data } = await apiClient.post<Alert>(`/alerts/${alertId}/assign`, body);
  return data;
}

export async function updateAlertStatus(alertId: string, body: AlertStatusUpdateRequest): Promise<Alert> {
  const { data } = await apiClient.post<Alert>(`/alerts/${alertId}/status`, body);
  return data;
}

export async function generateAlerts(body: AlertGenerateRequest = {}): Promise<AlertGenerateResponse> {
  const { data } = await apiClient.post<AlertGenerateResponse>('/alerts/generate', body);
  return data;
}
