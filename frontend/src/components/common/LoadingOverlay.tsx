import { Box, CircularProgress, Typography } from '@mui/material';

/**
 * LoadingOverlay
 *
 * A centered loading spinner with optional message.
 * Can fill its parent container or the full page.
 *
 * Usage:
 *   {isLoading && <LoadingOverlay message="Loading dashboard..." />}
 */

interface LoadingOverlayProps {
  /** Optional message below the spinner */
  message?: string;
  /** Whether to fill the full viewport height (default: true) */
  fullPage?: boolean;
}

export default function LoadingOverlay({
  message = 'Loading...',
  fullPage = true,
}: LoadingOverlayProps) {
  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 2,
        minHeight: fullPage ? '60vh' : 200,
        width: '100%',
      }}
    >
      <CircularProgress size={48} thickness={3} color="primary" />
      {message && (
        <Typography variant="body2" sx={{ color: 'text.secondary' }}>
          {message}
        </Typography>
      )}
    </Box>
  );
}
