import { Box, Typography } from '@mui/material';
import type { ReactNode } from 'react';

/**
 * PageHeader
 *
 * Consistent page title with optional subtitle and action buttons.
 * Used at the top of every page for a unified look.
 *
 * Usage:
 *   <PageHeader
 *     title="Dashboard"
 *     subtitle="Real-time food freshness overview"
 *     actions={<Button>Export</Button>}
 *   />
 */

interface PageHeaderProps {
  /** Main page title */
  title: string;
  /** Optional description below the title */
  subtitle?: string;
  /** Optional action buttons on the right side */
  actions?: ReactNode;
}

export default function PageHeader({ title, subtitle, actions }: PageHeaderProps) {
  return (
    <Box
      sx={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: { xs: 'flex-start', sm: 'center' },
        flexDirection: { xs: 'column', sm: 'row' },
        gap: 1,
        mb: 3,
      }}
    >
      <Box>
        <Typography variant="h4" sx={{ fontWeight: 700, color: 'text.primary' }}>
          {title}
        </Typography>
        {subtitle && (
          <Typography variant="body2" sx={{ color: 'text.secondary', mt: 0.5 }}>
            {subtitle}
          </Typography>
        )}
      </Box>

      {actions && <Box sx={{ display: 'flex', gap: 1 }}>{actions}</Box>}
    </Box>
  );
}
