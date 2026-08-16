import type { DashboardData } from '../types/dashboard';
import {
  mockSummary,
  mockFreshnessTrend,
  mockCategoryDistribution,
  mockProductsByCategory,
  mockRecentAlerts,
  mockExpiringProducts,
} from '../mocks/dashboardData';
import { simulateDelay } from './axiosInstance';

/**
 * Dashboard Service
 *
 * Fetches all data needed for the Dashboard page.
 * Currently returns mock data; when Django backend is ready,
 * replace with real Axios calls.
 */

/**
 * Get all dashboard data in a single call.
 *
 * Mock: Returns combined mock data.
 * Real: GET /api/v1/dashboard/
 */
export const getDashboardData = async (): Promise<DashboardData> => {
  await simulateDelay(600);

  // When backend is ready, replace with:
  // const response = await axiosInstance.get('/dashboard/');
  // return response.data;
  return {
    summary: mockSummary,
    freshness_trend: mockFreshnessTrend,
    category_distribution: mockCategoryDistribution,
    products_by_category: mockProductsByCategory,
    recent_alerts: mockRecentAlerts,
    expiring_products: mockExpiringProducts,
  };
};
