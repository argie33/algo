/**
 * ComponentErrorHandler - Higher-order component for wrapping any component with error handling
 * Provides granular error handling at the component level with recovery mechanisms
 */

import React, { Component, forwardRef } from 'react';
import ErrorManager from './ErrorManager';

const withErrorHandler = (WrappedComponent, options = {}) => {
  const {
    componentName = WrappedComponent.displayName || WrappedComponent.name || 'Component',
    fallbackComponent: CustomFallback = null,
    enableLogging = true,
    enableRecovery = true,
    maxRetries = 3,
    onError = null,
    isolateError = true, // Prevent error propagation to parent
    trackPerformance = true
  } = options;

  class ComponentErrorHandler extends Component {
    constructor(props) {
      super(props);
      this.state = {
        hasError: false,
        error: null,
        errorInfo: null,
        errorId: null,
        retryCount: 0,
        isRecovering: false,
        performanceStart: null
      };
      this.mountTime = Date.now();
    }

    static getDerivedStateFromError(error) {
      return { hasError: true };
    }

    componentDidCatch(error, errorInfo) {
      const errorId = this.generateErrorId();
      
      // Enhanced error context
      const enhancedError = ErrorManager.handleError({
        type: 'component_error',
        message: `Error in ${componentName}: ${error.message}`,
        error: error,
        category: ErrorManager.CATEGORIES.UI,
        severity: this.determineSeverity(error),
        context: {
          componentName,
          componentStack: errorInfo.componentStack,
          errorBoundary: 'ComponentErrorHandler',
          props: this.sanitizeProps(this.props),
          state: this.sanitizeState(this.state),
          retryCount: this.state.retryCount,
          mountTime: this.mountTime,
          errorTime: Date.now(),
          userAgent: navigator.userAgent,
          url: window.location.href,
          userId: this.getUserId(),
          sessionId: this.getSessionId()
        }
      });

      this.setState({
        error,
        errorInfo,
        errorId: enhancedError.id,
        performanceStart: Date.now()
      });

      // Call custom error handler if provided
      if (onError) {
        try {
          onError(error, errorInfo, enhancedError, this.props);
        } catch (handlerError) {
          console.error('Error in custom error handler:', handlerError);
        }
      }

      // Track component error patterns
      this.trackErrorPattern(error, errorInfo);
    }

    componentDidMount() {
      if (trackPerformance) {
        this.trackComponentPerformance('mount');
      }
    }

    componentDidUpdate() {
      if (trackPerformance && this.state.hasError && this.state.isRecovering) {
        this.trackComponentPerformance('recovery');
      }
    }

    determineSeverity(error) {
      // Critical errors that break core functionality
      if (error.message?.includes('ChunkLoadError') || 
          error.message?.includes('Loading chunk')) {
        return ErrorManager.SEVERITY.CRITICAL;
      }
      
      // High severity for data/API related errors
      if (error.message?.includes('API') || 
          error.message?.includes('fetch') ||
          error.message?.includes('Network')) {
        return ErrorManager.SEVERITY.HIGH;
      }
      
      // Medium for rendering errors
      if (error.name === 'TypeError' && error.message?.includes('render')) {
        return ErrorManager.SEVERITY.MEDIUM;
      }
      
      return ErrorManager.SEVERITY.MEDIUM;
    }

    trackErrorPattern(error, errorInfo) {
      const pattern = {
        component: componentName,
        errorType: error.name,
        errorMessage: error.message,
        stackDepth: errorInfo.componentStack?.split('\n').length || 0
      };

      ErrorManager.handleError({
        type: 'error_pattern',
        message: `Error pattern detected in ${componentName}`,
        category: ErrorManager.CATEGORIES.UI,
        severity: ErrorManager.SEVERITY.LOW,
        context: pattern
      });
    }

    trackComponentPerformance(phase) {
      const now = Date.now();
      const duration = now - (this.state.performanceStart || this.mountTime);
      
      if (duration > 1000) { // Slow component operation
        ErrorManager.handleError({
          type: 'slow_component_operation',
          message: `Slow ${phase} in ${componentName}: ${duration}ms`,
          category: ErrorManager.CATEGORIES.PERFORMANCE,
          severity: ErrorManager.SEVERITY.MEDIUM,
          context: {
            componentName,
            phase,
            duration,
            hasError: this.state.hasError,
            retryCount: this.state.retryCount
          }
        });
      }
    }

    handleRetry = async () => {
      if (this.state.retryCount >= maxRetries) {
        console.warn(`Max retries reached for ${componentName}`);
        return;
      }

      this.setState({ isRecovering: true, performanceStart: Date.now() });

      try {
        // Clear error state and increment retry count
        await new Promise(resolve => setTimeout(resolve, 100)); // Brief delay
        
        this.setState(prevState => ({
          hasError: false,
          error: null,
          errorInfo: null,
          errorId: null,
          retryCount: prevState.retryCount + 1,
          isRecovering: false
        }));

        // Log successful recovery
        ErrorManager.handleError({
          type: 'component_recovery_success',
          message: `${componentName} recovered successfully after retry`,
          category: ErrorManager.CATEGORIES.UI,
          severity: ErrorManager.SEVERITY.LOW,
          context: {
            componentName,
            retryCount: this.state.retryCount + 1,
            recoveryTime: Date.now() - this.state.performanceStart
          }
        });

      } catch (recoveryError) {
        console.error('Error during component recovery:', recoveryError);
        this.setState({ isRecovering: false });
      }
    };

    handleReload = () => {
      window.location.reload();
    };

    handleNavigateBack = () => {
      if (window.history.length > 1) {
        window.history.back();
      } else {
        window.location.href = '/';
      }
    };

    generateErrorId() {
      return `comp_err_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    }

    getUserId() {
      return localStorage.getItem('user_id') || 'anonymous';
    }

    getSessionId() {
      let sessionId = sessionStorage.getItem('session_id');
      if (!sessionId) {
        sessionId = `sess_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
        sessionStorage.setItem('session_id', sessionId);
      }
      return sessionId;
    }

    sanitizeProps(props) {
      const sanitized = { ...props };
      // Remove sensitive data and functions
      Object.keys(sanitized).forEach(key => {
        if (typeof sanitized[key] === 'function') {
          sanitized[key] = '[Function]';
        } else if (key.toLowerCase().includes('password') || 
                   key.toLowerCase().includes('token') ||
                   key.toLowerCase().includes('secret')) {
          sanitized[key] = '[REDACTED]';
        }
      });
      return sanitized;
    }

    sanitizeState(state) {
      const sanitized = { ...state };
      // Remove sensitive state data
      Object.keys(sanitized).forEach(key => {
        if (key.toLowerCase().includes('password') || 
            key.toLowerCase().includes('token') ||
            key.toLowerCase().includes('secret')) {
          sanitized[key] = '[REDACTED]';
        }
      });
      return sanitized;
    }

    renderErrorFallback() {
      const { error, errorInfo, errorId, retryCount, isRecovering } = this.state;
      const canRetry = retryCount < maxRetries && enableRecovery;

      // Use custom fallback if provided
      if (CustomFallback) {
        return (
          <CustomFallback
            error={error}
            errorInfo={errorInfo}
            errorId={errorId}
            componentName={componentName}
            retryCount={retryCount}
            onRetry={this.handleRetry}
            onReload={this.handleReload}
            onNavigateBack={this.handleNavigateBack}
            canRetry={canRetry}
            isRecovering={isRecovering}
          />
        );
      }

      // Default error UI
      return (
        <div className="min-h-32 bg-red-50 border border-red-200 rounded-lg p-4 m-2">
          <div className="flex items-start">
            <div className="text-red-500 text-xl mr-3">⚠️</div>
            <div className="flex-1">
              <h3 className="text-red-800 font-semibold mb-2">
                Error in {componentName}
              </h3>
              <p className="text-red-600 text-sm mb-3">
                Something went wrong with this component. 
                {canRetry ? ' You can try again or reload the page.' : ' Please reload the page.'}
              </p>
              
              {errorId && (
                <div className="bg-red-100 rounded px-2 py-1 mb-3">
                  <span className="text-xs font-mono text-red-700">ID: {errorId}</span>
                </div>
              )}

              <div className="flex gap-2">
                {canRetry && (
                  <button
                    onClick={this.handleRetry}
                    disabled={isRecovering}
                    className="px-3 py-1 bg-red-600 text-white text-sm rounded hover:bg-red-700 disabled:opacity-50 transition-colors"
                  >
                    {isRecovering ? 'Retrying...' : `Try Again (${maxRetries - retryCount} left)`}
                  </button>
                )}
                
                <button
                  onClick={this.handleReload}
                  className="px-3 py-1 border border-red-300 text-red-700 text-sm rounded hover:bg-red-100 transition-colors"
                >
                  Reload Page
                </button>

                <button
                  onClick={this.handleNavigateBack}
                  className="px-3 py-1 border border-red-300 text-red-700 text-sm rounded hover:bg-red-100 transition-colors"
                >
                  Go Back
                </button>
              </div>

              {/* Development info */}
              {import.meta.env.DEV && error && (
                <details className="mt-3">
                  <summary className="text-sm text-red-600 cursor-pointer">
                    Developer Information
                  </summary>
                  <pre className="mt-2 text-xs bg-red-100 p-2 rounded overflow-auto max-h-32">
                    {error.message}
                    {error.stack && '\n\n' + error.stack}
                  </pre>
                </details>
              )}
            </div>
          </div>
        </div>
      );
    }

    render() {
      if (this.state.hasError) {
        // Don't propagate error to parent if isolateError is true
        if (isolateError) {
          return this.renderErrorFallback();
        }
        
        // Re-throw to let parent boundary handle it
        throw this.state.error;
      }

      // Normal render
      return <WrappedComponent {...this.props} />;
    }
  }

  ComponentErrorHandler.displayName = `withErrorHandler(${componentName})`;
  
  return forwardRef((props, ref) => (
    <ComponentErrorHandler {...props} ref={ref} />
  ));
};

// Helper component for async component loading errors
export const AsyncErrorBoundary = ({ children, componentName = 'AsyncComponent', fallback = null }) => {
  return React.createElement(
    withErrorHandler(
      ({ children }) => children,
      {
        componentName,
        fallbackComponent: fallback,
        enableLogging: true,
        enableRecovery: true,
        maxRetries: 2
      }
    ),
    { children }
  );
};

export default withErrorHandler;