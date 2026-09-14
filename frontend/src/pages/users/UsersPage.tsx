import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  FormControlLabel,
  FormGroup,
  IconButton,
  MenuItem,
  Snackbar,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TablePagination,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import { Block, CheckCircle, Edit, People, PersonAdd, Refresh } from '@mui/icons-material';
import PageHeader from '../../components/common/PageHeader';
import EmptyState from '../../components/common/EmptyState';
import { useAuth } from '../../hooks/useAuth';
import { hasPermission } from '../../utils/permissions';
import {
  apiErrorMessage,
  disableUser,
  enableUser,
  listRoles,
  listUsers,
  setUserRoles,
} from '../../api/userService';
import type { ManagedUser, RoleName, UserListParams } from '../../types/users';
import CreateUserDialog from './CreateUserDialog';
import AccessRequestsSection from './AccessRequestsSection';
import { ROLE_COLORS, ROLE_LABELS, ROLE_NAMES } from './roles';

/**
 * Users
 *
 * Who can access ITBIS and what they're allowed to do. Anyone with
 * users:read can see this page (enforced by the route guard); creating
 * accounts needs users:create, and changing roles or disabling accounts needs
 * users:update. The backend refuses changes that would lock administrators
 * out, and this page shows its explanation when it does.
 */

type StatusFilter = '' | 'active' | 'disabled';

function formatDate(value: string | null): string {
  return value ? new Date(value).toLocaleString() : 'Never';
}

function displayName(user: ManagedUser | null): string {
  return user ? user.full_name || user.username : '';
}

export default function UsersPage() {
  const { user: me } = useAuth();
  const queryClient = useQueryClient();
  const canCreate = hasPermission(me, 'users:create');
  const canManage = hasPermission(me, 'users:update');

  const [search, setSearch] = useState('');
  const [role, setRole] = useState<RoleName | ''>('');
  const [status, setStatus] = useState<StatusFilter>('');
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);
  const [editing, setEditing] = useState<ManagedUser | null>(null);
  const [draftRoles, setDraftRoles] = useState<RoleName[]>([]);
  const [confirming, setConfirming] = useState<ManagedUser | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const params: UserListParams = {
    ...(search.trim() && { search: search.trim() }),
    ...(role && { role }),
    ...(status && { is_active: status === 'active' }),
    offset: page * rowsPerPage,
    limit: rowsPerPage,
  };

  const usersQuery = useQuery({
    queryKey: ['users', params],
    queryFn: () => listUsers(params),
  });
  const rolesQuery = useQuery({ queryKey: ['roles'], queryFn: listRoles });

  const refreshUsers = () => queryClient.invalidateQueries({ queryKey: ['users'] });

  const rolesMutation = useMutation({
    mutationFn: ({ id, roles }: { id: string; roles: RoleName[] }) => setUserRoles(id, roles),
    onSuccess: () => {
      setEditing(null);
      setActionError(null);
      refreshUsers();
    },
    onError: (error) => setActionError(apiErrorMessage(error)),
  });

  const statusMutation = useMutation({
    mutationFn: (target: ManagedUser) =>
      target.is_active ? disableUser(target.id) : enableUser(target.id),
    onSuccess: () => {
      setConfirming(null);
      setActionError(null);
      refreshUsers();
    },
    onError: (error) => {
      setConfirming(null);
      setActionError(apiErrorMessage(error));
    },
  });

  const permissionsPreview = useMemo(() => {
    const granted = new Set<string>();
    for (const info of rolesQuery.data ?? []) {
      if (draftRoles.includes(info.name)) info.permissions.forEach((p) => granted.add(p));
    }
    return [...granted].sort();
  }, [rolesQuery.data, draftRoles]);

  const openEditor = (target: ManagedUser) => {
    setDraftRoles(target.roles);
    setActionError(null);
    setEditing(target);
  };

  const toggleRole = (name: RoleName) =>
    setDraftRoles((current) =>
      current.includes(name) ? current.filter((r) => r !== name) : [...current, name],
    );

  const users = usersQuery.data?.users ?? [];

  return (
    <Box>
      <PageHeader
        title="Users"
        subtitle="Who can access ITBIS, and what they're allowed to do"
        actions={
          <>
            <Button startIcon={<Refresh />} onClick={() => usersQuery.refetch()}>
              Refresh
            </Button>
            {canCreate && (
              <Button variant="contained" startIcon={<PersonAdd />} onClick={() => setCreating(true)}>
                Create user
              </Button>
            )}
          </>
        }
      />

      {actionError && !editing && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setActionError(null)}>
          {actionError}
        </Alert>
      )}

      <AccessRequestsSection canDecide={canManage} onNotice={setNotice} />

      <Typography variant="h6" sx={{ fontWeight: 600, mb: 2 }}>
        Accounts
      </Typography>

      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ mb: 3 }}>
        <TextField
          size="small"
          label="Search name or email"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(0);
          }}
          sx={{ minWidth: 240 }}
        />
        <TextField
          select
          size="small"
          label="Role"
          value={role}
          onChange={(e) => {
            setRole(e.target.value as RoleName | '');
            setPage(0);
          }}
          sx={{ minWidth: 180 }}
        >
          <MenuItem value="">All roles</MenuItem>
          {ROLE_NAMES.map((name) => (
            <MenuItem key={name} value={name}>
              {ROLE_LABELS[name]}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          select
          size="small"
          label="Status"
          value={status}
          onChange={(e) => {
            setStatus(e.target.value as StatusFilter);
            setPage(0);
          }}
          sx={{ minWidth: 150 }}
        >
          <MenuItem value="">All</MenuItem>
          <MenuItem value="active">Active</MenuItem>
          <MenuItem value="disabled">Disabled</MenuItem>
        </TextField>
      </Stack>

      {usersQuery.isError && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {apiErrorMessage(usersQuery.error)}
        </Alert>
      )}

      {usersQuery.isLoading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}>
          <CircularProgress />
        </Box>
      ) : users.length === 0 ? (
        <EmptyState icon={<People />} title="No users match these filters" />
      ) : (
        <>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>User</TableCell>
                <TableCell>Roles</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Last sign-in</TableCell>
                {canManage && <TableCell align="right">Actions</TableCell>}
              </TableRow>
            </TableHead>
            <TableBody>
              {users.map((u) => {
                const isMe = me?.id === u.id;
                return (
                  <TableRow key={u.id} hover>
                    <TableCell>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        {displayName(u)}
                        {isMe && ' (you)'}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {u.email}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                        {u.is_superadmin && (
                          <Chip size="small" label="Superadmin" color="error" variant="outlined" />
                        )}
                        {u.roles.map((r) => (
                          <Chip key={r} size="small" label={ROLE_LABELS[r]} color={ROLE_COLORS[r]} />
                        ))}
                      </Box>
                    </TableCell>
                    <TableCell>
                      <Chip
                        size="small"
                        label={u.is_active ? 'Active' : 'Disabled'}
                        color={u.is_active ? 'success' : 'default'}
                        variant={u.is_active ? 'filled' : 'outlined'}
                      />
                    </TableCell>
                    <TableCell>{formatDate(u.last_login_at)}</TableCell>
                    {canManage && (
                      <TableCell align="right">
                        <Tooltip title="Edit roles">
                          <IconButton size="small" onClick={() => openEditor(u)}>
                            <Edit fontSize="small" />
                          </IconButton>
                        </Tooltip>
                        <Tooltip
                          title={
                            isMe
                              ? "You can't disable your own account"
                              : u.is_active
                                ? 'Disable account'
                                : 'Enable account'
                          }
                        >
                          <span>
                            <IconButton
                              size="small"
                              disabled={isMe}
                              color={u.is_active ? 'error' : 'success'}
                              onClick={() => setConfirming(u)}
                            >
                              {u.is_active ? (
                                <Block fontSize="small" />
                              ) : (
                                <CheckCircle fontSize="small" />
                              )}
                            </IconButton>
                          </span>
                        </Tooltip>
                      </TableCell>
                    )}
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
          <TablePagination
            component="div"
            count={usersQuery.data?.total ?? 0}
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
      )}

      {/* Edit roles */}
      <Dialog open={!!editing} onClose={() => setEditing(null)} maxWidth="sm" fullWidth>
        <DialogTitle>Roles for {displayName(editing)}</DialogTitle>
        <DialogContent>
          <FormGroup>
            {(rolesQuery.data ?? []).map((info) => (
              <FormControlLabel
                key={info.name}
                control={
                  <Checkbox
                    checked={draftRoles.includes(info.name)}
                    onChange={() => toggleRole(info.name)}
                  />
                }
                label={`${ROLE_LABELS[info.name]} (${info.permissions.length} permissions)`}
              />
            ))}
          </FormGroup>
          <Typography variant="subtitle2" sx={{ mt: 2 }}>
            Permissions this grants
          </Typography>
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, mt: 1 }}>
            {permissionsPreview.length === 0 ? (
              <Typography variant="body2" color="text.secondary">
                Select at least one role.
              </Typography>
            ) : (
              permissionsPreview.map((p) => (
                <Chip key={p} size="small" variant="outlined" label={p} />
              ))
            )}
          </Box>
          {editing?.is_superadmin && (
            <Alert severity="info" sx={{ mt: 2 }}>
              This is a superadmin account. It keeps full access whatever roles it has.
            </Alert>
          )}
          {actionError && editing && (
            <Alert severity="error" sx={{ mt: 2 }}>
              {actionError}
            </Alert>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditing(null)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={draftRoles.length === 0 || rolesMutation.isPending}
            onClick={() => editing && rolesMutation.mutate({ id: editing.id, roles: draftRoles })}
          >
            Save roles
          </Button>
        </DialogActions>
      </Dialog>

      {/* Create user */}
      <CreateUserDialog
        open={creating}
        onClose={() => setCreating(false)}
        onCreated={(created) => {
          setCreating(false);
          setNotice(`Created ${displayName(created)}.`);
          refreshUsers();
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

      {/* Disable / enable confirmation */}
      <Dialog open={!!confirming} onClose={() => setConfirming(null)}>
        <DialogTitle>
          {confirming?.is_active ? 'Disable' : 'Enable'} {displayName(confirming)}?
        </DialogTitle>
        <DialogContent>
          <DialogContentText>
            {confirming?.is_active
              ? "They'll be signed out straight away and can't sign in again until re-enabled."
              : 'They can sign in again with their existing password.'}
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirming(null)}>Cancel</Button>
          <Button
            variant="contained"
            color={confirming?.is_active ? 'error' : 'success'}
            disabled={statusMutation.isPending}
            onClick={() => confirming && statusMutation.mutate(confirming)}
          >
            {confirming?.is_active ? 'Disable' : 'Enable'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
