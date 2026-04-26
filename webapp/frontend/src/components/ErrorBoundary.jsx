import { Component } from 'react';
import { Alert, Box, Typography, Container } from '@mui/material';

class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('ErrorBoundary caught:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <Container maxWidth="md">
          <Box sx={{ py: 5 }}>
            <Alert severity="error" sx={{ mb: 2 }}>
              <Typography variant="h6">Something went wrong</Typography>
              <Typography variant="body2">{this.state.error?.message}</Typography>
            </Alert>
          </Box>
        </Container>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
