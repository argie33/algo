/**
 * useErrorHandler - React hook for component-level error handling
 * Provides async error handling, retry logic, and loading states
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import errorManager from './ErrorManager';

export const useErrorHandler = (options = {}) => {
  const {
    maxRetries = 3,
    retryDelay = 1000,
    category = errorManager.CATEGORIES.API,
    onError,
    onRetry,
    onSuccess
  } = options;

  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [retryCount, setRetryCount] = useState(0);
  const abortControllerRef = useRef(null);

  // Clear error when component unmounts or error changes
  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  /**
   * Execute an async operation with error handling
   */
  const execute = useCallback(async (asyncOperation, context = {}) => {
    // Create new abort controller for this operation
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    abortControllerRef.current = new AbortController();

    setLoading(true);
    setError(null);

    try {
      const result = await asyncOperation(abortControllerRef.current.signal);
      
      // Reset retry count on success
      setRetryCount(0);
      
      // Call success callback
      if (onSuccess) {
        onSuccess(result);
      }
      
      return result;
    } catch (err) {
      // Don't handle aborted requests
      if (err.name === 'AbortError') {
        return;
      }

      // Create enhanced error
      const enhancedError = errorManager.handleError({
        type: 'async_operation',
        message: err.message || 'Operation failed',
        error: err,
        category,
        severity: errorManager.SEVERITY.MEDIUM,
        context: {
          retryCount,
          ...context
        },
        retryCallback: () => execute(asyncOperation, context),
        autoRecover: false // Manual retry control
      });

      setError(enhancedError);

      // Call error callback
      if (onError) {
        onError(enhancedError);
      }

      throw enhancedError;
    } finally {
      setLoading(false);
    }
  }, [category, retryCount, onError, onSuccess]);

  /**
   * Retry the last failed operation
   */
  const retry = useCallback(async (customOperation) => {
    if (!error && !customOperation) {
      console.warn('No error to retry and no custom operation provided');
      return;
    }

    if (retryCount >= maxRetries) {
      console.warn('Maximum retry attempts reached');
      return;
    }

    setRetryCount(prev => prev + 1);

    // Call retry callback
    if (onRetry) {
      onRetry(retryCount + 1);
    }

    // Delay before retry
    if (retryDelay > 0) {
      await new Promise(resolve => setTimeout(resolve, retryDelay * Math.pow(2, retryCount)));
    }

    if (customOperation) {
      return execute(customOperation);
    } else if (error?.retryCallback) {
      return error.retryCallback();
    }
  }, [error, retryCount, maxRetries, retryDelay, onRetry, execute]);

  /**
   * Clear the current error
   */
  const clearError = useCallback(() => {
    setError(null);
    setRetryCount(0);
  }, []);

  /**
   * Reset all state
   */
  const reset = useCallback(() => {
    setError(null);
    setLoading(false);
    setRetryCount(0);
    
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
  }, []);

  /**
   * Check if can retry
   */
  const canRetry = retryCount < maxRetries;

  return {
    error,
    loading,
    retryCount,
    canRetry,
    execute,
    retry,
    clearError,
    reset
  };
};

/**
 * Hook for handling API calls specifically
 */
export const useApiErrorHandler = (options = {}) => {
  return useErrorHandler({
    category: errorManager.CATEGORIES.API,
    maxRetries: 3,
    retryDelay: 1000,
    ...options
  });
};

/**
 * Hook for handling network operations
 */
export const useNetworkErrorHandler = (options = {}) => {
  return useErrorHandler({
    category: errorManager.CATEGORIES.NETWORK,
    maxRetries: 5,
    retryDelay: 2000,
    ...options
  });
};

/**
 * Hook for handling authentication operations
 */
export const useAuthErrorHandler = (options = {}) => {
  return useErrorHandler({
    category: errorManager.CATEGORIES.AUTH,
    maxRetries: 1,
    retryDelay: 0,
    ...options
  });
};

/**
 * Hook for handling form validation
 */
export const useValidationErrorHandler = (options = {}) => {
  return useErrorHandler({
    category: errorManager.CATEGORIES.VALIDATION,
    maxRetries: 0,
    retryDelay: 0,
    ...options
  });
};

export default useErrorHandler;