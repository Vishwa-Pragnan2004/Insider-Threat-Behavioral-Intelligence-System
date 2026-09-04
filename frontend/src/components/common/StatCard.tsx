import { Card, CardContent, Box, Typography } from '@mui/material';
import TrendingUpIcon from '@mui/icons-material/TrendingUp';
import TrendingDownIcon from '@mui/icons-material/TrendingDown';
import type { ReactNode } from 'react';

/**
 * StatCard
 *
 * A KPI metric card showing a single key statistic with:
 * - An icon
 * - A label
 * - A large value
 * - A trend indicator (e.g. "+5.2%" with up/down arrow)
 */

interface StatCardProps {
  label: string;
  value: string;
  trend: number;
  trendUpIsGood?: boolean;
  icon: ReactNode;
  iconColor?: string;
}

export default function StatCard({
  label,
  value,
  trend,
  trendUpIsGood = true,
  icon,
  iconColor = 'rgba(59, 130, 246, 0.12)',
}: StatCardProps) {
  const isPositive = trend >= 0;
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
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 2 }}>
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: 48,
              height: 48,
              borderRadius: 2,
              bgcolor: iconColor,
              color: iconColor.replace('0.12', '1'),
            }}
          >
            {icon}
          </Box>

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

        <Typography variant="h4" sx={{ fontWeight: 700, mb: 0.5, color: 'text.primary' }}>
          {value}
        </Typography>

        <Typography variant="body2" sx={{ color: 'text.secondary' }}>
          {label}
        </Typography>
      </CardContent>
    </Card>
  );
}
