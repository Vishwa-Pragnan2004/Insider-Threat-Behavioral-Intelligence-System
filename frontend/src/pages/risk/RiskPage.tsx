import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Grid,
  MenuItem,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import { GppMaybe, Groups, Refresh, Speed, Warning } from '@mui/icons-material';
import PageHeader from '../../components/common/PageHeader';
import StatCard from '../../components/common/StatCard';
import EmptyState from '../../components/common/EmptyState';
import { listEmployeeRisk } from '../../api/riskService';
import { apiErrorMessage } from '../../api/userService';
import { useAuth } from '../../hooks/useAuth';
import { hasPermission } from '../../utils/permissions';
import { EmployeeNameLink, useEmployeeAccountIndex } from '../employees/employeeShared';
import { LevelChip, RiskScoreChip, formatNumber } from '../dashboards/shared';
import {
  ContributionBar,
  EmployeeLink,
  TrendIndicator,
  componentColor,
  componentLabel,
  formatDay,
  modelComponents,
  useRiskModel,
  weightPct,
} from './riskShared';

const WINDOWS = [7, 30, 90] as const;
const PRIORITY_FILTERS = [
  { value: 0, label: 'All' },
  { value: 40, label: '≥ 40' },
  { value: 60, label: '≥ 60' },
  { value: 80, label: '≥ 80' },
];

/**
 * Insider Risk
 *
 * The risk queue: latest weighted insider risk score per employee, ranked by
 * priority (which lifts a single strong signal the weighted sum would bury).
 */
export default function RiskPage() {
  const [days, setDays] = useState<number>(30);
  const [minPriority, setMinPriority] = useState<number>(0);

  const { user } = useAuth();
  // Optional: resolve accounts to directory names when the viewer may read the directory.
  const employeeIndex = useEmployeeAccountIndex(hasPermission(user, 'employees:read'));

  const modelQuery = useRiskModel();
  const model = modelQuery.data;

  const query = useQuery({
    queryKey: ['risk', 'employees', { days, minPriority }],
    queryFn: () =>
      listEmployeeRisk({ days, limit: 500, ...(minPriority > 0 && { min_priority: minPriority }) }),
  });

  const employees = useMemo(
    () => [...(query.data?.employees ?? [])].sort((a, b) => b.priority - a.priority),
    [query.data],
  );

  const stats = useMemo(() => {
    const n = employees.length;
    return {
      scored: n,
      highPlus: employees.filter((e) => e.priority >= 60).length,
      critical: employees.filter((e) => e.priority >= 80).length,
      avgScore: n ? employees.reduce((s, e) => s + e.score, 0) / n : null,
    };
  }, [employees]);

  return (
    <Box>
      <PageHeader
        title="Insider risk"
        subtitle="Weighted insider risk score per employee, ranked by priority"
        actions={
          <Button
            startIcon={query.isFetching ? <CircularProgress size={16} /> : <Refresh />}
            onClick={() => query.refetch()}
            disabled={query.isFetching}
            variant="outlined"
            size="small"
          >
            Refresh
          </Button>
        }
      />

      <Box sx={{ mb: 3 }}>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
          Score = weighted sum of five components (each 0–100). Priority is the higher of the score and
          0.8 × the strongest live signal; alerts are raised at priority ≥ {model?.alert_min_priority ?? 60}.
        </Typography>
        <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
          {modelComponents(model).map((c) => (
            <Chip
              key={c.component}
              size="small"
              label={`${c.label} ${weightPct(c.weight)}`}
              sx={{
                bgcolor: `${componentColor(c.component)}1f`,
                color: componentColor(c.component),
                fontWeight: 600,
                fontSize: '0.7rem',
              }}
            />
          ))}
          {model?.version && (
            <Chip size="small" variant="outlined" label={`model ${model.version}`} sx={{ fontSize: '0.7rem' }} />
          )}
        </Stack>
      </Box>

      <Box sx={{ mb: 3, display: 'flex', gap: 2, flexWrap: 'wrap' }}>
        <TextField
          select
          size="small"
          label="Window"
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
          sx={{ minWidth: 140 }}
        >
          {WINDOWS.map((d) => (
            <MenuItem key={d} value={d}>
              Last {d} days
            </MenuItem>
          ))}
        </TextField>
        <TextField
          select
          size="small"
          label="Minimum priority"
          value={minPriority}
          onChange={(e) => setMinPriority(Number(e.target.value))}
          sx={{ minWidth: 160 }}
        >
          {PRIORITY_FILTERS.map((p) => (
            <MenuItem key={p.value} value={p.value}>
              {p.label}
            </MenuItem>
          ))}
        </TextField>
      </Box>

      <Grid container spacing={2} sx={{ mb: 3 }}>
        <Grid item xs={12} sm={6} md={3}>
          <StatCard label="Employees scored" value={String(stats.scored)} icon={<Groups />} />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <StatCard
            label="HIGH+ priority (≥ 60)"
            value={String(stats.highPlus)}
            icon={<Warning sx={{ color: '#f97316 !important' }} />}
            iconColor="rgba(249, 115, 22, 0.12)"
          />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <StatCard
            label="CRITICAL priority (≥ 80)"
            value={String(stats.critical)}
            icon={<GppMaybe sx={{ color: '#ef4444 !important' }} />}
            iconColor="rgba(239, 68, 68, 0.12)"
          />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <StatCard
            label="Average score"
            value={formatNumber(stats.avgScore, '', 1)}
            icon={<Speed />}
            iconColor="rgba(139, 92, 246, 0.12)"
          />
        </Grid>
      </Grid>

      <Box sx={{ bgcolor: 'background.paper', borderRadius: 2, overflow: 'hidden' }}>
        {query.isLoading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 8 }}>
            <CircularProgress />
          </Box>
        ) : query.isError ? (
          <Alert severity="error" sx={{ m: 2 }}>
            Failed to load risk scores: {apiErrorMessage(query.error)}
          </Alert>
        ) : employees.length === 0 ? (
          <EmptyState
            icon={<GppMaybe sx={{ fontSize: 56 }} />}
            title="No risk scores yet"
            description={
              minPriority > 0
                ? `No employee reached priority ≥ ${minPriority} in the last ${days} days.`
                : 'Scores appear once the detection and risk scoring pipeline has run on collected activity.'
            }
          />
        ) : (
          <Box sx={{ overflowX: 'auto' }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>#</TableCell>
                  <TableCell>Employee</TableCell>
                  <TableCell align="center">Priority</TableCell>
                  <TableCell align="center">Score</TableCell>
                  <TableCell>Level</TableCell>
                  <TableCell>Trend</TableCell>
                  <TableCell>Dominant component</TableCell>
                  <TableCell>Contributions</TableCell>
                  <TableCell>Last scored</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {employees.map((e, i) => (
                  <TableRow key={e.user_id} hover>
                    <TableCell sx={{ color: 'text.secondary' }}>{i + 1}</TableCell>
                    <TableCell>
                      <EmployeeLink userId={e.user_id} />
                      {(() => {
                        const person = employeeIndex.get(e.user_id.toLowerCase());
                        return person ? (
                          <Typography variant="caption" component="div" color="text.secondary" noWrap>
                            <EmployeeNameLink employee={person} /> · {person.employee_id}
                          </Typography>
                        ) : null;
                      })()}
                    </TableCell>
                    <TableCell align="center">
                      <RiskScoreChip score={e.priority} />
                    </TableCell>
                    <TableCell align="center" sx={{ fontFamily: 'monospace', fontWeight: 600 }}>
                      {formatNumber(e.score, '', 1)}
                    </TableCell>
                    <TableCell>
                      <LevelChip level={e.level} />
                    </TableCell>
                    <TableCell>
                      <TrendIndicator trend={e.trend} />
                    </TableCell>
                    <TableCell sx={{ whiteSpace: 'nowrap' }}>{componentLabel(model, e.dominant_component)}</TableCell>
                    <TableCell>
                      <ContributionBar components={e.components} model={model} />
                    </TableCell>
                    <TableCell sx={{ whiteSpace: 'nowrap' }}>{formatDay(e.day)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Box>
        )}
      </Box>
    </Box>
  );
}
