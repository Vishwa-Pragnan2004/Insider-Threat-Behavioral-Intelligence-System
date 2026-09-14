import type { ReactNode } from 'react';
import { Alert, AlertTitle, Box } from '@mui/material';
import { useAuth } from '../../hooks/useAuth';
import { hasPermission } from '../../utils/permissions';

/**
 * RequirePermission
 *
 * Route guard for pages that need a specific permission. Renders an
 * explanation in place instead of redirecting, so there's no chance of a
 * redirect loop and the user knows what to ask an administrator for.
 */

interface RequirePermissionProps {
  permission: string;
  children: ReactNode;
}

export default function RequirePermission({ permission, children }: RequirePermissionProps) {
  const { user } = useAuth();

  if (!hasPermission(user, permission)) {
    return (
      <Box sx={{ maxWidth: 640, mx: 'auto', mt: 6 }}>
        <Alert severity="warning" variant="outlined">
          <AlertTitle>You don't have access to this page</AlertTitle>
          Ask an administrator for the <code>{permission}</code> permission.
        </Alert>
      </Box>
    );
  }

  return <>{children}</>;
}
