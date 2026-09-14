import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  MenuItem,
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
import { CheckCircle, Link as LinkIcon, Refresh } from '@mui/icons-material';
import EmptyState from '../../components/common/EmptyState';
import { listUnmappedAccounts } from '../../api/employeeService';
import { apiErrorMessage } from '../../api/userService';
import type { Employee } from '../../types/employees';
import { formatDateTime, formatNumber } from '../dashboards/shared';
import LinkAccountDialog from './LinkAccountDialog';

const WINDOWS = [7, 30, 90] as const;
const DEVICES_SHOWN = 3;

/**
 * Unmapped accounts
 *
 * Accounts that appear in ingested events but belong to no employee, so their
 * activity can't be attributed. Managers can link each one to an employee.
 */
export default function UnmappedAccountsSection({
  canManage,
  onNotice,
}: {
  canManage: boolean;
  onNotice: (message: string) => void;
}) {
  const queryClient = useQueryClient();
  const [days, setDays] = useState<number>(30);
  const [linking, setLinking] = useState<string | null>(null);

  const query = useQuery({
    queryKey: ['employees', 'unmapped', days],
    queryFn: () => listUnmappedAccounts(days),
  });
  const accounts = query.data?.accounts ?? [];

  const handleLinked = (employee: Employee, account: string) => {
    setLinking(null);
    onNotice(`Linked ${account} to ${employee.full_name}.`);
    queryClient.invalidateQueries({ queryKey: ['employees'] });
  };

  return (
    <Box>
      <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 2 }} flexWrap="wrap" useFlexGap>
        <TextField
          select
          size="small"
          label="Seen in"
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
          sx={{ minWidth: 150 }}
        >
          {WINDOWS.map((d) => (
            <MenuItem key={d} value={d}>
              Last {d} days
            </MenuItem>
          ))}
        </TextField>
        <Button
          size="small"
          startIcon={query.isFetching ? <CircularProgress size={16} /> : <Refresh />}
          disabled={query.isFetching}
          onClick={() => query.refetch()}
        >
          Refresh
        </Button>
        <Typography variant="body2" color="text.secondary">
          Activity from these accounts can't be attributed to an employee until they're linked.
        </Typography>
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
      ) : !query.isError && accounts.length === 0 ? (
        <EmptyState
          icon={<CheckCircle sx={{ fontSize: 56 }} />}
          title="Every account is mapped"
          description={`All accounts seen in the last ${days} days belong to an employee.`}
        />
      ) : accounts.length > 0 ? (
        <Box sx={{ overflowX: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Account</TableCell>
                <TableCell align="right">Events</TableCell>
                <TableCell>Devices</TableCell>
                <TableCell>Last seen</TableCell>
                {canManage && <TableCell align="right">Actions</TableCell>}
              </TableRow>
            </TableHead>
            <TableBody>
              {accounts.map((a) => (
                <TableRow key={a.account} hover>
                  <TableCell sx={{ fontFamily: 'monospace', fontWeight: 600, whiteSpace: 'nowrap' }}>
                    {a.account}
                  </TableCell>
                  <TableCell align="right" sx={{ fontFamily: 'monospace' }}>
                    {formatNumber(a.events)}
                  </TableCell>
                  <TableCell>
                    <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                      {a.devices.slice(0, DEVICES_SHOWN).map((d) => (
                        <Chip key={d} size="small" variant="outlined" label={d} />
                      ))}
                      {a.devices.length > DEVICES_SHOWN && (
                        <Tooltip title={a.devices.slice(DEVICES_SHOWN).join(', ')}>
                          <Chip size="small" label={`+${a.devices.length - DEVICES_SHOWN}`} />
                        </Tooltip>
                      )}
                    </Box>
                  </TableCell>
                  <TableCell sx={{ whiteSpace: 'nowrap' }}>{formatDateTime(a.last_seen)}</TableCell>
                  {canManage && (
                    <TableCell align="right">
                      <Button size="small" startIcon={<LinkIcon />} onClick={() => setLinking(a.account)}>
                        Link to employee
                      </Button>
                    </TableCell>
                  )}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Box>
      ) : null}

      <LinkAccountDialog account={linking} onClose={() => setLinking(null)} onLinked={handleLinked} />
    </Box>
  );
}
