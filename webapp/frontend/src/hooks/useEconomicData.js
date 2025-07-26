import { useState, useEffect, useCallback, useRef } from 'react';
import economicDataService from '../services/economicDataService';

/**
 * Enhanced hook for fetching economic data with real-time validation,
 * circuit breaker pattern, and intelligent fallback mechanisms
 */
export const useEconomicData = ({
  indicator = null,
  indicators = null,
  options = {},
  enableRealTimeValidation = true,
  circuitBreakerThreshold = 3,
  fallbackTimeout = 10000
} = {}) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [dataQuality, setDataQuality] = useState('unknown');
  const [lastUpdated, setLastUpdated] = useState(null);
  const [isUsingFallback, setIsUsingFallback] = useState(false);
  const [retryCount, setRetryCount] = useState(0);
  const [circuitBreakerOpen, setCircuitBreakerOpen] = useState(false);

  const failureCountRef = useRef(0);
  const lastRequestTimeRef = useRef(null);
  const timeoutRef = useRef(null);
  
  const maxRetries = options.maxRetries || 3;
  const retryDelay = options.retryDelay || 2000;
  const staleTime = options.staleTime || 5 * 60 * 1000; // 5 minutes

  // Circuit breaker logic
  const isCircuitBreakerTripped = useCallback(() => {
    return failureCountRef.current >= circuitBreakerThreshold;
  }, [circuitBreakerThreshold]);

  // Reset circuit breaker after timeout
  const resetCircuitBreaker = useCallback(() => {
    if (isCircuitBreakerTripped()) {
      const timeSinceLastFailure = Date.now() - (lastRequestTimeRef.current || 0);
      if (timeSinceLastFailure > 60000) { // 1 minute cooldown
        failureCountRef.current = 0;
        setCircuitBreakerOpen(false);
        console.log('🔄 Economic data circuit breaker reset');
      }
    }
  }, [isCircuitBreakerTripped]);

  // Validate data quality
  const validateDataQuality = useCallback((responseData) => {
    if (!responseData) return 'no_data';
    
    // Check if data is too old
    if (responseData.lastUpdated) {
      const dataAge = Date.now() - new Date(responseData.lastUpdated).getTime();
      if (dataAge > 24 * 60 * 60 * 1000) { // 24 hours
        return 'stale_data';
      }
    }
    
    // Check for FRED API data
    if (responseData.source === 'fred' || responseData.data?.some?.(d => d.source === 'fred')) {
      return 'excellent';
    }
    
    // Check for estimated/fallback data
    if (responseData.source === 'estimated' || responseData.data?.some?.(d => d.source === 'estimated')) {
      return 'estimated';
    }
    
    // Check data completeness
    if (Array.isArray(responseData.data)) {
      const validPoints = responseData.data.filter(point => 
        point.value !== null && point.value !== undefined && !isNaN(point.value)
      );
      const completeness = validPoints.length / responseData.data.length;
      
      if (completeness >= 0.9) return 'good';
      if (completeness >= 0.7) return 'fair';
      return 'poor';
    }
    
    return 'unknown';
  }, []);

  // Enhanced fetch function with circuit breaker and validation
  const fetchData = useCallback(async (isRetry = false) => {
    // Check circuit breaker
    if (isCircuitBreakerTripped() && !isRetry) {
      console.warn('🚫 Economic data circuit breaker is open, skipping request');
      setCircuitBreakerOpen(true);
      setError({
        type: 'circuit_breaker',
        message: 'Too many recent failures. Please wait before retrying.',
        isRecoverable: true
      });
      return;
    }

    setLoading(true);
    setError(null);
    lastRequestTimeRef.current = Date.now();

    try {
      let result;
      
      // Set timeout for the request
      const timeoutPromise = new Promise((_, reject) => {
        timeoutRef.current = setTimeout(() => {
          reject(new Error('Request timeout - Economic data taking too long to load'));
        }, fallbackTimeout);
      });

      const fetchPromise = (async () => {
        if (indicators && Array.isArray(indicators)) {
          // Fetch multiple indicators
          result = await economicDataService.getDashboardData();
        } else if (indicator) {
          // Fetch single indicator
          result = await economicDataService.getIndicator(indicator, options);
        } else {
          // Fetch default dashboard data
          result = await economicDataService.getDashboardData();
        }
        return result;
      })();

      result = await Promise.race([fetchPromise, timeoutPromise]);
      
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }

      // Validate data quality
      const quality = validateDataQuality(result);
      setDataQuality(quality);

      // Real-time validation
      if (enableRealTimeValidation && quality === 'poor') {
        console.warn('⚠️ Poor economic data quality detected, attempting refresh...');
        throw new Error('Data quality below threshold, retrying...');
      }

      // Success - reset failure count
      failureCountRef.current = 0;
      setCircuitBreakerOpen(false);
      setRetryCount(0);
      setData(result);
      setLastUpdated(Date.now());
      setIsUsingFallback(quality === 'estimated');
      
      console.log(`✅ Economic data loaded successfully (quality: ${quality})`);

    } catch (fetchError) {
      console.error('❌ Economic data fetch error:', fetchError);
      
      failureCountRef.current += 1;
      
      // Enhanced error classification
      const enhancedError = {
        ...fetchError,
        type: 'fetch_error',
        timestamp: Date.now(),
        retryCount,
        isRecoverable: true
      };

      // Determine if this is a network, API, or data issue
      if (fetchError.message?.includes('timeout')) {
        enhancedError.type = 'timeout';
        enhancedError.userMessage = 'Economic data request timed out. Please try again.';
      } else if (fetchError.message?.includes('network') || fetchError.name === 'TypeError') {
        enhancedError.type = 'network';
        enhancedError.userMessage = 'Network connection issue. Please check your internet connection.';
      } else if (fetchError.message?.includes('fred') || fetchError.message?.includes('api')) {
        enhancedError.type = 'api';
        enhancedError.userMessage = 'Economic data service temporarily unavailable. We\'re working to resolve this.';
      } else {
        enhancedError.type = 'unknown';
        enhancedError.userMessage = 'Unexpected error loading economic data. Please try again.';
      }

      setError(enhancedError);

      // Automatic retry logic (only for recoverable errors)
      if (retryCount < maxRetries && enhancedError.isRecoverable && !isCircuitBreakerTripped()) {
        console.log(`🔄 Retrying economic data fetch (attempt ${retryCount + 1}/${maxRetries})`);
        setRetryCount(prev => prev + 1);
        
        setTimeout(() => {
          fetchData(true);
        }, retryDelay * Math.pow(2, retryCount)); // Exponential backoff
      } else {
        // Try to provide fallback data for better UX
        try {
          console.log('🛡️ Attempting to provide fallback economic data...');
          const fallbackData = await economicDataService.getFallbackData(indicator || indicators);
          if (fallbackData) {
            setData(fallbackData);
            setDataQuality('fallback');
            setIsUsingFallback(true);
            console.log('✅ Fallback economic data provided');
          }
        } catch (fallbackError) {
          console.error('❌ Failed to provide fallback data:', fallbackError);
        }
      }
    } finally {
      setLoading(false);
      
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }
    }
  }, [
    indicator, 
    indicators, 
    options, 
    enableRealTimeValidation, 
    fallbackTimeout, 
    retryCount, 
    maxRetries, 
    retryDelay,
    isCircuitBreakerTripped,
    validateDataQuality
  ]);

  // Manual retry function
  const retry = useCallback(() => {
    if (circuitBreakerOpen) {
      resetCircuitBreaker();
    }
    setRetryCount(0);
    fetchData(true);
  }, [circuitBreakerOpen, resetCircuitBreaker, fetchData]);

  // Refresh function (bypasses circuit breaker)
  const refresh = useCallback(() => {
    failureCountRef.current = 0;
    setCircuitBreakerOpen(false);
    setRetryCount(0);
    fetchData(true);
  }, [fetchData]);

  // Auto-fetch on mount and dependency changes
  useEffect(() => {
    if (indicator || indicators) {
      fetchData();
    }
  }, [indicator, indicators, fetchData]);

  // Auto-refresh based on staleTime
  useEffect(() => {
    if (!data || !lastUpdated || !options.autoRefresh) return;
    
    const interval = setInterval(() => {
      const dataAge = Date.now() - lastUpdated;
      if (dataAge > staleTime) {
        console.log('🔄 Auto-refreshing stale economic data...');
        fetchData();
      }
    }, staleTime);
    
    return () => clearInterval(interval);
  }, [data, lastUpdated, staleTime, options.autoRefresh, fetchData]);

  // Circuit breaker reset timer
  useEffect(() => {
    const resetInterval = setInterval(resetCircuitBreaker, 30000); // Check every 30 seconds
    return () => clearInterval(resetInterval);
  }, [resetCircuitBreaker]);

  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, []);

  return {
    data,
    loading,
    error,
    dataQuality,
    lastUpdated,
    isUsingFallback,
    circuitBreakerOpen,
    retryCount,
    retry,
    refresh,
    // Status information
    canRetry: retryCount < maxRetries && !circuitBreakerOpen,
    isStale: lastUpdated && (Date.now() - lastUpdated) > staleTime,
    healthStatus: {
      dataQuality,
      isUsingFallback,
      circuitBreakerOpen,
      failureCount: failureCountRef.current,
      lastRequestTime: lastRequestTimeRef.current
    }
  };
};

// Specialized hooks for common economic data patterns
export const useEconomicIndicators = (options = {}) => {
  return useEconomicData({
    indicators: ['gdpGrowth', 'cpiYoY', 'unemployment', 'fedFunds', 'treasury10Y', 'vix'],
    options: { ...options, autoRefresh: true },
    enableRealTimeValidation: true
  });
};

export const useYieldCurve = (options = {}) => {
  return useEconomicData({
    indicator: 'yield_curve',
    options: { ...options, staleTime: 10 * 60 * 1000 }, // 10 minutes for yield curve
    enableRealTimeValidation: true
  });
};

export const useEconomicCalendar = (days = 7, options = {}) => {
  return useEconomicData({
    indicator: 'economic_calendar',
    options: { ...options, days, staleTime: 30 * 60 * 1000 }, // 30 minutes for calendar
    enableRealTimeValidation: false // Calendar data doesn't need real-time validation
  });
};

export default useEconomicData;