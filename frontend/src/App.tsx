import { Routes, Route, Navigate } from 'react-router-dom';
import { StatusPage } from '@/pages/StatusPage';
import { NotFoundPage } from '@/pages/NotFoundPage';

/**
 * ITBIS — Root Application Component
 *
 * Defines top-level routing for the platform.
 * Additional route groups will be added as modules are implemented:
 *
 * /                    → SOC Dashboard (Phase 11)
 * /alerts              → Alert Management (Phase 8)
 * /investigations      → Threat Investigation (Phase 10)
 * /users               → User Management (Phase 2)
 * /risk                → Risk Scores (Phase 7)
 * /activity            → Activity Timeline (Phase 3)
 * /reports             → Reporting (Phase 12)
 * /admin               → Administration
 * /auth/login          → Login (Phase 1)
 */
export default function App() {
  return (
    <Routes>
      {/* Phase 0 — Foundation placeholder */}
      <Route path="/" element={<Navigate to="/status" replace />} />
      <Route path="/status" element={<StatusPage />} />

      {/* Future routes — uncomment as phases are implemented */}
      {/* <Route path="/dashboard" element={<DashboardPage />} /> */}
      {/* <Route path="/alerts" element={<AlertsPage />} /> */}
      {/* <Route path="/investigations/*" element={<InvestigationsPage />} /> */}
      {/* <Route path="/auth/login" element={<LoginPage />} /> */}

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}
