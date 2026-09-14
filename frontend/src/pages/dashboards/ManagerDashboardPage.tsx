import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  Grid,
  LinearProgress,
  Stack,
  Typography,
} from '@mui/material';
import {
  Download,
  Groups,
  ManageSearch,
  School,
  Speed,
  VerifiedUser,
  Warning,
} from '@mui/icons-material';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from 'recharts';
import StatCard from '../../components/common/StatCard';
import ChartCard from '../../components/common/ChartCard';
import { getManagerDashboard } from '../../api/dashboardService';
import { exportAlertsCsv, exportInvestigationsCsv } from '../../api/reportService';
import { apiErrorMessage } from '../../api/userService';
import {
  CHART_AXIS_TICK,
  CHART_GRID_STROKE,
  CHART_TOOLTIP_PROPS,
  ChartEmpty,
  DASHBOARD_REFETCH_MS,
  DashboardShell,
  NO_VALUE,
  PanelCard,
  Section,
  UserRiskTable,
  formatNumber,
  riskColor,
  riskLevelFor,
  severityChartData,
  statusChartData,
} from './shared';

/**
 * Security Manager dashboard
 *
 * Organisation-level view: overall risk posture and how it's trending,
 * who the insider-threat report is about, and whether the SOC is meeting
 * its triage/response targets and agent coverage.
 */

function downloadBlob(blob: Blob, filename: string) {
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  window.URL.revokeObjectURL(url);
}

const shortDate = (value: unknown) =>
  new Date(String(value)).toLocaleDateString([], { month: 'short', day: 'numeric' });

export default function ManagerDashboardPage() {
  const query = useQuery({
    queryKey: ['dashboards', 'manager'],
    queryFn: getManagerDashboard,
    refetchInterval: DASHBOARD_REFETCH_MS,
  });
  const data = query.data;

  const [exporting, setExporting] = useState<'alerts' | 'investigations' | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);

  async function handleExport(kind: 'alerts' | 'investigations') {
    setExporting(kind);
    setExportError(null);
    try {
      // Scope the export to the report's window so it matches what's on screen.
      const start = data
        ? new Date(Date.now() - data.insider_threat_report.window_days * 86_400_000).toISOString()
        : undefined;
      const blob =
        kind === 'alerts' ? await exportAlertsCsv({ start }) : await exportInvestigationsCsv({ start });
      downloadBlob(blob, `${kind}_report_${new Date().toISOString().split('T')[0]}.csv`);
    } catch (error) {
      setExportError(`Failed to export ${kind}: ${apiErrorMessage(error)}`);
    } finally {
      setExporting(null);
    }
  }

  const posture = data?.risk_posture;
  const report = data?.insider_threat_report;
  const compliance = data?.compliance;
  const series = data?.risk_trends.series ?? [];

  return (
    <DashboardShell
      title="Security Manager"
      subtitle="Organisational risk posture, trends and compliance"
      generatedAt={data?.generated_at}
      isLoading={query.isLoading}
      isFetching={query.isFetching}
      error={query.error}
      onRefresh={() => query.refetch()}
    >
      {data && posture && report && compliance && (
        <>
          {/* ─── Organizational risk posture ───────────────────── */}
          <Section title="Organizational risk posture">
            <Grid container spacing={2}>
              <Grid item xs={12} md={4}>
                <Card sx={{ height: '100%' }}>
                  <CardContent sx={{ p: 3 }}>
                    <Typography variant="body2" color="text.secondary">
                      Organisation risk index
                    </Typography>
                    <Typography
                      variant="h2"
                      sx={{ fontWeight: 800, color: riskColor(posture.org_risk_index), my: 1 }}
                    >
                      {formatNumber(posture.org_risk_index, '', 1)}
                    </Typography>
                    <Typography variant="body2" sx={{ color: riskColor(posture.org_risk_index), fontWeight: 600 }}>
                      {posture.org_risk_index === null ? 'Not enough scored data yet' : riskLevelFor(posture.org_risk_index)}
                    </Typography>
                    {posture.org_risk_index !== null && (
                      <LinearProgress
                        variant="determinate"
                        value={Math.min(100, Math.max(0, posture.org_risk_index))}
                        sx={{
                          mt: 2,
                          height: 8,
                          borderRadius: 4,
                          bgcolor: 'rgba(255,255,255,0.08)',
                          '& .MuiLinearProgress-bar': { bgcolor: riskColor(posture.org_risk_index) },
                        }}
                      />
                    )}
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={12} md={8}>
                <Grid container spacing={2}>
                  <Grid item xs={12} sm={4}>
                    <StatCard label="Monitored users" value={String(posture.monitored_users)} icon={<Groups />} />
                  </Grid>
                  <Grid item xs={12} sm={4}>
                    <StatCard
                      label="Personal baseline"
                      value={String(posture.baselined_users)}
                      icon={<VerifiedUser sx={{ color: '#10b981 !important' }} />}
                      iconColor="rgba(16, 185, 129, 0.12)"
                    />
                  </Grid>
                  <Grid item xs={12} sm={4}>
                    <StatCard
                      label="Still learning"
                      value={String(posture.learning_users)}
                      icon={<School />}
                      iconColor="rgba(139, 92, 246, 0.12)"
                    />
                  </Grid>
                  <Grid item xs={12} sm={4}>
                    <StatCard
                      label="High-risk users"
                      value={String(posture.high_risk_users)}
                      icon={<Warning sx={{ color: '#f97316 !important' }} />}
                      iconColor="rgba(249, 115, 22, 0.12)"
                    />
                  </Grid>
                  <Grid item xs={12} sm={4}>
                    <StatCard
                      label="Open critical alerts"
                      value={String(posture.open_critical_alerts)}
                      icon={<Warning sx={{ color: '#ef4444 !important' }} />}
                      iconColor="rgba(239, 68, 68, 0.12)"
                    />
                  </Grid>
                  <Grid item xs={12} sm={4}>
                    <StatCard
                      label="Open investigations"
                      value={String(posture.open_investigations)}
                      icon={<ManageSearch />}
                      iconColor="rgba(245, 158, 11, 0.12)"
                    />
                  </Grid>
                </Grid>
              </Grid>
            </Grid>
          </Section>

          {/* ─── Risk trends ───────────────────────────────────── */}
          <Section title="Risk trends" subtitle={`Daily over the last ${data.risk_trends.days} days`}>
            <Grid container spacing={2}>
              <Grid item xs={12} md={7}>
                <ChartCard title="Risk score" subtitle="Average and peak per day">
                  {series.length === 0 ? (
                    <ChartEmpty />
                  ) : (
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={series} margin={{ top: 8, right: 16, left: -16, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID_STROKE} />
                        <XAxis dataKey="date" tick={CHART_AXIS_TICK} tickFormatter={shortDate} minTickGap={16} />
                        <YAxis domain={[0, 100]} tick={CHART_AXIS_TICK} />
                        <RechartsTooltip {...CHART_TOOLTIP_PROPS} labelFormatter={shortDate} />
                        <Legend wrapperStyle={{ fontSize: 12 }} />
                        <Line type="monotone" dataKey="avg_risk_score" name="Average" stroke="#3b82f6" strokeWidth={2} dot={false} connectNulls />
                        <Line type="monotone" dataKey="max_risk_score" name="Peak" stroke="#ef4444" strokeWidth={2} dot={false} connectNulls />
                      </LineChart>
                    </ResponsiveContainer>
                  )}
                </ChartCard>
              </Grid>
              <Grid item xs={12} md={5}>
                <ChartCard title="Anomalies and alerts" subtitle="Created per day">
                  {series.length === 0 ? (
                    <ChartEmpty />
                  ) : (
                    <ResponsiveContainer width="100%" height="100%">
                      <ComposedChart data={series} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID_STROKE} />
                        <XAxis dataKey="date" tick={CHART_AXIS_TICK} tickFormatter={shortDate} minTickGap={16} />
                        <YAxis tick={CHART_AXIS_TICK} allowDecimals={false} />
                        <RechartsTooltip {...CHART_TOOLTIP_PROPS} labelFormatter={shortDate} />
                        <Legend wrapperStyle={{ fontSize: 12 }} />
                        <Bar dataKey="anomalies" name="Anomalies" fill="#8b5cf6" radius={[3, 3, 0, 0]} />
                        <Line type="monotone" dataKey="alerts_created" name="Alerts" stroke="#f59e0b" strokeWidth={2} dot={false} />
                      </ComposedChart>
                    </ResponsiveContainer>
                  )}
                </ChartCard>
              </Grid>
            </Grid>
          </Section>

          {/* ─── Insider threat reports ────────────────────────── */}
          <Section
            title="Insider threat reports"
            subtitle={`Last ${report.window_days} days`}
            action={
              <Stack direction="row" spacing={1}>
                <Button
                  variant="outlined"
                  size="small"
                  startIcon={exporting === 'alerts' ? <CircularProgress size={16} /> : <Download />}
                  disabled={exporting !== null}
                  onClick={() => handleExport('alerts')}
                >
                  Alerts CSV
                </Button>
                <Button
                  variant="outlined"
                  size="small"
                  startIcon={exporting === 'investigations' ? <CircularProgress size={16} /> : <Download />}
                  disabled={exporting !== null}
                  onClick={() => handleExport('investigations')}
                >
                  Investigations CSV
                </Button>
              </Stack>
            }
          >
            {exportError && (
              <Alert severity="error" sx={{ mb: 2 }} onClose={() => setExportError(null)}>
                {exportError}
              </Alert>
            )}
            <Grid container spacing={2}>
              <Grid item xs={12} md={6}>
                <ChartCard title="Alerts by severity" height={240}>
                  {Object.values(report.alerts_by_severity).every((v) => v === 0) ? (
                    <ChartEmpty text="No alerts in this window" />
                  ) : (
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie
                          data={severityChartData(report.alerts_by_severity).filter((d) => d.value > 0)}
                          dataKey="value"
                          nameKey="name"
                          cx="50%"
                          cy="50%"
                          innerRadius={45}
                          outerRadius={80}
                          label={({ name, value }) => `${name} ${value}`}
                          labelLine={false}
                        >
                          {severityChartData(report.alerts_by_severity)
                            .filter((d) => d.value > 0)
                            .map((d) => (
                              <Cell key={d.name} fill={d.fill} />
                            ))}
                        </Pie>
                        <RechartsTooltip {...CHART_TOOLTIP_PROPS} />
                      </PieChart>
                    </ResponsiveContainer>
                  )}
                </ChartCard>
              </Grid>
              <Grid item xs={12} md={6}>
                <ChartCard title="Investigations by status" height={240}>
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={statusChartData(report.investigations_by_status)} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID_STROKE} />
                      <XAxis dataKey="name" tick={CHART_AXIS_TICK} />
                      <YAxis tick={CHART_AXIS_TICK} allowDecimals={false} />
                      <RechartsTooltip {...CHART_TOOLTIP_PROPS} />
                      <Bar dataKey="value" name="Investigations" radius={[4, 4, 0, 0]}>
                        {statusChartData(report.investigations_by_status).map((d) => (
                          <Cell key={d.name} fill={d.fill} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </ChartCard>
              </Grid>
              <Grid item xs={12}>
                <PanelCard title="Highest-risk users">
                  <UserRiskTable users={report.top_users} emptyText="No users scored in this window" />
                </PanelCard>
              </Grid>
            </Grid>
          </Section>

          {/* ─── Compliance metrics ────────────────────────────── */}
          <Section title="Compliance metrics" subtitle={`Last ${compliance.window_days} days`}>
            <Grid container spacing={2}>
              <MetricTile label="Alerts raised" value={compliance.alerts_total.toLocaleString()} />
              <MetricTile label="Alerts triaged" value={formatNumber(compliance.triaged_pct, '%', 1)} pct={compliance.triaged_pct} />
              <MetricTile label="Mean time to acknowledge" value={formatNumber(compliance.mean_hours_to_acknowledge, ' h', 1)} />
              <MetricTile label="Mean time to resolve" value={formatNumber(compliance.mean_hours_to_resolve, ' h', 1)} />
              <MetricTile
                label={`Critical alerts within ${compliance.critical_sla_hours} h SLA`}
                value={formatNumber(compliance.critical_within_sla_pct, '%', 1)}
                pct={compliance.critical_within_sla_pct}
              />
              <MetricTile
                label="Investigations closed"
                value={formatNumber(compliance.investigations_closed_pct, '%', 1)}
                pct={compliance.investigations_closed_pct}
              />
              <MetricTile
                label="Agent coverage"
                value={formatNumber(compliance.agent_coverage_pct, '%', 1)}
                pct={compliance.agent_coverage_pct}
                caption={`${compliance.devices_reporting_24h} of ${compliance.devices_enrolled} enrolled devices reported in 24h`}
              />
              <MetricTile label="Admin actions audited" value={compliance.admin_actions.toLocaleString()} icon={<Speed fontSize="small" />} />
            </Grid>
          </Section>
        </>
      )}
    </DashboardShell>
  );
}

interface MetricTileProps {
  label: string;
  value: string;
  /** 0–100; renders a progress bar when present. */
  pct?: number | null;
  caption?: string;
  icon?: React.ReactNode;
}

function MetricTile({ label, value, pct, caption, icon }: MetricTileProps) {
  const barColor =
    pct === null || pct === undefined ? '#64748b' : pct >= 90 ? '#10b981' : pct >= 70 ? '#f59e0b' : '#ef4444';
  return (
    <Grid item xs={12} sm={6} md={3}>
      <PanelCard title={label}>
        <Stack direction="row" spacing={1} alignItems="center">
          {icon}
          <Typography variant="h5" sx={{ fontWeight: 700 }}>
            {value}
          </Typography>
        </Stack>
        {pct !== undefined && (
          <Box sx={{ mt: 1 }}>
            <LinearProgress
              variant="determinate"
              value={pct === null ? 0 : Math.min(100, Math.max(0, pct))}
              sx={{
                height: 6,
                borderRadius: 3,
                bgcolor: 'rgba(255,255,255,0.08)',
                '& .MuiLinearProgress-bar': { bgcolor: barColor },
              }}
            />
          </Box>
        )}
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
          {caption ?? (value === NO_VALUE ? 'No data in this window' : ' ')}
        </Typography>
      </PanelCard>
    </Grid>
  );
}
