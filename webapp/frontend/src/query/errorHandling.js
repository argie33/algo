/**
 * React Query Error Handling - Comprehensive error handling for data fetching
 * Integrates with our error management system for better logging and recovery
 */

import { QueryClient } from '../hooks/useSimpleFetch.js';
import ErrorManager from '../error/ErrorManager';

// Create enhanced query client with comprehensive error handling
export const createErrorAwareQueryClient = () => {
  return new QueryClient({
    defaultOptions: {
      queries: {
        onError: (error, query) => {
          ErrorManager.handleError({
            type: 'react_query_error',
            message: `Query failed: ${JSON.stringify(query.queryKey)}`,
            error: error,
            category: ErrorManager.CATEGORIES.API,
            severity: ErrorManager.SEVERITY.MEDIUM,
            context: {
              queryKey: query.queryKey,
              queryHash: query.queryHash,
              failureCount: query.state.failureCount,
              errorUpdateCount: query.state.errorUpdateCount,
              dataUpdatedAt: query.state.dataUpdatedAt,
              source: 'react_query'
            }
          });
        },
        onSuccess: (data, query) => {
          // Log successful queries for debugging
          ErrorManager.handleError({
            type: 'react_query_success',
            message: `Query succeeded: ${JSON.stringify(query.queryKey)}`,
            category: ErrorManager.CATEGORIES.API,
            severity: ErrorManager.SEVERITY.LOW,
            context: {
              queryKey: query.queryKey,
              dataSize: JSON.stringify(data).length,
              fetchTime: Date.now() - query.state.dataUpdatedAt,
              source: 'react_query'
            }
          });
        },
        retry: (failureCount, error) => {
          // Custom retry logic with logging
          const shouldRetry = failureCount < 3;
          
          ErrorManager.handleError({
            type: 'react_query_retry',
            message: `Query retry ${failureCount}/3: ${shouldRetry ? 'retrying' : 'giving up'}`,
            category: ErrorManager.CATEGORIES.API,
            severity: shouldRetry ? ErrorManager.SEVERITY.LOW : ErrorManager.SEVERITY.MEDIUM,
            context: {
              failureCount,
              shouldRetry,
              error: error.message,
              source: 'react_query'
            }
          });
          
          return shouldRetry;
        },
        retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 30000)
      },
      mutations: {
        onError: (error, variables, context, mutation) => {
          ErrorManager.handleError({
            type: 'react_query_mutation_error',
            message: `Mutation failed: ${mutation.options.mutationKey || 'unknown'}`,
            error: error,
            category: ErrorManager.CATEGORIES.API,
            severity: ErrorManager.SEVERITY.HIGH,
            context: {
              mutationKey: mutation.options.mutationKey,
              variables: variables,
              mutationId: mutation.mutationId,
              failureCount: mutation.state.failureCount,
              source: 'react_query'
            }
          });
        },
        onSuccess: (data, variables, context, mutation) => {
          ErrorManager.handleError({
            type: 'react_query_mutation_success',
            message: `Mutation succeeded: ${mutation.options.mutationKey || 'unknown'}`,
            category: ErrorManager.CATEGORIES.API,
            severity: ErrorManager.SEVERITY.LOW,
            context: {
              mutationKey: mutation.options.mutationKey,
              variables: variables,
              responseSize: JSON.stringify(data).length,
              source: 'react_query'
            }
          });
        },
        retry: 2
      }
    }
  });
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

// Enhanced useMutation hook with error handling
export const useErrorAwareMutation = (mutationFn, options = {}) => {
  const enhancedOptions = {
    ...options,
    onError: (error, variables, context) => {
      const enhancedError = ErrorManager.handleError({
        type: 'use_mutation_error',
        message: `useMutation hook error: ${error.message}`,
        error: error,
        category: ErrorManager.CATEGORIES.API,
        severity: ErrorManager.SEVERITY.HIGH,
        context: {
          variables,
          context,
          componentStack: new Error().stack,
          source: 'useMutation_hook'
        }
      });

      // Call original onError if provided
      if (options.onError) {
        options.onError(enhancedError, variables, context);
      }
    },
    onSuccess: (data, variables, context) => {
      ErrorManager.handleError({
        type: 'use_mutation_success',
        message: `useMutation hook success`,
        category: ErrorManager.CATEGORIES.API,
        severity: ErrorManager.SEVERITY.LOW,
        context: {
          variables,
          responseSize: JSON.stringify(data).length,
          source: 'useMutation_hook'
        }
      });

      // Call original onSuccess if provided
      if (options.onSuccess) {
        options.onSuccess(data, variables, context);
      }
    }
  };

  return useMutation(mutationFn, enhancedOptions);
};

export default {
  createErrorAwareQueryClient,
  useErrorAwareQuery,
  useErrorAwareMutation
};