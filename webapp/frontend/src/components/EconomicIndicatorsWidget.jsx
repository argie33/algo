import React, { useState, useEffect } from 'react';
import {
  Card,
  CardContent,
  CardHeader,
  Typography,
  Box,
  Grid,
  Chip,
  IconButton,
  Menu,
  MenuItem,
  LinearProgress,
  Tooltip,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  Divider,
  Alert,
  Badge,
  Stack,
  Button
} from '@mui/material';
import {
  MoreVert,
  TrendingUp,
  TrendingDown,
  TrendingFlat,
  AccountBalance,
  ShowChart,
  Work,
  Home,
  AttachMoney,
  Refresh,
  Timeline,
  Analytics,
  CheckCircle,
  Warning,
  Error as ErrorIcon,
  NetworkCheck,
  Speed
} from '@mui/icons-material';
import { useEconomicIndicators } from '../hooks/useEconomicData';
import EconomicDataErrorBoundary from './EconomicDataErrorBoundary';
import economicDataService from '../services/economicDataService';

const EconomicIndicatorsWidget = ({ 
  height = 400, 
  autoRefresh = true,
  showHealthStatus = true,
  showQualityBadge = true,
  enableRealTimeValidation = true 
}) => {
  const [anchorEl, setAnchorEl] = useState(null);
  const [apiHealth, setApiHealth] = useState(null);
  const [lastHealthCheck, setLastHealthCheck] = useState(null);

  // Use enhanced economic data hook with real-time capabilities
  const {
    data: economicData,
    loading: isLoading,
    error,
    dataQuality,
    lastUpdated,
    isUsingFallback,
    circuitBreakerOpen,
    retry,
    refresh,
    healthStatus,
    canRetry
  } = useEconomicIndicators({
    autoRefresh,
    staleTime: 5 * 60 * 1000, // 5 minutes
    maxRetries: 3,
    enableRealTimeValidation
  });

  // Periodic API health check
  useEffect(() => {
    const checkHealth = async () => {
      try {
        const health = await economicDataService.checkApiHealth();
        setApiHealth(health);
        setLastHealthCheck(new Date());
      } catch (error) {
        console.error('Health check failed:', error);
        setApiHealth({ overall: 'error', error: error.message });
      }
    };

    // Initial health check
    checkHealth();

    // Periodic health checks every 5 minutes
    const healthInterval = setInterval(checkHealth, 5 * 60 * 1000);
    return () => clearInterval(healthInterval);
  }, []);

  const handleMenuOpen = (event) => {
    setAnchorEl(event.currentTarget);
  };

  const handleMenuClose = () => {
    setAnchorEl(null);
  };

  const handleRefresh = () => {
    refresh();
  };

  const getTrendIcon = (trend) => {
    switch (trend) {
      case 'up':
        return <TrendingUp color="success" fontSize="small" />;
      case 'down':
        return <TrendingDown color="error" fontSize="small" />;
      default:
        return <TrendingFlat color="action" fontSize="small" />;
    }
  };

  const getTrendColor = (trend) => {
    switch (trend) {
      case 'up':
        return 'success';
      case 'down':
        return 'error';
      default:
        return 'default';
    }
  };

  const getIndicatorIcon = (key) => {
    switch (key) {
      case 'gdpGrowth':
        return <ShowChart color="primary" />;
      case 'cpiYoY':
        return <AttachMoney color="warning" />;
      case 'unemployment':
        return <Work color="info" />;
      case 'fedFunds':
        return <AccountBalance color="primary" />;
      case 'treasury10Y':
        return <Timeline color="secondary" />;
      case 'vix':
        return <Analytics color="error" />;
      default:
        return <ShowChart color="action" />;
    }
  };

  const formatValue = (value, unit) => {
    if (value === null || value === undefined || value === 'N/A') return 'N/A';
    
    const numValue = Number(value);
    if (isNaN(numValue)) return 'N/A';
    
    if (unit === 'percent') {
      return `${numValue.toFixed(2)}%`;
    } else if (unit === 'billions' || unit === 'millions' || unit === 'thousands') {
      return `${numValue.toFixed(1)}${unit === 'billions' ? 'B' : unit === 'millions' ? 'M' : 'K'}`;
    } else if (unit === 'index') {
      return numValue.toFixed(1);
    } else {
      return numValue.toFixed(2);
    }
  };

  const getDataQualityIcon = (quality) => {
    switch (quality) {
      case 'excellent':
        return <CheckCircle color="success" fontSize="small" />;
      case 'good':
        return <CheckCircle color="primary" fontSize="small" />;
      case 'fair':
        return <Warning color="warning" fontSize="small" />;
      case 'poor':
      case 'fallback':
        return <Warning color="error" fontSize="small" />;
      default:
        return <NetworkCheck color="action" fontSize="small" />;
    }
  };

  const getDataQualityColor = (quality) => {
    switch (quality) {
      case 'excellent': return 'success';
      case 'good': return 'primary';
      case 'fair': return 'warning';
      case 'poor':
      case 'fallback': return 'error';
      default: return 'default';
    }
  };

  const getHealthStatusColor = (status) => {
    switch (status) {
      case 'healthy': return 'success';
      case 'degraded': return 'warning';
      case 'unhealthy':
      case 'unreachable':
      case 'error': return 'error';
      default: return 'default';
    }
  };

  const indicators = economicData ? [
    {
      key: 'gdpGrowth',
      name: 'GDP Growth',
      data: economicData.gdpGrowth
    },
    {
      key: 'cpiYoY',
      name: 'Inflation (CPI)',
      data: economicData.cpiYoY
    },
    {
      key: 'unemployment',
      name: 'Unemployment',
      data: economicData.unemployment
    },
    {
      key: 'fedFunds',
      name: 'Fed Funds Rate',
      data: economicData.fedFunds
    },
    {
      key: 'treasury10Y',
      name: '10Y Treasury',
      data: economicData.treasury10Y
    },
    {
      key: 'vix',
      name: 'VIX',
      data: economicData.vix
    }
  ] : [];

  return (
    <EconomicDataErrorBoundary
      showTechnicalDetails={false}
      fallbackComponent={
        economicData && (
          <Card sx={{ height }}>
            <CardContent>
              <Alert severity="info" sx={{ mb: 2 }}>
                Showing sample economic data while resolving connection issues.
              </Alert>
            </CardContent>
          </Card>
        )
      }
    >
      <Card sx={{ height }}>
        <CardHeader
          title={
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              <AccountBalance color="primary" />
              <Typography variant="h6" fontWeight="bold">
                Economic Indicators
              </Typography>
              
              {/* Data Quality Badge */}
              {showQualityBadge && dataQuality && (
                <Tooltip title={`Data Quality: ${dataQuality.charAt(0).toUpperCase() + dataQuality.slice(1)}`}>
                  <Chip
                    icon={getDataQualityIcon(dataQuality)}
                    label={dataQuality}
                    size="small"
                    color={getDataQualityColor(dataQuality)}
                    sx={{ textTransform: 'capitalize' }}
                  />
                </Tooltip>
              )}
              
              {/* Fallback Data Indicator */}
              {isUsingFallback && (
                <Tooltip title="Using sample data - live service temporarily unavailable">
                  <Chip
                    icon={<Warning />}
                    label="Sample Data"
                    size="small"
                    color="warning"
                    variant="outlined"
                  />
                </Tooltip>
              )}
            </Box>
          }
          action={
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              {/* Health Status Indicator */}
              {showHealthStatus && apiHealth && (
                <Tooltip title={`API Health: ${apiHealth.overall}`}>
                  <Badge
                    color={getHealthStatusColor(apiHealth.overall)}
                    variant="dot"
                    sx={{ mr: 1 }}
                  >
                    <NetworkCheck fontSize="small" />
                  </Badge>
                </Tooltip>
              )}
              
              {/* Circuit Breaker Warning */}
              {circuitBreakerOpen && (
                <Tooltip title="Circuit breaker active - too many recent failures">
                  <ErrorIcon color="error" fontSize="small" />
                </Tooltip>
              )}
              
              <IconButton 
                onClick={canRetry ? retry : refresh} 
                disabled={isLoading}
                color={canRetry ? "primary" : "secondary"}
              >
                <Refresh />
              </IconButton>
              <IconButton onClick={handleMenuOpen}>
                <MoreVert />
              </IconButton>
            </Box>
          }
          sx={{ pb: 1 }}
        />
      
        <Menu
          anchorEl={anchorEl}
          open={Boolean(anchorEl)}
          onClose={handleMenuClose}
        >
          <MenuItem onClick={() => { handleMenuClose(); canRetry ? retry() : refresh(); }}>
            <Refresh fontSize="small" sx={{ mr: 1 }} />
            {canRetry ? 'Retry Failed Request' : 'Force Refresh'}
          </MenuItem>
          
          {apiHealth && (
            <MenuItem disabled>
              <NetworkCheck fontSize="small" sx={{ mr: 1 }} />
              <Box>
                <Typography variant="caption">API Status: {apiHealth.overall}</Typography>
                {lastHealthCheck && (
                  <Typography variant="caption" display="block" color="text.secondary">
                    Checked: {lastHealthCheck.toLocaleTimeString()}
                  </Typography>
                )}
              </Box>
            </MenuItem>
          )}
          
          {dataQuality && (
            <MenuItem disabled>
              <Speed fontSize="small" sx={{ mr: 1 }} />
              <Box>
                <Typography variant="caption">Data Quality: {dataQuality}</Typography>
                {lastUpdated && (
                  <Typography variant="caption" display="block" color="text.secondary">
                    Updated: {new Date(lastUpdated).toLocaleTimeString()}
                  </Typography>
                )}
              </Box>
            </MenuItem>
          )}
          
          <Divider />
          <MenuItem disabled>
            <Typography variant="caption">Auto-refresh: {autoRefresh ? 'ON' : 'OFF'}</Typography>
          </MenuItem>
        </Menu>

        <CardContent sx={{ pt: 0, height: 'calc(100% - 64px)', overflow: 'hidden' }}>
          {isLoading && (
            <Box sx={{ mb: 2 }}>
              <LinearProgress />
              <Typography variant="caption" color="text.secondary" sx={{ mt: 1 }}>
                Loading real-time economic data...
              </Typography>
            </Box>
          )}
          
          {/* Enhanced Error Display */}
          {error && !isLoading && (
            <Alert 
              severity={error.type === 'network' ? 'warning' : 'error'}
              sx={{ mb: 2 }}
              action={
                canRetry && (
                  <Button size="small" onClick={retry}>
                    Retry
                  </Button>
                )
              }
            >
              <Typography variant="body2">
                {error.userMessage || error.message || 'Failed to load economic data'}
              </Typography>
              {error.retryCount > 0 && (
                <Typography variant="caption" display="block" sx={{ mt: 0.5 }}>
                  Retry attempt {error.retryCount}/3
                </Typography>
              )}
            </Alert>
          )}
          
          {/* Data Quality Warning */}
          {economicData && (dataQuality === 'poor' || dataQuality === 'fair') && (
            <Alert severity="warning" sx={{ mb: 2 }}>
              <Typography variant="body2">
                Data quality is {dataQuality}. Some indicators may be outdated or estimated.
              </Typography>
            </Alert>
          )}

        <Box sx={{ height: '100%', overflow: 'auto' }}>
          <List dense>
            {indicators.map((indicator, index) => {
              const data = indicator.data;
              const value = data?.value;
              const change = data?.change;
              const changePercent = data?.changePercent;
              const trend = data?.trend;
              const unit = data?.unit;

              return (
                <React.Fragment key={indicator.key}>
                  <ListItem sx={{ px: 0, py: 1 }}>
                    <ListItemIcon sx={{ minWidth: 40 }}>
                      {getIndicatorIcon(indicator.key)}
                    </ListItemIcon>
                    <ListItemText
                      primary={
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <Typography variant="body2" fontWeight="medium">
                            {indicator.name}
                          </Typography>
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                            <Typography variant="body2" fontWeight="bold">
                              {formatValue(value, unit)}
                            </Typography>
                            {getTrendIcon(trend)}
                          </Box>
                        </Box>
                      }
                      secondary={
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mt: 0.5 }}>
                          <Box sx={{ display: 'flex', gap: 1 }}>
                            <Chip
                              label={trend || 'stable'}
                              size="small"
                              color={getTrendColor(trend)}
                              sx={{ fontSize: '0.7rem', height: 20 }}
                            />
                          </Box>
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                            {change !== undefined && change !== null && (
                              <Typography 
                                variant="caption" 
                                color={change >= 0 ? 'success.main' : 'error.main'}
                                fontWeight="medium"
                              >
                                {change >= 0 ? '+' : ''}{change.toFixed(2)}
                              </Typography>
                            )}
                            {changePercent !== undefined && changePercent !== null && (
                              <Typography 
                                variant="caption" 
                                color={changePercent >= 0 ? 'success.main' : 'error.main'}
                                fontWeight="medium"
                              >
                                ({changePercent >= 0 ? '+' : ''}{changePercent.toFixed(1)}%)
                              </Typography>
                            )}
                          </Box>
                        </Box>
                      }
                    />
                  </ListItem>
                  {index < indicators.length - 1 && <Divider variant="inset" />}
                </React.Fragment>
              );
            })}
            
            {indicators.length === 0 && !isLoading && (
              <Box sx={{ textAlign: 'center', py: 4 }}>
                <Typography color="text.secondary">
                  No economic data available
                </Typography>
              </Box>
            )}
          </List>
        </Box>

          {/* Enhanced Footer with Status Information */}
          {economicData && (
            <Box sx={{ mt: 2, pt: 1, borderTop: 1, borderColor: 'divider' }}>
              <Stack 
                direction="row" 
                justifyContent="space-between" 
                alignItems="center"
                spacing={1}
              >
                <Typography variant="caption" color="text.secondary">
                  Updated: {lastUpdated ? new Date(lastUpdated).toLocaleTimeString() : 'Unknown'}
                </Typography>
                
                <Stack direction="row" spacing={1} alignItems="center">
                  {isUsingFallback && (
                    <Chip
                      label="Sample"
                      size="small"
                      color="warning"
                      variant="outlined"
                    />
                  )}
                  
                  {circuitBreakerOpen && (
                    <Chip
                      label="Limited"
                      size="small"
                      color="error"
                      variant="outlined"
                    />
                  )}
                  
                  <Chip
                    label={`${dataQuality || 'unknown'}`}
                    size="small"
                    color={getDataQualityColor(dataQuality)}
                    variant="outlined"
                    sx={{ textTransform: 'capitalize' }}
                  />
                </Stack>
              </Stack>
            </Box>
          )}
        </CardContent>
      </Card>
    </EconomicDataErrorBoundary>
  );
};

export default EconomicIndicatorsWidget;