import React from 'react';
import { Box, Card, CardContent, Typography, Button, Stack } from '@mui/material';
import { InboxIcon, RefreshCw } from 'lucide-react';

/**
 * EmptyDataPlaceholder - Shows friendly message when no data available.
 * Guides user to refresh or check API status.
 */
export function EmptyDataPlaceholder({
  title = 'No data available',
  message = 'Check back later or try refreshing the page.',
  onRefresh,
  icon: Icon = InboxIcon,
}) {
  return (
    <Card sx={{ bgcolor: 'grey.50', border: '1px solid', borderColor: 'divider' }}>
      <CardContent>
        <Stack spacing={2} alignItems="center" textAlign="center" sx={{ py: 4 }}>
          {Icon && (
            <Icon
              size={48}
              style={{ opacity: 0.3, marginBottom: 8 }}
            />
          )}
          <Typography variant="h6" color="textSecondary">
            {title}
          </Typography>
          <Typography variant="body2" color="textDisabled">
            {message}
          </Typography>
          {onRefresh && (
            <Button
              variant="outlined"
              size="small"
              startIcon={<RefreshCw size={16} />}
              onClick={onRefresh}
              sx={{ mt: 1 }}
            >
              Refresh
            </Button>
          )}
        </Stack>
      </CardContent>
    </Card>
  );
}

/**
 * DataStateHandler - Wrapper for common loading/error/empty states.
 * Usage:
 *   <DataStateHandler
 *     loading={isLoading}
 *     error={error}
 *     data={data}
 *     onRetry={refetch}
 *   >
 *     <YourContent data={data} />
 *   </DataStateHandler>
 */
export function DataStateHandler({
  loading,
  error,
  data,
  onRetry,
  loadingComponent: LoadingComponent,
  errorTitle = 'Failed to load data',
  errorMessage = 'An error occurred while loading data.',
  emptyMessage = 'No data available',
  children,
}) {
  if (loading) {
    return LoadingComponent || <Typography color="textSecondary">Loading...</Typography>;
  }

  if (error) {
    return (
      <Card sx={{ bgcolor: 'error.light', border: '1px solid', borderColor: 'error.main' }}>
        <CardContent>
          <Stack spacing={2}>
            <Typography variant="h6" color="error">
              {errorTitle}
            </Typography>
            <Typography variant="body2" color="textSecondary">
              {error || errorMessage}
            </Typography>
            {onRetry && (
              <Button
                variant="contained"
                size="small"
                onClick={onRetry}
                startIcon={<RefreshCw size={16} />}
                sx={{ width: 'fit-content' }}
              >
                Try Again
              </Button>
            )}
          </Stack>
        </CardContent>
      </Card>
    );
  }

  if (!data || (Array.isArray(data) && data.length === 0)) {
    return (
      <EmptyDataPlaceholder
        title="No data available"
        message={emptyMessage}
        onRefresh={onRetry}
      />
    );
  }

  return children;
}

export default EmptyDataPlaceholder;
