import { useEffect, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import {
  Alert,
  Autocomplete,
  Box,
  Button,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { addEmployeeAccount, listEmployees } from '../../api/employeeService';
import { apiErrorMessage } from '../../api/userService';
import { ACCOUNT_TYPES, type AccountType, type Employee } from '../../types/employees';
import { ACCOUNT_TYPE_LABELS, guessAccountType, useDebouncedValue } from './employeeShared';

/**
 * LinkAccountDialog
 *
 * Links an unmapped account to an employee found by search.
 */

interface LinkAccountDialogProps {
  /** The account to link; null closes the dialog. */
  account: string | null;
  onClose: () => void;
  onLinked: (employee: Employee, account: string) => void;
}

export default function LinkAccountDialog({ account, onClose, onLinked }: LinkAccountDialogProps) {
  const [selected, setSelected] = useState<Employee | null>(null);
  const [input, setInput] = useState('');
  const [accountType, setAccountType] = useState<AccountType>('windows');
  const [error, setError] = useState<string | null>(null);
  const search = useDebouncedValue(input.trim(), 300);

  useEffect(() => {
    if (account) {
      setSelected(null);
      setInput('');
      setAccountType(guessAccountType(account));
      setError(null);
    }
  }, [account]);

  const optionsQuery = useQuery({
    queryKey: ['employees', 'list', { search, limit: 20 }],
    queryFn: () => listEmployees({ ...(search && { search }), limit: 20 }),
    enabled: !!account,
  });

  const mutation = useMutation({
    mutationFn: ({ employee, value }: { employee: Employee; value: string }) =>
      addEmployeeAccount(employee.employee_id, value, accountType),
    onSuccess: (updated, vars) => onLinked(updated, vars.value),
    onError: (e) => setError(apiErrorMessage(e)),
  });

  const handleClose = () => {
    if (!mutation.isPending) onClose();
  };

  return (
    <Dialog open={!!account} onClose={handleClose} maxWidth="sm" fullWidth>
      <DialogTitle>Link account to employee</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Typography variant="body2">
            Account{' '}
            <Box component="span" sx={{ fontFamily: 'monospace', fontWeight: 600 }}>
              {account}
            </Box>
          </Typography>
          <Autocomplete
            options={optionsQuery.data?.employees ?? []}
            value={selected}
            onChange={(_, value) => setSelected(value)}
            inputValue={input}
            onInputChange={(_, value) => setInput(value)}
            filterOptions={(x) => x}
            isOptionEqualToValue={(a, b) => a.id === b.id}
            getOptionLabel={(e) => `${e.full_name} (${e.employee_id})`}
            loading={optionsQuery.isFetching}
            noOptionsText={search ? 'No employees match' : 'Type to search employees'}
            renderOption={(props, e) => (
              <li {...props} key={e.id}>
                <Box>
                  <Typography variant="body2" sx={{ fontWeight: 600 }}>
                    {e.full_name}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {e.employee_id}
                    {e.department ? ` · ${e.department}` : ''}
                    {e.status === 'LEFT' ? ' · Left' : ''}
                  </Typography>
                </Box>
              </li>
            )}
            renderInput={(params) => (
              <TextField
                {...params}
                label="Employee"
                autoFocus
                placeholder="Search name, ID or email"
                InputProps={{
                  ...params.InputProps,
                  endAdornment: (
                    <>
                      {optionsQuery.isFetching && <CircularProgress size={16} />}
                      {params.InputProps.endAdornment}
                    </>
                  ),
                }}
              />
            )}
          />
          <TextField
            select
            label="Account type"
            value={accountType}
            onChange={(e) => setAccountType(e.target.value as AccountType)}
          >
            {ACCOUNT_TYPES.map((t) => (
              <MenuItem key={t} value={t}>
                {ACCOUNT_TYPE_LABELS[t]}
              </MenuItem>
            ))}
          </TextField>
          {error && <Alert severity="error">{error}</Alert>}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose} disabled={mutation.isPending}>
          Cancel
        </Button>
        <Button
          variant="contained"
          disabled={!selected || !account || mutation.isPending}
          onClick={() => {
            if (!selected || !account) return;
            setError(null);
            mutation.mutate({ employee: selected, value: account });
          }}
        >
          {mutation.isPending ? 'Linking…' : 'Link account'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
