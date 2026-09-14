import { Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { DASHBOARD_ROUTES, hasPermission } from '../utils/permissions';

import AppLayout from '../components/layout/AppLayout';
import RequirePermission from '../components/auth/RequirePermission';

import LoginPage from '../pages/LoginPage';
import RequestAccessPage from '../pages/RequestAccessPage';
import DashboardPage from '../pages/dashboard/DashboardPage';
import AlertsPage from '../pages/alerts/AlertsPage';
import ActivityPage from '../pages/activity/ActivityPage';
import RiskPage from '../pages/risk/RiskPage';
import EmployeeRiskPage from '../pages/risk/EmployeeRiskPage';
import DetectionsPage from '../pages/detections/DetectionsPage';
import InvestigationsPage from '../pages/investigations/InvestigationsPage';
import InvestigationDetailPage from '../pages/investigations/InvestigationDetailPage';
import ReportsPage from '../pages/reports/ReportsPage';
import SettingsPage from '../pages/settings/SettingsPage';
import UsersPage from '../pages/users/UsersPage';
import EmployeesPage from '../pages/employees/EmployeesPage';
import EmployeeDetailPage from '../pages/employees/EmployeeDetailPage';
import AnalystDashboardPage from '../pages/dashboards/AnalystDashboardPage';
import SocDashboardPage from '../pages/dashboards/SocDashboardPage';
import ManagerDashboardPage from '../pages/dashboards/ManagerDashboardPage';
import { NotFoundPage } from '../pages/NotFoundPage';

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) return null;

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}

/**
 * /dashboard lands users holding exactly one role dashboard straight on it;
 * everyone else (superadmins, multi-role users, no dashboards) gets the overview.
 */
function DashboardHome() {
  const { user } = useAuth();
  if (user && !user.is_superadmin) {
    const permitted = DASHBOARD_ROUTES.filter((d) => hasPermission(user, d.permission));
    if (permitted.length === 1) {
      return <Navigate to={permitted[0].path} replace />;
    }
  }
  return <DashboardPage />;
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
        path="/request-access"
        element={
          isAuthenticated ? <Navigate to="/dashboard" replace /> : <RequestAccessPage />
        }
      />

      <Route
        element={
          <ProtectedRoute>
            <AppLayout />
          </ProtectedRoute>
        }
      >
        <Route path="/dashboard" element={<DashboardHome />} />
        <Route
          path="/dashboards/analyst"
          element={
            <RequirePermission permission="dashboard:analyst">
              <AnalystDashboardPage />
            </RequirePermission>
          }
        />
        <Route
          path="/dashboards/soc"
          element={
            <RequirePermission permission="dashboard:soc">
              <SocDashboardPage />
            </RequirePermission>
          }
        />
        <Route
          path="/dashboards/manager"
          element={
            <RequirePermission permission="dashboard:manager">
              <ManagerDashboardPage />
            </RequirePermission>
          }
        />
        <Route path="/alerts" element={<AlertsPage />} />
        <Route
          path="/risk"
          element={
            <RequirePermission permission="anomaly:read">
              <RiskPage />
            </RequirePermission>
          }
        />
        <Route
          path="/risk/:userId"
          element={
            <RequirePermission permission="anomaly:read">
              <EmployeeRiskPage />
            </RequirePermission>
          }
        />
        <Route
          path="/detections"
          element={
            <RequirePermission permission="anomaly:read">
              <DetectionsPage />
            </RequirePermission>
          }
        />
        <Route
          path="/activity"
          element={
            <RequirePermission permission="behavioral:read">
              <ActivityPage />
            </RequirePermission>
          }
        />
        <Route path="/investigations" element={<InvestigationsPage />} />
        <Route path="/investigations/:id" element={<InvestigationDetailPage />} />
        <Route path="/reports" element={<ReportsPage />} />
        <Route
          path="/users"
          element={
            <RequirePermission permission="users:read">
              <UsersPage />
            </RequirePermission>
          }
        />
        <Route
          path="/employees"
          element={
            <RequirePermission permission="employees:read">
              <EmployeesPage />
            </RequirePermission>
          }
        />
        <Route
          path="/employees/:employeeId"
          element={
            <RequirePermission permission="employees:read">
              <EmployeeDetailPage />
            </RequirePermission>
          }
        />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
