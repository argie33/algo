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
    <div  sx={{ p: 2 }}>
      {/* Main Status Alert */}
      <div className="p-4 rounded-md bg-blue-50 border border-blue-200" 
        severity={statusInfo.color} 
        sx={{ mb: 3 }}
        icon={statusInfo.icon}
        action={
          showRetry && (
            <div  sx={{ display: 'flex', gap: 1 }}>
              <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
                color="inherit" 
                size="small" 
                onClick={handleRetry}
                disabled={retrying}
                startIcon={retrying ? null : <Refresh />}
              >
                {retrying ? 'Retrying...' : 'Retry'}
              </button>
              <button className="p-2 rounded-full hover:bg-gray-100"
                color="inherit"
                size="small"
                onClick={() => setShowDetails(!showDetails)}
              >
                {showDetails ? <ExpandLess /> : <ExpandMore />}
              </button>
            </div>
          )
        }
      >
        <div  variant="h6" gutterBottom>
          {statusInfo.title}
        </div>
        <div  variant="body2">
          {message}
        </div>
      </div>

      {/* Progress indicator for retry */}
      {retrying && (
        <div  sx={{ mb: 2 }}>
          <div className="w-full bg-gray-200 rounded-full h-2" />
          <div  variant="body2" color="text.secondary" sx={{ mt: 1 }}>
            Attempting to reconnect to services...
          </div>
        </div>
      )}

      {/* Detailed Status Information */}
      <Collapse in={showDetails}>
        <div className="bg-white shadow-md rounded-lg" sx={{ mb: 3 }}>
          <div className="bg-white shadow-md rounded-lg"Content>
            <div  variant="h6" gutterBottom>
              Service Status Details
            </div>
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
            
            <div  sx={{ mt: 2, display: 'flex', gap: 1, flexWrap: 'wrap' }}>
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                label={`Status: ${apiStatus.toUpperCase()}`} 
                color={statusInfo.color} 
                size="small" 
              />
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                label={`Page: ${pageName}`} 
                variant="outlined" 
                size="small" 
              />
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                label={`Demo Mode: ${showDemoData ? 'Available' : 'Unavailable'}`} 
                color={showDemoData ? 'success' : 'default'}
                variant="outlined" 
                size="small" 
              />
            </div>
          </div>
        </div>
      </Collapse>

      {/* Demo Data Notice */}
      {showDemoData && (
        <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="info" sx={{ mb: 3 }} icon={<Storage />}>
          <div  variant="subtitle2" gutterBottom>
            Demo Mode Active
          </div>
          <div  variant="body2">
            {pageName} is displaying sample data while API services are unavailable. 
            This data is for demonstration purposes only and does not reflect real market conditions.
          </div>
        </div>
      )}

      {/* Action Buttons */}
      <div className="grid" container spacing={2} sx={{ mb: 3 }}>
        <div className="grid" item>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
            variant="outlined"
            startIcon={<Settings />}
            href="/settings"
          >
            Check Settings
          </button>
        </div>
        <div className="grid" item>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
            variant="outlined"
            startIcon={<Info />}
            onClick={() => setShowDetails(!showDetails)}
          >
            {showDetails ? 'Hide' : 'Show'} Details
          </button>
        </div>
        {onRetry && (
          <div className="grid" item>
            <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
              variant="contained"
              startIcon={<Refresh />}
              onClick={handleRetry}
              disabled={retrying}
            >
              Try Again
            </button>
          </div>
        )}
      </div>

      {/* Content with Demo Data Banner */}
      {showDemoData && children && (
        <div  sx={{ position: 'relative' }}>
          {/* Demo Data Overlay */}
          <div 
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
          </div>
          
          {/* Faded content to indicate demo mode */}
          <div  sx={{ opacity: 0.8, pointerEvents: 'none' }}>
            {children}
          </div>
        </div>
      )}

      {/* No Demo Data Available */}
      {!showDemoData && !children && (
        <div className="bg-white shadow-md rounded-lg">
          <div className="bg-white shadow-md rounded-lg"Content sx={{ textAlign: 'center', py: 6 }}>
            <CloudOff sx={{ fontSize: 64, color: 'text.secondary', mb: 2 }} />
            <div  variant="h6" color="text.secondary" gutterBottom>
              Content Unavailable
            </div>
            <div  variant="body2" color="text.secondary">
              {pageName} requires API connectivity to display content. 
              Please check your connection and try again.
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ApiUnavailableFallback;