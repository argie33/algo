/**
 * TailwindCSS Error Boundary - Production-grade error handling without MUI
 * Provides graceful fallbacks, error reporting, and recovery mechanisms
 */

import React from 'react';
import { ExclamationTriangleIcon, ArrowPathIcon, HomeIcon } from '@heroicons/react/24/outline';

class ErrorBoundaryTailwind extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
      errorId: null,
      showDetails: false,
      retryCount: 0,
      maxRetries: 3,
      isRetrying: false
    };
  }

  static getDerivedStateFromError(error) {
    return { 
      hasError: true,
      errorId: Math.random().toString(36).substr(2, 9)
    };
  }

  componentDidCatch(error, errorInfo) {
    console.error('🚨 Error Boundary caught an error:', error);
    this.setState({ error, errorInfo });
    this.reportError(error, errorInfo);
  }

  reportError = (error, errorInfo) => {
    const errorReport = {
      id: this.state.errorId,
      message: error.message,
      stack: error.stack,
      componentStack: errorInfo.componentStack,
      timestamp: new Date().toISOString(),
      url: window.location.href,
      userAgent: navigator.userAgent,
      retryCount: this.state.retryCount,
      props: this.props
    };

    console.group('📊 Error Boundary Report');
    console.error('Error:', error);
    console.error('Error Info:', errorInfo);
    console.log('Full Report:', errorReport);
    console.groupEnd();

    // Send to error reporting service in production
    if (process.env.NODE_ENV === 'production') {
      this.sendErrorReport(errorReport);
    }
  };

  sendErrorReport = async (errorReport) => {
    try {
      // Send to your error reporting service
      await fetch('/api/errors', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(errorReport)
      });
    } catch (reportingError) {
      console.warn('Failed to send error report:', reportingError);
    }
  };

  handleRetry = () => {
    if (this.state.retryCount < this.state.maxRetries) {
      this.setState({ isRetrying: true });
      
      // Add a small delay to prevent rapid retries
      setTimeout(() => {
        this.setState(prevState => ({
          hasError: false,
          error: null,
          errorInfo: null,
          retryCount: prevState.retryCount + 1,
          isRetrying: false,
          showDetails: false
        }));
      }, 500);
    }
  };

  handleReload = () => {
    window.location.reload();
  };

  handleGoHome = () => {
    window.location.href = '/';
  };

  toggleDetails = () => {
    this.setState(prevState => ({
      showDetails: !prevState.showDetails
    }));
  };

  render() {
    if (this.state.hasError) {
      const { retryCount, maxRetries, errorId, showDetails, error, errorInfo, isRetrying } = this.state;
      const canRetry = retryCount < maxRetries;
      
      return (
        <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
          <div className="max-w-md w-full bg-white rounded-lg shadow-lg border border-red-200">
            {/* Header */}
            <div className="bg-red-50 border-b border-red-200 p-6 rounded-t-lg">
              <div className="flex items-center justify-center">
                <div className="flex-shrink-0">
                  <ExclamationTriangleIcon className="h-12 w-12 text-red-600" />
                </div>
              </div>
              <div className="mt-4 text-center">
                <h3 className="text-lg font-medium text-red-900">
                  Something went wrong
                </h3>
                <p className="mt-2 text-sm text-red-700">
                  We encountered an unexpected error. Please try again.
                </p>
              </div>
            </div>

            {/* Content */}
            <div className="p-6">
              {/* Error ID */}
              <div className="mb-4 text-center">
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800">
                  Error ID: {errorId}
                </span>
              </div>

              {/* Retry Info */}
              {retryCount > 0 && (
                <div className="mb-4 p-3 bg-yellow-50 border border-yellow-200 rounded-md">
                  <p className="text-sm text-yellow-800">
                    Retry attempt {retryCount} of {maxRetries}
                  </p>
                </div>
              )}

              {/* Action Buttons */}
              <div className="space-y-3">
                {canRetry && (
                  <button
                    onClick={this.handleRetry}
                    disabled={isRetrying}
                    className={`w-full flex justify-center items-center px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white ${
                      isRetrying 
                        ? 'bg-gray-400 cursor-not-allowed' 
                        : 'bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500'
                    }`}
                  >
                    <ArrowPathIcon className={`-ml-1 mr-2 h-4 w-4 ${isRetrying ? 'animate-spin' : ''}`} />
                    {isRetrying ? 'Retrying...' : 'Try Again'}
                  </button>
                )}

                <button
                  onClick={this.handleReload}
                  className="w-full flex justify-center items-center px-4 py-2 border border-gray-300 rounded-md shadow-sm bg-white text-sm font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
                >
                  <ArrowPathIcon className="-ml-1 mr-2 h-4 w-4" />
                  Refresh Page
                </button>

                <button
                  onClick={this.handleGoHome}
                  className="w-full flex justify-center items-center px-4 py-2 border border-gray-300 rounded-md shadow-sm bg-white text-sm font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
                >
                  <HomeIcon className="-ml-1 mr-2 h-4 w-4" />
                  Go Home
                </button>
              </div>

              {/* Error Details Toggle */}
              <div className="mt-4">
                <button
                  onClick={this.toggleDetails}
                  className="text-sm text-gray-500 hover:text-gray-700 focus:outline-none focus:underline"
                >
                  {showDetails ? 'Hide' : 'Show'} error details
                </button>
              </div>

              {/* Error Details */}
              {showDetails && error && (
                <div className="mt-4 p-4 bg-gray-50 border border-gray-200 rounded-md">
                  <h4 className="text-sm font-medium text-gray-900 mb-2">Error Details</h4>
                  <div className="text-xs text-gray-600 space-y-2">
                    <div>
                      <span className="font-medium">Message:</span>
                      <pre className="mt-1 whitespace-pre-wrap break-words">{error.message}</pre>
                    </div>
                    
                    {process.env.NODE_ENV === 'development' && error.stack && (
                      <div>
                        <span className="font-medium">Stack Trace:</span>
                        <pre className="mt-1 whitespace-pre-wrap break-words text-xs">
                          {error.stack}
                        </pre>
                      </div>
                    )}
                    
                    {process.env.NODE_ENV === 'development' && errorInfo?.componentStack && (
                      <div>
                        <span className="font-medium">Component Stack:</span>
                        <pre className="mt-1 whitespace-pre-wrap break-words text-xs">
                          {errorInfo.componentStack}
                        </pre>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="bg-gray-50 border-t border-gray-200 px-6 py-3 rounded-b-lg">
              <p className="text-xs text-gray-500 text-center">
                If this problem persists, please contact support with error ID: {errorId}
              </p>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundaryTailwind;