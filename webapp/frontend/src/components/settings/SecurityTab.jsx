import React, { useState } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Grid,
  TextField,
  Button,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Switch,
  FormControlLabel,
  Alert,
  Divider,
  IconButton,
  InputAdornment,
  Chip,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  ListItemSecondaryAction,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions
} from '@mui/material';
import {
  Security,
  Lock,
  Visibility,
  VisibilityOff,
  Device,
  History,
  Shield,
  Fingerprint,
  Smartphone,
  Computer,
  Warning,
  CheckCircle,
  Delete,
  Refresh,
  VpnKey,
  Schedule
} from '@mui/icons-material';
import { useAuth } from '../../contexts/AuthContext';
import SecurityDashboard from '../auth/SecurityDashboard';
import PasswordStrengthValidator from '../auth/PasswordStrengthValidator';

const SecurityTab = ({ settings, updateSettings }) => {
  const { user, updatePassword, logout } = useAuth();
  const [showCurrentPassword, setShowCurrentPassword] = useState(false);
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [passwordForm, setPasswordForm] = useState({
    currentPassword: '',
    newPassword: '',
    confirmPassword: ''
  });
  const [passwordChangeLoading, setPasswordChangeLoading] = useState(false);
  const [passwordChangeError, setPasswordChangeError] = useState('');
  const [passwordChangeSuccess, setPasswordChangeSuccess] = useState('');
  const [deleteAccountDialog, setDeleteAccountDialog] = useState(false);

  const handlePasswordChange = async () => {
    if (passwordForm.newPassword !== passwordForm.confirmPassword) {
      setPasswordChangeError('New passwords do not match');
      return;
    }

    if (passwordForm.newPassword.length < 8) {
      setPasswordChangeError('Password must be at least 8 characters long');
      return;
    }

    setPasswordChangeLoading(true);
    setPasswordChangeError('');

    try {
      await updatePassword(passwordForm.currentPassword, passwordForm.newPassword);
      setPasswordChangeSuccess('Password updated successfully');
      setPasswordForm({
        currentPassword: '',
        newPassword: '',
        confirmPassword: ''
      });
    } catch (error) {
      setPasswordChangeError(error.message || 'Failed to update password');
    } finally {
      setPasswordChangeLoading(false);
    }
  };

  const handleSecuritySettingChange = (key, value) => {
    updateSettings('security', key, value);
  };

  return (
    <Grid container spacing={3}>
      {/* Password Management */}
      <Grid item xs={12} md={6}>
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              <Lock sx={{ mr: 1, verticalAlign: 'middle' }} />
              Password Management
            </Typography>
            <Typography variant="body2" color="text.secondary" gutterBottom>
              Change your account password and manage security settings
            </Typography>
            <Divider sx={{ my: 2 }} />

            {passwordChangeError && (
              <Alert severity="error" sx={{ mb: 2 }}>
                {passwordChangeError}
              </Alert>
            )}

            {passwordChangeSuccess && (
              <Alert severity="success" sx={{ mb: 2 }}>
                {passwordChangeSuccess}
              </Alert>
            )}

            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              <TextField
                fullWidth
                label="Current Password"
                type={showCurrentPassword ? 'text' : 'password'}
                value={passwordForm.currentPassword}
                onChange={(e) => setPasswordForm({ ...passwordForm, currentPassword: e.target.value })}
                InputProps={{
                  endAdornment: (
                    <InputAdornment position="end">
                      <IconButton
                        onClick={() => setShowCurrentPassword(!showCurrentPassword)}
                        edge="end"
                      >
                        {showCurrentPassword ? <VisibilityOff /> : <Visibility />}
                      </IconButton>
                    </InputAdornment>
                  )
                }}
              />

              <TextField
                fullWidth
                label="New Password"
                type={showNewPassword ? 'text' : 'password'}
                value={passwordForm.newPassword}
                onChange={(e) => setPasswordForm({ ...passwordForm, newPassword: e.target.value })}
                InputProps={{
                  endAdornment: (
                    <InputAdornment position="end">
                      <IconButton
                        onClick={() => setShowNewPassword(!showNewPassword)}
                        edge="end"
                      >
                        {showNewPassword ? <VisibilityOff /> : <Visibility />}
                      </IconButton>
                    </InputAdornment>
                  )
                }}
              />

              {passwordForm.newPassword && (
                <PasswordStrengthValidator password={passwordForm.newPassword} />
              )}

              <TextField
                fullWidth
                label="Confirm New Password"
                type={showConfirmPassword ? 'text' : 'password'}
                value={passwordForm.confirmPassword}
                onChange={(e) => setPasswordForm({ ...passwordForm, confirmPassword: e.target.value })}
                error={passwordForm.confirmPassword && passwordForm.newPassword !== passwordForm.confirmPassword}
                helperText={
                  passwordForm.confirmPassword && passwordForm.newPassword !== passwordForm.confirmPassword
                    ? 'Passwords do not match'
                    : ''
                }
                InputProps={{
                  endAdornment: (
                    <InputAdornment position="end">
                      <IconButton
                        onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                        edge="end"
                      >
                        {showConfirmPassword ? <VisibilityOff /> : <Visibility />}
                      </IconButton>
                    </InputAdornment>
                  )
                }}
              />

              <Button
                variant="contained"
                onClick={handlePasswordChange}
                disabled={
                  passwordChangeLoading ||
                  !passwordForm.currentPassword ||
                  !passwordForm.newPassword ||
                  !passwordForm.confirmPassword ||
                  passwordForm.newPassword !== passwordForm.confirmPassword
                }
                sx={{ mt: 1 }}
              >
                {passwordChangeLoading ? 'Updating...' : 'Update Password'}
              </Button>
            </Box>
          </CardContent>
        </Card>
      </Grid>

      {/* Security Settings */}
      <Grid item xs={12} md={6}>
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              <Shield sx={{ mr: 1, verticalAlign: 'middle' }} />
              Security Settings
            </Typography>
            <Typography variant="body2" color="text.secondary" gutterBottom>
              Configure your account security preferences
            </Typography>
            <Divider sx={{ my: 2 }} />

            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              <FormControlLabel
                control={
                  <Switch
                    checked={settings?.security?.twoFactorAuth || false}
                    onChange={(e) => handleSecuritySettingChange('twoFactorAuth', e.target.checked)}
                  />
                }
                label="Two-Factor Authentication"
              />

              <FormControlLabel
                control={
                  <Switch
                    checked={settings?.security?.requirePasswordForTrades || false}
                    onChange={(e) => handleSecuritySettingChange('requirePasswordForTrades', e.target.checked)}
                  />
                }
                label="Require Password for Trading"
              />

              <FormControlLabel
                control={
                  <Switch
                    checked={settings?.security?.auditLog || false}
                    onChange={(e) => handleSecuritySettingChange('auditLog', e.target.checked)}
                  />
                }
                label="Enable Audit Logging"
              />

              <FormControl fullWidth>
                <InputLabel>Session Timeout</InputLabel>
                <Select
                  value={settings?.security?.sessionTimeout || 30}
                  label="Session Timeout"
                  onChange={(e) => handleSecuritySettingChange('sessionTimeout', e.target.value)}
                >
                  <MenuItem value={15}>15 minutes</MenuItem>
                  <MenuItem value={30}>30 minutes</MenuItem>
                  <MenuItem value={60}>1 hour</MenuItem>
                  <MenuItem value={120}>2 hours</MenuItem>
                  <MenuItem value={480}>8 hours</MenuItem>
                  <MenuItem value={0}>Never</MenuItem>
                </Select>
              </FormControl>

              <Button
                variant="outlined"
                startIcon={<Fingerprint />}
                onClick={() => {
                  // TODO: Implement biometric setup
                  alert('Biometric authentication setup coming soon');
                }}
              >
                Setup Biometric Authentication
              </Button>
            </Box>
          </CardContent>
        </Card>
      </Grid>

      {/* Account Management */}
      <Grid item xs={12}>
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              <Security sx={{ mr: 1, verticalAlign: 'middle' }} />
              Account Information
            </Typography>
            <Typography variant="body2" color="text.secondary" gutterBottom>
              Manage your account details and dangerous actions
            </Typography>
            <Divider sx={{ my: 2 }} />

            <Grid container spacing={2}>
              <Grid item xs={12} md={6}>
                <TextField
                  fullWidth
                  label="Username"
                  value={user?.username || ''}
                  disabled
                  helperText="Contact support to change username"
                />
              </Grid>
              <Grid item xs={12} md={6}>
                <TextField
                  fullWidth
                  label="Email"
                  value={user?.email || ''}
                  disabled
                  helperText="Contact support to change email"
                />
              </Grid>
              <Grid item xs={12} md={6}>
                <TextField
                  fullWidth
                  label="Account Created"
                  value={user?.createdAt ? new Date(user.createdAt).toLocaleDateString() : 'Unknown'}
                  disabled
                />
              </Grid>
              <Grid item xs={12} md={6}>
                <TextField
                  fullWidth
                  label="Last Login"
                  value={user?.lastLogin ? new Date(user.lastLogin).toLocaleDateString() : 'Unknown'}
                  disabled
                />
              </Grid>
            </Grid>

            <Box sx={{ mt: 3, pt: 2, borderTop: '1px solid #e0e0e0' }}>
              <Typography variant="h6" color="error" gutterBottom>
                Danger Zone
              </Typography>
              <Button
                variant="outlined"
                color="error"
                startIcon={<Delete />}
                onClick={() => setDeleteAccountDialog(true)}
              >
                Delete Account
              </Button>
            </Box>
          </CardContent>
        </Card>
      </Grid>

      {/* Security Dashboard */}
      <Grid item xs={12}>
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              <History sx={{ mr: 1, verticalAlign: 'middle' }} />
              Login History & Device Management
            </Typography>
            <Typography variant="body2" color="text.secondary" gutterBottom>
              Monitor your account activity and manage trusted devices
            </Typography>
            <Divider sx={{ my: 2 }} />
            <SecurityDashboard />
          </CardContent>
        </Card>
      </Grid>

      {/* Delete Account Dialog */}
      <Dialog open={deleteAccountDialog} onClose={() => setDeleteAccountDialog(false)}>
        <DialogTitle>Delete Account</DialogTitle>
        <DialogContent>
          <Alert severity="error" sx={{ mb: 2 }}>
            This action cannot be undone. All your data will be permanently deleted.
          </Alert>
          <Typography>
            Are you sure you want to delete your account? This will:
          </Typography>
          <List dense>
            <ListItem>
              <ListItemText primary="• Delete all your portfolio data" />
            </ListItem>
            <ListItem>
              <ListItemText primary="• Remove all API key configurations" />
            </ListItem>
            <ListItem>
              <ListItemText primary="• Cancel any active subscriptions" />
            </ListItem>
            <ListItem>
              <ListItemText primary="• Permanently delete your account" />
            </ListItem>
          </List>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteAccountDialog(false)}>
            Cancel
          </Button>
          <Button
            color="error"
            variant="contained"
            onClick={() => {
              // TODO: Implement account deletion
              alert('Account deletion not implemented yet');
              setDeleteAccountDialog(false);
            }}
          >
            Delete Account
          </Button>
        </DialogActions>
      </Dialog>
    </Grid>
  );
};

export default SecurityTab;