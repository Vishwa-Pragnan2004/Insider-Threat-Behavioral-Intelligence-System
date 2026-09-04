import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Box, Typography, Grid, Skeleton } from '@mui/material';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from 'recharts';
import PageHeader from '../../components/common/PageHeader';
import StatCard from '../../components/common/StatCard';
import ChartCard from '../../components/common/ChartCard';
import {
  NotificationsActive,
  ManageSearch,
  Warning,
} from '@mui/icons-material';
import { listAlerts } from '../../api/alertService';
import { listInvestigations } from '../../api/investigationService';
import { listAnomalyResults } from '../../api/anomalyService';

const SEVERITY_COLORS: Record<string, string> = {
  LOW: '#3b82f6',
  MEDIUM: '#f59e0b',
  HIGH: '#f97316',
  CRITICAL: '#ef4444',
};

const STATUS_COLORS: Record<string, string> = {
  OPEN: '#3b82f6',
  ACKNOWLEDGED: '#f59e0b',
  IN_PROGRESS: '#8b5cf6',
  RESOLVED: '#10b981',
  FALSE_POSITIVE: '#64748b',
};

export default function DashboardPage() {
  const { data: openAlerts, isLoading: loadingOpen } = useQuery({
    queryKey: ['alerts', { status: 'OPEN', limit: 1 }],
    queryFn: () => listAlerts({ status: 'OPEN', limit: 1 }),
  });

  const { data: criticalAlerts, isLoading: loadingCritical } = useQuery({
    queryKey: ['alerts', { status: 'OPEN', severity: 'CRITICAL', limit: 1 }],
    queryFn: () => listAlerts({ status: 'OPEN', severity: 'CRITICAL', limit: 1 }),
  });

  const { data: highAlertsData, isLoading: loadingHigh } = useQuery({
    queryKey: ['alerts', { status: 'OPEN', severity: 'HIGH', limit: 1 }],
    queryFn: () => listAlerts({ status: 'OPEN', severity: 'HIGH', limit: 1 }),
  });

  const { data: activeInvestigations, isLoading: loadingInv } = useQuery({
    queryKey: ['investigations', { status: 'OPEN', limit: 1 }],
    queryFn: () => listInvestigations({ status: 'OPEN', limit: 1 }),
  });

  const { data: allAlerts, isLoading: loadingAllAlerts } = useQuery({
    queryKey: ['alerts', { limit: 500 }],
    queryFn: () => listAlerts({ limit: 500 }),
    staleTime: 60_000,
  });

  const { data: anomalyResults, isLoading: loadingAnomalies } = useQuery({
    queryKey: ['anomaly-results', { limit: 200 }],
    queryFn: () => listAnomalyResults({ limit: 200 }),
    staleTime: 60_000,
  });

  const alertSeverityData = useMemo(() => {
    if (!allAlerts) return [];
    const counts: Record<string, number> = { LOW: 0, MEDIUM: 0, HIGH: 0, CRITICAL: 0 };
    allAlerts.alerts.forEach(a => {
      if (a.severity in counts) counts[a.severity]++;
    });
    return Object.entries(counts)
      .filter(([, v]) => v > 0)
      .map(([name, value]) => ({ name, value, fill: SEVERITY_COLORS[name] }));
  }, [allAlerts]);

  const alertStatusData = useMemo(() => {
    if (!allAlerts) return [];
    const counts: Record<string, number> = {
      OPEN: 0, ACKNOWLEDGED: 0, IN_PROGRESS: 0, RESOLVED: 0, FALSE_POSITIVE: 0,
    };
    allAlerts.alerts.forEach(a => {
      if (a.status in counts) counts[a.status]++;
    });
    return Object.entries(counts)
      .filter(([, v]) => v > 0)
      .map(([name, value]) => ({ name: name.replace('_', ' '), value, fill: STATUS_COLORS[name] }));
  }, [allAlerts]);

  const anomalyRiskData = useMemo(() => {
    if (!anomalyResults) return [];
    const counts: Record<string, number> = { LOW: 0, MEDIUM: 0, HIGH: 0, CRITICAL: 0 };
    anomalyResults.results.forEach(r => {
      if (r.risk_level in counts) counts[r.risk_level]++;
    });
    return Object.entries(counts)
      .filter(([, v]) => v > 0)
      .map(([name, value]) => ({ name, value, fill: SEVERITY_COLORS[name] }));
  }, [anomalyResults]);

  const anomalyPredictionData = useMemo(() => {
    if (!anomalyResults) return [];
    const counts: Record<string, number> = { NORMAL: 0, ANOMALY: 0 };
    anomalyResults.results.forEach(r => {
      if (r.prediction in counts) counts[r.prediction]++;
    });
    return Object.entries(counts)
      .filter(([, v]) => v > 0)
      .map(([name, value]) => ({ name, value }));
  }, [anomalyResults]);

  return (
    <Box>
      <PageHeader title="SOC Dashboard" subtitle="Security operations center overview" />

      {/* KPI Cards */}
      <Grid container spacing={2} sx={{ mb: 3 }}>
        <Grid item xs={12} sm={6} md={3}>
          <StatCard
            label="Open Alerts"
            value={loadingOpen ? '—' : String(openAlerts?.total ?? 0)}
            trend={0}
            icon={<NotificationsActive />}
            iconColor="rgba(59, 130, 246, 0.12)"
          />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <StatCard
            label="Critical Alerts"
            value={loadingCritical ? '—' : String(criticalAlerts?.total ?? 0)}
            trend={0}
            icon={<Warning sx={{ color: '#ef4444 !important' }} />}
            iconColor="rgba(239, 68, 68, 0.12)"
          />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <StatCard
            label="Active Investigations"
            value={loadingInv ? '—' : String(activeInvestigations?.total ?? 0)}
            trend={0}
            icon={<ManageSearch />}
            iconColor="rgba(139, 92, 246, 0.12)"
          />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <StatCard
            label="High Alerts"
            value={loadingHigh ? '—' : String(highAlertsData?.total ?? 0)}
            trend={0}
            icon={<Warning sx={{ color: '#f97316 !important' }} />}
            iconColor="rgba(249, 115, 22, 0.12)"
          />
        </Grid>
      </Grid>

      {/* Charts Row 1 */}
      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={12} md={6}>
          <ChartCard title="Alerts by Severity" subtitle="All alerts by severity level">
            {loadingAllAlerts ? (
              <Skeleton variant="rectangular" width="100%" height="100%" />
            ) : alertSeverityData.length === 0 ? (
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
                <Typography color="text.secondary">No data</Typography>
              </Box>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={alertSeverityData} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" />
                  <XAxis dataKey="name" tick={{ fill: '#94a3b8', fontSize: 12 }} />
                  <YAxis tick={{ fill: '#94a3b8', fontSize: 12 }} allowDecimals={false} />
                  <RechartsTooltip
                    contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8 }}
                    labelStyle={{ color: '#f1f5f9' }}
                  />
                  <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                    {alertSeverityData.map((entry, i) => (
                      <Cell key={i} fill={entry.fill} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </ChartCard>
        </Grid>

        <Grid item xs={12} md={6}>
          <ChartCard title="Alerts by Status" subtitle="All alerts by lifecycle status">
            {loadingAllAlerts ? (
              <Skeleton variant="rectangular" width="100%" height="100%" />
            ) : alertStatusData.length === 0 ? (
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
                <Typography color="text.secondary">No data</Typography>
              </Box>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={alertStatusData}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    outerRadius={80}
                    label={({ name, percent }) => `${name} ${((percent ?? 0) * 100).toFixed(0)}%`}
                    labelLine={false}
                  >
                    {alertStatusData.map((entry, i) => (
                      <Cell key={i} fill={entry.fill} />
                    ))}
                  </Pie>
                  <RechartsTooltip
                    contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8 }}
                  />
                </PieChart>
              </ResponsiveContainer>
            )}
          </ChartCard>
        </Grid>
      </Grid>

      {/* Charts Row 2 */}
      <Grid container spacing={2}>
        <Grid item xs={12} md={6}>
          <ChartCard title="Anomaly Results by Risk Level" subtitle="Recent anomaly detections by risk">
            {loadingAnomalies ? (
              <Skeleton variant="rectangular" width="100%" height="100%" />
            ) : anomalyRiskData.length === 0 ? (
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
                <Typography color="text.secondary">No data</Typography>
              </Box>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={anomalyRiskData} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" />
                  <XAxis dataKey="name" tick={{ fill: '#94a3b8', fontSize: 12 }} />
                  <YAxis tick={{ fill: '#94a3b8', fontSize: 12 }} allowDecimals={false} />
                  <RechartsTooltip
                    contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8 }}
                    labelStyle={{ color: '#f1f5f9' }}
                  />
                  <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                    {anomalyRiskData.map((entry, i) => (
                      <Cell key={i} fill={entry.fill} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </ChartCard>
        </Grid>

        <Grid item xs={12} md={6}>
          <ChartCard title="Anomaly Predictions" subtitle="Normal vs anomalous detections">
            {loadingAnomalies ? (
              <Skeleton variant="rectangular" width="100%" height="100%" />
            ) : anomalyPredictionData.length === 0 ? (
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
                <Typography color="text.secondary">No data</Typography>
              </Box>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={anomalyPredictionData}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    outerRadius={80}
                    label={({ name, percent }) => `${name} ${((percent ?? 0) * 100).toFixed(1)}%`}
                    labelLine={false}
                  >
                    {anomalyPredictionData.map((entry, i) => (
                      <Cell key={i} fill={entry.name === 'ANOMALY' ? '#ef4444' : '#10b981'} />
                    ))}
                  </Pie>
                  <RechartsTooltip
                    contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8 }}
                  />
                </PieChart>
              </ResponsiveContainer>
            )}
          </ChartCard>
        </Grid>
      </Grid>
    </Box>
  );
}
