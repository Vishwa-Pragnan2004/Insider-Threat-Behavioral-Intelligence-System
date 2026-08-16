import { useState, useEffect } from 'react';
import {
  Grid,
  Card,
  CardContent,
  CardHeader,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
  Box,
  Chip,
  Button,
} from '@mui/material';
import {
  LineChart,
  Line,
  AreaChart,
  Area,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';

// Icons for the KPI stat cards
import Inventory2Icon from '@mui/icons-material/Inventory2';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import WarningAmberIcon from '@mui/icons-material/WarningAmber';
import NotificationsActiveIcon from '@mui/icons-material/NotificationsActive';
import RefreshIcon from '@mui/icons-material/Refresh';
import AccessTimeIcon from '@mui/icons-material/AccessTime';

// Reusable components
import PageHeader from '../components/common/PageHeader';
import StatCard from '../components/common/StatCard';
import ChartCard from '../components/common/ChartCard';
import { SeverityBadge, FreshnessBadge } from '../components/common/StatusBadge';
import LoadingOverlay from '../components/common/LoadingOverlay';

// API service & types
import { getDashboardData } from '../api/dashboardService';
import type { DashboardData } from '../types/dashboard';

/**
 * DashboardPage
 *
 * Main dashboard showing a real-time overview of food freshness:
 * - 4 KPI stat cards (Total Products, Fresh %, Expiring Soon, Active Alerts)
 * - Freshness trend chart (30-day area chart)
 * - Freshness distribution pie chart
 * - Products by category stacked bar chart
 * - Recent alerts table
 * - Expiring soon product list
 */
export default function DashboardPage() {
  // Dashboard data from the API service
  const [data, setData] = useState<DashboardData | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Fetch dashboard data on mount
  useEffect(() => {
    loadDashboard();
  }, []);

  const loadDashboard = async () => {
    setIsLoading(true);
    try {
      const result = await getDashboardData();
      setData(result);
    } catch (error) {
      console.error('Failed to load dashboard:', error);
    } finally {
      setIsLoading(false);
    }
  };

  // Show loading spinner while data is being fetched
  if (isLoading || !data) {
    return <LoadingOverlay message="Loading dashboard data..." />;
  }

  const { summary, freshness_trend, category_distribution, products_by_category, recent_alerts, expiring_products } = data;

  return (
    <>
      {/* Page Title */}
      <PageHeader
        title="Dashboard"
        subtitle="Real-time food freshness monitoring overview"
        actions={
          <Button
            variant="outlined"
            startIcon={<RefreshIcon />}
            onClick={loadDashboard}
            size="small"
          >
            Refresh
          </Button>
        }
      />

      {/* ─── KPI Stat Cards ─────────────────────────────────────── */}
      <Grid container spacing={3} sx={{ mb: 3 }}>
        <Grid size={{ xs: 12, sm: 6, md: 3 }}>
          <StatCard
            label="Total Products"
            value={summary.total_products.toLocaleString()}
            trend={summary.total_products_trend}
            icon={<Inventory2Icon />}
            iconColor="rgba(0, 188, 212, 0.15)"
          />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, md: 3 }}>
          <StatCard
            label="Fresh Products"
            value={`${summary.fresh_percentage}%`}
            trend={summary.fresh_percentage_trend}
            icon={<CheckCircleIcon />}
            iconColor="rgba(16, 185, 129, 0.15)"
          />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, md: 3 }}>
          <StatCard
            label="Expiring Soon"
            value={summary.expiring_soon.toString()}
            trend={summary.expiring_soon_trend}
            trendUpIsGood={false}
            icon={<WarningAmberIcon />}
            iconColor="rgba(245, 158, 11, 0.15)"
          />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, md: 3 }}>
          <StatCard
            label="Active Alerts"
            value={summary.active_alerts.toString()}
            trend={summary.active_alerts_trend}
            trendUpIsGood={false}
            icon={<NotificationsActiveIcon />}
            iconColor="rgba(239, 68, 68, 0.15)"
          />
        </Grid>
      </Grid>

      {/* ─── Charts Row 1: Trend + Distribution ─────────────────── */}
      <Grid container spacing={3} sx={{ mb: 3 }}>
        {/* Freshness Trend (Area Chart) */}
        <Grid size={{ xs: 12, lg: 8 }}>
          <ChartCard title="Freshness Score Trend" subtitle="Average freshness score — last 30 days">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={freshness_trend} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
                <defs>
                  <linearGradient id="colorScore" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#00BCD4" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#00BCD4" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#1E293B" />
                <XAxis
                  dataKey="date"
                  stroke="#475569"
                  fontSize={12}
                  tickLine={false}
                />
                <YAxis
                  domain={[0, 100]}
                  stroke="#475569"
                  fontSize={12}
                  tickLine={false}
                />
                <RechartsTooltip
                  contentStyle={{
                    backgroundColor: '#1E293B',
                    border: '1px solid #334155',
                    borderRadius: 8,
                    color: '#F1F5F9',
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="average_score"
                  stroke="#00BCD4"
                  strokeWidth={2}
                  fill="url(#colorScore)"
                  name="Avg Score"
                />
                <Line
                  type="monotone"
                  dataKey="min_score"
                  stroke="#EF4444"
                  strokeWidth={1}
                  strokeDasharray="4 4"
                  dot={false}
                  name="Min"
                />
                <Line
                  type="monotone"
                  dataKey="max_score"
                  stroke="#10B981"
                  strokeWidth={1}
                  strokeDasharray="4 4"
                  dot={false}
                  name="Max"
                />
                <Legend />
              </AreaChart>
            </ResponsiveContainer>
          </ChartCard>
        </Grid>

        {/* Freshness Distribution (Pie Chart) */}
        <Grid size={{ xs: 12, lg: 4 }}>
          <ChartCard title="Freshness Distribution" subtitle="Current inventory breakdown">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={category_distribution}
                  cx="50%"
                  cy="50%"
                  innerRadius={65}
                  outerRadius={100}
                  paddingAngle={4}
                  dataKey="value"
                  nameKey="name"
                  stroke="none"
                >
                  {category_distribution.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <RechartsTooltip
                  contentStyle={{
                    backgroundColor: '#1E293B',
                    border: '1px solid #334155',
                    borderRadius: 8,
                    color: '#F1F5F9',
                  }}
                  formatter={(value: number, name: string) => [`${value} items`, name]}
                />
                <Legend
                  verticalAlign="bottom"
                  height={36}
                  formatter={(value: string) => (
                    <span style={{ color: '#94A3B8', fontSize: '0.85rem' }}>{value}</span>
                  )}
                />
              </PieChart>
            </ResponsiveContainer>
          </ChartCard>
        </Grid>
      </Grid>

      {/* ─── Charts Row 2: Products by Category ─────────────────── */}
      <Grid container spacing={3} sx={{ mb: 3 }}>
        <Grid size={{ xs: 12 }}>
          <ChartCard title="Products by Category" subtitle="Freshness breakdown per food category" height={320}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={products_by_category} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1E293B" />
                <XAxis dataKey="category" stroke="#475569" fontSize={12} tickLine={false} />
                <YAxis stroke="#475569" fontSize={12} tickLine={false} />
                <RechartsTooltip
                  contentStyle={{
                    backgroundColor: '#1E293B',
                    border: '1px solid #334155',
                    borderRadius: 8,
                    color: '#F1F5F9',
                  }}
                />
                <Legend />
                <Bar dataKey="fresh" stackId="status" fill="#10B981" name="Fresh" radius={[0, 0, 0, 0]} />
                <Bar dataKey="warning" stackId="status" fill="#F59E0B" name="Warning" />
                <Bar dataKey="expired" stackId="status" fill="#EF4444" name="Expired" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>
        </Grid>
      </Grid>

      {/* ─── Bottom Row: Recent Alerts + Expiring Soon ──────────── */}
      <Grid container spacing={3}>
        {/* Recent Alerts Table */}
        <Grid size={{ xs: 12, lg: 7 }}>
          <Card>
            <CardHeader
              title="Recent Alerts"
              slotProps={{ title: { variant: 'h6', sx: { fontSize: '1rem', fontWeight: 600 } } }}
              action={
                <Button size="small" color="primary">
                  View All
                </Button>
              }
            />
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Severity</TableCell>
                    <TableCell>Message</TableCell>
                    <TableCell>Product</TableCell>
                    <TableCell>Time</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {recent_alerts.map((alert) => (
                    <TableRow
                      key={alert.id}
                      hover
                      sx={{ cursor: 'pointer', '&:last-child td': { border: 0 } }}
                    >
                      <TableCell>
                        <SeverityBadge severity={alert.severity} />
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2" sx={{ maxWidth: 300 }} noWrap>
                          {alert.message}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                          {alert.product_name}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2" sx={{ color: 'text.secondary', whiteSpace: 'nowrap' }}>
                          {formatTimeAgo(alert.timestamp)}
                        </Typography>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </Card>
        </Grid>

        {/* Expiring Soon List */}
        <Grid size={{ xs: 12, lg: 5 }}>
          <Card>
            <CardHeader
              title="Expiring Soon"
              subheader="Products expiring within 48 hours"
              slotProps={{
                title: { variant: 'h6', sx: { fontSize: '1rem', fontWeight: 600 } },
                subheader: { variant: 'body2', sx: { color: 'text.secondary', mt: 0.3 } },
              }}
            />
            <CardContent sx={{ pt: 0 }}>
              {expiring_products.map((product) => (
                <Box
                  key={product.id}
                  sx={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    py: 1.5,
                    borderBottom: '1px solid',
                    borderColor: 'divider',
                    '&:last-child': { borderBottom: 'none' },
                    cursor: 'pointer',
                    '&:hover': { bgcolor: 'rgba(255, 255, 255, 0.02)' },
                  }}
                >
                  {/* Product Info */}
                  <Box sx={{ flex: 1, minWidth: 0 }}>
                    <Typography variant="body2" sx={{ fontWeight: 500, color: 'text.primary' }} noWrap>
                      {product.name}
                    </Typography>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 0.5 }}>
                      <Chip
                        label={product.category}
                        size="small"
                        variant="outlined"
                        sx={{ fontSize: '0.7rem', height: 22, borderColor: 'divider' }}
                      />
                      <Typography variant="caption" sx={{ color: 'text.secondary', display: 'flex', alignItems: 'center', gap: 0.3 }}>
                        <AccessTimeIcon sx={{ fontSize: 14 }} />
                        {product.hours_remaining > 0 ? `${product.hours_remaining}h left` : 'Expired'}
                      </Typography>
                    </Box>
                  </Box>

                  {/* Score + Status */}
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, ml: 2 }}>
                    <Typography
                      variant="body2"
                      sx={{
                        fontWeight: 700,
                        color: product.freshness_score > 40 ? 'warning.main' : 'error.main',
                      }}
                    >
                      {product.freshness_score}%
                    </Typography>
                    <FreshnessBadge status={product.status} />
                  </Box>
                </Box>
              ))}
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </>
  );
}

// ─── Helper Functions ──────────────────────────────────────────

/**
 * Format a timestamp into a human-readable "time ago" string.
 * e.g. "2 hours ago", "Just now"
 */
function formatTimeAgo(timestamp: string): string {
  const now = new Date();
  const time = new Date(timestamp);
  const diffMs = now.getTime() - time.getTime();
  const diffMins = Math.floor(diffMs / 60000);

  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  return `${diffDays}d ago`;
}
