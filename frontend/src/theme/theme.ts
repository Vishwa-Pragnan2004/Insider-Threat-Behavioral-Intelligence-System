import { createTheme } from '@mui/material/styles';

/**
 * MUI Dark Theme Configuration
 * 
 * Enterprise dashboard theme inspired by Grafana and Azure Portal.
 * Uses a teal/cyan primary color for a "fresh" food-related aesthetic,
 * with amber for warnings and a dark background palette.
 */
const theme = createTheme({
  palette: {
    mode: 'dark',

    // Primary: Teal/Cyan — clean, fresh, professional
    primary: {
      main: '#00BCD4',
      light: '#4DD0E1',
      dark: '#00838F',
      contrastText: '#FFFFFF',
    },

    // Secondary: Amber — attention, warnings
    secondary: {
      main: '#FFC107',
      light: '#FFD54F',
      dark: '#FFA000',
      contrastText: '#000000',
    },

    // Background colors for the dashboard
    background: {
      default: '#0A0E17',    // Darkest — page background
      paper: '#111827',      // Card/surface background
    },

    // Severity colors used throughout the app
    error: {
      main: '#EF4444',       // Critical alerts
      light: '#F87171',
      dark: '#DC2626',
    },
    warning: {
      main: '#F59E0B',       // High/Warning alerts
      light: '#FBBF24',
      dark: '#D97706',
    },
    success: {
      main: '#10B981',       // Fresh status, success states
      light: '#34D399',
      dark: '#059669',
    },
    info: {
      main: '#3B82F6',       // Low alerts, informational
      light: '#60A5FA',
      dark: '#2563EB',
    },

    // Text colors
    text: {
      primary: '#F1F5F9',
      secondary: '#94A3B8',
      disabled: '#475569',
    },

    // Divider color
    divider: '#1E293B',
  },

  // Typography — clean, readable hierarchy
  typography: {
    fontFamily: '"Roboto", "Helvetica", "Arial", sans-serif',
    h4: {
      fontWeight: 700,
      fontSize: '1.75rem',
    },
    h5: {
      fontWeight: 600,
      fontSize: '1.25rem',
    },
    h6: {
      fontWeight: 600,
      fontSize: '1rem',
    },
    subtitle1: {
      fontWeight: 500,
      color: '#94A3B8',
    },
    subtitle2: {
      fontWeight: 400,
      fontSize: '0.8rem',
      color: '#94A3B8',
    },
    body2: {
      color: '#CBD5E1',
    },
  },

  // Shape — slightly rounded corners for a modern look
  shape: {
    borderRadius: 12,
  },

  // Component overrides for consistent styling
  components: {
    // Cards: subtle border, no heavy shadow
    MuiCard: {
      styleOverrides: {
        root: {
          backgroundImage: 'none',
          backgroundColor: '#111827',
          border: '1px solid #1E293B',
          borderRadius: 12,
        },
      },
    },

    // Paper: match card style
    MuiPaper: {
      styleOverrides: {
        root: {
          backgroundImage: 'none',
        },
      },
    },

    // Buttons: slightly rounded
    MuiButton: {
      styleOverrides: {
        root: {
          textTransform: 'none',  // Don't uppercase button text
          fontWeight: 600,
          borderRadius: 8,
        },
      },
    },

    // Text fields: outlined variant styling
    MuiTextField: {
      defaultProps: {
        variant: 'outlined',
        size: 'medium',
      },
    },

    // Table: cleaner borders
    MuiTableCell: {
      styleOverrides: {
        root: {
          borderBottom: '1px solid #1E293B',
        },
        head: {
          fontWeight: 600,
          color: '#94A3B8',
          backgroundColor: '#0F172A',
        },
      },
    },

    // Drawer: sidebar background
    MuiDrawer: {
      styleOverrides: {
        paper: {
          backgroundColor: '#0F172A',
          borderRight: '1px solid #1E293B',
        },
      },
    },

    // AppBar: transparent background, border instead
    MuiAppBar: {
      styleOverrides: {
        root: {
          backgroundColor: '#0F172A',
          borderBottom: '1px solid #1E293B',
          boxShadow: 'none',
        },
      },
    },

    // Chip: for status badges
    MuiChip: {
      styleOverrides: {
        root: {
          fontWeight: 600,
          fontSize: '0.75rem',
        },
      },
    },
  },
});

export default theme;
