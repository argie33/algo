import React from 'react';
import { Container, Alert, Button } from '@mui/material';
import { Refresh } from '@mui/icons-material';
import ApiErrorAlert from './ApiErrorAlert';

/**
 * Page-level wrapper that detects API routing issues and shows global alerts
 * Use this for quick updates to existing pages
 */
const PageWrapper = ({ 
  children, 
  title = 'Financial Data',
  showRoutingAlert = false,
  onRetry = null,
  containerProps = {}
}) => {
  return (
    <Container maxWidth="xl" sx={{ py: 3 }} {...containerProps}>
      {/* Global routing error alert */}
      {showRoutingAlert && (
        <Alert 
          severity="error" 
          sx={{ mb: 3 }}
          action={
            onRetry && (
              <Button color="inherit" size="small" onClick={onRetry} startIcon={<Refresh />}>
                Retry
              </Button>
            )
          }
        >
          <strong>API Configuration Issue:</strong> CloudFront is serving HTML instead of JSON for API endpoints. 
          This affects all data loading across the platform. Please check the CloudFront routing configuration.
        </Alert>
      )}
      
      {children}
    </Container>
  );
};

export default PageWrapper;