/**
 * Activity (raw endpoint / CERT event) types.
 *
 * Mirror the /api/v1/activity/events endpoints.
 */

/** One normalized event as stored by the activity module. */
export interface ActivityEvent {
  id: string;
  event_id: string | null;
  event_type: string;
  timestamp: string;
  user_id: string;
  device_id: string | null;
  device_name: string | null;
  source_dataset: string;
  target_resource: string | null;
  target_type: string | null;
  action: string | null;
  result: string | null;
  ip_address: string | null;
  is_remote: boolean | null;
  risk_indicators: string[];
  tags: string[];
  enrichments: Record<string, unknown> | null;
  ingested_at: string | null;
}

/** GET /api/v1/activity/events */
export interface ActivityEventList {
  events: ActivityEvent[];
  total: number;
  skip: number;
  limit: number;
}

export interface ActivityEventParams {
  user_id?: string;
  event_type?: string;
  source_dataset?: string;
  device_id?: string;
  start?: string;
  end?: string;
  skip?: number;
  limit?: number;
}

/** GET /api/v1/activity/events/summary */
export interface ActivitySummary {
  window_hours: number;
  total: number;
  flagged: number;
  active_users: number;
  active_devices: number;
  by_event_type: Record<string, number>;
  by_source: Record<string, number>;
  /** Up to 10 users, busiest first. */
  top_users: { user_id: string; count: number }[];
  /** One bucket per hour, oldest first. */
  hourly: { hour: string; count: number }[];
}
