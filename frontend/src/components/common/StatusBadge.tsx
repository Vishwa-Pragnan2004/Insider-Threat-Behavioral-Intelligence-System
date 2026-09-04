import { Chip } from '@mui/material';
import type { AlertStatus } from '../../types';

/**
 * StatusBadge
 *
 * Displays an alert lifecycle status with a color-coded chip.
 * Statuses come from the backend alerts module:
 *   OPEN | ACKNOWLEDGED | IN_PROGRESS | RESOLVED | FALSE_POSITIVE
 */

const statusConfig: Record<AlertStatus, { bg: string; color: string; label: string }> = {
  OPEN:           { bg: 'rgba(59, 130, 246, 0.12)',  color: '#3b82f6', label: 'Open' },
  ACKNOWLEDGED:   { bg: 'rgba(245, 158, 11, 0.12)', color: '#f59e0b', label: 'Acknowledged' },
  IN_PROGRESS:    { bg: 'rgba(59, 130, 246, 0.12)', color: '#8b5cf6', label: 'In Progress' },
  RESOLVED:      { bg: 'rgba(16, 185, 129, 0.12)',  color: '#10b981', label: 'Resolved' },
  FALSE_POSITIVE: { bg: 'rgba(100, 116, 139, 0.12)', color: '#64748b', label: 'False Positive' },
};

interface StatusBadgeProps {
  status: AlertStatus;
}

export default function StatusBadge({ status }: StatusBadgeProps) {
  const config = statusConfig[status] ?? { bg: 'rgba(100,116,139,0.12)', color: '#64748b', label: status };

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
