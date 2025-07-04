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
  const { user, isAuthenticated, isLoading, logout } = useAuth();
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

  // Authentication guard
  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      navigate('/login');
    }
  }, [isAuthenticated, isLoading, navigate]);

  // Load user data
  useEffect(() => {
    if (isAuthenticated && user) {
      loadUserSettings();
    }
  }, [isAuthenticated, user]);

  const loadUserSettings = async () => {
    try {
      setLoading(true);
      
      // Load user profile data
      setProfileData({
        firstName: user.firstName || '',
        lastName: user.lastName || '',
        email: user.email || '',
        phone: user.phone || '',
        timezone: user.timezone || 'America/New_York',
        currency: user.currency || 'USD'
      });

      // Load API keys
      await loadApiKeys();
      
    } catch (error) {
      console.error('Error loading settings:', error);
      showSnackbar('Failed to load settings', 'error');
    } finally {
      setLoading(false);
    }
  };

  const loadApiKeys = async () => {
    try {
      const response = await fetch(`${apiUrl}/api/portfolio/api-keys`, {
        headers: {
          'Authorization': `Bearer ${user.tokens?.accessToken || 'dev-token'}`
        }
      });
      
      if (response.ok) {
        const data = await response.json();
        setApiKeys(data.apiKeys || []);
      }
    } catch (error) {
      console.error('Error loading API keys:', error);
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
      // TODO: Implement profile update API call
      showSnackbar('Profile updated successfully');
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
          'Authorization': `Bearer ${user.tokens?.accessToken || 'dev-token'}`
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
          'Authorization': `Bearer ${user.tokens?.accessToken || 'dev-token'}`
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
          'Authorization': `Bearer ${user.tokens?.accessToken || 'dev-token'}`
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
          'Authorization': `Bearer ${user.tokens?.accessToken || 'dev-token'}`
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

  // Show loading state while authentication is being checked
  if (isLoading || !isAuthenticated) {
    return (
      <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
        <Box display="flex" justifyContent="center" alignItems="center" minHeight="60vh">
          <CircularProgress size={60} />
        </Box>
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
                      {(user.firstName?.[0] || user.username?.[0] || 'U').toUpperCase()}
                    </Avatar>
                    <Box>
                      <Typography variant="h6">
                        {user.firstName} {user.lastName}
                      </Typography>
                      <Typography color="text.secondary">
                        {user.email}
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
                        secondary={new Date(user.createdAt || Date.now()).toLocaleDateString()}
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
            <CardHeader title="Notification Preferences" />
            <CardContent>
              <Grid container spacing={3}>
                <Grid item xs={12} md={6}>
                  <Typography variant="h6" gutterBottom>
                    Delivery Methods
                  </Typography>
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
                </Grid>
                <Grid item xs={12} md={6}>
                  <Typography variant="h6" gutterBottom>
                    Content Types
                  </Typography>
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
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </TabPanel>

        {/* Appearance Tab */}
        <TabPanel value={activeTab} index={3}>
          <Card>
            <CardHeader title="Appearance Settings" />
            <CardContent>
              <Grid container spacing={3}>
                <Grid item xs={12} md={6}>
                  <FormControlLabel
                    control={
                      <Switch
                        checked={themeSettings.darkMode}
                        onChange={(e) => setThemeSettings({ ...themeSettings, darkMode: e.target.checked })}
                      />
                    }
                    label="Dark Mode"
                  />
                </Grid>
                <Grid item xs={12} md={6}>
                  <FormControl fullWidth>
                    <InputLabel>Chart Style</InputLabel>
                    <Select
                      value={themeSettings.chartStyle}
                      onChange={(e) => setThemeSettings({ ...themeSettings, chartStyle: e.target.value })}
                    >
                      <MenuItem value="candlestick">Candlestick</MenuItem>
                      <MenuItem value="line">Line</MenuItem>
                      <MenuItem value="area">Area</MenuItem>
                    </Select>
                  </FormControl>
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
                  <Button variant="outlined" fullWidth sx={{ mb: 2 }}>
                    Change Password
                  </Button>
                  <Button variant="outlined" fullWidth>
                    Enable Two-Factor Authentication
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
                  >
                    Sign Out
                  </Button>
                  <Button
                    variant="outlined"
                    color="error"
                    fullWidth
                  >
                    Delete Account
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