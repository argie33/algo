import React, { Component } from 'react';
import {
  Box,
  Alert,
  AlertTitle,
  Button,
  Typography,
  Card,
  CardContent,
  Stack,
  Chip,
  LinearProgress,
  Divider
} from '@mui/material';
import {
  ErrorOutline,
  Refresh,
  Warning,
  CheckCircle,
  NetworkCheck,
  TrendingUp,
  AccountBalance
} from '@mui/icons-material';

class EconomicDataErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
      retryCount: 0,
      isRetrying: false,
      lastErrorTime: null,
      dataQuality: 'unknown'
    };

    this.maxRetries = 3;
    this.retryDelay = 2000;
  }

  static getDerivedStateFromError(error) {
    return {
      hasError: true,
      error,
      lastErrorTime: Date.now()
    };
  }

  componentDidCatch(error, errorInfo) {
    // Log error details for debugging
    console.error('EconomicDataErrorBoundary caught an error:', {
      error: error.message,
      stack: error.stack,
      componentStack: errorInfo.componentStack,
      timestamp: new Date().toISOString(),
      context: 'economic-data'
    });

    this.setState({
      error,
      errorInfo,
      dataQuality: this.assessDataQuality(error)
    });

    // Report to monitoring service if available
    if (window.analytics && typeof window.analytics.track === 'function') {
      window.analytics.track('Economic Data Error', {
        error: error.message,
        component: 'EconomicDataErrorBoundary',
        timestamp: Date.now()
      });
    }
  }

  assessDataQuality = (error) => {
    const errorMessage = error?.message?.toLowerCase() || '';
    
    if (errorMessage.includes('network') || errorMessage.includes('fetch')) {
      return 'network_issue';
    } else if (errorMessage.includes('fred') || errorMessage.includes('api')) {
      return 'api_issue';
    } else if (errorMessage.includes('timeout')) {
      return 'timeout';
    } else if (errorMessage.includes('parse')) {
      return 'data_format';
    }
    
    return 'unknown';
  };

  handleRetry = async () => {
    if (this.state.retryCount >= this.maxRetries) {
      return;
    }

    this.setState({ 
      isRetrying: true,
      retryCount: this.state.retryCount + 1
    });

    // Progressive backoff delay
    const delay = this.retryDelay * Math.pow(2, this.state.retryCount);
    await new Promise(resolve => setTimeout(resolve, delay));

    this.setState({
      hasError: false,
      error: null,
      errorInfo: null,
      isRetrying: false
    });
  };

  handleRefreshPage = () => {
    window.location.reload();
  };

  getErrorSeverity = () => {
    const { dataQuality } = this.state;
    
    switch (dataQuality) {
      case 'network_issue':
      case 'timeout':
        return 'warning';
      case 'api_issue':
        return 'error';
      case 'data_format':
        return 'info';
      default:
        return 'error';
    }
  };

  getErrorMessage = () => {
    const { dataQuality, error } = this.state;
    
    const messages = {
      network_issue: {
        title: 'Network Connectivity Issue',
        description: 'Unable to connect to economic data services. Please check your internet connection.',
        action: 'Retry Connection'
      },
      api_issue: {
        title: 'Economic Data Service Unavailable',
        description: 'The Federal Reserve Economic Data (FRED) API is temporarily unavailable. We\'re using cached data when possible.',
        action: 'Try Again'
      },
      timeout: {
        title: 'Data Request Timeout',
        description: 'Economic data request is taking longer than expected. This may be due to high demand.',
        action: 'Retry Request'
      },
      data_format: {
        title: 'Data Format Issue',
        description: 'Received unexpected data format from economic services. Our team has been notified.',
        action: 'Refresh Page'
      },
      unknown: {
        title: 'Unexpected Error',
        description: error?.message || 'An unexpected error occurred while loading economic data.',
        action: 'Try Again'
      }
    };

    return messages[dataQuality] || messages.unknown;
  };

  getRecoveryStrategies = () => {
    const { dataQuality } = this.state;
    
    const strategies = {
      network_issue: [
        'Check your internet connection',
        'Try refreshing the page',
        'Switch to a different network if available'
      ],
      api_issue: [
        'Wait a few minutes and try again',
        'Check Federal Reserve system status',
        'Use cached data if available'
      ],
      timeout: [
        'Wait for the request to complete',
        'Try with a shorter time period',
        'Contact support if issue persists'
      ],
      data_format: [
        'Refresh the entire page',
        'Clear browser cache',
        'Report this issue to support'
      ],
      unknown: [
        'Refresh the page',
        'Try again in a few minutes',
        'Contact support with error details'
      ]
    };

    return strategies[dataQuality] || strategies.unknown;
  };

  render() {
    if (!this.state.hasError) {
      return this.props.children;
    }

    const errorDetails = this.getErrorMessage();
    const severity = this.getErrorSeverity();
    const strategies = this.getRecoveryStrategies();
    const { retryCount, isRetrying } = this.state;
    const canRetry = retryCount < this.maxRetries;

    return (
      <Box sx={{ p: 2 }}>
        <Alert 
          severity={severity} 
          icon={<ErrorOutline />}
          sx={{ mb: 2 }}
        >
          <AlertTitle sx={{ fontWeight: 'bold' }}>
            {errorDetails.title}
          </AlertTitle>
          <Typography variant="body2" sx={{ mb: 2 }}>
            {errorDetails.description}
          </Typography>
          
          <Stack direction="row" spacing={1} alignItems="center">
            <Chip
              icon={<AccountBalance />}
              label="Economic Data"
              size="small"
              color={severity}
            />
            <Chip
              icon={<NetworkCheck />}
              label={`Attempt ${retryCount + 1}/${this.maxRetries + 1}`}
              size="small"
              variant="outlined"
            />
          </Stack>
        </Alert>

        <Card sx={{ mb: 2 }}>
          <CardContent>
            <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center' }}>
              <Warning color="warning" sx={{ mr: 1 }} />
              Recovery Options
            </Typography>
            
            <Stack spacing={2}>
              {/* Action Buttons */}
              <Stack direction="row" spacing={2}>
                {canRetry && (
                  <Button
                    variant="contained"
                    startIcon={isRetrying ? <LinearProgress /> : <Refresh />}
                    onClick={this.handleRetry}
                    disabled={isRetrying}
                    color="primary"
                  >
                    {isRetrying ? 'Retrying...' : errorDetails.action}
                  </Button>
                )}
                
                <Button
                  variant="outlined"
                  startIcon={<Refresh />}
                  onClick={this.handleRefreshPage}
                  color="secondary"
                >
                  Refresh Page
                </Button>
              </Stack>

              <Divider />

              {/* Recovery Strategies */}
              <Box>
                <Typography variant="subtitle2" gutterBottom sx={{ fontWeight: 'bold' }}>
                  Suggested Actions:
                </Typography>
                <Stack spacing={1}>
                  {strategies.map((strategy, index) => (
                    <Box key={index} sx={{ display: 'flex', alignItems: 'center' }}>
                      <CheckCircle color="action" sx={{ mr: 1, fontSize: 16 }} />
                      <Typography variant="body2">{strategy}</Typography>
                    </Box>
                  ))}
                </Stack>
              </Box>

              {/* Technical Details */}
              {this.props.showTechnicalDetails && this.state.error && (
                <Box>
                  <Divider sx={{ my: 2 }} />
                  <Typography variant="subtitle2" gutterBottom sx={{ fontWeight: 'bold' }}>
                    Technical Details:
                  </Typography>
                  <Box sx={{ 
                    bgcolor: 'grey.100', 
                    p: 2, 
                    borderRadius: 1,
                    fontFamily: 'monospace',
                    fontSize: '0.875rem',
                    overflow: 'auto',
                    maxHeight: 150
                  }}>
                    <Typography variant="body2" component="pre">
                      {this.state.error.message}
                      {this.state.error.stack && `\n\nStack trace:\n${this.state.error.stack}`}
                    </Typography>
                  </Box>
                </Box>
              )}

              {/* Contact Information */}
              <Box sx={{ 
                bgcolor: 'info.light', 
                p: 2, 
                borderRadius: 1,
                border: '1px solid',
                borderColor: 'info.main'
              }}>
                <Typography variant="body2" color="info.dark">
                  <strong>Need Help?</strong> If this error persists, please contact our support team 
                  with the error details above. We monitor economic data quality 24/7 and typically 
                  resolve data issues within minutes.
                </Typography>
              </Box>
            </Stack>
          </CardContent>
        </Card>

        {/* Fallback Content */}
        {this.props.fallbackComponent && (
          <Box>
            <Alert severity="info" sx={{ mb: 2 }}>
              <Typography variant="body2">
                <strong>Demo Mode:</strong> Showing sample economic data while we resolve the connection issue.
              </Typography>
            </Alert>
            {this.props.fallbackComponent}
          </Box>
        )}
      </Box>
    );
  }
}

export default EconomicDataErrorBoundary;