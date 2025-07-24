/**
 * API Key Manager Component
 * Simplified, reliable API key management for Alpaca
 * Handles all API key operations with graceful error handling
 */

import React, { useState, useEffect } from 'react';
import {
  Box,
  Card,
  CardContent,
  CardHeader,
  Typography,
  TextField,
  Button,
  Alert,
  CircularProgress,
  Chip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  FormControlLabel,
  Switch,
  Grid,
  Divider
} from '@mui/material';
import {
  Add as AddIcon,
  Delete as DeleteIcon,
  Visibility as VisibilityIcon,
  VisibilityOff as VisibilityOffIcon,
  CheckCircle as CheckCircleIcon,
  Error as ErrorIcon
} from '@mui/icons-material';

import unifiedApiKeyService from '../services/unifiedApiKeyService';

const ApiKeyManager = () => {
  const [apiKeys, setApiKeys] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  
  // Add API key dialog state
  const [addDialogOpen, setAddDialogOpen] = useState(false);
  const [formData, setFormData] = useState({
    apiKey: '',
    secretKey: '',
    isSandbox: true
  });
  const [showSecret, setShowSecret] = useState(false);
  const [formErrors, setFormErrors] = useState([]);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    loadApiKeys();
  }, []);

  const loadApiKeys = async () => {
    try {
      setLoading(true);
      setError(null);
      
      const result = await unifiedApiKeyService.getCachedApiKeys();
      
      if (result.success) {
        setApiKeys(result.data || []);
        if (result.message && result.data.length === 0) {
          console.log('ℹ️ API Key service message:', result.message);
        }
      } else {
        throw new Error(result.message || 'Failed to load API keys');
      }
    } catch (err) {
      console.error('Error loading API keys:', err);
      setError('Unable to load API keys. The service may be temporarily unavailable.');
      setApiKeys([]); // Graceful degradation
    } finally {
      setLoading(false);
    }
  };

  const handleAddApiKey = async () => {
    try {
      setSubmitting(true);
      setFormErrors([]);
      setError(null);

      // Validate inputs
      const validation = unifiedApiKeyService.validateCredentials(formData.apiKey, formData.secretKey);
      
      if (!validation.isValid) {
        setFormErrors(validation.errors);
        return;
      }

      const result = await unifiedApiKeyService.addApiKey(
        formData.apiKey,
        formData.secretKey,
        formData.isSandbox
      );

      if (result.success) {
        setSuccess('API key added successfully!');
        setAddDialogOpen(false);
        setFormData({ apiKey: '', secretKey: '', isSandbox: true });
        setShowSecret(false);
        
        // Reload API keys
        await loadApiKeys();
      } else {
        throw new Error(result.message || 'Failed to add API key');
      }
    } catch (err) {
      console.error('Error adding API key:', err);
      setError(err.message || 'Failed to add API key');
    } finally {
      setSubmitting(false);
    }
  };

  const handleRemoveApiKey = async () => {
    try {
      setError(null);
      
      const result = await unifiedApiKeyService.removeApiKey();
      
      if (result.success) {
        setSuccess('API key removed successfully!');
        await loadApiKeys();
      } else {
        throw new Error(result.message || 'Failed to remove API key');
      }
    } catch (err) {
      console.error('Error removing API key:', err);
      setError(err.message || 'Failed to remove API key');
    }
  };

  const clearMessages = () => {
    setError(null);
    setSuccess(null);
  };

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight="200px">
        <CircularProgress />
        <Typography variant="body2" sx={{ ml: 2 }}>Loading API keys...</Typography>
      </Box>
    );
  }

  return (
    <Box>
      {/* Messages */}
      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={clearMessages}>
          {error}
        </Alert>
      )}
      
      {success && (
        <Alert severity="success" sx={{ mb: 2 }} onClose={clearMessages}>
          {success}
        </Alert>
      )}

      {/* API Keys List */}
      <Card>
        <CardHeader
          title="API Keys"
          subheader="Manage your Alpaca trading API credentials"
          action={
            apiKeys.length === 0 && (
              <Button
                variant="contained"
                startIcon={<AddIcon />}
                onClick={() => setAddDialogOpen(true)}
              >
                Add API Key
              </Button>
            )
          }
        />
        <CardContent>
          {apiKeys.length === 0 ? (
            <Box textAlign="center" py={4}>
              <Typography variant="h6" color="text.secondary" gutterBottom>
                No API Keys Configured
              </Typography>
              <Typography variant="body2" color="text.secondary" paragraph>
                Add your Alpaca API key to enable live trading features, portfolio sync, and real-time data.
              </Typography>
              <Button
                variant="outlined"
                startIcon={<AddIcon />}
                onClick={() => setAddDialogOpen(true)}
              >
                Add Your First API Key
              </Button>
            </Box>
          ) : (
            <Grid container spacing={2}>
              {apiKeys.map((key) => (
                <Grid item xs={12} key={key.id}>
                  <Card variant="outlined">
                    <CardContent>
                      <Box display="flex" justifyContent="space-between" alignItems="flex-start">
                        <Box>
                          <Typography variant="h6" gutterBottom>
                            {key.name}
                          </Typography>
                          <Typography variant="body2" color="text.secondary" gutterBottom>
                            {key.description}
                          </Typography>
                          <Box display="flex" gap={1} mb={1}>
                            <Chip 
                              size="small" 
                              label={key.is_sandbox ? 'Sandbox' : 'Live'} 
                              color={key.is_sandbox ? 'default' : 'warning'}
                            />
                            <Chip 
                              size="small" 
                              label={key.status} 
                              color="success"
                              icon={<CheckCircleIcon />}
                            />
                          </Box>
                          <Typography variant="caption" color="text.secondary">
                            API Key: {key.masked_api_key}
                          </Typography>
                          <br />
                          <Typography variant="caption" color="text.secondary">
                            Added: {new Date(key.created_at).toLocaleDateString()}
                          </Typography>
                        </Box>
                        <Button
                          variant="outlined"
                          color="error"
                          size="small"
                          startIcon={<DeleteIcon />}
                          onClick={handleRemoveApiKey}
                        >
                          Remove
                        </Button>
                      </Box>
                    </CardContent>
                  </Card>
                </Grid>
              ))}
            </Grid>
          )}
        </CardContent>
      </Card>

      {/* Add API Key Dialog */}
      <Dialog open={addDialogOpen} onClose={() => setAddDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Add Alpaca API Key</DialogTitle>
        <DialogContent>
          <Box sx={{ pt: 1 }}>
            {formErrors.length > 0 && (
              <Alert severity="error" sx={{ mb: 2 }}>
                <ul style={{ margin: 0, paddingLeft: '20px' }}>
                  {formErrors.map((error, index) => (
                    <li key={index}>{error}</li>
                  ))}
                </ul>
              </Alert>
            )}

            <TextField
              fullWidth
              label="API Key"
              value={formData.apiKey}
              onChange={(e) => setFormData({ ...formData, apiKey: e.target.value })}
              placeholder="PKxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
              helperText="Your Alpaca API key (starts with PK)"
              margin="normal"
              required
            />

            <TextField
              fullWidth
              label="Secret Key"
              type={showSecret ? 'text' : 'password'}
              value={formData.secretKey}
              onChange={(e) => setFormData({ ...formData, secretKey: e.target.value })}
              placeholder="Your secret key"
              helperText="Your Alpaca secret key (20-80 characters)"
              margin="normal"
              required
              InputProps={{
                endAdornment: (
                  <Button
                    onClick={() => setShowSecret(!showSecret)}
                    sx={{ minWidth: 'auto', p: 1 }}
                  >
                    {showSecret ? <VisibilityOffIcon /> : <VisibilityIcon />}
                  </Button>
                )
              }}
            />

            <FormControlLabel
              control={
                <Switch
                  checked={formData.isSandbox}
                  onChange={(e) => setFormData({ ...formData, isSandbox: e.target.checked })}
                />
              }
              label="Sandbox Mode (Recommended for testing)"
              sx={{ mt: 2 }}
            />

            <Divider sx={{ my: 2 }} />

            <Alert severity="info" sx={{ mt: 2 }}>
              <Typography variant="body2">
                <strong>Getting your API key:</strong>
                <br />
                1. Log in to your Alpaca account
                <br />
                2. Go to Account → API Keys
                <br />
                3. Generate a new API key
                <br />
                4. Copy both the API key and secret key here
              </Typography>
            </Alert>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAddDialogOpen(false)} disabled={submitting}>
            Cancel
          </Button>
          <Button 
            onClick={handleAddApiKey} 
            variant="contained" 
            disabled={submitting || !formData.apiKey || !formData.secretKey}
          >
            {submitting ? <CircularProgress size={20} /> : 'Add API Key'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default ApiKeyManager;