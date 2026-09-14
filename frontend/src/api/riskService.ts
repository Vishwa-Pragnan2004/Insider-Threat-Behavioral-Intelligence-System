/**
 * Risk & Detection Service
 * Anomaly detection findings and the weighted insider risk scores.
 */
import { apiClient } from '../services/apiClient';
import type {
  DetectionCategory,
  EmployeeRiskDetail,
  EmployeeRiskList,
  EmployeeRiskListParams,
  FindingList,
  FindingListParams,
  RiskModel,
} from '../types/risk';

export async function listDetectionCategories(): Promise<DetectionCategory[]> {
  const { data } = await apiClient.get<DetectionCategory[]>('/detections/categories');
  return data;
}

export async function listFindings(params: FindingListParams = {}): Promise<FindingList> {
  const { data } = await apiClient.get<FindingList>('/detections/findings', { params });
  return data;
}

export async function getRiskModel(): Promise<RiskModel> {
  const { data } = await apiClient.get<RiskModel>('/risk/model');
  return data;
}

export async function listEmployeeRisk(params: EmployeeRiskListParams = {}): Promise<EmployeeRiskList> {
  const { data } = await apiClient.get<EmployeeRiskList>('/risk/employees', { params });
  return data;
}

/** user_id may contain a backslash (DOMAIN\user), so it is always encoded. */
export async function getEmployeeRisk(userId: string, days = 30): Promise<EmployeeRiskDetail> {
  const { data } = await apiClient.get<EmployeeRiskDetail>(
    `/risk/employees/${encodeURIComponent(userId)}`,
    { params: { days } },
  );
  return data;
}
