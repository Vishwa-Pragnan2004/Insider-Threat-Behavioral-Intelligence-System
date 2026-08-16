import type {
  DashboardSummary,
  FreshnessTrendPoint,
  CategoryDistribution,
  ProductsByCategory,
  RecentAlert,
  ExpiringProduct,
} from '../types/dashboard';

/**
 * Mock Dashboard Data
 *
 * Realistic food freshness monitoring data that simulates what a
 * Django REST Framework API would return for the dashboard page.
 */

// ─── KPI Summary ───────────────────────────────────────────────

export const mockSummary: DashboardSummary = {
  total_products: 1247,
  fresh_percentage: 84.3,
  expiring_soon: 38,
  active_alerts: 12,
  // Trends: positive = improvement, negative = decline
  total_products_trend: 5.2,
  fresh_percentage_trend: 2.1,
  expiring_soon_trend: -8.4,    // Negative is good — fewer expiring
  active_alerts_trend: -15.3,   // Negative is good — fewer alerts
};

// ─── Freshness Trend (Last 30 Days) ────────────────────────────

export const mockFreshnessTrend: FreshnessTrendPoint[] = [
  { date: 'Jun 25', average_score: 78, min_score: 45, max_score: 98 },
  { date: 'Jun 26', average_score: 76, min_score: 42, max_score: 97 },
  { date: 'Jun 27', average_score: 79, min_score: 48, max_score: 99 },
  { date: 'Jun 28', average_score: 81, min_score: 50, max_score: 98 },
  { date: 'Jun 29', average_score: 77, min_score: 44, max_score: 96 },
  { date: 'Jun 30', average_score: 74, min_score: 38, max_score: 95 },
  { date: 'Jul 01', average_score: 80, min_score: 52, max_score: 99 },
  { date: 'Jul 02', average_score: 82, min_score: 55, max_score: 98 },
  { date: 'Jul 03', average_score: 79, min_score: 46, max_score: 97 },
  { date: 'Jul 04', average_score: 83, min_score: 58, max_score: 99 },
  { date: 'Jul 05', average_score: 85, min_score: 60, max_score: 100 },
  { date: 'Jul 06', average_score: 82, min_score: 54, max_score: 98 },
  { date: 'Jul 07', average_score: 80, min_score: 50, max_score: 97 },
  { date: 'Jul 08', average_score: 78, min_score: 47, max_score: 96 },
  { date: 'Jul 09', average_score: 81, min_score: 53, max_score: 99 },
  { date: 'Jul 10', average_score: 84, min_score: 58, max_score: 100 },
  { date: 'Jul 11', average_score: 86, min_score: 62, max_score: 99 },
  { date: 'Jul 12', average_score: 83, min_score: 55, max_score: 98 },
  { date: 'Jul 13', average_score: 81, min_score: 52, max_score: 97 },
  { date: 'Jul 14', average_score: 85, min_score: 60, max_score: 100 },
  { date: 'Jul 15', average_score: 87, min_score: 65, max_score: 99 },
  { date: 'Jul 16', average_score: 84, min_score: 57, max_score: 98 },
  { date: 'Jul 17', average_score: 82, min_score: 54, max_score: 97 },
  { date: 'Jul 18', average_score: 86, min_score: 62, max_score: 100 },
  { date: 'Jul 19', average_score: 88, min_score: 66, max_score: 99 },
  { date: 'Jul 20', average_score: 85, min_score: 59, max_score: 98 },
  { date: 'Jul 21', average_score: 83, min_score: 55, max_score: 97 },
  { date: 'Jul 22', average_score: 87, min_score: 64, max_score: 100 },
  { date: 'Jul 23', average_score: 89, min_score: 68, max_score: 99 },
  { date: 'Jul 24', average_score: 86, min_score: 61, max_score: 98 },
];

// ─── Category Distribution (Pie Chart) ─────────────────────────

export const mockCategoryDistribution: CategoryDistribution[] = [
  { name: 'Fresh',       value: 847, color: '#10B981' },  // Green
  { name: 'Near Expiry', value: 263, color: '#F59E0B' },  // Amber
  { name: 'Expired',     value: 137, color: '#EF4444' },  // Red
];

// ─── Products by Category (Bar Chart) ──────────────────────────

export const mockProductsByCategory: ProductsByCategory[] = [
  { category: 'Dairy',       count: 245, fresh: 198, warning: 32, expired: 15 },
  { category: 'Produce',     count: 312, fresh: 240, warning: 48, expired: 24 },
  { category: 'Meat',        count: 178, fresh: 142, warning: 22, expired: 14 },
  { category: 'Bakery',      count: 156, fresh: 108, warning: 31, expired: 17 },
  { category: 'Seafood',     count: 98,  fresh: 72,  warning: 16, expired: 10 },
  { category: 'Beverages',   count: 134, fresh: 120, warning: 10, expired: 4 },
  { category: 'Frozen',      count: 124, fresh: 112, warning: 8,  expired: 4 },
];

// ─── Recent Alerts ─────────────────────────────────────────────

export const mockRecentAlerts: RecentAlert[] = [
  {
    id: 1,
    severity: 'critical',
    message: 'Temperature breach in Cold Storage Unit B — dairy products at risk',
    product_name: 'Organic Whole Milk',
    category: 'Dairy',
    timestamp: '2026-07-24T14:32:00Z',
    status: 'new',
  },
  {
    id: 2,
    severity: 'high',
    message: 'Batch #BK-2847 freshness score dropped below 30%',
    product_name: 'Sourdough Loaf',
    category: 'Bakery',
    timestamp: '2026-07-24T13:15:00Z',
    status: 'new',
  },
  {
    id: 3,
    severity: 'high',
    message: 'Seafood shipment delayed — 12 items approaching expiry',
    product_name: 'Atlantic Salmon Fillet',
    category: 'Seafood',
    timestamp: '2026-07-24T11:48:00Z',
    status: 'acknowledged',
  },
  {
    id: 4,
    severity: 'medium',
    message: 'Humidity levels elevated in Produce Section A',
    product_name: 'Romaine Lettuce',
    category: 'Produce',
    timestamp: '2026-07-24T10:22:00Z',
    status: 'acknowledged',
  },
  {
    id: 5,
    severity: 'low',
    message: 'Routine freshness check due for frozen inventory',
    product_name: 'Frozen Peas (500g)',
    category: 'Frozen',
    timestamp: '2026-07-24T09:05:00Z',
    status: 'new',
  },
];

// ─── Expiring Soon Products ────────────────────────────────────

export const mockExpiringProducts: ExpiringProduct[] = [
  {
    id: 101,
    name: 'Greek Yogurt (500ml)',
    category: 'Dairy',
    freshness_score: 35,
    status: 'warning',
    expiry_date: '2026-07-25T06:00:00Z',
    hours_remaining: 12,
    storage_location: 'Cold Storage A',
  },
  {
    id: 102,
    name: 'Baby Spinach (200g)',
    category: 'Produce',
    freshness_score: 28,
    status: 'warning',
    expiry_date: '2026-07-25T12:00:00Z',
    hours_remaining: 18,
    storage_location: 'Produce Section B',
  },
  {
    id: 103,
    name: 'Fresh Tuna Steak',
    category: 'Seafood',
    freshness_score: 22,
    status: 'warning',
    expiry_date: '2026-07-25T08:00:00Z',
    hours_remaining: 14,
    storage_location: 'Cold Storage C',
  },
  {
    id: 104,
    name: 'Croissants (Pack of 6)',
    category: 'Bakery',
    freshness_score: 40,
    status: 'warning',
    expiry_date: '2026-07-26T00:00:00Z',
    hours_remaining: 30,
    storage_location: 'Bakery Display',
  },
  {
    id: 105,
    name: 'Chicken Breast (1kg)',
    category: 'Meat',
    freshness_score: 32,
    status: 'warning',
    expiry_date: '2026-07-25T18:00:00Z',
    hours_remaining: 24,
    storage_location: 'Cold Storage B',
  },
  {
    id: 106,
    name: 'Strawberries (250g)',
    category: 'Produce',
    freshness_score: 18,
    status: 'expired',
    expiry_date: '2026-07-24T18:00:00Z',
    hours_remaining: 0,
    storage_location: 'Produce Section A',
  },
];
