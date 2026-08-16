import { useState } from 'react';
import { Outlet } from 'react-router-dom';
import { Box, useMediaQuery, useTheme } from '@mui/material';
import Sidebar from './Sidebar';
import Topbar from './Topbar';

/**
 * AppLayout
 *
 * Main application shell that wraps all authenticated pages.
 * Contains a collapsible sidebar, top navigation bar, and a
 * scrollable content area where page components render via <Outlet />.
 *
 * Layout structure:
 * ┌──────┬──────────────────────────────┐
 * │      │         Topbar               │
 * │ Side ├──────────────────────────────┤
 * │ bar  │                              │
 * │      │      Content (<Outlet />)    │
 * │      │                              │
 * └──────┴──────────────────────────────┘
 */

const SIDEBAR_WIDTH = 260;           // Full sidebar width in pixels
const SIDEBAR_COLLAPSED_WIDTH = 72;  // Collapsed sidebar width

export default function AppLayout() {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));

  // Sidebar state: collapsed on desktop, drawer on mobile
  const [sidebarOpen, setSidebarOpen] = useState(!isMobile);

  const toggleSidebar = () => setSidebarOpen((prev) => !prev);

  // Calculate content margin based on sidebar state
  const sidebarWidth = isMobile
    ? 0 // Mobile: sidebar is an overlay, no margin
    : sidebarOpen
      ? SIDEBAR_WIDTH
      : SIDEBAR_COLLAPSED_WIDTH;

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh', bgcolor: 'background.default' }}>
      {/* Sidebar Navigation */}
      <Sidebar
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        width={SIDEBAR_WIDTH}
        collapsedWidth={SIDEBAR_COLLAPSED_WIDTH}
        isMobile={isMobile}
      />

      {/* Main Content Area */}
      <Box
        component="main"
        sx={{
          flexGrow: 1,
          ml: `${sidebarWidth}px`,
          transition: 'margin-left 0.3s ease',
          display: 'flex',
          flexDirection: 'column',
          minHeight: '100vh',
        }}
      >
        {/* Top Navigation Bar */}
        <Topbar onMenuClick={toggleSidebar} />

        {/* Page Content — rendered by React Router */}
        <Box
          sx={{
            flexGrow: 1,
            p: { xs: 2, sm: 3 },
            overflow: 'auto',
          }}
        >
          <Outlet />
        </Box>
      </Box>
    </Box>
  );
}
