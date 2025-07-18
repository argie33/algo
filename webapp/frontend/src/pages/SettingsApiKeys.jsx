import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
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
        console.log('API Key service setup required:', response);
      } else if (response?.note && response.note.includes('Database connectivity issue')) {
        setError(`API keys may not be visible due to database connectivity issues. ${response.note}`);
      } else if (response?.note) {
        console.warn('API Keys note:', response.note);
      }
    } catch (err) {
      // Handle enhanced error structure
      if (err.response?.data?.setupRequired) {
        console.log('Setup required error:', err.response.data);
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
      <div className="container mx-auto" maxWidth="lg">
        <div  display="flex" justifyContent="center" alignItems="center" minHeight="60vh">
          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" />
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto" maxWidth="lg">
      <div  sx={{ mb: 4 }}>
        <div  variant="h4" gutterBottom>
          API Keys & Credentials
        </div>
        <div  variant="body1" color="text.secondary">
          Manage your broker connections and data provider credentials
        </div>
      </div>

      {error && (
        <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error" sx={{ mb: 3 }} onClose={() => setError(null)}>
          {String(error)}
        </div>
      )}

      {success && (
        <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="success" sx={{ mb: 3 }} onClose={() => setSuccess(null)}>
          {success}
        </div>
      )}

      {/* Security Notice */}
      <div className="bg-white shadow-md rounded-lg" sx={{ mb: 3 }}>
        <div className="bg-white shadow-md rounded-lg"Content>
          <div  sx={{ display: 'flex', alignItems: 'flex-start' }}>
            <Security sx={{ mr: 2, mt: 0.5, color: 'primary.main' }} />
            <div>
              <div  variant="h6" gutterBottom>
                Security & Encryption
              </div>
              <div  variant="body2" color="text.secondary">
                Your API keys are encrypted using AES-256-GCM encryption before storage. 
                We never store your credentials in plain text and they are only decrypted 
                when needed for API calls. Your data is secure and isolated from other users.
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Add API Key Button */}
      <div  sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <div  variant="h6">
          Your API Keys ({apiKeys.length})
        </div>
        <div  sx={{ display: 'flex', gap: 2 }}>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
            variant="outlined"
            startIcon={<Refresh />}
            onClick={fetchApiKeys}
            disabled={loading}
          >
            Refresh
          </button>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
            variant="contained"
            startIcon={<Add />}
            onClick={() => setAddDialogOpen(true)}
          >
            Add API Key
          </button>
        </div>
      </div>

      {/* API Keys Table */}
      {apiKeys.length > 0 ? (
        <div className="bg-white shadow-md rounded-lg">
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Provider</td>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Description</td>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>API Key</td>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Environment</td>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Status</td>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Last Used</td>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center">Actions</td>
                </tr>
              </thead>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
                {apiKeys.map((key) => {
                  const provider = getProviderInfo(key.provider);
                  return (
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={key.id}>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                        <div  sx={{ display: 'flex', alignItems: 'center' }}>
                          <div  sx={{ color: provider.color, mr: 1 }}>
                            {provider.icon}
                          </div>
                          <div>
                            <div  variant="body2" fontWeight="bold">
                              {provider.name}
                            </div>
                            <div  variant="caption" color="text.secondary">
                              {provider.description}
                            </div>
                          </div>
                        </div>
                      </td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                        <div  variant="body2">
                          {key.description || 'No description'}
                        </div>
                      </td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                        <div  sx={{ display: 'flex', alignItems: 'center' }}>
                          <div  variant="body2" fontFamily="monospace">
                            {showSecrets[key.id] ? key.apiKey : maskApiKey(key.apiKey)}
                          </div>
                          <button className="p-2 rounded-full hover:bg-gray-100"
                            size="small"
                            onClick={() => toggleShowSecret(key.id)}
                          >
                            {showSecrets[key.id] ? <VisibilityOff /> : <Visibility />}
                          </button>
                        </div>
                      </td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                          label={key.isSandbox ? 'Paper' : 'Live'} 
                          color={key.isSandbox ? 'warning' : 'success'}
                          size="small"
                        />
                      </td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                          label={key.isActive ? 'Active' : 'Inactive'} 
                          color={key.isActive ? 'success' : 'default'}
                          size="small"
                        />
                      </td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                        <div  variant="body2" color="text.secondary">
                          {key.lastUsed ? new Date(key.lastUsed).toLocaleDateString() : 'Never'}
                        </div>
                      </td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center">
                        <div  sx={{ display: 'flex', gap: 1 }}>
                          <div  title="Test Connection">
                            <button className="p-2 rounded-full hover:bg-gray-100"
                              size="small"
                              onClick={() => handleTestConnection(key.id, provider.name)}
                              disabled={testing[key.id]}
                            >
                              {testing[key.id] ? <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" size={16} /> : <TestIcon />}
                            </button>
                          </div>
                          {provider.features.includes('Portfolio Import') && (
                            <div  title="Import Portfolio">
                              <button className="p-2 rounded-full hover:bg-gray-100"
                                size="small"
                                onClick={() => handleImportPortfolio(key.id, key.provider)}
                                disabled={importing[key.id]}
                              >
                                {importing[key.id] ? <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" size={16} /> : <ImportIcon />}
                              </button>
                            </div>
                          )}
                          <div  title="Edit">
                            <button className="p-2 rounded-full hover:bg-gray-100"
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
                            </button>
                          </div>
                          <div  title="Delete">
                            <button className="p-2 rounded-full hover:bg-gray-100"
                              size="small"
                              color="error"
                              onClick={() => handleDeleteApiKey(key.id)}
                            >
                              <Delete />
                            </button>
                          </div>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div className="bg-white shadow-md rounded-lg">
          <div className="bg-white shadow-md rounded-lg"Content sx={{ textAlign: 'center', py: 6 }}>
            <Key sx={{ fontSize: 64, color: 'text.secondary', mb: 2 }} />
            <div  variant="h6" gutterBottom>
              No API Keys Added
            </div>
            <div  variant="body2" color="text.secondary" sx={{ mb: 3 }}>
              Add your first API key to start importing portfolio data and accessing real-time market information.
            </div>
            <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
              variant="contained"
              startIcon={<Add />}
              onClick={() => setAddDialogOpen(true)}
            >
              Add Your First API Key
            </button>
          </div>
        </div>
      )}

      {/* Supported Providers */}
      <div className="bg-white shadow-md rounded-lg" sx={{ mt: 4 }}>
        <div className="bg-white shadow-md rounded-lg"Header title="Supported Providers" />
        <div className="bg-white shadow-md rounded-lg"Content>
          <div className="grid" container spacing={2}>
            {supportedProviders.map((provider) => (
              <div className="grid" item xs={12} md={6} key={provider.id}>
                <div className="bg-white shadow-md rounded-lg" variant="outlined">
                  <div className="bg-white shadow-md rounded-lg"Content>
                    <div  sx={{ display: 'flex', alignItems: 'flex-start', mb: 2 }}>
                      <div  sx={{ color: provider.color, mr: 2 }}>
                        {provider.icon}
                      </div>
                      <div>
                        <div  variant="h6" gutterBottom>
                          {provider.name}
                        </div>
                        <div  variant="body2" color="text.secondary" gutterBottom>
                          {provider.description}
                        </div>
                      </div>
                    </div>
                    <div  sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                      {provider.features.map((feature) => (
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" key={feature} label={feature} size="small" />
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Add API Key Dialog */}
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50" open={addDialogOpen} onClose={() => setAddDialogOpen(false)} maxWidth="sm" fullWidth>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Title>Add API Key</h2>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Content>
          <div  sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 1 }}>
            <div className="mb-4" fullWidth>
              <label className="block text-sm font-medium text-gray-700 mb-1">Provider</label>
              <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={formData.provider}
                label="Provider"
                onChange={(e) => setFormData({ ...formData, provider: e.target.value })}
              >
                {supportedProviders.map((provider) => (
                  <option  key={provider.id} value={provider.id}>
                    <div  sx={{ display: 'flex', alignItems: 'center' }}>
                      <div  sx={{ color: provider.color, mr: 1 }}>
                        {provider.icon}
                      </div>
                      {provider.name}
                    </div>
                  </option>
                ))}
              </select>
            </div>

            <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              fullWidth
              label="API Key"
              value={formData.apiKey}
              onChange={(e) => setFormData({ ...formData, apiKey: e.target.value })}
              required
              type="password"
            />

            <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              fullWidth
              label="API Secret (if required)"
              value={formData.apiSecret}
              onChange={(e) => setFormData({ ...formData, apiSecret: e.target.value })}
              type="password"
            />

            <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              fullWidth
              label="Description"
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              placeholder="e.g., Main trading account"
            />

            <div className="mb-4"Label
              control={
                <input type="checkbox" className="toggle"
                  checked={formData.isSandbox}
                  onChange={(e) => setFormData({ ...formData, isSandbox: e.target.checked })}
                />
              }
              label="Paper Trading Environment"
            />

            <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="info">
              <div  variant="body2">
                Start with paper trading to test the connection safely. 
                Your API keys will be encrypted before storage.
              </div>
            </div>
          </div>
        </div>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Actions>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" onClick={() => setAddDialogOpen(false)}>Cancel</button>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" onClick={handleAddApiKey} variant="contained">Add API Key</button>
        </div>
      </div>

      {/* Edit API Key Dialog */}
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50" open={editDialogOpen} onClose={() => setEditDialogOpen(false)} maxWidth="sm" fullWidth>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Title>Edit API Key</h2>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Content>
          <div  sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 1 }}>
            <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              fullWidth
              label="Provider"
              value={getProviderInfo(formData.provider).name}
              disabled
            />

            <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              fullWidth
              label="Description"
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              placeholder="e.g., Main trading account"
            />

            <div className="mb-4"Label
              control={
                <input type="checkbox" className="toggle"
                  checked={formData.isSandbox}
                  onChange={(e) => setFormData({ ...formData, isSandbox: e.target.checked })}
                />
              }
              label="Paper Trading Environment"
            />
          </div>
        </div>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Actions>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" onClick={() => setEditDialogOpen(false)}>Cancel</button>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" onClick={handleEditApiKey} variant="contained">Save Changes</button>
        </div>
      </div>
    </div>
  );
};

export default SettingsApiKeys;