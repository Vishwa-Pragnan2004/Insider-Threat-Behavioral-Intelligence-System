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
import DashboardIcon from '@mui/icons-material/Dashboard';
import NotificationsActiveIcon from '@mui/icons-material/NotificationsActive';
import SearchIcon from '@mui/icons-material/ManageSearch';
import AssessmentIcon from '@mui/icons-material/Assessment';
import SettingsIcon from '@mui/icons-material/Settings';
import SecurityIcon from '@mui/icons-material/Shield';

interface SidebarProps {
  open: boolean;
  onClose: () => void;
  width: number;
  collapsedWidth: number;
  isMobile: boolean;
}

const navItems = [
  { label: 'Dashboard',       path: '/dashboard',       icon: <DashboardIcon /> },
  { label: 'Alerts',          path: '/alerts',           icon: <NotificationsActiveIcon /> },
  { label: 'Investigations',  path: '/investigations',   icon: <SearchIcon /> },
  { label: 'Reports',         path: '/reports',          icon: <AssessmentIcon /> },
];

const bottomNavItems = [
  { label: 'Settings', path: '/settings', icon: <SettingsIcon /> },
];

export default function Sidebar({ open, onClose, width, collapsedWidth, isMobile }: SidebarProps) {
  const location = useLocation();
  const navigate = useNavigate();

  const currentWidth = open ? width : collapsedWidth;

  const handleNav = (path: string) => {
    navigate(path);
    if (isMobile) onClose();
  };

  const isActive = (path: string) => location.pathname.startsWith(path);

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
        <SecurityIcon sx={{ color: 'primary.main', fontSize: 32 }} />
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
                  {item.icon}
                </ListItemIcon>
                {open && <ListItemText primary={item.label} />}
              </ListItemButton>
            </ListItem>
          </Tooltip>
        ))}
      </List>

      <Divider sx={{ borderColor: 'divider' }} />

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
                    bgcolor: 'primary.dark',
                    color: 'primary.contrastText',
                    '& .MuiListItemIcon-root': { color: 'primary.contrastText' },
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
