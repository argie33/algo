/**
 * SystemHealthMonitor - Real-time infrastructure health monitoring
 * Displays API status, database connectivity, and system performance metrics
 * Production-grade monitoring with alerts and automated recovery suggestions
 */

import React, { useState, useEffect } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Grid,
  Chip,
  Alert,
  Button,
  LinearProgress,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  IconButton,
  Tooltip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions
} from '@mui/material';
import {
  HealthAndSafety,
  CheckCircle,
  Warning,
  Error,
  Storage,
  Api,
  Speed,
  NetworkCheck,
  Refresh,
  ExpandMore,
  Settings,
  Timeline,
  Memory,
  Security
} from '@mui/icons-material';
import apiHealthService from '../services/apiHealthService';
import { resetCircuitBreaker, getCircuitBreakerStatus } from '../services/api';
import { useApiKeys } from './ApiKeyProvider';

const SystemHealthMonitor = ({ 
  compact = false,
  showDetails = true,
  autoRefresh = true,
  refreshInterval = 30000 // 30 seconds
}) => {
  const { hasApiKeys, apiKeys, error: apiKeyError } = useApiKeys();
  const [healthData, setHealthData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [lastUpdate, setLastUpdate] = useState(null);
  const [showDetailDialog, setShowDetailDialog] = useState(false);
  const [performanceMetrics, setPerformanceMetrics] = useState({
    responseTime: 0,
    successRate: 0,
    errorRate: 0
  });
  const [circuitBreakerStatus, setCircuitBreakerStatus] = useState(null);

  // Load health data
  const loadHealthData = async () => {
    try {
      setLoading(true);
      const startTime = Date.now();
      
      // Get comprehensive health status
      const health = await apiHealthService.forceHealthCheck();
      const responseTime = Date.now() - startTime;
      
      setHealthData(health);
      setLastUpdate(new Date());
      
      // Calculate performance metrics
      const totalEndpoints = health.endpoints.length;
      const healthyEndpoints = health.endpoints.filter(e => e.healthy).length;
      const successRate = totalEndpoints > 0 ? (healthyEndpoints / totalEndpoints) * 100 : 0;
      
      setPerformanceMetrics({
        responseTime,
        successRate,
        errorRate: 100 - successRate
      });
      
      // Update circuit breaker status
      setCircuitBreakerStatus(getCircuitBreakerStatus());
      
    } catch (error) {
      console.error('Failed to load health data:', error);
    } finally {
      setLoading(false);
    }
  };

  // Auto-refresh health data
  useEffect(() => {
    loadHealthData();
    
    if (autoRefresh) {
      const interval = setInterval(loadHealthData, refreshInterval);
      return () => clearInterval(interval);
    }
  }, [autoRefresh, refreshInterval]);

  // Subscribe to health service updates
  useEffect(() => {
    const unsubscribe = apiHealthService.subscribe((health) => {
      setHealthData(health);
      setLastUpdate(new Date());
    });
    
    return unsubscribe;
  }, []);

  // Circuit breaker reset handler
  const handleCircuitBreakerReset = () => {
    resetCircuitBreaker();
    setCircuitBreakerStatus(getCircuitBreakerStatus());
    // Reload health data after reset
    setTimeout(loadHealthData, 1000);
  };

  const getOverallStatusInfo = () => {
    if (!healthData) {
      return { color: 'default', icon: <HealthAndSafety />, label: 'Unknown' };
    }
    
    switch (healthData.overall) {
      case 'healthy':
        return { color: 'success', icon: <CheckCircle />, label: 'Healthy' };
      case 'degraded':
        return { color: 'warning', icon: <Warning />, label: 'Degraded' };
      case 'unhealthy':
        return { color: 'error', icon: <Error />, label: 'Unhealthy' };
      case 'down':
        return { color: 'error', icon: <Error />, label: 'Down' };
      default:
        return { color: 'default', icon: <HealthAndSafety />, label: 'Unknown' };
    }
  };

  const getApiKeyStatus = () => {
    if (!hasApiKeys) return { color: 'warning', label: 'No API Keys' };
    if (apiKeyError) return { color: 'error', label: 'API Key Error' };
    
    const activeProviders = Object.values(apiKeys).filter(key => key.isActive).length;
    return { 
      color: activeProviders > 0 ? 'success' : 'warning', 
      label: `${activeProviders} Active` 
    };
  };

  const statusInfo = getOverallStatusInfo();
  const apiKeyStatus = getApiKeyStatus();

  if (compact) {
    return (
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <Chip
          icon={statusInfo.icon}
          label={`System: ${statusInfo.label}`}
          color={statusInfo.color}
          size="small"
        />
        <Chip
          icon={<Security />}
          label={`API Keys: ${apiKeyStatus.label}`}
          color={apiKeyStatus.color}
          size="small"
        />
        {loading && <LinearProgress sx={{ width: 60, height: 4 }} />}
      </Box>
    );
  }

  return (
    <Box>
      {/* Main Health Status Card */}
      <Card>
        <CardContent>
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'between', mb: 2 }}>
            <Box sx={{ display: 'flex', alignItems: 'center' }}>
              <HealthAndSafety sx={{ mr: 1, color: 'primary.main' }} />
              <Typography variant="h6">System Health</Typography>
            </Box>
            <Box sx={{ display: 'flex', gap: 1 }}>
              <Tooltip title="Refresh health status">
                <IconButton onClick={loadHealthData} disabled={loading}>
                  <Refresh />
                </IconButton>
              </Tooltip>
              {showDetails && (
                <Button
                  variant="outlined"
                  size="small"
                  onClick={() => setShowDetailDialog(true)}
                  startIcon={<Timeline />}
                >
                  Details
                </Button>
              )}
            </Box>
          </Box>

          {loading && <LinearProgress sx={{ mb: 2 }} />}

          {/* Status Grid */}
          <Grid container spacing={2}>
            <Grid item xs={12} md={3}>
              <Box sx={{ textAlign: 'center' }}>
                <Typography variant="body2" color="text.secondary">
                  Overall Status
                </Typography>
                <Chip
                  icon={statusInfo.icon}
                  label={statusInfo.label}
                  color={statusInfo.color}
                  sx={{ mt: 1 }}
                />
              </Box>
            </Grid>
            
            <Grid item xs={12} md={3}>
              <Box sx={{ textAlign: 'center' }}>
                <Typography variant="body2" color="text.secondary">
                  API Keys
                </Typography>
                <Chip
                  icon={<Security />}
                  label={apiKeyStatus.label}
                  color={apiKeyStatus.color}
                  sx={{ mt: 1 }}
                />
              </Box>
            </Grid>
            
            <Grid item xs={12} md={3}>
              <Box sx={{ textAlign: 'center' }}>
                <Typography variant="body2" color="text.secondary">
                  Success Rate
                </Typography>
                <Typography variant="h6" color="primary.main">
                  {performanceMetrics.successRate.toFixed(1)}%
                </Typography>
              </Box>
            </Grid>
            
            <Grid item xs={12} md={3}>
              <Box sx={{ textAlign: 'center' }}>
                <Typography variant="body2" color="text.secondary">
                  Response Time
                </Typography>
                <Typography variant="h6" color="primary.main">
                  {performanceMetrics.responseTime}ms
                </Typography>
              </Box>
            </Grid>
          </Grid>

          {/* Circuit Breaker Status & Control */}
          {circuitBreakerStatus && (
            <Alert 
              severity={circuitBreakerStatus.isOpen ? "error" : "success"} 
              sx={{ mt: 2 }}
              action={
                circuitBreakerStatus.isOpen && (
                  <Button 
                    color="inherit" 
                    size="small" 
                    onClick={handleCircuitBreakerReset}
                    variant="outlined"
                  >
                    Reset Now
                  </Button>
                )
              }
            >
              <Typography variant="subtitle2" gutterBottom>
                Circuit Breaker {circuitBreakerStatus.isOpen ? 'OPEN' : 'Closed'}
              </Typography>
              <Typography variant="body2">
                {circuitBreakerStatus.isOpen ? (
                  <>
                    ⚠️ API requests blocked after {circuitBreakerStatus.failures} failures. 
                    {circuitBreakerStatus.lastFailureTime && (
                      <> Last failure: {new Date(circuitBreakerStatus.lastFailureTime).toLocaleTimeString()}</>
                    )}
                  </>
                ) : (
                  <>
                    ✅ API requests flowing normally. 
                    {circuitBreakerStatus.failures > 0 && (
                      <> Previous failures: {circuitBreakerStatus.failures}</>
                    )}
                  </>
                )}
              </Typography>
            </Alert>
          )}

          {/* API Key Error */}
          {apiKeyError && (
            <Alert severity="error" sx={{ mt: 2 }}>
              <Typography variant="subtitle2" gutterBottom>
                API Key Issue
              </Typography>
              <Typography variant="body2">
                {apiKeyError}
              </Typography>
            </Alert>
          )}

          {/* Last Update */}
          {lastUpdate && (
            <Typography variant="caption" color="text.secondary" sx={{ mt: 2, display: 'block' }}>
              Last updated: {lastUpdate.toLocaleTimeString()}
            </Typography>
          )}
        </CardContent>
      </Card>

      {/* Detailed Health Dialog */}
      <Dialog 
        open={showDetailDialog} 
        onClose={() => setShowDetailDialog(false)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>
          <Box sx={{ display: 'flex', alignItems: 'center' }}>
            <Timeline sx={{ mr: 1 }} />
            System Health Details
          </Box>
        </DialogTitle>
        <DialogContent>
          {healthData && (
            <Box>
              {/* Endpoint Status */}
              <Accordion defaultExpanded>
                <AccordionSummary expandIcon={<ExpandMore />}>
                  <Typography variant="h6">
                    <Api sx={{ mr: 1, verticalAlign: 'middle' }} />
                    API Endpoints ({healthData.endpoints.filter(e => e.healthy).length}/{healthData.endpoints.length})
                  </Typography>
                </AccordionSummary>
                <AccordionDetails>
                  <List dense>
                    {healthData.endpoints.map((endpoint, index) => (
                      <ListItem key={index}>
                        <ListItemIcon>
                          {endpoint.healthy ? 
                            <CheckCircle color="success" /> : 
                            <Error color="error" />
                          }
                        </ListItemIcon>
                        <ListItemText
                          primary={endpoint.name}
                          secondary={`${endpoint.path} - ${endpoint.duration}ms`}
                        />
                        <Chip
                          label={endpoint.status || (endpoint.healthy ? 'OK' : 'FAIL')}
                          color={endpoint.healthy ? 'success' : 'error'}
                          size="small"
                        />
                      </ListItem>
                    ))}
                  </List>
                </AccordionDetails>
              </Accordion>

              {/* Performance Metrics */}
              <Accordion>
                <AccordionSummary expandIcon={<ExpandMore />}>
                  <Typography variant="h6">
                    <Speed sx={{ mr: 1, verticalAlign: 'middle' }} />
                    Performance Metrics
                  </Typography>
                </AccordionSummary>
                <AccordionDetails>
                  <Grid container spacing={2}>
                    <Grid item xs={6}>
                      <Typography variant="body2" color="text.secondary">
                        Success Rate
                      </Typography>
                      <LinearProgress 
                        variant="determinate" 
                        value={performanceMetrics.successRate} 
                        color="success"
                        sx={{ mt: 1 }}
                      />
                      <Typography variant="body2">
                        {performanceMetrics.successRate.toFixed(1)}%
                      </Typography>
                    </Grid>
                    <Grid item xs={6}>
                      <Typography variant="body2" color="text.secondary">
                        Error Rate
                      </Typography>
                      <LinearProgress 
                        variant="determinate" 
                        value={performanceMetrics.errorRate} 
                        color="error"
                        sx={{ mt: 1 }}
                      />
                      <Typography variant="body2">
                        {performanceMetrics.errorRate.toFixed(1)}%
                      </Typography>
                    </Grid>
                  </Grid>
                </AccordionDetails>
              </Accordion>
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowDetailDialog(false)}>
            Close
          </Button>
          <Button 
            variant="contained" 
            onClick={loadHealthData}
            startIcon={<Refresh />}
          >
            Refresh
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default SystemHealthMonitor;