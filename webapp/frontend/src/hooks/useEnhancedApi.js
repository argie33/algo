// Enhanced API Hook with Circuit Breaker and Error Handling
// Provides robust API calls with automatic retry, caching, and error recovery

import { useState, useEffect, useCallback, useRef } from 'react';
import { enhancedFetch, healthChecker, networkMonitor, circuitBreakers } from '../utils/errorHandler';

const useEnhancedApi = (serviceType = 'default') => {
  const [isOnline, setIsOnline] = useState(networkMonitor.isOnline());
  const [serviceHealth, setServiceHealth] = useState({});
  const [lastError, setLastError] = useState(null);
  const requestCount = useRef(0);

  useEffect(() => {
    // Monitor network status
    networkMonitor.onStatusChange(setIsOnline);
    
    // Initial health check
    checkHealth();
    
    // Periodic health check
    const healthInterval = setInterval(checkHealth, 60000); // Every minute
    
    return () => clearInterval(healthInterval);
  }, []);

  const checkHealth = useCallback(async () => {
    try {
      const health = await healthChecker.getDetailedStatus();
      setServiceHealth(health);
    } catch (error) {
      console.warn('Health check failed:', error);
    }
  }, []);

  const apiCall = useCallback(async (url, options = {}) => {
    if (!isOnline) {
      throw new Error('No internet connection available');
    }

    const requestId = ++requestCount.current;
    console.log(`[Request ${requestId}] ${options.method || 'GET'} ${url}`);

    try {
      setLastError(null);
      const response = await enhancedFetch(url, options, serviceType);
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      
      const data = await response.json();
      console.log(`[Request ${requestId}] Success`);
      return data;
    } catch (error) {
      console.error(`[Request ${requestId}] Failed:`, error);
      setLastError(error);
      throw error;
    }
  }, [isOnline, serviceType]);

  const get = useCallback((url, options = {}) => {
    return apiCall(url, { ...options, method: 'GET' });
  }, [apiCall]);

  const post = useCallback((url, data, options = {}) => {
    return apiCall(url, {
      ...options,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...options.headers
      },
      body: JSON.stringify(data)
    });
  }, [apiCall]);

  const put = useCallback((url, data, options = {}) => {
    return apiCall(url, {
      ...options,
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        ...options.headers
      },
      body: JSON.stringify(data)
    });
  }, [apiCall]);

  const del = useCallback((url, options = {}) => {
    return apiCall(url, { ...options, method: 'DELETE' });
  }, [apiCall]);

  const getCircuitBreakerStatus = useCallback(() => {
    return circuitBreakers[serviceType]?.getStatus() || null;
  }, [serviceType]);

  const clearCache = useCallback((pattern) => {
    const { cacheManager } = require('../utils/errorHandler');
    cacheManager.clear(pattern);
  }, []);

  return {
    // API methods
    get,
    post,
    put,
    delete: del,
    apiCall,
    
    // Status information
    isOnline,
    serviceHealth,
    lastError,
    circuitBreakerStatus: getCircuitBreakerStatus(),
    
    // Utility methods
    checkHealth,
    clearCache
  };
};

// Specific hooks for different services
export const useApiKeysApi = () => useEnhancedApi('apiKeys');
export const usePortfolioApi = () => useEnhancedApi('portfolio');
export const useTradesApi = () => useEnhancedApi('trades');
export const useWebSocketApi = () => useEnhancedApi('websocket');

export default useEnhancedApi;