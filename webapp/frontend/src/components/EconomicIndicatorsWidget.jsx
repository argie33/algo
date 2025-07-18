import React, { useState } from 'react';
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
  Divider
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
  Analytics
} from '@mui/icons-material';
import { useQuery } from '@tanstack/react-query';
import economicDataService from '../services/economicDataService';

const EconomicIndicatorsWidget = ({ height = 400, autoRefresh = true }) => {
  const [anchorEl, setAnchorEl] = useState(null);

  // Fetch economic dashboard data
  const { data: economicData, isLoading, error, refetch } = useQuery({
    queryKey: ['economic-dashboard'],
    queryFn: () => economicDataService.getDashboardData(),
    staleTime: 5 * 60 * 1000, // 5 minutes
    refetchInterval: autoRefresh ? 5 * 60 * 1000 : false,
    retry: 1
  });

  const handleMenuOpen = (event) => {
    setAnchorEl(event.currentTarget);
  };

  const handleMenuClose = () => {
    setAnchorEl(null);
  };

  const handleRefresh = () => {
    refetch();
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
    if (value === null || value === undefined) return 'N/A';
    
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
    <Card sx={{ height }}>
      <CardHeader
        title={
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <AccountBalance color="primary" />
            <Typography variant="h6" fontWeight="bold">
              Economic Indicators
            </Typography>
          </Box>
        }
        action={
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <IconButton onClick={handleRefresh} disabled={isLoading}>
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
        <MenuItem onClick={handleRefresh}>
          <Refresh fontSize="small" sx={{ mr: 1 }} />
          Refresh Data
        </MenuItem>
        <MenuItem disabled>
          <Typography variant="caption">Data updates every 5 minutes</Typography>
        </MenuItem>
      </Menu>

      <CardContent sx={{ pt: 0, height: 'calc(100% - 64px)', overflow: 'hidden' }}>
        {isLoading && <LinearProgress sx={{ mb: 2 }} />}
        
        {error && (
          <Box sx={{ textAlign: 'center', py: 2 }}>
            <Typography color="error" variant="body2">
              Using sample economic data
            </Typography>
          </Box>
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

        {economicData && (
          <Box sx={{ mt: 2, pt: 1, borderTop: 1, borderColor: 'divider' }}>
            <Typography variant="caption" color="text.secondary" align="center" display="block">
              Last updated: {new Date().toLocaleTimeString()}
            </Typography>
          </Box>
        )}
      </CardContent>
    </Card>
  );
};

export default EconomicIndicatorsWidget;