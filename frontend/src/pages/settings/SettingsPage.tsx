import { useState } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  TextField,
  Button,
  CircularProgress,
  Alert,
  Grid,
} from '@mui/material';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import PageHeader from '../../components/common/PageHeader';
import { getCurrentUser, updateCurrentUser, type UpdateUserRequest } from '../../api/authService';
import type { User } from '../../types/auth';

export default function SettingsPage() {
  const queryClient = useQueryClient();
  const [formData, setFormData] = useState<UpdateUserRequest>({});
  const [saved, setSaved] = useState(false);

  const { data: user, isLoading } = useQuery({
    queryKey: ['currentUser'],
    queryFn: getCurrentUser,
  });

  const mutation = useMutation({
    mutationFn: updateCurrentUser,
    onSuccess: (updatedUser: User) => {
      queryClient.setQueryData(['currentUser'], updatedUser);
      setSaved(true);
      setFormData({});
      setTimeout(() => setSaved(false), 3000);
    },
  });

  function handleChange(field: 'full_name' | 'email', value: string) {
    setFormData(prev => ({ ...prev, [field]: value }));
    setSaved(false);
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    mutation.mutate(formData);
  }

  if (isLoading) {
    return (
      <Box>
        <PageHeader title="Settings" subtitle="Application and user preferences" />
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 8 }}>
          <CircularProgress />
        </Box>
      </Box>
    );
  }

  return (
    <Box>
      <PageHeader title="Settings" subtitle="Application and user preferences" />

      {saved && (
        <Alert severity="success" sx={{ mb: 2 }}>
          Profile updated successfully!
        </Alert>
      )}

      {mutation.error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          Failed to update profile
        </Alert>
      )}

      <Grid container spacing={2}>
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                User Profile
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                Update your profile information.
              </Typography>

              <form onSubmit={handleSubmit}>
                <TextField
                  fullWidth
                  label="Username"
                  value={user?.username ?? ''}
                  disabled
                  sx={{ mb: 2 }}
                />
                <TextField
                  fullWidth
                  label="Email"
                  type="email"
                  value={formData.email ?? user?.email ?? ''}
                  onChange={(e) => handleChange('email', e.target.value)}
                  sx={{ mb: 2 }}
                />
                <TextField
                  fullWidth
                  label="Full Name"
                  value={formData.full_name ?? user?.full_name ?? ''}
                  onChange={(e) => handleChange('full_name', e.target.value)}
                  sx={{ mb: 2 }}
                />
                <TextField
                  fullWidth
                  label="Roles"
                  value={user?.roles?.join(', ') ?? ''}
                  disabled
                  sx={{ mb: 2 }}
                />
                <Button
                  type="submit"
                  variant="contained"
                  disabled={mutation.isPending || Object.keys(formData).length === 0}
                >
                  {mutation.isPending ? 'Saving...' : 'Save Changes'}
                </Button>
              </form>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Account Information
              </Typography>
              <Box sx={{ mb: 2 }}>
                <Typography variant="body2" color="text.secondary">
                  Account Type
                </Typography>
                <Typography variant="body1">
                  {user?.is_superadmin ? 'Super Administrator' : 'Standard User'}
                </Typography>
              </Box>
              <Box sx={{ mb: 2 }}>
                <Typography variant="body2" color="text.secondary">
                  Permissions
                </Typography>
                <Typography variant="body1">
                  {user?.permissions?.length ?? 0} permissions
                </Typography>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
}
