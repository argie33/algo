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
      <div  sx={{ p: 2 }}>
        <div className="bg-white shadow-md rounded-lg">
          <div className="bg-white shadow-md rounded-lg"Content>
            <div  sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
              <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" size={24} sx={{ mr: 2 }} />
              <div  variant="h6">
                Loading {pageName}...
              </div>
              {retryCount > 0 && (
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                  label={`Retry ${retryCount}/${retryAttempts}`} 
                  size="small" 
                  color="warning"
                  sx={{ ml: 2 }}
                />
              )}
            </div>
            
            {showProgress && (
              <div  sx={{ mb: 2 }}>
                <div className="w-full bg-gray-200 rounded-full h-2" variant="determinate" value={progress} />
                <div  variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                  {progress < 20 ? 'Initializing...' :
                   progress < 40 ? 'Checking API health...' :
                   progress < 80 ? 'Fetching data...' :
                   progress < 100 ? 'Processing...' : 'Complete'}
                </div>
              </div>
            )}

            {/* Loading skeleton */}
            <div>
              <Skeleton variant="text" width="60%" height={32} />
              <Skeleton variant="rectangular" width="100%" height={100} sx={{ my: 1 }} />
              <Skeleton variant="text" width="80%" height={24} />
            </div>
          </div>
        </div>
      </div>
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
    <div>
      {/* Data source indicator */}
      {(dataSource !== 'live' || error) && (
        <div className="p-4 rounded-md bg-blue-50 border border-blue-200" 
          severity={dataSource === 'cache' ? 'info' : dataSource === 'fallback' ? 'warning' : 'error'}
          sx={{ mb: 2 }}
          action={
            <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
              color="inherit"
              size="small"
              onClick={handleRetry}
              startIcon={<Refresh />}
            >
              Refresh
            </button>
          }
        >
          <div  sx={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 1 }}>
            <div  variant="body2">
              {dataSource === 'cache' && 'Showing cached data'}
              {dataSource === 'fallback' && 'Showing demo data'}
              {dataSource === 'live' && error && 'Live data with issues'}
            </div>
            
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
              label={dataSource.toUpperCase()}
              size="small"
              color={dataSource === 'live' ? 'success' : dataSource === 'cache' ? 'info' : 'warning'}
              icon={
                dataSource === 'live' ? <CheckCircle /> :
                dataSource === 'cache' ? <Storage /> :
                <Warning />
              }
            />
            
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
              label={`API: ${apiHealth.toUpperCase()}`}
              size="small"
              color={apiHealth === 'healthy' ? 'success' : apiHealth === 'degraded' ? 'warning' : 'error'}
            />
          </div>
          
          {error && (
            <div  variant="body2" sx={{ mt: 1 }}>
              {error}
            </div>
          )}
        </div>
      )}

      {/* Render children with data */}
      {children && typeof children === 'function' ? children(data) : children}
    </div>
  );
};

export default ProgressiveDataLoader;