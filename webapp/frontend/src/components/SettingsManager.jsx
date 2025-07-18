import React, { useState, useEffect } from 'react';
import settingsService from '../services/settingsService';
import { useApiKeys } from './ApiKeyProvider';
import ApiKeyOnboarding from './ApiKeyOnboarding';
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
  ShowChart,
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
  const { 
    apiKeys, 
    isLoading: apiKeysLoading, 
    hasApiKeys, 
    saveApiKey, 
    removeApiKey, 
    hasValidProvider,
    getActiveProviders,
    error: apiKeyError 
  } = useApiKeys();
  
  const [activeTab, setActiveTab] = useState(0);
  const [settings, setSettings] = useState({
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

  // Load settings from backend on mount
  useEffect(() => {
    const loadSettings = async () => {
      try {
        console.log('🔄 Loading API keys from backend...');
        
        // First, try to migrate any localStorage settings
        const migrationResult = await settingsService.migrateLocalStorageToBackend();
        if (migrationResult.migrated) {
          setSnackbar({ 
            open: true, 
            message: `Migrated ${migrationResult.keys.length} API key(s) to secure backend storage`, 
            severity: 'success' 
          });
        }
        
        // Load API keys from backend
        const apiKeys = await settingsService.getApiKeys();
        const formattedKeys = settingsService.formatApiKeysForFrontend(apiKeys);
        
        setSettings(prev => ({
          ...prev,
          apiKeys: formattedKeys
        }));
        
        console.log('✅ Successfully loaded settings from backend');
        
      } catch (error) {
        console.error('❌ Error loading settings from backend:', error);
        
        // Fallback to localStorage for graceful degradation
        console.log('🔄 Falling back to localStorage...');
        const savedSettings = localStorage.getItem('app_settings');
        if (savedSettings) {
          try {
            const parsed = JSON.parse(savedSettings);
            setSettings(prev => ({ ...prev, ...parsed }));
            setSnackbar({ 
              open: true, 
              message: 'Loaded settings from local storage. Connect to backend for secure storage.', 
              severity: 'warning' 
            });
          } catch (parseError) {
            console.error('Error parsing localStorage settings:', parseError);
          }
        }
      }
    };

    loadSettings();
  }, []);

  // Save API key to backend (local function)
  const saveApiKeyLocal = async (provider, apiKeyData) => {
    try {
      console.log('💾 Saving API key for provider:', provider);
      
      const keyData = {
        provider: provider,
        apiKey: apiKeyData.keyId || apiKeyData.apiKey,
        apiSecret: apiKeyData.secretKey || 'not_required',
        isSandbox: apiKeyData.paperTrading !== undefined ? apiKeyData.paperTrading : false,
        description: `${provider} API key`
      };

      // Check if this is an update (key has an id) or new key
      if (apiKeyData.id) {
        await settingsService.updateApiKey(apiKeyData.id, {
          description: keyData.description,
          isSandbox: keyData.isSandbox
        });
      } else {
        await settingsService.addApiKey(keyData);
      }
      
      // Reload settings from backend
      const apiKeys = await settingsService.getApiKeys();
      const formattedKeys = settingsService.formatApiKeysForFrontend(apiKeys);
      
      setSettings(prev => ({
        ...prev,
        apiKeys: formattedKeys
      }));
      
      setUnsavedChanges(false);
      setSnackbar({ open: true, message: `${provider} API key saved successfully`, severity: 'success' });
      
    } catch (error) {
      console.error('❌ Error saving API key:', error);
      setSnackbar({ 
        open: true, 
        message: `Error saving ${provider} API key: ${error.message}`, 
        severity: 'error' 
      });
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

  // Test API connection with real backend validation
  const testConnection = async (provider) => {
    setTestingConnection(true);
    
    try {
      console.log('🧪 Testing connection for provider:', provider);
      
      // Get the API key ID for this provider
      const apiKey = settings.apiKeys[provider];
      if (!apiKey || !apiKey.id) {
        throw new Error('No API key configured for this provider');
      }
      
      // Validate API key with backend
      const validationResult = await settingsService.validateApiKey(apiKey.id, provider);
      
      setConnectionResults(prev => ({
        ...prev,
        [provider]: {
          status: validationResult.valid ? 'success' : 'error',
          message: validationResult.message || (validationResult.valid ? 'Connection successful' : 'Invalid API credentials'),
          details: validationResult.details
        }
      }));
      
      // Update the validation status in settings
      if (validationResult.valid) {
        setSettings(prev => ({
          ...prev,
          apiKeys: {
            ...prev.apiKeys,
            [provider]: {
              ...prev.apiKeys[provider],
              validationStatus: 'VALID',
              lastValidated: new Date().toISOString()
            }
          }
        }));
      }
      
    } catch (error) {
      console.error('❌ Error testing connection:', error);
      setConnectionResults(prev => ({
        ...prev,
        [provider]: {
          status: 'error',
          message: error.message || 'Connection test failed'
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
    <div className="grid" container spacing={3}>
      {/* Alpaca */}
      <div className="grid" item xs={12}>
        <div className="bg-white shadow-md rounded-lg">
          <div className="bg-white shadow-md rounded-lg"Content>
            <div  sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
              <AccountBalance sx={{ mr: 1 }} />
              <div  variant="h6">Alpaca Trading</div>
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                label={settings.apiKeys.alpaca.enabled ? 'Connected' : 'Disconnected'} 
                color={settings.apiKeys.alpaca.enabled ? 'success' : 'default'}
                size="small"
                sx={{ ml: 2 }}
              />
            </div>
            
            <div className="grid" container spacing={2}>
              <div className="grid" item xs={12} md={6}>
                <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
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
                        <button className="p-2 rounded-full hover:bg-gray-100"
                          onClick={() => setShowPasswords(prev => ({
                            ...prev,
                            alpacaKey: !prev.alpacaKey
                          }))}
                        >
                          {showPasswords.alpacaKey ? <VisibilityOff /> : <Visibility />}
                        </button>
                      </InputAdornment>
                    )
                  }}
                />
              </div>
              <div className="grid" item xs={12} md={6}>
                <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
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
                        <button className="p-2 rounded-full hover:bg-gray-100"
                          onClick={() => setShowPasswords(prev => ({
                            ...prev,
                            alpacaSecret: !prev.alpacaSecret
                          }))}
                        >
                          {showPasswords.alpacaSecret ? <VisibilityOff /> : <Visibility />}
                        </button>
                      </InputAdornment>
                    )
                  }}
                />
              </div>
              <div className="grid" item xs={12}>
                <div  sx={{ display: 'flex', gap: 2, alignItems: 'center' }}>
                  <div className="mb-4"Label
                    control={
                      <input type="checkbox" className="toggle"
                        checked={settings.apiKeys.alpaca.paperTrading}
                        onChange={(e) => updateSettings('apiKeys', 'alpaca', {
                          ...settings.apiKeys.alpaca,
                          paperTrading: e.target.checked
                        })}
                      />
                    }
                    label="Paper Trading"
                  />
                  <div className="mb-4"Label
                    control={
                      <input type="checkbox" className="toggle"
                        checked={settings.apiKeys.alpaca.enabled}
                        onChange={(e) => updateSettings('apiKeys', 'alpaca', {
                          ...settings.apiKeys.alpaca,
                          enabled: e.target.checked
                        })}
                      />
                    }
                    label="Enabled"
                  />
                  <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                    variant="contained"
                    onClick={() => saveApiKeyLocal('alpaca', settings.apiKeys.alpaca)}
                    disabled={!settings.apiKeys.alpaca.keyId || !settings.apiKeys.alpaca.secretKey}
                    sx={{ mr: 1 }}
                  >
                    Save API Key
                  </button>
                  <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                    variant="outlined"
                    onClick={() => testConnection('alpaca')}
                    disabled={testingConnection || !settings.apiKeys.alpaca.id}
                  >
                    Test Connection
                  </button>
                </div>
              </div>
            </div>
            
            {connectionResults.alpaca && (
              <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity={connectionResults.alpaca.status} sx={{ mt: 2 }}>
                {connectionResults.alpaca.message}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Polygon */}
      <div className="grid" item xs={12}>
        <div className="bg-white shadow-md rounded-lg">
          <div className="bg-white shadow-md rounded-lg"Content>
            <div  sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
              <Assessment sx={{ mr: 1 }} />
              <div  variant="h6">Polygon Market Data</div>
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                label={settings.apiKeys.polygon.enabled ? 'Connected' : 'Disconnected'} 
                color={settings.apiKeys.polygon.enabled ? 'success' : 'default'}
                size="small"
                sx={{ ml: 2 }}
              />
            </div>
            
            <div className="grid" container spacing={2}>
              <div className="grid" item xs={12} md={8}>
                <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
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
                        <button className="p-2 rounded-full hover:bg-gray-100"
                          onClick={() => setShowPasswords(prev => ({
                            ...prev,
                            polygonKey: !prev.polygonKey
                          }))}
                        >
                          {showPasswords.polygonKey ? <VisibilityOff /> : <Visibility />}
                        </button>
                      </InputAdornment>
                    )
                  }}
                />
              </div>
              <div className="grid" item xs={12} md={4}>
                <div  sx={{ display: 'flex', gap: 2, alignItems: 'center' }}>
                  <div className="mb-4"Label
                    control={
                      <input type="checkbox" className="toggle"
                        checked={settings.apiKeys.polygon.enabled}
                        onChange={(e) => updateSettings('apiKeys', 'polygon', {
                          ...settings.apiKeys.polygon,
                          enabled: e.target.checked
                        })}
                      />
                    }
                    label="Enabled"
                  />
                  <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                    variant="contained"
                    onClick={() => saveApiKeyLocal('polygon', settings.apiKeys.polygon)}
                    disabled={!settings.apiKeys.polygon.apiKey}
                    sx={{ mr: 1 }}
                  >
                    Save API Key
                  </button>
                  <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                    variant="outlined"
                    onClick={() => testConnection('polygon')}
                    disabled={testingConnection || !settings.apiKeys.polygon.id}
                  >
                    Test Connection
                  </button>
                </div>
              </div>
            </div>
            
            {connectionResults.polygon && (
              <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity={connectionResults.polygon.status} sx={{ mt: 2 }}>
                {connectionResults.polygon.message}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );

  const renderTradingTab = () => (
    <div className="grid" container spacing={3}>
      <div className="grid" item xs={12} md={6}>
        <div className="bg-white shadow-md rounded-lg">
          <div className="bg-white shadow-md rounded-lg"Content>
            <div  variant="h6" gutterBottom>
              <TrendingUp sx={{ mr: 1, verticalAlign: 'middle' }} />
              Order Defaults
            </div>
            
            <div className="grid" container spacing={2}>
              <div className="grid" item xs={12}>
                <div className="mb-4" fullWidth>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Default Order Type</label>
                  <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={settings.trading.defaultOrderType}
                    onChange={(e) => updateSettings('trading', 'defaultOrderType', e.target.value)}
                  >
                    <option  value="market">Market</option>
                    <option  value="limit">Limit</option>
                    <option  value="stop">Stop</option>
                    <option  value="stop_limit">Stop Limit</option>
                  </select>
                </div>
              </div>
              
              <div className="grid" item xs={12}>
                <div className="mb-4" fullWidth>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Time in Force</label>
                  <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={settings.trading.defaultTimeInForce}
                    onChange={(e) => updateSettings('trading', 'defaultTimeInForce', e.target.value)}
                  >
                    <option  value="day">Day</option>
                    <option  value="gtc">Good Till Canceled</option>
                    <option  value="ioc">Immediate or Cancel</option>
                    <option  value="fok">Fill or Kill</option>
                  </select>
                </div>
              </div>
              
              <div className="grid" item xs={12}>
                <div className="mb-4"Label
                  control={
                    <input type="checkbox" className="toggle"
                      checked={settings.trading.enableAfterHours}
                      onChange={(e) => updateSettings('trading', 'enableAfterHours', e.target.checked)}
                    />
                  }
                  label="Enable After Hours Trading"
                />
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="grid" item xs={12} md={6}>
        <div className="bg-white shadow-md rounded-lg">
          <div className="bg-white shadow-md rounded-lg"Content>
            <div  variant="h6" gutterBottom>
              <Security sx={{ mr: 1, verticalAlign: 'middle' }} />
              Risk Management
            </div>
            
            <div className="grid" container spacing={2}>
              <div className="grid" item xs={12}>
                <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  fullWidth
                  label="Max Position Size (%)"
                  type="number"
                  value={settings.trading.maxPositionSize * 100}
                  onChange={(e) => updateSettings('trading', 'maxPositionSize', e.target.value / 100)}
                  InputProps={{
                    endAdornment: <InputAdornment position="end">%</InputAdornment>
                  }}
                />
              </div>
              
              <div className="grid" item xs={12}>
                <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  fullWidth
                  label="Max Daily Loss (%)"
                  type="number"
                  value={settings.trading.maxDailyLoss * 100}
                  onChange={(e) => updateSettings('trading', 'maxDailyLoss', e.target.value / 100)}
                  InputProps={{
                    endAdornment: <InputAdornment position="end">%</InputAdornment>
                  }}
                />
              </div>
              
              <div className="grid" item xs={12}>
                <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  fullWidth
                  label="Risk Per Trade (%)"
                  type="number"
                  value={settings.trading.riskPerTrade * 100}
                  onChange={(e) => updateSettings('trading', 'riskPerTrade', e.target.value / 100)}
                  InputProps={{
                    endAdornment: <InputAdornment position="end">%</InputAdornment>
                  }}
                />
              </div>
              
              <div className="grid" item xs={12}>
                <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  fullWidth
                  label="Max Open Positions"
                  type="number"
                  value={settings.trading.maxOpenPositions}
                  onChange={(e) => updateSettings('trading', 'maxOpenPositions', parseInt(e.target.value))}
                />
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="grid" item xs={12}>
        <div className="bg-white shadow-md rounded-lg">
          <div className="bg-white shadow-md rounded-lg"Content>
            <div  variant="h6" gutterBottom>
              Automatic Stop Loss & Take Profit
            </div>
            
            <div className="grid" container spacing={2}>
              <div className="grid" item xs={12} md={6}>
                <div className="mb-4"Label
                  control={
                    <input type="checkbox" className="toggle"
                      checked={settings.trading.autoStopLoss}
                      onChange={(e) => updateSettings('trading', 'autoStopLoss', e.target.checked)}
                    />
                  }
                  label="Auto Stop Loss"
                />
                {settings.trading.autoStopLoss && (
                  <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
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
              </div>
              
              <div className="grid" item xs={12} md={6}>
                <div className="mb-4"Label
                  control={
                    <input type="checkbox" className="toggle"
                      checked={settings.trading.autoTakeProfit}
                      onChange={(e) => updateSettings('trading', 'autoTakeProfit', e.target.checked)}
                    />
                  }
                  label="Auto Take Profit"
                />
                {settings.trading.autoTakeProfit && (
                  <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
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
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );

  const renderNotificationsTab = () => (
    <div className="grid" container spacing={3}>
      <div className="grid" item xs={12}>
        <div className="bg-white shadow-md rounded-lg">
          <div className="bg-white shadow-md rounded-lg"Content>
            <div  variant="h6" gutterBottom>
              <Notifications sx={{ mr: 1, verticalAlign: 'middle' }} />
              Notification Preferences
            </div>
            
            <div className="grid" container spacing={2}>
              <div className="grid" item xs={12} md={4}>
                <div  variant="subtitle1" gutterBottom>Methods</div>
                <div className="mb-4"Label
                  control={
                    <input type="checkbox" className="toggle"
                      checked={settings.notifications.browser}
                      onChange={(e) => updateSettings('notifications', 'browser', e.target.checked)}
                    />
                  }
                  label="Browser Notifications"
                />
                <div className="mb-4"Label
                  control={
                    <input type="checkbox" className="toggle"
                      checked={settings.notifications.email}
                      onChange={(e) => updateSettings('notifications', 'email', e.target.checked)}
                    />
                  }
                  label="Email Notifications"
                />
                <div className="mb-4"Label
                  control={
                    <input type="checkbox" className="toggle"
                      checked={settings.notifications.sms}
                      onChange={(e) => updateSettings('notifications', 'sms', e.target.checked)}
                    />
                  }
                  label="SMS Notifications"
                />
              </div>
              
              <div className="grid" item xs={12} md={8}>
                <div  variant="subtitle1" gutterBottom>Alert Types</div>
                <div className="grid" container spacing={1}>
                  <div className="grid" item xs={12} sm={6}>
                    <div className="mb-4"Label
                      control={
                        <input type="checkbox" className="toggle"
                          checked={settings.notifications.priceAlerts}
                          onChange={(e) => updateSettings('notifications', 'priceAlerts', e.target.checked)}
                        />
                      }
                      label="Price Alerts"
                    />
                  </div>
                  <div className="grid" item xs={12} sm={6}>
                    <div className="mb-4"Label
                      control={
                        <input type="checkbox" className="toggle"
                          checked={settings.notifications.tradeExecutions}
                          onChange={(e) => updateSettings('notifications', 'tradeExecutions', e.target.checked)}
                        />
                      }
                      label="Trade Executions"
                    />
                  </div>
                  <div className="grid" item xs={12} sm={6}>
                    <div className="mb-4"Label
                      control={
                        <input type="checkbox" className="toggle"
                          checked={settings.notifications.portfolioUpdates}
                          onChange={(e) => updateSettings('notifications', 'portfolioUpdates', e.target.checked)}
                        />
                      }
                      label="Portfolio Updates"
                    />
                  </div>
                  <div className="grid" item xs={12} sm={6}>
                    <div className="mb-4"Label
                      control={
                        <input type="checkbox" className="toggle"
                          checked={settings.notifications.riskAlerts}
                          onChange={(e) => updateSettings('notifications', 'riskAlerts', e.target.checked)}
                        />
                      }
                      label="Risk Alerts"
                    />
                  </div>
                  <div className="grid" item xs={12} sm={6}>
                    <div className="mb-4"Label
                      control={
                        <input type="checkbox" className="toggle"
                          checked={settings.notifications.systemUpdates}
                          onChange={(e) => updateSettings('notifications', 'systemUpdates', e.target.checked)}
                        />
                      }
                      label="System Updates"
                    />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );

  const renderDisplayTab = () => (
    <div className="grid" container spacing={3}>
      <div className="grid" item xs={12} md={6}>
        <div className="bg-white shadow-md rounded-lg">
          <div className="bg-white shadow-md rounded-lg"Content>
            <div  variant="h6" gutterBottom>
              <ColorLens sx={{ mr: 1, verticalAlign: 'middle' }} />
              Display Preferences
            </div>
            
            <div className="grid" container spacing={2}>
              <div className="grid" item xs={12}>
                <div className="mb-4" fullWidth>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Theme</label>
                  <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={settings.display.theme}
                    onChange={(e) => updateSettings('display', 'theme', e.target.value)}
                  >
                    <option  value="light">Light</option>
                    <option  value="dark">Dark</option>
                    <option  value="auto">Auto</option>
                  </select>
                </div>
              </div>
              
              <div className="grid" item xs={12}>
                <div className="mb-4" fullWidth>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Currency</label>
                  <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={settings.display.currency}
                    onChange={(e) => updateSettings('display', 'currency', e.target.value)}
                  >
                    <option  value="USD">USD</option>
                    <option  value="EUR">EUR</option>
                    <option  value="GBP">GBP</option>
                    <option  value="JPY">JPY</option>
                  </select>
                </div>
              </div>
              
              <div className="grid" item xs={6}>
                <div className="mb-4" fullWidth>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Date Format</label>
                  <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={settings.display.dateFormat}
                    onChange={(e) => updateSettings('display', 'dateFormat', e.target.value)}
                  >
                    <option  value="MM/DD/YYYY">MM/DD/YYYY</option>
                    <option  value="DD/MM/YYYY">DD/MM/YYYY</option>
                    <option  value="YYYY-MM-DD">YYYY-MM-DD</option>
                  </select>
                </div>
              </div>
              
              <div className="grid" item xs={6}>
                <div className="mb-4" fullWidth>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Time Format</label>
                  <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={settings.display.timeFormat}
                    onChange={(e) => updateSettings('display', 'timeFormat', e.target.value)}
                  >
                    <option  value="12h">12 Hour</option>
                    <option  value="24h">24 Hour</option>
                  </select>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="grid" item xs={12} md={6}>
        <div className="bg-white shadow-md rounded-lg">
          <div className="bg-white shadow-md rounded-lg"Content>
            <div  variant="h6" gutterBottom>
              <Settings sx={{ mr: 1, verticalAlign: 'middle' }} />
              Interface Settings
            </div>
            
            <div className="grid" container spacing={2}>
              <div className="grid" item xs={12}>
                <div className="mb-4"Label
                  control={
                    <input type="checkbox" className="toggle"
                      checked={settings.display.compactMode}
                      onChange={(e) => updateSettings('display', 'compactMode', e.target.checked)}
                    />
                  }
                  label="Compact Mode"
                />
              </div>
              
              <div className="grid" item xs={12}>
                <div className="mb-4"Label
                  control={
                    <input type="checkbox" className="toggle"
                      checked={settings.display.showAdvancedMetrics}
                      onChange={(e) => updateSettings('display', 'showAdvancedMetrics', e.target.checked)}
                    />
                  }
                  label="Show Advanced Metrics"
                />
              </div>
              
              <div className="grid" item xs={12}>
                <div className="mb-4"Label
                  control={
                    <input type="checkbox" className="toggle"
                      checked={settings.display.autoRefresh}
                      onChange={(e) => updateSettings('display', 'autoRefresh', e.target.checked)}
                    />
                  }
                  label="Auto Refresh"
                />
              </div>
              
              {settings.display.autoRefresh && (
                <div className="grid" item xs={12}>
                  <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    fullWidth
                    label="Refresh Interval (seconds)"
                    type="number"
                    value={settings.display.refreshInterval}
                    onChange={(e) => updateSettings('display', 'refreshInterval', parseInt(e.target.value))}
                  />
                </div>
              )}
              
              <div className="grid" item xs={12}>
                <div className="mb-4" fullWidth>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Default Chart Type</label>
                  <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={settings.display.defaultChartType}
                    onChange={(e) => updateSettings('display', 'defaultChartType', e.target.value)}
                  >
                    <option  value="candlestick">Candlestick</option>
                    <option  value="line">Line</option>
                    <option  value="bar">Bar</option>
                    <option  value="area">Area</option>
                  </select>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );

  return (
    <div>
      <div  sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 3 }}>
        <div  variant="h5">
          <Settings sx={{ mr: 1, verticalAlign: 'middle' }} />
          Settings
        </div>
        
        <div  sx={{ display: 'flex', gap: 1 }}>
          <input
            accept=".json"
            style={{ display: 'none' }}
            id="import-settings"
            type="file"
            onChange={importSettings}
          />
          <label htmlFor="import-settings">
            <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" variant="outlined" component="span" size="small">
              Import
            </button>
          </label>
          
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" variant="outlined" onClick={exportSettings} size="small">
            Export
          </button>
          
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" variant="outlined" onClick={resetSettings} size="small" color="error">
            Reset
          </button>
          
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
            variant="contained" 
            onClick={() => {
              // Save API keys to backend
              Object.keys(settings.apiKeys).forEach(provider => {
                const apiKey = settings.apiKeys[provider];
                if (apiKey.enabled && (apiKey.keyId || apiKey.apiKey)) {
                  saveApiKey(provider, apiKey);
                }
              });
            }}
            disabled={!unsavedChanges}
            startIcon={<Save />}
          >
            Save Changes
          </button>
        </div>
      </div>

      {unsavedChanges && (
        <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="warning" sx={{ mb: 2 }}>
          You have unsaved changes. Don't forget to save your settings.
        </div>
      )}

      <div className="border-b border-gray-200" value={activeTab} onChange={(e, newValue) => setActiveTab(newValue)} sx={{ mb: 3 }}>
        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="API Keys" icon={<VpnKey />} />
        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Trading" icon={<ShowChart />} />
        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Notifications" icon={<Notifications />} />
        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Display" icon={<ColorLens />} />
      </div>

      {activeTab === 0 && renderAPIKeysTab()}
      {activeTab === 1 && renderTradingTab()}
      {activeTab === 2 && renderNotificationsTab()}
      {activeTab === 3 && renderDisplayTab()}

      <div className="fixed bottom-4 right-4 bg-gray-800 text-white p-4 rounded-md shadow-lg"
        open={snackbar.open}
        autoHideDuration={6000}
        onClose={() => setSnackbar({ ...snackbar, open: false })}
      >
        <div className="p-4 rounded-md bg-blue-50 border border-blue-200" 
          onClose={() => setSnackbar({ ...snackbar, open: false })} 
          severity={snackbar.severity}
        >
          {snackbar.message}
        </div>
      </div>
    </div>
  );
};

export default SettingsManager;