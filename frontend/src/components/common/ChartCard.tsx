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
 *   <ChartCard title="Freshness Trend" subtitle="Last 30 days">
 *     <ResponsiveContainer>
 *       <LineChart data={data}>...</LineChart>
 *     </ResponsiveContainer>
 *   </ChartCard>
 */

interface ChartCardProps {
  /** Card title */
  title: string;
  /** Optional subtitle shown below the title */
  subtitle?: string;
  /** The chart component to render inside */
  children: ReactNode;
  /** Optional fixed height for the chart area (default: 300px) */
  height?: number;
  /** Whether to show the options menu icon */
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
        slotProps={{
          title: {
            variant: 'h6',
            sx: { fontSize: '1rem', fontWeight: 600 },
          },
          subheader: {
            variant: 'body2',
            sx: { color: 'text.secondary', mt: 0.3 },
          },
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
