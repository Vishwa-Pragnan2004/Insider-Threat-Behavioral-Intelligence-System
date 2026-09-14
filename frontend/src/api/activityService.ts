/**
 * Activity Service
 * Raw endpoint / CERT events as ingested by the activity module.
 */
import { apiClient } from '../services/apiClient';
import type { ActivityEventList, ActivityEventParams, ActivitySummary } from '../types/activity';

export async function listActivityEvents(params: ActivityEventParams = {}): Promise<ActivityEventList> {
  const { data } = await apiClient.get<ActivityEventList>('/activity/events', { params });
  return data;
}

export async function getActivitySummary(hours = 24): Promise<ActivitySummary> {
  const { data } = await apiClient.get<ActivitySummary>('/activity/events/summary', {
    params: { hours },
  });
  return data;
}
