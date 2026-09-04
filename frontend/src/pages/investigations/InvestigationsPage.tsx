import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Typography,
  Button,
  Table,
  TableHead,
  TableBody,
  TableRow,
  TableCell,
  TableSortLabel,
  TablePagination,
  Chip,
  TextField,
  MenuItem,
  CircularProgress,
  Alert,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Stack,
  InputLabel,
  FormControl,
  Select,
} from '@mui/material';
import RefreshIcon from '@mui/icons-material/Refresh';
import AddIcon from '@mui/icons-material/Add';
import PageHeader from '../../components/common/PageHeader';
import SeverityBadge from '../../components/common/SeverityBadge';
import EmptyState from '../../components/common/EmptyState';
import type { InvestigationStatus } from '../../types';
import { listInvestigations, createInvestigation } from '../../api/investigationService';
import type { InvestigationListParams, InvestigationCreateRequest } from '../../types/investigation';

const SEVERITIES = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'];
const STATUSES: InvestigationStatus[] = ['OPEN', 'IN_PROGRESS', 'RESOLVED', 'CLOSED'];

const STATUS_COLORS: Record<string, string> = {
  OPEN: '#3b82f6',
  IN_PROGRESS: '#8b5cf6',
  RESOLVED: '#10b981',
  CLOSED: '#64748b',
};

type SortField = 'created_at' | 'severity' | 'status' | 'updated_at';
type SortDir = 'asc' | 'desc';

interface FilterState {
  severity: string;
  status: string;
}

export default function InvestigationsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [filters, setFilters] = useState<FilterState>({ severity: '', status: '' });
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);
  const [sortField, setSortField] = useState<SortField>('created_at');
  const [sortDir, setSortDir] = useState<SortDir>('desc');
  const [createOpen, setCreateOpen] = useState(false);
  const [createForm, setCreateForm] = useState<InvestigationCreateRequest>({
    title: '',
    description: '',
    severity: 'MEDIUM',
  });

  const params: InvestigationListParams = {
    ...(filters.severity && { severity: filters.severity }),
    ...(filters.status && { status: filters.status }),
    skip: page * rowsPerPage,
    limit: rowsPerPage,
  };

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['investigations', params],
    queryFn: () => listInvestigations(params),
  });

  const createMutation = useMutation({
    mutationFn: (body: InvestigationCreateRequest) => createInvestigation(body),
    onSuccess: (inv) => {
      queryClient.invalidateQueries({ queryKey: ['investigations'] });
      setCreateOpen(false);
      setCreateForm({ title: '', description: '', severity: 'MEDIUM' });
      navigate(`/investigations/${inv.id}`);
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

  const sortedInvestigations = [...(data?.investigations ?? [])].sort((a, b) => {
    let cmp = 0;
    if (sortField === 'created_at') cmp = new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
    else if (sortField === 'updated_at') cmp = new Date(a.updated_at).getTime() - new Date(b.updated_at).getTime();
    else if (sortField === 'severity') cmp = SEVERITIES.indexOf(a.severity) - SEVERITIES.indexOf(b.severity);
    else if (sortField === 'status') cmp = STATUSES.indexOf(a.status as InvestigationStatus) - STATUSES.indexOf(b.status as InvestigationStatus);
    return sortDir === 'asc' ? cmp : -cmp;
  });

  return (
    <Box>
      <PageHeader
        title="Investigations"
        subtitle="Track and manage security investigations"
        actions={
          <Button
            startIcon={<AddIcon />}
            variant="contained"
            onClick={() => setCreateOpen(true)}
          >
            New Investigation
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

        <Box sx={{ flexGrow: 1 }} />

        <Button startIcon={<RefreshIcon />} variant="outlined" size="small" onClick={() => refetch()}>
          Refresh
        </Button>
      </Box>

      {/* Table */}
      <Box sx={{ bgcolor: 'background.paper', borderRadius: 2, overflow: 'hidden' }}>
        {isLoading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 8 }}>
            <CircularProgress />
          </Box>
        ) : isError ? (
          <Alert severity="error" sx={{ m: 2 }}>{(error as Error).message}</Alert>
        ) : !data || data.investigations.length === 0 ? (
          <EmptyState
            title="No investigations found"
            description="No investigations match the current filters."
          />
        ) : (
          <>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Title</TableCell>
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
                  <TableCell>Assignee</TableCell>
                  <TableCell>Linked Alerts</TableCell>
                  <TableCell>Created By</TableCell>
                  <TableCell>
                    <TableSortLabel active={sortField === 'created_at'} direction={sortField === 'created_at' ? sortDir : 'asc'} onClick={() => handleSort('created_at')}>
                      Created
                    </TableSortLabel>
                  </TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {sortedInvestigations.map(inv => (
                  <TableRow
                    key={inv.id}
                    hover
                    sx={{ cursor: 'pointer' }}
                    onClick={() => navigate(`/investigations/${inv.id}`)}
                  >
                    <TableCell>
                      <Typography variant="body2" sx={{ fontWeight: 500, maxWidth: 300 }} noWrap>
                        {inv.title}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <SeverityBadge severity={inv.severity as any} />
                    </TableCell>
                    <TableCell>
                      <Chip
                        label={inv.status.replace('_', ' ')}
                        size="small"
                        sx={{ bgcolor: `${STATUS_COLORS[inv.status] ?? '#64748b'}20`, color: STATUS_COLORS[inv.status] ?? '#64748b', fontWeight: 600, fontSize: '0.75rem' }}
                      />
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2">{inv.assigned_to ?? '—'}</Typography>
                    </TableCell>
                    <TableCell>
                      <Chip label={`${inv.related_alert_ids.length} alert${inv.related_alert_ids.length !== 1 ? 's' : ''}`} size="small" />
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" sx={{ fontFamily: 'monospace', fontSize: '0.8rem' }}>{inv.created_by}</Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" sx={{ fontSize: '0.75rem', whiteSpace: 'nowrap' }}>
                        {new Date(inv.created_at).toLocaleString()}
                      </Typography>
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

      {/* Create Dialog */}
      <Dialog open={createOpen} onClose={() => setCreateOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>New Investigation</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Title"
              value={createForm.title}
              onChange={e => setCreateForm(f => ({ ...f, title: e.target.value }))}
              fullWidth
              required
              inputProps={{ minLength: 3 }}
            />
            <TextField
              label="Description"
              value={createForm.description}
              onChange={e => setCreateForm(f => ({ ...f, description: e.target.value }))}
              fullWidth
              multiline
              rows={3}
            />
            <FormControl fullWidth size="small">
              <InputLabel>Severity</InputLabel>
              <Select
                label="Severity"
                value={createForm.severity}
                onChange={e => setCreateForm(f => ({ ...f, severity: e.target.value }))}
              >
                {SEVERITIES.map(s => <MenuItem key={s} value={s}>{s}</MenuItem>)}
              </Select>
            </FormControl>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={!createForm.title.trim() || createForm.title.trim().length < 3 || createMutation.isPending}
            onClick={() => createMutation.mutate(createForm)}
          >
            {createMutation.isPending ? 'Creating...' : 'Create'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
