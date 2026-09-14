import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  Alert,
  AlertTitle,
  Box,
  Button,
  Chip,
  Grid,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import {
  Devices,
  Event as EventIcon,
  Flag,
  Insights,
  People,
  Psychology,
} from '@mui/icons-material';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from 'recharts';
import StatCard from '../../components/common/StatCard';
import ChartCard from '../../components/common/ChartCard';
import { getSocDashboard } from '../../api/dashboardService';
import {
  CHART_AXIS_TICK,
  CHART_GRID_STROKE,
  CHART_TOOLTIP_PROPS,
  ChartEmpty,
  DASHBOARD_REFETCH_MS,
  DashboardShell,
  EmptyRow,
  InvestigationTable,
  LearningChip,
  LevelChip,
  NO_VALUE,
  PanelCard,
  RiskScoreChip,
  Section,
  formatDateTime,
  severityChartData,
  statusChartData,
} from './shared';

/**
 * SOC Operations dashboard
 *
 * Live operational picture: event flow from endpoints, what the behavioural
 * model is flagging, investigations in flight, and internally-derived threat
 * indicators plus the health of the scoring pipeline.
 */
export default function SocDashboardPage() {
  const navigate = useNavigate();
  const query = useQuery({
    queryKey: ['dashboards', 'soc'],
    queryFn: getSocDashboard,
    refetchInterval: DASHBOARD_REFETCH_MS,
  });
  const data = query.data;

  const events = data?.security_events;
  const anomalies = data?.behavioral_anomalies;
  const intel = data?.threat_intelligence;
  const eventTypeData = Object.entries(events?.by_event_type ?? {})
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value);

  return (
    <DashboardShell
      title="SOC Operations"
      subtitle="Event flow, behavioural anomalies and active investigations"
      generatedAt={data?.generated_at}
      isLoading={query.isLoading}
      isFetching={query.isFetching}
      error={query.error}
      onRefresh={() => query.refetch()}
    >
      {data && events && anomalies && intel && (
        <>
          {/* ─── Security events ───────────────────────────────── */}
          <Section
            title="Security events"
            subtitle={`Endpoint and dataset events over the last ${events.window_hours} hours`}
            action={<Button onClick={() => navigate('/activity')}>Open activity log</Button>}
          >
            <Grid container spacing={2} sx={{ mb: 2 }}>
              <Grid item xs={12} sm={6} md={3}>
                <StatCard label="Events" value={events.total.toLocaleString()} icon={<EventIcon />} />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <StatCard
                  label="Flagged events"
                  value={events.flagged.toLocaleString()}
                  icon={<Flag sx={{ color: '#f97316 !important' }} />}
                  iconColor="rgba(249, 115, 22, 0.12)"
                />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <StatCard
                  label="Active users"
                  value={String(events.active_users)}
                  icon={<People />}
                  iconColor="rgba(139, 92, 246, 0.12)"
                />
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <StatCard
                  label="Active devices"
                  value={String(events.active_devices)}
                  icon={<Devices />}
                  iconColor="rgba(16, 185, 129, 0.12)"
                />
              </Grid>
            </Grid>
            <Grid container spacing={2} sx={{ mb: 2 }}>
              <Grid item xs={12} md={7}>
                <ChartCard title="Events per hour" height={240}>
                  {events.hourly.length === 0 ? (
                    <ChartEmpty text="No events in this window" />
                  ) : (
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={events.hourly} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID_STROKE} />
                        <XAxis
                          dataKey="hour"
                          tick={CHART_AXIS_TICK}
                          tickFormatter={(v) => new Date(String(v)).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                          minTickGap={24}
                        />
                        <YAxis tick={CHART_AXIS_TICK} allowDecimals={false} />
                        <RechartsTooltip
                          {...CHART_TOOLTIP_PROPS}
                          labelFormatter={(label) => new Date(String(label)).toLocaleString()}
                        />
                        <Area type="monotone" dataKey="count" name="Events" stroke="#3b82f6" fill="rgba(59, 130, 246, 0.25)" />
                      </AreaChart>
                    </ResponsiveContainer>
                  )}
                </ChartCard>
              </Grid>
              <Grid item xs={12} md={5}>
                <ChartCard title="Events by type" height={240}>
                  {eventTypeData.length === 0 ? (
                    <ChartEmpty />
                  ) : (
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={eventTypeData} layout="vertical" margin={{ top: 4, right: 16, left: 8, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID_STROKE} />
                        <XAxis type="number" tick={CHART_AXIS_TICK} allowDecimals={false} />
                        <YAxis type="category" dataKey="name" tick={CHART_AXIS_TICK} width={110} />
                        <RechartsTooltip {...CHART_TOOLTIP_PROPS} />
                        <Bar dataKey="value" name="Events" fill="#8b5cf6" radius={[0, 4, 4, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  )}
                </ChartCard>
              </Grid>
            </Grid>
            <PanelCard title="Latest events">
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Time</TableCell>
                    <TableCell>User</TableCell>
                    <TableCell>Event type</TableCell>
                    <TableCell>Target</TableCell>
                    <TableCell>Device</TableCell>
                    <TableCell>Risk indicators</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {events.recent.length === 0 ? (
                    <EmptyRow colSpan={6} text="No events yet — start the ITBIS agent or upload CERT data" />
                  ) : (
                    events.recent.map((ev) => (
                      <TableRow key={ev.id} hover>
                        <TableCell sx={{ whiteSpace: 'nowrap' }}>{formatDateTime(ev.timestamp)}</TableCell>
                        <TableCell>{ev.user_id}</TableCell>
                        <TableCell>
                          <Chip size="small" variant="outlined" label={ev.event_type} />
                        </TableCell>
                        <TableCell sx={{ maxWidth: 260, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {ev.target_resource ?? NO_VALUE}
                        </TableCell>
                        <TableCell>{ev.device_name ?? ev.device_id ?? NO_VALUE}</TableCell>
                        <TableCell>
                          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                            {ev.risk_indicators.map((ri) => (
                              <Chip key={ri} size="small" color="warning" variant="outlined" label={ri} sx={{ height: 20, fontSize: '0.7rem' }} />
                            ))}
                          </Box>
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </PanelCard>
          </Section>

          {/* ─── Behavioral anomalies ──────────────────────────── */}
          <Section
            title="Behavioral anomalies"
            subtitle={`Model scoring results over the last ${anomalies.window_days} days`}
          >
            <Grid container spacing={2}>
              <Grid item xs={12} md={4}>
                <Stack spacing={2} sx={{ height: '100%' }}>
                  <StatCard
                    label="Windows scored"
                    value={anomalies.results.toLocaleString()}
                    icon={<Psychology />}
                    iconColor="rgba(59, 130, 246, 0.12)"
                  />
                  <StatCard
                    label={`Anomalies (${anomalies.results ? ((anomalies.anomalies / anomalies.results) * 100).toFixed(1) : '0.0'}% of windows)`}
                    value={anomalies.anomalies.toLocaleString()}
                    icon={<Insights sx={{ color: '#ef4444 !important' }} />}
                    iconColor="rgba(239, 68, 68, 0.12)"
                  />
                </Stack>
              </Grid>
              <Grid item xs={12} md={8}>
                <ChartCard title="Results by risk level" height={250}>
                  {anomalies.results === 0 ? (
                    <ChartEmpty text="Nothing scored in this window" />
                  ) : (
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={severityChartData(anomalies.by_risk_level)} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID_STROKE} />
                        <XAxis dataKey="name" tick={CHART_AXIS_TICK} />
                        <YAxis tick={CHART_AXIS_TICK} allowDecimals={false} />
                        <RechartsTooltip {...CHART_TOOLTIP_PROPS} />
                        <Bar dataKey="value" name="Results" radius={[4, 4, 0, 0]}>
                          {severityChartData(anomalies.by_risk_level).map((d) => (
                            <Cell key={d.name} fill={d.fill} />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  )}
                </ChartCard>
              </Grid>
              <Grid item xs={12}>
                <PanelCard title="Recent anomalous windows">
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>User</TableCell>
                        <TableCell>Window start</TableCell>
                        <TableCell align="center">Risk</TableCell>
                        <TableCell>Level</TableCell>
                        <TableCell>Prediction</TableCell>
                        <TableCell>Top deviation</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {anomalies.recent.length === 0 ? (
                        <EmptyRow colSpan={6} text="No recent results" />
                      ) : (
                        anomalies.recent.map((r) => (
                          <TableRow key={r.id} hover>
                            <TableCell sx={{ whiteSpace: 'nowrap' }}>
                              {r.user_id}
                              {r.baseline_source === 'global' && <LearningChip />}
                            </TableCell>
                            <TableCell sx={{ whiteSpace: 'nowrap' }}>{formatDateTime(r.window_start)}</TableCell>
                            <TableCell align="center">
                              <RiskScoreChip score={r.risk_score} />
                            </TableCell>
                            <TableCell>
                              <LevelChip level={r.risk_level} />
                            </TableCell>
                            <TableCell>
                              <Chip
                                size="small"
                                label={r.prediction}
                                color={r.prediction.toLowerCase() === 'anomaly' ? 'error' : 'success'}
                                variant="outlined"
                              />
                            </TableCell>
                            <TableCell>{r.top_deviation ?? NO_VALUE}</TableCell>
                          </TableRow>
                        ))
                      )}
                    </TableBody>
                  </Table>
                </PanelCard>
              </Grid>
            </Grid>
          </Section>

          {/* ─── Active investigations ─────────────────────────── */}
          <Section
            title="Active investigations"
            action={<Button onClick={() => navigate('/investigations')}>View all investigations</Button>}
          >
            <Grid container spacing={2}>
              <Grid item xs={12} md={4}>
                <ChartCard title="By status" height={240}>
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={statusChartData(data.active_investigations.counts_by_status)} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID_STROKE} />
                      <XAxis dataKey="name" tick={CHART_AXIS_TICK} />
                      <YAxis tick={CHART_AXIS_TICK} allowDecimals={false} />
                      <RechartsTooltip {...CHART_TOOLTIP_PROPS} />
                      <Bar dataKey="value" name="Investigations" radius={[4, 4, 0, 0]}>
                        {statusChartData(data.active_investigations.counts_by_status).map((d) => (
                          <Cell key={d.name} fill={d.fill} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </ChartCard>
              </Grid>
              <Grid item xs={12} md={8}>
                <PanelCard title="In flight">
                  <InvestigationTable items={data.active_investigations.items} emptyText="No active investigations" />
                </PanelCard>
              </Grid>
            </Grid>
          </Section>

          {/* ─── Threat intelligence ───────────────────────────── */}
          <Section
            title="Threat intelligence"
            subtitle={`Indicators observed over the last ${intel.window_days} days`}
          >
            <Alert severity="info" variant="outlined" sx={{ mb: 2, fontSize: '0.95rem' }}>
              <AlertTitle>About these indicators</AlertTitle>
              {intel.note}
            </Alert>
            <Grid container spacing={2}>
              <Grid item xs={12} md={4}>
                <PanelCard title="Risk indicators">
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Indicator</TableCell>
                        <TableCell align="right">Count</TableCell>
                        <TableCell>Last seen</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {intel.indicators.length === 0 ? (
                        <EmptyRow colSpan={3} text="No indicators observed" />
                      ) : (
                        intel.indicators.map((i) => (
                          <TableRow key={i.indicator} hover>
                            <TableCell>
                              <Chip size="small" color="warning" variant="outlined" label={i.indicator} />
                            </TableCell>
                            <TableCell align="right">{i.count.toLocaleString()}</TableCell>
                            <TableCell sx={{ whiteSpace: 'nowrap' }}>{formatDateTime(i.last_seen)}</TableCell>
                          </TableRow>
                        ))
                      )}
                    </TableBody>
                  </Table>
                </PanelCard>
              </Grid>
              <Grid item xs={12} md={4}>
                <PanelCard title="External destinations">
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Destination</TableCell>
                        <TableCell align="right">Events</TableCell>
                        <TableCell align="right">Users</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {intel.external_destinations.length === 0 ? (
                        <EmptyRow colSpan={3} text="No external destinations seen" />
                      ) : (
                        intel.external_destinations.map((d) => (
                          <TableRow key={d.destination} hover>
                            <TableCell sx={{ wordBreak: 'break-all' }}>{d.destination}</TableCell>
                            <TableCell align="right">{d.count.toLocaleString()}</TableCell>
                            <TableCell align="right">{d.users}</TableCell>
                          </TableRow>
                        ))
                      )}
                    </TableBody>
                  </Table>
                </PanelCard>
              </Grid>
              <Grid item xs={12} md={4}>
                <PanelCard title="Scoring pipeline">
                  <Stack spacing={1.5}>
                    <Stack direction="row" spacing={1}>
                      <Chip
                        size="small"
                        label={intel.pipeline.scheduler_enabled ? 'Scheduler enabled' : 'Scheduler disabled'}
                        color={intel.pipeline.scheduler_enabled ? 'success' : 'default'}
                      />
                      {intel.pipeline.running && <Chip size="small" label="Running now" color="info" />}
                    </Stack>
                    <PipelineRow label="Last success" value={formatDateTime(intel.pipeline.last_success_at)} />
                    <PipelineRow label="Next run" value={formatDateTime(intel.pipeline.next_run_at)} />
                    {intel.pipeline.last_error && (
                      <Alert severity="error" sx={{ wordBreak: 'break-word' }}>
                        {intel.pipeline.last_error}
                      </Alert>
                    )}
                  </Stack>
                </PanelCard>
              </Grid>
            </Grid>
          </Section>
        </>
      )}
    </DashboardShell>
  );
}

function PipelineRow({ label, value }: { label: string; value: string }) {
  return (
    <Box>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="body2">{value}</Typography>
    </Box>
  );
}
