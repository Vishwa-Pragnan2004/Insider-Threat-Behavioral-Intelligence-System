import type { ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Tooltip,
  Typography,
} from '@mui/material';
import { Refresh } from '@mui/icons-material';
import PageHeader from '../../components/common/PageHeader';
import { apiErrorMessage } from '../../api/userService';
import type { InvestigationBrief, SeverityCounts, UserRisk } from '../../types/dashboards';

/**
 * Building blocks shared by the role dashboards: page shell, section
 * headings, risk colouring and the compact tables that appear on more than
 * one dashboard.
 */

/** Every role dashboard polls at this interval. */
export const DASHBOARD_REFETCH_MS = 60_000;

// ─── Formatting ───────────────────────────────────────────────

export const NO_VALUE = '—';

export function formatDateTime(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleString() : NO_VALUE;
}

export function formatNumber(value: number | null | undefined, suffix = '', digits = 0): string {
  return value === null || value === undefined ? NO_VALUE : `${value.toFixed(digits)}${suffix}`;
}

// ─── Risk colours ─────────────────────────────────────────────

export const RISK_COLORS: Record<keyof SeverityCounts, string> = {
  LOW: '#10b981',
  MEDIUM: '#f59e0b',
  HIGH: '#f97316',
  CRITICAL: '#ef4444',
};

export const INVESTIGATION_STATUS_COLORS: Record<string, string> = {
  OPEN: '#3b82f6',
  IN_PROGRESS: '#8b5cf6',
  RESOLVED: '#10b981',
  CLOSED: '#64748b',
};

/** LOW < 40, MEDIUM < 60, HIGH < 80, otherwise CRITICAL. */
export function riskLevelFor(score: number): keyof SeverityCounts {
  if (score >= 80) return 'CRITICAL';
  if (score >= 60) return 'HIGH';
  if (score >= 40) return 'MEDIUM';
  return 'LOW';
}

export function riskColor(score: number | null | undefined): string {
  return score === null || score === undefined ? '#64748b' : RISK_COLORS[riskLevelFor(score)];
}

/** Turns {LOW: n, ...} into chart rows, keeping severity order. */
export function severityChartData(counts: SeverityCounts) {
  return (Object.keys(RISK_COLORS) as (keyof SeverityCounts)[]).map((name) => ({
    name,
    value: counts[name] ?? 0,
    fill: RISK_COLORS[name],
  }));
}

export function statusChartData(counts: Record<string, number>) {
  return Object.entries(counts).map(([name, value]) => ({
    name: name.replace('_', ' '),
    value,
    fill: INVESTIGATION_STATUS_COLORS[name] ?? '#64748b',
  }));
}

// ─── Recharts dark-theme styling (matches DashboardPage) ──────

export const CHART_GRID_STROKE = 'rgba(255,255,255,0.08)';
export const CHART_AXIS_TICK = { fill: '#94a3b8', fontSize: 12 };
export const CHART_TOOLTIP_PROPS = {
  contentStyle: { background: '#1e293b', border: '1px solid #334155', borderRadius: 8 },
  labelStyle: { color: '#f1f5f9' },
};

// ─── Chips ────────────────────────────────────────────────────

export function RiskScoreChip({ score }: { score: number | null | undefined }) {
  const color = riskColor(score);
  return (
    <Chip
      size="small"
      label={score === null || score === undefined ? NO_VALUE : Math.round(score)}
      sx={{
        bgcolor: `${color}1f`,
        color,
        fontWeight: 700,
        fontFamily: '"JetBrains Mono", monospace',
        minWidth: 44,
      }}
    />
  );
}

export function LevelChip({ level }: { level: string }) {
  const color = RISK_COLORS[level.toUpperCase() as keyof SeverityCounts] ?? '#64748b';
  return (
    <Chip
      size="small"
      label={level.toUpperCase()}
      sx={{ bgcolor: `${color}1f`, color, fontWeight: 600, fontSize: '0.7rem' }}
    />
  );
}

export function LearningChip() {
  return (
    <Tooltip title="Still in the learning period — scored against the global baseline until a personal baseline exists">
      <Chip size="small" label="learning" color="info" variant="outlined" sx={{ ml: 1, height: 20 }} />
    </Tooltip>
  );
}

export function StatusChip({ status }: { status: string }) {
  const color = INVESTIGATION_STATUS_COLORS[status] ?? '#64748b';
  return (
    <Chip
      size="small"
      label={status.replace('_', ' ')}
      sx={{ bgcolor: `${color}1f`, color, fontWeight: 600, fontSize: '0.7rem' }}
    />
  );
}

// ─── Layout ───────────────────────────────────────────────────

interface DashboardShellProps {
  title: string;
  subtitle: string;
  generatedAt: string | undefined;
  isLoading: boolean;
  isFetching: boolean;
  error: unknown;
  onRefresh: () => void;
  children: ReactNode;
}

/** Page header with "last updated", refresh, and loading/error handling. */
export function DashboardShell({
  title,
  subtitle,
  generatedAt,
  isLoading,
  isFetching,
  error,
  onRefresh,
  children,
}: DashboardShellProps) {
  return (
    <Box>
      <PageHeader
        title={title}
        subtitle={subtitle}
        actions={
          <Stack direction="row" spacing={2} alignItems="center">
            <Typography variant="caption" color="text.secondary">
              Last updated {formatDateTime(generatedAt)}
            </Typography>
            <Button
              startIcon={isFetching ? <CircularProgress size={16} /> : <Refresh />}
              onClick={onRefresh}
              disabled={isFetching}
            >
              Refresh
            </Button>
          </Stack>
        }
      />

      {error ? (
        <Alert severity="error" sx={{ mb: 2 }}>
          Couldn't load this dashboard: {apiErrorMessage(error)}
        </Alert>
      ) : null}

      {isLoading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 8 }}>
          <CircularProgress />
        </Box>
      ) : (
        children
      )}
    </Box>
  );
}

interface SectionProps {
  title: string;
  subtitle?: string;
  action?: ReactNode;
  children: ReactNode;
}

export function Section({ title, subtitle, action, children }: SectionProps) {
  return (
    <Box component="section" sx={{ mb: 4 }}>
      <Box
        sx={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: { xs: 'flex-start', sm: 'flex-end' },
          flexDirection: { xs: 'column', sm: 'row' },
          gap: 1,
          mb: 2,
          pb: 1,
          borderBottom: 1,
          borderColor: 'divider',
        }}
      >
        <Box>
          <Typography variant="h6" sx={{ fontWeight: 700 }}>
            {title}
          </Typography>
          {subtitle && (
            <Typography variant="body2" color="text.secondary">
              {subtitle}
            </Typography>
          )}
        </Box>
        {action}
      </Box>
      {children}
    </Box>
  );
}

/** A titled card holding a compact table or list. */
export function PanelCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Card sx={{ height: '100%' }}>
      <CardContent sx={{ '&:last-child': { pb: 2 } }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>
          {title}
        </Typography>
        <Box sx={{ overflowX: 'auto' }}>{children}</Box>
      </CardContent>
    </Card>
  );
}

export function EmptyRow({ colSpan, text }: { colSpan: number; text: string }) {
  return (
    <TableRow>
      <TableCell colSpan={colSpan} align="center" sx={{ color: 'text.secondary', py: 3 }}>
        {text}
      </TableCell>
    </TableRow>
  );
}

export function ChartEmpty({ text = 'No data' }: { text?: string }) {
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
      <Typography color="text.secondary">{text}</Typography>
    </Box>
  );
}

// ─── Shared tables ────────────────────────────────────────────

export function UserRiskTable({ users, emptyText }: { users: UserRisk[]; emptyText: string }) {
  return (
    <Table size="small">
      <TableHead>
        <TableRow>
          <TableCell>User</TableCell>
          <TableCell align="center">Max</TableCell>
          <TableCell align="center">Latest</TableCell>
          <TableCell>Level</TableCell>
          <TableCell align="right">Anomalies</TableCell>
          <TableCell>Last scored</TableCell>
        </TableRow>
      </TableHead>
      <TableBody>
        {users.length === 0 ? (
          <EmptyRow colSpan={6} text={emptyText} />
        ) : (
          users.map((u) => (
            <TableRow key={u.user_id} hover>
              <TableCell sx={{ whiteSpace: 'nowrap' }}>
                {u.user_id}
                {u.baseline_source === 'global' && <LearningChip />}
              </TableCell>
              <TableCell align="center">
                <RiskScoreChip score={u.max_risk_score} />
              </TableCell>
              <TableCell align="center">
                <RiskScoreChip score={u.latest_risk_score} />
              </TableCell>
              <TableCell>
                <LevelChip level={u.risk_level} />
              </TableCell>
              <TableCell align="right">
                {u.anomalies} / {u.results}
              </TableCell>
              <TableCell sx={{ whiteSpace: 'nowrap' }}>{formatDateTime(u.last_scored_at)}</TableCell>
            </TableRow>
          ))
        )}
      </TableBody>
    </Table>
  );
}

export function InvestigationTable({
  items,
  emptyText,
}: {
  items: InvestigationBrief[];
  emptyText: string;
}) {
  const navigate = useNavigate();
  return (
    <Table size="small">
      <TableHead>
        <TableRow>
          <TableCell>Title</TableCell>
          <TableCell>Severity</TableCell>
          <TableCell>Status</TableCell>
          <TableCell>Assignee</TableCell>
          <TableCell>Users</TableCell>
          <TableCell>Updated</TableCell>
        </TableRow>
      </TableHead>
      <TableBody>
        {items.length === 0 ? (
          <EmptyRow colSpan={6} text={emptyText} />
        ) : (
          items.map((inv) => (
            <TableRow
              key={inv.id}
              hover
              onClick={() => navigate(`/investigations/${inv.id}`)}
              sx={{ cursor: 'pointer' }}
            >
              <TableCell sx={{ fontWeight: 600 }}>{inv.title}</TableCell>
              <TableCell>
                <LevelChip level={inv.severity} />
              </TableCell>
              <TableCell>
                <StatusChip status={inv.status} />
              </TableCell>
              <TableCell>{inv.assigned_to ?? 'Unassigned'}</TableCell>
              <TableCell>{inv.related_user_ids.join(', ') || NO_VALUE}</TableCell>
              <TableCell sx={{ whiteSpace: 'nowrap' }}>{formatDateTime(inv.updated_at)}</TableCell>
            </TableRow>
          ))
        )}
      </TableBody>
    </Table>
  );
}
