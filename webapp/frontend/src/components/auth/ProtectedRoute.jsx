import React, { useState, useEffect } from 'react';
import { Box, CircularProgress, Typography, Button, Card, CardContent, Alert } from '@mui/material';
import { Lock, Key, Settings } from '@mui/icons-material';
import { useAuth } from '../../contexts/AuthContext';
import { useNavigate } from 'react-router-dom';
import { getApiKeys } from '../../services/api';
import ApiKeySetupWizard from '../ApiKeySetupWizard';

function ProtectedRoute({ 
  children, 
  requireAuth = false, 
  requireApiKeys = false, 
  fallback = null 
}) {
  const { user, isAuthenticated, isLoading } = useAuth();
  const [apiKeys, setApiKeys] = useState([]);
  const [loadingApiKeys, setLoadingApiKeys] = useState(false);
  const [showSetupWizard, setShowSetupWizard] = useState(false);
  const navigate = useNavigate();

  // Check for API keys when component mounts
  useEffect(() => {
    if (requireApiKeys && isAuthenticated && user) {
      checkApiKeys();
    }
  }, [requireApiKeys, isAuthenticated, user]);

  const checkApiKeys = async () => {
    setLoadingApiKeys(true);
    try {
      const response = await getApiKeys();
      const keys = response?.apiKeys || [];
      setApiKeys(keys);
    } catch (error) {
      console.error('Error checking API keys:', error);
      setApiKeys([]);
    } finally {
      setLoadingApiKeys(false);
    }
  };

  const handleApiKeySetup = async (formData) => {
    // This would be called from the wizard
    await checkApiKeys(); // Refresh API keys after setup
    setShowSetupWizard(false);
  };

  // Show loading spinner while checking authentication
  if (isLoading || loadingApiKeys) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight="60vh">
        <CircularProgress />
      </Box>
    );
  }

  // Show fallback if provided and not authenticated
  if (requireAuth && !isAuthenticated && fallback) {
    return fallback;
  }

  // Show auth required message
  if (requireAuth && !isAuthenticated) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight="60vh">
        <Card sx={{ maxWidth: 400, textAlign: 'center' }}>
          <CardContent>
            <Lock sx={{ fontSize: 48, color: 'primary.main', mb: 2 }} />
            <Typography variant="h6" gutterBottom>
              Authentication Required
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
              Please sign in to access this page.
            </Typography>
            <Button
              variant="contained"
              onClick={() => navigate('/login')}
            >
              Sign In
            </Button>
          </CardContent>
        </Card>
      </Box>
    );
  }

  // Show API key setup required message
  if (requireApiKeys && isAuthenticated && apiKeys.length === 0) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight="60vh">
        <Card sx={{ maxWidth: 500, textAlign: 'center' }}>
          <CardContent>
            <Key sx={{ fontSize: 48, color: 'primary.main', mb: 2 }} />
            <Typography variant="h6" gutterBottom>
              API Key Setup Required
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
              This page requires connection to your brokerage account to display live data. 
              Set up your API keys to get started.
            </Typography>
            
            <Alert severity="info" sx={{ mb: 3, textAlign: 'left' }}>
              <Typography variant="body2">
                <strong>Why do I need API keys?</strong><br />
                API keys allow us to securely connect to your brokerage account to:
                <br />• Import your real portfolio holdings
                <br />• Display live market data
                <br />• Execute trades (if enabled)
                <br />• Provide real-time analytics
              </Typography>
            </Alert>

            <Box sx={{ display: 'flex', gap: 2, justifyContent: 'center' }}>
              <Button
                variant="contained"
                startIcon={<Key />}
                onClick={() => setShowSetupWizard(true)}
              >
                Set Up API Keys
              </Button>
              <Button
                variant="outlined"
                startIcon={<Settings />}
                onClick={() => navigate('/settings')}
              >
                Go to Settings
              </Button>
            </Box>
          </CardContent>
        </Card>

        <ApiKeySetupWizard
          open={showSetupWizard}
          onClose={() => setShowSetupWizard(false)}
          onComplete={handleApiKeySetup}
        />
      </Box>
    );
  }

  return children;
}

export default ProtectedRoute;