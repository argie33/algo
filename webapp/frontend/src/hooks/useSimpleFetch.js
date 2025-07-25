/**
 * Simple Fetch Hook - NO external store dependencies
 * Replaces React Query to eliminate useSyncExternalStore issues
 */

import { useState, useEffect, useCallback } from 'react';
import { extractResponseData, normalizeError, getUIState } from '../utils/dataFormatHelper';

export function useSimpleFetch(urlOrOptions, options = {}) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  
  // Handle both React Query style objects and simple URL strings
  let url, queryFn, actualOptions;
  
  if (typeof urlOrOptions === 'string') {
    // Simple URL string usage
    url = urlOrOptions;
    queryFn = async () => {
      const response = await fetch(url);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      
      const contentType = response.headers.get('content-type');
      const text = await response.text();
      
      // Detect HTML response (routing issue)
      if (text.includes('<!DOCTYPE html>') || contentType?.includes('text/html')) {
        throw new Error('API routing misconfiguration - receiving HTML instead of JSON');
      }
      
      try {
        return JSON.parse(text);
      } catch (parseError) {
        throw new Error(`Invalid JSON response: ${parseError.message}`);
      }
    };
    actualOptions = options;
  } else if (typeof urlOrOptions === 'object' && urlOrOptions !== null) {
    // React Query style object
    if (urlOrOptions.queryFn && typeof urlOrOptions.queryFn === 'function') {
      // Valid React Query object with queryFn
      url = JSON.stringify(urlOrOptions.queryKey || 'query');
      queryFn = urlOrOptions.queryFn;
      actualOptions = { ...options, ...urlOrOptions };
    } else {
      // Invalid object - disable the hook
      console.error('useSimpleFetch: Invalid object parameter. Missing queryFn function.', urlOrOptions);
      url = null;
      queryFn = null;
      actualOptions = { ...options, enabled: false };
    }
  } else {
    // Invalid input - disable the hook
    console.error('useSimpleFetch: Invalid first parameter. Expected string URL or options object with queryFn.', urlOrOptions);
    url = null;
    queryFn = null;
    actualOptions = { ...options, enabled: false };
  }
  
  const {
    enabled = true,
    retry = 3,
    staleTime = 30000,
    refetchOnWindowFocus = false,
    onError
  } = actualOptions;

  const fetchData = useCallback(async () => {
    if (!enabled || !queryFn) return;
    
    setLoading(true);
    setError(null);
    
    let attempt = 0;
    while (attempt <= retry) {
      try {
        const result = await queryFn();
        const normalized = extractResponseData(result);
        
        if (normalized.success) {
          setData(normalized.data);
          setError(null);
        } else {
          setError(normalized.error);
          setData(null);
        }
        break;
      } catch (err) {
        attempt++;
        
        // Stop retrying for non-retryable errors to prevent infinite loops
        const shouldNotRetry = err.message?.includes('Circuit breaker is open') ||
                              err.message?.includes('HTTP 404') ||
                              err.message?.includes('Not Found') ||
                              err.message?.includes('API routing misconfiguration');
        
        if (shouldNotRetry) {
          if (err.message?.includes('Circuit breaker is open')) {
            console.warn('🚫 Circuit breaker is open, stopping retries');
            setError('Service temporarily unavailable - please try again in a few moments');
          } else if (err.message?.includes('HTTP 404') || err.message?.includes('Not Found')) {
            console.warn('🚫 404 endpoint not found, stopping retries:', url);
            setError('API endpoint not available');
          } else if (err.message?.includes('API routing misconfiguration')) {
            console.warn('🚫 API routing issue, stopping retries');
            setError('API configuration issue - please contact support');
          } else {
            setError(err.message);
          }
          
          setData(null);
          
          if (onError) {
            try {
              onError(err);
            } catch (callbackError) {
              console.error('Error in onError callback:', callbackError);
            }
          }
          break;
        }
        
        if (attempt > retry) {
          const errorMessage = err.message || 'Fetch failed';
          setError(errorMessage);
          setData(null);
          
          // Call onError callback if provided
          if (onError) {
            try {
              onError(err);
            } catch (callbackError) {
              console.error('Error in onError callback:', callbackError);
            }
          }
        } else {
          // Wait before retry
          await new Promise(resolve => setTimeout(resolve, 1000 * attempt));
        }
      }
    }
    setLoading(false);
  }, [queryFn, enabled, retry, onError]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Optional: refetch on window focus
  useEffect(() => {
    if (!refetchOnWindowFocus) return;
    
    const handleFocus = () => {
      if (document.visibilityState === 'visible') {
        fetchData();
      }
    };
    
    window.addEventListener('visibilitychange', handleFocus);
    return () => window.removeEventListener('visibilitychange', handleFocus);
  }, [fetchData, refetchOnWindowFocus]);

  const refetch = useCallback(() => {
    fetchData();
  }, [fetchData]);

  const uiState = getUIState(loading, error, data);
  
  return {
    data,
    loading,
    error,
    refetch,
    isLoading: loading,
    isError: !!error,
    isSuccess: !loading && !error && data !== null,
    ...uiState
  };
}

// Simple query client replacement
export class SimpleQueryClient {
  constructor(options = {}) {
    this.cache = new Map();
    this.options = {
      staleTime: 30000,
      cacheTime: 10 * 60 * 1000,
      retry: 3,
      ...options.defaultOptions?.queries
    };
  }

  invalidateQueries() {
    this.cache.clear();
  }

  setQueryData(key, data) {
    this.cache.set(JSON.stringify(key), {
      data,
      timestamp: Date.now()
    });
  }

  getQueryData(key) {
    const cached = this.cache.get(JSON.stringify(key));
    if (!cached) return undefined;
    
    const isStale = Date.now() - cached.timestamp > this.options.staleTime;
    return isStale ? undefined : cached.data;
  }
}

// Provider replacement
export function SimpleQueryProvider({ client, children }) {
  return children; // No provider needed for simple approach
}

export default useSimpleFetch;