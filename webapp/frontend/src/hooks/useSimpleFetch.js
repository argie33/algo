/**
 * Simple Fetch Hook - NO external store dependencies
 * Replaces React Query to eliminate useSyncExternalStore issues
 */

import { useState, useEffect, useCallback } from 'react';

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
      return response.json();
    };
    actualOptions = options;
  } else if (typeof urlOrOptions === 'object' && urlOrOptions !== null) {
    // React Query style object
    url = JSON.stringify(urlOrOptions.queryKey || 'unknown');
    queryFn = urlOrOptions.queryFn;
    actualOptions = { ...options, ...urlOrOptions };
  } else {
    // Invalid input
    console.error('useSimpleFetch: Invalid first parameter. Expected string URL or options object.');
    url = null;
    queryFn = null;
    actualOptions = options;
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
        setData(result);
        setError(null);
        break;
      } catch (err) {
        attempt++;
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

  return {
    data,
    loading,
    error,
    refetch,
    isLoading: loading,
    isError: !!error,
    isSuccess: !loading && !error && data !== null
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