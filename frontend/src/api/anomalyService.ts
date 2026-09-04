/**
 * Anomaly Service
 * All calls use the canonical apiClient with auto token attachment.
 */
import { apiClient } from '../services/apiClient';
import type {
  AnomalyResult,
  AnomalyResultListResponse,
  AnomalyDetectRequest,
  AnomalyDetectResponse,
  ModelInfoResponse,
} from '../types/anomaly';

export async function listAnomalyResults(params: {
  risk_level?: string;
  prediction?: string;
  limit?: number;
} = {}): Promise<AnomalyResultListResponse> {
  const { data } = await apiClient.get<AnomalyResultListResponse>('/anomaly/results', { params });
  return data;
}

export async function getAnomalyResult(resultId: string): Promise<AnomalyResult> {
  const { data } = await apiClient.get<AnomalyResult>(`/anomaly/results/${resultId}`);
  return data;
}

export async function getUserAnomalyResults(userId: string, params: {
  start?: string;
  end?: string;
  risk_level?: string;
  limit?: number;
} = {}): Promise<AnomalyResultListResponse> {
  const { data } = await apiClient.get<AnomalyResultListResponse>(`/anomaly/users/${userId}/results`, { params });
  return data;
}

export async function runDetection(body: AnomalyDetectRequest): Promise<AnomalyDetectResponse> {
  const { data } = await apiClient.post<AnomalyDetectResponse>('/anomaly/detect', body);
  return data;
}

export async function getModelInfo(): Promise<ModelInfoResponse> {
  const { data } = await apiClient.get<ModelInfoResponse>('/anomaly/model-info');
  return data;
}
