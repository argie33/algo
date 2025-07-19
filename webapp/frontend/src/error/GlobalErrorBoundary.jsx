/**
 * GlobalErrorBoundary - React error boundary with comprehensive error handling
 * Catches all unhandled React errors and provides graceful fallbacks
 */

import React from 'react';
import errorManager from './ErrorManager';

class GlobalErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
      errorId: null,
      retryCount: 0
    };
  }

  static getDerivedStateFromError(error) {
    // Update state so the next render will show the fallback UI
    return { hasError: true };
  }

  componentDidCatch(error, errorInfo) {
    // Handle the error through our error manager
    const managedError = errorManager.handleError({
      type: 'react_error',
      message: error.message,
      error: error,
      componentStack: errorInfo.componentStack,
      category: errorManager.CATEGORIES.UI,
      severity: errorManager.SEVERITY.HIGH,
      context: {
        componentName: this.props.name || 'GlobalErrorBoundary',
        props: this.props.children?.props,
        retryCount: this.state.retryCount
      }
    });

    this.setState({
      error,
      errorInfo,
      errorId: managedError.id
    });

    // Report to parent if callback provided
    if (this.props.onError) {
      this.props.onError(error, errorInfo, managedError);
    }
  }

  handleRetry = () => {
    this.setState(prevState => ({
      hasError: false,
      error: null,
      errorInfo: null,
      errorId: null,
      retryCount: prevState.retryCount + 1
    }));
  };

  handleReload = () => {
    if (typeof window !== 'undefined') {
      window.location.reload();
    }
  };

  handleReportIssue = () => {
    const errorReport = {
      errorId: this.state.errorId,
      message: this.state.error?.message,
      stack: this.state.error?.stack,
      componentStack: this.state.errorInfo?.componentStack,
      url: window.location.href,
      timestamp: new Date().toISOString(),
      userAgent: navigator.userAgent,
      retryCount: this.state.retryCount
    };

    // Copy to clipboard for user
    if (navigator.clipboard) {
      navigator.clipboard.writeText(JSON.stringify(errorReport, null, 2))
        .then(() => {
          alert('Error report copied to clipboard. Please send this to our support team.');
        })
        .catch(() => {
          this.fallbackCopyToClipboard(errorReport);
        });
    } else {
      this.fallbackCopyToClipboard(errorReport);
    }
  };

  fallbackCopyToClipboard = (errorReport) => {
    const textArea = document.createElement('textarea');
    textArea.value = JSON.stringify(errorReport, null, 2);
    document.body.appendChild(textArea);
    textArea.select();
    try {
      document.execCommand('copy');
      alert('Error report copied to clipboard. Please send this to our support team.');
    } catch (err) {
      console.log('Error report:', errorReport);
      alert('Error report logged to console. Please copy and send to our support team.');
    }
    document.body.removeChild(textArea);
  };

  handleNavigateHome = () => {
    if (typeof window !== 'undefined') {
      window.location.href = '/';
    }
  };

  render() {
    if (this.state.hasError) {
      const { fallback: CustomFallback, maxRetries = 3 } = this.props;
      const { error, errorInfo, errorId, retryCount } = this.state;

      // If custom fallback provided, use it
      if (CustomFallback) {
        return (
          <CustomFallback 
            error={error}
            errorInfo={errorInfo}
            errorId={errorId}
            onRetry={this.handleRetry}
            onReload={this.handleReload}
            onReportIssue={this.handleReportIssue}
            canRetry={retryCount < maxRetries}
            retryCount={retryCount}
          />
        );
      }

      // Default error UI
      return (
        <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
          <div className="max-w-md w-full bg-white border border-red-200 rounded-lg shadow-lg">
            {/* Header */}
            <div className="bg-red-50 border-b border-red-200 px-6 py-4 rounded-t-lg">
              <div className="flex items-center">
                <div className="text-red-500 text-2xl mr-3">🚨</div>
                <div>
                  <h2 className="text-lg font-semibold text-red-800">
                    Something went wrong
                  </h2>
                  <p className="text-sm text-red-600 mt-1">
                    An unexpected error occurred
                  </p>
                </div>
              </div>
            </div>

            {/* Content */}
            <div className="p-6">
              <p className="text-gray-600 mb-4">
                We apologize for the inconvenience. Our team has been notified and is working on a fix.
              </p>

              {errorId && (
                <div className="bg-gray-100 border border-gray-200 rounded-lg p-3 mb-4">
                  <p className="text-xs font-mono text-gray-700">
                    Error ID: {errorId}
                  </p>
                </div>
              )}

              {/* Action buttons */}
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  {retryCount < maxRetries && (
                    <button
                      onClick={this.handleRetry}
                      className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition-colors"
                    >
                      Try Again ({maxRetries - retryCount} left)
                    </button>
                  )}
                  
                  <button
                    onClick={this.handleReload}
                    className="px-4 py-2 bg-gray-600 text-white text-sm font-medium rounded-lg hover:bg-gray-700 transition-colors"
                  >
                    Reload Page
                  </button>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <button
                    onClick={this.handleNavigateHome}
                    className="px-4 py-2 border border-gray-300 text-gray-700 text-sm font-medium rounded-lg hover:bg-gray-50 transition-colors"
                  >
                    Go Home
                  </button>
                  
                  <button
                    onClick={this.handleReportIssue}
                    className="px-4 py-2 border border-gray-300 text-gray-700 text-sm font-medium rounded-lg hover:bg-gray-50 transition-colors"
                  >
                    Report Issue
                  </button>
                </div>
              </div>

              {/* Retry limit reached */}
              {retryCount >= maxRetries && (
                <div className="mt-4 p-3 bg-yellow-50 border border-yellow-200 rounded-lg">
                  <p className="text-sm text-yellow-800">
                    ⚠️ Maximum retry attempts reached. Please reload the page or contact support.
                  </p>
                </div>
              )}

              {/* Error details (development only) */}
              {import.meta.env.DEV && error && (
                <details className="mt-4">
                  <summary className="text-sm font-medium text-gray-600 cursor-pointer">
                    Developer Information
                  </summary>
                  <div className="mt-2 p-3 bg-gray-100 rounded border overflow-auto">
                    <p className="text-xs font-mono text-gray-800 mb-2">
                      <strong>Error:</strong> {error.message}
                    </p>
                    {error.stack && (
                      <pre className="text-xs font-mono text-gray-600 whitespace-pre-wrap">
                        {error.stack}
                      </pre>
                    )}
                  </div>
                </details>
              )}
            </div>

            {/* Footer */}
            <div className="bg-gray-50 border-t border-gray-200 px-6 py-3 rounded-b-lg">
              <p className="text-xs text-gray-500 text-center">
                If this problem persists, please contact our support team
              </p>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

export default GlobalErrorBoundary;