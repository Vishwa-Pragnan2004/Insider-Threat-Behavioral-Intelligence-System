import { useState, type ChangeEvent, type FormEvent } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  FormControl,
  FormControlLabel,
  FormHelperText,
  FormLabel,
  IconButton,
  InputAdornment,
  Link,
  Radio,
  RadioGroup,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { CheckCircle, HowToReg, Visibility, VisibilityOff } from '@mui/icons-material';
import { submitAccessRequest } from '../api/authService';
import { apiErrorMessage } from '../api/userService';
import type { RequestableRole } from '../types/users';

/**
 * RequestAccessPage
 *
 * Public form for people who need an ITBIS account. The account it creates
 * stays locked until an administrator approves the request on the Users page
 * (and chooses the roles actually granted). The backend's password policy
 * is authoritative; its 409/422 explanations are shown inline.
 */

const USERNAME_PATTERN = /^[A-Za-z0-9._-]+$/;
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const PASSWORD_HINT = 'At least 8 characters with upper, lower, digit and symbol';

const ROLE_OPTIONS: { value: RequestableRole; title: string; description: string }[] = [
  { value: 'SECURITY_ANALYST', title: 'Security Analyst', description: 'Triage alerts, investigate insider risk' },
  { value: 'SOC_ENGINEER', title: 'SOC Engineer', description: 'Monitor security events, anomalies and sensors' },
  { value: 'SECURITY_MANAGER', title: 'Security Manager', description: 'Organisational risk posture, trends and compliance' },
  { value: 'INVESTIGATOR', title: 'Investigator', description: 'Work assigned investigations' },
  { value: 'VIEWER', title: 'Viewer', description: 'Read-only access' },
];

interface FormState {
  full_name: string;
  username: string;
  email: string;
  password: string;
  confirm: string;
  requested_role: RequestableRole | '';
  reason: string;
}

type Field = keyof FormState;

const EMPTY_FORM: FormState = {
  full_name: '',
  username: '',
  email: '',
  password: '',
  confirm: '',
  requested_role: '',
  reason: '',
};

function validate(form: FormState): Partial<Record<Field, string>> {
  const errors: Partial<Record<Field, string>> = {};
  if (!form.full_name.trim()) errors.full_name = 'Required';
  const username = form.username.trim();
  if (username.length < 3 || username.length > 50) {
    errors.username = 'Must be 3–50 characters';
  } else if (!USERNAME_PATTERN.test(username)) {
    errors.username = 'Only letters, digits, dots, underscores and hyphens';
  }
  if (!EMAIL_PATTERN.test(form.email.trim())) errors.email = 'Enter a valid email address';
  if (form.password.length < 8) errors.password = PASSWORD_HINT;
  if (form.confirm !== form.password) errors.confirm = "Passwords don't match";
  if (!form.requested_role) errors.requested_role = 'Choose the role you need';
  const reason = form.reason.trim();
  if (reason.length < 10) errors.reason = 'At least 10 characters';
  else if (reason.length > 1000) errors.reason = 'At most 1000 characters';
  return errors;
}

export default function RequestAccessPage() {
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [touched, setTouched] = useState<Partial<Record<Field, boolean>>>({});
  const [submitted, setSubmitted] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);

  const errors = validate(form);
  const isValid = Object.keys(errors).length === 0;
  const errorFor = (name: Field) => (submitted || touched[name] ? errors[name] : undefined);

  const mutation = useMutation({
    mutationFn: () =>
      submitAccessRequest({
        full_name: form.full_name.trim(),
        username: form.username.trim(),
        email: form.email.trim(),
        password: form.password,
        requested_role: form.requested_role as RequestableRole,
        reason: form.reason.trim(),
      }),
    onError: (error) => setServerError(apiErrorMessage(error)),
  });

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    setSubmitted(true);
    setServerError(null);
    if (isValid) mutation.mutate();
  };

  const field = (name: Exclude<Field, 'requested_role'>) => ({
    id: name,
    value: form[name],
    onChange: (e: ChangeEvent<HTMLInputElement>) =>
      setForm((current) => ({ ...current, [name]: e.target.value })),
    onBlur: () => setTouched((current) => ({ ...current, [name]: true })),
    error: !!errorFor(name),
    fullWidth: true,
  });

  const passwordAdornment = {
    endAdornment: (
      <InputAdornment position="end">
        <IconButton
          aria-label={showPassword ? 'Hide password' : 'Show password'}
          onClick={() => setShowPassword((v) => !v)}
          edge="end"
          size="small"
        >
          {showPassword ? <VisibilityOff sx={{ fontSize: 20 }} /> : <Visibility sx={{ fontSize: 20 }} />}
        </IconButton>
      </InputAdornment>
    ),
  };

  return (
    <Box
      sx={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        bgcolor: 'background.default',
        background: 'linear-gradient(135deg, #020617 0%, #0f172a 50%, #020617 100%)',
        p: 2,
      }}
    >
      <Card sx={{ width: '100%', maxWidth: 560, border: '1px solid', borderColor: 'divider', my: 4 }}>
        <CardContent sx={{ p: { xs: 3, sm: 4 } }}>
          <Box sx={{ textAlign: 'center', mb: 4 }}>
            <Box
              sx={{
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: 64,
                height: 64,
                borderRadius: 3,
                bgcolor: 'rgba(59, 130, 246, 0.12)',
                border: '1px solid rgba(59, 130, 246, 0.3)',
                mb: 2,
              }}
            >
              <HowToReg sx={{ fontSize: 36, color: 'primary.main' }} />
            </Box>
            <Typography
              variant="h4"
              sx={{
                fontWeight: 700,
                mb: 0.5,
                background: 'linear-gradient(135deg, #3b82f6, #10b981)',
                backgroundClip: 'text',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
              }}
            >
              Request access
            </Typography>
            <Typography variant="body2" sx={{ color: 'text.secondary' }}>
              An administrator reviews every request before the account can sign in.
            </Typography>
          </Box>

          {mutation.isSuccess ? (
            <Stack spacing={3} alignItems="center" sx={{ textAlign: 'center' }}>
              <CheckCircle sx={{ fontSize: 48, color: 'success.main' }} />
              <Typography variant="body1">
                Request submitted. An administrator will review it; you&apos;ll be able to sign in
                once it&apos;s approved.
              </Typography>
              <Button component={RouterLink} to="/login" variant="outlined">
                Back to sign in
              </Button>
            </Stack>
          ) : (
            <Box component="form" onSubmit={handleSubmit} noValidate>
              <Stack spacing={2.5}>
                <TextField
                  label="Full name"
                  required
                  autoFocus
                  autoComplete="name"
                  {...field('full_name')}
                  helperText={errorFor('full_name')}
                />
                <TextField
                  label="Username"
                  required
                  autoComplete="username"
                  {...field('username')}
                  helperText={errorFor('username') ?? '3–50 characters: letters, digits, . _ -'}
                />
                <TextField
                  label="Work email"
                  type="email"
                  required
                  autoComplete="email"
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
                  InputProps={passwordAdornment}
                />
                <TextField
                  label="Confirm password"
                  type={showPassword ? 'text' : 'password'}
                  required
                  autoComplete="new-password"
                  {...field('confirm')}
                  helperText={errorFor('confirm')}
                />

                <FormControl error={!!errorFor('requested_role')} required>
                  <FormLabel sx={{ mb: 1 }}>Role needed</FormLabel>
                  <RadioGroup
                    value={form.requested_role}
                    onChange={(e) => {
                      setForm((current) => ({ ...current, requested_role: e.target.value as RequestableRole }));
                      setTouched((current) => ({ ...current, requested_role: true }));
                    }}
                  >
                    <Stack spacing={1}>
                      {ROLE_OPTIONS.map((option) => {
                        const selected = form.requested_role === option.value;
                        return (
                          <FormControlLabel
                            key={option.value}
                            value={option.value}
                            control={<Radio size="small" />}
                            sx={{
                              m: 0,
                              px: 1,
                              py: 0.75,
                              borderRadius: 2,
                              border: '1px solid',
                              borderColor: selected ? 'primary.main' : 'divider',
                              bgcolor: selected ? 'rgba(59, 130, 246, 0.08)' : 'transparent',
                              transition: 'border-color 0.15s, background-color 0.15s',
                              '&:hover': { borderColor: 'primary.light' },
                            }}
                            label={
                              <Box sx={{ py: 0.25 }}>
                                <Typography variant="body2" sx={{ fontWeight: 600 }}>
                                  {option.title}
                                </Typography>
                                <Typography variant="caption" color="text.secondary">
                                  {option.description}
                                </Typography>
                              </Box>
                            }
                          />
                        );
                      })}
                    </Stack>
                  </RadioGroup>
                  {errorFor('requested_role') && <FormHelperText>{errorFor('requested_role')}</FormHelperText>}
                </FormControl>

                <TextField
                  label="Why do you need this access?"
                  required
                  multiline
                  minRows={3}
                  {...field('reason')}
                  inputProps={{ maxLength: 1000 }}
                  helperText={errorFor('reason') ?? `${form.reason.trim().length}/1000 (at least 10)`}
                />

                {serverError && <Alert severity="error">{serverError}</Alert>}

                <Button
                  type="submit"
                  fullWidth
                  variant="contained"
                  size="large"
                  disabled={mutation.isPending || (submitted && !isValid)}
                  sx={{
                    py: 1.5,
                    fontSize: '1rem',
                    background: 'linear-gradient(135deg, #3b82f6, #1d4ed8)',
                    '&:hover': { background: 'linear-gradient(135deg, #2563eb, #1e40af)' },
                  }}
                >
                  {mutation.isPending ? <CircularProgress size={24} color="inherit" /> : 'Submit request'}
                </Button>

                <Typography variant="body2" sx={{ textAlign: 'center', color: 'text.secondary' }}>
                  Already have an account?{' '}
                  <Link component={RouterLink} to="/login" underline="hover" sx={{ fontWeight: 600 }}>
                    Sign in
                  </Link>
                </Typography>
              </Stack>
            </Box>
          )}
        </CardContent>
      </Card>
    </Box>
  );
}
