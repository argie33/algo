import React, { useState, useEffect } from 'react';
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
  DialogActions,
  CircularProgress,
  Paper,
  Accordion,
  AccordionSummary,
  AccordionDetails
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
  Schedule,
  Sms,
  PhoneAndroid,
  ExpandMore,
  Backup
} from '@mui/icons-material';
import { useAuth } from '../../contexts/AuthContext';
import SecurityDashboard from '../auth/SecurityDashboard';
import PasswordStrengthValidator from '../auth/PasswordStrengthValidator';

const SecurityTab = ({ settings, updateSettings }) => {
  const { user, updatePassword, logout, updateUserMfaStatus } = useAuth();
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

  // MFA Management State
  const [mfaStatus, setMfaStatus] = useState({
    enabled: false,
    methods: [],
    loading: true,
    backupCodes: []
  });
  const [showMfaDialog, setShowMfaDialog] = useState(false);
  const [mfaSetupStep, setMfaSetupStep] = useState(1);
  const [selectedMfaMethod, setSelectedMfaMethod] = useState('');
  const [verificationCode, setVerificationCode] = useState('');
  const [phoneNumber, setPhoneNumber] = useState('');
  const [qrCodeUrl, setQrCodeUrl] = useState('');
  const [showBackupCodes, setShowBackupCodes] = useState(false);

  // Load actual MFA status from backend
  useEffect(() => {
    loadMfaStatus();
  }, [user]);

  const loadMfaStatus = async () => {
    if (!user) return;
    
    try {
      const response = await fetch('/api/user/mfa-status', {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('accessToken')}`,
          'Content-Type': 'application/json'
        }
      });

      if (response.ok) {
        const data = await response.json();
        setMfaStatus({
          enabled: data.mfaEnabled || false,
          methods: data.mfaMethods || [],
          backupCodes: data.backupCodes || [],
          loading: false
        });
      } else {
        // Fallback if endpoint not available
        setMfaStatus(prev => ({
          ...prev,
          enabled: settings?.security?.twoFactorAuth || false,
          loading: false
        }));
      }
    } catch (error) {
      console.error('Failed to load MFA status:', error);
      setMfaStatus(prev => ({
        ...prev,
        enabled: settings?.security?.twoFactorAuth || false,
        loading: false
      }));
    }
  };

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

  // MFA Management Functions
  const handleMfaToggle = async (enabled) => {
    if (enabled) {
      setShowMfaDialog(true);
      setMfaSetupStep(1);
    } else {
      // Disable MFA
      try {
        const response = await fetch('/api/user/two-factor/disable', {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('accessToken')}`,
            'Content-Type': 'application/json'
          }
        });

        if (response.ok) {
          setMfaStatus(prev => ({
            ...prev,
            enabled: false,
            methods: []
          }));
          // Update settings to keep UI in sync
          handleSecuritySettingChange('twoFactorAuth', false);
          // Update AuthContext to prevent inappropriate MFA prompts
          updateUserMfaStatus(false);
        }
      } catch (error) {
        console.error('Failed to disable MFA:', error);
      }
    }
  };

  const setupMfaMethod = async (method) => {
    setSelectedMfaMethod(method);
    
    try {
      const response = await fetch(`/api/user/two-factor/setup/${method}`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('accessToken')}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          phoneNumber: method === 'sms' ? phoneNumber : undefined
        })
      });

      const result = await response.json();

      if (response.ok) {
        if (method === 'totp' && result.qrCodeUrl) {
          setQrCodeUrl(result.qrCodeUrl);
        }
        setMfaSetupStep(2);
      } else {
        console.error('MFA setup failed:', result.message);
      }
    } catch (error) {
      console.error('Failed to setup MFA:', error);
    }
  };

  const verifyMfaSetup = async () => {
    try {
      const response = await fetch('/api/user/two-factor/verify', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('accessToken')}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          method: selectedMfaMethod,
          code: verificationCode
        })
      });

      const result = await response.json();

      if (response.ok) {
        setMfaStatus(prev => ({
          ...prev,
          enabled: true,
          methods: [...prev.methods, selectedMfaMethod],
          backupCodes: result.backupCodes || prev.backupCodes
        }));
        
        // Update settings to keep UI in sync
        handleSecuritySettingChange('twoFactorAuth', true);
        // Update AuthContext so MFA challenges work properly
        updateUserMfaStatus(true);
        
        setShowMfaDialog(false);
        resetMfaDialog();
      } else {
        console.error('MFA verification failed:', result.message);
      }
    } catch (error) {
      console.error('Failed to verify MFA setup:', error);
    }
  };

  const resetMfaDialog = () => {
    setMfaSetupStep(1);
    setSelectedMfaMethod('');
    setQrCodeUrl('');
    setVerificationCode('');
    setPhoneNumber('');
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

      {/* Two-Factor Authentication */}
      <Grid item xs={12} md={6}>
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              <Shield sx={{ mr: 1, verticalAlign: 'middle' }} />
              Two-Factor Authentication
              {mfaStatus.enabled && (
                <Chip 
                  label="Active" 
                  color="success" 
                  size="small" 
                  sx={{ ml: 2 }} 
                />
              )}
            </Typography>
            <Typography variant="body2" color="text.secondary" gutterBottom>
              Add an extra layer of security to your account
            </Typography>
            <Divider sx={{ my: 2 }} />

            {mfaStatus.loading ? (
              <Box display="flex" justifyContent="center" py={2}>
                <CircularProgress size={24} />
              </Box>
            ) : (
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                <FormControlLabel
                  control={
                    <Switch
                      checked={mfaStatus.enabled}
                      onChange={(e) => handleMfaToggle(e.target.checked)}
                      color="primary"
                    />
                  }
                  label="Enable Two-Factor Authentication"
                />

                {mfaStatus.enabled && mfaStatus.methods.length > 0 && (
                  <Box>
                    <Typography variant="subtitle2" gutterBottom>
                      Active Methods:
                    </Typography>
                    <List dense>
                      {mfaStatus.methods.map((method) => (
                        <ListItem key={method} sx={{ px: 0 }}>
                          <ListItemIcon>
                            {method === 'sms' ? <Sms /> : <PhoneAndroid />}
                          </ListItemIcon>
                          <ListItemText
                            primary={method === 'sms' ? 'SMS Authentication' : 'Authenticator App'}
                            secondary={method === 'sms' ? 'Verification codes via text message' : 'Time-based codes from authenticator app'}
                          />
                          <ListItemSecondaryAction>
                            <Button size="small" color="error">
                              Remove
                            </Button>
                          </ListItemSecondaryAction>
                        </ListItem>
                      ))}
                    </List>

                    {mfaStatus.backupCodes.length > 0 && (
                      <Box mt={2}>
                        <Button
                          startIcon={<Backup />}
                          onClick={() => setShowBackupCodes(!showBackupCodes)}
                          variant="outlined"
                          size="small"
                        >
                          {showBackupCodes ? 'Hide' : 'Show'} Backup Codes
                        </Button>
                        
                        {showBackupCodes && (
                          <Paper sx={{ p: 2, mt: 1, bgcolor: 'grey.50' }}>
                            <Typography variant="body2" gutterBottom>
                              Keep these backup codes safe. Each can only be used once:
                            </Typography>
                            <Grid container spacing={1}>
                              {mfaStatus.backupCodes.map((code, index) => (
                                <Grid item xs={6} sm={4} key={index}>
                                  <Typography variant="body2" fontFamily="monospace">
                                    {code}
                                  </Typography>
                                </Grid>
                              ))}
                            </Grid>
                          </Paper>
                        )}
                      </Box>
                    )}
                  </Box>
                )}

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
            )}
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

      {/* MFA Setup Dialog */}
      <Dialog 
        open={showMfaDialog} 
        onClose={() => {
          setShowMfaDialog(false);
          resetMfaDialog();
        }}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Set Up Two-Factor Authentication</DialogTitle>
        <DialogContent>
          {mfaSetupStep === 1 && (
            <Box>
              <Typography variant="body2" paragraph>
                Choose how you'd like to receive verification codes:
              </Typography>
              
              <List>
                <ListItem 
                  button 
                  onClick={() => setupMfaMethod('totp')}
                  sx={{ border: 1, borderColor: 'divider', borderRadius: 1, mb: 1 }}
                >
                  <ListItemIcon>
                    <PhoneAndroid />
                  </ListItemIcon>
                  <ListItemText
                    primary="Authenticator App"
                    secondary="Use apps like Google Authenticator or Authy (Recommended)"
                  />
                </ListItem>
                
                <ListItem 
                  button 
                  onClick={() => setSelectedMfaMethod('sms')}
                  sx={{ border: 1, borderColor: 'divider', borderRadius: 1 }}
                >
                  <ListItemIcon>
                    <Sms />
                  </ListItemIcon>
                  <ListItemText
                    primary="SMS Text Message"
                    secondary="Receive codes via text message"
                  />
                </ListItem>
              </List>

              {selectedMfaMethod === 'sms' && (
                <Box mt={2}>
                  <TextField
                    fullWidth
                    label="Phone Number"
                    value={phoneNumber}
                    onChange={(e) => setPhoneNumber(e.target.value)}
                    placeholder="+1 (555) 123-4567"
                    helperText="Enter your phone number with country code"
                  />
                  <Box mt={2}>
                    <Button 
                      variant="contained" 
                      onClick={() => setupMfaMethod('sms')}
                      disabled={!phoneNumber}
                    >
                      Continue
                    </Button>
                  </Box>
                </Box>
              )}
            </Box>
          )}

          {mfaSetupStep === 2 && (
            <Box>
              <Typography variant="body2" paragraph>
                {selectedMfaMethod === 'totp' 
                  ? 'Scan this QR code with your authenticator app, then enter the verification code:'
                  : 'Enter the verification code sent to your phone:'
                }
              </Typography>

              {selectedMfaMethod === 'totp' && qrCodeUrl && (
                <Box textAlign="center" mb={2}>
                  <img src={qrCodeUrl} alt="QR Code" style={{ maxWidth: '200px' }} />
                </Box>
              )}

              <TextField
                fullWidth
                label="Verification Code"
                value={verificationCode}
                onChange={(e) => setVerificationCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                placeholder="000000"
                inputProps={{ maxLength: 6 }}
              />

              <Box mt={2}>
                <Button 
                  variant="contained" 
                  onClick={verifyMfaSetup}
                  disabled={verificationCode.length !== 6}
                >
                  Verify & Enable
                </Button>
              </Box>
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => {
            setShowMfaDialog(false);
            resetMfaDialog();
          }}>
            Cancel
          </Button>
        </DialogActions>
      </Dialog>
    </Grid>
  );
};

export default SecurityTab;