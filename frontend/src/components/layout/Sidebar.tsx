import { useLocation, useNavigate } from 'react-router-dom';
import {
  Box,
  Drawer,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  ListSubheader,
  Typography,
  Divider,
  Tooltip,
} from '@mui/material';
import {
  Dashboard,
  NotificationsActive,
  ManageSearch,
  Assessment,
  Settings,
  Shield,
  People,
  Timeline,
  TravelExplore,
  MonitorHeart,
  Insights,
  GppMaybe,
  Radar,
  Badge as BadgeIcon,
} from '@mui/icons-material';
import type { ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Badge } from '@mui/material';
import { listAccessRequests } from '../../api/userService';
import { useAuth } from '../../hooks/useAuth';
import { hasPermission } from '../../utils/permissions';

interface SidebarProps {
  open: boolean;
  onClose: () => void;
  width: number;
  collapsedWidth: number;
  isMobile: boolean;
}

interface NavItem {
  label: string;
  path: string;
  icon: ReactNode;
  /** Hide the item unless the user holds this permission. */
  permission?: string;
}

const navItems: NavItem[] = [
  { label: 'Dashboard',       path: '/dashboard',       icon: <Dashboard /> },
  { label: 'Alerts',          path: '/alerts',           icon: <NotificationsActive /> },
  { label: 'Insider risk',    path: '/risk',             icon: <GppMaybe />, permission: 'anomaly:read' },
  { label: 'Detections',      path: '/detections',       icon: <Radar />, permission: 'anomaly:read' },
  { label: 'Activity',        path: '/activity',         icon: <Timeline />, permission: 'behavioral:read' },
  { label: 'Investigations',  path: '/investigations',   icon: <ManageSearch /> },
  { label: 'Reports',         path: '/reports',          icon: <Assessment /> },
  { label: 'Users',           path: '/users',            icon: <People />, permission: 'users:read' },
  { label: 'Employees',       path: '/employees',        icon: <BadgeIcon />, permission: 'employees:read' },
];

/** Role dashboards — the group is hidden entirely when none are permitted. */
const dashboardItems: NavItem[] = [
  { label: 'Analyst workspace', path: '/dashboards/analyst', icon: <TravelExplore />, permission: 'dashboard:analyst' },
  { label: 'SOC operations',    path: '/dashboards/soc',     icon: <MonitorHeart />,  permission: 'dashboard:soc' },
  { label: 'Risk posture',      path: '/dashboards/manager', icon: <Insights />,      permission: 'dashboard:manager' },
];

const bottomNavItems: NavItem[] = [
  { label: 'Settings', path: '/settings', icon: <Settings /> },
];

export default function Sidebar({ open, onClose, width, collapsedWidth, isMobile }: SidebarProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const { user } = useAuth();
  const isVisible = (item: NavItem) => !item.permission || hasPermission(user, item.permission);
  const visibleNavItems = navItems.filter(isVisible);
  const visibleDashboardItems = dashboardItems.filter(isVisible);

  // Pending access requests badge on "Users" (same query key as the Users page section).
  const canReadUsers = hasPermission(user, 'users:read');
  const pendingQuery = useQuery({
    queryKey: ['access-requests', 'PENDING'],
    queryFn: () => listAccessRequests('PENDING'),
    enabled: canReadUsers,
    refetchInterval: 60_000,
  });
  const pendingCount = canReadUsers ? pendingQuery.data?.pending ?? 0 : 0;
  const badgeFor = (item: NavItem) => (item.path === '/users' ? pendingCount : 0);

  const currentWidth = open ? width : collapsedWidth;

  const handleNav = (path: string) => {
    navigate(path);
    if (isMobile) onClose();
  };

  // Exact segment match, so "/dashboard" isn't highlighted on "/dashboards/soc".
  const isActive = (path: string) =>
    location.pathname === path || location.pathname.startsWith(`${path}/`);

  const renderItem = (item: NavItem) => (
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
              bgcolor: 'primary.dark',
              color: 'primary.contrastText',
              '& .MuiListItemIcon-root': { color: 'primary.contrastText' },
              '&:hover': { bgcolor: 'primary.main' },
            },
            '&:hover': { bgcolor: 'action.hover' },
          }}
        >
          <ListItemIcon
            sx={{
              minWidth: open ? 40 : 'unset',
              color: 'text.secondary',
              justifyContent: 'center',
            }}
          >
            <Badge badgeContent={badgeFor(item)} color="warning" max={99}>
              {item.icon}
            </Badge>
          </ListItemIcon>
          {open && <ListItemText primary={item.label} />}
        </ListItemButton>
      </ListItem>
    </Tooltip>
  );

  const sidebarContent = (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        overflow: 'hidden',
      }}
    >
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
        <Shield sx={{ color: 'primary.main', fontSize: 32 }} />
        {open && (
          <Typography
            variant="h6"
            sx={{
              fontWeight: 700,
              fontSize: '1.1rem',
              color: 'primary.main',
              whiteSpace: 'nowrap',
            }}
          >
            ITBIS SOC
          </Typography>
        )}
      </Box>

      <Divider sx={{ borderColor: 'divider' }} />

      <Box sx={{ flexGrow: 1, overflowY: 'auto', overflowX: 'hidden' }}>
        <List sx={{ px: 1, py: 1.5 }}>
          {visibleNavItems.map(renderItem)}
        </List>

        {visibleDashboardItems.length > 0 && (
          <List
            sx={{ px: 1, pt: 0 }}
            subheader={
              open ? (
                <ListSubheader
                  disableSticky
                  sx={{
                    bgcolor: 'transparent',
                    lineHeight: '32px',
                    fontSize: '0.7rem',
                    fontWeight: 700,
                    letterSpacing: '0.08em',
                    textTransform: 'uppercase',
                    color: 'text.disabled',
                  }}
                >
                  Dashboards
                </ListSubheader>
              ) : (
                <Divider sx={{ borderColor: 'divider', mx: 1, mb: 1 }} />
              )
            }
          >
            {visibleDashboardItems.map(renderItem)}
          </List>
        )}
      </Box>

      <Divider sx={{ borderColor: 'divider' }} />

      <List sx={{ px: 1, py: 1 }}>
        {bottomNavItems.map(renderItem)}
      </List>
    </Box>
  );

  if (isMobile) {
    return (
      <Drawer
        variant="temporary"
        open={open}
        onClose={onClose}
        ModalProps={{ keepMounted: true }}
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
