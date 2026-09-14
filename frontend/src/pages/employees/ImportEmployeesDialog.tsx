import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Grid,
  Stack,
  Typography,
} from '@mui/material';
import { UploadFile } from '@mui/icons-material';
import { importEmployees } from '../../api/employeeService';
import { apiErrorMessage } from '../../api/userService';
import type { EmployeeImportResult } from '../../types/employees';

/**
 * ImportEmployeesDialog
 *
 * Uploads a CSV to POST /employees/import. Accepts the ITBIS directory format
 * or a CERT LDAP export as-is; the backend detects which from the header row.
 */

const MAX_ERRORS_SHOWN = 50;

const ITBIS_EXAMPLE = `employee_id,full_name,email,department,job_title,team,manager_employee_id,status,privileged,accounts,devices
E1001,Asha Rao,asha.rao@example.com,Finance,Accountant,Payables,E1000,ACTIVE,false,CORP\\arao;asha.rao@example.com,PC-1001
E1000,Vikram Shah,vikram.shah@example.com,Finance,Finance Manager,Payables,,ACTIVE,true,CORP\\vshah,PC-1000;LAPTOP-22`;

const CERT_EXAMPLE = `employee_name,user_id,email,role,business_unit,functional_unit,department,team,supervisor
Calvin Edward Rios,CER0001,Calvin.Edward.Rios@dtaa.com,Salesman,1,5 - SalesAndMarketing,2 - Sales,3 - RegionalSales,Kaye Hyacinth Gray`;

interface ImportEmployeesDialogProps {
  open: boolean;
  onClose: () => void;
  onImported: (result: EmployeeImportResult) => void;
}

function CodeBlock({ children }: { children: string }) {
  return (
    <Box
      component="pre"
      sx={{
        m: 0,
        p: 1.5,
        bgcolor: 'background.default',
        borderRadius: 1,
        fontSize: '0.72rem',
        fontFamily: '"JetBrains Mono", monospace',
        overflowX: 'auto',
        whiteSpace: 'pre',
      }}
    >
      {children}
    </Box>
  );
}

export default function ImportEmployeesDialog({ open, onClose, onImported }: ImportEmployeesDialogProps) {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<EmployeeImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: (f: File) => importEmployees(f),
    onSuccess: (data) => {
      setResult(data);
      onImported(data);
    },
    onError: (e) => setError(apiErrorMessage(e)),
  });

  const handleClose = () => {
    if (mutation.isPending) return;
    setFile(null);
    setResult(null);
    setError(null);
    onClose();
  };

  const counts: [string, number][] = result
    ? [
        ['Created', result.created],
        ['Updated', result.updated],
        ['Accounts linked', result.accounts_linked],
        ['Devices linked', result.devices_linked],
        ['Skipped', result.skipped],
      ]
    : [];

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="md" fullWidth>
      <DialogTitle>Import employees from CSV</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Typography variant="body2" color="text.secondary">
            Two formats are accepted, detected from the header row. Existing employees (matched by
            employee ID) are updated; new ones are created.
          </Typography>

          <Box>
            <Typography variant="subtitle2" gutterBottom>
              ITBIS directory format
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
              <code>accounts</code> and <code>devices</code> take several values separated by{' '}
              <code>;</code>. <code>status</code> is ACTIVE or LEFT; <code>privileged</code> is true or false.
            </Typography>
            <CodeBlock>{ITBIS_EXAMPLE}</CodeBlock>
          </Box>

          <Box>
            <Typography variant="subtitle2" gutterBottom>
              CERT insider threat dataset LDAP export
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
              Upload the monthly LDAP file unchanged; <code>user_id</code> becomes both the employee ID
              and a linked dataset account.
            </Typography>
            <CodeBlock>{CERT_EXAMPLE}</CodeBlock>
          </Box>

          <Stack direction="row" spacing={2} alignItems="center">
            <Button component="label" variant="outlined" startIcon={<UploadFile />} disabled={mutation.isPending}>
              Choose CSV file
              <input
                hidden
                type="file"
                accept=".csv,text/csv"
                onChange={(e) => {
                  setFile(e.target.files?.[0] ?? null);
                  setResult(null);
                  setError(null);
                  e.target.value = '';
                }}
              />
            </Button>
            <Typography variant="body2" color={file ? 'text.primary' : 'text.secondary'} noWrap>
              {file ? `${file.name} (${(file.size / 1024).toFixed(1)} KB)` : 'No file selected'}
            </Typography>
          </Stack>

          {error && <Alert severity="error">{error}</Alert>}

          {result && (
            <Box>
              <Alert severity={result.errors.length ? 'warning' : 'success'} sx={{ mb: 2 }}>
                Imported as {result.format === 'cert_ldap' ? 'CERT LDAP export' : 'ITBIS directory'}
                {result.errors.length ? ` with ${result.errors.length} error${result.errors.length === 1 ? '' : 's'}` : ''}.
              </Alert>
              <Grid container spacing={1} sx={{ mb: result.errors.length ? 2 : 0 }}>
                {counts.map(([label, value]) => (
                  <Grid item xs={6} sm={4} md key={label}>
                    <Box sx={{ p: 1.5, bgcolor: 'background.default', borderRadius: 1, textAlign: 'center' }}>
                      <Typography variant="h6" sx={{ fontWeight: 700 }}>
                        {value}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {label}
                      </Typography>
                    </Box>
                  </Grid>
                ))}
              </Grid>
              {result.errors.length > 0 && (
                <Box
                  component="ul"
                  sx={{ m: 0, pl: 2.5, maxHeight: 200, overflowY: 'auto', fontSize: '0.8rem', color: 'error.main' }}
                >
                  {result.errors.slice(0, MAX_ERRORS_SHOWN).map((msg, i) => (
                    <li key={i}>{msg}</li>
                  ))}
                  {result.errors.length > MAX_ERRORS_SHOWN && (
                    <li>…and {result.errors.length - MAX_ERRORS_SHOWN} more</li>
                  )}
                </Box>
              )}
            </Box>
          )}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose} disabled={mutation.isPending}>
          {result ? 'Close' : 'Cancel'}
        </Button>
        <Button
          variant="contained"
          disabled={!file || mutation.isPending}
          onClick={() => {
            if (!file) return;
            setError(null);
            setResult(null);
            mutation.mutate(file);
          }}
        >
          {mutation.isPending ? 'Importing…' : 'Import'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
