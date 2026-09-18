import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Alert as MuiAlert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { apiErrorMessage } from '../../api/userService';
import { recordVerdict } from '../../api/feedbackService';
import type { Alert } from '../../types/alert';
import type { Verdict } from '../../types/feedback';

/**
 * VerdictDialog
 *
 * Where an analyst says what an alert turned out to be. This is the only
 * place a training label is created, which is why it asks for an
 * explanation every time: a label nobody can account for later is worse
 * than no label, because it looks like evidence.
 */

interface VerdictOption {
  value: Verdict;
  label: string;
  helper: string;
  closes: string;
  color: string;
}

const OPTIONS: VerdictOption[] = [
  {
    value: 'CONFIRMED_THREAT',
    label: 'Confirmed threat',
    helper: 'The behaviour was what the alert said it was.',
    closes: 'Closes the alert as resolved.',
    color: '#ef4444',
  },
  {
    value: 'POLICY_VIOLATION',
    label: 'Policy violation',
    helper: 'Real misconduct, but not an insider threat.',
    closes: 'Closes the alert as resolved. Not used for training.',
    color: '#f59e0b',
  },
  {
    value: 'BENIGN',
    label: 'Benign',
    helper: 'Ordinary work the system misread.',
    closes: 'Closes the alert as a false positive.',
    color: '#3b82f6',
  },
  {
    value: 'INCONCLUSIVE',
    label: 'Inconclusive',
    helper: 'Investigated and still unclear.',
    closes: 'Leaves the alert where it is. Not used for training.',
    color: '#94a3b8',
  },
];

interface VerdictDialogProps {
  alert: Alert;
  open: boolean;
  /** Set when the analyst is changing a call they (or a colleague) made before. */
  revising?: boolean;
  onClose: () => void;
  onRecorded: (updated: Alert, verdict: Verdict) => void;
}

export default function VerdictDialog({
  alert,
  open,
  revising = false,
  onClose,
  onRecorded,
}: VerdictDialogProps) {
  const queryClient = useQueryClient();
  const [choice, setChoice] = useState<Verdict | null>(null);
  const [rationale, setRationale] = useState('');

  const selected = OPTIONS.find(o => o.value === choice);

  const mutation = useMutation({
    mutationFn: () => recordVerdict(alert.id, { verdict: choice!, rationale }),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['alerts'] });
      queryClient.invalidateQueries({ queryKey: ['verdicts'] });
      queryClient.invalidateQueries({ queryKey: ['verdict-stats'] });
      onRecorded(result.alert, result.verdict.verdict);
      reset();
    },
  });

  const reset = () => {
    setChoice(null);
    setRationale('');
    mutation.reset();
  };

  const handleClose = () => {
    reset();
    onClose();
  };

  const canSubmit = choice !== null && rationale.trim().length >= 3 && !mutation.isPending;

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ pb: 0.5 }}>
        {revising ? 'Change the verdict' : 'What did this turn out to be?'}
      </DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          {alert.user_id} · {new Date(alert.window_start).toLocaleDateString()}
          {revising && ' — the earlier verdict is kept in the history.'}
        </Typography>

        <Stack spacing={1}>
          {OPTIONS.map(option => {
            const active = choice === option.value;
            return (
              <Box
                key={option.value}
                onClick={() => setChoice(option.value)}
                role="button"
                tabIndex={0}
                onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') setChoice(option.value); }}
                sx={{
                  cursor: 'pointer',
                  borderRadius: 1,
                  p: 1.5,
                  border: '1px solid',
                  borderColor: active ? option.color : 'divider',
                  bgcolor: active ? `${option.color}14` : 'transparent',
                  '&:hover': { borderColor: option.color },
                }}
              >
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Box sx={{ width: 10, height: 10, borderRadius: '50%', bgcolor: option.color }} />
                  <Typography variant="body2" sx={{ fontWeight: 600 }}>{option.label}</Typography>
                </Box>
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block', ml: 2.5 }}>
                  {option.helper}
                </Typography>
              </Box>
            );
          })}
        </Stack>

        {selected && (
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1.5 }}>
            {selected.closes}
          </Typography>
        )}

        <TextField
          label="Why"
          placeholder="What you checked, and what settled it."
          value={rationale}
          onChange={e => setRationale(e.target.value)}
          multiline
          minRows={3}
          fullWidth
          required
          sx={{ mt: 2 }}
          helperText="Required — this is the record of how the call was reached."
        />

        {alert.findings && alert.findings.length > 0 && (
          <Box sx={{ mt: 2 }}>
            <Typography variant="caption" color="text.secondary">
              RECORDED WITH THIS VERDICT
            </Typography>
            <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap', mt: 0.5 }}>
              {[...new Set(alert.findings.map(f => f.detector))].map(d => (
                <Chip key={d} label={d} size="small" variant="outlined" sx={{ fontSize: '0.68rem', height: 20 }} />
              ))}
            </Box>
          </Box>
        )}

        {mutation.isError && (
          <MuiAlert severity="error" sx={{ mt: 2 }}>
            {apiErrorMessage(mutation.error)}
          </MuiAlert>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={handleClose} color="inherit">Cancel</Button>
        <Button
          variant="contained"
          onClick={() => mutation.mutate()}
          disabled={!canSubmit}
        >
          {mutation.isPending ? 'Recording...' : 'Record verdict'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
