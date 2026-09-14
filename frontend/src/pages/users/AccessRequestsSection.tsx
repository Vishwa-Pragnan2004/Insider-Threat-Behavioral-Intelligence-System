import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Badge,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  MenuItem,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import { Check, Close, HowToReg } from '@mui/icons-material';
import EmptyState from '../../components/common/EmptyState';
import {
  apiErrorMessage,
  approveAccessRequest,
  listAccessRequests,
  rejectAccessRequest,
} from '../../api/userService';
import type { AccessRequest, AccessRequestStatus, RoleName } from '../../types/users';
import { ROLE_COLORS, ROLE_LABELS, ROLE_NAMES } from './roles';

/**
 * AccessRequestsSection
 *
 * People who asked for an account from the public request-access page.
 * Visible with users:read; approving (choosing the roles actually granted)
 * or rejecting needs users:update.
 */

type StatusFilter = AccessRequestStatus | 'ALL';

const STATUS_COLORS: Record<AccessRequestStatus, 'warning' | 'success' | 'default'> = {
  PENDING: 'warning',
  APPROVED: 'success',
  REJECTED: 'default',
};

const STATUS_LABELS: Record<AccessRequestStatus, string> = {
  PENDING: 'Pending',
  APPROVED: 'Approved',
  REJECTED: 'Rejected',
};

function relativeTime(value: string): string {
  const seconds = Math.round((Date.now() - new Date(value).getTime()) / 1000);
  if (seconds < 60) return 'just now';
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days} d ago`;
  return new Date(value).toLocaleDateString();
}

interface AccessRequestsSectionProps {
  canDecide: boolean;
  onNotice: (message: string) => void;
}

export default function AccessRequestsSection({ canDecide, onNotice }: AccessRequestsSectionProps) {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('PENDING');
  const [approving, setApproving] = useState<AccessRequest | null>(null);
  const [rejecting, setRejecting] = useState<AccessRequest | null>(null);
  const [draftRoles, setDraftRoles] = useState<RoleName[]>([]);
  const [note, setNote] = useState('');
  const [dialogError, setDialogError] = useState<string | null>(null);

  const status = statusFilter === 'ALL' ? undefined : statusFilter;
  const requestsQuery = useQuery({
    queryKey: ['access-requests', statusFilter],
    queryFn: () => listAccessRequests(status),
  });

  const afterDecision = (message: string) => {
    setApproving(null);
    setRejecting(null);
    setDialogError(null);
    queryClient.invalidateQueries({ queryKey: ['access-requests'] });
    queryClient.invalidateQueries({ queryKey: ['users'] });
    onNotice(message);
  };

  const onDecisionError = (error: unknown) => {
    setDialogError(apiErrorMessage(error));
    // A 409 means someone else decided it meanwhile; refresh the list.
    queryClient.invalidateQueries({ queryKey: ['access-requests'] });
  };

  const approveMutation = useMutation({
    mutationFn: ({ id, roles }: { id: string; roles: RoleName[] }) => approveAccessRequest(id, roles),
    onSuccess: (req) => afterDecision(`Approved access for ${req.full_name || req.username}.`),
    onError: onDecisionError,
  });

  const rejectMutation = useMutation({
    mutationFn: ({ id, note: text }: { id: string; note?: string }) => rejectAccessRequest(id, text),
    onSuccess: (req) => afterDecision(`Rejected the request from ${req.full_name || req.username}.`),
    onError: onDecisionError,
  });

  const openApprove = (req: AccessRequest) => {
    setDraftRoles([req.requested_role]);
    setDialogError(null);
    setApproving(req);
  };

  const openReject = (req: AccessRequest) => {
    setNote('');
    setDialogError(null);
    setRejecting(req);
  };

  const requests = requestsQuery.data?.requests ?? [];
  const pending = requestsQuery.data?.pending ?? 0;
  const busy = approveMutation.isPending || rejectMutation.isPending;

  return (
    <Paper variant="outlined" sx={{ p: 2, mb: 4 }}>
      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        spacing={2}
        alignItems={{ xs: 'flex-start', sm: 'center' }}
        justifyContent="space-between"
        sx={{ mb: 2 }}
      >
        <Badge badgeContent={pending} color="warning" max={99} sx={{ '& .MuiBadge-badge': { right: -14, top: 12 } }}>
          <Typography variant="h6" sx={{ fontWeight: 600 }}>
            Access requests
          </Typography>
        </Badge>
        <TextField
          select
          size="small"
          label="Status"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
          sx={{ minWidth: 150 }}
        >
          <MenuItem value="PENDING">Pending</MenuItem>
          <MenuItem value="APPROVED">Approved</MenuItem>
          <MenuItem value="REJECTED">Rejected</MenuItem>
          <MenuItem value="ALL">All</MenuItem>
        </TextField>
      </Stack>

      {requestsQuery.isError && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {apiErrorMessage(requestsQuery.error)}
        </Alert>
      )}

      {requestsQuery.isLoading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
          <CircularProgress size={28} />
        </Box>
      ) : requests.length === 0 ? (
        <EmptyState
          icon={<HowToReg />}
          title={statusFilter === 'PENDING' ? 'No pending access requests' : 'No access requests'}
        />
      ) : (
        <Box sx={{ overflowX: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Requested</TableCell>
                <TableCell>Person</TableCell>
                <TableCell>Requested role</TableCell>
                <TableCell>Reason</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Decided</TableCell>
                {canDecide && <TableCell align="right">Actions</TableCell>}
              </TableRow>
            </TableHead>
            <TableBody>
              {requests.map((req) => (
                <TableRow key={req.id} hover>
                  <TableCell sx={{ whiteSpace: 'nowrap' }}>
                    <Tooltip title={new Date(req.created_at).toLocaleString()}>
                      <span>{relativeTime(req.created_at)}</span>
                    </Tooltip>
                  </TableCell>
                  <TableCell>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>
                      {req.full_name}
                    </Typography>
                    <Typography variant="caption" color="text.secondary" component="div">
                      @{req.username} · {req.email}
                    </Typography>
                  </TableCell>
                  <TableCell>
                    <Chip
                      size="small"
                      label={ROLE_LABELS[req.requested_role]}
                      color={ROLE_COLORS[req.requested_role]}
                    />
                  </TableCell>
                  <TableCell sx={{ maxWidth: 280 }}>
                    <Tooltip title={<Box sx={{ whiteSpace: 'pre-wrap' }}>{req.reason}</Box>}>
                      <Typography variant="body2" noWrap>
                        {req.reason}
                      </Typography>
                    </Tooltip>
                  </TableCell>
                  <TableCell>
                    <Chip
                      size="small"
                      label={STATUS_LABELS[req.status]}
                      color={STATUS_COLORS[req.status]}
                      variant={req.status === 'REJECTED' ? 'outlined' : 'filled'}
                    />
                  </TableCell>
                  <TableCell>
                    {req.decided_at ? (
                      <>
                        <Typography variant="body2">{req.decided_by ?? '—'}</Typography>
                        <Tooltip title={new Date(req.decided_at).toLocaleString()}>
                          <Typography variant="caption" color="text.secondary" component="div">
                            {relativeTime(req.decided_at)}
                          </Typography>
                        </Tooltip>
                        {req.status === 'APPROVED' && req.granted_roles.length > 0 && (
                          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, mt: 0.5 }}>
                            {req.granted_roles.map((r) => (
                              <Chip key={r} size="small" variant="outlined" label={ROLE_LABELS[r]} />
                            ))}
                          </Box>
                        )}
                        {req.decision_note && (
                          <Tooltip title={req.decision_note}>
                            <Typography variant="caption" color="text.secondary" noWrap component="div" sx={{ maxWidth: 180 }}>
                              “{req.decision_note}”
                            </Typography>
                          </Tooltip>
                        )}
                      </>
                    ) : (
                      <Typography variant="body2" color="text.secondary">
                        —
                      </Typography>
                    )}
                  </TableCell>
                  {canDecide && (
                    <TableCell align="right" sx={{ whiteSpace: 'nowrap' }}>
                      {req.status === 'PENDING' && (
                        <>
                          <Button
                            size="small"
                            color="success"
                            startIcon={<Check />}
                            onClick={() => openApprove(req)}
                          >
                            Approve
                          </Button>
                          <Button
                            size="small"
                            color="error"
                            startIcon={<Close />}
                            onClick={() => openReject(req)}
                          >
                            Reject
                          </Button>
                        </>
                      )}
                    </TableCell>
                  )}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Box>
      )}

      {/* Approve */}
      <Dialog open={!!approving} onClose={() => !busy && setApproving(null)} maxWidth="sm" fullWidth>
        <DialogTitle>Approve access for {approving?.full_name || approving?.username}</DialogTitle>
        <DialogContent>
          <DialogContentText sx={{ mb: 2 }}>
            They asked for <strong>{approving && ROLE_LABELS[approving.requested_role]}</strong>. Choose the
            roles to grant; they can sign in straight away.
          </DialogContentText>
          <TextField
            select
            fullWidth
            label="Roles"
            required
            value={draftRoles}
            error={draftRoles.length === 0}
            helperText={draftRoles.length === 0 ? 'Select at least one role' : undefined}
            SelectProps={{
              multiple: true,
              renderValue: (selected) => (
                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                  {(selected as RoleName[]).map((r) => (
                    <Chip key={r} size="small" label={ROLE_LABELS[r]} color={ROLE_COLORS[r]} />
                  ))}
                </Box>
              ),
            }}
            onChange={(e) => {
              const value = e.target.value as unknown;
              setDraftRoles((typeof value === 'string' ? value.split(',') : value) as RoleName[]);
            }}
          >
            {ROLE_NAMES.map((name) => (
              <MenuItem key={name} value={name}>
                {ROLE_LABELS[name]}
              </MenuItem>
            ))}
          </TextField>
          {draftRoles.includes('ADMIN') && (
            <Alert severity="warning" sx={{ mt: 2 }}>
              Administrator grants full control over users and roles.
            </Alert>
          )}
          {dialogError && (
            <Alert severity="error" sx={{ mt: 2 }}>
              {dialogError}
            </Alert>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setApproving(null)} disabled={busy}>
            Cancel
          </Button>
          <Button
            variant="contained"
            color="success"
            disabled={draftRoles.length === 0 || busy}
            onClick={() => approving && approveMutation.mutate({ id: approving.id, roles: draftRoles })}
          >
            {approveMutation.isPending ? 'Approving…' : 'Approve'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Reject */}
      <Dialog open={!!rejecting} onClose={() => !busy && setRejecting(null)} maxWidth="sm" fullWidth>
        <DialogTitle>Reject request from {rejecting?.full_name || rejecting?.username}?</DialogTitle>
        <DialogContent>
          <DialogContentText sx={{ mb: 2 }}>
            The account stays locked; signing in will tell them the request was declined.
          </DialogContentText>
          <TextField
            fullWidth
            multiline
            minRows={2}
            label="Note (optional)"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            inputProps={{ maxLength: 500 }}
            helperText={`${note.length}/500`}
          />
          {dialogError && (
            <Alert severity="error" sx={{ mt: 2 }}>
              {dialogError}
            </Alert>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRejecting(null)} disabled={busy}>
            Cancel
          </Button>
          <Button
            variant="contained"
            color="error"
            disabled={busy}
            onClick={() =>
              rejecting && rejectMutation.mutate({ id: rejecting.id, note: note.trim() || undefined })
            }
          >
            {rejectMutation.isPending ? 'Rejecting…' : 'Reject'}
          </Button>
        </DialogActions>
      </Dialog>
    </Paper>
  );
}
