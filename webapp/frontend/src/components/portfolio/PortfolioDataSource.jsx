import React from 'react';
import {
  Box,
  Chip,
  Tooltip,
  Typography,
  Stack
} from '@mui/material';
import {
  Storage,
  CloudSync,
  Api,
  Code,
  Error,
  Speed
} from '@mui/icons-material';

const PortfolioDataSource = ({ 
  source, 
  responseTime, 
  syncInfo, 
  warning, 
  error,
  compact = false 
}) => {
  const getSourceInfo = (source) => {
    switch (source) {
      case 'database':
        return {
          label: 'Cached',
          icon: <Storage />,
          color: 'success',
          description: 'Data served from database cache for optimal performance'
        };
      case 'alpaca':
        return {
          label: 'Live Sync',
          icon: <CloudSync />,
          color: 'info',
          description: 'Fresh data synchronized from Alpaca API'
        };
      case 'alpaca_direct':
        return {
          label: 'Direct API',
          icon: <Api />,
          color: 'warning',
          description: 'Data fetched directly from Alpaca API (sync unavailable)'
        };
      case 'sample_emergency':
        return {
          label: 'Sample Data',
          icon: <Code />,
          color: 'error',
          description: 'Emergency sample data (system error occurred)'
        };
      default:
        return {
          label: 'Unknown',
          icon: <Error />,
          color: 'default',
          description: 'Data source not identified'
        };
    }
  };

  const sourceInfo = getSourceInfo(source);
  const responseMs = typeof responseTime === 'number' ? `${responseTime}ms` : responseTime;

  if (compact) {
    return (
      <Box display="flex" alignItems="center" gap={1}>
        <Tooltip title={sourceInfo.description}>
          <Chip
            icon={sourceInfo.icon}
            label={sourceInfo.label}
            color={sourceInfo.color}
            size="small"
            variant="outlined"
          />
        </Tooltip>
        {responseTime && (
          <Tooltip title="Response time">
            <Chip
              icon={<Speed />}
              label={responseMs}
              size="small"
              variant="outlined"
              color={responseTime < 200 ? 'success' : responseTime < 1000 ? 'warning' : 'error'}
            />
          </Tooltip>
        )}
      </Box>
    );
  }

  return (
    <Box sx={{ p: 2, bgcolor: 'background.paper', borderRadius: 1, border: 1, borderColor: 'divider' }}>
      <Stack spacing={2}>
        <Box display="flex" justifyContent="between" alignItems="center">
          <Typography variant="subtitle2" color="text.secondary">
            Data Source
          </Typography>
          <Chip
            icon={sourceInfo.icon}
            label={sourceInfo.label}
            color={sourceInfo.color}
            size="small"
          />
        </Box>

        <Typography variant="body2" color="text.secondary">
          {sourceInfo.description}
        </Typography>

        {responseTime && (
          <Box display="flex" justifyContent="between" alignItems="center">
            <Typography variant="body2" color="text.secondary">
              Response Time:
            </Typography>
            <Chip
              icon={<Speed />}
              label={responseMs}
              size="small"
              color={responseTime < 200 ? 'success' : responseTime < 1000 ? 'warning' : 'error'}
            />
          </Box>
        )}

        {syncInfo && (
          <Box>
            <Typography variant="body2" color="text.secondary" gutterBottom>
              Sync Information:
            </Typography>
            <Stack spacing={1}>
              {syncInfo.syncId && (
                <Typography variant="caption">
                  Sync ID: {syncInfo.syncId}
                </Typography>
              )}
              {syncInfo.duration && (
                <Typography variant="caption">
                  Duration: {syncInfo.duration}ms
                </Typography>
              )}
              {syncInfo.recordsUpdated !== undefined && (
                <Typography variant="caption">
                  Records Updated: {syncInfo.recordsUpdated}
                </Typography>
              )}
            </Stack>
          </Box>
        )}

        {warning && (
          <Box sx={{ p: 1, bgcolor: 'warning.light', borderRadius: 1 }}>
            <Typography variant="body2" color="warning.dark">
              ⚠️ {warning}
            </Typography>
          </Box>
        )}

        {error && (
          <Box sx={{ p: 1, bgcolor: 'error.light', borderRadius: 1 }}>
            <Typography variant="body2" color="error.dark">
              ❌ {error}
            </Typography>
          </Box>
        )}
      </Stack>
    </Box>
  );
};

export default PortfolioDataSource;