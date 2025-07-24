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
  MonetizationOn
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
  const { user, tokens, isAuthenticated, isLoading, logout, checkAuthState, retryCount, maxRetries } = useAuth();
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

  // Helper function to get authentication headers
  const getAuthHeaders = () => {
    const token = tokens?.accessToken || 
                 localStorage.getItem('accessToken') || 
                 localStorage.getItem('authToken') || 
                 localStorage.getItem('token');
    
    const headers = {
      'Content-Type': 'application/json'
    };
    
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
    
    return headers;
  };

  // Authentication guard - disabled
  // useEffect(() => {
  //   if (!isLoading && !isAuthenticated) {
  //     navigate('/login');
  //   }
  // }, [isAuthenticated, isLoading, navigate]);

  // Load user data with circuit breaker
  useEffect(() => {
    if (isAuthenticated && user) {
      loadUserSettings();
    } else if (!isLoading && !user && !isAuthenticated && retryCount < maxRetries) {
      // Only retry if we haven't exceeded the limit
      console.log(`Settings: No user found, attempting to re-check authentication (${retryCount}/${maxRetries})`);
      checkAuthState();
    } else if (retryCount >= maxRetries) {
      console.warn('🛑 Settings: Auth retry limit reached, stopping attempts');
    }
  }, [isAuthenticated, user, isLoading, retryCount, maxRetries]);

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
        const notifResponse = await fetch(`${apiUrl}/api/user/notifications`, {
          headers: getAuthHeaders()
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
        const themeResponse = await fetch(`${apiUrl}/api/user/theme`, {
          headers: getAuthHeaders()
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
      const response = await fetch(`${apiUrl}/api/portfolio/api/api-keys`, {
        headers: getAuthHeaders()
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
      
      const response = await fetch(`${apiUrl}/api/user/profile`, {
        method: 'PUT',
        headers: getAuthHeaders(),
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
      
      const response = await fetch(`${apiUrl}/api/portfolio/api/api-keys`, {
        method: 'POST',
        headers: getAuthHeaders(),
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
      const response = await fetch(`${apiUrl}/api/portfolio/api/api-keys/${brokerName}`, {
        method: 'DELETE',
        headers: getAuthHeaders()
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
        headers: getAuthHeaders()
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
        headers: getAuthHeaders()
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
      
      const response = await fetch(`${apiUrl}/api/user/notifications`, {
        method: 'PUT',
        headers: getAuthHeaders(),
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
      
      const response = await fetch(`${apiUrl}/api/user/theme`, {
        method: 'PUT',
        headers: getAuthHeaders(),
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
    // Create a simple password change dialog
    const result = await new Promise(resolve => {
      let currentPassword = '';
      let newPassword = '';
      let confirmPassword = '';

      const dialog = document.createElement('div');
      dialog.innerHTML = `
        <div style="position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); display: flex; justify-content: center; align-items: center; z-index: 9999;">
          <div style="background: white; padding: 24px; border-radius: 8px; min-width: 400px; max-width: 500px;">
            <h3 style="margin: 0 0 16px 0;">Change Password</h3>
            <div style="margin-bottom: 16px;">
              <label style="display: block; margin-bottom: 4px;">Current Password:</label>
              <input type="password" id="currentPassword" style="width: 100%; padding: 8px; border: 1px solid #ccc; border-radius: 4px;">
            </div>
            <div style="margin-bottom: 16px;">
              <label style="display: block; margin-bottom: 4px;">New Password:</label>
              <input type="password" id="newPassword" style="width: 100%; padding: 8px; border: 1px solid #ccc; border-radius: 4px;">
              <small style="color: #666;">Must be at least 8 characters with uppercase, lowercase, number, and special character</small>
            </div>
            <div style="margin-bottom: 24px;">
              <label style="display: block; margin-bottom: 4px;">Confirm New Password:</label>
              <input type="password" id="confirmPassword" style="width: 100%; padding: 8px; border: 1px solid #ccc; border-radius: 4px;">
            </div>
            <div style="display: flex; gap: 8px; justify-content: flex-end;">
              <button id="cancelBtn" style="padding: 8px 16px; border: 1px solid #ccc; background: white; border-radius: 4px; cursor: pointer;">Cancel</button>
              <button id="changeBtn" style="padding: 8px 16px; border: none; background: #1976d2; color: white; border-radius: 4px; cursor: pointer;">Change Password</button>
            </div>
          </div>
        </div>
      `;

      document.body.appendChild(dialog);

      const handleSubmit = () => {
        currentPassword = document.getElementById('currentPassword').value;
        newPassword = document.getElementById('newPassword').value;
        confirmPassword = document.getElementById('confirmPassword').value;

        if (!currentPassword || !newPassword || !confirmPassword) {
          alert('Please fill in all fields');
          return;
        }

        if (newPassword !== confirmPassword) {
          alert('New passwords do not match');
          return;
        }

        if (newPassword.length < 8) {
          alert('New password must be at least 8 characters long');
          return;
        }

        document.body.removeChild(dialog);
        resolve({ currentPassword, newPassword });
      };

      const handleCancel = () => {
        document.body.removeChild(dialog);
        resolve(null);
      };

      document.getElementById('changeBtn').onclick = handleSubmit;
      document.getElementById('cancelBtn').onclick = handleCancel;
      document.getElementById('currentPassword').focus();

      // Handle Enter key
      dialog.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') handleSubmit();
        if (e.key === 'Escape') handleCancel();
      });
    });

    if (!result) return; // User cancelled

    try {
      setLoading(true);
      
      // Generate a proper development token for testing
      const generateDevToken = () => {
        const payload = {
          sub: 'dev-user',
          email: 'dev@example.com',
          username: 'dev-user',
          'custom:role': 'admin',
          'cognito:groups': ['admin'],
          given_name: 'Dev',
          family_name: 'User',
          email_verified: true,
          iat: Math.floor(Date.now() / 1000),
          exp: Math.floor(Date.now() / 1000) + (24 * 60 * 60), // 24 hours
          aud: 'development-client',
          iss: 'https://cognito-idp.us-east-1.amazonaws.com/development'
        };
        
        // Create a simple JWT-like token for development
        const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }));
        const payloadStr = btoa(JSON.stringify(payload));
        const signature = btoa('dev-signature');
        return `${header}.${payloadStr}.${signature}`;
      };

      const response = await fetch(`${apiUrl}/api/user/change-password`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          currentPassword: result.currentPassword,
          newPassword: result.newPassword
        })
      });

      if (response.ok) {
        showSnackbar('Password changed successfully', 'success');
      } else {
        const error = await response.json();
        showSnackbar(error.error || 'Failed to change password', 'error');
      }
    } catch (error) {
      console.error('Error changing password:', error);
      showSnackbar('Failed to change password', 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleToggleTwoFactor = async () => {
    try {
      setLoading(true);
      
      const action = user?.twoFactorEnabled ? 'disable' : 'enable';
      const response = await fetch(`${apiUrl}/api/user/two-factor/${action}`, {
        method: 'POST',
        headers: getAuthHeaders()
      });

      if (response.ok) {
        const data = await response.json();
        showSnackbar(
          user?.twoFactorEnabled 
            ? 'Two-factor authentication disabled' 
            : 'Two-factor authentication enabled'
        );
        
        // Show QR code or setup instructions if enabling
        if (!user?.twoFactorEnabled && data.qrCode) {
          showSnackbar('Please scan the QR code with your authenticator app', 'info');
        }
        
        // Refresh user settings
        await loadUserSettings();
      } else {
        const error = await response.json();
        showSnackbar(error.error || 'Failed to toggle two-factor authentication', 'error');
      }
    } catch (error) {
      console.error('Error toggling two-factor auth:', error);
      showSnackbar('Failed to toggle two-factor authentication', 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleDownloadRecoveryCodes = async () => {
    try {
      setLoading(true);
      
      const response = await fetch(`${apiUrl}/api/user/recovery-codes`, {
        headers: getAuthHeaders()
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
              headers: getAuthHeaders()
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
          headers: getAuthHeaders()
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
                    onClick={async () => {
                      try {
                        setLoading(true);
                        // Call backend logout first
                        await fetch(`${apiUrl}/api/user/logout`, {
                          method: 'POST',
                          headers: getAuthHeaders()
                        });
                        // Then call frontend logout
                        await logout();
                        navigate('/login');
                      } catch (error) {
                        console.error('Logout error:', error);
                        // Still logout locally even if backend fails
                        await logout();
                        navigate('/login');
                      } finally {
                        setLoading(false);
                      }
                    }}
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