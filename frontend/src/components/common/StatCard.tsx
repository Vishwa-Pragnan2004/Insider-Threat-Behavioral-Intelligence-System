import { Card, CardContent, Box, Typography } from '@mui/material';
import TrendingUpIcon from '@mui/icons-material/TrendingUp';
import TrendingDownIcon from '@mui/icons-material/TrendingDown';
import type { ReactNode } from 'react';

/**
 * StatCard
 *
 * A KPI metric card showing a single key statistic with:
 * - An icon
 * - A label (e.g. "Total Products")
 * - A large value (e.g. "1,247")
 * - A trend indicator (e.g. "+5.2%" with up/down arrow)
 *
 * Used on the Dashboard page for the top row of summary cards.
 */

interface StatCardProps {
  /** The name of the metric */
  label: string;
  /** The main value to display (pre-formatted string) */
  value: string;
  /** Percentage change from previous period */
  trend: number;
  /** Whether a positive trend is good (true) or bad (false) */
  trendUpIsGood?: boolean;
  /** Icon displayed in the top-left corner */
  icon: ReactNode;
  /** Background color for the icon container */
  iconColor?: string;
}

export default function StatCard({
  label,
  value,
  trend,
  trendUpIsGood = true,
  icon,
  iconColor = 'rgba(0, 188, 212, 0.15)',
}: StatCardProps) {
  // Determine if the trend is positive or negative
  const isPositive = trend >= 0;

  // Determine if the trend represents a good or bad outcome
  const isGood = trendUpIsGood ? isPositive : !isPositive;

  return (
    <Card
      sx={{
        height: '100%',
        transition: 'transform 0.2s ease, box-shadow 0.2s ease',
        '&:hover': {
          transform: 'translateY(-2px)',
          boxShadow: '0 4px 20px rgba(0, 0, 0, 0.3)',
        },
      }}
    >
      <CardContent sx={{ p: 3, '&:last-child': { pb: 3 } }}>
        {/* Top row: Icon + Trend */}
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 2 }}>
          {/* Icon */}
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: 48,
              height: 48,
              borderRadius: 2,
              bgcolor: iconColor,
              color: iconColor.replace('0.15', '1'), // Full opacity for the icon
            }}
          >
            {icon}
          </Box>

          {/* Trend Badge */}
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              gap: 0.3,
              px: 1,
              py: 0.3,
              borderRadius: 1,
              bgcolor: isGood ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)',
              color: isGood ? 'success.main' : 'error.main',
              fontSize: '0.8rem',
              fontWeight: 600,
            }}
          >
            {isPositive ? (
              <TrendingUpIcon sx={{ fontSize: 16 }} />
            ) : (
              <TrendingDownIcon sx={{ fontSize: 16 }} />
            )}
            {Math.abs(trend).toFixed(1)}%
          </Box>
        </Box>

        {/* Value */}
        <Typography variant="h4" sx={{ fontWeight: 700, mb: 0.5, color: 'text.primary' }}>
          {value}
        </Typography>

        {/* Label */}
        <Typography variant="body2" sx={{ color: 'text.secondary' }}>
          {label}
        </Typography>
      </CardContent>
    </Card>
  );
}
