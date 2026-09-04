import { Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';

import AppLayout from '../components/layout/AppLayout';

import LoginPage from '../pages/LoginPage';
import DashboardPage from '../pages/dashboard/DashboardPage';
import AlertsPage from '../pages/alerts/AlertsPage';
import InvestigationsPage from '../pages/investigations/InvestigationsPage';
import InvestigationDetailPage from '../pages/investigations/InvestigationDetailPage';
import ReportsPage from '../pages/reports/ReportsPage';
import SettingsPage from '../pages/settings/SettingsPage';
import { NotFoundPage } from '../pages/NotFoundPage';

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) return null;

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}

export default function AppRoutes() {
  const { isAuthenticated } = useAuth();

  return (
    <Routes>
      <Route
        path="/login"
        element={
          isAuthenticated ? <Navigate to="/dashboard" replace /> : <LoginPage />
        }
      />

      <Route
        element={
          <ProtectedRoute>
            <AppLayout />
          </ProtectedRoute>
        }
      >
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/alerts" element={<AlertsPage />} />
        <Route path="/investigations" element={<InvestigationsPage />} />
        <Route path="/investigations/:id" element={<InvestigationDetailPage />} />
        <Route path="/reports" element={<ReportsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
