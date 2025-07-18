// API Key Status Indicator Component
// Shows the status of broker API key integration across portfolio pages

import React, { useState, useEffect } from 'react';
import {
  Box,
  Chip,
  Button,
  Alert,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Typography,
  IconButton,
  Tooltip
} from '@mui/material';
import {
  CheckCircle,
  Warning,
  Error,
  Settings,
  Refresh,
  Info
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { getApiKeys } from '../services/api';

const ApiKeyStatusIndicator = ({ 
  compact = false, 
  showSetupDialog = true, 
  provider = null,
  onStatusChange = null 
}) => {
  const [apiKeys, setApiKeys] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [setupDialogOpen, setSetupDialogOpen] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    checkApiKeyStatus();
  }, [provider]);

  const checkApiKeyStatus = async () => {
    try {
      setLoading(true);
      setError(null);
      const keys = await getApiKeys();
      
      const filteredKeys = provider 
        ? keys.filter(key => key.provider === provider && key.isActive)
        : keys.filter(key => key.isActive);
        
      setApiKeys(filteredKeys);
      
      if (onStatusChange) {
        onStatusChange({
          hasKeys: filteredKeys.length > 0,
          keyCount: filteredKeys.length,
          providers: [...new Set(filteredKeys.map(k => k.provider))]
        });
      }
    } catch (err) {
      setError(err.message);
      setApiKeys([]);
    } finally {
      setLoading(false);
    }
  };

  const getStatusInfo = () => {
    if (loading) {
      return {
        status: 'loading',
        color: 'default',
        icon: <Refresh />,
        message: 'Checking API keys...',
        severity: 'info'
      };
    }

    if (error) {
      return {
        status: 'error',
        color: 'error',
        icon: <Error />,
        message: 'Failed to check API keys',
        severity: 'error'
      };
    }

    if (apiKeys.length === 0) {
      return {
        status: 'missing',
        color: 'warning',
        icon: <Warning />,
        message: provider 
          ? `${provider} API key not configured`
          : 'No broker API keys configured',
        severity: 'warning'
      };
    }

    return {
      status: 'connected',
      color: 'success',
      icon: <CheckCircle />,
      message: provider
        ? `${provider} connected`
        : `${apiKeys.length} broker${apiKeys.length > 1 ? 's' : ''} connected`,
      severity: 'success'
    };
  };

  const statusInfo = getStatusInfo();

  const handleSetupClick = () => {
    if (showSetupDialog) {
      setSetupDialogOpen(true);
    } else {
      navigate('/settings');
    }
  };

  const handleNavigateToSettings = () => {
    setSetupDialogOpen(false);
    navigate('/settings');
  };

  if (compact) {
    return (
      <div  sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <div  title={statusInfo.message}>
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
            icon={statusInfo.icon}
            label={apiKeys.length > 0 ? `${apiKeys.length} connected` : 'No API keys'}
            color={statusInfo.color}
            size="small"
            variant="outlined"
          />
        </div>
        {statusInfo.status === 'missing' && (
          <div  title="Configure API keys">
            <button className="p-2 rounded-full hover:bg-gray-100" size="small" onClick={handleSetupClick}>
              <Settings fontSize="small" />
            </button>
          </div>
        )}
      </div>
    );
  }

  return (
    <div>
      <div className="p-4 rounded-md bg-blue-50 border border-blue-200" 
        severity={statusInfo.severity}
        action={
          statusInfo.status === 'missing' ? (
            <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
              color="inherit" 
              size="small" 
              onClick={handleSetupClick}
              startIcon={<Settings />}
            >
              Setup API Keys
            </button>
          ) : statusInfo.status === 'error' ? (
            <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
              color="inherit" 
              size="small" 
              onClick={checkApiKeyStatus}
              startIcon={<Refresh />}
            >
              Retry
            </button>
          ) : null
        }
      >
        <div  variant="body2">
          {statusInfo.message}
          {statusInfo.status === 'missing' && (
            <span>
              . Portfolio data will use demo/mock data until broker API keys are configured.
            </span>
          )}
          {statusInfo.status === 'connected' && apiKeys.length > 0 && (
            <span>
              . Live data from: {apiKeys.map(k => k.provider).join(', ')}
            </span>
          )}
        </div>
      </div>

      {/* Setup Dialog */}
      <Dialog open={setupDialogOpen} onClose={() => setSetupDialogOpen(false)}>
        <DialogTitle>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Info color="primary" />
            Setup Broker API Keys
          </Box>
        </DialogTitle>
        <DialogContent>
          <Typography paragraph>
            To access live portfolio data, trading history, and real-time market feeds, 
            you'll need to configure your broker API keys.
          </Typography>
          <Typography paragraph>
            <strong>Supported Brokers:</strong>
          </Typography>
          <Box sx={{ ml: 2, mb: 2 }}>
            <Typography variant="body2">• Alpaca (Paper & Live Trading)</Typography>
            <Typography variant="body2">• TD Ameritrade (Coming Soon)</Typography>
            <Typography variant="body2">• Interactive Brokers (Coming Soon)</Typography>
          </Box>
          <Typography paragraph>
            <strong>Security:</strong> Your API keys are encrypted with AES-256-GCM 
            and stored securely. We never store your credentials in plaintext.
          </Typography>
          <Typography variant="body2" color="textSecondary">
            Don't have API keys? You can still use the demo data to explore the platform.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSetupDialogOpen(false)}>
            Use Demo Data
          </Button>
          <Button 
            variant="contained" 
            onClick={handleNavigateToSettings}
            startIcon={<Settings />}
          >
            Configure API Keys
          </Button>
        </DialogActions>
      </Dialog>
      </div>
    </div>
  );
};

export default ApiKeyStatusIndicator;