/**
 * Error Boundary Route - Route-level error handling with comprehensive logging
 * Wraps routes with error boundaries and provides fallback UI
 */

import React, { Suspense } from 'react';
import { ErrorBoundary } from 'react-error-boundary';
import ErrorManager from '../error/ErrorManager';

// Route-level error fallback component
const RouteErrorFallback = ({ error, resetErrorBoundary, routeName }) => {
  const errorId = `route_error_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  
  React.useEffect(() => {
    // Log route-level error
    ErrorManager.handleError({
      type: 'route_error',
      message: `Route error in ${routeName}: ${error.message}`,
      error: error,
      category: ErrorManager.CATEGORIES.UI,
      severity: ErrorManager.SEVERITY.HIGH,
      context: {
        routeName,
        errorId,
        url: window.location.href,
        userAgent: navigator.userAgent,
        timestamp: new Date().toISOString(),
        stack: error.stack
      }
    });
  }, [error, routeName, errorId]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="max-w-md w-full bg-white shadow-lg rounded-lg p-6">
        <div className="flex items-center mb-4">
          <div className="text-red-500 text-3xl mr-3">⚠️</div>
          <div>
            <h1 className="text-xl font-semibold text-gray-900">Page Error</h1>
            <p className="text-sm text-gray-600">Something went wrong with this page</p>
          </div>
        </div>
        
        <div className="mb-4">
          <p className="text-gray-700 mb-2">
            We encountered an error while loading the {routeName} page.
          </p>
          <div className="bg-gray-100 rounded p-2 mb-4">
            <p className="text-xs font-mono text-gray-600">Error ID: {errorId}</p>
          </div>
        </div>

        <div className="flex gap-3">
          <button
            onClick={resetErrorBoundary}
            className="flex-1 bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700 transition-colors"
          >
            Try Again
          </button>
          <button
            onClick={() => window.location.href = '/'}
            className="flex-1 border border-gray-300 text-gray-700 px-4 py-2 rounded hover:bg-gray-50 transition-colors"
          >
            Go Home
          </button>
        </div>

        {import.meta.env.DEV && (
          <details className="mt-4">
            <summary className="text-sm text-gray-600 cursor-pointer">
              Developer Information
            </summary>
            <pre className="mt-2 text-xs bg-red-100 p-2 rounded overflow-auto max-h-32 text-red-800">
              {error.message}
              {error.stack && '\n\n' + error.stack}
            </pre>
          </details>
        )}
      </div>
    </div>
  );
};

// Loading fallback component
const RouteLoadingFallback = ({ routeName }) => (
  <div className="min-h-screen flex items-center justify-center">
    <div className="text-center">
      <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
      <p className="text-gray-600">Loading {routeName}...</p>
    </div>
  </div>
);

// Enhanced route wrapper with comprehensive error handling
export const ErrorBoundaryRoute = ({ 
  children, 
  routeName = 'Unknown Route',
  fallback = null,
  loadingFallback = null,
  onError = null 
}) => {
  const handleError = (error, errorInfo) => {
    // Log route error with full context
    const enhancedError = ErrorManager.handleError({
      type: 'route_boundary_error',
      message: `Error boundary caught error in route ${routeName}`,
      error: error,
      category: ErrorManager.CATEGORIES.UI,
      severity: ErrorManager.SEVERITY.HIGH,
      context: {
        routeName,
        componentStack: errorInfo.componentStack,
        errorBoundary: 'ErrorBoundaryRoute',
        url: window.location.href,
        referrer: document.referrer,
        timestamp: new Date().toISOString(),
        userAgent: navigator.userAgent
      }
    });

    // Call custom error handler if provided
    if (onError) {
      onError(enhancedError, errorInfo);
    }
  };

  const handleReset = () => {
    ErrorManager.handleError({
      type: 'route_error_reset',
      message: `Route error boundary reset for ${routeName}`,
      category: ErrorManager.CATEGORIES.UI,
      severity: ErrorManager.SEVERITY.LOW,
      context: {
        routeName,
        url: window.location.href,
        timestamp: new Date().toISOString()
      }
    });
  };

  return (
    <ErrorBoundary
      FallbackComponent={fallback || ((props) => <RouteErrorFallback {...props} routeName={routeName} />)}
      onError={handleError}
      onReset={handleReset}
    >
      <Suspense fallback={loadingFallback || <RouteLoadingFallback routeName={routeName} />}>
        {children}
      </Suspense>
    </ErrorBoundary>
  );
};

// HOC for wrapping components with route-level error handling
export const withRouteErrorHandling = (Component, routeName) => {
  const WrappedComponent = (props) => (
    <ErrorBoundaryRoute routeName={routeName}>
      <Component {...props} />
    </ErrorBoundaryRoute>
  );

  WrappedComponent.displayName = `withRouteErrorHandling(${routeName})`;
  return WrappedComponent;
};

// Navigation error handler
export const NavigationErrorHandler = () => {
  React.useEffect(() => {
    const handleNavigationError = (event) => {
      ErrorManager.handleError({
        type: 'navigation_error',
        message: `Navigation error: ${event.message || 'Unknown navigation error'}`,
        category: ErrorManager.CATEGORIES.UI,
        severity: ErrorManager.SEVERITY.MEDIUM,
        context: {
          url: window.location.href,
          event: event,
          timestamp: new Date().toISOString()
        }
      });
    };

    // Listen for unhandled navigation errors
    window.addEventListener('unhandledrejection', handleNavigationError);
    
    return () => {
      window.removeEventListener('unhandledrejection', handleNavigationError);
    };
  }, []);

  return null;
};

export default ErrorBoundaryRoute;