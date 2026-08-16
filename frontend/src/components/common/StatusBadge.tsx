import { Chip } from '@mui/material';
import type { AlertSeverity, FreshnessStatus } from '../../types/dashboard';

/**
 * StatusBadge
 *
 * A colored chip/badge that displays a status label.
 * Used throughout the app for freshness status and alert severity.
 *
 * Supports two variants:
 * - "freshness": Fresh (green), Warning (amber), Expired (red)
 * - "severity": Critical (red), High (orange), Medium (yellow), Low (blue)
 */

// Color mappings for freshness statuses
const freshnessColors: Record<FreshnessStatus, { bg: string; text: string }> = {
  fresh:   { bg: 'rgba(16, 185, 129, 0.15)', text: '#10B981' },
  warning: { bg: 'rgba(245, 158, 11, 0.15)', text: '#F59E0B' },
  expired: { bg: 'rgba(239, 68, 68, 0.15)',  text: '#EF4444' },
};

// Color mappings for alert severities
const severityColors: Record<AlertSeverity, { bg: string; text: string }> = {
  critical: { bg: 'rgba(239, 68, 68, 0.15)',  text: '#EF4444' },
  high:     { bg: 'rgba(249, 115, 22, 0.15)', text: '#F97316' },
  medium:   { bg: 'rgba(245, 158, 11, 0.15)', text: '#F59E0B' },
  low:      { bg: 'rgba(59, 130, 246, 0.15)',  text: '#3B82F6' },
};

// ─── Freshness Badge ───────────────────────────────────────────

interface FreshnessBadgeProps {
  status: FreshnessStatus;
}

export function FreshnessBadge({ status }: FreshnessBadgeProps) {
  const colors = freshnessColors[status];
  const label = status.charAt(0).toUpperCase() + status.slice(1);

  return (
    <Chip
      label={label}
      size="small"
      sx={{
        bgcolor: colors.bg,
        color: colors.text,
        fontWeight: 600,
        fontSize: '0.75rem',
        border: 'none',
      }}
    />
  );
}

// ─── Severity Badge ────────────────────────────────────────────

interface SeverityBadgeProps {
  severity: AlertSeverity;
}

export function SeverityBadge({ severity }: SeverityBadgeProps) {
  const colors = severityColors[severity];
  const label = severity.charAt(0).toUpperCase() + severity.slice(1);

  return (
    <Chip
      label={label}
      size="small"
      sx={{
        bgcolor: colors.bg,
        color: colors.text,
        fontWeight: 600,
        fontSize: '0.75rem',
        border: 'none',
      }}
    />
  );
}
