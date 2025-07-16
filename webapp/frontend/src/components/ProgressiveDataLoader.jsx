/**
 * ProgressiveDataLoader - Smart data loading with fallback strategies
 * Implements progressive enhancement for data fetching with graceful degradation
 * Production-grade component with retry logic, caching, and offline support
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
  LinearProgress,
  Chip,
  Skeleton
} from '@mui/material';
import {
  Refresh,
  CloudOff,
  Storage,
  CheckCircle,
  Warning,
  Error
} from '@mui/icons-material';
import apiHealthService from '../services/apiHealthService';
import ApiUnavailableFallback from './ApiUnavailableFallback';

const ProgressiveDataLoader = ({
  children,
  dataFetcher,
  fallbackData = null,
  cacheDuration = 5 * 60 * 1000, // 5 minutes default
  retryAttempts = 3,
  retryDelay = 1000,
  loadingComponent = null,
  errorComponent = null,
  showProgress = true,
  pageName = 'content',
  dependencies = []
}) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [retryCount, setRetryCount] = useState(0);
  const [dataSource, setDataSource] = useState('loading');
  const [progress, setProgress] = useState(0);
  const [apiHealth, setApiHealth] = useState('unknown');

  // Cache management
  const getCacheKey = useCallback(() => {
    return `progressive_data_${pageName}_${JSON.stringify(dependencies)}`;
  }, [pageName, dependencies]);

  const getCachedData = useCallback(() => {
    try {
      const cached = localStorage.getItem(getCacheKey());
      if (cached) {
        const parsedCache = JSON.parse(cached);
        const isExpired = Date.now() - parsedCache.timestamp > cacheDuration;
        if (!isExpired) {
          return parsedCache.data;
        } else {
          localStorage.removeItem(getCacheKey());
        }
      }
    } catch (error) {
      console.warn('Failed to load cached data:', error);
    }
    return null;
  }, [getCacheKey, cacheDuration]);

  const setCachedData = useCallback((data) => {
    try {
      localStorage.setItem(getCacheKey(), JSON.stringify({
        data,
        timestamp: Date.now()
      }));
    } catch (error) {
      console.warn('Failed to cache data:', error);
    }
  }, [getCacheKey]);

  // Progressive data loading with fallback strategy
  const loadData = useCallback(async (attempt = 0) => {
    setLoading(true);
    setProgress(0);
    setError(null);

    try {
      // Step 1: Check API health
      setProgress(20);
      const healthStatus = apiHealthService.getHealthStatus();
      setApiHealth(healthStatus.overall);

      // Step 2: Try cached data first if API is down
      if (healthStatus.overall === 'down' || healthStatus.circuitBreakerOpen) {
        const cached = getCachedData();
        if (cached) {
          setData(cached);
          setDataSource('cache');
          setLoading(false);
          setProgress(100);
          return;
        }
      }

      // Step 3: Attempt live data fetch
      setProgress(40);
      if (dataFetcher) {
        const startTime = Date.now();
        const liveData = await dataFetcher();
        const loadTime = Date.now() - startTime;
        
        setProgress(80);
        
        // Cache successful data
        setCachedData(liveData);
        setData(liveData);
        setDataSource('live');
        setRetryCount(0);
        
        console.log(`✅ Data loaded successfully in ${loadTime}ms from live API`);
      }

      setProgress(100);
      setLoading(false);

    } catch (fetchError) {
      console.warn(`❌ Data fetch attempt ${attempt + 1} failed:`, fetchError.message);
      
      // Step 4: Try cached data on error
      const cached = getCachedData();
      if (cached) {
        setData(cached);
        setDataSource('cache');
        setLoading(false);
        setProgress(100);
        setError(`Using cached data due to API error: ${fetchError.message}`);
        return;
      }

      // Step 5: Try fallback data
      if (fallbackData) {
        setData(fallbackData);
        setDataSource('fallback');
        setLoading(false);
        setProgress(100);
        setError(`Using fallback data due to API error: ${fetchError.message}`);
        return;
      }

      // Step 6: Retry logic
      if (attempt < retryAttempts) {
        const delay = retryDelay * Math.pow(2, attempt); // Exponential backoff
        console.log(`🔄 Retrying in ${delay}ms (attempt ${attempt + 1}/${retryAttempts})`);
        setTimeout(() => loadData(attempt + 1), delay);
        setRetryCount(attempt + 1);
        return;
      }

      // Step 7: Complete failure
      setError(fetchError.message);
      setLoading(false);
      setProgress(100);
    }
  }, [dataFetcher, fallbackData, retryAttempts, retryDelay, getCachedData, setCachedData]);

  // Load data on mount and dependency changes
  useEffect(() => {
    loadData();
  }, [loadData, ...dependencies]);

  // Monitor API health changes
  useEffect(() => {
    const unsubscribe = apiHealthService.subscribe((healthStatus) => {
      setApiHealth(healthStatus.overall);
      
      // If API comes back online and we're using fallback data, try to refresh
      if (healthStatus.overall === 'healthy' && (dataSource === 'cache' || dataSource === 'fallback')) {
        console.log('🔄 API is healthy again, refreshing data...');
        loadData();
      }
    });

    return unsubscribe;
  }, [loadData, dataSource]);

  const handleRetry = () => {
    setRetryCount(0);
    loadData();
  };

  // Loading state
  if (loading) {
    if (loadingComponent) {
      return loadingComponent;
    }

    return (
      <Box sx={{ p: 2 }}>
        <Card>
          <CardContent>
            <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
              <CircularProgress size={24} sx={{ mr: 2 }} />
              <Typography variant="h6">
                Loading {pageName}...
              </Typography>
              {retryCount > 0 && (
                <Chip 
                  label={`Retry ${retryCount}/${retryAttempts}`} 
                  size="small" 
                  color="warning"
                  sx={{ ml: 2 }}
                />
              )}
            </Box>
            
            {showProgress && (
              <Box sx={{ mb: 2 }}>
                <LinearProgress variant="determinate" value={progress} />
                <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                  {progress < 20 ? 'Initializing...' :
                   progress < 40 ? 'Checking API health...' :
                   progress < 80 ? 'Fetching data...' :
                   progress < 100 ? 'Processing...' : 'Complete'}
                </Typography>
              </Box>
            )}

            {/* Loading skeleton */}
            <Box>
              <Skeleton variant="text" width="60%" height={32} />
              <Skeleton variant="rectangular" width="100%" height={100} sx={{ my: 1 }} />
              <Skeleton variant="text" width="80%" height={24} />
            </Box>
          </CardContent>
        </Card>
      </Box>
    );
  }

  // Error state with no data
  if (error && !data) {
    if (errorComponent) {
      return errorComponent;
    }

    return (
      <ApiUnavailableFallback
        apiStatus={apiHealth}
        onRetry={handleRetry}
        pageName={pageName}
        showDemoData={false}
        customMessage={error}
      />
    );
  }

  // Success state with data
  return (
    <Box>
      {/* Data source indicator */}
      {(dataSource !== 'live' || error) && (
        <Alert 
          severity={dataSource === 'cache' ? 'info' : dataSource === 'fallback' ? 'warning' : 'error'}
          sx={{ mb: 2 }}
          action={
            <Button
              color="inherit"
              size="small"
              onClick={handleRetry}
              startIcon={<Refresh />}
            >
              Refresh
            </Button>
          }
        >
          <Box sx={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 1 }}>
            <Typography variant="body2">
              {dataSource === 'cache' && 'Showing cached data'}
              {dataSource === 'fallback' && 'Showing demo data'}
              {dataSource === 'live' && error && 'Live data with issues'}
            </Typography>
            
            <Chip
              label={dataSource.toUpperCase()}
              size="small"
              color={dataSource === 'live' ? 'success' : dataSource === 'cache' ? 'info' : 'warning'}
              icon={
                dataSource === 'live' ? <CheckCircle /> :
                dataSource === 'cache' ? <Storage /> :
                <Warning />
              }
            />
            
            <Chip
              label={`API: ${apiHealth.toUpperCase()}`}
              size="small"
              color={apiHealth === 'healthy' ? 'success' : apiHealth === 'degraded' ? 'warning' : 'error'}
            />
          </Box>
          
          {error && (
            <Typography variant="body2" sx={{ mt: 1 }}>
              {error}
            </Typography>
          )}
        </Alert>
      )}

      {/* Render children with data */}
      {children && typeof children === 'function' ? children(data) : children}
    </Box>
  );
};

export default ProgressiveDataLoader;