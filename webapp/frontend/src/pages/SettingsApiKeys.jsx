import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import secureLogger from '../utils/secureLogger.js';
import {
  Box,
  Container,
  Typography,
  Grid,
  Card,
  CardContent,
  CardHeader,
  Button,
  TextField,
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Switch,
  FormControlLabel,
  Alert,
  CircularProgress,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Chip,
  Tooltip,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  Divider
} from '@mui/material';
import {
  Add,
  Delete,
  Edit,
  Visibility,
  VisibilityOff,
  PlayArrow as TestIcon,
  CloudDownload as ImportIcon,
  Security,
  Key,
  Warning,
  CheckCircle,
  Info,
  ExpandMore,
  AccountBalance,
  TrendingUp,
  Psychology,
  DataObject,
  Api,
  Refresh
} from '@mui/icons-material';
import { 
  getApiKeys, 
  addApiKey, 
  updateApiKey, 
  deleteApiKey, 
  testApiKeyConnection,
  importPortfolioFromBroker 
} from '../services/api';

const SettingsApiKeys = () => {
  const { user } = useAuth();
  const [apiKeys, setApiKeys] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [addDialogOpen, setAddDialogOpen] = useState(false);
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [selectedKey, setSelectedKey] = useState(null);
  const [testing, setTesting] = useState({});
  const [importing, setImporting] = useState({});

  // Add/Edit form state
  const [formData, setFormData] = useState({
    provider: '',
    apiKey: '',
    apiSecret: '',
    isSandbox: true,
    description: ''
  });

  const [showSecrets, setShowSecrets] = useState({});

  const supportedProviders = [
    {
      id: 'alpaca',
      name: 'Alpaca Markets',
      description: 'Commission-free stock trading with API access - Paper & Live trading',
      features: ['Portfolio Import', 'Real-time Data', 'Paper Trading', 'Live Trading'],
      icon: <AccountBalance />,
      color: '#FFD700'
    },
    {
      id: 'td_ameritrade',
      name: 'TD Ameritrade',
      description: 'Professional trading platform with comprehensive API (Legacy - Migrating to Schwab)',
      features: ['Portfolio Import', 'Real-time Data', 'Options Trading', 'Advanced Orders'],
      icon: <TrendingUp />,
      color: '#00C851'
    }
  ];

  useEffect(() => {
    fetchApiKeys();
  }, []);

  const fetchApiKeys = async () => {
    try {
      setLoading(true);
      const response = await getApiKeys();
      setApiKeys(response?.apiKeys || []);
      
      // Handle new error structure with guidance
      if (response?.setupRequired || response?.encryptionEnabled === false) {
        // Clear previous errors and show setup guidance
        setError(null);
        import('../utils/secureLogger.js').then(({ info }) => 
          info('API Key service setup required', { setupRequired: response?.setupRequired, encryptionEnabled: response?.encryptionEnabled })
        );
      } else if (response?.note && response.note.includes('Database connectivity issue')) {
        setError(`API keys may not be visible due to database connectivity issues. ${response.note}`);
      } else if (response?.note) {
        console.warn('API Keys note:', response.note);
      }
    } catch (err) {
      // Handle enhanced error structure
      if (err.response?.data?.setupRequired) {
        console.log('Setup required error - data received');
        setError(null); // Clear error to show guidance instead
      } else if (err.response?.data?.guidance) {
        const guidance = err.response.data.guidance;
        setError(`${guidance.title}: ${guidance.description}`);
      } else {
        setError(err.response?.data?.message || 'Failed to fetch API keys');
      }
      console.error('API keys fetch error:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleAddApiKey = async () => {
    try {
      if (!formData.provider || !formData.apiKey) {
        setError('Please fill in all required fields');
        return;
      }

      await addApiKey(formData);
      setAddDialogOpen(false);
      setFormData({
        provider: '',
        apiKey: '',
        apiSecret: '',
        isSandbox: true,
        description: ''
      });
      setSuccess('API key added successfully!');
      // Add a delay before fetching to allow database write to complete
      setTimeout(() => {
        fetchApiKeys();
      }, 1000);
    } catch (err) {
      const errorMessage = err.response?.data?.error || err.response?.data?.message || err.message || 'Failed to add API key';
      setError(`Failed to add API key: ${errorMessage}`);
      console.error('Add API key error:', err);
    }
  };

  const handleEditApiKey = async () => {
    try {
      await updateApiKey(selectedKey.id, {
        description: formData.description,
        isSandbox: formData.isSandbox
      });
      setEditDialogOpen(false);
      setSelectedKey(null);
      setSuccess('API key updated successfully');
      fetchApiKeys();
    } catch (err) {
      setError('Failed to update API key');
      console.error('Update API key error:', err);
    }
  };

  const handleDeleteApiKey = async (keyId) => {
    try {
      await deleteApiKey(keyId);
      setSuccess('API key deleted successfully');
      fetchApiKeys();
    } catch (err) {
      setError('Failed to delete API key');
      console.error('Delete API key error:', err);
    }
  };

  const handleTestConnection = async (keyId, provider) => {
    try {
      setTesting(prev => ({ ...prev, [keyId]: true }));
      const result = await testApiKeyConnection(keyId);
      
      if (result.success) {
        setSuccess(`${provider} connection test successful`);
      } else {
        setError(`${provider} connection test failed: ${result.error}`);
      }
    } catch (err) {
      setError(`Connection test failed: ${err.message}`);
    } finally {
      setTesting(prev => ({ ...prev, [keyId]: false }));
    }
  };

  const handleImportPortfolio = async (keyId, provider) => {
    try {
      setImporting(prev => ({ ...prev, [keyId]: true }));
      const result = await importPortfolioFromBroker(provider);
      
      if (result.success) {
        setSuccess(`Portfolio imported successfully from ${provider}`);
      } else {
        setError(`Portfolio import failed: ${result.error}`);
      }
    } catch (err) {
      setError(`Portfolio import failed: ${err.message}`);
    } finally {
      setImporting(prev => ({ ...prev, [keyId]: false }));
    }
  };

  const toggleShowSecret = (keyId) => {
    setShowSecrets(prev => ({
      ...prev,
      [keyId]: !prev[keyId]
    }));
  };

  const getProviderInfo = (providerId) => {
    return supportedProviders.find(p => p.id === providerId) || {
      name: providerId,
      description: 'External API provider',
      features: [],
      icon: <Api />,
      color: '#666666'
    };
  };

  const maskApiKey = (key) => {
    if (!key) return '';
    if (key.length <= 8) return '*'.repeat(key.length);
    return key.substring(0, 4) + '*'.repeat(key.length - 8) + key.substring(key.length - 4);
  };

  if (loading) {
    return (
      <Container maxWidth="lg">
        <Box display="flex" justifyContent="center" alignItems="center" minHeight="60vh">
          <CircularProgress />
        </Box>
      </Container>
    );
  }

  return (
    <Container maxWidth="lg">
      <Box sx={{ mb: 4 }}>
        <Typography variant="h4" gutterBottom>
          API Keys & Credentials
        </Typography>
        <Typography variant="body1" color="text.secondary">
          Manage your broker connections and data provider credentials
        </Typography>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 3 }} onClose={() => setError(null)}>
          {String(error)}
        </Alert>
      )}

      {success && (
        <Alert severity="success" sx={{ mb: 3 }} onClose={() => setSuccess(null)}>
          {success}
        </Alert>
      )}

      {/* Security Notice */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Box sx={{ display: 'flex', alignItems: 'flex-start' }}>
            <Security sx={{ mr: 2, mt: 0.5, color: 'primary.main' }} />
            <Box>
              <Typography variant="h6" gutterBottom>
                Security & Encryption
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Your API keys are encrypted using AES-256-GCM encryption before storage. 
                We never store your credentials in plain text and they are only decrypted 
                when needed for API calls. Your data is secure and isolated from other users.
              </Typography>
            </Box>
          </Box>
        </CardContent>
      </Card>

      {/* Add API Key Button */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Typography variant="h6">
          Your API Keys ({apiKeys.length})
        </Typography>
        <Box sx={{ display: 'flex', gap: 2 }}>
          <Button
            variant="outlined"
            startIcon={<Refresh />}
            onClick={fetchApiKeys}
            disabled={loading}
          >
            Refresh
          </Button>
          <Button
            variant="contained"
            startIcon={<Add />}
            onClick={() => setAddDialogOpen(true)}
          >
            Add API Key
          </Button>
        </Box>
      </Box>

      {/* API Keys Table */}
      {apiKeys.length > 0 ? (
        <Card>
          <TableContainer>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>Provider</TableCell>
                  <TableCell>Description</TableCell>
                  <TableCell>API Key</TableCell>
                  <TableCell>Environment</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell>Last Used</TableCell>
                  <TableCell align="center">Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {apiKeys.map((key) => {
                  const provider = getProviderInfo(key.provider);
                  return (
                    <TableRow key={key.id}>
                      <TableCell>
                        <Box sx={{ display: 'flex', alignItems: 'center' }}>
                          <Box sx={{ color: provider.color, mr: 1 }}>
                            {provider.icon}
                          </Box>
                          <Box>
                            <Typography variant="body2" fontWeight="bold">
                              {provider.name}
                            </Typography>
                            <Typography variant="caption" color="text.secondary">
                              {provider.description}
                            </Typography>
                          </Box>
                        </Box>
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2">
                          {key.description || 'No description'}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        <Box sx={{ display: 'flex', alignItems: 'center' }}>
                          <Typography variant="body2" fontFamily="monospace">
                            {showSecrets[key.id] ? key.apiKey : maskApiKey(key.apiKey)}
                          </Typography>
                          <IconButton
                            size="small"
                            onClick={() => toggleShowSecret(key.id)}
                          >
                            {showSecrets[key.id] ? <VisibilityOff /> : <Visibility />}
                          </IconButton>
                        </Box>
                      </TableCell>
                      <TableCell>
                        <Chip 
                          label={key.isSandbox ? 'Paper' : 'Live'} 
                          color={key.isSandbox ? 'warning' : 'success'}
                          size="small"
                        />
                      </TableCell>
                      <TableCell>
                        <Chip 
                          label={key.isActive ? 'Active' : 'Inactive'} 
                          color={key.isActive ? 'success' : 'default'}
                          size="small"
                        />
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2" color="text.secondary">
                          {key.lastUsed ? new Date(key.lastUsed).toLocaleDateString() : 'Never'}
                        </Typography>
                      </TableCell>
                      <TableCell align="center">
                        <Box sx={{ display: 'flex', gap: 1 }}>
                          <Tooltip title="Test Connection">
                            <IconButton
                              size="small"
                              onClick={() => handleTestConnection(key.id, provider.name)}
                              disabled={testing[key.id]}
                            >
                              {testing[key.id] ? <CircularProgress size={16} /> : <TestIcon />}
                            </IconButton>
                          </Tooltip>
                          {provider.features.includes('Portfolio Import') && (
                            <Tooltip title="Import Portfolio">
                              <IconButton
                                size="small"
                                onClick={() => handleImportPortfolio(key.id, key.provider)}
                                disabled={importing[key.id]}
                              >
                                {importing[key.id] ? <CircularProgress size={16} /> : <ImportIcon />}
                              </IconButton>
                            </Tooltip>
                          )}
                          <Tooltip title="Edit">
                            <IconButton
                              size="small"
                              onClick={() => {
                                setSelectedKey(key);
                                setFormData({
                                  provider: key.provider,
                                  description: key.description || '',
                                  isSandbox: key.isSandbox
                                });
                                setEditDialogOpen(true);
                              }}
                            >
                              <Edit />
                            </IconButton>
                          </Tooltip>
                          <Tooltip title="Delete">
                            <IconButton
                              size="small"
                              color="error"
                              onClick={() => handleDeleteApiKey(key.id)}
                            >
                              <Delete />
                            </IconButton>
                          </Tooltip>
                        </Box>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </TableContainer>
        </Card>
      ) : (
        <Card>
          <CardContent sx={{ textAlign: 'center', py: 6 }}>
            <Key sx={{ fontSize: 64, color: 'text.secondary', mb: 2 }} />
            <Typography variant="h6" gutterBottom>
              No API Keys Added
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
              Add your first API key to start importing portfolio data and accessing real-time market information.
            </Typography>
            <Button
              variant="contained"
              startIcon={<Add />}
              onClick={() => setAddDialogOpen(true)}
            >
              Add Your First API Key
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Supported Providers */}
      <Card sx={{ mt: 4 }}>
        <CardHeader title="Supported Providers" />
        <CardContent>
          <Grid container spacing={2}>
            {supportedProviders.map((provider) => (
              <Grid item xs={12} md={6} key={provider.id}>
                <Card variant="outlined">
                  <CardContent>
                    <Box sx={{ display: 'flex', alignItems: 'flex-start', mb: 2 }}>
                      <Box sx={{ color: provider.color, mr: 2 }}>
                        {provider.icon}
                      </Box>
                      <Box>
                        <Typography variant="h6" gutterBottom>
                          {provider.name}
                        </Typography>
                        <Typography variant="body2" color="text.secondary" gutterBottom>
                          {provider.description}
                        </Typography>
                      </Box>
                    </Box>
                    <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                      {provider.features.map((feature) => (
                        <Chip key={feature} label={feature} size="small" />
                      ))}
                    </Box>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>
        </CardContent>
      </Card>

      {/* Add API Key Dialog */}
      <Dialog open={addDialogOpen} onClose={() => setAddDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Add API Key</DialogTitle>
        <DialogContent>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 1 }}>
            <FormControl fullWidth>
              <InputLabel>Provider</InputLabel>
              <Select
                value={formData.provider}
                label="Provider"
                onChange={(e) => setFormData({ ...formData, provider: e.target.value })}
              >
                {supportedProviders.map((provider) => (
                  <MenuItem key={provider.id} value={provider.id}>
                    <Box sx={{ display: 'flex', alignItems: 'center' }}>
                      <Box sx={{ color: provider.color, mr: 1 }}>
                        {provider.icon}
                      </Box>
                      {provider.name}
                    </Box>
                  </MenuItem>
                ))}
              </Select>
            </FormControl>

            <TextField
              fullWidth
              label="API Key"
              value={formData.apiKey}
              onChange={(e) => setFormData({ ...formData, apiKey: e.target.value })}
              required
              type="password"
            />

            <TextField
              fullWidth
              label="API Secret (if required)"
              value={formData.apiSecret}
              onChange={(e) => setFormData({ ...formData, apiSecret: e.target.value })}
              type="password"
            />

            <TextField
              fullWidth
              label="Description"
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              placeholder="e.g., Main trading account"
            />

            <FormControlLabel
              control={
                <Switch
                  checked={formData.isSandbox}
                  onChange={(e) => setFormData({ ...formData, isSandbox: e.target.checked })}
                />
              }
              label="Paper Trading Environment"
            />

            <Alert severity="info">
              <Typography variant="body2">
                Start with paper trading to test the connection safely. 
                Your API keys will be encrypted before storage.
              </Typography>
            </Alert>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAddDialogOpen(false)}>Cancel</Button>
          <Button onClick={handleAddApiKey} variant="contained">Add API Key</Button>
        </DialogActions>
      </Dialog>

      {/* Edit API Key Dialog */}
      <Dialog open={editDialogOpen} onClose={() => setEditDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Edit API Key</DialogTitle>
        <DialogContent>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 1 }}>
            <TextField
              fullWidth
              label="Provider"
              value={getProviderInfo(formData.provider).name}
              disabled
            />

            <TextField
              fullWidth
              label="Description"
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              placeholder="e.g., Main trading account"
            />

            <FormControlLabel
              control={
                <Switch
                  checked={formData.isSandbox}
                  onChange={(e) => setFormData({ ...formData, isSandbox: e.target.checked })}
                />
              }
              label="Paper Trading Environment"
            />
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditDialogOpen(false)}>Cancel</Button>
          <Button onClick={handleEditApiKey} variant="contained">Save Changes</Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
};

export default SettingsApiKeys;