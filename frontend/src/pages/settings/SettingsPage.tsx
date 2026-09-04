import { Box, Typography } from '@mui/material';
import PageHeader from '../../components/common/PageHeader';

export default function SettingsPage() {
  return (
    <Box>
      <PageHeader title="Settings" subtitle="Application and user preferences" />
      <Box sx={{ py: 4, textAlign: 'center' }}>
        <Typography variant="h6" color="text.secondary">
          Settings — coming soon
        </Typography>
        <Typography variant="body2" color="text.disabled" sx={{ mt: 1 }}>
          User profile, notification preferences, and system configuration will appear here.
        </Typography>
      </Box>
    </Box>
  );
}
