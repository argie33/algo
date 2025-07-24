import React, { useState, useEffect } from 'react';
import {
  Card,
  CardContent,
  Typography,
  TextField,
  Button,
  Box,
  Grid,
  Alert,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Chip,
  IconButton,
  Tooltip,
  LinearProgress,
  Switch,
  FormControlLabel,
  List,
  ListItem,
  ListItemText,
  ListItemSecondaryAction,
  Divider,
  Paper
} from '@mui/material';
import {
  Add as AddIcon,
  Edit as EditIcon,
  Delete as DeleteIcon,
  Visibility as VisibilityIcon,
  VisibilityOff as VisibilityOffIcon,
  CheckCircle as CheckCircleIcon,
  Error as ErrorIcon,
  Warning as WarningIcon,
  Refresh as RefreshIcon,
  Security as SecurityIcon,
  TrendingUp as TrendingUpIcon,
  AccountBalance as AccountBalanceIcon
} from '@mui/icons-material';

const API_PROVIDERS = {
  alpaca: {
    name: 'Alpaca Trading',
    description: 'Commission-free stock trading API',
    icon: TrendingUpIcon,
    fields: [
      { key: 'alpaca_key_id', label: 'API Key ID', type: 'text', required: true },
      { key: 'alpaca_secret_key', label: 'Secret Key', type: 'password', required: true }
    ],
    testEndpoint: '/api/alpaca/account',
    website: 'https://alpaca.markets',
    color: '#FFD700'
  },
  polygon: {
    name: 'Polygon.io',
    description: 'Real-time and historical market data',
    icon: TrendingUpIcon,
    fields: [
      { key: 'polygon_api_key', label: 'API Key', type: 'password', required: true }
    ],
    testEndpoint: '/api/polygon/reference/tickers',
    website: 'https://polygon.io',
    color: '#4CAF50'
  },
  finnhub: {
    name: 'Finnhub',
    description: 'Stock prices and company fundamentals',
    icon: AccountBalanceIcon,
    fields: [
      { key: 'finnhub_api_key', label: 'API Key', type: 'password', required: true }
    ],
    testEndpoint: '/api/finnhub/stock/profile2',
    website: 'https://finnhub.io',
    color: '#2196F3'
  }
};

const APIKeyManager = ({ userId, onAPIKeysChange }) => {
  const [apiKeys, setApiKeys] = useState({});
  const [connectionStatus, setConnectionStatus] = useState({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState({});
  const [testing, setTesting] = useState({});
  const [showDialog, setShowDialog] = useState(false);
  const [currentProvider, setCurrentProvider] = useState(null);
  const [formData, setFormData] = useState({});
  const [showSecrets, setShowSecrets] = useState({});
  const [alerts, setAlerts] = useState([]);
  const [autoValidation, setAutoValidation] = useState(true);

  useEffect(() => {
    loadAPIKeys();
  }, [userId]);

  useEffect(() => {
    if (autoValidation) {
      const interval = setInterval(() => {
        validateAllConnections();
      }, 30000); // Check every 30 seconds

      return () => clearInterval(interval);
    }
  }, [apiKeys, autoValidation]);

  const loadAPIKeys = async () => {
    if (!userId) return;
    
    setLoading(true);
    try {
      const response = await fetch(`/api/settings/api/api-keys/${userId}`);
      if (response.ok) {
        const data = await response.json();
        setApiKeys(data.apiKeys || {});
        setConnectionStatus(data.connectionStatus || {});
      } else {
        throw new Error('Failed to load API keys');
      }
    } catch (error) {
      console.error('Error loading API keys:', error);
      addAlert('error', 'Failed to load API keys');
    } finally {
      setLoading(false);
    }
  };

  const saveAPIKey = async (provider, keyData) => {
    setSaving(prev => ({ ...prev, [provider]: true }));
    try {
      const response = await fetch(`/api/settings/api/api-keys/${userId}/${provider}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(keyData)
      });

      if (response.ok) {
        const result = await response.json();
        setApiKeys(prev => ({ ...prev, [provider]: result.data }));
        addAlert('success', `${API_PROVIDERS[provider].name} API key saved successfully`);
        
        // Test connection after saving
        await testConnection(provider);
        
        if (onAPIKeysChange) {
          onAPIKeysChange({ ...apiKeys, [provider]: result.data });
        }
      } else {
        throw new Error('Failed to save API key');
      }
    } catch (error) {
      console.error('Error saving API key:', error);
      addAlert('error', `Failed to save ${API_PROVIDERS[provider].name} API key`);
    } finally {
      setSaving(prev => ({ ...prev, [provider]: false }));
    }
  };

  const deleteAPIKey = async (provider) => {
    if (!window.confirm(`Are you sure you want to delete your ${API_PROVIDERS[provider].name} API key?`)) {
      return;
    }

    setSaving(prev => ({ ...prev, [provider]: true }));
    try {
      const response = await fetch(`/api/settings/api/api-keys/${userId}/${provider}`, {
        method: 'DELETE'
      });

      if (response.ok) {
        setApiKeys(prev => {
          const updated = { ...prev };
          delete updated[provider];
          return updated;
        });
        setConnectionStatus(prev => {
          const updated = { ...prev };
          delete updated[provider];
          return updated;
        });
        addAlert('info', `${API_PROVIDERS[provider].name} API key deleted`);
        
        if (onAPIKeysChange) {
          const updated = { ...apiKeys };
          delete updated[provider];
          onAPIKeysChange(updated);
        }
      } else {
        throw new Error('Failed to delete API key');
      }
    } catch (error) {
      console.error('Error deleting API key:', error);
      addAlert('error', `Failed to delete ${API_PROVIDERS[provider].name} API key`);
    } finally {
      setSaving(prev => ({ ...prev, [provider]: false }));
    }
  };

  const testConnection = async (provider) => {
    setTesting(prev => ({ ...prev, [provider]: true }));
    try {
      const response = await fetch(`/api/settings/api/api-keys/${userId}/${provider}/test`, {
        method: 'POST'
      });

      if (response.ok) {
        const result = await response.json();
        setConnectionStatus(prev => ({
          ...prev,
          [provider]: {
            status: result.success ? 'connected' : 'error',
            message: result.message,
            lastTested: new Date().toISOString(),
            responseTime: result.responseTime
          }
        }));
        addAlert(
          result.success ? 'success' : 'error',
          `${API_PROVIDERS[provider].name}: ${result.message}`
        );
      } else {
        throw new Error('Connection test failed');
      }
    } catch (error) {
      console.error('Error testing connection:', error);
      setConnectionStatus(prev => ({
        ...prev,
        [provider]: {
          status: 'error',
          message: 'Connection test failed',
          lastTested: new Date().toISOString()
        }
      }));
      addAlert('error', `${API_PROVIDERS[provider].name} connection test failed`);
    } finally {
      setTesting(prev => ({ ...prev, [provider]: false }));
    }
  };

  const validateAllConnections = async () => {
    for (const provider of Object.keys(apiKeys)) {
      if (apiKeys[provider] && !testing[provider]) {
        await testConnection(provider);
      }
    }
  };

  const addAlert = (severity, message) => {
    const id = Date.now();
    setAlerts(prev => [...prev, { id, severity, message }]);
    setTimeout(() => {
      setAlerts(prev => prev.filter(alert => alert.id !== id));
    }, 5000);
  };

  const openDialog = (provider) => {
    setCurrentProvider(provider);
    setFormData(apiKeys[provider] || {});
    setShowDialog(true);
  };

  const closeDialog = () => {
    setShowDialog(false);
    setCurrentProvider(null);
    setFormData({});
  };

  const handleSave = async () => {
    if (!currentProvider) return;
    
    await saveAPIKey(currentProvider, formData);
    closeDialog();
  };

  const getStatusIcon = (provider) => {
    const status = connectionStatus[provider]?.status;
    switch (status) {
      case 'connected':
        return <CheckCircleIcon color="success" />;
      case 'error':
        return <ErrorIcon color="error" />;
      case 'warning':
        return <WarningIcon color="warning" />;
      default:
        return <WarningIcon color="disabled" />;
    }
  };

  const getStatusColor = (provider) => {
    const status = connectionStatus[provider]?.status;
    switch (status) {
      case 'connected':
        return 'success';
      case 'error':
        return 'error';
      case 'warning':
        return 'warning';
      default:
        return 'default';
    }
  };

  const maskApiKey = (key) => {
    if (!key) return '';
    if (key.length <= 8) return '*'.repeat(key.length);
    return key.substring(0, 4) + '*'.repeat(key.length - 8) + key.substring(key.length - 4);
  };

  return (
    <Box>
      {/* Header */}
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Box>
          <Typography variant="h5" gutterBottom>
            <SecurityIcon sx={{ mr: 1, verticalAlign: 'middle' }} />
            API Key Management
          </Typography>
          <Typography variant="body2" color="textSecondary">
            Securely manage your trading and market data API connections
          </Typography>
        </Box>
        <Box>
          <FormControlLabel
            control={
              <Switch
                checked={autoValidation}
                onChange={(e) => setAutoValidation(e.target.checked)}
              />
            }
            label="Auto-validate"
          />
          <Tooltip title="Refresh all connections">
            <IconButton onClick={validateAllConnections} disabled={loading}>
              <RefreshIcon />
            </IconButton>
          </Tooltip>
        </Box>
      </Box>

      {/* Alerts */}
      {alerts.map((alert) => (
        <Alert key={alert.id} severity={alert.severity} sx={{ mb: 2 }}>
          {alert.message}
        </Alert>
      ))}

      {/* Loading */}
      {loading && <LinearProgress sx={{ mb: 2 }} />}

      {/* API Providers */}
      <Grid container spacing={3}>
        {Object.entries(API_PROVIDERS).map(([provider, config]) => {
          const isConfigured = !!apiKeys[provider];
          const status = connectionStatus[provider];
          const IconComponent = config.icon;

          return (
            <Grid item xs={12} md={6} lg={4} key={provider}>
              <Card 
                sx={{ 
                  height: '100%', 
                  border: isConfigured ? `2px solid ${config.color}` : '2px solid transparent',
                  '&:hover': { boxShadow: 6 }
                }}
              >
                <CardContent>
                  <Box display="flex" alignItems="center" mb={2}>
                    <IconComponent sx={{ color: config.color, mr: 1 }} />
                    <Typography variant="h6" component="div" sx={{ flexGrow: 1 }}>
                      {config.name}
                    </Typography>
                    {getStatusIcon(provider)}
                  </Box>

                  <Typography variant="body2" color="textSecondary" paragraph>
                    {config.description}
                  </Typography>

                  {isConfigured && (
                    <Paper sx={{ p: 2, mb: 2, bgcolor: 'grey.50' }}>
                      <Typography variant="body2" gutterBottom>
                        <strong>Status:</strong>
                      </Typography>
                      <Chip
                        label={status?.status || 'Unknown'}
                        color={getStatusColor(provider)}
                        size="small"
                        sx={{ mb: 1 }}
                      />
                      {status?.message && (
                        <Typography variant="caption" display="block">
                          {status.message}
                        </Typography>
                      )}
                      {status?.lastTested && (
                        <Typography variant="caption" display="block" color="textSecondary">
                          Last tested: {new Date(status.lastTested).toLocaleString()}
                        </Typography>
                      )}
                      {status?.responseTime && (
                        <Typography variant="caption" display="block" color="textSecondary">
                          Response time: {status.responseTime}ms
                        </Typography>
                      )}
                    </Paper>
                  )}

                  {isConfigured && (
                    <List dense>
                      {config.fields.map((field) => {
                        const value = apiKeys[provider]?.[field.key];
                        return (
                          <ListItem key={field.key} sx={{ px: 0 }}>
                            <ListItemText
                              primary={field.label}
                              secondary={
                                value
                                  ? showSecrets[`${provider}-${field.key}`]
                                    ? value
                                    : maskApiKey(value)
                                  : 'Not configured'
                              }
                            />
                            {value && (
                              <ListItemSecondaryAction>
                                <IconButton
                                  size="small"
                                  onClick={() => 
                                    setShowSecrets(prev => ({
                                      ...prev,
                                      [`${provider}-${field.key}`]: !prev[`${provider}-${field.key}`]
                                    }))
                                  }
                                >
                                  {showSecrets[`${provider}-${field.key}`] ? 
                                    <VisibilityOffIcon fontSize="small" /> : 
                                    <VisibilityIcon fontSize="small" />
                                  }
                                </IconButton>
                              </ListItemSecondaryAction>
                            )}
                          </ListItem>
                        );
                      })}
                    </List>
                  )}

                  <Box display="flex" gap={1} mt={2}>
                    <Button
                      variant={isConfigured ? "outlined" : "contained"}
                      startIcon={isConfigured ? <EditIcon /> : <AddIcon />}
                      onClick={() => openDialog(provider)}
                      disabled={saving[provider]}
                      fullWidth
                    >
                      {isConfigured ? 'Edit' : 'Add'} Keys
                    </Button>
                    
                    {isConfigured && (
                      <>
                        <Button
                          variant="outlined"
                          startIcon={<RefreshIcon />}
                          onClick={() => testConnection(provider)}
                          disabled={testing[provider] || saving[provider]}
                        >
                          Test
                        </Button>
                        <IconButton
                          color="error"
                          onClick={() => deleteAPIKey(provider)}
                          disabled={saving[provider]}
                        >
                          <DeleteIcon />
                        </IconButton>
                      </>
                    )}
                  </Box>
                </CardContent>
              </Card>
            </Grid>
          );
        })}
      </Grid>

      {/* Configuration Dialog */}
      <Dialog open={showDialog} onClose={closeDialog} maxWidth="sm" fullWidth>
        <DialogTitle>
          {currentProvider && (
            <>
              Configure {API_PROVIDERS[currentProvider].name}
              <Typography variant="body2" color="textSecondary">
                {API_PROVIDERS[currentProvider].description}
              </Typography>
            </>
          )}
        </DialogTitle>
        <DialogContent>
          {currentProvider && (
            <Box mt={2}>
              <Alert severity="info" sx={{ mb: 3 }}>
                <Typography variant="body2">
                  Your API keys are encrypted and stored securely. They are only used to authenticate 
                  with {API_PROVIDERS[currentProvider].name} on your behalf.
                </Typography>
              </Alert>

              {API_PROVIDERS[currentProvider].fields.map((field) => (
                <TextField
                  key={field.key}
                  fullWidth
                  label={field.label}
                  type={showSecrets[`dialog-${field.key}`] ? 'text' : field.type}
                  value={formData[field.key] || ''}
                  onChange={(e) => setFormData(prev => ({ ...prev, [field.key]: e.target.value }))}
                  required={field.required}
                  margin="normal"
                  InputProps={field.type === 'password' ? {
                    endAdornment: (
                      <IconButton
                        onClick={() => 
                          setShowSecrets(prev => ({
                            ...prev,
                            [`dialog-${field.key}`]: !prev[`dialog-${field.key}`]
                          }))
                        }
                      >
                        {showSecrets[`dialog-${field.key}`] ? 
                          <VisibilityOffIcon /> : <VisibilityIcon />
                        }
                      </IconButton>
                    )
                  } : undefined}
                />
              ))}

              <Box mt={2}>
                <Typography variant="body2" color="textSecondary">
                  Get your API keys from:{' '}
                  <a 
                    href={API_PROVIDERS[currentProvider].website} 
                    target="_blank" 
                    rel="noopener noreferrer"
                  >
                    {API_PROVIDERS[currentProvider].website}
                  </a>
                </Typography>
              </Box>
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={closeDialog}>Cancel</Button>
          <Button 
            onClick={handleSave} 
            variant="contained"
            disabled={saving[currentProvider]}
          >
            {saving[currentProvider] ? 'Saving...' : 'Save & Test'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default APIKeyManager;