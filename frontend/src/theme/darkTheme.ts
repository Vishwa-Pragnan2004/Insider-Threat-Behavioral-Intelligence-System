/**
 * MUI Dark Theme for ITBIS
 *
 * Cyber/SOC aesthetic matching the existing Tailwind CSS variables
 * in index.css (surface-950 background, blue accent, etc.).
 */

import { createTheme } from '@mui/material/styles';

export const darkTheme = createTheme({
  palette: {
    mode: 'dark',
    primary: {
      main: '#3b82f6',   // primary-500 — blue accent
      light: '#60a5fa',
      dark: '#1d4ed8',
    },
    secondary: {
      main: '#10b981',   // success green accent
    },
    background: {
      default: '#020617',  // surface-950
      paper: '#0f172a',  // surface-900
    },
    text: {
      primary: '#f1f5f9', // surface-100
      secondary: '#94a3b8', // surface-400
    },
    error: {
      main: '#ef4444',
    },
    warning: {
      main: '#f59e0b',
    },
    success: {
      main: '#10b981',
    },
    info: {
      main: '#3b82f6',
    },
    divider: 'rgba(59, 130, 246, 0.15)',
  },
  typography: {
    fontFamily: '"Inter", system-ui, sans-serif',
    h4: { fontWeight: 700 },
    h5: { fontWeight: 600 },
    h6: { fontWeight: 600 },
  },
  shape: {
    borderRadius: 8,
  },
  components: {
    MuiButton: {
      styleOverrides: {
        root: {
          textTransform: 'none',
          fontWeight: 600,
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          backgroundImage: 'none',
          border: '1px solid rgba(59, 130, 246, 0.15)',
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          backgroundImage: 'none',
        },
      },
    },
    MuiAppBar: {
      styleOverrides: {
        root: {
          backgroundImage: 'none',
          backgroundColor: '#0f172a',
          borderBottom: '1px solid rgba(59, 130, 246, 0.15)',
        },
      },
    },
  },
});
