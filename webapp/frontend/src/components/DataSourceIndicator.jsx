import React from 'react';
import {
  Box,
  Chip,
  Tooltip,
  Typography,
  IconButton,
  Badge
} from '@mui/material';
import {
  CloudDone,
  CloudOff,
  Warning,
  Schedule,
  Refresh,
  Settings,
  TrendingUp,
  PlayCircleFilled
} from '@mui/icons-material';

const DataSourceIndicator = ({ 
  dataSource = 'demo', 
  lastUpdated = null,
  isConnected = false,
  onSetupClick,
  onRefreshClick,
  compact = false,
  showActions = true 
}) => {
  const getDataSourceConfig = () => {
    switch (dataSource) {
      case 'live':
        return {
          label: 'Live Data',
          color: 'success',
          icon: <CloudDone />,
          description: 'Real-time data from your broker API',
          bgColor: '#e8f5e8',
          textColor: '#2e7d32'
        };
      case 'cached':
        return {
          label: 'Cached Data',
          color: 'warning',
          icon: <Schedule />,
          description: 'Recent data from cache (may be delayed)',
          bgColor: '#fff3e0',
          textColor: '#f57c00'
        };
      case 'demo':
        return {
          label: 'Demo Data',
          color: 'info',
          icon: <PlayCircleFilled />,
          description: 'Sample data for demonstration',
          bgColor: '#e3f2fd',
          textColor: '#1976d2'
        };
      case 'error':
        return {
          label: 'Data Error',
          color: 'error',
          icon: <CloudOff />,
          description: 'Unable to fetch data',
          bgColor: '#ffebee',
          textColor: '#d32f2f'
        };
      default:
        return {
          label: 'Unknown',
          color: 'default',
          icon: <Warning />,
          description: 'Data source unknown',
          bgColor: '#f5f5f5',
          textColor: '#666666'
        };
    }
  };

  const config = getDataSourceConfig();
  const isStale = lastUpdated && (Date.now() - new Date(lastUpdated).getTime()) > 5 * 60 * 1000; // 5 minutes

  if (compact) {
    return (
      <Tooltip title={`${config.description}${lastUpdated ? ` • Last updated: ${new Date(lastUpdated).toLocaleTimeString()}` : ''}`}>
        <Badge
          badgeContent={isStale ? '!' : 0}
          color="warning"
          invisible={!isStale}
        >
          <Chip
            size="small"
            label={config.label}
            color={config.color}
            icon={config.icon}
            variant="outlined"
            sx={{
              backgroundColor: config.bgColor,
              color: config.textColor,
              borderColor: config.textColor,
              '& .MuiChip-icon': {
                color: config.textColor
              }
            }}
          />
        </Badge>
      </Tooltip>
    );
  }

  return (
    <Box
      sx={{
        display: 'flex',
        alignItems: 'center',
        gap: 1,
        p: 1.5,
        borderRadius: 1,
        backgroundColor: config.bgColor,
        border: `1px solid ${config.textColor}20`
      }}
    >
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flex: 1 }}>
        <Badge
          badgeContent={!isConnected && dataSource === 'live' ? '!' : 0}
          color="error"
          invisible={isConnected || dataSource !== 'live'}
        >
          <Box sx={{ color: config.textColor }}>
            {config.icon}
          </Box>
        </Badge>
        
        <Box>
          <Typography
            variant="body2"
            fontWeight="bold"
            sx={{ color: config.textColor }}
          >
            {config.label}
          </Typography>
          
          {lastUpdated && (
            <Typography
              variant="caption"
              sx={{ 
                color: isStale ? '#f57c00' : config.textColor,
                display: 'flex',
                alignItems: 'center',
                gap: 0.5
              }}
            >
              {isStale && <Warning sx={{ fontSize: 12 }} />}
              Updated: {new Date(lastUpdated).toLocaleTimeString()}
            </Typography>
          )}
          
          {!lastUpdated && dataSource === 'demo' && (
            <Typography
              variant="caption"
              sx={{ color: config.textColor }}
            >
              Sample data for testing
            </Typography>
          )}
        </Box>
      </Box>

      {showActions && (
        <Box sx={{ display: 'flex', gap: 0.5 }}>
          {dataSource === 'demo' && onSetupClick && (
            <Tooltip title="Set up API keys for live data">
              <IconButton
                size="small"
                onClick={onSetupClick}
                sx={{ 
                  color: config.textColor,
                  '&:hover': {
                    backgroundColor: `${config.textColor}10`
                  }
                }}
              >
                <Settings fontSize="small" />
              </IconButton>
            </Tooltip>
          )}
          
          {(dataSource === 'cached' || dataSource === 'error') && onRefreshClick && (
            <Tooltip title="Refresh data">
              <IconButton
                size="small"
                onClick={onRefreshClick}
                sx={{ 
                  color: config.textColor,
                  '&:hover': {
                    backgroundColor: `${config.textColor}10`
                  }
                }}
              >
                <Refresh fontSize="small" />
              </IconButton>
            </Tooltip>
          )}
          
          {dataSource === 'live' && (
            <Tooltip title={`Connection: ${isConnected ? 'Active' : 'Inactive'}`}>
              <Box
                sx={{
                  width: 8,
                  height: 8,
                  borderRadius: '50%',
                  backgroundColor: isConnected ? '#4caf50' : '#f44336',
                  alignSelf: 'center'
                }}
              />
            </Tooltip>
          )}
        </Box>
      )}
    </Box>
  );
};

export default DataSourceIndicator;