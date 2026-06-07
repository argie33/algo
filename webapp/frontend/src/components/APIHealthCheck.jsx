import React, { useEffect, useState } from 'react';
import { Alert, Box, CircularProgress, Button } from '@mui/material';
import { api } from '../services/api';

/**
 * APIHealthCheck - Validates API is accessible before loading app.
 * Shows status indicator and allows retry if connection fails.
 */
export function APIHealthCheck({ onHealthy, onUnhealthy, children }) {
  const [checkComplete, setCheckComplete] = useState(false);
  const [isHealthy, setIsHealthy] = useState(true);

  useEffect(() => {
    // Check API health immediately
    const checkHealth = async () => {
      try {
        const _response = await api.get('/api/health', { timeout: 5000 });
        setIsHealthy(true);
        onHealthy?.();
      } catch (error) {
        console.error('[APIHealthCheck] Health check failed:', {
          message: error.message,
          code: error.code,
          status: error.response?.status,
          isNetworkError: !error.response
        });
        setIsHealthy(false);
        onUnhealthy?.(error);
      } finally {
        setCheckComplete(true);
      }
    };

    checkHealth();
  }, [onHealthy, onUnhealthy]);

  if (!checkComplete) {
    return (
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh' }}>
        <CircularProgress />
      </Box>
    );
  }

  if (!isHealthy) {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="error" sx={{ mb: 2 }}>
          <strong>API Connection Failed</strong>
          <p>
            The backend API is currently unavailable. Please check your network connection and try again.
          </p>
          <Button
            variant="contained"
            size="small"
            onClick={() => window.location.reload()}
            sx={{ mt: 1 }}
          >
            Retry
          </Button>
        </Alert>
      </Box>
    );
  }

  return children;
}

export default APIHealthCheck;

