import {
  AppBar,
  Toolbar,
  IconButton,
  Typography,
  Box,
  Avatar,
  Badge,
  Tooltip,
  Menu,
  MenuItem,
  Divider,
} from '@mui/material';
import MenuIcon from '@mui/icons-material/Menu';
import NotificationsIcon from '@mui/icons-material/Notifications';
import LogoutIcon from '@mui/icons-material/Logout';
import PersonIcon from '@mui/icons-material/Person';
import { useState } from 'react';
import { useAuth } from '../../hooks/useAuth';
import { useNavigate } from 'react-router-dom';

/**
 * Topbar Navigation
 *
 * Top navigation bar with:
 * - Hamburger menu to toggle sidebar
 * - Page context (could show breadcrumbs in the future)
 * - Notification bell with badge
 * - User avatar with dropdown menu (profile, logout)
 */

interface TopbarProps {
  onMenuClick: () => void;
}

export default function Topbar({ onMenuClick }: TopbarProps) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  // User menu anchor
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);
  const menuOpen = Boolean(anchorEl);

  const handleMenuOpen = (event: React.MouseEvent<HTMLElement>) => {
    setAnchorEl(event.currentTarget);
  };

  const handleMenuClose = () => {
    setAnchorEl(null);
  };

  const handleLogout = async () => {
    handleMenuClose();
    await logout();
    navigate('/login');
  };

  // Get user initials for the avatar
  const initials = user
    ? `${user.first_name[0]}${user.last_name[0]}`
    : '?';

  return (
    <AppBar position="sticky" elevation={0}>
      <Toolbar sx={{ gap: 1 }}>
        {/* Sidebar Toggle */}
        <IconButton
          color="inherit"
          aria-label="toggle sidebar"
          onClick={onMenuClick}
          edge="start"
        >
          <MenuIcon />
        </IconButton>

        {/* Spacer — pushes right-side items to the end */}
        <Box sx={{ flexGrow: 1 }} />

        {/* Notification Bell */}
        <Tooltip title="Notifications">
          <IconButton color="inherit" aria-label="notifications">
            <Badge badgeContent={3} color="error">
              <NotificationsIcon />
            </Badge>
          </IconButton>
        </Tooltip>

        {/* User Avatar & Menu */}
        <Tooltip title="Account">
          <IconButton onClick={handleMenuOpen} sx={{ ml: 1 }}>
            <Avatar
              sx={{
                width: 36,
                height: 36,
                bgcolor: 'primary.main',
                fontSize: '0.875rem',
                fontWeight: 700,
              }}
            >
              {initials}
            </Avatar>
          </IconButton>
        </Tooltip>

        {/* Dropdown Menu */}
        <Menu
          anchorEl={anchorEl}
          open={menuOpen}
          onClose={handleMenuClose}
          transformOrigin={{ horizontal: 'right', vertical: 'top' }}
          anchorOrigin={{ horizontal: 'right', vertical: 'bottom' }}
          slotProps={{
            paper: {
              sx: {
                mt: 1,
                minWidth: 200,
                bgcolor: 'background.paper',
                border: '1px solid',
                borderColor: 'divider',
              },
            },
          }}
        >
          {/* User Info */}
          <Box sx={{ px: 2, py: 1.5 }}>
            <Typography variant="subtitle1" sx={{ fontWeight: 600, color: 'text.primary' }}>
              {user ? `${user.first_name} ${user.last_name}` : 'User'}
            </Typography>
            <Typography variant="body2" sx={{ color: 'text.secondary', fontSize: '0.8rem' }}>
              {user?.email}
            </Typography>
          </Box>

          <Divider />

          <MenuItem onClick={handleMenuClose}>
            <PersonIcon sx={{ mr: 1.5, fontSize: 20, color: 'text.secondary' }} />
            Profile
          </MenuItem>

          <Divider />

          <MenuItem onClick={handleLogout} sx={{ color: 'error.main' }}>
            <LogoutIcon sx={{ mr: 1.5, fontSize: 20 }} />
            Sign Out
          </MenuItem>
        </Menu>
      </Toolbar>
    </AppBar>
  );
}
