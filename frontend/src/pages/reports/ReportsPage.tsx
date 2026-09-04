import { Box, Typography } from '@mui/material';
import PageHeader from '../../components/common/PageHeader';

export default function ReportsPage() {
  return (
    <Box>
      <PageHeader title="Reports" subtitle="Generate and export security reports" />
      <Box sx={{ py: 4, textAlign: 'center' }}>
        <Typography variant="h6" color="text.secondary">
          Reports — coming soon
        </Typography>
        <Typography variant="body2" color="text.disabled" sx={{ mt: 1 }}>
          Scheduled and on-demand reports for alerts, investigations, and risk trends will appear here.
        </Typography>
      </Box>
    </Box>
  );
}
