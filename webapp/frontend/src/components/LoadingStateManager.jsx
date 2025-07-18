/**
 * Loading State Manager - Comprehensive loading states and user feedback
 * Provides skeleton loading, progress indicators, and timeout handling
 */

import React, { useState, useEffect, createContext, useContext } from 'react';
import { ArrowPathIcon, ExclamationTriangleIcon } from '@heroicons/react/24/outline';

// Loading Context
const LoadingContext = createContext();

export const useLoading = () => {
  const context = useContext(LoadingContext);
  if (!context) {
    throw new Error('useLoading must be used within a LoadingProvider');
  }
  return context;
};

// Loading Provider
export const LoadingProvider = ({ children }) => {
  const [loadingStates, setLoadingStates] = useState({});
  const [errors, setErrors] = useState({});

  const setLoading = (key, isLoading, options = {}) => {
    setLoadingStates(prev => ({
      ...prev,
      [key]: {
        isLoading,
        startTime: isLoading ? Date.now() : null,
        message: options.message || '',
        timeout: options.timeout || 30000
      }
    }));

    // Clear error when starting to load
    if (isLoading) {
      setErrors(prev => {
        const newErrors = { ...prev };
        delete newErrors[key];
        return newErrors;
      });
    }
  };

  const setError = (key, error) => {
    setErrors(prev => ({
      ...prev,
      [key]: {
        message: error?.message || String(error),
        timestamp: Date.now(),
        retryable: true
      }
    }));
    
    // Stop loading
    setLoading(key, false);
  };

  const clearError = (key) => {
    setErrors(prev => {
      const newErrors = { ...prev };
      delete newErrors[key];
      return newErrors;
    });
  };

  const isLoading = (key) => loadingStates[key]?.isLoading || false;
  const getError = (key) => errors[key];

  const value = {
    setLoading,
    setError,
    clearError,
    isLoading,
    getError,
    loadingStates,
    errors
  };

  return (
    <LoadingContext.Provider value={value}>
      {children}
    </LoadingContext.Provider>
  );
};

// Loading Spinner Component
export const LoadingSpinner = ({ size = 'md', color = 'blue' }) => {
  const sizeClasses = {
    sm: 'h-4 w-4',
    md: 'h-6 w-6',
    lg: 'h-8 w-8',
    xl: 'h-12 w-12'
  };

  const colorClasses = {
    blue: 'text-blue-600',
    gray: 'text-gray-600',
    white: 'text-white'
  };

  return (
    <ArrowPathIcon 
      className={`${sizeClasses[size]} ${colorClasses[color]} animate-spin`}
    />
  );
};

// Skeleton Loading Component
export const SkeletonLoader = ({ lines = 3, className = '' }) => {
  return (
    <div className={`animate-pulse ${className}`}>
      {Array.from({ length: lines }).map((_, index) => (
        <div
          key={index}
          className={`bg-gray-300 rounded h-4 mb-2 ${
            index === lines - 1 ? 'w-3/4' : 'w-full'
          }`}
        />
      ))}
    </div>
  );
};

// Loading Button Component
export const LoadingButton = ({ 
  children, 
  isLoading = false, 
  disabled = false,
  className = '',
  loadingText = 'Loading...',
  ...props 
}) => {
  return (
    <button
      {...props}
      disabled={disabled || isLoading}
      className={`relative inline-flex items-center justify-center ${
        isLoading || disabled 
          ? 'cursor-not-allowed opacity-75' 
          : 'cursor-pointer'
      } ${className}`}
    >
      {isLoading && (
        <LoadingSpinner size="sm" className="mr-2" />
      )}
      {isLoading ? loadingText : children}
    </button>
  );
};

// Loading Overlay Component
export const LoadingOverlay = ({ 
  isLoading, 
  message = 'Loading...', 
  children 
}) => {
  if (!isLoading) return children;

  return (
    <div className="relative">
      {children}
      <div className="absolute inset-0 bg-white bg-opacity-75 flex items-center justify-center z-50">
        <div className="flex flex-col items-center space-y-2">
          <LoadingSpinner size="lg" />
          <p className="text-sm text-gray-600">{message}</p>
        </div>
      </div>
    </div>
  );
};

// Loading Card Component
export const LoadingCard = ({ 
  title = 'Loading...', 
  description,
  progress = null,
  onCancel = null 
}) => {
  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
      <div className="flex items-center space-x-3">
        <LoadingSpinner size="lg" />
        <div className="flex-1">
          <h3 className="text-lg font-medium text-gray-900">{title}</h3>
          {description && (
            <p className="text-sm text-gray-600 mt-1">{description}</p>
          )}
          {progress !== null && (
            <div className="mt-2">
              <div className="bg-gray-200 rounded-full h-2">
                <div 
                  className="bg-blue-600 h-2 rounded-full transition-all duration-300"
                  style={{ width: `${Math.min(100, Math.max(0, progress))}%` }}
                />
              </div>
              <p className="text-xs text-gray-500 mt-1">{Math.round(progress)}% complete</p>
            </div>
          )}
        </div>
        {onCancel && (
          <button
            onClick={onCancel}
            className="text-gray-400 hover:text-gray-600 focus:outline-none"
          >
            <span className="sr-only">Cancel</span>
            ×
          </button>
        )}
      </div>
    </div>
  );
};

// Error Card Component
export const ErrorCard = ({ 
  error, 
  onRetry = null, 
  onDismiss = null,
  retryText = 'Try Again' 
}) => {
  return (
    <div className="bg-red-50 border border-red-200 rounded-lg p-4">
      <div className="flex items-start space-x-3">
        <ExclamationTriangleIcon className="h-5 w-5 text-red-600 mt-0.5" />
        <div className="flex-1">
          <h3 className="text-sm font-medium text-red-900">
            Something went wrong
          </h3>
          <p className="text-sm text-red-700 mt-1">
            {error?.message || 'An unexpected error occurred'}
          </p>
          <div className="mt-3 flex space-x-2">
            {onRetry && (
              <button
                onClick={onRetry}
                className="text-sm bg-red-600 text-white px-3 py-1 rounded hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-500"
              >
                {retryText}
              </button>
            )}
            {onDismiss && (
              <button
                onClick={onDismiss}
                className="text-sm text-red-600 hover:text-red-800 focus:outline-none"
              >
                Dismiss
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

// Loading State Hook
export const useLoadingState = (key) => {
  const { setLoading, setError, clearError, isLoading, getError } = useLoading();

  const startLoading = (options) => setLoading(key, true, options);
  const stopLoading = () => setLoading(key, false);
  const reportError = (error) => setError(key, error);
  const clearCurrentError = () => clearError(key);

  return {
    isLoading: isLoading(key),
    error: getError(key),
    startLoading,
    stopLoading,
    reportError,
    clearError: clearCurrentError
  };
};

// With Loading HOC
export const withLoading = (WrappedComponent, loadingKey) => {
  return function WithLoadingComponent(props) {
    const loadingState = useLoadingState(loadingKey);
    return <WrappedComponent {...props} loading={loadingState} />;
  };
};

export default LoadingProvider;