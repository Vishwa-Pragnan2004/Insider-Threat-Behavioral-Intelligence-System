import { BrowserRouter } from 'react-router-dom';
import { ThemeProvider, CssBaseline } from '@mui/material';
import theme from './theme/theme';
import { AuthProvider } from './hooks/useAuth';
import AppRoutes from './routes/AppRoutes';

/**
 * App — Root Component
 *
 * Wraps the application with:
 * 1. BrowserRouter — client-side routing
 * 2. ThemeProvider — MUI dark theme
 * 3. CssBaseline — normalizes browser CSS
 * 4. AuthProvider — authentication context
 * 5. AppRoutes — route definitions
 */
export default function App() {
  return (
    <BrowserRouter>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <AuthProvider>
          <AppRoutes />
        </AuthProvider>
      </ThemeProvider>
    </BrowserRouter>
  );
}
