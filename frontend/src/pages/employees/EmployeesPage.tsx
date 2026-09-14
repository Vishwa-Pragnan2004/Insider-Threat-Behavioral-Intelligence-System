import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  MenuItem,
  Snackbar,
  Stack,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TablePagination,
  TableRow,
  Tabs,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import { Badge as BadgeIcon, PersonAdd, Refresh, UploadFile } from '@mui/icons-material';
import PageHeader from '../../components/common/PageHeader';
import EmptyState from '../../components/common/EmptyState';
import { useAuth } from '../../hooks/useAuth';
import { hasPermission } from '../../utils/permissions';
import { listEmployees } from '../../api/employeeService';
import { apiErrorMessage } from '../../api/userService';
import type { EmployeeListParams, EmployeeStatus } from '../../types/employees';
import EmployeeFormDialog from './EmployeeFormDialog';
import ImportEmployeesDialog from './ImportEmployeesDialog';
import UnmappedAccountsSection from './UnmappedAccountsSection';
import { PrivilegedChip, StatusChip, employeePath, useDebouncedValue } from './employeeShared';

/**
 * Employees
 *
 * The employee directory: who is behind each monitored account and device.
 * employees:read to browse (route guard); employees:manage to add, import and
 * link accounts.
 */

const ACCOUNTS_SHOWN = 3;
type Section = 'directory' | 'unmapped';

export default function EmployeesPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const canManage = hasPermission(user, 'employees:manage');

  const [section, setSection] = useState<Section>('directory');
  const [search, setSearch] = useState('');
  const [department, setDepartment] = useState('');
  const [status, setStatus] = useState<EmployeeStatus | ''>('');
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);
  const [creating, setCreating] = useState(false);
  const [importing, setImporting] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const debouncedSearch = useDebouncedValue(search.trim(), 400);
  const debouncedDepartment = useDebouncedValue(department.trim(), 400);

  useEffect(() => {
    setPage(0);
  }, [debouncedSearch, debouncedDepartment, status]);

  const params: EmployeeListParams = {
    ...(debouncedSearch && { search: debouncedSearch }),
    ...(debouncedDepartment && { department: debouncedDepartment }),
    ...(status && { status }),
    skip: page * rowsPerPage,
    limit: rowsPerPage,
  };

  const query = useQuery({
    queryKey: ['employees', 'list', params],
    queryFn: () => listEmployees(params),
    placeholderData: (previous) => previous,
    enabled: section === 'directory',
  });

  const refresh = () => queryClient.invalidateQueries({ queryKey: ['employees'] });
  const employees = query.data?.employees ?? [];
  const filtered = !!(debouncedSearch || debouncedDepartment || status);

  return (
    <Box>
      <PageHeader
        title="Employees"
        subtitle="Who is behind each monitored account and device"
        actions={
          <>
            <Button startIcon={<Refresh />} onClick={refresh}>
              Refresh
            </Button>
            {canManage && (
              <>
                <Button variant="outlined" startIcon={<UploadFile />} onClick={() => setImporting(true)}>
                  Import CSV
                </Button>
                <Button variant="contained" startIcon={<PersonAdd />} onClick={() => setCreating(true)}>
                  Add employee
                </Button>
              </>
            )}
          </>
        }
      />

      <Tabs value={section} onChange={(_, v: Section) => setSection(v)} sx={{ mb: 3, borderBottom: 1, borderColor: 'divider' }}>
        <Tab value="directory" label="Directory" />
        <Tab value="unmapped" label="Unmapped accounts" />
      </Tabs>

      {section === 'unmapped' ? (
        <UnmappedAccountsSection canManage={canManage} onNotice={setNotice} />
      ) : (
        <>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ mb: 3 }}>
            <TextField
              size="small"
              label="Search name, ID, email or account"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              sx={{ minWidth: 280 }}
            />
            <TextField
              size="small"
              label="Department"
              value={department}
              onChange={(e) => setDepartment(e.target.value)}
              sx={{ minWidth: 180 }}
            />
            <TextField
              select
              size="small"
              label="Status"
              value={status}
              onChange={(e) => setStatus(e.target.value as EmployeeStatus | '')}
              sx={{ minWidth: 140 }}
            >
              <MenuItem value="">All</MenuItem>
              <MenuItem value="ACTIVE">Active</MenuItem>
              <MenuItem value="LEFT">Left</MenuItem>
            </TextField>
            {query.isFetching && !query.isLoading && <CircularProgress size={20} sx={{ alignSelf: 'center' }} />}
          </Stack>

          {query.isError && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {apiErrorMessage(query.error)}
            </Alert>
          )}

          {query.isLoading ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}>
              <CircularProgress />
            </Box>
          ) : !query.isError && employees.length === 0 ? (
            <EmptyState
              icon={<BadgeIcon sx={{ fontSize: 56 }} />}
              title={filtered ? 'No employees match these filters' : 'The directory is empty'}
              description={
                filtered
                  ? undefined
                  : 'Add employees or import a CSV so activity can be attributed to the people behind each account.'
              }
            />
          ) : employees.length > 0 ? (
            <>
              <Box sx={{ overflowX: 'auto' }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Employee</TableCell>
                      <TableCell>Department</TableCell>
                      <TableCell>Job title</TableCell>
                      <TableCell>Status</TableCell>
                      <TableCell>Accounts</TableCell>
                      <TableCell align="right">Devices</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {employees.map((e) => (
                      <TableRow
                        key={e.id}
                        hover
                        onClick={() => navigate(employeePath(e.employee_id))}
                        sx={{ cursor: 'pointer' }}
                      >
                        <TableCell>
                          <Typography variant="body2" sx={{ fontWeight: 600 }}>
                            {e.full_name}
                          </Typography>
                          <Typography variant="caption" color="text.secondary" sx={{ fontFamily: 'monospace' }}>
                            {e.employee_id}
                          </Typography>
                        </TableCell>
                        <TableCell>{e.department || '—'}</TableCell>
                        <TableCell>{e.job_title || '—'}</TableCell>
                        <TableCell>
                          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                            <StatusChip status={e.status} />
                            {e.privileged && <PrivilegedChip />}
                          </Box>
                        </TableCell>
                        <TableCell>
                          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                            {e.accounts.length === 0 && (
                              <Typography variant="caption" color="text.disabled">
                                None
                              </Typography>
                            )}
                            {e.accounts.slice(0, ACCOUNTS_SHOWN).map((a) => (
                              <Chip
                                key={a.id}
                                size="small"
                                variant="outlined"
                                label={a.account}
                                sx={{ fontFamily: 'monospace', fontSize: '0.72rem' }}
                              />
                            ))}
                            {e.accounts.length > ACCOUNTS_SHOWN && (
                              <Tooltip
                                title={e.accounts
                                  .slice(ACCOUNTS_SHOWN)
                                  .map((a) => a.account)
                                  .join(', ')}
                              >
                                <Chip size="small" label={`+${e.accounts.length - ACCOUNTS_SHOWN}`} />
                              </Tooltip>
                            )}
                          </Box>
                        </TableCell>
                        <TableCell align="right" sx={{ fontFamily: 'monospace' }}>
                          {e.devices.length}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Box>
              <TablePagination
                component="div"
                count={query.data?.total ?? 0}
                page={page}
                rowsPerPage={rowsPerPage}
                rowsPerPageOptions={[10, 25, 50, 100]}
                onPageChange={(_, next) => setPage(next)}
                onRowsPerPageChange={(e) => {
                  setRowsPerPage(parseInt(e.target.value, 10));
                  setPage(0);
                }}
              />
            </>
          ) : null}
        </>
      )}

      <EmployeeFormDialog
        open={creating}
        onClose={() => setCreating(false)}
        onSaved={(created) => {
          setCreating(false);
          setNotice(`Added ${created.full_name}.`);
          refresh();
        }}
      />

      <ImportEmployeesDialog
        open={importing}
        onClose={() => setImporting(false)}
        onImported={(result) => {
          setNotice(`Import finished: ${result.created} created, ${result.updated} updated.`);
          refresh();
        }}
      />

      <Snackbar
        open={!!notice}
        autoHideDuration={5000}
        onClose={() => setNotice(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
      >
        <Alert severity="success" variant="filled" onClose={() => setNotice(null)}>
          {notice}
        </Alert>
      </Snackbar>
    </Box>
  );
}
