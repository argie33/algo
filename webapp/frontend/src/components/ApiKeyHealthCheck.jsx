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
      <div className="bg-white shadow-md rounded-lg">
        <div className="bg-white shadow-md rounded-lg"Content>
          <div  sx={{ textAlign: 'center', py: 3 }}>
            <CloudOff sx={{ fontSize: 48, color: 'text.secondary', mb: 2 }} />
            <div  variant="h6" color="text.secondary" gutterBottom>
              No API Keys Configured
            </div>
            <div  variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              Add API keys to monitor connection health and performance.
            </div>
            <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" variant="contained" onClick={onSettings} startIcon={<Settings />}>
              Set Up API Keys
            </button>
          </div>
        </div>
      </div>
    );
  }

  const overallHealth = getOverallHealth();
  const overallConfig = getStatusConfig(overallHealth);

  return (
    <div className="bg-white shadow-md rounded-lg">
      <div className="bg-white shadow-md rounded-lg"Content>
        <div  sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
          <div  sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Assessment color="primary" />
            <div  variant="h6">
              API Health Status
            </div>
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
              size="small" 
              label={overallConfig.label}
              color={overallConfig.color}
              icon={overallConfig.icon}
            />
          </div>
          
          <div  sx={{ display: 'flex', gap: 1 }}>
            {lastCheck && (
              <div  variant="caption" color="text.secondary">
                Last check: {lastCheck.toLocaleTimeString()}
              </div>
            )}
            <div  title="Refresh health check">
              <button className="p-2 rounded-full hover:bg-gray-100" 
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
              </button>
            </div>
          </div>
        </div>

        {isChecking && (
          <div  sx={{ mb: 2 }}>
            <div className="w-full bg-gray-200 rounded-full h-2" />
            <div  variant="caption" color="text.secondary" sx={{ mt: 1 }}>
              Checking API connections...
            </div>
          </div>
        )}

        <div className="grid" container spacing={2}>
          {apiKeys.map((apiKey) => {
            const health = healthData[apiKey.id];
            if (!health) return null;

            const statusConfig = getStatusConfig(health.status);

            return (
              <div className="grid" item xs={12} md={6} key={apiKey.id}>
                <div className="bg-white shadow-md rounded-lg p-4" variant="outlined" sx={{ p: 2 }}>
                  <div  sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
                    {statusConfig.icon}
                    <div>
                      <div  variant="subtitle2" fontWeight="bold">
                        {apiKey.provider.toUpperCase()} 
                        {apiKey.isSandbox && (
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" size="small" label="Paper" sx={{ ml: 1 }} />
                        )}
                      </div>
                      <div  variant="caption" color="text.secondary">
                        {apiKey.description || 'No description'}
                      </div>
                    </div>
                  </div>

                  <div className="grid" container spacing={2} sx={{ mb: 2 }}>
                    <div className="grid" item xs={6}>
                      <div  sx={{ textAlign: 'center' }}>
                        <div  variant="h6" color={statusConfig.color}>
                          {health.latency}ms
                        </div>
                        <div  variant="caption" color="text.secondary">
                          Latency
                        </div>
                      </div>
                    </div>
                    <div className="grid" item xs={6}>
                      <div  sx={{ textAlign: 'center' }}>
                        <div  variant="h6" color="success.main">
                          {health.uptime.toFixed(1)}%
                        </div>
                        <div  variant="caption" color="text.secondary">
                          Uptime
                        </div>
                      </div>
                    </div>
                  </div>

                  <div  sx={{ mb: 1 }}>
                    <div  variant="caption" color="text.secondary">
                      Rate Limit Usage
                    </div>
                    <div className="w-full bg-gray-200 rounded-full h-2" 
                      variant="determinate" 
                      value={health.rateLimitUsed}
                      color={health.rateLimitUsed > 80 ? 'warning' : 'primary'}
                      sx={{ mt: 0.5 }}
                    />
                    <div  variant="caption" color="text.secondary">
                      {health.rateLimitUsed}% used
                    </div>
                  </div>

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
                    <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="warning" sx={{ mt: 1 }}>
                      <div  variant="caption">
                        {health.errorCount24h} errors in last 24h
                      </div>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {overallHealth !== 'excellent' && overallHealth !== 'good' && (
          <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="warning" sx={{ mt: 2 }}>
            <div  variant="body2">
              Some API connections are experiencing issues. 
              Check your broker account and API key settings.
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default ApiKeyHealthCheck;