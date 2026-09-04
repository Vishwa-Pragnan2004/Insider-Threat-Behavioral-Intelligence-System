import { useState } from 'react';
import {
  Box,
  Typography,
  Card,
  CardContent,
  Grid,
  Button,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  CircularProgress,
  Alert,
} from '@mui/material';
import { Download } from '@mui/icons-material';
import PageHeader from '../../components/common/PageHeader';
import { exportAlertsCsv, exportInvestigationsCsv } from '../../api/reportService';

const SEVERITY_OPTIONS = [
  { value: '', label: 'All Severities' },
  { value: 'LOW', label: 'Low' },
  { value: 'MEDIUM', label: 'Medium' },
  { value: 'HIGH', label: 'High' },
  { value: 'CRITICAL', label: 'Critical' },
];

const STATUS_OPTIONS = [
  { value: '', label: 'All Statuses' },
  { value: 'OPEN', label: 'Open' },
  { value: 'ACKNOWLEDGED', label: 'Acknowledged' },
  { value: 'IN_PROGRESS', label: 'In Progress' },
  { value: 'RESOLVED', label: 'Resolved' },
  { value: 'FALSE_POSITIVE', label: 'False Positive' },
];

const INVESTIGATION_STATUS_OPTIONS = [
  { value: '', label: 'All Statuses' },
  { value: 'OPEN', label: 'Open' },
  { value: 'IN_PROGRESS', label: 'In Progress' },
  { value: 'CLOSED', label: 'Closed' },
  { value: 'CANCELLED', label: 'Cancelled' },
];

function downloadBlob(blob: Blob, filename: string) {
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  window.URL.revokeObjectURL(url);
}

export default function ReportsPage() {
  const [alertSeverity, setAlertSeverity] = useState('');
  const [alertStatus, setAlertStatus] = useState('');
  const [invStatus, setInvStatus] = useState('');
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleExportAlerts() {
    setLoading('alerts');
    setError(null);
    try {
      const blob = await exportAlertsCsv({
        severity: alertSeverity || undefined,
        status: alertStatus || undefined,
      });
      downloadBlob(blob, `alerts_report_${new Date().toISOString().split('T')[0]}.csv`);
    } catch (e) {
      setError('Failed to export alerts report');
    } finally {
      setLoading(null);
    }
  }

  async function handleExportInvestigations() {
    setLoading('investigations');
    setError(null);
    try {
      const blob = await exportInvestigationsCsv({
        status: invStatus || undefined,
      });
      downloadBlob(blob, `investigations_report_${new Date().toISOString().split('T')[0]}.csv`);
    } catch (e) {
      setError('Failed to export investigations report');
    } finally {
      setLoading(null);
    }
  }

  return (
    <Box>
      <PageHeader title="Reports" subtitle="Generate and export security reports" />

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      <Grid container spacing={2}>
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Alert Report
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                Export all alerts with optional filtering by severity and status.
              </Typography>
              <Box sx={{ display: 'flex', gap: 2, mb: 2 }}>
                <FormControl size="small" sx={{ minWidth: 150 }}>
                  <InputLabel>Severity</InputLabel>
                  <Select
                    value={alertSeverity}
                    label="Severity"
                    onChange={(e) => setAlertSeverity(e.target.value)}
                  >
                    {SEVERITY_OPTIONS.map((o) => (
                      <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>
                    ))}
                  </Select>
                </FormControl>
                <FormControl size="small" sx={{ minWidth: 150 }}>
                  <InputLabel>Status</InputLabel>
                  <Select
                    value={alertStatus}
                    label="Status"
                    onChange={(e) => setAlertStatus(e.target.value)}
                  >
                    {STATUS_OPTIONS.map((o) => (
                      <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </Box>
              <Button
                variant="contained"
                startIcon={loading === 'alerts' ? <CircularProgress size={18} /> : <Download />}
                onClick={handleExportAlerts}
                disabled={loading === 'alerts'}
              >
                {loading === 'alerts' ? 'Exporting...' : 'Export Alerts CSV'}
              </Button>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Investigation Report
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                Export all investigations with optional filtering by status.
              </Typography>
              <Box sx={{ display: 'flex', gap: 2, mb: 2 }}>
                <FormControl size="small" sx={{ minWidth: 150 }}>
                  <InputLabel>Status</InputLabel>
                  <Select
                    value={invStatus}
                    label="Status"
                    onChange={(e) => setInvStatus(e.target.value)}
                  >
                    {INVESTIGATION_STATUS_OPTIONS.map((o) => (
                      <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </Box>
              <Button
                variant="contained"
                startIcon={loading === 'investigations' ? <CircularProgress size={18} /> : <Download />}
                onClick={handleExportInvestigations}
                disabled={loading === 'investigations'}
              >
                {loading === 'investigations' ? 'Exporting...' : 'Export Investigations CSV'}
              </Button>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
}
