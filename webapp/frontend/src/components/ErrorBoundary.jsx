/**
 * Enhanced Error Boundary - Production-grade error handling for React components
 * Provides graceful fallbacks, error reporting, and recovery mechanisms
 */

import React from 'react';
import { 
  Box, 
  Typography, 
  Button, 
  Alert, 
  Card, 
  CardContent, 
  Collapse,
  IconButton,
  Chip
} from '@mui/material';
import { 
  ErrorOutline, 
  Refresh, 
  ExpandMore, 
  ExpandLess, 
  BugReport,
  Home
} from '@mui/icons-material';
import { debugReactError } from '../utils/reactDebugger.js';
// import { diagnoseReactError } from '../utils/testRunner.js'; // Temporarily disabled
const diagnoseReactError = () => Promise.resolve({ skipped: true, reason: 'Disabled during test runs' });

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
      errorId: null,
      showDetails: false,
      retryCount: 0,
      maxRetries: 3
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
    
    // Enhanced error debugging
    debugReactError(error, errorInfo.componentStack);
    
    // Run diagnostic tests for this specific error
    diagnoseReactError(error).then(diagnosticResults => {
      console.log('🔍 Diagnostic results for error:', diagnosticResults);
      this.setState({ diagnosticResults });
    }).catch(diagError => {
      console.warn('Failed to run diagnostic tests:', diagError);
    });
  }

  reportError = (error, errorInfo) => {
    const errorReport = {
      id: this.state.errorId,
      message: error.message,
      stack: error.stack,
      componentStack: errorInfo.componentStack,
      timestamp: new Date().toISOString(),
      url: window.location.href,
      retryCount: this.state.retryCount
    };

    console.log('📊 Error report:', errorReport);
  };

  handleRetry = () => {
    if (this.state.retryCount < this.state.maxRetries) {
      this.setState(prevState => ({
        hasError: false,
        error: null,
        errorInfo: null,
        retryCount: prevState.retryCount + 1
      }));
    }
  };

  render() {
    if (this.state.hasError) {
      const { retryCount, maxRetries, errorId } = this.state;
      const canRetry = retryCount < maxRetries;
      
      return (
        <Card sx={{ m: 2, border: '2px solid', borderColor: 'error.main' }}>
          <CardContent sx={{ textAlign: 'center' }}>
            <ErrorOutline sx={{ fontSize: 48, color: 'error.main', mb: 2 }} />
            <Typography variant="h6" gutterBottom>Component Error</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              This component encountered an error.
            </Typography>
            
            <Chip label={`Error ID: ${errorId}`} size="small" color="error" sx={{ mb: 2 }} />
            
            {canRetry && (
              <Button
                variant="contained"
                startIcon={<Refresh />}
                onClick={this.handleRetry}
                sx={{ mr: 1 }}
              >
                Try Again
              </Button>
            )}
            
            <Button
              variant="outlined"
              onClick={() => window.location.reload()}
            >
              Refresh Page
            </Button>
          </CardContent>
        </Card>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;