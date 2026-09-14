import { useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  Divider,
  Grid,
  LinearProgress,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { ArrowBack, GppMaybe, Refresh, Speed, TrendingUp, Flag } from '@mui/icons-material';
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from 'recharts';
import PageHeader from '../../components/common/PageHeader';
import StatCard from '../../components/common/StatCard';
import ChartCard from '../../components/common/ChartCard';
import EmptyState from '../../components/common/EmptyState';
import { getEmployeeRisk } from '../../api/riskService';
import { apiErrorMessage } from '../../api/userService';
import type { Finding } from '../../types/risk';
import {
  CHART_AXIS_TICK,
  CHART_GRID_STROKE,
  CHART_TOOLTIP_PROPS,
  ChartEmpty,
  LevelChip,
  NO_VALUE,
  PanelCard,
  RiskScoreChip,
  formatNumber,
  riskColor,
} from '../dashboards/shared';
import {
  CategoryChip,
  DEFAULT_ALERT_MIN_PRIORITY,
  EvidenceToggle,
  TrendIndicator,
  componentColor,
  componentLabel,
  formatDay,
  modelComponents,
  useRiskModel,
  weightPct,
} from './riskShared';

const WINDOWS = [30, 90] as const;

/** Route params may arrive still percent-encoded depending on the router version. */
function decodeParam(value: string | undefined): string {
  if (!value) return '';
  if (!/%[0-9A-Fa-f]{2}/.test(value)) return value;
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

/**
 * Employee risk detail
 *
 * One employee's insider risk: latest score, how it moved, what drives it,
 * and the detection findings behind it.
 */
export default function EmployeeRiskPage() {
  const navigate = useNavigate();
  const userId = decodeParam(useParams<{ userId: string }>().userId);
  const [days, setDays] = useState<number>(30);

  const modelQuery = useRiskModel();
  const model = modelQuery.data;
  const alertMinPriority = model?.alert_min_priority ?? DEFAULT_ALERT_MIN_PRIORITY;

  const query = useQuery({
    queryKey: ['risk', 'employee', userId, days],
    queryFn: () => getEmployeeRisk(userId, days),
    enabled: !!userId,
  });
  const data = query.data;
  const latest = data?.latest ?? null;

  const chartData = useMemo(
    () => (data?.series ?? []).map((s) => ({ day: s.day, score: s.score, priority: s.priority })),
    [data],
  );

  const findingsByDay = useMemo(() => {
    const groups = new Map<string, Finding[]>();
    for (const f of data?.findings ?? []) {
      const key = f.day.slice(0, 10);
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key)!.push(f);
    }
    return [...groups.entries()]
      .sort(([a], [b]) => b.localeCompare(a))
      .map(([day, items]) => ({ day, items: [...items].sort((a, b) => b.severity - a.severity) }));
  }, [data]);

  return (
    <Box>
      <PageHeader
        title={userId || 'Employee'}
        subtitle="Insider risk score, drivers and detection findings"
        actions={
          <Stack direction="row" spacing={1} alignItems="center">
            <Button startIcon={<ArrowBack />} size="small" onClick={() => navigate('/risk')}>
              Risk queue
            </Button>
            <TextField
              select
              size="small"
              label="Window"
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
              sx={{ minWidth: 130 }}
            >
              {WINDOWS.map((d) => (
                <MenuItem key={d} value={d}>
                  Last {d} days
                </MenuItem>
              ))}
            </TextField>
            <Button
              startIcon={query.isFetching ? <CircularProgress size={16} /> : <Refresh />}
              onClick={() => query.refetch()}
              disabled={query.isFetching}
              variant="outlined"
              size="small"
            >
              Refresh
            </Button>
          </Stack>
        }
      />

      {query.isLoading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 8 }}>
          <CircularProgress />
        </Box>
      ) : query.isError ? (
        <Alert severity="error">Failed to load employee risk: {apiErrorMessage(query.error)}</Alert>
      ) : !data ? null : (
        <>
          {!latest && (
            <Alert severity="info" sx={{ mb: 3 }}>
              No risk score for this employee in the last {days} days. Scores appear once the pipeline has run on
              their collected activity.
            </Alert>
          )}

          {/* ─── Latest ─────────────────────────────────────────── */}
          <Grid container spacing={2} sx={{ mb: 3 }}>
            <Grid item xs={12} sm={6} md={3}>
              <StatCard
                label={`Priority${latest ? ` · alerts at ≥ ${alertMinPriority}` : ''}`}
                value={formatNumber(latest?.priority, '', 1)}
                icon={<Flag sx={{ color: `${riskColor(latest?.priority)} !important` }} />}
                iconColor="rgba(239, 68, 68, 0.12)"
              />
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <StatCard
                label="Insider risk score"
                value={formatNumber(latest?.score, '', 1)}
                icon={<Speed sx={{ color: `${riskColor(latest?.score)} !important` }} />}
                iconColor="rgba(139, 92, 246, 0.12)"
              />
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Card sx={{ height: '100%' }}>
                <CardContent sx={{ p: 3 }}>
                  <GppMaybe sx={{ color: 'text.secondary', mb: 2 }} />
                  <Box sx={{ mb: 0.5, minHeight: 40, display: 'flex', alignItems: 'center' }}>
                    {latest ? <LevelChip level={latest.level} /> : <Typography variant="h4">{NO_VALUE}</Typography>}
                  </Box>
                  <Typography variant="body2" color="text.secondary">
                    Level{latest ? ` · scored ${formatDay(latest.day)}` : ''}
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Card sx={{ height: '100%' }}>
                <CardContent sx={{ p: 3 }}>
                  <TrendingUp sx={{ color: 'text.secondary', mb: 2 }} />
                  <Box sx={{ mb: 0.5, minHeight: 40, display: 'flex', alignItems: 'center', '& *': { fontSize: '1.5rem !important' } }}>
                    <TrendIndicator trend={latest?.trend} />
                  </Box>
                  <Typography variant="body2" color="text.secondary">
                    Trend vs previous score
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
          </Grid>

          <Grid container spacing={2} sx={{ mb: 3 }}>
            {/* ─── Series ─────────────────────────────────────── */}
            <Grid item xs={12} md={7}>
              <ChartCard title="Score and priority" subtitle={`Daily, last ${days} days`} height={300}>
                {chartData.length === 0 ? (
                  <ChartEmpty text="No scores in this window" />
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={chartData} margin={{ top: 8, right: 16, left: -16, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID_STROKE} />
                      <XAxis dataKey="day" tick={CHART_AXIS_TICK} tickFormatter={(d: string) => d.slice(5)} />
                      <YAxis domain={[0, 100]} tick={CHART_AXIS_TICK} />
                      <RechartsTooltip {...CHART_TOOLTIP_PROPS} formatter={(v) => (typeof v === 'number' ? v.toFixed(1) : v)} />
                      <Legend />
                      <ReferenceLine
                        y={alertMinPriority}
                        stroke="#ef4444"
                        strokeDasharray="6 4"
                        label={{ value: `alert ≥ ${alertMinPriority}`, fill: '#ef4444', fontSize: 11, position: 'insideTopRight' }}
                      />
                      <Line type="monotone" dataKey="priority" name="Priority" stroke="#f97316" strokeWidth={2} dot={chartData.length < 40} />
                      <Line type="monotone" dataKey="score" name="Score" stroke="#8b5cf6" strokeWidth={2} dot={chartData.length < 40} />
                    </LineChart>
                  </ResponsiveContainer>
                )}
              </ChartCard>
            </Grid>

            {/* ─── Component breakdown ────────────────────────── */}
            <Grid item xs={12} md={5}>
              <PanelCard title="Component breakdown">
                <Stack spacing={1.5} sx={{ pt: 1 }}>
                  {modelComponents(model).map((c) => {
                    const value = latest?.components?.[c.component];
                    const contribution = value === undefined ? undefined : value * c.weight;
                    const color = componentColor(c.component);
                    return (
                      <Box key={c.component}>
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5, gap: 1 }}>
                          <Typography variant="body2" sx={{ fontWeight: latest?.dominant_component === c.component ? 700 : 500 }}>
                            {c.label}{' '}
                            <Typography component="span" variant="caption" color="text.secondary">
                              ({weightPct(c.weight)})
                            </Typography>
                          </Typography>
                          <Typography variant="body2" sx={{ fontFamily: 'monospace', whiteSpace: 'nowrap' }}>
                            {formatNumber(value, '', 0)}
                            <Typography component="span" variant="caption" color="text.secondary">
                              {' '}→ +{formatNumber(contribution, '', 1)}
                            </Typography>
                          </Typography>
                        </Box>
                        <LinearProgress
                          variant="determinate"
                          value={Math.max(0, Math.min(100, value ?? 0))}
                          sx={{
                            height: 8,
                            borderRadius: 1,
                            bgcolor: 'rgba(148,163,184,0.15)',
                            '& .MuiLinearProgress-bar': { bgcolor: color, borderRadius: 1 },
                          }}
                        />
                      </Box>
                    );
                  })}
                  <Typography variant="caption" color="text.secondary">
                    Bar = component value (0–100); → + = weighted contribution to the score.
                  </Typography>
                </Stack>
              </PanelCard>
            </Grid>
          </Grid>

          {/* ─── Top signals ──────────────────────────────────── */}
          <Box sx={{ mb: 3 }}>
            <PanelCard title="Top signals">
              {!latest || latest.top_signals.length === 0 ? (
                <Typography color="text.secondary" sx={{ py: 2 }}>
                  No live signals.
                </Typography>
              ) : (
                <Stack divider={<Divider flexItem />} spacing={1}>
                  {latest.top_signals.map((s, i) => (
                    <Box key={`${s.label}-${s.day}-${i}`} sx={{ display: 'flex', gap: 2, alignItems: 'center', flexWrap: 'wrap' }}>
                      <RiskScoreChip score={s.severity} />
                      <Box sx={{ flexGrow: 1, minWidth: 200 }}>
                        <Typography variant="body2" sx={{ fontWeight: 600 }}>
                          {s.label}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          {s.component_label || componentLabel(model, s.component)} · {formatDay(s.day)} · current weight{' '}
                          {s.current_weight.toFixed(2)}
                          {s.reference ? ` · ${s.reference}` : ''}
                        </Typography>
                      </Box>
                      {s.category && <CategoryChip label={s.category} />}
                    </Box>
                  ))}
                </Stack>
              )}
            </PanelCard>
          </Box>

          {/* ─── Findings timeline ────────────────────────────── */}
          <PanelCard title={`Findings (${data.findings.length})`}>
            {findingsByDay.length === 0 ? (
              <EmptyState title="No findings" description={`No detections for this employee in the last ${days} days.`} />
            ) : (
              <Stack spacing={3} sx={{ pt: 1 }}>
                {findingsByDay.map((group) => (
                  <Box key={group.day}>
                    <Typography variant="overline" color="text.secondary" sx={{ fontWeight: 700 }}>
                      {formatDay(group.day)}
                    </Typography>
                    <Stack spacing={1.5} sx={{ borderLeft: 2, borderColor: 'divider', pl: 2, mt: 0.5 }}>
                      {group.items.map((f) => (
                        <Box key={f.id}>
                          <Stack direction="row" spacing={1} alignItems="center" useFlexGap flexWrap="wrap" sx={{ mb: 0.5 }}>
                            <RiskScoreChip score={f.severity} />
                            <CategoryChip label={f.category_label || f.category} />
                            <Typography variant="body2" sx={{ fontWeight: 600 }}>
                              {f.title}
                            </Typography>
                          </Stack>
                          <Typography variant="body2" color="text.secondary">
                            {f.description}
                          </Typography>
                          <Typography variant="caption" color="text.disabled" sx={{ display: 'block' }}>
                            {f.engine} · {f.detector} v{f.detector_version}
                          </Typography>
                          <EvidenceToggle evidence={f.evidence} eventIds={f.event_ids} />
                        </Box>
                      ))}
                    </Stack>
                  </Box>
                ))}
              </Stack>
            )}
          </PanelCard>
        </>
      )}
    </Box>
  );
}
