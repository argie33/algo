import React, { useState, useEffect } from 'react';
import settingsService from '../services/settingsService';
import { useApiKeys } from './ApiKeyProvider';
import ApiKeyOnboarding from './ApiKeyOnboarding';
import ApiKeysTab from './settings/ApiKeysTab';
import TradingTab from './settings/TradingTab';
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
    // API Keys
    apiKeys: {
      alpaca: {
        keyId: '',
        secretKey: '',
        enabled: false,
        paperTrading: true
      },
      polygon: {
        apiKey: '',
        enabled: false
      },
      fmp: {
        apiKey: '',
        enabled: false
      }
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
  
  // Dialog and UI state
  const [openDialog, setOpenDialog] = useState(null); // 'onboarding', 'editSetting', 'schedule', etc.
  const [viewMode, setViewMode] = useState('tabs'); // 'tabs', 'list', 'accordion'
  const [editingItem, setEditingItem] = useState(null);
  const [showAdvancedSettings, setShowAdvancedSettings] = useState(false);
  const [scheduleSettings, setScheduleSettings] = useState({
    autoTradingEnabled: false,
    tradingSchedule: {
      enabled: false,
      startTime: '09:30',
      endTime: '16:00',
      timezone: 'America/New_York',
      weekdays: [1, 2, 3, 4, 5] // Monday to Friday
    },
    rebalancing: {
      enabled: false,
      frequency: 'weekly',
      day: 'monday',
      time: '09:30'
    }
  });
  const [languageSettings, setLanguageSettings] = useState({
    language: 'en',
    region: 'US',
    timezone: 'America/New_York',
    currency: 'USD'
  });
  const [cloudSyncSettings, setCloudSyncSettings] = useState({
    enabled: false,
    lastSync: null,
    syncSettings: true,
    syncApiKeys: false,
    syncTradingHistory: false,
    autoSync: true
  });

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

  // Check if onboarding is needed
  const needsOnboarding = () => {
    return !hasApiKeys && !apiKeysLoading;
  };

  // Handle onboarding completion
  const handleOnboardingComplete = () => {
    setOpenDialog(null);
    setSnackbar({ 
      open: true, 
      message: 'Welcome! Your API keys have been configured successfully.', 
      severity: 'success' 
    });
  };

  // CRUD operations for settings
  const handleAddSetting = (category, settingData) => {
    setSettings(prev => ({
      ...prev,
      [category]: {
        ...prev[category],
        ...settingData
      }
    }));
    setUnsavedChanges(true);
    setOpenDialog(null);
    setSnackbar({ open: true, message: 'Setting added successfully', severity: 'success' });
  };

  const handleEditSetting = (category, key, value) => {
    setSettings(prev => ({
      ...prev,
      [category]: {
        ...prev[category],
        [key]: value
      }
    }));
    setUnsavedChanges(true);
    setOpenDialog(null);
    setSnackbar({ open: true, message: 'Setting updated successfully', severity: 'success' });
  };

  const handleDeleteSetting = (category, key) => {
    if (window.confirm('Are you sure you want to delete this setting?')) {
      setSettings(prev => {
        const updated = { ...prev };
        if (updated[category] && updated[category][key]) {
          delete updated[category][key];
        }
        return updated;
      });
      setUnsavedChanges(true);
      setSnackbar({ open: true, message: 'Setting deleted successfully', severity: 'warning' });
    }
  };

  // Schedule management
  const handleScheduleUpdate = (scheduleData) => {
    setScheduleSettings(scheduleData);
    setUnsavedChanges(true);
    setOpenDialog(null);
    setSnackbar({ open: true, message: 'Schedule updated successfully', severity: 'success' });
  };

  // Language settings
  const handleLanguageUpdate = (languageData) => {
    setLanguageSettings(languageData);
    setUnsavedChanges(true);
    setSnackbar({ open: true, message: 'Language settings updated', severity: 'success' });
  };

  // Cloud sync management
  const handleCloudSyncToggle = async () => {
    try {
      const newState = !cloudSyncSettings.enabled;
      setCloudSyncSettings(prev => ({ 
        ...prev, 
        enabled: newState,
        lastSync: newState ? new Date().toISOString() : null
      }));
      setUnsavedChanges(true);
      setSnackbar({ 
        open: true, 
        message: newState ? 'Cloud sync enabled' : 'Cloud sync disabled', 
        severity: 'success' 
      });
    } catch (error) {
      setSnackbar({ 
        open: true, 
        message: 'Error updating cloud sync settings', 
        severity: 'error' 
      });
    }
  };

  // Get setting validation status
  const getSettingStatus = (category, key, value) => {
    // Add validation logic for different settings
    if (!value) return { status: 'warning', message: 'Not configured' };
    if (category === 'apiKeys' && value.enabled && !value.keyId) {
      return { status: 'error', message: 'API key required' };
    }
    if (category === 'trading' && key === 'maxPositionSize' && value > 0.1) {
      return { status: 'warning', message: 'High risk setting' };
    }
    return { status: 'success', message: 'Configured' };
  };

  // Dialog Components
  const renderOnboardingDialog = () => (
    <Dialog
      open={openDialog === 'onboarding'}
      onClose={() => setOpenDialog(null)}
      maxWidth="md"
      fullWidth
    >
      <DialogTitle>Welcome to Trading Platform</DialogTitle>
      <DialogContent>
        <ApiKeyOnboarding onComplete={handleOnboardingComplete} />
      </DialogContent>
      <DialogActions>
        <Button onClick={() => setOpenDialog(null)}>Skip for Now</Button>
      </DialogActions>
    </Dialog>
  );

  const renderScheduleDialog = () => (
    <Dialog
      open={openDialog === 'schedule'}
      onClose={() => setOpenDialog(null)}
      maxWidth="md"
      fullWidth
    >
      <DialogTitle>
        <Schedule sx={{ mr: 1, verticalAlign: 'middle' }} />
        Trading Schedule Settings
      </DialogTitle>
      <DialogContent>
        <Grid container spacing={3} sx={{ mt: 1 }}>
          <Grid item xs={12}>
            <FormControlLabel
              control={
                <Switch
                  checked={scheduleSettings.autoTradingEnabled}
                  onChange={(e) => setScheduleSettings(prev => ({ 
                    ...prev, 
                    autoTradingEnabled: e.target.checked 
                  }))}
                />
              }
              label="Enable Automated Trading"
            />
          </Grid>
          
          <Grid item xs={12}>
            <Typography variant="h6" gutterBottom>Trading Hours</Typography>
            <Grid container spacing={2}>
              <Grid item xs={6}>
                <TextField
                  fullWidth
                  label="Market Open"
                  type="time"
                  value={scheduleSettings.tradingSchedule.startTime}
                  onChange={(e) => setScheduleSettings(prev => ({
                    ...prev,
                    tradingSchedule: { ...prev.tradingSchedule, startTime: e.target.value }
                  }))}
                  InputLabelProps={{ shrink: true }}
                />
              </Grid>
              <Grid item xs={6}>
                <TextField
                  fullWidth
                  label="Market Close"
                  type="time"
                  value={scheduleSettings.tradingSchedule.endTime}
                  onChange={(e) => setScheduleSettings(prev => ({
                    ...prev,
                    tradingSchedule: { ...prev.tradingSchedule, endTime: e.target.value }
                  }))}
                  InputLabelProps={{ shrink: true }}
                />
              </Grid>
            </Grid>
          </Grid>
          
          <Grid item xs={12}>
            <Typography variant="h6" gutterBottom>Portfolio Rebalancing</Typography>
            <FormControlLabel
              control={
                <Switch
                  checked={scheduleSettings.rebalancing.enabled}
                  onChange={(e) => setScheduleSettings(prev => ({
                    ...prev,
                    rebalancing: { ...prev.rebalancing, enabled: e.target.checked }
                  }))}
                />
              }
              label="Auto-Rebalancing"
            />
            
            {scheduleSettings.rebalancing.enabled && (
              <Grid container spacing={2} sx={{ mt: 1 }}>
                <Grid item xs={6}>
                  <FormControl fullWidth>
                    <InputLabel>Frequency</InputLabel>
                    <Select
                      value={scheduleSettings.rebalancing.frequency}
                      onChange={(e) => setScheduleSettings(prev => ({
                        ...prev,
                        rebalancing: { ...prev.rebalancing, frequency: e.target.value }
                      }))}
                    >
                      <MenuItem value="daily">Daily</MenuItem>
                      <MenuItem value="weekly">Weekly</MenuItem>
                      <MenuItem value="monthly">Monthly</MenuItem>
                    </Select>
                  </FormControl>
                </Grid>
                <Grid item xs={6}>
                  <TextField
                    fullWidth
                    label="Time"
                    type="time"
                    value={scheduleSettings.rebalancing.time}
                    onChange={(e) => setScheduleSettings(prev => ({
                      ...prev,
                      rebalancing: { ...prev.rebalancing, time: e.target.value }
                    }))}
                    InputLabelProps={{ shrink: true }}
                  />
                </Grid>
              </Grid>
            )}
          </Grid>
        </Grid>
      </DialogContent>
      <DialogActions>
        <Button onClick={() => setOpenDialog(null)}>Cancel</Button>
        <Button 
          onClick={() => handleScheduleUpdate(scheduleSettings)} 
          variant="contained"
        >
          Save Schedule
        </Button>
      </DialogActions>
    </Dialog>
  );

  const renderLanguageDialog = () => (
    <Dialog
      open={openDialog === 'language'}
      onClose={() => setOpenDialog(null)}
      maxWidth="sm"
      fullWidth
    >
      <DialogTitle>
        <Language sx={{ mr: 1, verticalAlign: 'middle' }} />
        Language & Region Settings
      </DialogTitle>
      <DialogContent>
        <Grid container spacing={2} sx={{ mt: 1 }}>
          <Grid item xs={12}>
            <FormControl fullWidth>
              <InputLabel>Language</InputLabel>
              <Select
                value={languageSettings.language}
                onChange={(e) => setLanguageSettings(prev => ({ 
                  ...prev, 
                  language: e.target.value 
                }))}
              >
                <MenuItem value="en">English</MenuItem>
                <MenuItem value="es">Español</MenuItem>
                <MenuItem value="fr">Français</MenuItem>
                <MenuItem value="de">Deutsch</MenuItem>
                <MenuItem value="zh">中文</MenuItem>
                <MenuItem value="ja">日本語</MenuItem>
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12}>
            <FormControl fullWidth>
              <InputLabel>Region</InputLabel>
              <Select
                value={languageSettings.region}
                onChange={(e) => setLanguageSettings(prev => ({ 
                  ...prev, 
                  region: e.target.value 
                }))}
              >
                <MenuItem value="US">United States</MenuItem>
                <MenuItem value="CA">Canada</MenuItem>
                <MenuItem value="UK">United Kingdom</MenuItem>
                <MenuItem value="EU">European Union</MenuItem>
                <MenuItem value="AU">Australia</MenuItem>
                <MenuItem value="JP">Japan</MenuItem>
              </Select>
            </FormControl>
          </Grid>
        </Grid>
      </DialogContent>
      <DialogActions>
        <Button onClick={() => setOpenDialog(null)}>Cancel</Button>
        <Button 
          onClick={() => handleLanguageUpdate(languageSettings)} 
          variant="contained"
        >
          Apply
        </Button>
      </DialogActions>
    </Dialog>
  );

  const renderCloudSyncDialog = () => (
    <Dialog
      open={openDialog === 'cloudsync'}
      onClose={() => setOpenDialog(null)}
      maxWidth="sm"
      fullWidth
    >
      <DialogTitle>
        <CloudSync sx={{ mr: 1, verticalAlign: 'middle' }} />
        Cloud Synchronization
      </DialogTitle>
      <DialogContent>
        <Box sx={{ mt: 2 }}>
          <FormControlLabel
            control={
              <Switch
                checked={cloudSyncSettings.enabled}
                onChange={handleCloudSyncToggle}
              />
            }
            label="Enable Cloud Sync"
          />
          
          {cloudSyncSettings.enabled && (
            <Box sx={{ mt: 2 }}>
              <Typography variant="body2" color="text.secondary" gutterBottom>
                Last sync: {cloudSyncSettings.lastSync ? 
                  new Date(cloudSyncSettings.lastSync).toLocaleString() : 
                  'Never'
                }
              </Typography>
              
              <Divider sx={{ my: 2 }} />
              
              <Typography variant="subtitle2" gutterBottom>Sync Options</Typography>
              
              <FormControlLabel
                control={
                  <Switch
                    checked={cloudSyncSettings.syncSettings}
                    onChange={(e) => setCloudSyncSettings(prev => ({ 
                      ...prev, 
                      syncSettings: e.target.checked 
                    }))}
                  />
                }
                label="Sync Application Settings"
              />
              
              <FormControlLabel
                control={
                  <Switch
                    checked={cloudSyncSettings.syncApiKeys}
                    onChange={(e) => setCloudSyncSettings(prev => ({ 
                      ...prev, 
                      syncApiKeys: e.target.checked 
                    }))}
                  />
                }
                label="Sync API Keys (Encrypted)"
              />
              
              <FormControlLabel
                control={
                  <Switch
                    checked={cloudSyncSettings.autoSync}
                    onChange={(e) => setCloudSyncSettings(prev => ({ 
                      ...prev, 
                      autoSync: e.target.checked 
                    }))}
                  />
                }
                label="Auto-sync Changes"
              />
            </Box>
          )}
        </Box>
      </DialogContent>
      <DialogActions>
        <Button onClick={() => setOpenDialog(null)}>Close</Button>
        {cloudSyncSettings.enabled && (
          <Button variant="contained" onClick={() => {
            setCloudSyncSettings(prev => ({ ...prev, lastSync: new Date().toISOString() }));
            setSnackbar({ open: true, message: 'Settings synced to cloud', severity: 'success' });
          }}>
            Sync Now
          </Button>
        )}
      </DialogActions>
    </Dialog>
  );

  // List-based settings view
  const renderSettingsList = () => (
    <Paper>
      <List>
        <ListItem>
          <ListItemText 
            primary="API Keys" 
            secondary={`${getActiveProviders().length} configured`}
          />
          <ListItemSecondaryAction>
            <Tooltip title="Add API Key">
              <IconButton onClick={() => setOpenDialog('onboarding')}>
                <Add />
              </IconButton>
            </Tooltip>
            <Tooltip title="Edit API Keys">
              <IconButton onClick={() => setActiveTab(0)}>
                <Edit />
              </IconButton>
            </Tooltip>
          </ListItemSecondaryAction>
        </ListItem>
        
        <Divider />
        
        <ListItem>
          <ListItemText 
            primary="Trading Schedule" 
            secondary={scheduleSettings.autoTradingEnabled ? 'Automated trading enabled' : 'Manual trading only'}
          />
          <ListItemSecondaryAction>
            <Tooltip title="Configure Schedule">
              <IconButton onClick={() => setOpenDialog('schedule')}>
                <Schedule />
              </IconButton>
            </Tooltip>
          </ListItemSecondaryAction>
        </ListItem>
        
        <Divider />
        
        <ListItem>
          <ListItemText 
            primary="Language & Region" 
            secondary={`${languageSettings.language.toUpperCase()} - ${languageSettings.region}`}
          />
          <ListItemSecondaryAction>
            <Tooltip title="Change Language">
              <IconButton onClick={() => setOpenDialog('language')}>
                <Language />
              </IconButton>
            </Tooltip>
          </ListItemSecondaryAction>
        </ListItem>
        
        <Divider />
        
        <ListItem>
          <ListItemText 
            primary="Cloud Sync" 
            secondary={cloudSyncSettings.enabled ? 'Enabled' : 'Disabled'}
          />
          <ListItemSecondaryAction>
            {cloudSyncSettings.enabled ? 
              <CheckCircle color="success" /> : 
              <Warning color="warning" />
            }
            <Tooltip title="Configure Cloud Sync">
              <IconButton onClick={() => setOpenDialog('cloudsync')}>
                <CloudSync />
              </IconButton>
            </Tooltip>
          </ListItemSecondaryAction>
        </ListItem>
      </List>
    </Paper>
  );

  // Accordion-based settings view
  const renderSettingsAccordion = () => (
    <Box>
      <Accordion>
        <AccordionSummary expandIcon={<ExpandMore />}>
          <Typography variant="h6">API Configuration</Typography>
          {hasApiKeys ? <CheckCircle color="success" sx={{ ml: 1 }} /> : <Warning color="warning" sx={{ ml: 1 }} />}
        </AccordionSummary>
        <AccordionDetails>
          {renderAPIKeysTab()}
        </AccordionDetails>
      </Accordion>
      
      <Accordion>
        <AccordionSummary expandIcon={<ExpandMore />}>
          <Typography variant="h6">Trading Settings</Typography>
        </AccordionSummary>
        <AccordionDetails>
          {renderTradingTab()}
        </AccordionDetails>
      </Accordion>
      
      <Accordion>
        <AccordionSummary expandIcon={<ExpandMore />}>
          <Typography variant="h6">Notifications</Typography>
        </AccordionSummary>
        <AccordionDetails>
          {renderNotificationsTab()}
        </AccordionDetails>
      </Accordion>
      
      <Accordion>
        <AccordionSummary expandIcon={<ExpandMore />}>
          <Typography variant="h6">Advanced Settings</Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Grid container spacing={2}>
            <Grid item xs={12} md={4}>
              <Button
                fullWidth
                variant="outlined"
                startIcon={<Schedule />}
                onClick={() => setOpenDialog('schedule')}
              >
                Trading Schedule
              </Button>
            </Grid>
            <Grid item xs={12} md={4}>
              <Button
                fullWidth
                variant="outlined"
                startIcon={<Language />}
                onClick={() => setOpenDialog('language')}
              >
                Language & Region
              </Button>
            </Grid>
            <Grid item xs={12} md={4}>
              <Button
                fullWidth
                variant="outlined"
                startIcon={<CloudSync />}
                onClick={() => setOpenDialog('cloudsync')}
              >
                Cloud Sync
              </Button>
            </Grid>
          </Grid>
        </AccordionDetails>
      </Accordion>
    </Box>
  );

  const renderAPIKeysTab = () => (
    <ApiKeysTab
      settings={settings}
      updateSettings={updateSettings}
      showPasswords={showPasswords}
      setShowPasswords={setShowPasswords}
      saveApiKeyLocal={saveApiKeyLocal}
      testConnection={testConnection}
      testingConnection={testingConnection}
      connectionResults={connectionResults}
    />
  );

  const renderAPIKeysTabOld = () => (
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
                    variant="contained"
                    onClick={() => saveApiKeyLocal('alpaca', settings.apiKeys.alpaca)}
                    disabled={!settings.apiKeys.alpaca.keyId || !settings.apiKeys.alpaca.secretKey}
                    sx={{ mr: 1 }}
                  >
                    Save API Key
                  </Button>
                  <Button
                    variant="outlined"
                    onClick={() => testConnection('alpaca')}
                    disabled={testingConnection || !settings.apiKeys.alpaca.id}
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
                    variant="contained"
                    onClick={() => saveApiKeyLocal('polygon', settings.apiKeys.polygon)}
                    disabled={!settings.apiKeys.polygon.apiKey}
                    sx={{ mr: 1 }}
                  >
                    Save API Key
                  </Button>
                  <Button
                    variant="outlined"
                    onClick={() => testConnection('polygon')}
                    disabled={testingConnection || !settings.apiKeys.polygon.id}
                  >
                    Test Connection
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
    <TradingTab
      settings={settings}
      updateSettings={updateSettings}
    />
  );

  const renderTradingTabOld = () => (
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
      {/* Auto-trigger onboarding for new users */}
      {needsOnboarding() && !openDialog && (
        <Alert 
          severity="info" 
          action={
            <Button color="inherit" onClick={() => setOpenDialog('onboarding')}>
              Get Started
            </Button>
          }
          sx={{ mb: 2 }}
        >
          Welcome! Set up your API keys to get started with trading.
        </Alert>
      )}

      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 3 }}>
        <Typography variant="h5">
          <Settings sx={{ mr: 1, verticalAlign: 'middle' }} />
          Settings
        </Typography>
        
        <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
          {/* View Mode Toggle */}
          <Box sx={{ display: 'flex', mr: 2 }}>
            <Tooltip title="Tabs View">
              <IconButton 
                size="small"
                color={viewMode === 'tabs' ? 'primary' : 'default'}
                onClick={() => setViewMode('tabs')}
              >
                <Tabs fontSize="small" />
              </IconButton>
            </Tooltip>
            <Tooltip title="List View">
              <IconButton 
                size="small"
                color={viewMode === 'list' ? 'primary' : 'default'}
                onClick={() => setViewMode('list')}
              >
                <List fontSize="small" />
              </IconButton>
            </Tooltip>
            <Tooltip title="Accordion View">
              <IconButton 
                size="small"
                color={viewMode === 'accordion' ? 'primary' : 'default'}
                onClick={() => setViewMode('accordion')}
              >
                <ExpandMore fontSize="small" />
              </IconButton>
            </Tooltip>
          </Box>

          {/* Advanced Settings Toggle */}
          <Tooltip title="Advanced Settings">
            <IconButton 
              size="small"
              color={showAdvancedSettings ? 'primary' : 'default'}
              onClick={() => setShowAdvancedSettings(!showAdvancedSettings)}
            >
              <Settings fontSize="small" />
            </IconButton>
          </Tooltip>

          <Divider orientation="vertical" flexItem />
          
          {/* Action Buttons */}
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
            onClick={() => {
              // Save API keys to backend
              Object.keys(settings.apiKeys || {}).forEach(provider => {
                const apiKey = settings.apiKeys[provider];
                if (apiKey && apiKey.enabled && (apiKey.keyId || apiKey.apiKey)) {
                  saveApiKey(provider, apiKey);
                }
              });
              setUnsavedChanges(false);
              setSnackbar({ open: true, message: 'Settings saved successfully', severity: 'success' });
            }}
            disabled={!unsavedChanges}
            startIcon={<Save />}
          >
            Save Changes
          </Button>
        </Box>
      </Box>

      {/* Advanced Settings Panel */}
      {showAdvancedSettings && (
        <Card sx={{ mb: 3, bgcolor: 'background.paper' }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Advanced Features
            </Typography>
            <Grid container spacing={2}>
              <Grid item>
                <Button
                  variant="outlined"
                  startIcon={<Schedule />}
                  onClick={() => setOpenDialog('schedule')}
                >
                  Trading Schedule
                </Button>
              </Grid>
              <Grid item>
                <Button
                  variant="outlined"
                  startIcon={<Language />}
                  onClick={() => setOpenDialog('language')}
                >
                  Language & Region
                </Button>
              </Grid>
              <Grid item>
                <Button
                  variant="outlined"
                  startIcon={<CloudSync />}
                  onClick={() => setOpenDialog('cloudsync')}
                  color={cloudSyncSettings.enabled ? 'success' : 'primary'}
                >
                  Cloud Sync {cloudSyncSettings.enabled && <CheckCircle sx={{ ml: 1 }} fontSize="small" />}
                </Button>
              </Grid>
              <Grid item>
                <Button
                  variant="outlined"
                  startIcon={<Add />}
                  onClick={() => setOpenDialog('onboarding')}
                >
                  Add API Key
                </Button>
              </Grid>
            </Grid>
          </CardContent>
        </Card>
      )}

      {unsavedChanges && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Warning />
            You have unsaved changes. Don&apos;t forget to save your settings.
          </Box>
        </Alert>
      )}

      {/* Conditional Rendering Based on View Mode */}
      {viewMode === 'tabs' && (
        <>
          <Tabs value={activeTab} onChange={(e, newValue) => setActiveTab(newValue)} sx={{ mb: 3 }}>
            <Tab label="API Keys" icon={<VpnKey />} />
            <Tab label="Trading" icon={<ShowChart />} />
            <Tab label="Notifications" icon={<Notifications />} />
            <Tab label="Display" icon={<ColorLens />} />
          </Tabs>

          {activeTab === 0 && renderAPIKeysTab()}
          {activeTab === 1 && renderTradingTab()}
          {activeTab === 2 && renderNotificationsTab()}
          {activeTab === 3 && renderDisplayTab()}
        </>
      )}

      {viewMode === 'list' && renderSettingsList()}

      {viewMode === 'accordion' && renderSettingsAccordion()}

      {/* All Dialog Components */}
      {renderOnboardingDialog()}
      {renderScheduleDialog()}
      {renderLanguageDialog()}
      {renderCloudSyncDialog()}

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