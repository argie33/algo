/**
 * ApiUnavailableFallback - Graceful fallback UI when APIs are unreachable
 * Provides demo data, offline mode indicators, and helpful user guidance
 * Production-grade fallback strategy for API failures
 */

import React from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Alert,
  Button,
  Chip,
  Grid,
  LinearProgress,
  IconButton,
  Collapse,
  List,
  ListItem,
  ListItemIcon,
  ListItemText
} from '@mui/material';
import {
  CloudOff,
  Refresh,
  Warning,
  Info,
  Settings,
  WifiOff,
  Storage,
  TrendingUp,
  ExpandMore,
  ExpandLess,
  CheckCircle,
  Error
} from '@mui/icons-material';

const ApiUnavailableFallback = ({ 
  children, 
  apiStatus = 'down',
  showDemoData = true,
  showRetry = true,
  onRetry,
  pageName = 'this page',
  requiredApis = ['Backend API'],
  customMessage
}) => {
  const [showDetails, setShowDetails] = React.useState(false);
  const [retrying, setRetrying] = React.useState(false);

  const handleRetry = async () => {
    if (onRetry) {
      setRetrying(true);
      try {
        await onRetry();
      } finally {
        setRetrying(false);
      }
    } else {
      // Default retry - reload page
      window.location.reload();
    }
  };

  const getStatusInfo = () => {
    switch (apiStatus) {
      case 'down':
        return {
          color: 'error',
          icon: <CloudOff />,
          title: 'API Services Unavailable',
          description: 'Unable to connect to backend services. Please check your connection and try again.'
        };
      case 'degraded':
        return {
          color: 'warning',
          icon: <Warning />,
          title: 'Limited Functionality',
          description: 'Some API services are experiencing issues. Basic functionality is available.'
        };
      case 'slow':
        return {
          color: 'info',
          icon: <WifiOff />,
          title: 'Slow Connection',
          description: 'API responses are slower than normal. Please be patient.'
        };
      default:
        return {
          color: 'error',
          icon: <Error />,
          title: 'Service Error',
          description: 'An unexpected error occurred with the API services.'
        };
    }
  };

  const statusInfo = getStatusInfo();
  const message = customMessage || statusInfo.description;

  return (
    <Box sx={{ p: 2 }}>
      {/* Main Status Alert */}
      <Alert 
        severity={statusInfo.color} 
        sx={{ mb: 3 }}
        icon={statusInfo.icon}
        action={
          showRetry && (
            <Box sx={{ display: 'flex', gap: 1 }}>
              <Button 
                color="inherit" 
                size="small" 
                onClick={handleRetry}
                disabled={retrying}
                startIcon={retrying ? null : <Refresh />}
              >
                {retrying ? 'Retrying...' : 'Retry'}
              </Button>
              <IconButton
                color="inherit"
                size="small"
                onClick={() => setShowDetails(!showDetails)}
              >
                {showDetails ? <ExpandLess /> : <ExpandMore />}
              </IconButton>
            </Box>
          )
        }
      >
        <Typography variant="h6" gutterBottom>
          {statusInfo.title}
        </Typography>
        <Typography variant="body2">
          {message}
        </Typography>
      </Alert>

      {/* Progress indicator for retry */}
      {retrying && (
        <Box sx={{ mb: 2 }}>
          <LinearProgress />
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
            Attempting to reconnect to services...
          </Typography>
        </Box>
      )}

      {/* Detailed Status Information */}
      <Collapse in={showDetails}>
        <Card sx={{ mb: 3 }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Service Status Details
            </Typography>
            <List dense>
              {requiredApis.map((api, index) => (
                <ListItem key={index}>
                  <ListItemIcon>
                    {apiStatus === 'down' ? (
                      <Error color="error" />
                    ) : apiStatus === 'degraded' ? (
                      <Warning color="warning" />
                    ) : (
                      <CheckCircle color="success" />
                    )}
                  </ListItemIcon>
                  <ListItemText 
                    primary={api}
                    secondary={apiStatus === 'down' ? 'Unavailable' : apiStatus === 'degraded' ? 'Limited' : 'Online'}
                  />
                </ListItem>
              ))}
            </List>
            
            <Box sx={{ mt: 2, display: 'flex', gap: 1, flexWrap: 'wrap' }}>
              <Chip 
                label={`Status: ${apiStatus.toUpperCase()}`} 
                color={statusInfo.color} 
                size="small" 
              />
              <Chip 
                label={`Page: ${pageName}`} 
                variant="outlined" 
                size="small" 
              />
              <Chip 
                label={`Demo Mode: ${showDemoData ? 'Available' : 'Unavailable'}`} 
                color={showDemoData ? 'success' : 'default'}
                variant="outlined" 
                size="small" 
              />
            </Box>
          </CardContent>
        </Card>
      </Collapse>

      {/* Demo Data Notice */}
      {showDemoData && (
        <Alert severity="info" sx={{ mb: 3 }} icon={<Storage />}>
          <Typography variant="subtitle2" gutterBottom>
            Demo Mode Active
          </Typography>
          <Typography variant="body2">
            {pageName} is displaying sample data while API services are unavailable. 
            This data is for demonstration purposes only and does not reflect real market conditions.
          </Typography>
        </Alert>
      )}

      {/* Action Buttons */}
      <Grid container spacing={2} sx={{ mb: 3 }}>
        <Grid item>
          <Button
            variant="outlined"
            startIcon={<Settings />}
            href="/settings"
          >
            Check Settings
          </Button>
        </Grid>
        <Grid item>
          <Button
            variant="outlined"
            startIcon={<Info />}
            onClick={() => setShowDetails(!showDetails)}
          >
            {showDetails ? 'Hide' : 'Show'} Details
          </Button>
        </Grid>
        {onRetry && (
          <Grid item>
            <Button
              variant="contained"
              startIcon={<Refresh />}
              onClick={handleRetry}
              disabled={retrying}
            >
              Try Again
            </Button>
          </Grid>
        )}
      </Grid>

      {/* Content with Demo Data Banner */}
      {showDemoData && children && (
        <Box sx={{ position: 'relative' }}>
          {/* Demo Data Overlay */}
          <Box
            sx={{
              position: 'absolute',
              top: 0,
              right: 0,
              zIndex: 1,
              backgroundColor: 'warning.main',
              color: 'warning.contrastText',
              px: 1,
              py: 0.5,
              borderRadius: 1,
              fontSize: '0.75rem',
              fontWeight: 'bold'
            }}
          >
            <Storage fontSize="small" sx={{ mr: 0.5, verticalAlign: 'middle' }} />
            DEMO DATA
          </Box>
          
          {/* Faded content to indicate demo mode */}
          <Box sx={{ opacity: 0.8, pointerEvents: 'none' }}>
            {children}
          </Box>
        </Box>
      )}

      {/* No Demo Data Available */}
      {!showDemoData && !children && (
        <Card>
          <CardContent sx={{ textAlign: 'center', py: 6 }}>
            <CloudOff sx={{ fontSize: 64, color: 'text.secondary', mb: 2 }} />
            <Typography variant="h6" color="text.secondary" gutterBottom>
              Content Unavailable
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {pageName} requires API connectivity to display content. 
              Please check your connection and try again.
            </Typography>
          </CardContent>
        </Card>
      )}
    </Box>
  );
};

export default ApiUnavailableFallback;