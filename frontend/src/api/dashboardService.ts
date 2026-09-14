/**
 * Dashboard Service
 * Role-specific dashboard aggregates, each computed server-side in one call.
 */
import { apiClient } from '../services/apiClient';
import type { AnalystDashboard, ManagerDashboard, SocDashboard } from '../types/dashboards';

export async function getAnalystDashboard(): Promise<AnalystDashboard> {
  const { data } = await apiClient.get<AnalystDashboard>('/dashboards/analyst');
  return data;
}

export async function getSocDashboard(): Promise<SocDashboard> {
  const { data } = await apiClient.get<SocDashboard>('/dashboards/soc');
  return data;
}

export async function getManagerDashboard(): Promise<ManagerDashboard> {
  const { data } = await apiClient.get<ManagerDashboard>('/dashboards/manager');
  return data;
}
