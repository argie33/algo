/**
 * ProgressiveDataLoader - Real data loading only
 * No fallbacks, no mocks, real functionality only
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  CircularProgress,
  Alert,
  Button,
  LinearProgress
} from '@mui/material';
import {
  Refresh,
  Error as ErrorIcon
} from '@mui/icons-material';

const ProgressiveDataLoader = ({
  children,
  dataFetcher,
  retryAttempts = 3,
  retryDelay = 1000,
  showProgress = true,
  pageName = 'content'
}) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [retryCount, setRetryCount] = useState(0);

  const loadData = useCallback(async (attempt = 0) => {
    setLoading(true);
    setError(null);

    try {
      if (dataFetcher) {
        const result = await dataFetcher();
        setData(result);
        setRetryCount(0);
      }
      setLoading(false);
    } catch (fetchError) {
      console.error(`Data fetch attempt ${attempt + 1} failed:`, fetchError.message);
      
      if (attempt < retryAttempts) {
        setRetryCount(attempt + 1);
        setTimeout(() => loadData(attempt + 1), retryDelay);
      } else {
        setError(fetchError.message || 'Failed to load data');
        setLoading(false);
      }
    }
  }, [dataFetcher, retryAttempts, retryDelay]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleRetry = () => {
    setRetryCount(0);
    loadData();
  };

  if (loading) {
    return (
      <Box sx={{ p: 3, textAlign: 'center' }}>
        <CircularProgress size={40} sx={{ mb: 2 }} />
        <Typography variant="body2" color="textSecondary">
          Loading {pageName}...
        </Typography>
        {showProgress && retryCount > 0 && (
          <Typography variant="caption" color="textSecondary" sx={{ mt: 1, display: 'block' }}>
            Retry attempt {retryCount} of {retryAttempts}
          </Typography>
        )}
      </Box>
    );
  }

  if (error) {
    return (
      <Card sx={{ m: 2 }}>
        <CardContent sx={{ textAlign: 'center' }}>
          <ErrorIcon color="error" sx={{ fontSize: 48, mb: 2 }} />
          <Typography variant="h6" color="error" gutterBottom>
            Error Loading {pageName}
          </Typography>
          <Typography variant="body2" color="textSecondary" sx={{ mb: 2 }}>
            {error}
          </Typography>
          <Button 
            variant="contained" 
            startIcon={<Refresh />}
            onClick={handleRetry}
            disabled={loading}
          >
            Try Again
          </Button>
        </CardContent>
      </Card>
    );
  }

  if (data && children) {
    return React.cloneElement(children, { data });
  }

  return (
    <Box sx={{ p: 3, textAlign: 'center' }}>
      <Typography variant="body2" color="textSecondary">
        No data available for {pageName}
      </Typography>
      <Button 
        variant="outlined" 
        startIcon={<Refresh />}
        onClick={handleRetry}
        sx={{ mt: 2 }}
      >
        Refresh
      </Button>
    </Box>
  );
};

export default ProgressiveDataLoader;