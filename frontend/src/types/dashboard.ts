/**
 * Dashboard Types
 *
 * Interfaces for the dashboard page data, matching the expected
 * Django REST Framework API responses for dashboard endpoints.
 */

// ─── KPI Summary ───────────────────────────────────────────────

/** Response from GET /api/v1/dashboard/summary/ */
export interface DashboardSummary {
  total_products: number;
  fresh_percentage: number;
  expiring_soon: number;
  active_alerts: number;
  // Trend compared to previous period (percentage change)
  total_products_trend: number;
  fresh_percentage_trend: number;
  expiring_soon_trend: number;
  active_alerts_trend: number;
}

// ─── Charts ────────────────────────────────────────────────────

/** Single data point for the freshness trend line chart */
export interface FreshnessTrendPoint {
  date: string;            // e.g. "Jul 01"
  average_score: number;   // 0–100
  min_score: number;
  max_score: number;
}

/** Category breakdown for the pie chart */
export interface CategoryDistribution {
  name: string;    // e.g. "Fresh", "Near Expiry", "Expired"
  value: number;   // count of products
  color: string;   // hex color for the chart segment
}

/** Products by category for the bar chart */
export interface ProductsByCategory {
  category: string;  // e.g. "Dairy", "Produce", "Meat"
  count: number;
  fresh: number;
  warning: number;
  expired: number;
}

// ─── Tables / Lists ────────────────────────────────────────────

/** Alert severity levels */
export type AlertSeverity = 'critical' | 'high' | 'medium' | 'low';

/** Alert status */
export type AlertStatus = 'new' | 'acknowledged' | 'resolved';

/** Recent alert shown on the dashboard */
export interface RecentAlert {
  id: number;
  severity: AlertSeverity;
  message: string;
  product_name: string;
  category: string;
  timestamp: string;       // ISO 8601
  status: AlertStatus;
}

/** Freshness status for products */
export type FreshnessStatus = 'fresh' | 'warning' | 'expired';

/** Product that is expiring soon, shown in the dashboard list */
export interface ExpiringProduct {
  id: number;
  name: string;
  category: string;
  freshness_score: number;  // 0–100
  status: FreshnessStatus;
  expiry_date: string;      // ISO 8601
  hours_remaining: number;
  storage_location: string;
}

// ─── Full Dashboard Response ───────────────────────────────────

/** Combined response from GET /api/v1/dashboard/ */
export interface DashboardData {
  summary: DashboardSummary;
  freshness_trend: FreshnessTrendPoint[];
  category_distribution: CategoryDistribution[];
  products_by_category: ProductsByCategory[];
  recent_alerts: RecentAlert[];
  expiring_products: ExpiringProduct[];
}
