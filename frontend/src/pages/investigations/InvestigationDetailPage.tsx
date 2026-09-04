import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Box,
  Typography,
  Button,
  Chip,
  CircularProgress,
  Alert,
  Stack,
  TextField,
  IconButton,
  Paper,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  MenuItem,
  Select,
  FormControl,
  InputLabel,
  Card,
  CardContent,
} from '@mui/material';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import SendIcon from '@mui/icons-material/Send';
import AddLinkIcon from '@mui/icons-material/AddLink';
import PageHeader from '../../components/common/PageHeader';
import SeverityBadge from '../../components/common/SeverityBadge';
import EmptyState from '../../components/common/EmptyState';
import type { InvestigationStatus } from '../../types';
import {
  getInvestigation,
  updateInvestigationStatus,
  assignInvestigation,
  listNotes,
  addNote,
  linkAlertToInvestigation,
  unlinkAlertFromInvestigation,
} from '../../api/investigationService';
import type { InvestigationStatusRequest } from '../../types/investigation';

const STATUSES: InvestigationStatus[] = ['OPEN', 'IN_PROGRESS', 'RESOLVED', 'CLOSED'];

const STATUS_COLORS: Record<string, string> = {
  OPEN: '#3b82f6',
  IN_PROGRESS: '#8b5cf6',
  RESOLVED: '#10b981',
  CLOSED: '#64748b',
};

export default function InvestigationDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [noteContent, setNoteContent] = useState('');
  const [linkAlertId, setLinkAlertId] = useState('');
  const [linkDialogOpen, setLinkDialogOpen] = useState(false);
  const [statusDialogOpen, setStatusDialogOpen] = useState(false);
  const [assignDialogOpen, setAssignDialogOpen] = useState(false);
  const [newStatus, setNewStatus] = useState('');
  const [newAssignee, setNewAssignee] = useState('');
  const [resolution, setResolution] = useState('');

  const { data: investigation, isLoading, isError, error } = useQuery({
    queryKey: ['investigation', id],
    queryFn: () => getInvestigation(id!),
    enabled: !!id,
  });

  const { data: notesData, refetch: refetchNotes } = useQuery({
    queryKey: ['investigation-notes', id],
    queryFn: () => listNotes(id!),
    enabled: !!id,
  });

  const statusMutation = useMutation({
    mutationFn: (body: InvestigationStatusRequest) => updateInvestigationStatus(id!, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['investigation', id] });
      setStatusDialogOpen(false);
    },
  });

  const assignMutation = useMutation({
    mutationFn: (userId: string) => assignInvestigation(id!, { user_id: userId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['investigation', id] });
      setAssignDialogOpen(false);
    },
  });

  const noteMutation = useMutation({
    mutationFn: (content: string) => addNote(id!, { content }),
    onSuccess: () => {
      setNoteContent('');
      refetchNotes();
    },
  });

  const linkMutation = useMutation({
    mutationFn: (alertId: string) => linkAlertToInvestigation(id!, { alert_id: alertId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['investigation', id] });
      setLinkDialogOpen(false);
      setLinkAlertId('');
    },
  });

  const unlinkMutation = useMutation({
    mutationFn: (alertId: string) => unlinkAlertFromInvestigation(id!, alertId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['investigation', id] }),
  });

  if (isLoading) return <Box sx={{ display: 'flex', justifyContent: 'center', py: 8 }}><CircularProgress /></Box>;
  if (isError) return <Alert severity="error">{(error as Error).message}</Alert>;
  if (!investigation) return null;

  const inv = investigation;

  return (
    <Box>
      <Box sx={{ mb: 2 }}>
        <Button startIcon={<ArrowBackIcon />} variant="text" size="small" onClick={() => navigate('/investigations')}>
          Back to Investigations
        </Button>
      </Box>

      <PageHeader
        title={inv.title}
        subtitle={inv.description || undefined}
        actions={
          <Stack direction="row" spacing={1}>
            <Button variant="outlined" size="small" onClick={() => setAssignDialogOpen(true)}>
              Assign
            </Button>
            <Button variant="outlined" size="small" color="warning" onClick={() => { setNewStatus(''); setResolution(''); setStatusDialogOpen(true); }}>
              Change Status
            </Button>
            <Button variant="contained" size="small" startIcon={<AddLinkIcon />} onClick={() => setLinkDialogOpen(true)}>
              Link Alert
            </Button>
          </Stack>
        }
      />

      <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: 3 }}>
        {/* Left column */}
        <Stack spacing={3}>
          {/* Investigation Info Card */}
          <Card>
            <CardContent>
              <Typography variant="subtitle2" color="text.secondary" gutterBottom>Investigation Info</Typography>
              <Stack spacing={1.5}>
                <Box sx={{ display: 'flex', gap: 2 }}>
                  <SeverityBadge severity={inv.severity as any} />
                  <Chip
                    label={inv.status.replace('_', ' ')}
                    size="small"
                    sx={{ bgcolor: `${STATUS_COLORS[inv.status] ?? '#64748b'}20`, color: STATUS_COLORS[inv.status] ?? '#64748b', fontWeight: 600 }}
                  />
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">ASSIGNEE</Typography>
                  <Typography variant="body2">{inv.assigned_to ?? 'Unassigned'}</Typography>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">CREATED BY</Typography>
                  <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>{inv.created_by}</Typography>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">CREATED AT</Typography>
                  <Typography variant="body2">{new Date(inv.created_at).toLocaleString()}</Typography>
                </Box>
                <Box>
                  <Typography variant="caption" color="text.secondary">UPDATED AT</Typography>
                  <Typography variant="body2">{new Date(inv.updated_at).toLocaleString()}</Typography>
                </Box>
                {inv.resolution && (
                  <Box>
                    <Typography variant="caption" color="text.secondary">RESOLUTION</Typography>
                    <Typography variant="body2">{inv.resolution}</Typography>
                  </Box>
                )}
              </Stack>
            </CardContent>
          </Card>

          {/* Linked Alerts */}
          <Card>
            <CardContent>
              <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                Linked Alerts ({inv.related_alert_ids.length})
              </Typography>
              {inv.related_alert_ids.length === 0 ? (
                <Typography variant="body2" color="text.disabled">No alerts linked.</Typography>
              ) : (
                <Stack spacing={1}>
                  {inv.related_alert_ids.map(alertId => (
                    <Box key={alertId} sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', bgcolor: 'background.default', borderRadius: 1, px: 1.5, py: 1 }}>
                      <Typography variant="body2" sx={{ fontFamily: 'monospace', fontSize: '0.8rem' }}>{alertId}</Typography>
                      <IconButton size="small" color="error" onClick={() => unlinkMutation.mutate(alertId)}>
                        ×
                      </IconButton>
                    </Box>
                  ))}
                </Stack>
              )}
            </CardContent>
          </Card>

          {/* Related Users */}
          {inv.related_user_ids.length > 0 && (
            <Card>
              <CardContent>
                <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                  Related Users ({inv.related_user_ids.length})
                </Typography>
                <Stack spacing={0.5}>
                  {inv.related_user_ids.map(uid => (
                    <Typography key={uid} variant="body2" sx={{ fontFamily: 'monospace', fontSize: '0.8rem' }}>{uid}</Typography>
                  ))}
                </Stack>
              </CardContent>
            </Card>
          )}
        </Stack>

        {/* Right column — Notes Timeline */}
        <Stack spacing={2}>
          <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>Timeline / Notes</Typography>

          {/* Add note */}
          <Paper variant="outlined" sx={{ p: 2 }}>
            <TextField
              multiline
              rows={3}
              fullWidth
              size="small"
              placeholder="Add a note..."
              value={noteContent}
              onChange={e => setNoteContent(e.target.value)}
            />
            <Box sx={{ display: 'flex', justifyContent: 'flex-end', mt: 1 }}>
              <Button
                size="small"
                variant="contained"
                endIcon={<SendIcon />}
                disabled={!noteContent.trim() || noteMutation.isPending}
                onClick={() => noteMutation.mutate(noteContent.trim())}
              >
                Add Note
              </Button>
            </Box>
          </Paper>

          {/* Notes list */}
          {(!notesData?.notes || notesData.notes.length === 0) ? (
            <EmptyState title="No notes yet" description="Add the first note to the timeline." />
          ) : (
            <Stack spacing={1.5}>
              {[...notesData.notes].reverse().map(note => (
                <Paper key={note.id} variant="outlined" sx={{ p: 2 }}>
                  <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>{note.content}</Typography>
                  <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
                    {note.author_id} · {new Date(note.created_at).toLocaleString()}
                  </Typography>
                </Paper>
              ))}
            </Stack>
          )}
        </Stack>
      </Box>

      {/* Status Change Dialog */}
      <Dialog open={statusDialogOpen} onClose={() => setStatusDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Change Investigation Status</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <FormControl fullWidth size="small">
              <InputLabel>New Status</InputLabel>
              <Select label="New Status" value={newStatus} onChange={e => setNewStatus(e.target.value)}>
                {STATUSES.map(s => <MenuItem key={s} value={s}>{s.replace('_', ' ')}</MenuItem>)}
              </Select>
            </FormControl>
            <TextField
              label="Resolution (optional)"
              multiline
              rows={2}
              fullWidth
              value={resolution}
              onChange={e => setResolution(e.target.value)}
              placeholder="Describe the resolution..."
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setStatusDialogOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={!newStatus || statusMutation.isPending}
            onClick={() => statusMutation.mutate({ status: newStatus, resolution: resolution || undefined })}
          >
            {statusMutation.isPending ? 'Saving...' : 'Save'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Assign Dialog */}
      <Dialog open={assignDialogOpen} onClose={() => setAssignDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Assign Investigator</DialogTitle>
        <DialogContent>
          <TextField
            label="User ID"
            fullWidth
            size="small"
            sx={{ mt: 1 }}
            value={newAssignee}
            onChange={e => setNewAssignee(e.target.value)}
            placeholder="Enter user ID..."
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAssignDialogOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={!newAssignee.trim() || assignMutation.isPending}
            onClick={() => assignMutation.mutate(newAssignee.trim())}
          >
            {assignMutation.isPending ? 'Saving...' : 'Assign'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Link Alert Dialog */}
      <Dialog open={linkDialogOpen} onClose={() => setLinkDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Link Alert to Investigation</DialogTitle>
        <DialogContent>
          <TextField
            label="Alert ID"
            fullWidth
            size="small"
            sx={{ mt: 1 }}
            value={linkAlertId}
            onChange={e => setLinkAlertId(e.target.value)}
            placeholder="Enter the alert UUID..."
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setLinkDialogOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={!linkAlertId.trim() || linkMutation.isPending}
            onClick={() => linkMutation.mutate(linkAlertId.trim())}
          >
            {linkMutation.isPending ? 'Linking...' : 'Link Alert'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
