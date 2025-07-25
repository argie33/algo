import React from 'react';
import {
  Alert,
  AlertTitle,
  Button,
  Box,
  Typography,
  Chip,
  Stack,
  Accordion,
  AccordionSummary,
  AccordionDetails
} from '@mui/material';
import {
  Warning,
  Error,
  Refresh,
  Settings,
  ExpandMore,
  CloudOff,
  Router
} from '@mui/icons-material';

const ApiErrorAlert = ({ 
  error, 
  onRetry, 
  showTechnicalDetails = false,
  context = 'data',
  hideAlert = false 
}) => {
  if (!error || hideAlert) return null;

  const isRoutingError = error?.isRoutingError || 
                        error?.message?.includes('HTML instead of JSON') ||
                        error?.message?.includes('routing');

  const getErrorSeverity = () => {
    if (isRoutingError) return 'error';
    if (error?.type === 'validation_error') return 'warning';
    return 'error';
  };

  const getErrorIcon = () => {
    if (isRoutingError) return <Router />;
    if (error?.type === 'network_error') return <CloudOff />;
    return <Error />;
  };

  const getErrorTitle = () => {
    if (isRoutingError) return 'API Configuration Issue';
    if (error?.type === 'network_error') return 'Network Connection Error';
    if (error?.type === 'validation_error') return 'Data Validation Error';
    return 'Data Loading Error';
  };

  const getErrorMessage = () => {
    if (isRoutingError) {
      return 'The API endpoints are returning HTML instead of JSON data. This indicates a CloudFront routing configuration issue.';
    }
    return error?.message || `Failed to load ${context}`;
  };

  const getResolutionSteps = () => {
    if (isRoutingError) {
      return [
        'Check CloudFront distribution behavior settings',
        'Ensure /api/* routes forward to Lambda function',
        'Verify API Gateway configuration',
        'Test endpoints directly with curl or Postman'
      ];
    }
    
    if (error?.type === 'network_error') {
      return [
        'Check your internet connection',
        'Verify API endpoint is accessible',
        'Try refreshing the page'
      ];
    }
    
    return [
      'Try refreshing the data',
      'Check if the service is temporarily down',
      'Contact support if the issue persists'
    ];
  };

  return (
    <Alert 
      severity={getErrorSeverity()} 
      icon={getErrorIcon()}
      sx={{ mb: 2 }}
      action={
        <Stack direction="row" spacing={1}>
          {error?.canRetry !== false && onRetry && (
            <Button 
              color="inherit" 
              size="small" 
              onClick={onRetry}
              startIcon={<Refresh />}
            >
              Retry
            </Button>
          )}
          {isRoutingError && (
            <Chip 
              label="Infrastructure Issue" 
              color="error" 
              size="small" 
            />
          )}
        </Stack>
      }
    >
      <AlertTitle>{getErrorTitle()}</AlertTitle>
      <Typography variant="body2" sx={{ mb: 1 }}>
        {getErrorMessage()}
      </Typography>
      
      {isRoutingError && (
        <Box sx={{ mt: 1 }}>
          <Typography variant="body2" color="text.secondary">
            <strong>Impact:</strong> All API endpoints are affected. Pages will show empty data or fallback content.
          </Typography>
        </Box>
      )}

      {showTechnicalDetails && (
        <Accordion sx={{ mt: 2, bgcolor: 'transparent' }}>
          <AccordionSummary expandIcon={<ExpandMore />}>
            <Typography variant="body2" fontWeight="bold">
              Technical Details & Resolution
            </Typography>
          </AccordionSummary>
          <AccordionDetails>
            <Stack spacing={2}>
              <Box>
                <Typography variant="body2" fontWeight="bold" gutterBottom>
                  Error Details:
                </Typography>
                <Typography variant="body2" color="text.secondary" fontFamily="monospace">
                  Type: {error?.type || 'unknown'}<br/>
                  Code: {error?.code || 'N/A'}<br/>
                  Message: {error?.message}<br/>
                  {error?.details && `Details: ${JSON.stringify(error.details)}`}
                </Typography>
              </Box>
              
              <Box>
                <Typography variant="body2" fontWeight="bold" gutterBottom>
                  Resolution Steps:
                </Typography>
                <ol style={{ margin: 0, paddingLeft: '20px' }}>
                  {getResolutionSteps().map((step, index) => (
                    <li key={index}>
                      <Typography variant="body2" color="text.secondary">
                        {step}
                      </Typography>
                    </li>
                  ))}
                </ol>
              </Box>

              {isRoutingError && (
                <Box>
                  <Typography variant="body2" fontWeight="bold" gutterBottom>
                    Quick Test:
                  </Typography>
                  <Typography variant="body2" color="text.secondary" fontFamily="monospace">
                    curl -H "Accept: application/json" https://d1zb7knau41vl9.cloudfront.net/api/health
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    Should return JSON, not HTML
                  </Typography>
                </Box>
              )}
            </Stack>
          </AccordionDetails>
        </Accordion>
      )}
    </Alert>
  );
};

export default ApiErrorAlert;