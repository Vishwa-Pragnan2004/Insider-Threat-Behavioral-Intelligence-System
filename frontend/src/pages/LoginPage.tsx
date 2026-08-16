import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Card,
  CardContent,
  TextField,
  Button,
  Typography,
  Checkbox,
  FormControlLabel,
  Alert,
  CircularProgress,
  InputAdornment,
  IconButton,
} from '@mui/material';
import SpaIcon from '@mui/icons-material/Spa';
import VisibilityIcon from '@mui/icons-material/Visibility';
import VisibilityOffIcon from '@mui/icons-material/VisibilityOff';
import EmailIcon from '@mui/icons-material/Email';
import LockIcon from '@mui/icons-material/Lock';
import { useAuth } from '../hooks/useAuth';

/**
 * LoginPage
 *
 * Full-screen centered login form with app branding.
 * Uses mock authentication — any valid-looking email + password (4+ chars) works.
 *
 * On successful login, navigates to the Dashboard.
 */
export default function LoginPage() {
  const navigate = useNavigate();
  const { login } = useAuth();

  // Form state
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [rememberMe, setRememberMe] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  // UI state
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Handle form submission
  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsLoading(true);

    try {
      await login({ email, password });
      navigate('/'); // Redirect to Dashboard
    } catch (err) {
      // Show the error message from the auth service
      setError(err instanceof Error ? err.message : 'Login failed. Please try again.');
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
        // Subtle gradient overlay for visual interest
        background: 'linear-gradient(135deg, #0A0E17 0%, #111827 50%, #0F172A 100%)',
        p: 2,
      }}
    >
      <Card
        sx={{
          width: '100%',
          maxWidth: 440,
          border: '1px solid',
          borderColor: 'divider',
        }}
      >
        <CardContent sx={{ p: 4 }}>
          {/* App Logo & Title */}
          <Box sx={{ textAlign: 'center', mb: 4 }}>
            <Box
              sx={{
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: 64,
                height: 64,
                borderRadius: 3,
                bgcolor: 'rgba(0, 188, 212, 0.12)',
                mb: 2,
              }}
            >
              <SpaIcon sx={{ fontSize: 36, color: 'primary.main' }} />
            </Box>

            <Typography
              variant="h4"
              sx={{
                fontWeight: 700,
                mb: 0.5,
                background: 'linear-gradient(135deg, #00BCD4, #10B981)',
                backgroundClip: 'text',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
              }}
            >
              FreshTrack
            </Typography>

            <Typography variant="body2" sx={{ color: 'text.secondary' }}>
              Food Freshness Monitoring Platform
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
            {/* Email Field */}
            <TextField
              id="email"
              label="Email Address"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              fullWidth
              required
              autoComplete="email"
              autoFocus
              placeholder="sarah.chen@freshtrack.io"
              sx={{ mb: 2.5 }}
              slotProps={{
                input: {
                  startAdornment: (
                    <InputAdornment position="start">
                      <EmailIcon sx={{ color: 'text.secondary', fontSize: 20 }} />
                    </InputAdornment>
                  ),
                },
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
              sx={{ mb: 2 }}
              slotProps={{
                input: {
                  startAdornment: (
                    <InputAdornment position="start">
                      <LockIcon sx={{ color: 'text.secondary', fontSize: 20 }} />
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
                          <VisibilityOffIcon sx={{ fontSize: 20 }} />
                        ) : (
                          <VisibilityIcon sx={{ fontSize: 20 }} />
                        )}
                      </IconButton>
                    </InputAdornment>
                  ),
                },
              }}
            />

            {/* Remember Me */}
            <FormControlLabel
              control={
                <Checkbox
                  checked={rememberMe}
                  onChange={(e) => setRememberMe(e.target.checked)}
                  color="primary"
                  size="small"
                />
              }
              label={
                <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                  Remember me
                </Typography>
              }
              sx={{ mb: 3 }}
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
                background: 'linear-gradient(135deg, #00BCD4, #00838F)',
                '&:hover': {
                  background: 'linear-gradient(135deg, #00ACC1, #006064)',
                },
              }}
            >
              {isLoading ? (
                <CircularProgress size={24} color="inherit" />
              ) : (
                'Sign In'
              )}
            </Button>
          </Box>

          {/* Hint for demo */}
          <Box sx={{ mt: 3, textAlign: 'center' }}>
            <Typography variant="body2" sx={{ color: 'text.disabled', fontSize: '0.75rem' }}>
              Demo: Use any valid email and password (4+ characters)
            </Typography>
          </Box>
        </CardContent>
      </Card>
    </Box>
  );
}
