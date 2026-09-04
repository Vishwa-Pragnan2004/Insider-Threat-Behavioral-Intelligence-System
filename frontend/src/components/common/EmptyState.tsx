import { Box, Typography } from '@mui/material';

/**
 * EmptyState
 *
 * Centered empty-state message with an icon and description.
 * Used when a page or list has no data to display.
 */

interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
}

export default function EmptyState({ icon, title, description, action }: EmptyStateProps) {
  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 2,
        py: 8,
        px: 4,
        textAlign: 'center',
      }}
    >
      {icon && (
        <Box sx={{ color: 'text.disabled', opacity: 0.5 }}>
          {icon}
        </Box>
      )}
      <Typography variant="h6" sx={{ color: 'text.secondary', fontWeight: 600 }}>
        {title}
      </Typography>
      {description && (
        <Typography variant="body2" sx={{ color: 'text.disabled', maxWidth: 400 }}>
          {description}
        </Typography>
      )}
      {action && <Box sx={{ mt: 1 }}>{action}</Box>}
    </Box>
  );
}
