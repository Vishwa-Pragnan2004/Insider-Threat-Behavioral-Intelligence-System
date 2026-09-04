import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Box,
  Typography,
  Table,
  TableHead,
  TableBody,
  TableRow,
  TableCell,
  TableSortLabel,
  TablePagination,
  Chip,
  IconButton,
  Tooltip,
  TextField,
  MenuItem,
  Button,
  Drawer,
  Divider,
  Stack,
  CircularProgress,
  Alert,
} from '@mui/material';
import RefreshIcon from '@mui/icons-material/Refresh';
import CloseIcon from '@mui/icons-material/Close';
import VisibilityIcon from '@mui/icons-material/Visibility';
import PageHeader from '../../components/common/PageHeader';
import SeverityBadge from '../../components/common/SeverityBadge';
import StatusBadge from '../../components/common/StatusBadge';
import EmptyState from '../../components/common/EmptyState';
import type { AlertSeverity, AlertStatus } from '../../types';
import { listAlerts, acknowledgeAlert, updateAlertStatus } from '../../api/alertService';
import type { Alert as AlertType, AlertDeviation, AlertListParams } from '../../types/alert';

const SEVERITIES: AlertSeverity[] = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'];
const STATUSES: AlertStatus[] = ['OPEN', 'ACKNOWLEDGED', 'IN_PROGRESS', 'RESOLVED', 'FALSE_POSITIVE'];

const SEVERITY_COLORS: Record<string, string> = {
  LOW: '#3b82f6',
  MEDIUM: '#f59e0b',
  HIGH: '#f97316',
  CRITICAL: '#ef4444',
};

type SortField = 'created_at' | 'severity' | 'status' | 'risk_score';
type SortDir = 'asc' | 'desc';

interface FilterState {
  severity: string;
  status: string;
  search: string;
}

export default function AlertsPage() {
  const queryClient = useQueryClient();

  const [filters, setFilters] = useState<FilterState>({ severity: '', status: '', search: '' });
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);
  const [sortField, setSortField] = useState<SortField>('created_at');
  const [sortDir, setSortDir] = useState<SortDir>('desc');
  const [selectedAlert, setSelectedAlert] = useState<AlertType | null>(null);

  const params: AlertListParams = {
    ...(filters.severity && { severity: filters.severity }),
    ...(filters.status && { status: filters.status }),
    skip: page * rowsPerPage,
    limit: rowsPerPage,
  };

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['alerts', params],
    queryFn: () => listAlerts(params),
  });

  const ackMutation = useMutation({
    mutationFn: (alertId: string) => acknowledgeAlert(alertId),
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ['alerts'] });
      if (selectedAlert?.id === updated.id) setSelectedAlert(updated);
    },
  });

  const statusMutation = useMutation({
    mutationFn: ({ alertId, status }: { alertId: string; status: string }) =>
      updateAlertStatus(alertId, { status }),
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ['alerts'] });
      if (selectedAlert?.id === updated.id) setSelectedAlert(updated);
    },
  });

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDir('desc');
    }
  };

  const sortedAlerts = [...(data?.alerts ?? [])].sort((a, b) => {
    let cmp = 0;
    if (sortField === 'created_at') cmp = new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
    else if (sortField === 'severity') cmp = SEVERITIES.indexOf(a.severity as AlertSeverity) - SEVERITIES.indexOf(b.severity as AlertSeverity);
    else if (sortField === 'status') cmp = STATUSES.indexOf(a.status as AlertStatus) - STATUSES.indexOf(b.status as AlertStatus);
    else if (sortField === 'risk_score') cmp = a.risk_score - b.risk_score;
    return sortDir === 'asc' ? cmp : -cmp;
  });

  const handleRefresh = () => refetch();

  return (
    <Box>
      <PageHeader
        title="Alerts"
        subtitle="Monitor and triage security alerts"
        actions={
          <Button
            startIcon={<RefreshIcon />}
            onClick={handleRefresh}
            variant="outlined"
            size="small"
          >
            Refresh
          </Button>
        }
      />

      {/* Filters */}
      <Box sx={{ mb: 3, display: 'flex', gap: 2, flexWrap: 'wrap' }}>
        <TextField
          select
          size="small"
          label="Severity"
          value={filters.severity}
          onChange={e => { setFilters(f => ({ ...f, severity: e.target.value })); setPage(0); }}
          sx={{ minWidth: 140 }}
        >
          <MenuItem value="">All</MenuItem>
          {SEVERITIES.map(s => <MenuItem key={s} value={s}>{s}</MenuItem>)}
        </TextField>

        <TextField
          select
          size="small"
          label="Status"
          value={filters.status}
          onChange={e => { setFilters(f => ({ ...f, status: e.target.value })); setPage(0); }}
          sx={{ minWidth: 160 }}
        >
          <MenuItem value="">All</MenuItem>
          {STATUSES.map(s => <MenuItem key={s} value={s}>{s.replace('_', ' ')}</MenuItem>)}
        </TextField>

        <TextField
          size="small"
          label="Search"
          placeholder="Search by user ID or title..."
          value={filters.search}
          onChange={e => setFilters(f => ({ ...f, search: e.target.value }))}
          sx={{ flexGrow: 1, maxWidth: 400 }}
        />
      </Box>

      {/* Table */}
      <Box sx={{ bgcolor: 'background.paper', borderRadius: 2, overflow: 'hidden' }}>
        {isLoading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 8 }}>
            <CircularProgress />
          </Box>
        ) : isError ? (
          <Alert severity="error" sx={{ m: 2 }}>
            Failed to load alerts: {(error as Error).message}
          </Alert>
        ) : !data || data.alerts.length === 0 ? (
          <EmptyState
            title="No alerts found"
            description="No alerts match the current filters."
          />
        ) : (
          <>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>
                    <TableSortLabel active={sortField === 'severity'} direction={sortField === 'severity' ? sortDir : 'asc'} onClick={() => handleSort('severity')}>
                      Severity
                    </TableSortLabel>
                  </TableCell>
                  <TableCell>
                    <TableSortLabel active={sortField === 'status'} direction={sortField === 'status' ? sortDir : 'asc'} onClick={() => handleSort('status')}>
                      Status
                    </TableSortLabel>
                  </TableCell>
                  <TableCell>User</TableCell>
                  <TableCell>Title / Description</TableCell>
                  <TableCell>
                    <TableSortLabel active={sortField === 'risk_score'} direction={sortField === 'risk_score' ? sortDir : 'asc'} onClick={() => handleSort('risk_score')}>
                      Risk Score
                    </TableSortLabel>
                  </TableCell>
                  <TableCell>Investigation</TableCell>
                  <TableCell>
                    <TableSortLabel active={sortField === 'created_at'} direction={sortField === 'created_at' ? sortDir : 'asc'} onClick={() => handleSort('created_at')}>
                      Created
                    </TableSortLabel>
                  </TableCell>
                  <TableCell align="center">Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {sortedAlerts.map(alert => (
                  <TableRow key={alert.id} hover>
                    <TableCell>
                      <SeverityBadge severity={alert.severity as AlertSeverity} />
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={alert.status as AlertStatus} />
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" sx={{ fontFamily: 'monospace', fontSize: '0.8rem' }}>
                        {alert.user_id}
                      </Typography>
                    </TableCell>
                    <TableCell sx={{ maxWidth: 300 }}>
                      <Typography variant="body2" sx={{ fontWeight: 500 }} noWrap>
                        {alert.title || 'Untitled Alert'}
                      </Typography>
                      {alert.description && (
                        <Typography variant="caption" color="text.secondary" noWrap>
                          {alert.description}
                        </Typography>
                      )}
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" sx={{ fontFamily: 'monospace', fontWeight: 600, color: SEVERITY_COLORS[alert.severity] ?? 'inherit' }}>
                        {alert.risk_score.toFixed(1)}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      {alert.investigation_id ? (
                        <Chip label="Linked" size="small" sx={{ bgcolor: 'rgba(139,92,246,0.12)', color: '#8b5cf6' }} />
                      ) : (
                        <Typography variant="caption" color="text.disabled">—</Typography>
                      )}
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" sx={{ fontSize: '0.75rem', whiteSpace: 'nowrap' }}>
                        {new Date(alert.created_at).toLocaleString()}
                      </Typography>
                    </TableCell>
                    <TableCell align="center">
                      <Tooltip title="View details">
                        <IconButton size="small" onClick={() => setSelectedAlert(alert)}>
                          <VisibilityIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>

            <TablePagination
              component="div"
              count={data?.total ?? 0}
              page={page}
              onPageChange={(_, p) => setPage(p)}
              rowsPerPage={rowsPerPage}
              onRowsPerPageChange={e => { setRowsPerPage(parseInt(e.target.value)); setPage(0); }}
              rowsPerPageOptions={[10, 25, 50, 100]}
            />
          </>
        )}
      </Box>

      {/* Alert Detail Drawer */}
      <Drawer anchor="right" open={!!selectedAlert} onClose={() => setSelectedAlert(null)}>
        <Box sx={{ width: 480, p: 3 }}>
          {selectedAlert && (
            <>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 3 }}>
                <Typography variant="h6">Alert Details</Typography>
                <IconButton size="small" onClick={() => setSelectedAlert(null)}>
                  <CloseIcon />
                </IconButton>
              </Box>

              <Stack spacing={2}>
                <Box sx={{ display: 'flex', gap: 2 }}>
                  <SeverityBadge severity={selectedAlert.severity as AlertSeverity} />
                  <StatusBadge status={selectedAlert.status as AlertStatus} />
                </Box>

                <Box>
                  <Typography variant="caption" color="text.secondary">TITLE</Typography>
                  <Typography variant="body1" sx={{ fontWeight: 500 }}>{selectedAlert.title || 'Untitled Alert'}</Typography>
                </Box>

                {selectedAlert.description && (
                  <Box>
                    <Typography variant="caption" color="text.secondary">DESCRIPTION</Typography>
                    <Typography variant="body2">{selectedAlert.description}</Typography>
                  </Box>
                )}

                <Divider />

                <Box>
                  <Typography variant="caption" color="text.secondary">USER ID</Typography>
                  <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>{selectedAlert.user_id}</Typography>
                </Box>

                <Box>
                  <Typography variant="caption" color="text.secondary">RISK SCORE</Typography>
                  <Typography variant="body2" sx={{ fontWeight: 700, color: SEVERITY_COLORS[selectedAlert.severity] }}>
                    {selectedAlert.risk_score.toFixed(3)}
                  </Typography>
                </Box>

                <Box>
                  <Typography variant="caption" color="text.secondary">SOURCE</Typography>
                  <Typography variant="body2">{selectedAlert.source_dataset} / {selectedAlert.window}</Typography>
                </Box>

                <Box>
                  <Typography variant="caption" color="text.secondary">TIME WINDOW</Typography>
                  <Typography variant="body2">
                    {new Date(selectedAlert.window_start).toLocaleString()} — {new Date(selectedAlert.window_end).toLocaleString()}
                  </Typography>
                </Box>

                <Box>
                  <Typography variant="caption" color="text.secondary">ASSIGNED TO</Typography>
                  <Typography variant="body2">{selectedAlert.assigned_to ?? 'Unassigned'}</Typography>
                </Box>

                <Box>
                  <Typography variant="caption" color="text.secondary">INVESTIGATION</Typography>
                  <Typography variant="body2">{selectedAlert.investigation_id ?? 'Not linked'}</Typography>
                </Box>

                <Box>
                  <Typography variant="caption" color="text.secondary">CREATED</Typography>
                  <Typography variant="body2">{new Date(selectedAlert.created_at).toLocaleString()}</Typography>
                </Box>

                {selectedAlert.top_behavioral_deviations.length > 0 && (
                  <>
                    <Divider />
                    <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>Top Deviations</Typography>
                    {selectedAlert.top_behavioral_deviations.slice(0, 5).map((d: AlertDeviation, i: number) => (
                      <Box key={i} sx={{ bgcolor: 'background.default', borderRadius: 1, p: 1.5 }}>
                        <Typography variant="body2" sx={{ fontFamily: 'monospace', fontWeight: 600 }}>
                          {d.feature}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          value={d.value.toFixed(4)} | baseline={d.baseline_mean.toFixed(4)} | z={d.zscore.toFixed(2)}
                        </Typography>
                      </Box>
                    ))}
                  </>
                )}

                <Divider />

                {/* Quick Actions */}
                <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                  {selectedAlert.status === 'OPEN' && (
                    <Button
                      variant="outlined"
                      size="small"
                      onClick={() => ackMutation.mutate(selectedAlert.id)}
                      disabled={ackMutation.isPending}
                    >
                      Acknowledge
                    </Button>
                  )}
                  {selectedAlert.status !== 'RESOLVED' && selectedAlert.status !== 'FALSE_POSITIVE' && (
                    <Button
                      variant="outlined"
                      size="small"
                      color="success"
                      onClick={() => statusMutation.mutate({ alertId: selectedAlert.id, status: 'RESOLVED' })}
                      disabled={statusMutation.isPending}
                    >
                      Mark Resolved
                    </Button>
                  )}
                  {selectedAlert.status !== 'FALSE_POSITIVE' && (
                    <Button
                      variant="outlined"
                      size="small"
                      color="inherit"
                      onClick={() => statusMutation.mutate({ alertId: selectedAlert.id, status: 'FALSE_POSITIVE' })}
                      disabled={statusMutation.isPending}
                    >
                      Mark False Positive
                    </Button>
                  )}
                </Box>
              </Stack>
            </>
          )}
        </Box>
      </Drawer>
    </Box>
  );
}
