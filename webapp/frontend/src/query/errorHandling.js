/**
 * Custom Query Error Handling - Comprehensive error handling for data fetching
 * Integrates with our error management system for better logging and recovery
 */

import { useSimpleFetch } from '../hooks/useSimpleFetch.js';
import ErrorManager from '../error/ErrorManager';

// Error handling configuration for custom fetch implementation
export const createErrorAwareConfig = () => {
  return {
    defaultRetry: 3,
    retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 30000),
    onError: (error, context = {}) => {
      ErrorManager.handleError({
        type: 'custom_query_error',
        message: `Query failed: ${context.url || 'unknown'}`,
        error: error,
        category: ErrorManager.CATEGORIES.API,
        severity: ErrorManager.SEVERITY.MEDIUM,
        context: {
          url: context.url,
          source: 'custom_fetch'
        }
      });
    },
    onSuccess: (data, context = {}) => {
      ErrorManager.handleError({
        type: 'custom_query_success',
        message: `Query succeeded: ${context.url || 'unknown'}`,
        category: ErrorManager.CATEGORIES.API,
        severity: ErrorManager.SEVERITY.LOW,
        context: {
          url: context.url,
          dataSize: JSON.stringify(data).length,
          source: 'custom_fetch'
        }
      });
    }
  };
};

// Enhanced useSimpleFetch hook with error handling
export const useErrorAwareQuery = (queryKey, queryFn, options = {}) => {
  const enhancedOptions = {
    ...options,
    onError: (error) => {
      // Custom error handling
      const enhancedError = ErrorManager.handleError({
        type: 'use_query_error',
        message: `useSimpleFetch hook error: ${JSON.stringify(queryKey)}`,
        error: error,
        category: ErrorManager.CATEGORIES.API,
        severity: ErrorManager.SEVERITY.MEDIUM,
        context: {
          queryKey,
          componentStack: new Error().stack,
          hookOptions: options,
          source: 'useSimpleFetch_hook'
        }
      });

      // Call original onError if provided
      if (options.onError) {
        options.onError(enhancedError);
      }
    },
    onSuccess: (data) => {
      // Log successful data fetching
      ErrorManager.handleError({
        type: 'use_query_success',
        message: `useSimpleFetch hook success: ${JSON.stringify(queryKey)}`,
        category: ErrorManager.CATEGORIES.API,
        severity: ErrorManager.SEVERITY.LOW,
        context: {
          queryKey,
          dataSize: JSON.stringify(data).length,
          source: 'useSimpleFetch_hook'
        }
      });

      // Call original onSuccess if provided
      if (options.onSuccess) {
        options.onSuccess(data);
      }
    }
  };

  return useSimpleFetch(queryKey, queryFn, enhancedOptions);
};

// Enhanced mutation helper with error handling
export const useErrorAwareMutation = (mutationFn, options = {}) => {
  const enhancedMutationFn = async (variables) => {
    try {
      const result = await mutationFn(variables);
      
      ErrorManager.handleError({
        type: 'use_mutation_success',
        message: `Custom mutation success`,
        category: ErrorManager.CATEGORIES.API,
        severity: ErrorManager.SEVERITY.LOW,
        context: {
          variables,
          responseSize: JSON.stringify(result).length,
          source: 'custom_mutation'
        }
      });

      if (options.onSuccess) {
        options.onSuccess(result, variables);
      }
      
      return result;
    } catch (error) {
      const enhancedError = ErrorManager.handleError({
        type: 'use_mutation_error',
        message: `Custom mutation error: ${error.message}`,
        error: error,
        category: ErrorManager.CATEGORIES.API,
        severity: ErrorManager.SEVERITY.HIGH,
        context: {
          variables,
          componentStack: new Error().stack,
          source: 'custom_mutation'
        }
      });

      if (options.onError) {
        options.onError(enhancedError, variables);
      }
      
      throw enhancedError;
    }
  };

  return { mutateAsync: enhancedMutationFn };
};

export default {
  createErrorAwareConfig,
  useErrorAwareQuery,
  useErrorAwareMutation
};