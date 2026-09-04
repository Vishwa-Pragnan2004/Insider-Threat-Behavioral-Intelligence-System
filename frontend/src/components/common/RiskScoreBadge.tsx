import { Box, Typography } from '@mui/material';
import type { RiskLevel } from '../../types';

/**
 * RiskScoreBadge
 *
 * Displays a numeric risk score (0–100) with a color-coded risk level indicator.
 * The numeric score and the derived risk level are both shown.
 *
 * Risk level thresholds (from anomaly domain):
 *   LOW:      0-39
 *   MEDIUM:  40-59
 *   HIGH:    60-79
 *   CRITICAL: 80-100
 */

const riskConfig: Record<RiskLevel, { bg: string; color: string; label: string }> = {
  LOW:      { bg: 'rgba(59, 130, 246, 0.12)',  color: '#3b82f6', label: 'Low' },
  MEDIUM:   { bg: 'rgba(245, 158, 11, 0.12)', color: '#f59e0b', label: 'Medium' },
  HIGH:     { bg: 'rgba(249, 115, 22, 0.12)', color: '#f97316', label: 'High' },
  CRITICAL: { bg: 'rgba(239, 68, 68, 0.12)',  color: '#ef4444', label: 'Critical' },
};

function scoreToLevel(score: number): RiskLevel {
  if (score >= 80) return 'CRITICAL';
  if (score >= 60) return 'HIGH';
  if (score >= 40) return 'MEDIUM';
  return 'LOW';
}

interface RiskScoreBadgeProps {
  score: number;
  showLabel?: boolean;
}

export default function RiskScoreBadge({ score, showLabel = true }: RiskScoreBadgeProps) {
  const level = scoreToLevel(score);
  const config = riskConfig[level];

  return (
    <Box
      sx={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 1,
        px: 1.5,
        py: 0.5,
        borderRadius: 1,
        bgcolor: config.bg,
        border: `1px solid ${config.color}30`,
      }}
    >
      <Typography
        sx={{
          fontWeight: 700,
          fontSize: '0.9rem',
          color: config.color,
          fontFamily: '"JetBrains Mono", monospace',
          lineHeight: 1,
        }}
      >
        {score}
      </Typography>

      {showLabel && (
        <Typography
          sx={{
            fontWeight: 600,
            fontSize: '0.7rem',
            color: config.color,
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
          }}
        >
          {config.label}
        </Typography>
      )}
    </Box>
  );
}
