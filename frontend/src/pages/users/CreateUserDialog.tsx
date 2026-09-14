import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  InputAdornment,
  MenuItem,
  Stack,
  TextField,
} from '@mui/material';
import { Visibility, VisibilityOff } from '@mui/icons-material';
import { apiErrorMessage, createUser } from '../../api/userService';
import type { ManagedUser, RoleName } from '../../types/users';
import { ROLE_COLORS, ROLE_LABELS, ROLE_NAMES } from './roles';

/**
 * CreateUserDialog
 *
 * Collects a new account's details and roles. Validation here only catches
 * obvious mistakes early; the backend's password policy is authoritative and
 * its explanation (409 duplicate, 422 weak password) is shown in the dialog.
 */

const USERNAME_PATTERN = /^[A-Za-z0-9._-]+$/;
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const PASSWORD_HINT = 'At least 8 characters with upper, lower, digit and symbol';

interface CreateUserDialogProps {
  open: boolean;
  onClose: () => void;
  onCreated: (user: ManagedUser) => void;
}

interface FormState {
  username: string;
  full_name: string;
  email: string;
  password: string;
  roles: RoleName[];
}

const EMPTY_FORM: FormState = { username: '', full_name: '', email: '', password: '', roles: [] };

function validate(form: FormState): Partial<Record<keyof FormState, string>> {
  const errors: Partial<Record<keyof FormState, string>> = {};
  const username = form.username.trim();
  if (username.length < 3 || username.length > 50) {
    errors.username = 'Must be 3–50 characters';
  } else if (!USERNAME_PATTERN.test(username)) {
    errors.username = 'Only letters, digits, dots, underscores and hyphens';
  }
  if (!form.full_name.trim()) errors.full_name = 'Required';
  if (!EMAIL_PATTERN.test(form.email.trim())) errors.email = 'Enter a valid email address';
  if (form.password.length < 8) errors.password = PASSWORD_HINT;
  if (form.roles.length === 0) errors.roles = 'Select at least one role';
  return errors;
}

export default function CreateUserDialog({ open, onClose, onCreated }: CreateUserDialogProps) {
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [touched, setTouched] = useState<Partial<Record<keyof FormState, boolean>>>({});
  const [submitted, setSubmitted] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);

  const errors = validate(form);
  const isValid = Object.keys(errors).length === 0;
  const errorFor = (field: keyof FormState) =>
    submitted || touched[field] ? errors[field] : undefined;

  const mutation = useMutation({
    mutationFn: () =>
      createUser({
        username: form.username.trim(),
        email: form.email.trim(),
        full_name: form.full_name.trim(),
        password: form.password,
        roles: form.roles,
      }),
    onSuccess: (created) => {
      reset();
      onCreated(created);
    },
    onError: (error) => setServerError(apiErrorMessage(error)),
  });

  function reset() {
    setForm(EMPTY_FORM);
    setTouched({});
    setSubmitted(false);
    setShowPassword(false);
    setServerError(null);
  }

  const handleClose = () => {
    if (mutation.isPending) return;
    reset();
    onClose();
  };

  const handleSubmit = () => {
    setSubmitted(true);
    setServerError(null);
    if (isValid) mutation.mutate();
  };

  const field = (name: Exclude<keyof FormState, 'roles'>) => ({
    value: form[name],
    onChange: (e: React.ChangeEvent<HTMLInputElement>) =>
      setForm((current) => ({ ...current, [name]: e.target.value })),
    onBlur: () => setTouched((current) => ({ ...current, [name]: true })),
    error: !!errorFor(name),
  });

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
      <DialogTitle>Create user</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <TextField
            label="Username"
            autoFocus
            required
            autoComplete="off"
            {...field('username')}
            helperText={errorFor('username') ?? '3–50 characters: letters, digits, . _ -'}
          />
          <TextField
            label="Full name"
            required
            {...field('full_name')}
            helperText={errorFor('full_name')}
          />
          <TextField
            label="Email"
            type="email"
            required
            autoComplete="off"
            {...field('email')}
            helperText={errorFor('email')}
          />
          <TextField
            label="Password"
            type={showPassword ? 'text' : 'password'}
            required
            autoComplete="new-password"
            {...field('password')}
            helperText={PASSWORD_HINT}
            InputProps={{
              endAdornment: (
                <InputAdornment position="end">
                  <IconButton
                    aria-label={showPassword ? 'Hide password' : 'Show password'}
                    onClick={() => setShowPassword((v) => !v)}
                    edge="end"
                  >
                    {showPassword ? <VisibilityOff /> : <Visibility />}
                  </IconButton>
                </InputAdornment>
              ),
            }}
          />
          <TextField
            select
            label="Roles"
            required
            value={form.roles}
            error={!!errorFor('roles')}
            helperText={errorFor('roles')}
            onBlur={() => setTouched((current) => ({ ...current, roles: true }))}
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
              setForm((current) => ({
                ...current,
                roles: (typeof value === 'string' ? value.split(',') : value) as RoleName[],
              }));
            }}
          >
            {ROLE_NAMES.map((name) => (
              <MenuItem key={name} value={name}>
                {ROLE_LABELS[name]}
              </MenuItem>
            ))}
          </TextField>

          {serverError && <Alert severity="error">{serverError}</Alert>}
        </Stack>
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
          {mutation.isPending ? 'Creating…' : 'Create user'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
