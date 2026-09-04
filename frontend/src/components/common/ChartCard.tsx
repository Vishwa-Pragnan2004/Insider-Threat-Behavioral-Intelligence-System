import { Card, CardContent, CardHeader, Box, IconButton, Tooltip } from '@mui/material';
import MoreVertIcon from '@mui/icons-material/MoreVert';
import type { ReactNode } from 'react';

/**
 * ChartCard
 *
 * A card wrapper for Recharts components. Provides a consistent
 * container with a title, optional subtitle, and optional action menu.
 *
 * Usage:
 *   <ChartCard title="Risk Score Trend" subtitle="Last 30 days">
 *     <ResponsiveContainer>
 *       <LineChart data={data}>...</LineChart>
 *     </ResponsiveContainer>
 *   </ChartCard>
 */

interface ChartCardProps {
  title: string;
  subtitle?: string;
  children: ReactNode;
  height?: number;
  showMenu?: boolean;
}

export default function ChartCard({
  title,
  subtitle,
  children,
  height = 300,
  showMenu = false,
}: ChartCardProps) {
  return (
    <Card sx={{ height: '100%' }}>
      <CardHeader
        title={title}
        subheader={subtitle}
        titleTypographyProps={{
          variant: 'h6',
          sx: { fontSize: '1rem', fontWeight: 600 },
        }}
        subheaderTypographyProps={{
          variant: 'body2',
          sx: { color: 'text.secondary', mt: 0.3 },
        }}
        action={
          showMenu ? (
            <Tooltip title="Options">
              <IconButton size="small" sx={{ color: 'text.secondary' }}>
                <MoreVertIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          ) : null
        }
        sx={{ pb: 0 }}
      />
      <CardContent sx={{ pt: 1 }}>
        <Box sx={{ width: '100%', height }}>
          {children}
        </Box>
      </CardContent>
    </Card>
  );
}
