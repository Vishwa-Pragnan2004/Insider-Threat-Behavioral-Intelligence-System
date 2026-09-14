import { useState } from 'react';
import { Link as RouterLink, useNavigate, useParams } from 'react-router-dom';
import axios from 'axios';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
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
  DialogContentText,
  DialogTitle,
  Divider,
  FormControlLabel,
  Grid,
  IconButton,
  Link,
  List,
  ListItem,
  ListItemText,
  MenuItem,
  Snackbar,
  Stack,
  Switch,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import { Add, ArrowBack, Badge as BadgeIcon, Delete, Edit, GppMaybe } from '@mui/icons-material';
import PageHeader from '../../components/common/PageHeader';
import EmptyState from '../../components/common/EmptyState';
import { useAuth } from '../../hooks/useAuth';
import { hasPermission } from '../../utils/permissions';
import {
  addEmployeeAccount,
  addEmployeeDevice,
  getEmployee,
  removeEmployeeAccount,
  removeEmployeeDevice,
  updateEmployee,
} from '../../api/employeeService';
import { getEmployeeRisk } from '../../api/riskService';
import { apiErrorMessage } from '../../api/userService';
import {
  ACCOUNT_TYPES,
  type AccountType,
  type Employee,
  type EmployeeAccount,
  type EmployeeDevice,
  type EmployeeUpdateRequest,
} from '../../types/employees';
import { LevelChip, NO_VALUE, RiskScoreChip, formatDateTime, formatNumber } from '../dashboards/shared';
import { TrendIndicator, employeeRiskPath, formatDay } from '../risk/riskShared';
import EmployeeFormDialog from './EmployeeFormDialog';
import {
  ACCOUNT_TYPE_LABELS,
  PrivilegedChip,
  StatusChip,
  decodeParam,
  employeePath,
  guessAccountType,
  primaryAccount,
} from './employeeShared';

/**
 * Employee detail
 *
 * One employee's profile and the accounts and devices linked to them.
 * employees:manage to edit; anomaly:read adds an insider risk summary.
 */

type Removal =
  | { kind: 'account'; item: EmployeeAccount }
  | { kind: 'device'; item: EmployeeDevice };

function is404(error: unknown): boolean {
  return axios.isAxiosError(error) && error.response?.status === 404;
}

function ProfileField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Box>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="body2" component="div" sx={{ fontWeight: 500, wordBreak: 'break-word' }}>
        {children || NO_VALUE}
      </Typography>
    </Box>
  );
}

function ManagerLink({ managerId }: { managerId: string }) {
  const managerQuery = useQuery({
    queryKey: ['employees', 'detail', managerId],
    queryFn: () => getEmployee(managerId),
    retry: false,
    staleTime: 60_000,
  });
  return (
    <Link component={RouterLink} to={employeePath(managerId)} underline="hover">
      {managerQuery.data ? `${managerQuery.data.full_name} (${managerId})` : managerId}
    </Link>
  );
}

function RiskCard({ account }: { account: string | null }) {
  const riskQuery = useQuery({
    queryKey: ['risk', 'employee', account, 30],
    queryFn: () => getEmployeeRisk(account as string, 30),
    enabled: !!account,
    retry: (count, error) => !is404(error) && count < 2,
  });
  const latest = riskQuery.data?.latest ?? null;

  return (
    <Card>
      <CardContent>
        <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 2 }}>
          <GppMaybe color="action" />
          <Typography variant="h6" sx={{ fontWeight: 600, flexGrow: 1 }}>
            Insider risk
          </Typography>
          {account && (
            <Button size="small" component={RouterLink} to={employeeRiskPath(account)}>
              View
            </Button>
          )}
        </Stack>
        {!account ? (
          <Typography variant="body2" color="text.secondary">
            Link a Windows, dataset or email account to see this employee's risk score.
          </Typography>
        ) : riskQuery.isLoading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 2 }}>
            <CircularProgress size={24} />
          </Box>
        ) : riskQuery.isError && !is404(riskQuery.error) ? (
          <Alert severity="error">{apiErrorMessage(riskQuery.error)}</Alert>
        ) : !latest ? (
          <Typography variant="body2" color="text.secondary">
            No risk score for <code>{account}</code> in the last 30 days.
          </Typography>
        ) : (
          <Stack spacing={1.5}>
            <Stack direction="row" spacing={3} alignItems="center" flexWrap="wrap" useFlexGap>
              <Box>
                <Typography variant="caption" color="text.secondary" display="block">
                  Priority
                </Typography>
                <RiskScoreChip score={latest.priority} />
              </Box>
              <Box>
                <Typography variant="caption" color="text.secondary" display="block">
                  Score
                </Typography>
                <Typography sx={{ fontFamily: 'monospace', fontWeight: 600 }}>
                  {formatNumber(latest.score, '', 1)}
                </Typography>
              </Box>
              <Box>
                <Typography variant="caption" color="text.secondary" display="block">
                  Level
                </Typography>
                <LevelChip level={latest.level} />
              </Box>
              <Box>
                <Typography variant="caption" color="text.secondary" display="block">
                  Trend
                </Typography>
                <TrendIndicator trend={latest.trend} />
              </Box>
            </Stack>
            <Typography variant="caption" color="text.secondary">
              Account <code>{account}</code> · last scored {formatDay(latest.day)}
            </Typography>
          </Stack>
        )}
      </CardContent>
    </Card>
  );
}

export default function EmployeeDetailPage() {
  const params = useParams<{ employeeId: string }>();
  const employeeId = decodeParam(params.employeeId);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const canManage = hasPermission(user, 'employees:manage');
  const canReadRisk = hasPermission(user, 'anomaly:read');

  const [editing, setEditing] = useState(false);
  const [newAccount, setNewAccount] = useState('');
  const [newAccountType, setNewAccountType] = useState<AccountType>('windows');
  const [accountTypeTouched, setAccountTypeTouched] = useState(false);
  const [newDevice, setNewDevice] = useState('');
  const [newDeviceDedicated, setNewDeviceDedicated] = useState(true);
  const [removing, setRemoving] = useState<Removal | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const detailKey = ['employees', 'detail', employeeId];
  const query = useQuery({
    queryKey: detailKey,
    queryFn: () => getEmployee(employeeId),
    enabled: !!employeeId,
    retry: (count, error) => !is404(error) && count < 2,
  });
  const employee = query.data;

  /** Apply the returned employee, then let lists and lookups refetch. */
  const applyUpdate = (updated: Employee) => {
    queryClient.setQueryData(detailKey, updated);
    queryClient.invalidateQueries({
      queryKey: ['employees'],
      predicate: (q) => !(q.queryKey[1] === 'detail' && q.queryKey[2] === employeeId),
    });
  };

  const onError = (error: unknown) => setActionError(apiErrorMessage(error));

  const patchMutation = useMutation({
    mutationFn: (body: EmployeeUpdateRequest) => updateEmployee(employeeId, body),
    onSuccess: (updated) => {
      setActionError(null);
      applyUpdate(updated);
    },
    onError,
  });

  const addAccountMutation = useMutation({
    mutationFn: () => addEmployeeAccount(employeeId, newAccount.trim(), newAccountType),
    onSuccess: (updated) => {
      setNotice(`Linked ${newAccount.trim()}.`);
      setNewAccount('');
      setAccountTypeTouched(false);
      setNewAccountType('windows');
      setActionError(null);
      applyUpdate(updated);
    },
    onError,
  });

  const addDeviceMutation = useMutation({
    mutationFn: () => addEmployeeDevice(employeeId, newDevice.trim(), newDeviceDedicated),
    onSuccess: (updated) => {
      setNotice(`Assigned ${newDevice.trim()}.`);
      setNewDevice('');
      setNewDeviceDedicated(true);
      setActionError(null);
      applyUpdate(updated);
    },
    onError,
  });

  const removeMutation = useMutation({
    mutationFn: (target: Removal) =>
      target.kind === 'account'
        ? removeEmployeeAccount(employeeId, target.item.id)
        : removeEmployeeDevice(employeeId, target.item.id),
    onSuccess: (updated, target) => {
      setRemoving(null);
      setActionError(null);
      setNotice(`Removed ${target.kind === 'account' ? target.item.account : target.item.device_id}.`);
      applyUpdate(updated);
    },
    onError: (error) => {
      setRemoving(null);
      onError(error);
    },
  });

  const back = (
    <Button startIcon={<ArrowBack />} onClick={() => navigate('/employees')}>
      Employees
    </Button>
  );

  if (query.isLoading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', py: 8 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (!employee) {
    return (
      <Box>
        <PageHeader title="Employee" actions={back} />
        {query.isError && !is404(query.error) ? (
          <Alert severity="error">{apiErrorMessage(query.error)}</Alert>
        ) : (
          <EmptyState
            icon={<BadgeIcon sx={{ fontSize: 56 }} />}
            title="Employee not found"
            description={`No employee has the ID ${employeeId}.`}
          />
        )}
      </Box>
    );
  }

  const accountValue = newAccount.trim();

  return (
    <Box>
      <PageHeader
        title={employee.full_name}
        subtitle={`Employee ${employee.employee_id} · updated ${formatDateTime(employee.updated_at)}`}
        actions={
          <>
            {back}
            {canManage && (
              <Button variant="contained" startIcon={<Edit />} onClick={() => setEditing(true)}>
                Edit
              </Button>
            )}
          </>
        }
      />

      <Stack direction="row" spacing={1} sx={{ mb: 3 }} alignItems="center" flexWrap="wrap" useFlexGap>
        <StatusChip status={employee.status} />
        {employee.privileged && <PrivilegedChip />}
        {canManage && (
          <>
            <Divider orientation="vertical" flexItem sx={{ mx: 1 }} />
            <FormControlLabel
              control={
                <Switch
                  size="small"
                  checked={employee.status === 'ACTIVE'}
                  disabled={patchMutation.isPending}
                  onChange={(e) => patchMutation.mutate({ status: e.target.checked ? 'ACTIVE' : 'LEFT' })}
                />
              }
              label="Active"
            />
            <FormControlLabel
              control={
                <Switch
                  size="small"
                  checked={employee.privileged}
                  disabled={patchMutation.isPending}
                  onChange={(e) => patchMutation.mutate({ privileged: e.target.checked })}
                />
              }
              label="Privileged"
            />
          </>
        )}
      </Stack>

      {actionError && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setActionError(null)}>
          {actionError}
        </Alert>
      )}

      <Grid container spacing={2}>
        <Grid item xs={12} md={canReadRisk ? 8 : 12}>
          <Card sx={{ height: '100%' }}>
            <CardContent>
              <Typography variant="h6" sx={{ fontWeight: 600, mb: 2 }}>
                Profile
              </Typography>
              <Grid container spacing={2}>
                <Grid item xs={12} sm={6}>
                  <ProfileField label="Department">{employee.department}</ProfileField>
                </Grid>
                <Grid item xs={12} sm={6}>
                  <ProfileField label="Job title">{employee.job_title}</ProfileField>
                </Grid>
                <Grid item xs={12} sm={6}>
                  <ProfileField label="Team">{employee.team}</ProfileField>
                </Grid>
                <Grid item xs={12} sm={6}>
                  <ProfileField label="Manager">
                    {employee.manager_employee_id && <ManagerLink managerId={employee.manager_employee_id} />}
                  </ProfileField>
                </Grid>
                <Grid item xs={12} sm={6}>
                  <ProfileField label="Email">
                    {employee.email && (
                      <Link href={`mailto:${employee.email}`} underline="hover">
                        {employee.email}
                      </Link>
                    )}
                  </ProfileField>
                </Grid>
                <Grid item xs={12} sm={6}>
                  <ProfileField label="In directory since">{formatDateTime(employee.created_at)}</ProfileField>
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </Grid>

        {canReadRisk && (
          <Grid item xs={12} md={4}>
            <RiskCard account={primaryAccount(employee)} />
          </Grid>
        )}

        <Grid item xs={12} md={6}>
          <Card sx={{ height: '100%' }}>
            <CardContent>
              <Typography variant="h6" sx={{ fontWeight: 600 }}>
                Accounts ({employee.accounts.length})
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                Events from these accounts are attributed to {employee.full_name}.
              </Typography>
              {employee.accounts.length === 0 ? (
                <Typography variant="body2" color="text.disabled" sx={{ py: 2 }}>
                  No accounts linked.
                </Typography>
              ) : (
                <List dense disablePadding>
                  {employee.accounts.map((a) => (
                    <ListItem
                      key={a.id}
                      divider
                      secondaryAction={
                        canManage && (
                          <Tooltip title="Remove account">
                            <IconButton edge="end" size="small" onClick={() => setRemoving({ kind: 'account', item: a })}>
                              <Delete fontSize="small" />
                            </IconButton>
                          </Tooltip>
                        )
                      }
                    >
                      <ListItemText
                        primary={a.account}
                        primaryTypographyProps={{ sx: { fontFamily: 'monospace', fontWeight: 600, wordBreak: 'break-all' } }}
                      />
                      <Chip
                        size="small"
                        variant="outlined"
                        label={ACCOUNT_TYPE_LABELS[a.account_type] ?? a.account_type}
                        sx={{ ml: 1, mr: canManage ? 2 : 0 }}
                      />
                    </ListItem>
                  ))}
                </List>
              )}
              {canManage && (
                <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ mt: 2 }}>
                  <TextField
                    size="small"
                    label="Account"
                    placeholder="DOMAIN\user, id or email"
                    value={newAccount}
                    onChange={(e) => {
                      setNewAccount(e.target.value);
                      if (!accountTypeTouched) setNewAccountType(guessAccountType(e.target.value.trim()));
                    }}
                    sx={{ flexGrow: 1 }}
                  />
                  <TextField
                    select
                    size="small"
                    label="Type"
                    value={newAccountType}
                    onChange={(e) => {
                      setNewAccountType(e.target.value as AccountType);
                      setAccountTypeTouched(true);
                    }}
                    sx={{ minWidth: 120 }}
                  >
                    {ACCOUNT_TYPES.map((t) => (
                      <MenuItem key={t} value={t}>
                        {ACCOUNT_TYPE_LABELS[t]}
                      </MenuItem>
                    ))}
                  </TextField>
                  <Button
                    variant="outlined"
                    startIcon={<Add />}
                    disabled={!accountValue || addAccountMutation.isPending}
                    onClick={() => addAccountMutation.mutate()}
                  >
                    Add
                  </Button>
                </Stack>
              )}
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={6}>
          <Card sx={{ height: '100%' }}>
            <CardContent>
              <Typography variant="h6" sx={{ fontWeight: 600 }}>
                Devices ({employee.devices.length})
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                Dedicated devices are treated as this employee's own machine by live detection.
              </Typography>
              {employee.devices.length === 0 ? (
                <Typography variant="body2" color="text.disabled" sx={{ py: 2 }}>
                  No devices assigned.
                </Typography>
              ) : (
                <List dense disablePadding>
                  {employee.devices.map((d) => (
                    <ListItem
                      key={d.id}
                      divider
                      secondaryAction={
                        canManage && (
                          <Tooltip title="Remove device">
                            <IconButton edge="end" size="small" onClick={() => setRemoving({ kind: 'device', item: d })}>
                              <Delete fontSize="small" />
                            </IconButton>
                          </Tooltip>
                        )
                      }
                    >
                      <ListItemText
                        primary={d.device_id}
                        primaryTypographyProps={{ sx: { fontFamily: 'monospace', fontWeight: 600, wordBreak: 'break-all' } }}
                      />
                      <Chip
                        size="small"
                        label={d.dedicated ? 'Dedicated' : 'Shared'}
                        color={d.dedicated ? 'primary' : 'default'}
                        variant={d.dedicated ? 'filled' : 'outlined'}
                        sx={{ ml: 1, mr: canManage ? 2 : 0 }}
                      />
                    </ListItem>
                  ))}
                </List>
              )}
              {canManage && (
                <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ mt: 2 }} alignItems={{ sm: 'center' }}>
                  <TextField
                    size="small"
                    label="Device ID"
                    placeholder="Hostname or agent device id"
                    value={newDevice}
                    onChange={(e) => setNewDevice(e.target.value)}
                    sx={{ flexGrow: 1 }}
                  />
                  <FormControlLabel
                    control={
                      <Switch
                        size="small"
                        checked={newDeviceDedicated}
                        onChange={(e) => setNewDeviceDedicated(e.target.checked)}
                      />
                    }
                    label="Dedicated"
                  />
                  <Button
                    variant="outlined"
                    startIcon={<Add />}
                    disabled={!newDevice.trim() || addDeviceMutation.isPending}
                    onClick={() => addDeviceMutation.mutate()}
                  >
                    Add
                  </Button>
                </Stack>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      <EmployeeFormDialog
        open={editing}
        employee={employee}
        onClose={() => setEditing(false)}
        onSaved={(updated) => {
          setEditing(false);
          setNotice('Saved changes.');
          applyUpdate(updated);
        }}
      />

      <Dialog open={!!removing} onClose={() => !removeMutation.isPending && setRemoving(null)}>
        <DialogTitle>
          Remove {removing?.kind === 'account' ? removing.item.account : removing?.item.device_id}?
        </DialogTitle>
        <DialogContent>
          <DialogContentText>
            {removing?.kind === 'account'
              ? `New events from this account will no longer be attributed to ${employee.full_name}.`
              : `Live detection will no longer treat this device as ${employee.full_name}'s.`}
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRemoving(null)} disabled={removeMutation.isPending}>
            Cancel
          </Button>
          <Button
            variant="contained"
            color="error"
            disabled={removeMutation.isPending}
            onClick={() => removing && removeMutation.mutate(removing)}
          >
            Remove
          </Button>
        </DialogActions>
      </Dialog>

      <Snackbar
        open={!!notice}
        autoHideDuration={4000}
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
