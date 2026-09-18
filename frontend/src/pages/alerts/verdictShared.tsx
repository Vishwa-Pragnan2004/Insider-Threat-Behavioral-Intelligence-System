import { Chip } from '@mui/material';
import type { Verdict } from '../../types/feedback';

/** Shared presentation for analyst verdicts. */

export const VERDICT_LABELS: Record<Verdict, string> = {
  CONFIRMED_THREAT: 'Confirmed threat',
  POLICY_VIOLATION: 'Policy violation',
  BENIGN: 'Benign',
  INCONCLUSIVE: 'Inconclusive',
};

export const VERDICT_COLORS: Record<Verdict, string> = {
  CONFIRMED_THREAT: '#ef4444',
  POLICY_VIOLATION: '#f59e0b',
  BENIGN: '#3b82f6',
  INCONCLUSIVE: '#94a3b8',
};

export function VerdictChip({ verdict, size = 'small' }: { verdict: Verdict; size?: 'small' | 'medium' }) {
  const color = VERDICT_COLORS[verdict];
  return (
    <Chip
      label={VERDICT_LABELS[verdict]}
      size={size}
      sx={{
        bgcolor: `${color}1F`,
        color,
        fontWeight: 600,
        fontSize: '0.7rem',
        height: 20,
      }}
    />
  );
}
