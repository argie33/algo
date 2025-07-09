import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { useNavigate } from 'react-router-dom';
import {
  Container,
  Paper,
  Tabs,
  Tab,
  Box,
  Typography,
  Grid,
  Card,
  CardContent,
  CardHeader,
  Button,
  TextField,
  Switch,
  FormControlLabel,
  Divider,
  Alert,
  Chip,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Avatar,
  CircularProgress,
  Snackbar,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  ListItemSecondaryAction
} from '@mui/material';
import {
  AccountCircle,
  Security,
  Api,
  Notifications,
  Palette,
  Delete,
  Edit,
  Add,
  Visibility,
  VisibilityOff,
  CloudUpload,
  Download,
  Key,
  Link,
  Warning,
  CheckCircle,
  Save,
  Cancel,
  BusinessCenter,
  TrendingUp,
  MonetizationOn,
  ContentCopy
} from '@mui/icons-material';
import { getApiConfig } from '../services/api';
import SettingsApiKeys from './SettingsApiKeys';

function TabPanel({ children, value, index, ...other }) {
  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`settings-tabpanel-${index}`}
      aria-labelledby={`settings-tab-${index}`}
      {...other}
    >
      {value === index && (
        <Box sx={{ py: 3 }}>
          {children}
        </Box>
      )}
    </div>
  );
}

const Settings = () => {
  const { user, isAuthenticated, isLoading, logout, checkAuthState } = useAuth();
  const navigate = useNavigate();
  const { apiUrl } = getApiConfig();
  
  const [activeTab, setActiveTab] = useState(0);
  const [loading, setLoading] = useState(false);
  const [snackbar, setSnackbar] = useState({ open: false, message: '', severity: 'success' });
  const [apiKeys, setApiKeys] = useState([]);
  const [addApiKeyDialog, setAddApiKeyDialog] = useState(false);
  const [showApiKeys, setShowApiKeys] = useState({});
  
  // New API key form
  const [newApiKey, setNewApiKey] = useState({
    brokerName: '',
    apiKey: '',
    apiSecret: '',
    sandbox: true
  });

  // User profile form
  const [profileData, setProfileData] = useState({
    firstName: '',
    lastName: '',
    email: '',
    phone: '',
    timezone: 'America/New_York',
    currency: 'USD'
  });

  // Notification preferences
  const [notifications, setNotifications] = useState({
    email: true,
    push: true,
    priceAlerts: true,
    portfolioUpdates: true,
    marketNews: false,
    weeklyReports: true
  });

  // Theme preferences
  const [themeSettings, setThemeSettings] = useState({
    darkMode: false,
    primaryColor: '#1976d2',
    chartStyle: 'candlestick',
    layout: 'standard'
  });

  // Authentication guard - disabled
  // useEffect(() => {
  //   if (!isLoading && !isAuthenticated) {
  //     navigate('/login');
  //   }
  // }, [isAuthenticated, isLoading, navigate]);

  // Load user data
  useEffect(() => {
    if (isAuthenticated && user) {
      loadUserSettings();
    } else if (!isLoading && !user && !isAuthenticated) {
      // If we're not loading, have no user, and not authenticated, try to re-check auth
      console.log('Settings: No user found, attempting to re-check authentication');
      checkAuthState();
    }
  }, [isAuthenticated, user, isLoading]);

  const loadUserSettings = async () => {
    try {
      setLoading(true);
      
      // Load user profile data
      setProfileData({
        firstName: user?.firstName || '',
        lastName: user?.lastName || '',
        email: user?.email || '',
        phone: user?.phone || '',
        timezone: user?.timezone || 'America/New_York',
        currency: user?.currency || 'USD'
      });

      // Load API keys with error handling
      try {
        await loadApiKeys();
      } catch (apiError) {
        console.error('API keys loading failed:', apiError);
        showSnackbar(`Failed to load API keys: ${apiError.message}`, 'error');
        // Don't fail the entire settings load if API keys fail
      }

      // Load notification preferences
      try {
        const notifResponse = await fetch(`${apiUrl}/api/settings/notifications`, {
          headers: {
            'Authorization': `Bearer ${user?.tokens?.accessToken || 'dev-token'}`
          }
        });
        if (notifResponse.ok) {
          const notifData = await notifResponse.json();
          setNotifications(prev => ({ ...prev, ...notifData.preferences }));
        }
      } catch (error) {
        console.log('Failed to load notification preferences, using defaults');
      }

      // Load theme preferences
      try {
        const themeResponse = await fetch(`${apiUrl}/api/settings/theme`, {
          headers: {
            'Authorization': `Bearer ${user?.tokens?.accessToken || 'dev-token'}`
          }
        });
        if (themeResponse.ok) {
          const themeData = await themeResponse.json();
          setThemeSettings(prev => ({ ...prev, ...themeData.preferences }));
        }
      } catch (error) {
        console.log('Failed to load theme preferences, using defaults');
      }
      
    } catch (error) {
      console.error('Error loading settings:', error);
      showSnackbar('Failed to load settings', 'error');
      
      // Set empty profile data to show there's an issue
      setProfileData({
        firstName: '',
        lastName: '',
        email: '',
        phone: '',
        timezone: 'America/New_York',
        currency: 'USD'
      });
    } finally {
      setLoading(false);
    }
  };

  const loadApiKeys = async () => {
    try {
      const response = await fetch(`${apiUrl}/api/user/api-keys`, {
        headers: {
          'Authorization': `Bearer ${user?.tokens?.accessToken || 'dev-token'}`
        }
      });
      
      if (response.ok) {
        const data = await response.json();
        setApiKeys(data.apiKeys || []);
      } else {
        console.error('API keys endpoint returned non-OK status:', response.status);
        throw new Error(`API keys endpoint failed: ${response.status}`);
      }
    } catch (error) {
      console.error('Error loading API keys:', error);
      setApiKeys([]); // Set empty array and let user see there's no data
      throw error; // Re-throw so parent catch can handle it
    }
  };

  const handleTabChange = (event, newValue) => {
    setActiveTab(newValue);
  };

  const showSnackbar = (message, severity = 'success') => {
    setSnackbar({ open: true, message, severity });
  };

  const handleSaveProfile = async () => {
    try {
      setLoading(true);
      
      const response = await fetch(`${apiUrl}/api/settings/profile`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${user?.tokens?.accessToken || 'dev-token'}`
        },
        body: JSON.stringify(profileData)
      });

      if (response.ok) {
        const updatedUser = await response.json();
        showSnackbar('Profile updated successfully');
        
        // Update the user context with new data
        if (updatedUser.user) {
          // This would typically update the auth context
          // For now, just refresh the settings
          await loadUserSettings();
        }
      } else {
        const error = await response.json();
        showSnackbar(error.error || 'Failed to update profile', 'error');
      }
    } catch (error) {
      console.error('Error saving profile:', error);
      showSnackbar('Failed to update profile', 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleAddApiKey = async () => {
    try {
      setLoading(true);
      
      const response = await fetch(`${apiUrl}/api/portfolio/api-keys`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${user?.tokens?.accessToken || 'dev-token'}`
        },
        body: JSON.stringify(newApiKey)
      });

      if (response.ok) {
        showSnackbar('API key added successfully');
        setAddApiKeyDialog(false);
        setNewApiKey({ brokerName: '', apiKey: '', apiSecret: '', sandbox: true });
        await loadApiKeys();
      } else {
        const error = await response.json();
        showSnackbar(error.error || 'Failed to add API key', 'error');
      }
    } catch (error) {
      console.error('Error adding API key:', error);
      showSnackbar('Failed to add API key', 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteApiKey = async (brokerName) => {
    try {
      const response = await fetch(`${apiUrl}/api/portfolio/api-keys/${brokerName}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${user?.tokens?.accessToken || 'dev-token'}`
        }
      });

      if (response.ok) {
        showSnackbar('API key deleted successfully');
        await loadApiKeys();
      } else {
        showSnackbar('Failed to delete API key', 'error');
      }
    } catch (error) {
      console.error('Error deleting API key:', error);
      showSnackbar('Failed to delete API key', 'error');
    }
  };

  const handleTestConnection = async (brokerName) => {
    try {
      setLoading(true);
      
      const response = await fetch(`${apiUrl}/api/portfolio/test-connection/${brokerName}`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${user?.tokens?.accessToken || 'dev-token'}`
        }
      });

      if (response.ok) {
        const data = await response.json();
        if (data.connection.valid) {
          const accountInfo = data.connection.accountInfo;
          showSnackbar(
            `✅ Connection successful! Account: ${accountInfo.accountId}, 
            Portfolio Value: $${accountInfo.portfolioValue?.toLocaleString()}, 
            Environment: ${accountInfo.environment}`, 
            'success'
          );
        } else {
          showSnackbar(`❌ Connection failed: ${data.connection.error}`, 'error');
        }
      } else {
        const error = await response.json();
        showSnackbar(error.error || 'Failed to test connection', 'error');
      }
    } catch (error) {
      console.error('Error testing connection:', error);
      showSnackbar('Failed to test connection', 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleImportPortfolio = async (brokerName) => {
    try {
      setLoading(true);
      
      const response = await fetch(`${apiUrl}/api/portfolio/import/${brokerName}`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${user?.tokens?.accessToken || 'dev-token'}`
        }
      });

      if (response.ok) {
        const data = await response.json();
        const summary = data.data.summary;
        showSnackbar(
          `✅ Portfolio imported! ${summary.positions} positions, 
          $${summary.totalValue?.toLocaleString()} total value, 
          $${summary.totalPnL?.toLocaleString()} P&L (${summary.totalPnLPercent?.toFixed(2)}%)`, 
          'success'
        );
        
        // Refresh the page or redirect to portfolio view
        setTimeout(() => {
          window.location.href = '/portfolio';
        }, 2000);
      } else {
        const error = await response.json();
        showSnackbar(error.error || 'Failed to import portfolio', 'error');
      }
    } catch (error) {
      console.error('Error importing portfolio:', error);
      showSnackbar('Failed to import portfolio', 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleSaveNotifications = async () => {
    try {
      setLoading(true);
      
      const response = await fetch(`${apiUrl}/api/settings/notifications`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${user?.tokens?.accessToken || 'dev-token'}`
        },
        body: JSON.stringify(notifications)
      });

      if (response.ok) {
        showSnackbar('Notification preferences updated successfully');
      } else {
        const error = await response.json();
        showSnackbar(error.error || 'Failed to update notification preferences', 'error');
      }
    } catch (error) {
      console.error('Error saving notifications:', error);
      showSnackbar('Failed to update notification preferences', 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleSaveTheme = async () => {
    try {
      setLoading(true);
      
      const response = await fetch(`${apiUrl}/api/settings/theme`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${user?.tokens?.accessToken || 'dev-token'}`
        },
        body: JSON.stringify(themeSettings)
      });

      if (response.ok) {
        showSnackbar('Theme preferences updated successfully');
      } else {
        const error = await response.json();
        showSnackbar(error.error || 'Failed to update theme preferences', 'error');
      }
    } catch (error) {
      console.error('Error saving theme:', error);
      showSnackbar('Failed to update theme preferences', 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleChangePassword = async () => {
    // TODO: Implement password change dialog with proper form
    try {
      // For now, redirect to Cognito hosted UI for password change
      // In a full implementation, you'd show a modal with old/new password fields
      const cognitoUrl = `https://${process.env.REACT_APP_COGNITO_DOMAIN}/forgotPassword?client_id=${process.env.REACT_APP_COGNITO_CLIENT_ID}&response_type=code&scope=email+openid&redirect_uri=${encodeURIComponent(window.location.origin)}`;
      window.open(cognitoUrl, '_blank');
      showSnackbar('Password change opened in new tab', 'info');
    } catch (error) {
      console.error('Error opening password change:', error);
      showSnackbar('Error opening password change. Please try again.', 'error');
    }
  };

  const [mfaSetupDialog, setMfaSetupDialog] = useState({ open: false, qrCode: null, secret: null });
  const [mfaVerifyCode, setMfaVerifyCode] = useState('');

  const handleToggleTwoFactor = async () => {
    try {
      setLoading(true);
      
      if (user?.twoFactorEnabled) {
        // Disable 2FA
        const response = await fetch(`${apiUrl}/api/settings/two-factor/disable`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${user?.tokens?.accessToken || 'dev-token'}`
          }
        });

        if (response.ok) {
          showSnackbar('Two-factor authentication disabled', 'success');
          await loadUserSettings();
        } else {
          const error = await response.json();
          showSnackbar(error.error || 'Failed to disable two-factor authentication', 'error');
        }
      } else {
        // Enable 2FA - start setup process
        const response = await fetch(`${apiUrl}/api/settings/two-factor/enable`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${user?.tokens?.accessToken || 'dev-token'}`
          }
        });

        if (response.ok) {
          const data = await response.json();
          setMfaSetupDialog({
            open: true,
            qrCode: data.qrCodeUrl,
            secret: data.manualEntryKey
          });
          showSnackbar('Scan the QR code with your authenticator app, then enter a code to verify', 'info');
        } else {
          const error = await response.json();
          showSnackbar(error.error || 'Failed to enable two-factor authentication', 'error');
        }
      }
    } catch (error) {
      console.error('Error toggling two-factor auth:', error);
      showSnackbar('Failed to toggle two-factor authentication', 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyMfa = async () => {
    try {
      setLoading(true);
      
      const response = await fetch(`${apiUrl}/api/settings/two-factor/verify`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${user?.tokens?.accessToken || 'dev-token'}`
        },
        body: JSON.stringify({ code: mfaVerifyCode })
      });

      if (response.ok) {
        const data = await response.json();
        setMfaSetupDialog({ open: false, qrCode: null, secret: null });
        setMfaVerifyCode('');
        showSnackbar('Two-factor authentication enabled successfully!', 'success');
        
        // Show recovery codes
        if (data.recoveryCodes) {
          const codesText = data.recoveryCodes.join('\n');
          const blob = new Blob([`Recovery Codes for Financial Platform\n\nSave these codes in a safe place. You can use them to access your account if you lose your authenticator device.\n\n${codesText}\n\nGenerated: ${new Date().toLocaleDateString()}`], { type: 'text/plain' });
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = 'recovery-codes.txt';
          a.click();
          URL.revokeObjectURL(url);
        }
        
        await loadUserSettings();
      } else {
        const error = await response.json();
        showSnackbar(error.error || 'Invalid verification code', 'error');
      }
    } catch (error) {
      console.error('Error verifying MFA:', error);
      showSnackbar('Failed to verify code', 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleDownloadRecoveryCodes = async () => {
    try {
      setLoading(true);
      
      const response = await fetch(`${apiUrl}/api/settings/recovery-codes`, {
        headers: {
          'Authorization': `Bearer ${user?.tokens?.accessToken || 'dev-token'}`
        }
      });

      if (response.ok) {
        const data = await response.json();
        
        // Create and download recovery codes file
        const codesText = data.codes.join('\n');
        const blob = new Blob([codesText], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = 'recovery-codes.txt';
        link.click();
        URL.revokeObjectURL(url);
        
        showSnackbar('Recovery codes downloaded successfully', 'success');
      } else {
        const error = await response.json();
        showSnackbar(error.error || 'Failed to download recovery codes', 'error');
      }
    } catch (error) {
      console.error('Error downloading recovery codes:', error);
      showSnackbar('Failed to download recovery codes', 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteAccount = async () => {
    if (window.confirm('Are you sure you want to delete your account? This action cannot be undone.')) {
      if (window.confirm('This will permanently delete all your data. Type "DELETE" to confirm.')) {
        const userInput = window.prompt('Type "DELETE" to confirm account deletion:');
        if (userInput === 'DELETE') {
          try {
            setLoading(true);
            
            const response = await fetch(`${apiUrl}/api/user/delete-account`, {
              method: 'DELETE',
              headers: {
                'Authorization': `Bearer ${user?.tokens?.accessToken || 'dev-token'}`
              }
            });

            if (response.ok) {
              showSnackbar('Account deleted successfully', 'success');
              await logout();
              navigate('/');
            } else {
              const error = await response.json();
              showSnackbar(error.error || 'Failed to delete account', 'error');
            }
          } catch (error) {
            console.error('Error deleting account:', error);
            showSnackbar('Failed to delete account', 'error');
          } finally {
            setLoading(false);
          }
        }
      }
    }
  };

  const handleRevokeAllSessions = async () => {
    if (window.confirm('This will sign you out of all devices except this one. Continue?')) {
      try {
        setLoading(true);
        
        const response = await fetch(`${apiUrl}/api/user/revoke-sessions`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${user?.tokens?.accessToken || 'dev-token'}`
          }
        });

        if (response.ok) {
          showSnackbar('All other sessions have been revoked', 'success');
        } else {
          const error = await response.json();
          showSnackbar(error.error || 'Failed to revoke sessions', 'error');
        }
      } catch (error) {
        console.error('Error revoking sessions:', error);
        showSnackbar('Failed to revoke sessions', 'error');
      } finally {
        setLoading(false);
      }
    }
  };

  // Show loading state while authentication is being checked
  if (loading || isLoading) {
    return (
      <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
        <Box display="flex" justifyContent="center" alignItems="center" minHeight="60vh">
          <CircularProgress size={60} />
        </Box>
      </Container>
    );
  }

  // If we don't have a user object at all, show a fallback with more options
  if (!user && !isLoading) {
    return (
      <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
        <Alert 
          severity="warning" 
          action={
            <Box sx={{ display: 'flex', gap: 1 }}>
              <Button 
                color="inherit" 
                size="small" 
                onClick={() => window.location.reload()}
              >
                Refresh
              </Button>
              <Button 
                color="inherit" 
                size="small" 
                onClick={() => navigate('/login')}
              >
                Login
              </Button>
            </Box>
          }
        >
          Unable to load user information. This may be due to an expired session or authentication issue.
        </Alert>
      </Container>
    );
  }

  return (
    <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
      <Typography variant="h3" component="h1" gutterBottom>
        Account Settings
      </Typography>
      <Typography variant="subtitle1" color="text.secondary" sx={{ mb: 4 }}>
        Manage your account preferences, API connections, and security settings
      </Typography>

      <Paper sx={{ width: '100%' }}>
        <Tabs
          value={activeTab}
          onChange={handleTabChange}
          variant="scrollable"
          scrollButtons="auto"
          sx={{ borderBottom: 1, borderColor: 'divider' }}
        >
          <Tab icon={<AccountCircle />} label="Profile" />
          <Tab icon={<Api />} label="API Keys" />
          <Tab icon={<Notifications />} label="Notifications" />
          <Tab icon={<Palette />} label="Appearance" />
          <Tab icon={<Security />} label="Security" />
        </Tabs>

        {/* Profile Tab */}
        <TabPanel value={activeTab} index={0}>
          <Grid container spacing={3}>
            <Grid item xs={12} md={8}>
              <Card>
                <CardHeader title="Personal Information" />
                <CardContent>
                  <Grid container spacing={2}>
                    <Grid item xs={12} sm={6}>
                      <TextField
                        fullWidth
                        label="First Name"
                        value={profileData.firstName}
                        onChange={(e) => setProfileData({ ...profileData, firstName: e.target.value })}
                      />
                    </Grid>
                    <Grid item xs={12} sm={6}>
                      <TextField
                        fullWidth
                        label="Last Name"
                        value={profileData.lastName}
                        onChange={(e) => setProfileData({ ...profileData, lastName: e.target.value })}
                      />
                    </Grid>
                    <Grid item xs={12}>
                      <TextField
                        fullWidth
                        label="Email"
                        type="email"
                        value={profileData.email}
                        onChange={(e) => setProfileData({ ...profileData, email: e.target.value })}
                      />
                    </Grid>
                    <Grid item xs={12} sm={6}>
                      <FormControl fullWidth>
                        <InputLabel>Timezone</InputLabel>
                        <Select
                          value={profileData.timezone}
                          onChange={(e) => setProfileData({ ...profileData, timezone: e.target.value })}
                        >
                          <MenuItem value="America/New_York">Eastern Time</MenuItem>
                          <MenuItem value="America/Chicago">Central Time</MenuItem>
                          <MenuItem value="America/Denver">Mountain Time</MenuItem>
                          <MenuItem value="America/Los_Angeles">Pacific Time</MenuItem>
                          <MenuItem value="Europe/London">London</MenuItem>
                          <MenuItem value="Asia/Tokyo">Tokyo</MenuItem>
                        </Select>
                      </FormControl>
                    </Grid>
                    <Grid item xs={12} sm={6}>
                      <FormControl fullWidth>
                        <InputLabel>Currency</InputLabel>
                        <Select
                          value={profileData.currency}
                          onChange={(e) => setProfileData({ ...profileData, currency: e.target.value })}
                        >
                          <MenuItem value="USD">USD - US Dollar</MenuItem>
                          <MenuItem value="EUR">EUR - Euro</MenuItem>
                          <MenuItem value="GBP">GBP - British Pound</MenuItem>
                          <MenuItem value="CAD">CAD - Canadian Dollar</MenuItem>
                        </Select>
                      </FormControl>
                    </Grid>
                  </Grid>
                  <Box sx={{ mt: 3, display: 'flex', gap: 2 }}>
                    <Button
                      variant="contained"
                      startIcon={<Save />}
                      onClick={handleSaveProfile}
                      disabled={loading}
                    >
                      Save Changes
                    </Button>
                    <Button
                      variant="outlined"
                      startIcon={<Cancel />}
                      onClick={loadUserSettings}
                    >
                      Reset
                    </Button>
                  </Box>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} md={4}>
              <Card>
                <CardHeader title="Account Overview" />
                <CardContent>
                  <Box display="flex" alignItems="center" mb={2}>
                    <Avatar sx={{ mr: 2, width: 56, height: 56 }}>
                      {(user?.firstName?.[0] || user?.username?.[0] || 'U').toUpperCase()}
                    </Avatar>
                    <Box>
                      <Typography variant="h6">
                        {user?.firstName || 'Unknown'} {user?.lastName || 'User'}
                      </Typography>
                      <Typography color="text.secondary">
                        {user?.email || 'No email provided'}
                      </Typography>
                    </Box>
                  </Box>
                  <Divider sx={{ my: 2 }} />
                  <List dense>
                    <ListItem>
                      <ListItemText
                        primary="Account Status"
                        secondary={
                          <Chip label="Active" color="success" size="small" />
                        }
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText
                        primary="Member Since"
                        secondary={new Date(user?.createdAt || Date.now()).toLocaleDateString()}
                      />
                    </ListItem>
                  </List>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        </TabPanel>

        {/* API Keys Tab */}
        <TabPanel value={activeTab} index={1}>
          <SettingsApiKeys />
        </TabPanel>

        {/* Notifications Tab */}
        <TabPanel value={activeTab} index={2}>
          <Card>
            <CardHeader 
              title="Notification Preferences" 
              action={
                <Button
                  variant="contained"
                  startIcon={<Save />}
                  onClick={handleSaveNotifications}
                  disabled={loading}
                >
                  Save
                </Button>
              }
            />
            <CardContent>
              <Grid container spacing={3}>
                <Grid item xs={12} md={6}>
                  <Typography variant="h6" gutterBottom>
                    Delivery Methods
                  </Typography>
                  <Box sx={{ display: 'flex', flexDirection: 'column' }}>
                    <FormControlLabel
                      control={
                        <Switch
                          checked={notifications.email}
                          onChange={(e) => setNotifications({ ...notifications, email: e.target.checked })}
                        />
                      }
                      label="Email Notifications"
                    />
                    <FormControlLabel
                      control={
                        <Switch
                          checked={notifications.push}
                          onChange={(e) => setNotifications({ ...notifications, push: e.target.checked })}
                        />
                      }
                      label="Push Notifications"
                    />
                  </Box>
                </Grid>
                <Grid item xs={12} md={6}>
                  <Typography variant="h6" gutterBottom>
                    Content Types
                  </Typography>
                  <Box sx={{ display: 'flex', flexDirection: 'column' }}>
                    <FormControlLabel
                      control={
                        <Switch
                          checked={notifications.priceAlerts}
                          onChange={(e) => setNotifications({ ...notifications, priceAlerts: e.target.checked })}
                        />
                      }
                      label="Price Alerts"
                    />
                    <FormControlLabel
                      control={
                        <Switch
                          checked={notifications.portfolioUpdates}
                          onChange={(e) => setNotifications({ ...notifications, portfolioUpdates: e.target.checked })}
                        />
                      }
                      label="Portfolio Updates"
                    />
                    <FormControlLabel
                      control={
                        <Switch
                          checked={notifications.marketNews}
                          onChange={(e) => setNotifications({ ...notifications, marketNews: e.target.checked })}
                        />
                      }
                      label="Market News"
                    />
                    <FormControlLabel
                      control={
                        <Switch
                          checked={notifications.weeklyReports}
                          onChange={(e) => setNotifications({ ...notifications, weeklyReports: e.target.checked })}
                        />
                      }
                      label="Weekly Reports"
                    />
                  </Box>
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </TabPanel>

        {/* Appearance Tab */}
        <TabPanel value={activeTab} index={3}>
          <Card>
            <CardHeader 
              title="Appearance Settings" 
              action={
                <Button
                  variant="contained"
                  startIcon={<Save />}
                  onClick={handleSaveTheme}
                  disabled={loading}
                >
                  Save
                </Button>
              }
            />
            <CardContent>
              <Grid container spacing={3}>
                <Grid item xs={12} md={6}>
                  <Typography variant="h6" gutterBottom>
                    Theme Settings
                  </Typography>
                  <Box sx={{ mb: 2 }}>
                    <FormControlLabel
                      control={
                        <Switch
                          checked={themeSettings.darkMode}
                          onChange={(e) => setThemeSettings({ ...themeSettings, darkMode: e.target.checked })}
                        />
                      }
                      label="Dark Mode"
                    />
                  </Box>
                  <FormControl fullWidth sx={{ mb: 2 }}>
                    <InputLabel>Primary Color</InputLabel>
                    <Select
                      value={themeSettings.primaryColor}
                      onChange={(e) => setThemeSettings({ ...themeSettings, primaryColor: e.target.value })}
                    >
                      <MenuItem value="#1976d2">Blue</MenuItem>
                      <MenuItem value="#2e7d32">Green</MenuItem>
                      <MenuItem value="#ed6c02">Orange</MenuItem>
                      <MenuItem value="#9c27b0">Purple</MenuItem>
                      <MenuItem value="#d32f2f">Red</MenuItem>
                    </Select>
                  </FormControl>
                  <FormControl fullWidth>
                    <InputLabel>Layout Style</InputLabel>
                    <Select
                      value={themeSettings.layout}
                      onChange={(e) => setThemeSettings({ ...themeSettings, layout: e.target.value })}
                    >
                      <MenuItem value="standard">Standard</MenuItem>
                      <MenuItem value="compact">Compact</MenuItem>
                      <MenuItem value="spacious">Spacious</MenuItem>
                    </Select>
                  </FormControl>
                </Grid>
                <Grid item xs={12} md={6}>
                  <Typography variant="h6" gutterBottom>
                    Chart Settings
                  </Typography>
                  <FormControl fullWidth sx={{ mb: 2 }}>
                    <InputLabel>Default Chart Style</InputLabel>
                    <Select
                      value={themeSettings.chartStyle}
                      onChange={(e) => setThemeSettings({ ...themeSettings, chartStyle: e.target.value })}
                    >
                      <MenuItem value="candlestick">Candlestick</MenuItem>
                      <MenuItem value="line">Line</MenuItem>
                      <MenuItem value="area">Area</MenuItem>
                      <MenuItem value="bar">Bar</MenuItem>
                    </Select>
                  </FormControl>
                  <Alert severity="info">
                    Theme changes will be applied immediately. Some changes may require a page refresh.
                  </Alert>
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </TabPanel>

        {/* Security Tab */}
        <TabPanel value={activeTab} index={4}>
          <Grid container spacing={3}>
            <Grid item xs={12} md={6}>
              <Card>
                <CardHeader title="Password & Authentication" />
                <CardContent>
                  <Button 
                    variant="outlined" 
                    fullWidth 
                    sx={{ mb: 2 }}
                    startIcon={<Security />}
                    onClick={handleChangePassword}
                    disabled={loading}
                  >
                    Change Password
                  </Button>
                  <Button 
                    variant="outlined" 
                    fullWidth 
                    sx={{ mb: 2 }}
                    startIcon={<Security />}
                    onClick={handleToggleTwoFactor}
                    disabled={loading}
                  >
                    {user?.twoFactorEnabled ? 'Disable' : 'Enable'} Two-Factor Authentication
                  </Button>
                  <Button 
                    variant="outlined" 
                    fullWidth
                    startIcon={<Download />}
                    onClick={handleDownloadRecoveryCodes}
                    disabled={loading || !user?.twoFactorEnabled}
                  >
                    Download Recovery Codes
                  </Button>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} md={6}>
              <Card>
                <CardHeader title="Account Actions" />
                <CardContent>
                  <Button
                    variant="outlined"
                    fullWidth
                    onClick={logout}
                    sx={{ mb: 2 }}
                    disabled={loading}
                  >
                    Sign Out
                  </Button>
                  <Button
                    variant="outlined"
                    color="error"
                    fullWidth
                    startIcon={<Warning />}
                    onClick={handleDeleteAccount}
                    disabled={loading}
                  >
                    Delete Account
                  </Button>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12}>
              <Card>
                <CardHeader title="Active Sessions" />
                <CardContent>
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                    Manage your active login sessions across different devices.
                  </Typography>
                  <List>
                    <ListItem>
                      <ListItemIcon>
                        <CheckCircle color="success" />
                      </ListItemIcon>
                      <ListItemText
                        primary="Current Session"
                        secondary={`${navigator.userAgent.includes('Chrome') ? 'Chrome' : 'Browser'} on ${navigator.platform} - ${new Date().toLocaleString()}`}
                      />
                      <ListItemSecondaryAction>
                        <Chip label="Current" color="primary" size="small" />
                      </ListItemSecondaryAction>
                    </ListItem>
                  </List>
                  <Button
                    variant="outlined"
                    color="warning"
                    startIcon={<Security />}
                    onClick={handleRevokeAllSessions}
                    disabled={loading}
                  >
                    Revoke All Other Sessions
                  </Button>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        </TabPanel>
      </Paper>

      {/* Add API Key Dialog */}
      <Dialog
        open={addApiKeyDialog}
        onClose={() => setAddApiKeyDialog(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Add Broker API Key</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12}>
              <FormControl fullWidth>
                <InputLabel>Broker</InputLabel>
                <Select
                  value={newApiKey.brokerName}
                  onChange={(e) => setNewApiKey({ ...newApiKey, brokerName: e.target.value })}
                >
                  <MenuItem value="alpaca">Alpaca</MenuItem>
                  <MenuItem value="robinhood">Robinhood</MenuItem>
                  <MenuItem value="td_ameritrade">TD Ameritrade</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="API Key"
                type={showApiKeys.apiKey ? 'text' : 'password'}
                value={newApiKey.apiKey}
                onChange={(e) => setNewApiKey({ ...newApiKey, apiKey: e.target.value })}
                InputProps={{
                  endAdornment: (
                    <IconButton
                      onClick={() => setShowApiKeys({ ...showApiKeys, apiKey: !showApiKeys.apiKey })}
                    >
                      {showApiKeys.apiKey ? <VisibilityOff /> : <Visibility />}
                    </IconButton>
                  )
                }}
              />
            </Grid>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="API Secret"
                type={showApiKeys.apiSecret ? 'text' : 'password'}
                value={newApiKey.apiSecret}
                onChange={(e) => setNewApiKey({ ...newApiKey, apiSecret: e.target.value })}
                InputProps={{
                  endAdornment: (
                    <IconButton
                      onClick={() => setShowApiKeys({ ...showApiKeys, apiSecret: !showApiKeys.apiSecret })}
                    >
                      {showApiKeys.apiSecret ? <VisibilityOff /> : <Visibility />}
                    </IconButton>
                  )
                }}
              />
            </Grid>
            <Grid item xs={12}>
              <FormControlLabel
                control={
                  <Switch
                    checked={newApiKey.sandbox}
                    onChange={(e) => setNewApiKey({ ...newApiKey, sandbox: e.target.checked })}
                  />
                }
                label="Sandbox Environment (recommended for testing)"
              />
            </Grid>
          </Grid>
          <Alert severity="info" sx={{ mt: 2 }}>
            API keys are encrypted and stored securely. We recommend starting with sandbox mode for testing.
          </Alert>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAddApiKeyDialog(false)}>Cancel</Button>
          <Button
            onClick={handleAddApiKey}
            variant="contained"
            disabled={!newApiKey.brokerName || !newApiKey.apiKey || loading}
          >
            Add API Key
          </Button>
        </DialogActions>
      </Dialog>

      {/* MFA Setup Dialog */}
      <Dialog open={mfaSetupDialog.open} onClose={() => setMfaSetupDialog({ open: false, qrCode: null, secret: null })} maxWidth="sm" fullWidth>
        <DialogTitle>
          <Box display="flex" alignItems="center" gap={1}>
            <Security color="primary" />
            Setup Two-Factor Authentication
          </Box>
        </DialogTitle>
        <DialogContent>
          <Alert severity="info" sx={{ mb: 3 }}>
            Two-factor authentication adds an extra layer of security to your account and is required for managing API keys.
          </Alert>
          
          {mfaSetupDialog.qrCode && (
            <Box textAlign="center" mb={3}>
              <Typography variant="h6" gutterBottom>
                Step 1: Scan QR Code
              </Typography>
              <img 
                src={mfaSetupDialog.qrCode} 
                alt="2FA QR Code" 
                style={{ maxWidth: '200px', height: 'auto' }}
              />
              <Typography variant="body2" color="textSecondary" mt={1}>
                Scan this QR code with your authenticator app (Google Authenticator, Authy, etc.)
              </Typography>
            </Box>
          )}
          
          {mfaSetupDialog.secret && (
            <Box mb={3}>
              <Typography variant="h6" gutterBottom>
                Step 2: Manual Entry (if needed)
              </Typography>
              <TextField
                label="Manual Entry Key"
                value={mfaSetupDialog.secret}
                fullWidth
                InputProps={{
                  readOnly: true,
                  endAdornment: (
                    <IconButton
                      onClick={() => navigator.clipboard.writeText(mfaSetupDialog.secret)}
                      size="small"
                    >
                      <ContentCopy />
                    </IconButton>
                  )
                }}
                sx={{ mb: 2 }}
              />
              <Typography variant="body2" color="textSecondary">
                Enter this key manually in your authenticator app if you can't scan the QR code.
              </Typography>
            </Box>
          )}
          
          <Box>
            <Typography variant="h6" gutterBottom>
              Step 3: Verify Setup
            </Typography>
            <TextField
              label="Verification Code"
              value={mfaVerifyCode}
              onChange={(e) => setMfaVerifyCode(e.target.value)}
              fullWidth
              placeholder="Enter 6-digit code from your authenticator app"
              inputProps={{ maxLength: 6, pattern: '[0-9]*' }}
            />
            <Typography variant="body2" color="textSecondary" mt={1}>
              Enter the 6-digit code shown in your authenticator app to complete setup.
            </Typography>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button 
            onClick={() => setMfaSetupDialog({ open: false, qrCode: null, secret: null })}
            disabled={loading}
          >
            Cancel
          </Button>
          <Button
            onClick={handleVerifyMfa}
            variant="contained"
            disabled={!mfaVerifyCode || mfaVerifyCode.length !== 6 || loading}
          >
            Verify & Enable 2FA
          </Button>
        </DialogActions>
      </Dialog>

      {/* Snackbar for notifications */}
      <Snackbar
        open={snackbar.open}
        autoHideDuration={6000}
        onClose={() => setSnackbar({ ...snackbar, open: false })}
      >
        <Alert
          onClose={() => setSnackbar({ ...snackbar, open: false })}
          severity={snackbar.severity}
          sx={{ width: '100%' }}
        >
          {snackbar.message}
        </Alert>
      </Snackbar>
    </Container>
  );
};

export default Settings;