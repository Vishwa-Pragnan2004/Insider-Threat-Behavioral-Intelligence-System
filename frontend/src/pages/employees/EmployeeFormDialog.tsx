import { useEffect, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  Grid,
  MenuItem,
  Switch,
  TextField,
} from '@mui/material';
import { createEmployee, updateEmployee } from '../../api/employeeService';
import { apiErrorMessage } from '../../api/userService';
import type { Employee, EmployeeStatus } from '../../types/employees';
import { EMAIL_PATTERN, EMPLOYEE_ID_PATTERN } from './employeeShared';

/**
 * EmployeeFormDialog
 *
 * Creates an employee (POST /employees) or, given `employee`, edits one
 * (PATCH /employees/{id}; the employee ID itself can't change). Client checks
 * catch obvious mistakes; the backend's 409/422 explanation is shown inline.
 */

interface EmployeeFormDialogProps {
  open: boolean;
  /** Edit this employee; omit to create a new one. */
  employee?: Employee | null;
  onClose: () => void;
  onSaved: (employee: Employee) => void;
}

interface FormState {
  employee_id: string;
  full_name: string;
  email: string;
  department: string;
  job_title: string;
  team: string;
  manager_employee_id: string;
  status: EmployeeStatus;
  privileged: boolean;
}

type TextKey = Exclude<keyof FormState, 'status' | 'privileged'>;

const EMPTY_FORM: FormState = {
  employee_id: '',
  full_name: '',
  email: '',
  department: '',
  job_title: '',
  team: '',
  manager_employee_id: '',
  status: 'ACTIVE',
  privileged: false,
};

function fromEmployee(e: Employee): FormState {
  return {
    employee_id: e.employee_id,
    full_name: e.full_name,
    email: e.email ?? '',
    department: e.department ?? '',
    job_title: e.job_title ?? '',
    team: e.team ?? '',
    manager_employee_id: e.manager_employee_id ?? '',
    status: e.status,
    privileged: e.privileged,
  };
}

function validate(form: FormState, isEdit: boolean): Partial<Record<keyof FormState, string>> {
  const errors: Partial<Record<keyof FormState, string>> = {};
  const id = form.employee_id.trim();
  if (!isEdit) {
    if (id.length < 1 || id.length > 64) errors.employee_id = 'Must be 1–64 characters';
    else if (!EMPLOYEE_ID_PATTERN.test(id)) errors.employee_id = 'Only letters, digits and . _ @ \\ -';
  }
  if (!form.full_name.trim()) errors.full_name = 'Required';
  const email = form.email.trim();
  if (email && !EMAIL_PATTERN.test(email)) errors.email = 'Enter a valid email address';
  const manager = form.manager_employee_id.trim();
  if (manager && !EMPLOYEE_ID_PATTERN.test(manager)) {
    errors.manager_employee_id = 'Not a valid employee ID';
  } else if (manager && manager === (isEdit ? form.employee_id : id)) {
    errors.manager_employee_id = "An employee can't manage themselves";
  }
  return errors;
}

export default function EmployeeFormDialog({ open, employee, onClose, onSaved }: EmployeeFormDialogProps) {
  const isEdit = !!employee;
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [touched, setTouched] = useState<Partial<Record<keyof FormState, boolean>>>({});
  const [submitted, setSubmitted] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setForm(employee ? fromEmployee(employee) : EMPTY_FORM);
      setTouched({});
      setSubmitted(false);
      setServerError(null);
    }
    // Reset only when the dialog opens (or targets another employee), not on background refetches.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, employee?.id]);

  const errors = validate(form, isEdit);
  const isValid = Object.keys(errors).length === 0;
  const errorFor = (name: keyof FormState) => (submitted || touched[name] ? errors[name] : undefined);

  const mutation = useMutation({
    mutationFn: () => {
      const body = {
        full_name: form.full_name.trim(),
        email: form.email.trim() || null,
        department: form.department.trim(),
        job_title: form.job_title.trim(),
        team: form.team.trim(),
        manager_employee_id: form.manager_employee_id.trim() || null,
        status: form.status,
        privileged: form.privileged,
      };
      return employee
        ? updateEmployee(employee.employee_id, body)
        : createEmployee({ employee_id: form.employee_id.trim(), ...body });
    },
    onSuccess: (saved) => onSaved(saved),
    onError: (error) => setServerError(apiErrorMessage(error)),
  });

  const handleClose = () => {
    if (!mutation.isPending) onClose();
  };

  const handleSubmit = () => {
    setSubmitted(true);
    setServerError(null);
    if (isValid) mutation.mutate();
  };

  const field = (name: TextKey) => ({
    value: form[name],
    onChange: (e: React.ChangeEvent<HTMLInputElement>) =>
      setForm((current) => ({ ...current, [name]: e.target.value })),
    onBlur: () => setTouched((current) => ({ ...current, [name]: true })),
    error: !!errorFor(name),
    fullWidth: true,
  });

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
      <DialogTitle>{isEdit ? `Edit ${employee?.full_name}` : 'Add employee'}</DialogTitle>
      <DialogContent>
        <Grid container spacing={2} sx={{ mt: 0 }}>
          <Grid item xs={12} sm={6}>
            <TextField
              label="Employee ID"
              required
              autoFocus={!isEdit}
              autoComplete="off"
              disabled={isEdit}
              {...field('employee_id')}
              helperText={errorFor('employee_id') ?? (isEdit ? "Can't be changed" : 'e.g. E1024 or BBS0039')}
            />
          </Grid>
          <Grid item xs={12} sm={6}>
            <TextField
              label="Full name"
              required
              autoFocus={isEdit}
              {...field('full_name')}
              helperText={errorFor('full_name')}
            />
          </Grid>
          <Grid item xs={12}>
            <TextField
              label="Email"
              type="email"
              autoComplete="off"
              {...field('email')}
              helperText={errorFor('email') ?? 'Optional'}
            />
          </Grid>
          <Grid item xs={12} sm={6}>
            <TextField label="Department" {...field('department')} />
          </Grid>
          <Grid item xs={12} sm={6}>
            <TextField label="Job title" {...field('job_title')} />
          </Grid>
          <Grid item xs={12} sm={6}>
            <TextField label="Team" {...field('team')} />
          </Grid>
          <Grid item xs={12} sm={6}>
            <TextField
              label="Manager employee ID"
              autoComplete="off"
              {...field('manager_employee_id')}
              helperText={errorFor('manager_employee_id') ?? 'Optional'}
            />
          </Grid>
          <Grid item xs={12} sm={6}>
            <TextField
              select
              fullWidth
              label="Status"
              value={form.status}
              onChange={(e) => setForm((c) => ({ ...c, status: e.target.value as EmployeeStatus }))}
            >
              <MenuItem value="ACTIVE">Active</MenuItem>
              <MenuItem value="LEFT">Left</MenuItem>
            </TextField>
          </Grid>
          <Grid item xs={12} sm={6} sx={{ display: 'flex', alignItems: 'center' }}>
            <FormControlLabel
              control={
                <Switch
                  checked={form.privileged}
                  onChange={(e) => setForm((c) => ({ ...c, privileged: e.target.checked }))}
                />
              }
              label="Privileged account holder"
            />
          </Grid>
          {serverError && (
            <Grid item xs={12}>
              <Alert severity="error">{serverError}</Alert>
            </Grid>
          )}
        </Grid>
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose} disabled={mutation.isPending}>
          Cancel
        </Button>
        <Button
          variant="contained"
          onClick={handleSubmit}
          disabled={mutation.isPending || (submitted && !isValid)}
        >
          {mutation.isPending ? 'Saving…' : isEdit ? 'Save changes' : 'Add employee'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
