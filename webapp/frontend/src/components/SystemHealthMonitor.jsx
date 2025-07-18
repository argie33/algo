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
      <div  sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
          icon={statusInfo.icon}
          label={`System: ${statusInfo.label}`}
          color={statusInfo.color}
          size="small"
        />
        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
          icon={<Security />}
          label={`API Keys: ${apiKeyStatus.label}`}
          color={apiKeyStatus.color}
          size="small"
        />
        {loading && <div className="w-full bg-gray-200 rounded-full h-2" sx={{ width: 60, height: 4 }} />}
      </div>
    );
  }

  return (
    <div>
      {/* Main Health Status Card */}
      <div className="bg-white shadow-md rounded-lg">
        <div className="bg-white shadow-md rounded-lg"Content>
          <div  sx={{ display: 'flex', alignItems: 'center', justifyContent: 'between', mb: 2 }}>
            <div  sx={{ display: 'flex', alignItems: 'center' }}>
              <HealthAndSafety sx={{ mr: 1, color: 'primary.main' }} />
              <div  variant="h6">System Health</div>
            </div>
            <div  sx={{ display: 'flex', gap: 1 }}>
              <div  title="Refresh health status">
                <button className="p-2 rounded-full hover:bg-gray-100" onClick={loadHealthData} disabled={loading}>
                  <Refresh />
                </button>
              </div>
              {showDetails && (
                <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  variant="outlined"
                  size="small"
                  onClick={() => setShowDetailDialog(true)}
                  startIcon={<Timeline />}
                >
                  Details
                </button>
              )}
            </div>
          </div>

          {loading && <div className="w-full bg-gray-200 rounded-full h-2" sx={{ mb: 2 }} />}

          {/* Status Grid */}
          <div className="grid" container spacing={2}>
            <div className="grid" item xs={12} md={3}>
              <div  sx={{ textAlign: 'center' }}>
                <div  variant="body2" color="text.secondary">
                  Overall Status
                </div>
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                  icon={statusInfo.icon}
                  label={statusInfo.label}
                  color={statusInfo.color}
                  sx={{ mt: 1 }}
                />
              </div>
            </div>
            
            <div className="grid" item xs={12} md={3}>
              <div  sx={{ textAlign: 'center' }}>
                <div  variant="body2" color="text.secondary">
                  API Keys
                </div>
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                  icon={<Security />}
                  label={apiKeyStatus.label}
                  color={apiKeyStatus.color}
                  sx={{ mt: 1 }}
                />
              </div>
            </div>
            
            <div className="grid" item xs={12} md={3}>
              <div  sx={{ textAlign: 'center' }}>
                <div  variant="body2" color="text.secondary">
                  Success Rate
                </div>
                <div  variant="h6" color="primary.main">
                  {performanceMetrics.successRate.toFixed(1)}%
                </div>
              </div>
            </div>
            
            <div className="grid" item xs={12} md={3}>
              <div  sx={{ textAlign: 'center' }}>
                <div  variant="body2" color="text.secondary">
                  Response Time
                </div>
                <div  variant="h6" color="primary.main">
                  {performanceMetrics.responseTime}ms
                </div>
              </div>
            </div>
          </div>

          {/* Circuit Breaker Warning */}
          {healthData?.circuitBreakerOpen && (
            <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error" sx={{ mt: 2 }}>
              <div  variant="subtitle2" gutterBottom>
                Circuit Breaker Active
              </div>
              <div  variant="body2">
                API requests are being blocked due to consecutive failures. 
                The system will automatically retry when the timeout expires.
              </div>
            </div>
          )}

          {/* API Key Error */}
          {apiKeyError && (
            <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error" sx={{ mt: 2 }}>
              <div  variant="subtitle2" gutterBottom>
                API Key Issue
              </div>
              <div  variant="body2">
                {apiKeyError}
              </div>
            </div>
          )}

          {/* Last Update */}
          {lastUpdate && (
            <div  variant="caption" color="text.secondary" sx={{ mt: 2, display: 'block' }}>
              Last updated: {lastUpdate.toLocaleTimeString()}
            </div>
          )}
        </div>
      </div>

      {/* Detailed Health Dialog */}
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50" 
        open={showDetailDialog} 
        onClose={() => setShowDetailDialog(false)}
        maxWidth="md"
        fullWidth
      >
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Title>
          <div  sx={{ display: 'flex', alignItems: 'center' }}>
            <Timeline sx={{ mr: 1 }} />
            System Health Details
          </div>
        </h2>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Content>
          {healthData && (
            <div>
              {/* Endpoint Status */}
              <Accordion defaultExpanded>
                <AccordionSummary expandIcon={<ExpandMore />}>
                  <div  variant="h6">
                    <Api sx={{ mr: 1, verticalAlign: 'middle' }} />
                    API Endpoints ({healthData.endpoints.filter(e => e.healthy).length}/{healthData.endpoints.length})
                  </div>
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
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
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
                  <div  variant="h6">
                    <Speed sx={{ mr: 1, verticalAlign: 'middle' }} />
                    Performance Metrics
                  </div>
                </AccordionSummary>
                <AccordionDetails>
                  <div className="grid" container spacing={2}>
                    <div className="grid" item xs={6}>
                      <div  variant="body2" color="text.secondary">
                        Success Rate
                      </div>
                      <div className="w-full bg-gray-200 rounded-full h-2" 
                        variant="determinate" 
                        value={performanceMetrics.successRate} 
                        color="success"
                        sx={{ mt: 1 }}
                      />
                      <div  variant="body2">
                        {performanceMetrics.successRate.toFixed(1)}%
                      </div>
                    </div>
                    <div className="grid" item xs={6}>
                      <div  variant="body2" color="text.secondary">
                        Error Rate
                      </div>
                      <div className="w-full bg-gray-200 rounded-full h-2" 
                        variant="determinate" 
                        value={performanceMetrics.errorRate} 
                        color="error"
                        sx={{ mt: 1 }}
                      />
                      <div  variant="body2">
                        {performanceMetrics.errorRate.toFixed(1)}%
                      </div>
                    </div>
                  </div>
                </AccordionDetails>
              </Accordion>
            </div>
          )}
        </div>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Actions>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" onClick={() => setShowDetailDialog(false)}>
            Close
          </button>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
            variant="contained" 
            onClick={loadHealthData}
            startIcon={<Refresh />}
          >
            Refresh
          </button>
        </div>
      </div>
    </div>
  );
};

export default SystemHealthMonitor;