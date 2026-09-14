import { useState, type FormEvent } from 'react';
import axios from 'axios';
import { useNavigate, Link as RouterLink } from 'react-router-dom';
import {
  Box,
  Card,
  CardContent,
  TextField,
  Button,
  Typography,
  Alert,
  CircularProgress,
  InputAdornment,
  IconButton,
  Link,
} from '@mui/material';
import { Security, Visibility, VisibilityOff, Email, Lock } from '@mui/icons-material';
import { useAuth } from '../hooks/useAuth';
import { apiErrorMessage } from '../api/userService';

/**
 * LoginPage
 *
 * ITBIS authentication page.
 * Authenticates against POST /api/v1/auth/login and stores tokens.
 */
export default function LoginPage() {
  const navigate = useNavigate();
  const { login } = useAuth();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsLoading(true);

    try {
      await login({ email, password });
      navigate('/');
    } catch (err) {
      // Show the backend's own reason (wrong credentials, request still pending,
      // declined…) rather than axios's "Request failed with status code …".
      if (axios.isAxiosError(err) && err.response) {
        setError(apiErrorMessage(err));
        return;
      }
      setError('Could not reach the server. Please try again.');
    } finally {
      setIsLoading(false);
    }
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
      <Card sx={{ width: '100%', maxWidth: 440, border: '1px solid', borderColor: 'divider' }}>
        <CardContent sx={{ p: 4 }}>
          {/* Logo & Title */}
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
            <Security sx={{ fontSize: 36, color: 'primary.main' }} />
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
              ITBIS
            </Typography>

            <Typography variant="body2" sx={{ color: 'text.secondary' }}>
              Insider Threat Behavioral Intelligence System
            </Typography>
          </Box>

          {/* Error Alert */}
          {error && (
            <Alert severity="error" sx={{ mb: 3 }} onClose={() => setError(null)}>
              {error}
            </Alert>
          )}

          {/* Login Form */}
          <Box component="form" onSubmit={handleSubmit} noValidate>
            {/* Email or username (the API field is still called `email`) */}
            <TextField
              id="email"
              label="Email or username"
              type="text"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              fullWidth
              required
              autoComplete="username"
              autoFocus
              placeholder="analyst@itbis.io or analyst"
              sx={{ mb: 2.5 }}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <Email sx={{ color: 'text.secondary', fontSize: 20 }} />
                  </InputAdornment>
                ),
              }}
            />

            {/* Password Field */}
            <TextField
              id="password"
              label="Password"
              type={showPassword ? 'text' : 'password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              fullWidth
              required
              autoComplete="current-password"
              placeholder="Enter your password"
              sx={{ mb: 3 }}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <Lock sx={{ color: 'text.secondary', fontSize: 20 }} />
                  </InputAdornment>
                ),
                endAdornment: (
                  <InputAdornment position="end">
                    <IconButton
                      onClick={() => setShowPassword(!showPassword)}
                      edge="end"
                      size="small"
                      aria-label={showPassword ? 'hide password' : 'show password'}
                    >
                      {showPassword ? (
                        <VisibilityOff sx={{ fontSize: 20 }} />
                      ) : (
                        <Visibility sx={{ fontSize: 20 }} />
                      )}
                    </IconButton>
                  </InputAdornment>
                ),
              }}
            />

            {/* Submit Button */}
            <Button
              type="submit"
              fullWidth
              variant="contained"
              size="large"
              disabled={isLoading}
              sx={{
                py: 1.5,
                fontSize: '1rem',
                background: 'linear-gradient(135deg, #3b82f6, #1d4ed8)',
                '&:hover': {
                  background: 'linear-gradient(135deg, #2563eb, #1e40af)',
                },
              }}
            >
              {isLoading ? (
                <CircularProgress size={24} color="inherit" />
              ) : (
                'Sign In'
              )}
            </Button>

            <Typography variant="body2" sx={{ mt: 3, textAlign: 'center', color: 'text.secondary' }}>
              Don&apos;t have an account?{' '}
              <Link component={RouterLink} to="/request-access" underline="hover" sx={{ fontWeight: 600 }}>
                Request access
              </Link>
            </Typography>
          </Box>
        </CardContent>
      </Card>
    </Box>
  );
}
