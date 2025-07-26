/**
 * Centralized Error Handling Utilities
 * Standardizes error handling patterns across all components
 * 
 * PERFORMANCE FIX: Eliminates inconsistent error handling patterns
 */

import React from 'react';
import { Alert, Typography } from '@mui/material';

// Error types for consistent classification
export const ERROR_TYPES = {
  NETWORK: 'NETWORK',
  VALIDATION: 'VALIDATION', 
  AUTHENTICATION: 'AUTHENTICATION',
  AUTHORIZATION: 'AUTHORIZATION',
  API: 'API',
  COMPONENT: 'COMPONENT',
  DATA: 'DATA',
  TIMEOUT: 'TIMEOUT',
  CONFIGURATION: 'CONFIGURATION',
  UNKNOWN: 'UNKNOWN'
};

// Error severity levels
export const ERROR_SEVERITY = {
  LOW: 'low',
  MEDIUM: 'medium',
  HIGH: 'high',
  CRITICAL: 'critical'
};

/**
 * Standardized error object structure
 */
export class StandardError extends Error {
  constructor(message, type = ERROR_TYPES.UNKNOWN, severity = ERROR_SEVERITY.MEDIUM, details = {}) {
    super(message);
    this.name = 'StandardError';
    this.type = type;
    this.severity = severity;
    this.details = details;
    this.timestamp = new Date().toISOString();
    this.id = Math.random().toString(36).substr(2, 9);
  }
}

/**
 * Error classification utility
 */
export const classifyError = (error) => {
  if (!error) return { type: ERROR_TYPES.UNKNOWN, severity: ERROR_SEVERITY.LOW };
  
  const message = error.message?.toLowerCase() || '';
  const code = error.code?.toLowerCase() || '';
  
  // Network errors
  if (message.includes('network') || message.includes('fetch') || message.includes('connection') || code === 'network_error') {
    return { type: ERROR_TYPES.NETWORK, severity: ERROR_SEVERITY.HIGH };
  }
  
  // Authentication errors
  if (message.includes('unauthorized') || message.includes('auth') || error.status === 401) {
    return { type: ERROR_TYPES.AUTHENTICATION, severity: ERROR_SEVERITY.HIGH };
  }
  
  // Authorization errors
  if (message.includes('forbidden') || message.includes('permission') || error.status === 403) {
    return { type: ERROR_TYPES.AUTHORIZATION, severity: ERROR_SEVERITY.MEDIUM };
  }
  
  // API errors
  if (error.status >= 400 || message.includes('api') || message.includes('server')) {
    return { type: ERROR_TYPES.API, severity: ERROR_SEVERITY.MEDIUM };
  }
  
  // Timeout errors
  if (message.includes('timeout') || code === 'timeout') {
    return { type: ERROR_TYPES.TIMEOUT, severity: ERROR_SEVERITY.MEDIUM };
  }
  
  // Validation errors
  if (message.includes('validation') || message.includes('invalid') || message.includes('required')) {
    return { type: ERROR_TYPES.VALIDATION, severity: ERROR_SEVERITY.LOW };
  }
  
  // Configuration errors
  if (message.includes('config') || message.includes('environment')) {
    return { type: ERROR_TYPES.CONFIGURATION, severity: ERROR_SEVERITY.HIGH };
  }
  
  return { type: ERROR_TYPES.UNKNOWN, severity: ERROR_SEVERITY.MEDIUM };
};

/**
 * Enhanced error logging with context
 */
export const logError = (error, context = {}) => {
  const { type, severity } = classifyError(error);
  const errorLog = {
    id: error.id || Math.random().toString(36).substr(2, 9),
    message: error.message,
    type,
    severity,
    stack: error.stack,
    timestamp: new Date().toISOString(),
    context,
    userAgent: navigator.userAgent,
    url: window.location.href
  };
  
  // Console logging with appropriate level
  const logMethod = severity === ERROR_SEVERITY.CRITICAL ? 'error' : 
                   severity === ERROR_SEVERITY.HIGH ? 'error' :
                   severity === ERROR_SEVERITY.MEDIUM ? 'warn' : 'info';
  
  console[logMethod](`🚨 [${type}] ${error.message}`, errorLog);
  
  // In production, send to error tracking service
  if (process.env.NODE_ENV === 'production') {
    // TODO: Integrate with error tracking service (Sentry, etc.)
    // sendToErrorTracking(errorLog);
  }
  
  return errorLog;
};

/**
 * Async error handler with retry logic
 */
export const handleAsyncError = async (asyncFn, options = {}) => {
  const {
    retries = 3,
    retryDelay = 1000,
    onError = null,
    context = {}
  } = options;
  
  let lastError;
  
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      return await asyncFn();
    } catch (error) {
      lastError = error;
      const { type, severity } = classifyError(error);
      
      // Don't retry validation or authentication errors
      if (type === ERROR_TYPES.VALIDATION || type === ERROR_TYPES.AUTHENTICATION) {
        break;
      }
      
      // Don't retry on last attempt
      if (attempt === retries) {
        break;
      }
      
      // Wait before retry
      await new Promise(resolve => setTimeout(resolve, retryDelay * (attempt + 1)));
    }
  }
  
  // Log the final error
  const errorLog = logError(lastError, { ...context, attempts: retries + 1 });
  
  // Call custom error handler if provided
  if (onError) {
    onError(lastError, errorLog);
  }
  
  throw lastError;
};

/**
 * React error handler hook for consistent component error handling
 */
export const useErrorHandler = () => {
  const [error, setError] = React.useState(null);
  const [loading, setLoading] = React.useState(false);
  
  const handleError = React.useCallback((error, context = {}) => {
    const errorLog = logError(error, context);
    setError(errorLog);
    setLoading(false);
    return errorLog;
  }, []);
  
  const clearError = React.useCallback(() => {
    setError(null);
  }, []);
  
  const executeAsync = React.useCallback(async (asyncFn, options = {}) => {
    try {
      setLoading(true);
      setError(null);
      const result = await handleAsyncError(asyncFn, {
        ...options,
        onError: (error, errorLog) => setError(errorLog)
      });
      setLoading(false);
      return result;
    } catch (error) {
      setLoading(false);
      throw error;
    }
  }, []);
  
  return {
    error,
    loading,
    handleError,
    clearError,
    executeAsync
  };
};

/**
 * Error message formatter for user-friendly display
 */
export const formatErrorMessage = (error) => {
  if (!error) return 'An unknown error occurred';
  
  const { type } = classifyError(error);
  
  switch (type) {
    case ERROR_TYPES.NETWORK:
      return 'Network connection error. Please check your internet connection and try again.';
    case ERROR_TYPES.AUTHENTICATION:
      return 'Authentication required. Please sign in to continue.';
    case ERROR_TYPES.AUTHORIZATION:
      return 'You do not have permission to perform this action.';
    case ERROR_TYPES.VALIDATION:
      return error.message || 'Please check your input and try again.';
    case ERROR_TYPES.TIMEOUT:
      return 'Request timed out. Please try again.';
    case ERROR_TYPES.API:
      return 'Server error. Please try again later.';
    case ERROR_TYPES.CONFIGURATION:
      return 'Configuration error. Please contact support.';
    default:
      return error.message || 'An unexpected error occurred.';
  }
};

/**
 * Error recovery suggestions
 */
export const getErrorRecoveryActions = (error) => {
  const { type } = classifyError(error);
  
  const baseActions = [
    { label: 'Try Again', action: 'retry' },
    { label: 'Refresh Page', action: 'refresh' }
  ];
  
  switch (type) {
    case ERROR_TYPES.NETWORK:
      return [
        { label: 'Check Connection', action: 'check_network' },
        ...baseActions
      ];
    case ERROR_TYPES.AUTHENTICATION:
      return [
        { label: 'Sign In', action: 'sign_in' },
        { label: 'Go to Dashboard', action: 'navigate_dashboard' }
      ];
    case ERROR_TYPES.AUTHORIZATION:
      return [
        { label: 'Go Back', action: 'go_back' },
        { label: 'Go to Dashboard', action: 'navigate_dashboard' }
      ];
    case ERROR_TYPES.VALIDATION:
      return [
        { label: 'Fix Input', action: 'fix_validation' }
      ];
    default:
      return baseActions;
  }
};

/**
 * Component wrapper for consistent error handling
 */
export const withErrorHandling = (WrappedComponent) => {
  return function ErrorHandledComponent(props) {
    const { error, handleError, clearError } = useErrorHandler();
    
    if (error) {
      return (
        <Alert 
          severity={error.severity === ERROR_SEVERITY.CRITICAL ? 'error' : 'warning'}
          onClose={clearError}
          sx={{ m: 2 }}
        >
          <Typography variant="subtitle2" gutterBottom>
            {formatErrorMessage(error)}
          </Typography>
          {error.id && (
            <Typography variant="caption" color="text.secondary">
              Error ID: {error.id}
            </Typography>
          )}
        </Alert>
      );
    }
    
    return (
      <WrappedComponent 
        {...props}
        onError={handleError}  
        clearError={clearError}
      />
    );
  };
};

export default {
  ERROR_TYPES,
  ERROR_SEVERITY,
  StandardError,
  classifyError,
  logError,
  handleAsyncError,
  useErrorHandler,
  formatErrorMessage,
  getErrorRecoveryActions,
  withErrorHandling
};