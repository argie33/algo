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
        <div className="bg-white shadow-md rounded-lg" sx={{ m: 2, border: '2px solid', borderColor: 'error.main' }}>
          <div className="bg-white shadow-md rounded-lg"Content sx={{ textAlign: 'center' }}>
            <ErrorOutline sx={{ fontSize: 48, color: 'error.main', mb: 2 }} />
            <div  variant="h6" gutterBottom>Component Error</div>
            <div  variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              This component encountered an error.
            </div>
            
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label={`Error ID: ${errorId}`} size="small" color="error" sx={{ mb: 2 }} />
            
            {canRetry && (
              <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                variant="contained"
                startIcon={<Refresh />}
                onClick={this.handleRetry}
                sx={{ mr: 1 }}
              >
                Try Again
              </button>
            )}
            
            <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
              variant="outlined"
              onClick={() => window.location.reload()}
            >
              Refresh Page
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;