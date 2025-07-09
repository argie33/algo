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
  Snackbar,
  Divider,
  Tabs,
  Tab,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  IconButton,
  Tooltip,
  Chip,
  List,
  ListItem,
  ListItemText,
  ListItemSecondaryAction,
  Paper,
  InputAdornment,
  Accordion,
  AccordionSummary,
  AccordionDetails
} from '@mui/material';
import {
  Save,
  Settings,
  Security,
  Notifications,
  Trading,
  Visibility,
  VisibilityOff,
  Delete,
  Edit,
  Add,
  Warning,
  CheckCircle,
  ExpandMore,
  VpnKey,
  AccountBalance,
  TrendingUp,
  Schedule,
  ColorLens,
  Language,
  CloudSync,
  Assessment
} from '@mui/icons-material';

const SettingsManager = () => {
  const [activeTab, setActiveTab] = useState(0);
  const [settings, setSettings] = useState({
    // API Keys
    apiKeys: {
      alpaca: {
        keyId: '',
        secretKey: '',
        paperTrading: true,
        enabled: false
      },
      polygon: {
        apiKey: '',
        enabled: false
      },
      finnhub: {
        apiKey: '',
        enabled: false
      }
    },
    // Trading Preferences
    trading: {
      defaultOrderType: 'market',
      defaultTimeInForce: 'day',
      enableAfterHours: false,
      maxPositionSize: 0.05,
      maxDailyLoss: 0.02,
      autoStopLoss: true,
      defaultStopLoss: 0.02,
      autoTakeProfit: true,
      defaultTakeProfit: 0.04,
      riskPerTrade: 0.01,
      maxOpenPositions: 10
    },
    // Notifications
    notifications: {
      browser: true,
      email: false,
      sms: false,
      priceAlerts: true,
      tradeExecutions: true,
      portfolioUpdates: true,
      riskAlerts: true,
      systemUpdates: false
    },
    // Display Preferences
    display: {
      theme: 'light',
      currency: 'USD',
      dateFormat: 'MM/DD/YYYY',
      timeFormat: '12h',
      compactMode: false,
      showAdvancedMetrics: false,
      defaultChartType: 'candlestick',
      autoRefresh: true,
      refreshInterval: 30
    },
    // Security
    security: {
      twoFactorAuth: false,
      sessionTimeout: 30,
      requirePasswordForTrades: false,
      ipWhitelist: [],
      auditLog: true
    }
  });

  const [showPasswords, setShowPasswords] = useState({});
  const [snackbar, setSnackbar] = useState({ open: false, message: '', severity: 'success' });
  const [testingConnection, setTestingConnection] = useState(false);
  const [connectionResults, setConnectionResults] = useState({});
  const [unsavedChanges, setUnsavedChanges] = useState(false);

  // Load settings from localStorage on mount
  useEffect(() => {
    const savedSettings = localStorage.getItem('app_settings');
    if (savedSettings) {
      try {
        const parsed = JSON.parse(savedSettings);
        setSettings(prev => ({ ...prev, ...parsed }));
      } catch (error) {
        console.error('Error loading settings:', error);
      }
    }
  }, []);

  // Save settings to localStorage
  const saveSettings = () => {
    try {
      localStorage.setItem('app_settings', JSON.stringify(settings));
      setUnsavedChanges(false);
      setSnackbar({ open: true, message: 'Settings saved successfully', severity: 'success' });
    } catch (error) {
      console.error('Error saving settings:', error);
      setSnackbar({ open: true, message: 'Error saving settings', severity: 'error' });
    }
  };

  // Update settings and mark as unsaved
  const updateSettings = (section, key, value) => {
    setSettings(prev => ({
      ...prev,
      [section]: {
        ...prev[section],
        [key]: value
      }
    }));
    setUnsavedChanges(true);
  };

  // Test API connection
  const testConnection = async (provider) => {
    setTestingConnection(true);
    
    try {
      // Simulate API test
      await new Promise(resolve => setTimeout(resolve, 2000));
      
      // Mock success/failure
      const isSuccess = Math.random() > 0.3;
      setConnectionResults(prev => ({
        ...prev,
        [provider]: {
          status: isSuccess ? 'success' : 'error',
          message: isSuccess ? 'Connection successful' : 'Invalid API credentials'
        }
      }));
    } catch (error) {
      setConnectionResults(prev => ({
        ...prev,
        [provider]: {
          status: 'error',
          message: 'Connection failed'
        }
      }));
    } finally {
      setTestingConnection(false);
    }
  };

  // Reset settings to defaults
  const resetSettings = () => {
    if (window.confirm('Are you sure you want to reset all settings to defaults?')) {
      localStorage.removeItem('app_settings');
      window.location.reload();
    }
  };

  // Export settings
  const exportSettings = () => {
    const dataStr = JSON.stringify(settings, null, 2);
    const dataUri = 'data:application/json;charset=utf-8,'+ encodeURIComponent(dataStr);
    
    const exportFileDefaultName = 'trading_settings.json';
    const linkElement = document.createElement('a');
    linkElement.setAttribute('href', dataUri);
    linkElement.setAttribute('download', exportFileDefaultName);
    linkElement.click();
  };

  // Import settings
  const importSettings = (event) => {
    const file = event.target.files[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = (e) => {
        try {
          const importedSettings = JSON.parse(e.target.result);
          setSettings(prev => ({ ...prev, ...importedSettings }));
          setUnsavedChanges(true);
          setSnackbar({ open: true, message: 'Settings imported successfully', severity: 'success' });
        } catch (error) {
          setSnackbar({ open: true, message: 'Error importing settings', severity: 'error' });
        }
      };
      reader.readAsText(file);
    }
  };

  const renderAPIKeysTab = () => (
    <Grid container spacing={3}>
      {/* Alpaca */}
      <Grid item xs={12}>
        <Card>
          <CardContent>
            <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
              <AccountBalance sx={{ mr: 1 }} />
              <Typography variant="h6">Alpaca Trading</Typography>
              <Chip 
                label={settings.apiKeys.alpaca.enabled ? 'Connected' : 'Disconnected'} 
                color={settings.apiKeys.alpaca.enabled ? 'success' : 'default'}
                size="small"
                sx={{ ml: 2 }}
              />
            </Box>
            
            <Grid container spacing={2}>
              <Grid item xs={12} md={6}>
                <TextField
                  fullWidth
                  label="API Key ID"
                  type={showPasswords.alpacaKey ? 'text' : 'password'}
                  value={settings.apiKeys.alpaca.keyId}
                  onChange={(e) => updateSettings('apiKeys', 'alpaca', {
                    ...settings.apiKeys.alpaca,
                    keyId: e.target.value
                  })}
                  InputProps={{
                    endAdornment: (
                      <InputAdornment position="end">
                        <IconButton
                          onClick={() => setShowPasswords(prev => ({
                            ...prev,
                            alpacaKey: !prev.alpacaKey
                          }))}
                        >
                          {showPasswords.alpacaKey ? <VisibilityOff /> : <Visibility />}
                        </IconButton>
                      </InputAdornment>
                    )
                  }}
                />
              </Grid>
              <Grid item xs={12} md={6}>
                <TextField
                  fullWidth
                  label="Secret Key"
                  type={showPasswords.alpacaSecret ? 'text' : 'password'}
                  value={settings.apiKeys.alpaca.secretKey}
                  onChange={(e) => updateSettings('apiKeys', 'alpaca', {
                    ...settings.apiKeys.alpaca,
                    secretKey: e.target.value
                  })}
                  InputProps={{
                    endAdornment: (
                      <InputAdornment position="end">
                        <IconButton
                          onClick={() => setShowPasswords(prev => ({
                            ...prev,
                            alpacaSecret: !prev.alpacaSecret
                          }))}
                        >
                          {showPasswords.alpacaSecret ? <VisibilityOff /> : <Visibility />}
                        </IconButton>
                      </InputAdornment>
                    )
                  }}
                />
              </Grid>
              <Grid item xs={12}>
                <Box sx={{ display: 'flex', gap: 2, alignItems: 'center' }}>
                  <FormControlLabel
                    control={
                      <Switch
                        checked={settings.apiKeys.alpaca.paperTrading}
                        onChange={(e) => updateSettings('apiKeys', 'alpaca', {
                          ...settings.apiKeys.alpaca,
                          paperTrading: e.target.checked
                        })}
                      />
                    }
                    label="Paper Trading"
                  />
                  <FormControlLabel
                    control={
                      <Switch
                        checked={settings.apiKeys.alpaca.enabled}
                        onChange={(e) => updateSettings('apiKeys', 'alpaca', {
                          ...settings.apiKeys.alpaca,
                          enabled: e.target.checked
                        })}
                      />
                    }
                    label="Enabled"
                  />
                  <Button
                    variant="outlined"
                    onClick={() => testConnection('alpaca')}
                    disabled={testingConnection}
                  >
                    Test Connection
                  </Button>
                </Box>
              </Grid>
            </Grid>
            
            {connectionResults.alpaca && (
              <Alert severity={connectionResults.alpaca.status} sx={{ mt: 2 }}>
                {connectionResults.alpaca.message}
              </Alert>
            )}
          </CardContent>
        </Card>
      </Grid>

      {/* Polygon */}
      <Grid item xs={12}>
        <Card>
          <CardContent>
            <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
              <Assessment sx={{ mr: 1 }} />
              <Typography variant="h6">Polygon Market Data</Typography>
              <Chip 
                label={settings.apiKeys.polygon.enabled ? 'Connected' : 'Disconnected'} 
                color={settings.apiKeys.polygon.enabled ? 'success' : 'default'}
                size="small"
                sx={{ ml: 2 }}
              />
            </Box>
            
            <Grid container spacing={2}>
              <Grid item xs={12} md={8}>
                <TextField
                  fullWidth
                  label="API Key"
                  type={showPasswords.polygonKey ? 'text' : 'password'}
                  value={settings.apiKeys.polygon.apiKey}
                  onChange={(e) => updateSettings('apiKeys', 'polygon', {
                    ...settings.apiKeys.polygon,
                    apiKey: e.target.value
                  })}
                  InputProps={{
                    endAdornment: (
                      <InputAdornment position="end">
                        <IconButton
                          onClick={() => setShowPasswords(prev => ({
                            ...prev,
                            polygonKey: !prev.polygonKey
                          }))}
                        >
                          {showPasswords.polygonKey ? <VisibilityOff /> : <Visibility />}
                        </IconButton>
                      </InputAdornment>
                    )
                  }}
                />
              </Grid>
              <Grid item xs={12} md={4}>
                <Box sx={{ display: 'flex', gap: 2, alignItems: 'center' }}>
                  <FormControlLabel
                    control={
                      <Switch
                        checked={settings.apiKeys.polygon.enabled}
                        onChange={(e) => updateSettings('apiKeys', 'polygon', {
                          ...settings.apiKeys.polygon,
                          enabled: e.target.checked
                        })}
                      />
                    }
                    label="Enabled"
                  />
                  <Button
                    variant="outlined"
                    onClick={() => testConnection('polygon')}
                    disabled={testingConnection}
                  >
                    Test
                  </Button>
                </Box>
              </Grid>
            </Grid>
            
            {connectionResults.polygon && (
              <Alert severity={connectionResults.polygon.status} sx={{ mt: 2 }}>
                {connectionResults.polygon.message}
              </Alert>
            )}
          </CardContent>
        </Card>
      </Grid>
    </Grid>
  );

  const renderTradingTab = () => (
    <Grid container spacing={3}>
      <Grid item xs={12} md={6}>
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              <TrendingUp sx={{ mr: 1, verticalAlign: 'middle' }} />
              Order Defaults
            </Typography>
            
            <Grid container spacing={2}>
              <Grid item xs={12}>
                <FormControl fullWidth>
                  <InputLabel>Default Order Type</InputLabel>
                  <Select
                    value={settings.trading.defaultOrderType}
                    onChange={(e) => updateSettings('trading', 'defaultOrderType', e.target.value)}
                  >
                    <MenuItem value="market">Market</MenuItem>
                    <MenuItem value="limit">Limit</MenuItem>
                    <MenuItem value="stop">Stop</MenuItem>
                    <MenuItem value="stop_limit">Stop Limit</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
              
              <Grid item xs={12}>
                <FormControl fullWidth>
                  <InputLabel>Time in Force</InputLabel>
                  <Select
                    value={settings.trading.defaultTimeInForce}
                    onChange={(e) => updateSettings('trading', 'defaultTimeInForce', e.target.value)}
                  >
                    <MenuItem value="day">Day</MenuItem>
                    <MenuItem value="gtc">Good Till Canceled</MenuItem>
                    <MenuItem value="ioc">Immediate or Cancel</MenuItem>
                    <MenuItem value="fok">Fill or Kill</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
              
              <Grid item xs={12}>
                <FormControlLabel
                  control={
                    <Switch
                      checked={settings.trading.enableAfterHours}
                      onChange={(e) => updateSettings('trading', 'enableAfterHours', e.target.checked)}
                    />
                  }
                  label="Enable After Hours Trading"
                />
              </Grid>
            </Grid>
          </CardContent>
        </Card>
      </Grid>

      <Grid item xs={12} md={6}>
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              <Security sx={{ mr: 1, verticalAlign: 'middle' }} />
              Risk Management
            </Typography>
            
            <Grid container spacing={2}>
              <Grid item xs={12}>
                <TextField
                  fullWidth
                  label="Max Position Size (%)"
                  type="number"
                  value={settings.trading.maxPositionSize * 100}
                  onChange={(e) => updateSettings('trading', 'maxPositionSize', e.target.value / 100)}
                  InputProps={{
                    endAdornment: <InputAdornment position="end">%</InputAdornment>
                  }}
                />
              </Grid>
              
              <Grid item xs={12}>
                <TextField
                  fullWidth
                  label="Max Daily Loss (%)"
                  type="number"
                  value={settings.trading.maxDailyLoss * 100}
                  onChange={(e) => updateSettings('trading', 'maxDailyLoss', e.target.value / 100)}
                  InputProps={{
                    endAdornment: <InputAdornment position="end">%</InputAdornment>
                  }}
                />
              </Grid>
              
              <Grid item xs={12}>
                <TextField
                  fullWidth
                  label="Risk Per Trade (%)"
                  type="number"
                  value={settings.trading.riskPerTrade * 100}
                  onChange={(e) => updateSettings('trading', 'riskPerTrade', e.target.value / 100)}
                  InputProps={{
                    endAdornment: <InputAdornment position="end">%</InputAdornment>
                  }}
                />
              </Grid>
              
              <Grid item xs={12}>
                <TextField
                  fullWidth
                  label="Max Open Positions"
                  type="number"
                  value={settings.trading.maxOpenPositions}
                  onChange={(e) => updateSettings('trading', 'maxOpenPositions', parseInt(e.target.value))}
                />
              </Grid>
            </Grid>
          </CardContent>
        </Card>
      </Grid>

      <Grid item xs={12}>
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Automatic Stop Loss & Take Profit
            </Typography>
            
            <Grid container spacing={2}>
              <Grid item xs={12} md={6}>
                <FormControlLabel
                  control={
                    <Switch
                      checked={settings.trading.autoStopLoss}
                      onChange={(e) => updateSettings('trading', 'autoStopLoss', e.target.checked)}
                    />
                  }
                  label="Auto Stop Loss"
                />
                {settings.trading.autoStopLoss && (
                  <TextField
                    fullWidth
                    label="Default Stop Loss (%)"
                    type="number"
                    value={settings.trading.defaultStopLoss * 100}
                    onChange={(e) => updateSettings('trading', 'defaultStopLoss', e.target.value / 100)}
                    InputProps={{
                      endAdornment: <InputAdornment position="end">%</InputAdornment>
                    }}
                    sx={{ mt: 1 }}
                  />
                )}
              </Grid>
              
              <Grid item xs={12} md={6}>
                <FormControlLabel
                  control={
                    <Switch
                      checked={settings.trading.autoTakeProfit}
                      onChange={(e) => updateSettings('trading', 'autoTakeProfit', e.target.checked)}
                    />
                  }
                  label="Auto Take Profit"
                />
                {settings.trading.autoTakeProfit && (
                  <TextField
                    fullWidth
                    label="Default Take Profit (%)"
                    type="number"
                    value={settings.trading.defaultTakeProfit * 100}
                    onChange={(e) => updateSettings('trading', 'defaultTakeProfit', e.target.value / 100)}
                    InputProps={{
                      endAdornment: <InputAdornment position="end">%</InputAdornment>
                    }}
                    sx={{ mt: 1 }}
                  />
                )}
              </Grid>
            </Grid>
          </CardContent>
        </Card>
      </Grid>
    </Grid>
  );

  const renderNotificationsTab = () => (
    <Grid container spacing={3}>
      <Grid item xs={12}>
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              <Notifications sx={{ mr: 1, verticalAlign: 'middle' }} />
              Notification Preferences
            </Typography>
            
            <Grid container spacing={2}>
              <Grid item xs={12} md={4}>
                <Typography variant="subtitle1" gutterBottom>Methods</Typography>
                <FormControlLabel
                  control={
                    <Switch
                      checked={settings.notifications.browser}
                      onChange={(e) => updateSettings('notifications', 'browser', e.target.checked)}
                    />
                  }
                  label="Browser Notifications"
                />
                <FormControlLabel
                  control={
                    <Switch
                      checked={settings.notifications.email}
                      onChange={(e) => updateSettings('notifications', 'email', e.target.checked)}
                    />
                  }
                  label="Email Notifications"
                />
                <FormControlLabel
                  control={
                    <Switch
                      checked={settings.notifications.sms}
                      onChange={(e) => updateSettings('notifications', 'sms', e.target.checked)}
                    />
                  }
                  label="SMS Notifications"
                />
              </Grid>
              
              <Grid item xs={12} md={8}>
                <Typography variant="subtitle1" gutterBottom>Alert Types</Typography>
                <Grid container spacing={1}>
                  <Grid item xs={12} sm={6}>
                    <FormControlLabel
                      control={
                        <Switch
                          checked={settings.notifications.priceAlerts}
                          onChange={(e) => updateSettings('notifications', 'priceAlerts', e.target.checked)}
                        />
                      }
                      label="Price Alerts"
                    />
                  </Grid>
                  <Grid item xs={12} sm={6}>
                    <FormControlLabel
                      control={
                        <Switch
                          checked={settings.notifications.tradeExecutions}
                          onChange={(e) => updateSettings('notifications', 'tradeExecutions', e.target.checked)}
                        />
                      }
                      label="Trade Executions"
                    />
                  </Grid>
                  <Grid item xs={12} sm={6}>
                    <FormControlLabel
                      control={
                        <Switch
                          checked={settings.notifications.portfolioUpdates}
                          onChange={(e) => updateSettings('notifications', 'portfolioUpdates', e.target.checked)}
                        />
                      }
                      label="Portfolio Updates"
                    />
                  </Grid>
                  <Grid item xs={12} sm={6}>
                    <FormControlLabel
                      control={
                        <Switch
                          checked={settings.notifications.riskAlerts}
                          onChange={(e) => updateSettings('notifications', 'riskAlerts', e.target.checked)}
                        />
                      }
                      label="Risk Alerts"
                    />
                  </Grid>
                  <Grid item xs={12} sm={6}>
                    <FormControlLabel
                      control={
                        <Switch
                          checked={settings.notifications.systemUpdates}
                          onChange={(e) => updateSettings('notifications', 'systemUpdates', e.target.checked)}
                        />
                      }
                      label="System Updates"
                    />
                  </Grid>
                </Grid>
              </Grid>
            </Grid>
          </CardContent>
        </Card>
      </Grid>
    </Grid>
  );

  const renderDisplayTab = () => (
    <Grid container spacing={3}>
      <Grid item xs={12} md={6}>
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              <ColorLens sx={{ mr: 1, verticalAlign: 'middle' }} />
              Display Preferences
            </Typography>
            
            <Grid container spacing={2}>
              <Grid item xs={12}>
                <FormControl fullWidth>
                  <InputLabel>Theme</InputLabel>
                  <Select
                    value={settings.display.theme}
                    onChange={(e) => updateSettings('display', 'theme', e.target.value)}
                  >
                    <MenuItem value="light">Light</MenuItem>
                    <MenuItem value="dark">Dark</MenuItem>
                    <MenuItem value="auto">Auto</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
              
              <Grid item xs={12}>
                <FormControl fullWidth>
                  <InputLabel>Currency</InputLabel>
                  <Select
                    value={settings.display.currency}
                    onChange={(e) => updateSettings('display', 'currency', e.target.value)}
                  >
                    <MenuItem value="USD">USD</MenuItem>
                    <MenuItem value="EUR">EUR</MenuItem>
                    <MenuItem value="GBP">GBP</MenuItem>
                    <MenuItem value="JPY">JPY</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
              
              <Grid item xs={6}>
                <FormControl fullWidth>
                  <InputLabel>Date Format</InputLabel>
                  <Select
                    value={settings.display.dateFormat}
                    onChange={(e) => updateSettings('display', 'dateFormat', e.target.value)}
                  >
                    <MenuItem value="MM/DD/YYYY">MM/DD/YYYY</MenuItem>
                    <MenuItem value="DD/MM/YYYY">DD/MM/YYYY</MenuItem>
                    <MenuItem value="YYYY-MM-DD">YYYY-MM-DD</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
              
              <Grid item xs={6}>
                <FormControl fullWidth>
                  <InputLabel>Time Format</InputLabel>
                  <Select
                    value={settings.display.timeFormat}
                    onChange={(e) => updateSettings('display', 'timeFormat', e.target.value)}
                  >
                    <MenuItem value="12h">12 Hour</MenuItem>
                    <MenuItem value="24h">24 Hour</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
            </Grid>
          </CardContent>
        </Card>
      </Grid>

      <Grid item xs={12} md={6}>
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              <Settings sx={{ mr: 1, verticalAlign: 'middle' }} />
              Interface Settings
            </Typography>
            
            <Grid container spacing={2}>
              <Grid item xs={12}>
                <FormControlLabel
                  control={
                    <Switch
                      checked={settings.display.compactMode}
                      onChange={(e) => updateSettings('display', 'compactMode', e.target.checked)}
                    />
                  }
                  label="Compact Mode"
                />
              </Grid>
              
              <Grid item xs={12}>
                <FormControlLabel
                  control={
                    <Switch
                      checked={settings.display.showAdvancedMetrics}
                      onChange={(e) => updateSettings('display', 'showAdvancedMetrics', e.target.checked)}
                    />
                  }
                  label="Show Advanced Metrics"
                />
              </Grid>
              
              <Grid item xs={12}>
                <FormControlLabel
                  control={
                    <Switch
                      checked={settings.display.autoRefresh}
                      onChange={(e) => updateSettings('display', 'autoRefresh', e.target.checked)}
                    />
                  }
                  label="Auto Refresh"
                />
              </Grid>
              
              {settings.display.autoRefresh && (
                <Grid item xs={12}>
                  <TextField
                    fullWidth
                    label="Refresh Interval (seconds)"
                    type="number"
                    value={settings.display.refreshInterval}
                    onChange={(e) => updateSettings('display', 'refreshInterval', parseInt(e.target.value))}
                  />
                </Grid>
              )}
              
              <Grid item xs={12}>
                <FormControl fullWidth>
                  <InputLabel>Default Chart Type</InputLabel>
                  <Select
                    value={settings.display.defaultChartType}
                    onChange={(e) => updateSettings('display', 'defaultChartType', e.target.value)}
                  >
                    <MenuItem value="candlestick">Candlestick</MenuItem>
                    <MenuItem value="line">Line</MenuItem>
                    <MenuItem value="bar">Bar</MenuItem>
                    <MenuItem value="area">Area</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
            </Grid>
          </CardContent>
        </Card>
      </Grid>
    </Grid>
  );

  return (
    <Box>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 3 }}>
        <Typography variant="h5">
          <Settings sx={{ mr: 1, verticalAlign: 'middle' }} />
          Settings
        </Typography>
        
        <Box sx={{ display: 'flex', gap: 1 }}>
          <input
            accept=".json"
            style={{ display: 'none' }}
            id="import-settings"
            type="file"
            onChange={importSettings}
          />
          <label htmlFor="import-settings">
            <Button variant="outlined" component="span" size="small">
              Import
            </Button>
          </label>
          
          <Button variant="outlined" onClick={exportSettings} size="small">
            Export
          </Button>
          
          <Button variant="outlined" onClick={resetSettings} size="small" color="error">
            Reset
          </Button>
          
          <Button 
            variant="contained" 
            onClick={saveSettings}
            disabled={!unsavedChanges}
            startIcon={<Save />}
          >
            Save Changes
          </Button>
        </Box>
      </Box>

      {unsavedChanges && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          You have unsaved changes. Don't forget to save your settings.
        </Alert>
      )}

      <Tabs value={activeTab} onChange={(e, newValue) => setActiveTab(newValue)} sx={{ mb: 3 }}>
        <Tab label="API Keys" icon={<VpnKey />} />
        <Tab label="Trading" icon={<Trading />} />
        <Tab label="Notifications" icon={<Notifications />} />
        <Tab label="Display" icon={<ColorLens />} />
      </Tabs>

      {activeTab === 0 && renderAPIKeysTab()}
      {activeTab === 1 && renderTradingTab()}
      {activeTab === 2 && renderNotificationsTab()}
      {activeTab === 3 && renderDisplayTab()}

      <Snackbar
        open={snackbar.open}
        autoHideDuration={6000}
        onClose={() => setSnackbar({ ...snackbar, open: false })}
      >
        <Alert 
          onClose={() => setSnackbar({ ...snackbar, open: false })} 
          severity={snackbar.severity}
        >
          {snackbar.message}
        </Alert>
      </Snackbar>
    </Box>
  );
};

export default SettingsManager;