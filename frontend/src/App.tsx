import { Routes, Route } from 'react-router-dom';
import { ThemeProvider } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from './hooks/useAuth';
import AppRoutes from './routes/AppRoutes';
import { StatusPage } from './pages/StatusPage';
import { NotFoundPage } from './pages/NotFoundPage';
import { darkTheme } from './theme/darkTheme';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider theme={darkTheme}>
        <CssBaseline />
        <AuthProvider>
          <Routes>
            <Route path="/status" element={<StatusPage />} />
            <Route path="/*" element={<AppRoutes />} />
            <Route path="*" element={<NotFoundPage />} />
          </Routes>
        </AuthProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
