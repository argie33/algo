import React, { useState, useEffect } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  IconButton,
  Tooltip,
  Chip,
  LinearProgress,
  Alert,
  Button,
  Divider,
  Grid,
  Paper
} from '@mui/material';
import {
  CheckCircle,
  Error,
  Warning,
  Schedule,
  Refresh,
  Settings,
  Speed,
  Timeline,
  TrendingUp,
  CloudDone,
  CloudOff,
  Info,
  Assessment
} from '@mui/icons-material';

const ApiKeyHealthCheck = ({ 
  apiKeys = [], 
  onRefresh,
  onSettings,
  autoRefresh = true,
  refreshInterval = 30000 // 30 seconds
}) => {
  const [isChecking, setIsChecking] = useState(false);
  const [healthData, setHealthData] = useState({});
  const [lastCheck, setLastCheck] = useState(null);

  useEffect(() => {
    if (apiKeys.length > 0) {
      performHealthCheck();
    }
  }, [apiKeys]);

  useEffect(() => {
    if (!autoRefresh || apiKeys.length === 0) return;

    const interval = setInterval(() => {
      performHealthCheck();
    }, refreshInterval);

    return () => clearInterval(interval);
  }, [autoRefresh, refreshInterval, apiKeys]);

  const performHealthCheck = async () => {
    if (isChecking) return;
    
    setIsChecking(true);
    try {
      // Simulate health check API calls for each API key
      const newHealthData = {};
      
      for (const apiKey of apiKeys) {
        // In real implementation, this would call the test connection API
        newHealthData[apiKey.id] = await simulateHealthCheck(apiKey);
      }
      
      setHealthData(newHealthData);
      setLastCheck(new Date());
    } catch (error) {
      console.error('Health check failed:', error);
    } finally {
      setIsChecking(false);
    }
  };

  const simulateHealthCheck = async (apiKey) => {
    // Simulate API call delay
    await new Promise(resolve => setTimeout(resolve, Math.random() * 1000 + 500));
    
    // Simulate different health states based on provider and sandbox status
    const states = ['excellent', 'good', 'fair', 'poor', 'error'];
    const weights = apiKey.isSandbox ? [0.7, 0.2, 0.1, 0, 0] : [0.4, 0.3, 0.2, 0.08, 0.02];
    
    const random = Math.random();
    let cumulative = 0;
    let status = 'excellent';
    
    for (let i = 0; i < states.length; i++) {
      cumulative += weights[i];
      if (random <= cumulative) {
        status = states[i];
        break;
      }
    }

    return {
      status,
      latency: Math.floor(Math.random() * 200 + 50), // 50-250ms
      uptime: Math.random() * 20 + 95, // 95-100%
      dataQuality: Math.random() * 10 + 90, // 90-100%
      lastSuccessfulCall: new Date(Date.now() - Math.random() * 300000), // Within last 5 minutes
      rateLimitUsed: Math.floor(Math.random() * 80), // 0-80% of rate limit
      errorCount24h: Math.floor(Math.random() * 5), // 0-5 errors in 24h
      features: {
        portfolioAccess: status !== 'error',
        realTimeData: status === 'excellent' || status === 'good',
        historicalData: status !== 'error',
        tradingEnabled: !apiKey.isSandbox && status !== 'error' && status !== 'poor'
      }
    };
  };

  const getStatusConfig = (status) => {
    switch (status) {
      case 'excellent':
        return {
          icon: <CheckCircle color="success" />,
          color: 'success',
          label: 'Excellent',
          description: 'Optimal performance'
        };
      case 'good':
        return {
          icon: <CheckCircle color="success" />,
          color: 'success',
          label: 'Good',
          description: 'Working well'
        };
      case 'fair':
        return {
          icon: <Warning color="warning" />,
          color: 'warning',
          label: 'Fair',
          description: 'Some issues detected'
        };
      case 'poor':
        return {
          icon: <Warning color="error" />,
          color: 'error',
          label: 'Poor',
          description: 'Performance issues'
        };
      case 'error':
        return {
          icon: <Error color="error" />,
          color: 'error',
          label: 'Error',
          description: 'Connection failed'
        };
      default:
        return {
          icon: <Schedule color="disabled" />,
          color: 'default',
          label: 'Unknown',
          description: 'Status pending'
        };
    }
  };

  const getOverallHealth = () => {
    if (Object.keys(healthData).length === 0) return 'unknown';
    
    const statuses = Object.values(healthData).map(h => h.status);
    if (statuses.every(s => s === 'excellent')) return 'excellent';
    if (statuses.some(s => s === 'error')) return 'error';
    if (statuses.some(s => s === 'poor')) return 'poor';
    if (statuses.some(s => s === 'fair')) return 'fair';
    return 'good';
  };

  if (apiKeys.length === 0) {
    return (
      <Card>
        <CardContent>
          <Box sx={{ textAlign: 'center', py: 3 }}>
            <CloudOff sx={{ fontSize: 48, color: 'text.secondary', mb: 2 }} />
            <Typography variant="h6" color="text.secondary" gutterBottom>
              No API Keys Configured
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              Add API keys to monitor connection health and performance.
            </Typography>
            <Button variant="contained" onClick={onSettings} startIcon={<Settings />}>
              Set Up API Keys
            </Button>
          </Box>
        </CardContent>
      </Card>
    );
  }

  const overallHealth = getOverallHealth();
  const overallConfig = getStatusConfig(overallHealth);

  return (
    <Card>
      <CardContent>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Assessment color="primary" />
            <Typography variant="h6">
              API Health Status
            </Typography>
            <Chip 
              size="small" 
              label={overallConfig.label}
              color={overallConfig.color}
              icon={overallConfig.icon}
            />
          </Box>
          
          <Box sx={{ display: 'flex', gap: 1 }}>
            {lastCheck && (
              <Typography variant="caption" color="text.secondary">
                Last check: {lastCheck.toLocaleTimeString()}
              </Typography>
            )}
            <Tooltip title="Refresh health check">
              <IconButton 
                size="small" 
                onClick={performHealthCheck}
                disabled={isChecking}
              >
                <Refresh sx={{ 
                  animation: isChecking ? 'spin 1s linear infinite' : 'none',
                  '@keyframes spin': {
                    '0%': { transform: 'rotate(0deg)' },
                    '100%': { transform: 'rotate(360deg)' }
                  }
                }} />
              </IconButton>
            </Tooltip>
          </Box>
        </Box>

        {isChecking && (
          <Box sx={{ mb: 2 }}>
            <LinearProgress />
            <Typography variant="caption" color="text.secondary" sx={{ mt: 1 }}>
              Checking API connections...
            </Typography>
          </Box>
        )}

        <Grid container spacing={2}>
          {apiKeys.map((apiKey) => {
            const health = healthData[apiKey.id];
            if (!health) return null;

            const statusConfig = getStatusConfig(health.status);

            return (
              <Grid item xs={12} md={6} key={apiKey.id}>
                <Paper variant="outlined" sx={{ p: 2 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
                    {statusConfig.icon}
                    <Box>
                      <Typography variant="subtitle2" fontWeight="bold">
                        {apiKey.provider.toUpperCase()} 
                        {apiKey.isSandbox && (
                          <Chip size="small" label="Paper" sx={{ ml: 1 }} />
                        )}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {apiKey.description || 'No description'}
                      </Typography>
                    </Box>
                  </Box>

                  <Grid container spacing={2} sx={{ mb: 2 }}>
                    <Grid item xs={6}>
                      <Box sx={{ textAlign: 'center' }}>
                        <Typography variant="h6" color={statusConfig.color}>
                          {health.latency}ms
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          Latency
                        </Typography>
                      </Box>
                    </Grid>
                    <Grid item xs={6}>
                      <Box sx={{ textAlign: 'center' }}>
                        <Typography variant="h6" color="success.main">
                          {health.uptime.toFixed(1)}%
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          Uptime
                        </Typography>
                      </Box>
                    </Grid>
                  </Grid>

                  <Box sx={{ mb: 1 }}>
                    <Typography variant="caption" color="text.secondary">
                      Rate Limit Usage
                    </Typography>
                    <LinearProgress 
                      variant="determinate" 
                      value={health.rateLimitUsed}
                      color={health.rateLimitUsed > 80 ? 'warning' : 'primary'}
                      sx={{ mt: 0.5 }}
                    />
                    <Typography variant="caption" color="text.secondary">
                      {health.rateLimitUsed}% used
                    </Typography>
                  </Box>

                  <List dense>
                    <ListItem sx={{ px: 0 }}>
                      <ListItemIcon sx={{ minWidth: 24 }}>
                        {health.features.portfolioAccess ? 
                          <CheckCircle color="success" fontSize="small" /> : 
                          <Error color="error" fontSize="small" />
                        }
                      </ListItemIcon>
                      <ListItemText 
                        primary="Portfolio Access" 
                        primaryTypographyProps={{ variant: 'caption' }}
                      />
                    </ListItem>
                    
                    <ListItem sx={{ px: 0 }}>
                      <ListItemIcon sx={{ minWidth: 24 }}>
                        {health.features.realTimeData ? 
                          <CheckCircle color="success" fontSize="small" /> : 
                          <Warning color="warning" fontSize="small" />
                        }
                      </ListItemIcon>
                      <ListItemText 
                        primary="Real-time Data" 
                        primaryTypographyProps={{ variant: 'caption' }}
                      />
                    </ListItem>
                  </List>

                  {health.errorCount24h > 0 && (
                    <Alert severity="warning" sx={{ mt: 1 }}>
                      <Typography variant="caption">
                        {health.errorCount24h} errors in last 24h
                      </Typography>
                    </Alert>
                  )}
                </Paper>
              </Grid>
            );
          })}
        </Grid>

        {overallHealth !== 'excellent' && overallHealth !== 'good' && (
          <Alert severity="warning" sx={{ mt: 2 }}>
            <Typography variant="body2">
              Some API connections are experiencing issues. 
              Check your broker account and API key settings.
            </Typography>
          </Alert>
        )}
      </CardContent>
    </Card>
  );
};

export default ApiKeyHealthCheck;