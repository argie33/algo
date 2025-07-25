import React from 'react';
import {
  Box,
  CircularProgress,
  Typography,
  Skeleton,
  Alert,
  Button,
  Stack
} from '@mui/material';
import { Refresh, Warning } from '@mui/icons-material';
import ApiErrorAlert from './ApiErrorAlert';
import { createFallbackData } from '../utils/dataFormatHelper';

const DataContainer = ({
  children,
  loading = false,
  error = null,
  data = null,
  onRetry = null,
  fallbackDataType = null,
  fallbackCount = 5,
  emptyMessage = 'No data available',
  showTechnicalDetails = false,
  context = 'data',
  minHeight = 200,
  loadingComponent = null,
  enableFallback = true
}) => {
  // Loading state
  if (loading) {
    if (loadingComponent) return loadingComponent;
    
    return (
      <Box 
        display="flex" 
        flexDirection="column" 
        alignItems="center" 
        justifyContent="center" 
        minHeight={minHeight}
        p={3}
      >
        <CircularProgress size={40} />
        <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
          Loading {context}...
        </Typography>
      </Box>
    );
  }

  // Error state with routing detection
  if (error) {
    const isRoutingError = error?.isRoutingError || 
                          error?.message?.includes('HTML instead of JSON') ||
                          error?.message?.includes('routing');
    
    return (
      <Box minHeight={minHeight}>
        <ApiErrorAlert 
          error={error}
          onRetry={onRetry}
          showTechnicalDetails={showTechnicalDetails}
          context={context}
        />
        
        {/* Show fallback data for routing errors to maintain UX */}
        {isRoutingError && enableFallback && fallbackDataType && (
          <Box sx={{ mt: 2 }}>
            <Alert severity="info" sx={{ mb: 2 }}>
              <Typography variant="body2">
                Showing sample data while the API issue is resolved.
                <Button 
                  size="small" 
                  sx={{ ml: 1 }}
                  onClick={() => window.location.reload()}
                >
                  Refresh Page
                </Button>
              </Typography>
            </Alert>
            {React.cloneElement(children, {
              data: createFallbackData(fallbackDataType, fallbackCount),
              isFallbackData: true
            })}
          </Box>
        )}
      </Box>
    );
  }

  // Empty data state
  if (!data || (Array.isArray(data) && data.length === 0)) {
    return (
      <Box 
        display="flex" 
        flexDirection="column" 
        alignItems="center" 
        justifyContent="center" 
        minHeight={minHeight}
        p={3}
      >
        <Warning color="disabled" sx={{ fontSize: 48, mb: 2 }} />
        <Typography variant="h6" color="text.secondary" gutterBottom>
          {emptyMessage}
        </Typography>
        {onRetry && (
          <Button 
            variant="outlined" 
            startIcon={<Refresh />} 
            onClick={onRetry}
            sx={{ mt: 1 }}
          >
            Try Again
          </Button>
        )}
      </Box>
    );
  }

  // Success state - render children with data
  return React.cloneElement(children, { data });
};

// Loading skeleton variants
export const SkeletonCard = ({ height = 200, count = 1 }) => (
  <Stack spacing={2}>
    {Array.from({ length: count }, (_, i) => (
      <Skeleton key={i} variant="rectangular" height={height} />
    ))}
  </Stack>
);

export const SkeletonTable = ({ rows = 5, columns = 4 }) => (
  <Box>
    {Array.from({ length: rows }, (_, i) => (
      <Box key={i} display="flex" gap={2} mb={1}>
        {Array.from({ length: columns }, (_, j) => (
          <Skeleton key={j} variant="text" sx={{ flex: 1 }} />
        ))}
      </Box>
    ))}
  </Box>
);

export const SkeletonList = ({ items = 5 }) => (
  <Stack spacing={1}>
    {Array.from({ length: items }, (_, i) => (
      <Box key={i} display="flex" alignItems="center" gap={2}>
        <Skeleton variant="circular" width={40} height={40} />
        <Box sx={{ flex: 1 }}>
          <Skeleton variant="text" width="60%" />
          <Skeleton variant="text" width="40%" />
        </Box>
      </Box>
    ))}
  </Stack>
);

export default DataContainer;