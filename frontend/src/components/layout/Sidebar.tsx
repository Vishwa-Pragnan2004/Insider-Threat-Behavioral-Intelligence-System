import { useLocation, useNavigate } from 'react-router-dom';
import {
  Box,
  Drawer,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Typography,
  Divider,
  Tooltip,
} from '@mui/material';

// Icons for each navigation item
import DashboardIcon from '@mui/icons-material/Dashboard';
import ImageSearchIcon from '@mui/icons-material/ImageSearch';
import InventoryIcon from '@mui/icons-material/Inventory2';
import NotificationsActiveIcon from '@mui/icons-material/NotificationsActive';
import RecommendIcon from '@mui/icons-material/Lightbulb';
import AnalyticsIcon from '@mui/icons-material/BarChart';
import AssessmentIcon from '@mui/icons-material/Assessment';
import SettingsIcon from '@mui/icons-material/Settings';
import SpaIcon from '@mui/icons-material/Spa';

/**
 * Sidebar Navigation
 *
 * Collapsible sidebar with navigation links to all pages.
 * Shows icons + text when expanded, icons only when collapsed.
 * On mobile, renders as an overlay drawer.
 */

interface SidebarProps {
  open: boolean;
  onClose: () => void;
  width: number;
  collapsedWidth: number;
  isMobile: boolean;
}

// Navigation items — add new pages here as they're built
const navItems = [
  { label: 'Dashboard',       path: '/',               icon: <DashboardIcon /> },
  { label: 'Image Analysis',  path: '/image-analysis',  icon: <ImageSearchIcon /> },
  { label: 'Inventory',       path: '/inventory',       icon: <InventoryIcon /> },
  { label: 'Alerts',          path: '/alerts',          icon: <NotificationsActiveIcon /> },
  { label: 'Recommendations', path: '/recommendations', icon: <RecommendIcon /> },
  { label: 'Analytics',       path: '/analytics',       icon: <AnalyticsIcon /> },
  { label: 'Reports',         path: '/reports',         icon: <AssessmentIcon /> },
];

const bottomNavItems = [
  { label: 'Settings', path: '/settings', icon: <SettingsIcon /> },
];

export default function Sidebar({ open, onClose, width, collapsedWidth, isMobile }: SidebarProps) {
  const location = useLocation();
  const navigate = useNavigate();

  // Current sidebar width based on open/collapsed state
  const currentWidth = open ? width : collapsedWidth;

  // Navigate to a page and close mobile drawer
  const handleNav = (path: string) => {
    navigate(path);
    if (isMobile) onClose();
  };

  // Check if a nav item is active
  const isActive = (path: string) => {
    if (path === '/') return location.pathname === '/';
    return location.pathname.startsWith(path);
  };

  // Sidebar content — shared between permanent and temporary drawer
  const sidebarContent = (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        overflow: 'hidden',
      }}
    >
      {/* App Logo & Title */}
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          gap: 1.5,
          px: open ? 2.5 : 1.5,
          py: 2.5,
          minHeight: 64,
          justifyContent: open ? 'flex-start' : 'center',
        }}
      >
        <SpaIcon sx={{ color: 'primary.main', fontSize: 32 }} />
        {open && (
          <Typography
            variant="h6"
            sx={{
              fontWeight: 700,
              background: 'linear-gradient(135deg, #00BCD4, #10B981)',
              backgroundClip: 'text',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              whiteSpace: 'nowrap',
            }}
          >
            FreshTrack
          </Typography>
        )}
      </Box>

      <Divider sx={{ borderColor: 'divider' }} />

      {/* Main Navigation */}
      <List sx={{ flexGrow: 1, px: 1, py: 1.5 }}>
        {navItems.map((item) => (
          <Tooltip
            key={item.path}
            title={open ? '' : item.label}
            placement="right"
            arrow
          >
            <ListItem disablePadding sx={{ mb: 0.5 }}>
              <ListItemButton
                onClick={() => handleNav(item.path)}
                selected={isActive(item.path)}
                sx={{
                  borderRadius: 2,
                  minHeight: 44,
                  px: open ? 2 : 1.5,
                  justifyContent: open ? 'flex-start' : 'center',
                  '&.Mui-selected': {
                    bgcolor: 'rgba(0, 188, 212, 0.12)',
                    color: 'primary.main',
                    '& .MuiListItemIcon-root': { color: 'primary.main' },
                    '&:hover': { bgcolor: 'rgba(0, 188, 212, 0.18)' },
                  },
                  '&:hover': { bgcolor: 'rgba(255, 255, 255, 0.04)' },
                }}
              >
                <ListItemIcon
                  sx={{
                    minWidth: open ? 40 : 'unset',
                    color: 'text.secondary',
                    justifyContent: 'center',
                  }}
                >
                  {item.icon}
                </ListItemIcon>
                {open && <ListItemText primary={item.label} />}
              </ListItemButton>
            </ListItem>
          </Tooltip>
        ))}
      </List>

      <Divider sx={{ borderColor: 'divider' }} />

      {/* Bottom Navigation (Settings) */}
      <List sx={{ px: 1, py: 1 }}>
        {bottomNavItems.map((item) => (
          <Tooltip
            key={item.path}
            title={open ? '' : item.label}
            placement="right"
            arrow
          >
            <ListItem disablePadding>
              <ListItemButton
                onClick={() => handleNav(item.path)}
                selected={isActive(item.path)}
                sx={{
                  borderRadius: 2,
                  minHeight: 44,
                  px: open ? 2 : 1.5,
                  justifyContent: open ? 'flex-start' : 'center',
                  '&.Mui-selected': {
                    bgcolor: 'rgba(0, 188, 212, 0.12)',
                    color: 'primary.main',
                    '& .MuiListItemIcon-root': { color: 'primary.main' },
                  },
                  '&:hover': { bgcolor: 'rgba(255, 255, 255, 0.04)' },
                }}
              >
                <ListItemIcon
                  sx={{
                    minWidth: open ? 40 : 'unset',
                    color: 'text.secondary',
                    justifyContent: 'center',
                  }}
                >
                  {item.icon}
                </ListItemIcon>
                {open && <ListItemText primary={item.label} />}
              </ListItemButton>
            </ListItem>
          </Tooltip>
        ))}
      </List>
    </Box>
  );

  // Mobile: Temporary drawer (overlay)
  if (isMobile) {
    return (
      <Drawer
        variant="temporary"
        open={open}
        onClose={onClose}
        ModalProps={{ keepMounted: true }} // Better mobile performance
        sx={{
          '& .MuiDrawer-paper': {
            width: width,
            boxSizing: 'border-box',
          },
        }}
      >
        {sidebarContent}
      </Drawer>
    );
  }

  // Desktop: Permanent drawer (always visible, collapsible)
  return (
    <Drawer
      variant="permanent"
      sx={{
        '& .MuiDrawer-paper': {
          width: currentWidth,
          boxSizing: 'border-box',
          transition: 'width 0.3s ease',
          overflowX: 'hidden',
        },
      }}
    >
      {sidebarContent}
    </Drawer>
  );
}
