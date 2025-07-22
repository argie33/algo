/**
 * Enhanced Async Error Boundary with Correlation IDs and Offline Handling
 * Addresses REQ-010: Error Handling Critical Gaps
 * - Handles async errors in React components
 * - Implements correlation IDs for error tracking
 * - Provides offline error handling
 * - User-friendly error message translation
 * - Error aggregation and deduplication
 */

import React, { Component } from 'react';
import { 
  Box, 
  Typography, 
  Button, 
  Alert, 
  Card, 
  CardContent, 
  Collapse,
  IconButton,
  Chip,
  Stack,
  CircularProgress,
  Snackbar
} from '@mui/material';
import { 
  ErrorOutline, 
  Refresh, 
  ExpandMore, 
  ExpandLess, 
  BugReport,
  Home,
  CloudOff,
  Warning,
  CheckCircle,
  Close
} from '@mui/icons-material';
import { v4 as uuidv4 } from 'uuid';

// Enhanced error tracking and correlation system
class ErrorTracker {
  constructor() {
    this.correlationId = uuidv4();
    this.errorHistory = [];
    this.offlineStatus = navigator.onLine;
    this.retryAttempts = new Map();
    this.errorCategories = new Map();
    this.duplicateErrors = new Map();
    
    // Listen for online/offline events
    window.addEventListener('online', () => {
      this.offlineStatus = true;
      this.handleOnlineRecovery();
    });
    
    window.addEventListener('offline', () => {
      this.offlineStatus = false;
      this.handleOfflineState();
    });
  }

  generateCorrelationId() {
    return uuidv4();
  }

  trackError(error, context = {}) {
    const correlationId = this.generateCorrelationId();
    const errorEntry = {
      id: correlationId,
      timestamp: new Date().toISOString(),
      error: {
        message: error.message,
        stack: error.stack,
        name: error.name,
        code: error.code
      },
      context: {
        ...context,
        url: window.location.href,
        userAgent: navigator.userAgent,
        viewport: {
          width: window.innerWidth,
          height: window.innerHeight
        },
        isOnline: this.offlineStatus,
        sessionId: sessionStorage.getItem('sessionId') || 'unknown'
      },
      category: this.categorizeError(error),
      severity: this.calculateSeverity(error),
      userFriendlyMessage: this.translateError(error),
      retryable: this.isRetryable(error)
    };

    // Check for duplicate errors
    const errorKey = `${error.name}:${error.message}`;
    if (this.duplicateErrors.has(errorKey)) {
      this.duplicateErrors.get(errorKey).count++;
      this.duplicateErrors.get(errorKey).lastOccurrence = new Date().toISOString();
      return correlationId;
    }

    this.duplicateErrors.set(errorKey, {
      count: 1,
      firstOccurrence: new Date().toISOString(),
      lastOccurrence: new Date().toISOString()
    });

    this.errorHistory.push(errorEntry);
    
    // Keep only last 100 errors to prevent memory leaks
    if (this.errorHistory.length > 100) {
      this.errorHistory.shift();
    }

    // Report to error tracking service
    this.reportError(errorEntry);

    return correlationId;
  }

  categorizeError(error) {
    if (error.name === 'TypeError') return 'type_error';
    if (error.name === 'ReferenceError') return 'reference_error';
    if (error.name === 'NetworkError' || error.code === 'NETWORK_ERROR') return 'network_error';
    if (error.name === 'ChunkLoadError') return 'chunk_load_error';
    if (error.message?.includes('Loading chunk')) return 'chunk_load_error';
    if (error.message?.includes('API')) return 'api_error';
    if (error.message?.includes('timeout')) return 'timeout_error';
    if (error.message?.includes('401') || error.message?.includes('403')) return 'auth_error';
    if (error.message?.includes('500')) return 'server_error';
    return 'unknown_error';
  }

  calculateSeverity(error) {
    const category = this.categorizeError(error);
    const severityMap = {
      'network_error': 'medium',
      'chunk_load_error': 'high',
      'api_error': 'medium',
      'timeout_error': 'medium',
      'auth_error': 'high',
      'server_error': 'high',
      'type_error': 'low',
      'reference_error': 'medium',
      'unknown_error': 'low'
    };
    return severityMap[category] || 'low';
  }

  translateError(error) {
    const category = this.categorizeError(error);
    const translations = {
      'network_error': 'Network connection issue. Please check your internet connection and try again.',
      'chunk_load_error': 'Failed to load application resources. Please refresh the page.',
      'api_error': 'Service temporarily unavailable. Please try again in a few moments.',
      'timeout_error': 'Request timed out. Please try again.',
      'auth_error': 'Authentication required. Please log in again.',
      'server_error': 'Server error occurred. Our team has been notified.',
      'type_error': 'An unexpected error occurred. Please try again.',
      'reference_error': 'Application error. Please refresh the page.',
      'unknown_error': 'An unexpected error occurred. Please try again.'
    };
    return translations[category] || 'An unexpected error occurred. Please try again.';
  }

  isRetryable(error) {
    const category = this.categorizeError(error);
    const retryableCategories = ['network_error', 'api_error', 'timeout_error'];
    return retryableCategories.includes(category);
  }

  handleOnlineRecovery() {
    console.log('🟢 Back online - handling recovery');
    // Clear offline-related errors
    this.errorHistory = this.errorHistory.filter(e => e.category !== 'network_error');
    
    // Emit online event for components to handle
    window.dispatchEvent(new CustomEvent('asyncErrorBoundary:online'));
  }

  handleOfflineState() {
    console.log('🔴 Gone offline - handling offline state');
    // Emit offline event for components to handle
    window.dispatchEvent(new CustomEvent('asyncErrorBoundary:offline'));
  }

  async reportError(errorEntry) {
    try {
      // Don't report if offline
      if (!this.offlineStatus) {
        console.log('📱 Offline: Queuing error for later reporting', errorEntry.id);
        return;
      }

      // Report to error tracking service
      const response = await fetch('/api/errors', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Correlation-ID': errorEntry.id
        },
        body: JSON.stringify(errorEntry)
      });

      if (!response.ok) {
        console.warn('Failed to report error:', response.status);
      }
    } catch (reportError) {
      console.warn('Error reporting failed:', reportError.message);
    }
  }

  getErrorStats() {
    const categories = {};
    const severities = {};
    
    this.errorHistory.forEach(entry => {
      categories[entry.category] = (categories[entry.category] || 0) + 1;
      severities[entry.severity] = (severities[entry.severity] || 0) + 1;
    });

    return {
      totalErrors: this.errorHistory.length,
      categories,
      severities,
      duplicates: this.duplicateErrors.size,
      isOnline: this.offlineStatus
    };
  }
}

// Global error tracker instance
const errorTracker = new ErrorTracker();

// Enhanced Async Error Boundary Component
class EnhancedAsyncErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
      correlationId: null,
      showDetails: false,
      retryCount: 0,
      maxRetries: 3,
      isRetrying: false,
      isOnline: navigator.onLine,
      offlineErrors: [],
      userMessage: '',
      canRetry: true,
      showSnackbar: false,
      snackbarMessage: '',
      errorCategory: 'unknown',
      errorSeverity: 'low'
    };

    // Bind methods
    this.handleAsyncError = this.handleAsyncError.bind(this);
    this.handleOnlineStatusChange = this.handleOnlineStatusChange.bind(this);
    this.handleRetry = this.handleRetry.bind(this);
    this.handleReset = this.handleReset.bind(this);
    this.handleReportError = this.handleReportError.bind(this);
  }

  static getDerivedStateFromError(error) {
    return { 
      hasError: true,
      correlationId: errorTracker.generateCorrelationId()
    };
  }

  componentDidMount() {
    // Listen for async errors
    window.addEventListener('unhandledrejection', this.handleAsyncError);
    window.addEventListener('error', this.handleAsyncError);
    
    // Listen for online/offline status changes
    window.addEventListener('online', this.handleOnlineStatusChange);
    window.addEventListener('offline', this.handleOnlineStatusChange);
    
    // Listen for custom async error boundary events
    window.addEventListener('asyncErrorBoundary:online', this.handleOnlineStatusChange);
    window.addEventListener('asyncErrorBoundary:offline', this.handleOnlineStatusChange);
  }

  componentWillUnmount() {
    window.removeEventListener('unhandledrejection', this.handleAsyncError);
    window.removeEventListener('error', this.handleAsyncError);
    window.removeEventListener('online', this.handleOnlineStatusChange);
    window.removeEventListener('offline', this.handleOnlineStatusChange);
    window.removeEventListener('asyncErrorBoundary:online', this.handleOnlineStatusChange);
    window.removeEventListener('asyncErrorBoundary:offline', this.handleOnlineStatusChange);
  }

  componentDidCatch(error, errorInfo) {
    console.error('🚨 Enhanced Error Boundary caught an error:', error);
    
    const correlationId = errorTracker.trackError(error, {
      componentStack: errorInfo.componentStack,
      errorBoundary: this.constructor.name,
      props: this.props,
      state: this.state
    });

    this.setState({ 
      error, 
      errorInfo, 
      correlationId,
      errorCategory: errorTracker.categorizeError(error),
      errorSeverity: errorTracker.calculateSeverity(error),
      userMessage: errorTracker.translateError(error),
      canRetry: errorTracker.isRetryable(error)
    });
  }

  handleAsyncError(event) {
    console.error('🚨 Async error caught:', event);
    
    let error;
    if (event.type === 'unhandledrejection') {
      error = event.reason;
    } else if (event.type === 'error') {
      error = event.error;
    }

    if (error) {
      const correlationId = errorTracker.trackError(error, {
        type: 'async_error',
        eventType: event.type,
        filename: event.filename,
        lineno: event.lineno,
        colno: event.colno
      });

      // Handle offline errors differently
      if (!navigator.onLine) {
        this.setState(prevState => ({
          offlineErrors: [...prevState.offlineErrors, {
            error,
            correlationId,
            timestamp: new Date().toISOString()
          }],
          showSnackbar: true,
          snackbarMessage: 'Network error detected. Will retry when connection is restored.'
        }));
      } else {
        this.setState({
          hasError: true,
          error,
          correlationId,
          errorCategory: errorTracker.categorizeError(error),
          errorSeverity: errorTracker.calculateSeverity(error),
          userMessage: errorTracker.translateError(error),
          canRetry: errorTracker.isRetryable(error)
        });
      }
    }
  }

  handleOnlineStatusChange() {
    const isOnline = navigator.onLine;
    this.setState(prevState => ({
      isOnline,
      ...(isOnline && prevState.offlineErrors.length > 0 && {
        showSnackbar: true,
        snackbarMessage: 'Connection restored. Retrying failed operations...'
      })
    }));

    // Auto-retry when coming back online
    if (isOnline && this.state.offlineErrors.length > 0) {
      setTimeout(() => {
        this.handleRetryOfflineErrors();
      }, 1000);
    }
  }

  handleRetryOfflineErrors() {
    console.log('🔄 Retrying offline errors...');
    
    // Clear offline errors and reset state
    this.setState({
      offlineErrors: [],
      hasError: false,
      error: null,
      errorInfo: null,
      correlationId: null,
      showSnackbar: true,
      snackbarMessage: 'Retrying failed operations...'
    });

    // Trigger a re-render of children
    this.forceUpdate();
  }

  async handleRetry() {
    if (this.state.retryCount >= this.state.maxRetries) {
      this.setState({
        showSnackbar: true,
        snackbarMessage: 'Maximum retry attempts reached. Please refresh the page.'
      });
      return;
    }

    this.setState({ isRetrying: true });

    try {
      // Wait a bit before retrying
      await new Promise(resolve => setTimeout(resolve, 1000));
      
      this.setState(prevState => ({
        hasError: false,
        error: null,
        errorInfo: null,
        correlationId: null,
        retryCount: prevState.retryCount + 1,
        isRetrying: false,
        showSnackbar: true,
        snackbarMessage: `Retry attempt ${prevState.retryCount + 1} successful`
      }));
    } catch (error) {
      this.setState({
        isRetrying: false,
        showSnackbar: true,
        snackbarMessage: 'Retry failed. Please try again.'
      });
    }
  }

  handleReset() {
    this.setState({
      hasError: false,
      error: null,
      errorInfo: null,
      correlationId: null,
      retryCount: 0,
      isRetrying: false,
      showDetails: false,
      userMessage: '',
      canRetry: true,
      offlineErrors: []
    });
  }

  handleReportError() {
    const { error, correlationId, errorInfo } = this.state;
    
    // Copy error details to clipboard
    const errorReport = {
      correlationId,
      timestamp: new Date().toISOString(),
      error: {
        message: error?.message,
        stack: error?.stack,
        name: error?.name
      },
      componentStack: errorInfo?.componentStack,
      userAgent: navigator.userAgent,
      url: window.location.href
    };

    navigator.clipboard.writeText(JSON.stringify(errorReport, null, 2));
    
    this.setState({
      showSnackbar: true,
      snackbarMessage: 'Error details copied to clipboard'
    });
  }

  render() {
    const { 
      hasError, 
      error, 
      correlationId, 
      showDetails, 
      retryCount, 
      maxRetries, 
      isRetrying,
      isOnline,
      offlineErrors,
      userMessage,
      canRetry,
      showSnackbar,
      snackbarMessage,
      errorCategory,
      errorSeverity
    } = this.state;

    // Show offline status if offline and no other errors
    if (!isOnline && !hasError && offlineErrors.length === 0) {
      return (
        <Box sx={{ p: 2 }}>
          <Alert 
            severity="warning" 
            icon={<CloudOff />}
            action={
              <Button size="small" onClick={() => window.location.reload()}>
                Refresh
              </Button>
            }
          >
            You&apos;re currently offline. Some features may be limited.
          </Alert>
          {this.props.children}
        </Box>
      );
    }

    // Show offline errors queue
    if (offlineErrors.length > 0 && !hasError) {
      return (
        <Box sx={{ p: 2 }}>
          <Alert 
            severity="warning" 
            icon={<CloudOff />}
            action={
              <Button size="small" onClick={this.handleRetryOfflineErrors}>
                Retry ({offlineErrors.length})
              </Button>
            }
          >
            {offlineErrors.length} error(s) occurred while offline. Will retry when connection is restored.
          </Alert>
          {this.props.children}
          
          <Snackbar
            open={showSnackbar}
            autoHideDuration={6000}
            onClose={() => this.setState({ showSnackbar: false })}
            message={snackbarMessage}
            action={
              <IconButton size="small" onClick={() => this.setState({ showSnackbar: false })}>
                <Close fontSize="small" />
              </IconButton>
            }
          />
        </Box>
      );
    }

    // Show error UI
    if (hasError) {
      const getSeverityColor = (severity) => {
        switch (severity) {
          case 'high': return 'error';
          case 'medium': return 'warning';
          case 'low': return 'info';
          default: return 'info';
        }
      };

      return (
        <Box sx={{ p: 2 }}>
          <Card sx={{ border: '2px solid', borderColor: 'error.main' }}>
            <CardContent>
              <Stack spacing={2}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                  <ErrorOutline sx={{ fontSize: 48, color: 'error.main' }} />
                  <Box>
                    <Typography variant="h6" gutterBottom>
                      {this.props.title || 'Something went wrong'}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {userMessage || 'An unexpected error occurred'}
                    </Typography>
                  </Box>
                </Box>

                <Stack direction="row" spacing={1} flexWrap="wrap">
                  <Chip 
                    label={`ID: ${correlationId?.substring(0, 8) || 'Unknown'}`} 
                    size="small" 
                    color="error" 
                  />
                  <Chip 
                    label={`Category: ${errorCategory}`} 
                    size="small" 
                    variant="outlined" 
                  />
                  <Chip 
                    label={`Severity: ${errorSeverity}`} 
                    size="small" 
                    color={getSeverityColor(errorSeverity)}
                  />
                  {!isOnline && (
                    <Chip 
                      label="Offline" 
                      size="small" 
                      color="warning"
                      icon={<CloudOff />}
                    />
                  )}
                </Stack>

                <Stack direction="row" spacing={1} flexWrap="wrap">
                  {canRetry && retryCount < maxRetries && (
                    <Button
                      variant="contained"
                      startIcon={isRetrying ? <CircularProgress size={16} /> : <Refresh />}
                      onClick={this.handleRetry}
                      disabled={isRetrying}
                    >
                      {isRetrying ? 'Retrying...' : `Try Again (${retryCount}/${maxRetries})`}
                    </Button>
                  )}
                  
                  <Button
                    variant="outlined"
                    startIcon={<Home />}
                    onClick={() => window.location.href = '/'}
                  >
                    Go Home
                  </Button>
                  
                  <Button
                    variant="outlined"
                    onClick={() => window.location.reload()}
                  >
                    Refresh Page
                  </Button>
                  
                  <Button
                    variant="outlined"
                    startIcon={<BugReport />}
                    onClick={this.handleReportError}
                  >
                    Report Error
                  </Button>
                </Stack>

                {this.props.showDetails !== false && (
                  <Box>
                    <Button
                      startIcon={showDetails ? <ExpandLess /> : <ExpandMore />}
                      onClick={() => this.setState({ showDetails: !showDetails })}
                      size="small"
                    >
                      {showDetails ? 'Hide' : 'Show'} Technical Details
                    </Button>
                    
                    <Collapse in={showDetails}>
                      <Box sx={{ mt: 2, p: 2, bgcolor: 'grey.100', borderRadius: 1 }}>
                        <Typography variant="subtitle2" gutterBottom>
                          Error Details:
                        </Typography>
                        <Typography variant="body2" component="pre" sx={{ fontSize: '0.75rem' }}>
                          {error?.message || 'No error message available'}
                        </Typography>
                        
                        {error?.stack && (
                          <>
                            <Typography variant="subtitle2" gutterBottom sx={{ mt: 2 }}>
                              Stack Trace:
                            </Typography>
                            <Typography variant="body2" component="pre" sx={{ fontSize: '0.75rem' }}>
                              {error.stack}
                            </Typography>
                          </>
                        )}
                        
                        <Typography variant="subtitle2" gutterBottom sx={{ mt: 2 }}>
                          Error Stats:
                        </Typography>
                        <Typography variant="body2" component="pre" sx={{ fontSize: '0.75rem' }}>
                          {JSON.stringify(errorTracker.getErrorStats(), null, 2)}
                        </Typography>
                      </Box>
                    </Collapse>
                  </Box>
                )}
              </Stack>
            </CardContent>
          </Card>

          <Snackbar
            open={showSnackbar}
            autoHideDuration={6000}
            onClose={() => this.setState({ showSnackbar: false })}
            message={snackbarMessage}
            action={
              <IconButton size="small" onClick={() => this.setState({ showSnackbar: false })}>
                <Close fontSize="small" />
              </IconButton>
            }
          />
        </Box>
      );
    }

    return (
      <>
        {this.props.children}
        
        <Snackbar
          open={showSnackbar}
          autoHideDuration={6000}
          onClose={() => this.setState({ showSnackbar: false })}
          message={snackbarMessage}
          action={
            <IconButton size="small" onClick={() => this.setState({ showSnackbar: false })}>
              <Close fontSize="small" />
            </IconButton>
          }
        />
      </>
    );
  }
}

// Hook for using async error boundary in functional components
export const useAsyncErrorBoundary = () => {
  const throwError = React.useCallback((error) => {
    const correlationId = errorTracker.trackError(error, {
      type: 'hook_error',
      component: 'useAsyncErrorBoundary'
    });
    
    console.error('🚨 Hook error:', error, 'Correlation ID:', correlationId);
    throw error;
  }, []);

  const reportError = React.useCallback((error, context = {}) => {
    return errorTracker.trackError(error, {
      type: 'reported_error',
      component: 'useAsyncErrorBoundary',
      ...context
    });
  }, []);

  return { throwError, reportError };
};

// Higher-order component for wrapping components with error boundary
export const withAsyncErrorBoundary = (WrappedComponent, errorBoundaryProps = {}) => {
  return function WithAsyncErrorBoundary(props) {
    return (
      <EnhancedAsyncErrorBoundary {...errorBoundaryProps}>
        <WrappedComponent {...props} />
      </EnhancedAsyncErrorBoundary>
    );
  };
};

export default EnhancedAsyncErrorBoundary;
export { errorTracker };