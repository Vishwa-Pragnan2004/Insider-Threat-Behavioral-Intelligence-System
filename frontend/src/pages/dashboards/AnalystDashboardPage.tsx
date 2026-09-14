import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  Button,
  Grid,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
} from '@mui/material';
import {
  AssignmentInd,
  CheckCircle,
  DoNotDisturb,
  NotificationsActive,
  PersonSearch,
  Warning,
} from '@mui/icons-material';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from 'recharts';
import StatCard from '../../components/common/StatCard';
import ChartCard from '../../components/common/ChartCard';
import SeverityBadge from '../../components/common/SeverityBadge';
import StatusBadge from '../../components/common/StatusBadge';
import { getAnalystDashboard } from '../../api/dashboardService';
import { listEmployeeRisk } from '../../api/riskService';
import { useAuth } from '../../hooks/useAuth';
import { hasPermission } from '../../utils/permissions';
import { EmployeeLink, componentLabel, useRiskModel } from '../risk/riskShared';
import type { AlertStatus } from '../../types';
import {
  CHART_AXIS_TICK,
  CHART_GRID_STROKE,
  CHART_TOOLTIP_PROPS,
  ChartEmpty,
  DASHBOARD_REFETCH_MS,
  DashboardShell,
  EmptyRow,
  InvestigationTable,
  LevelChip,
  NO_VALUE,
  PanelCard,
  RiskScoreChip,
  Section,
  UserRiskTable,
  formatDateTime,
  riskColor,
  severityChartData,
  statusChartData,
} from './shared';

/**
 * Security Analyst dashboard
 *
 * Day-to-day triage view: what's open and new, which users look riskiest,
 * what's waiting in the investigation queue, and how recent incidents ended.
 */
export default function AnalystDashboardPage() {
  const navigate = useNavigate();
  const query = useQuery({
    queryKey: ['dashboards', 'analyst'],
    queryFn: getAnalystDashboard,
    refetchInterval: DASHBOARD_REFETCH_MS,
  });
  const data = query.data;

  // Weighted insider risk queue — needs anomaly:read, otherwise the section keeps the legacy table.
  const { user } = useAuth();
  const canReadRisk = hasPermission(user, 'anomaly:read');
  const riskQuery = useQuery({
    queryKey: ['risk', 'employees', 'analyst-dashboard'],
    queryFn: () => listEmployeeRisk({ days: 7, limit: 10 }),
    enabled: canReadRisk,
    refetchInterval: DASHBOARD_REFETCH_MS,
  });
  const riskModel = useRiskModel(canReadRisk).data;

  return (
    <DashboardShell
      title="Security Analyst"
      subtitle="Threat triage, insider risk and your investigation queue"
      generatedAt={data?.generated_at}
      isLoading={query.isLoading}
      isFetching={query.isFetching}
      error={query.error}
      onRefresh={() => query.refetch()}
    >
      {data && (
        <>
          {/* ─── Threat alerts ─────────────────────────────────── */}
          <Section
            title="Threat alerts"
            subtitle="Open alerts awaiting triage"
            action={<Button onClick={() => navigate('/alerts')}>View all alerts</Button>}
          >
            <Grid container spacing={2} sx={{ mb: 2 }}>
              <Grid item xs={12} sm={6} md={3}>
                <StatCard label="Open alerts" value={String(data.threat_alerts.open_total)} icon={<NotificationsActive />} />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <StatCard
                  label="New in last 24h"
                  value={String(data.threat_alerts.new_last_24h)}
                  icon={<NotificationsActive />}
                  iconColor="rgba(139, 92, 246, 0.12)"
                />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <StatCard
                  label="Open critical"
                  value={String(data.threat_alerts.open_by_severity.CRITICAL)}
                  icon={<Warning sx={{ color: '#ef4444 !important' }} />}
                  iconColor="rgba(239, 68, 68, 0.12)"
                />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <StatCard
                  label="Open high"
                  value={String(data.threat_alerts.open_by_severity.HIGH)}
                  icon={<Warning sx={{ color: '#f97316 !important' }} />}
                  iconColor="rgba(249, 115, 22, 0.12)"
                />
              </Grid>
            </Grid>
            <Grid container spacing={2}>
              <Grid item xs={12} md={4}>
                <ChartCard title="Open alerts by severity" height={260}>
                  {data.threat_alerts.open_total === 0 ? (
                    <ChartEmpty text="No open alerts" />
                  ) : (
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={severityChartData(data.threat_alerts.open_by_severity)} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID_STROKE} />
                        <XAxis dataKey="name" tick={CHART_AXIS_TICK} />
                        <YAxis tick={CHART_AXIS_TICK} allowDecimals={false} />
                        <RechartsTooltip {...CHART_TOOLTIP_PROPS} />
                        <Bar dataKey="value" name="Alerts" radius={[4, 4, 0, 0]}>
                          {severityChartData(data.threat_alerts.open_by_severity).map((d) => (
                            <Cell key={d.name} fill={d.fill} />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  )}
                </ChartCard>
              </Grid>
              <Grid item xs={12} md={8}>
                <PanelCard title="Recent alerts">
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Title</TableCell>
                        <TableCell>User</TableCell>
                        <TableCell>Severity</TableCell>
                        <TableCell>Status</TableCell>
                        <TableCell align="center">Risk</TableCell>
                        <TableCell>Created</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {data.threat_alerts.recent.length === 0 ? (
                        <EmptyRow colSpan={6} text="No recent alerts" />
                      ) : (
                        data.threat_alerts.recent.map((a) => (
                          <TableRow key={a.id} hover onClick={() => navigate('/alerts')} sx={{ cursor: 'pointer' }}>
                            <TableCell sx={{ fontWeight: 600 }}>{a.title}</TableCell>
                            <TableCell>{a.user_id}</TableCell>
                            <TableCell>
                              <SeverityBadge severity={a.severity} />
                            </TableCell>
                            <TableCell>
                              <StatusBadge status={a.status as AlertStatus} />
                            </TableCell>
                            <TableCell align="center">
                              <RiskScoreChip score={a.risk_score} />
                            </TableCell>
                            <TableCell sx={{ whiteSpace: 'nowrap' }}>{formatDateTime(a.created_at)}</TableCell>
                          </TableRow>
                        ))
                      )}
                    </TableBody>
                  </Table>
                </PanelCard>
              </Grid>
            </Grid>
          </Section>

          {/* ─── Insider risk scores ───────────────────────────── */}
          <Section
            title="Insider risk scores"
            subtitle={`Highest-risk users over the last ${data.insider_risk.window_days} days`}
          >
            <Grid container spacing={2}>
              <Grid item xs={12} md={5}>
                <ChartCard title="Peak risk score by user" height={280}>
                  {data.insider_risk.users.length === 0 ? (
                    <ChartEmpty text="No users scored yet" />
                  ) : (
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={data.insider_risk.users} layout="vertical" margin={{ top: 4, right: 16, left: 8, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID_STROKE} />
                        <XAxis type="number" domain={[0, 100]} tick={CHART_AXIS_TICK} />
                        <YAxis type="category" dataKey="user_id" tick={CHART_AXIS_TICK} width={90} />
                        <RechartsTooltip {...CHART_TOOLTIP_PROPS} />
                        <Bar dataKey="max_risk_score" name="Max risk" radius={[0, 4, 4, 0]}>
                          {data.insider_risk.users.map((u) => (
                            <Cell key={u.user_id} fill={riskColor(u.max_risk_score)} />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  )}
                </ChartCard>
              </Grid>
              <Grid item xs={12} md={7}>
                {canReadRisk ? (
                  <PanelCard title="Risk queue · last 7 days">
                    <Table size="small">
                      <TableHead>
                        <TableRow>
                          <TableCell>Employee</TableCell>
                          <TableCell align="center">Priority</TableCell>
                          <TableCell align="center">Score</TableCell>
                          <TableCell>Level</TableCell>
                          <TableCell>Dominant component</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {riskQuery.isLoading ? (
                          <EmptyRow colSpan={5} text="Loading…" />
                        ) : riskQuery.isError ? (
                          <EmptyRow colSpan={5} text="Couldn't load insider risk scores" />
                        ) : (riskQuery.data?.employees ?? []).length === 0 ? (
                          <EmptyRow colSpan={5} text="No employees scored in the last 7 days" />
                        ) : (
                          riskQuery.data!.employees.map((e) => (
                            <TableRow key={e.user_id} hover>
                              <TableCell>
                                <EmployeeLink userId={e.user_id} />
                              </TableCell>
                              <TableCell align="center">
                                <RiskScoreChip score={e.priority} />
                              </TableCell>
                              <TableCell align="center">{e.score === null || e.score === undefined ? NO_VALUE : e.score.toFixed(1)}</TableCell>
                              <TableCell>
                                <LevelChip level={e.level} />
                              </TableCell>
                              <TableCell>{componentLabel(riskModel, e.dominant_component)}</TableCell>
                            </TableRow>
                          ))
                        )}
                      </TableBody>
                    </Table>
                    <Button size="small" sx={{ mt: 1 }} onClick={() => navigate('/risk')}>
                      Open insider risk
                    </Button>
                  </PanelCard>
                ) : (
                  <PanelCard title="Top users">
                    <UserRiskTable users={data.insider_risk.users} emptyText="No users scored in this window" />
                  </PanelCard>
                )}
              </Grid>
            </Grid>
          </Section>

          {/* ─── Investigation queue ───────────────────────────── */}
          <Section
            title="Investigation queue"
            action={<Button onClick={() => navigate('/investigations')}>View all investigations</Button>}
          >
            <Grid container spacing={2}>
              <Grid item xs={12} md={4}>
                <ChartCard title="Investigations by status" height={260}>
                  {Object.values(data.investigation_queue.counts_by_status).every((v) => v === 0) ? (
                    <ChartEmpty text="No investigations" />
                  ) : (
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie
                          data={statusChartData(data.investigation_queue.counts_by_status).filter((d) => d.value > 0)}
                          dataKey="value"
                          nameKey="name"
                          cx="50%"
                          cy="50%"
                          innerRadius={50}
                          outerRadius={85}
                          label={({ name, value }) => `${name} ${value}`}
                          labelLine={false}
                        >
                          {statusChartData(data.investigation_queue.counts_by_status)
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
              <Grid item xs={12} md={8}>
                <Grid container spacing={2}>
                  <Grid item xs={12}>
                    <PanelCard title="Assigned to me">
                      <InvestigationTable
                        items={data.investigation_queue.assigned_to_me}
                        emptyText="Nothing assigned to you"
                      />
                    </PanelCard>
                  </Grid>
                  <Grid item xs={12}>
                    <PanelCard title="Unassigned">
                      <InvestigationTable
                        items={data.investigation_queue.unassigned}
                        emptyText="No unassigned investigations"
                      />
                    </PanelCard>
                  </Grid>
                </Grid>
              </Grid>
            </Grid>
          </Section>

          {/* ─── Incident summaries ────────────────────────────── */}
          <Section
            title="Incident summaries"
            subtitle={`Closed out over the last ${data.incident_summaries.window_days} days`}
          >
            <Grid container spacing={2} sx={{ mb: 2 }}>
              <Grid item xs={12} sm={6} md={3}>
                <StatCard
                  label="Resolved"
                  value={String(data.incident_summaries.resolved)}
                  icon={<CheckCircle sx={{ color: '#10b981 !important' }} />}
                  iconColor="rgba(16, 185, 129, 0.12)"
                />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <StatCard
                  label="False positives"
                  value={String(data.incident_summaries.false_positives)}
                  icon={<DoNotDisturb />}
                  iconColor="rgba(100, 116, 139, 0.12)"
                />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <StatCard
                  label="Assigned to me"
                  value={String(data.investigation_queue.assigned_to_me.length)}
                  icon={<AssignmentInd />}
                  iconColor="rgba(139, 92, 246, 0.12)"
                />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <StatCard
                  label="Unassigned"
                  value={String(data.investigation_queue.unassigned.length)}
                  icon={<PersonSearch />}
                  iconColor="rgba(245, 158, 11, 0.12)"
                />
              </Grid>
            </Grid>
            <PanelCard title="Recently closed">
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Title</TableCell>
                    <TableCell>Severity</TableCell>
                    <TableCell>Status</TableCell>
                    <TableCell>Resolution</TableCell>
                    <TableCell>Users</TableCell>
                    <TableCell>Closed</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {data.incident_summaries.recent.length === 0 ? (
                    <EmptyRow colSpan={6} text="No incidents closed in this window" />
                  ) : (
                    data.incident_summaries.recent.map((inc) => (
                      <TableRow
                        key={inc.id}
                        hover
                        onClick={() => navigate(`/investigations/${inc.id}`)}
                        sx={{ cursor: 'pointer' }}
                      >
                        <TableCell sx={{ fontWeight: 600 }}>{inc.title}</TableCell>
                        <TableCell>
                          <LevelChip level={inc.severity} />
                        </TableCell>
                        <TableCell>{inc.status.replace('_', ' ')}</TableCell>
                        <TableCell sx={{ maxWidth: 320 }}>{inc.resolution ?? NO_VALUE}</TableCell>
                        <TableCell>{inc.related_user_ids.join(', ') || NO_VALUE}</TableCell>
                        <TableCell sx={{ whiteSpace: 'nowrap' }}>{formatDateTime(inc.closed_at)}</TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </PanelCard>
          </Section>
        </>
      )}
    </DashboardShell>
  );
}
