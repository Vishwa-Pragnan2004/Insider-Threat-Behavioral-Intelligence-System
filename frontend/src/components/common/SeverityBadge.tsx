import { Chip } from '@mui/material';
import type { AlertSeverity } from '../../types';

/**
 * SeverityBadge
 *
 * Displays an alert severity level with a color-coded chip.
 * Severities come from the backend alerts module:
 *   LOW | MEDIUM | HIGH | CRITICAL
 */

const severityConfig: Record<AlertSeverity, { bg: string; color: string; label: string }> = {
  LOW:      { bg: 'rgba(59, 130, 246, 0.12)',  color: '#3b82f6', label: 'Low' },
  MEDIUM:   { bg: 'rgba(245, 158, 11, 0.12)', color: '#f59e0b', label: 'Medium' },
  HIGH:     { bg: 'rgba(249, 115, 22, 0.12)', color: '#f97316', label: 'High' },
  CRITICAL: { bg: 'rgba(239, 68, 68, 0.12)',  color: '#ef4444', label: 'Critical' },
};

interface SeverityBadgeProps {
  severity: AlertSeverity;
}

export default function SeverityBadge({ severity }: SeverityBadgeProps) {
  const config = severityConfig[severity] ?? severityConfig.MEDIUM;

  return (
    <Chip
      label={config.label}
      size="small"
      sx={{
        bgcolor: config.bg,
        color: config.color,
        fontWeight: 600,
        fontSize: '0.75rem',
        border: 'none',
      }}
    />
  );
}
