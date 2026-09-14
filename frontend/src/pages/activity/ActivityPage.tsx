import { useEffect, useState } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Grid,
  MenuItem,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TablePagination,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import {
  Devices,
  Event as EventIcon,
  Flag,
  People,
  Refresh,
  Timeline,
  Warning,
} from '@mui/icons-material';
import { Area, AreaChart, ResponsiveContainer, Tooltip as RechartsTooltip, XAxis } from 'recharts';
import PageHeader from '../../components/common/PageHeader';
import StatCard from '../../components/common/StatCard';
import EmptyState from '../../components/common/EmptyState';
import { getActivitySummary, listActivityEvents } from '../../api/activityService';
import { apiErrorMessage } from '../../api/userService';
import type { ActivityEvent, ActivityEventParams } from '../../types/activity';

/**
 * Activity
 *
 * The raw endpoint and CERT events as they're ingested, so operators can
 * confirm the ITBIS agent (or a CERT upload) is actually delivering data
 * before anything is scored. Refreshes every 30 seconds.
 */

const REFETCH_MS = 30_000;
const NO_VALUE = '—';

/** datetime-local gives local wall-clock time; the API wants ISO-8601 (UTC). */
function toIso(local: string): string | undefined {
  if (!local) return undefined;
  const date = new Date(local);
  return Number.isNaN(date.getTime()) ? undefined : date.toISOString();
}

/** `value`, once it has stopped changing for `delayMs` — so typing doesn't fire a request per key. */
function useDebounced<T>(value: T, delayMs = 400): T {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setSettled(value), delayMs);
    return () => window.clearTimeout(timer);
  }, [value, delayMs]);
  return settled;
}

export default function ActivityPage() {
  const [userId, setUserId] = useState('');
  const [eventType, setEventType] = useState('');
  const [sourceDataset, setSourceDataset] = useState('');
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);
  const [selected, setSelected] = useState<ActivityEvent | null>(null);
  const typedUserId = useDebounced(userId.trim());
  const typedSource = useDebounced(sourceDataset.trim());

  const params: ActivityEventParams = {
    user_id: typedUserId || undefined,
    event_type: eventType || undefined,
    source_dataset: typedSource || undefined,
    start: toIso(start),
    end: toIso(end),
    skip: page * rowsPerPage,
    limit: rowsPerPage,
  };

  const summaryQuery = useQuery({
    queryKey: ['activity-summary', 24],
    queryFn: () => getActivitySummary(24),
    refetchInterval: REFETCH_MS,
  });

  const eventsQuery = useQuery({
    queryKey: ['activity-events', params],
    queryFn: () => listActivityEvents(params),
    refetchInterval: REFETCH_MS,
    placeholderData: keepPreviousData,
  });

  const summary = summaryQuery.data;
  const events = eventsQuery.data?.events ?? [];
  const eventTypes = Object.keys(summary?.by_event_type ?? {}).sort();
  const hasFilters = !!(userId || eventType || sourceDataset || start || end);

  // Any filter change goes back to the first page.
  const withReset = (setter: (value: string) => void) => (value: string) => {
    setter(value);
    setPage(0);
  };

  const refresh = () => {
    summaryQuery.refetch();
    eventsQuery.refetch();
  };

  return (
    <Box>
      <PageHeader
        title="Activity"
        subtitle="Raw endpoint and CERT events as they arrive"
        actions={
          <Button
            startIcon={eventsQuery.isFetching ? <CircularProgress size={16} /> : <Refresh />}
            onClick={refresh}
            disabled={eventsQuery.isFetching}
          >
            Refresh
          </Button>
        }
      />

      {/* Summary strip — last 24 hours */}
      <Grid container spacing={2} sx={{ mb: 3 }}>
        <Grid item xs={12} sm={6} md={3} lg={2}>
          <StatCard
            label="Events (24h)"
            value={summary ? summary.total.toLocaleString() : NO_VALUE}
            icon={<EventIcon />}
          />
        </Grid>
        <Grid item xs={12} sm={6} md={3} lg={2}>
          <StatCard
            label="Flagged (24h)"
            value={summary ? summary.flagged.toLocaleString() : NO_VALUE}
            icon={<Flag sx={{ color: '#f97316 !important' }} />}
            iconColor="rgba(249, 115, 22, 0.12)"
          />
        </Grid>
        <Grid item xs={12} sm={6} md={3} lg={2}>
          <StatCard
            label="Active users"
            value={summary ? String(summary.active_users) : NO_VALUE}
            icon={<People />}
            iconColor="rgba(139, 92, 246, 0.12)"
          />
        </Grid>
        <Grid item xs={12} sm={6} md={3} lg={2}>
          <StatCard
            label="Active devices"
            value={summary ? String(summary.active_devices) : NO_VALUE}
            icon={<Devices />}
            iconColor="rgba(16, 185, 129, 0.12)"
          />
        </Grid>
        <Grid item xs={12} lg={4}>
          <Card sx={{ height: '100%' }}>
            <CardContent sx={{ '&:last-child': { pb: 2 } }}>
              <Typography variant="body2" color="text.secondary">
                Events per hour
              </Typography>
              <Box sx={{ height: 90, mt: 1 }}>
                {summary && summary.hourly.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={summary.hourly}>
                      <XAxis dataKey="hour" hide />
                      <RechartsTooltip
                        contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8 }}
                        labelStyle={{ color: '#f1f5f9' }}
                        labelFormatter={(label) => new Date(String(label)).toLocaleString()}
                      />
                      <Area
                        type="monotone"
                        dataKey="count"
                        name="Events"
                        stroke="#3b82f6"
                        fill="rgba(59, 130, 246, 0.25)"
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                ) : (
                  <Typography variant="caption" color="text.disabled">
                    {summaryQuery.isLoading ? 'Loading…' : 'No events in the last 24 hours'}
                  </Typography>
                )}
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Filters */}
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ mb: 2 }} flexWrap="wrap" useFlexGap>
        <TextField
          size="small"
          label="User ID"
          value={userId}
          onChange={(e) => withReset(setUserId)(e.target.value)}
        />
        <TextField
          select
          size="small"
          label="Event type"
          value={eventType}
          onChange={(e) => withReset(setEventType)(e.target.value)}
          sx={{ minWidth: 180 }}
        >
          <MenuItem value="">All</MenuItem>
          {eventTypes.map((t) => (
            <MenuItem key={t} value={t}>
              {t}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          size="small"
          label="Source dataset"
          value={sourceDataset}
          onChange={(e) => withReset(setSourceDataset)(e.target.value)}
        />
        <TextField
          size="small"
          type="datetime-local"
          label="From"
          value={start}
          onChange={(e) => withReset(setStart)(e.target.value)}
          InputLabelProps={{ shrink: true }}
        />
        <TextField
          size="small"
          type="datetime-local"
          label="To"
          value={end}
          onChange={(e) => withReset(setEnd)(e.target.value)}
          InputLabelProps={{ shrink: true }}
        />
        {hasFilters && (
          <Button
            onClick={() => {
              setUserId('');
              setEventType('');
              setSourceDataset('');
              setStart('');
              setEnd('');
              setPage(0);
            }}
          >
            Clear filters
          </Button>
        )}
      </Stack>

      {eventsQuery.isError && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {apiErrorMessage(eventsQuery.error)}
        </Alert>
      )}

      {eventsQuery.isLoading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}>
          <CircularProgress />
        </Box>
      ) : events.length === 0 ? (
        <EmptyState
          icon={<Timeline sx={{ fontSize: 48 }} />}
          title={hasFilters ? 'No events match these filters' : 'No events yet'}
          description={
            hasFilters
              ? 'Try widening the time range or clearing a filter.'
              : 'No events yet — start the ITBIS agent or upload CERT data.'
          }
        />
      ) : (
        <Card>
          <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Time</TableCell>
                  <TableCell>User</TableCell>
                  <TableCell>Event type</TableCell>
                  <TableCell>Target</TableCell>
                  <TableCell>Device</TableCell>
                  <TableCell>Source</TableCell>
                  <TableCell>Result</TableCell>
                  <TableCell>Risk indicators</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {events.map((ev) => (
                  <TableRow
                    key={ev.id}
                    hover
                    onClick={() => setSelected(ev)}
                    sx={{ cursor: 'pointer' }}
                  >
                    <TableCell sx={{ whiteSpace: 'nowrap' }}>
                      {new Date(ev.timestamp).toLocaleString()}
                    </TableCell>
                    <TableCell>{ev.user_id}</TableCell>
                    <TableCell>
                      <Chip size="small" label={ev.event_type} variant="outlined" />
                    </TableCell>
                    <TableCell
                      sx={{ maxWidth: 280, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                      title={ev.target_resource ?? undefined}
                    >
                      {ev.target_resource ?? NO_VALUE}
                    </TableCell>
                    <TableCell>{ev.device_name ?? ev.device_id ?? NO_VALUE}</TableCell>
                    <TableCell>{ev.source_dataset}</TableCell>
                    <TableCell>{ev.result ?? NO_VALUE}</TableCell>
                    <TableCell>
                      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                        {ev.risk_indicators.map((ri) => (
                          <Chip
                            key={ri}
                            size="small"
                            color="warning"
                            variant="outlined"
                            icon={<Warning sx={{ fontSize: 14 }} />}
                            label={ri}
                            sx={{ height: 22, fontSize: '0.7rem' }}
                          />
                        ))}
                      </Box>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
          <TablePagination
            component="div"
            count={eventsQuery.data?.total ?? 0}
            page={page}
            rowsPerPage={rowsPerPage}
            rowsPerPageOptions={[25, 50, 100]}
            onPageChange={(_, next) => setPage(next)}
            onRowsPerPageChange={(e) => {
              setRowsPerPage(parseInt(e.target.value, 10));
              setPage(0);
            }}
          />
        </Card>
      )}

      {/* Event detail */}
      <Dialog open={!!selected} onClose={() => setSelected(null)} maxWidth="md" fullWidth>
        <DialogTitle>
          {selected?.event_type} · {selected?.user_id}
        </DialogTitle>
        <DialogContent dividers>
          {selected && (
            <Stack spacing={2}>
              <Grid container spacing={1}>
                {(
                  [
                    ['Time', new Date(selected.timestamp).toLocaleString()],
                    ['Ingested', selected.ingested_at ? new Date(selected.ingested_at).toLocaleString() : NO_VALUE],
                    ['Event ID', selected.event_id],
                    ['Device', selected.device_name ?? selected.device_id],
                    ['Target', selected.target_resource],
                    ['Target type', selected.target_type],
                    ['Action', selected.action],
                    ['Result', selected.result],
                    ['IP address', selected.ip_address],
                    ['Remote', selected.is_remote === null ? null : selected.is_remote ? 'Yes' : 'No'],
                    ['Source', selected.source_dataset],
                  ] as [string, string | null][]
                ).map(([label, value]) => (
                  <Grid item xs={12} sm={6} key={label}>
                    <Typography variant="caption" color="text.secondary">
                      {label}
                    </Typography>
                    <Typography variant="body2" sx={{ wordBreak: 'break-all' }}>
                      {value ?? NO_VALUE}
                    </Typography>
                  </Grid>
                ))}
              </Grid>
              <JsonBlock label="Tags" value={selected.tags} />
              <JsonBlock label="Enrichments" value={selected.enrichments} />
            </Stack>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSelected(null)}>Close</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

function JsonBlock({ label, value }: { label: string; value: unknown }) {
  return (
    <Box>
      <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
        {label}
      </Typography>
      <Box
        component="pre"
        sx={{
          m: 0,
          p: 1.5,
          borderRadius: 1,
          bgcolor: 'rgba(15, 23, 42, 0.6)',
          border: 1,
          borderColor: 'divider',
          fontFamily: '"JetBrains Mono", monospace',
          fontSize: '0.8rem',
          overflowX: 'auto',
          maxHeight: 320,
        }}
      >
        {JSON.stringify(value ?? null, null, 2)}
      </Box>
    </Box>
  );
}
