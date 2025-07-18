import React from 'react';
import { Box, Card, CardContent, Typography, Button, Alert, Stack } from '@mui/material';
import { Error, Refresh, Home, BugReport } from '@mui/icons-material';

class DashboardErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { 
      hasError: false, 
      error: null, 
      errorInfo: null,
      retryCount: 0 
    };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true };
  }

  componentDidCatch(error, errorInfo) {
    console.error('Dashboard Error Boundary caught an error:', error, errorInfo);
    this.setState({
      error,
      errorInfo,
      hasError: true
    });

    // Report error to monitoring service
    if (window.gtag) {
      window.gtag('event', 'exception', {
        description: error.toString(),
        fatal: false
      });
    }
  }

  handleRetry = () => {
    this.setState({ 
      hasError: false, 
      error: null, 
      errorInfo: null,
      retryCount: this.state.retryCount + 1 
    });
  };

  render() {
    if (this.state.hasError) {
      return (
        <Box sx={{ p: 4, maxWidth: 800, mx: 'auto' }}>
          <Card sx={{ border: '1px solid', borderColor: 'error.main' }}>
            <CardContent sx={{ p: 4 }}>
              <Stack spacing={3} alignItems="center" textAlign="center">
                <Error sx={{ fontSize: 60, color: 'error.main' }} />
                
                <Typography variant="h4" color="error.main" gutterBottom>
                  Dashboard Error
                </Typography>
                
                <Typography variant="body1" color="text.secondary">
                  Something went wrong while loading your dashboard. This is likely due to:
                </Typography>

                <Stack spacing={1} sx={{ width: '100%', maxWidth: 500 }}>
                  <Alert severity="warning" variant="outlined">
                    <strong>Database Connection Issues:</strong> The backend may be unable to connect to the database
                  </Alert>
                  <Alert severity="warning" variant="outlined">
                    <strong>Authentication Problems:</strong> Cognito configuration may be using fallback values
                  </Alert>
                  <Alert severity="warning" variant="outlined">
                    <strong>API Failures:</strong> One or more API endpoints may be returning errors
                  </Alert>
                </Stack>

                <Typography variant="body2" color="text.secondary" sx={{ fontFamily: 'monospace', mt: 2 }}>
                  <strong>Error:</strong> {this.state.error && this.state.error.toString()}
                </Typography>

                <Stack direction="row" spacing={2}>
                  <Button
                    variant="contained"
                    onClick={this.handleRetry}
                    startIcon={<Refresh />}
                    disabled={this.state.retryCount >= 3}
                  >
                    {this.state.retryCount >= 3 ? 'Max Retries Reached' : 'Retry Dashboard'}
                  </Button>
                  <Button
                    variant="outlined"
                    onClick={() => window.location.href = '/'}
                    startIcon={<Home />}
                  >
                    Go Home
                  </Button>
                  <Button
                    variant="outlined"
                    onClick={() => {
                      const issue = encodeURIComponent(`Dashboard Error: ${this.state.error}`);
                      window.open(`https://github.com/anthropics/claude-code/issues/new?title=Dashboard%20Error&body=${issue}`);
                    }}
                    startIcon={<BugReport />}
                  >
                    Report Bug
                  </Button>
                </Stack>

                <Typography variant="caption" color="text.secondary" sx={{ mt: 2 }}>
                  Retry count: {this.state.retryCount}/3
                </Typography>
              </Stack>
            </CardContent>
          </Card>
        </Box>
      );
    }

    return this.props.children;
  }
}

export default DashboardErrorBoundary;