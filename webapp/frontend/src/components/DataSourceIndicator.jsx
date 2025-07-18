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
      <div  title={`${config.description}${lastUpdated ? ` • Last updated: ${new Date(lastUpdated).toLocaleTimeString()}` : ''}`}>
        <span className="inline-flex items-center justify-center px-2 py-1 text-xs font-bold leading-none text-red-100 bg-red-600 rounded-full"
          badgeContent={isStale ? '!' : 0}
          color="warning"
          invisible={!isStale}
        >
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
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
        </span>
      </div>
    );
  }

  return (
    <div 
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
      <div  sx={{ display: 'flex', alignItems: 'center', gap: 1, flex: 1 }}>
        <span className="inline-flex items-center justify-center px-2 py-1 text-xs font-bold leading-none text-red-100 bg-red-600 rounded-full"
          badgeContent={!isConnected && dataSource === 'live' ? '!' : 0}
          color="error"
          invisible={isConnected || dataSource !== 'live'}
        >
          <div  sx={{ color: config.textColor }}>
            {config.icon}
          </div>
        </span>
        
        <div>
          <div 
            variant="body2"
            fontWeight="bold"
            sx={{ color: config.textColor }}
          >
            {config.label}
          </div>
          
          {lastUpdated && (
            <div 
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
            </div>
          )}
          
          {!lastUpdated && dataSource === 'demo' && (
            <div 
              variant="caption"
              sx={{ color: config.textColor }}
            >
              Sample data for testing
            </div>
          )}
        </div>
      </div>

      {showActions && (
        <div  sx={{ display: 'flex', gap: 0.5 }}>
          {dataSource === 'demo' && onSetupClick && (
            <div  title="Set up API keys for live data">
              <button className="p-2 rounded-full hover:bg-gray-100"
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
              </button>
            </div>
          )}
          
          {(dataSource === 'cached' || dataSource === 'error') && onRefreshClick && (
            <div  title="Refresh data">
              <button className="p-2 rounded-full hover:bg-gray-100"
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
              </button>
            </div>
          )}
          
          {dataSource === 'live' && (
            <div  title={`Connection: ${isConnected ? 'Active' : 'Inactive'}`}>
              <div 
                sx={{
                  width: 8,
                  height: 8,
                  borderRadius: '50%',
                  backgroundColor: isConnected ? '#4caf50' : '#f44336',
                  alignSelf: 'center'
                }}
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default DataSourceIndicator;