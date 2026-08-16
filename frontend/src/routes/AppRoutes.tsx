import { Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';

// Layout
import AppLayout from '../components/layout/AppLayout';

// Pages
import LoginPage from '../pages/LoginPage';
import DashboardPage from '../pages/DashboardPage';

/**
 * AppRoutes
 *
 * Application routing configuration with authentication guards.
 *
 * - /login       → Login page (public)
 * - /            → Dashboard (protected)
 * - /image-analysis, /inventory, etc. → Coming in future stages
 *
 * Protected routes are wrapped in AppLayout (sidebar + topbar).
 * Unauthenticated users are redirected to /login.
 * Authenticated users visiting /login are redirected to /.
 */

/** Wrapper that redirects to /login if the user is not authenticated */
function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();

  // While checking stored auth, don't redirect yet
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
      {/* Public Route: Login */}
      <Route
        path="/login"
        element={
          isAuthenticated ? <Navigate to="/" replace /> : <LoginPage />
        }
      />

      {/* Protected Routes: Wrapped in AppLayout */}
      <Route
        element={
          <ProtectedRoute>
            <AppLayout />
          </ProtectedRoute>
        }
      >
        {/* Dashboard — index route */}
        <Route index element={<DashboardPage />} />

        {/* 
          Future pages will be added here:
          <Route path="/image-analysis" element={<ImageAnalysisPage />} />
          <Route path="/inventory" element={<InventoryPage />} />
          <Route path="/inventory/:id" element={<ProductDetailPage />} />
          <Route path="/alerts" element={<AlertsPage />} />
          <Route path="/recommendations" element={<RecommendationsPage />} />
          <Route path="/analytics" element={<AnalyticsPage />} />
          <Route path="/reports" element={<ReportsPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        */}

        {/* Placeholder for unbuilt pages — shows a "Coming Soon" message */}
        <Route path="*" element={<ComingSoon />} />
      </Route>
    </Routes>
  );
}

/**
 * Temporary placeholder for pages that haven't been built yet.
 * Will be removed as each page is implemented.
 */
function ComingSoon() {
  return (
    <div style={{ textAlign: 'center', paddingTop: '10vh' }}>
      <h2 style={{ color: '#94A3B8' }}>🚧 Coming Soon</h2>
      <p style={{ color: '#475569' }}>This page will be built in a future stage.</p>
    </div>
  );
}
