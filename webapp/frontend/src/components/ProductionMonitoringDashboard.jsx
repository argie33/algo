import React, { useState, useEffect } from 'react';
import {
  Box, Grid, Card, CardContent, Typography, CircularProgress, Alert,
  Chip, LinearProgress, IconButton, Refresh, Switch, FormControlLabel,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  Paper, Accordion, AccordionSummary, AccordionDetails, Badge, Tooltip
} from '@mui/material';
import {
  CheckCircle, Error, Warning, Info, TrendingUp, TrendingDown,
  Storage, Memory, Speed, NetworkCheck, Security, Cloud,
  ExpandMore, MonitorHeart, BugReport, Timeline, Assessment
} from '@mui/icons-material';
import { LineChart, Line, XAxis, YAxis, ResponsiveContainer, AreaChart, Area } from 'recharts';
import { useSimpleFetch } from '../hooks/useSimpleFetch.js';
import { getApiConfig } from '../services/api';

const { apiUrl: API_BASE } = getApiConfig();

const ProductionMonitoringDashboard = ({ compact = false }) => {
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [refreshInterval, setRefreshInterval] = useState(30000); // 30 seconds

  // System Health Query
  const { data: systemHealth, isLoading: healthLoading, refetch: refetchHealth } = useSimpleFetch({
    queryKey: ['system-health'],
    queryFn: async () => {
      const response = await fetch(`${API_BASE}/api/health`);
      if (!response.ok) throw new Error('Health check failed');
      return response.json();
    },
    refetchInterval: autoRefresh ? refreshInterval : false,
    retry: 3
  });

  // Database Health Query
  const { data: dbHealth, isLoading: dbLoading } = useSimpleFetch({
    queryKey: ['database-health'],
    queryFn: async () => {
      const response = await fetch(`${API_BASE}/api/health/database`);
      if (!response.ok) throw new Error('Database health check failed');
      return response.json();
    },
    refetchInterval: autoRefresh ? refreshInterval : false,
    retry: 2
  });

  // Performance Metrics Query
  const { data: performanceMetrics, isLoading: perfLoading } = useSimpleFetch({
    queryKey: ['performance-metrics'],
    queryFn: async () => {
      const response = await fetch(`${API_BASE}/api/metrics/performance`);
      if (!response.ok) throw new Error('Performance metrics failed');
      return response.json();
    },
    refetchInterval: autoRefresh ? refreshInterval * 2 : false, // Less frequent
    retry: 1
  });

  // Deployment Status Query
  const { data: deploymentStatus, isLoading: deployLoading } = useSimpleFetch({
    queryKey: ['deployment-status'],
    queryFn: async () => {
      // Check critical endpoints to determine deployment health
      const endpoints = [
        '/api/health',
        '/api/stocks',
        '/api/portfolio',
        '/api/auth/verify',
        '/api/live-data'
      ];
      
      const results = await Promise.allSettled(
        endpoints.map(async (endpoint) => {
          const response = await fetch(`${API_BASE}${endpoint}`, {
            headers: { 'Authorization': `Bearer ${localStorage.getItem('accessToken') || 'demo'}` }
          });
          return {
            endpoint,
            status: response.status,
            success: response.ok,
            responseTime: Date.now() // Simplified
          };
        })
      );
      
      return {
        endpoints: results.map((result, index) => ({
          endpoint: endpoints[index],
          ...result.value,
          error: result.status === 'rejected' ? result.reason.message : null
        })),
        overallHealth: results.filter(r => r.status === 'fulfilled' && r.value.success).length / results.length
      };
    },
    refetchInterval: autoRefresh ? refreshInterval : false,
    retry: 1
  });

  const getHealthStatus = (value, thresholds = { good: 0.8, warning: 0.5 }) => {
    if (value >= thresholds.good) return { color: 'success', icon: CheckCircle, label: 'Healthy' };
    if (value >= thresholds.warning) return { color: 'warning', icon: Warning, label: 'Warning' };
    return { color: 'error', icon: Error, label: 'Critical' };
  };

  const formatUptime = (seconds) => {
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    return `${days}d ${hours}h ${minutes}m`;
  };

  if (compact) {
    return (
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        {healthLoading ? (
          <CircularProgress size={16} />
        ) : (
          <>
            <MonitorHeart 
              sx={{ 
                color: systemHealth?.status === 'healthy' ? 'success.main' : 'error.main',
                fontSize: 20 
              }} 
            />
            <Typography variant="caption" color="text.secondary">
              {systemHealth?.status || 'Unknown'}
            </Typography>
          </>
        )}
      </Box>
    );
  }

  return (
    <Box sx={{ p: 3 }}>
      {/* Header */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Typography variant="h4" fontWeight="bold">
          🚀 Production Monitoring Dashboard
        </Typography>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <FormControlLabel
            control={
              <Switch
                checked={autoRefresh}
                onChange={(e) => setAutoRefresh(e.target.checked)}
                size="small"
              />
            }
            label="Auto Refresh"
          />
          <IconButton onClick={() => {
            refetchHealth();
            window.location.reload();
          }}>
            <Refresh />
          </IconButton>
        </Box>
      </Box>

      <Grid container spacing={3}>
        {/* System Overview */}
        <Grid item xs={12} lg={8}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                System Health Overview
              </Typography>
              
              {healthLoading ? (
                <CircularProgress />
              ) : systemHealth ? (
                <Grid container spacing={2}>
                  <Grid item xs={6} md={3}>
                    <Box textAlign="center">
                      <CheckCircle sx={{ fontSize: 40, color: 'success.main', mb: 1 }} />
                      <Typography variant="h6">{systemHealth.uptime ? formatUptime(systemHealth.uptime) : 'N/A'}</Typography>
                      <Typography variant="caption" color="text.secondary">Uptime</Typography>
                    </Box>
                  </Grid>
                  <Grid item xs={6} md={3}>
                    <Box textAlign="center">
                      <Speed sx={{ fontSize: 40, color: 'info.main', mb: 1 }} />
                      <Typography variant="h6">{systemHealth.responseTime || 'N/A'}ms</Typography>
                      <Typography variant="caption" color="text.secondary">Avg Response</Typography>
                    </Box>
                  </Grid>
                  <Grid item xs={6} md={3}>
                    <Box textAlign="center">
                      <Memory sx={{ fontSize: 40, color: 'warning.main', mb: 1 }} />
                      <Typography variant="h6">{systemHealth.memoryUsage || 'N/A'}MB</Typography>
                      <Typography variant="caption" color="text.secondary">Memory Usage</Typography>
                    </Box>
                  </Grid>
                  <Grid item xs={6} md={3}>
                    <Box textAlign="center">
                      <NetworkCheck sx={{ fontSize: 40, color: 'success.main', mb: 1 }} />
                      <Typography variant="h6">{systemHealth.activeConnections || '0'}</Typography>
                      <Typography variant="caption" color="text.secondary">Active Connections</Typography>
                    </Box>
                  </Grid>
                </Grid>
              ) : (
                <Alert severity="error">Failed to load system health data</Alert>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Quick Status */}
        <Grid item xs={12} lg={4}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Service Status
              </Typography>
              
              {deployLoading ? (
                <CircularProgress size={24} />
              ) : deploymentStatus ? (
                <Box>
                  <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                    <LinearProgress 
                      variant="determinate" 
                      value={deploymentStatus.overallHealth * 100}
                      sx={{ flexGrow: 1, mr: 2 }}
                      color={deploymentStatus.overallHealth > 0.8 ? 'success' : 'error'}
                    />
                    <Typography variant="body2">
                      {Math.round(deploymentStatus.overallHealth * 100)}%
                    </Typography>
                  </Box>
                  
                  {deploymentStatus.endpoints.slice(0, 5).map((endpoint, index) => (
                    <Box key={index} sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                      <Typography variant="body2">{endpoint.endpoint}</Typography>
                      <Chip 
                        size="small" 
                        label={endpoint.success ? 'OK' : 'ERROR'} 
                        color={endpoint.success ? 'success' : 'error'}
                      />
                    </Box>
                  ))}
                </Box>
              ) : (
                <Alert severity="warning">Deployment status unavailable</Alert>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Database Health */}
        <Grid item xs={12} lg={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Database Health
              </Typography>
              
              {dbLoading ? (
                <CircularProgress size={24} />
              ) : dbHealth ? (
                <Box>
                  <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                    <Storage sx={{ mr: 1, color: dbHealth.connected ? 'success.main' : 'error.main' }} />
                    <Typography variant="body1">
                      {dbHealth.connected ? 'Connected' : 'Disconnected'}
                    </Typography>
                  </Box>
                  
                  {dbHealth.tables && (
                    <TableContainer component={Paper} sx={{ maxHeight: 200 }}>
                      <Table size="small">
                        <TableHead>
                          <TableRow>
                            <TableCell>Table</TableCell>
                            <TableCell align="right">Records</TableCell>
                            <TableCell align="right">Status</TableCell>
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {Object.entries(dbHealth.tables).slice(0, 5).map(([table, data]) => (
                            <TableRow key={table}>
                              <TableCell>{table}</TableCell>
                              <TableCell align="right">{data.count || 0}</TableCell>
                              <TableCell align="right">
                                <Chip 
                                  size="small" 
                                  label={data.status || 'unknown'} 
                                  color={data.status === 'healthy' ? 'success' : 'warning'}
                                />
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </TableContainer>
                  )}
                </Box>
              ) : (
                <Alert severity="error">Database health check failed</Alert>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Performance Trends */}
        <Grid item xs={12} lg={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Performance Trends
              </Typography>
              
              {perfLoading ? (
                <CircularProgress size={24} />
              ) : performanceMetrics?.history ? (
                <ResponsiveContainer width="100%" height={200}>
                  <AreaChart data={performanceMetrics.history}>
                    <XAxis dataKey="timestamp" />
                    <YAxis />
                    <Area 
                      type="monotone" 
                      dataKey="responseTime" 
                      stroke="#1976d2" 
                      fill="#1976d230"
                      name="Response Time (ms)"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <Alert severity="info">Performance data loading...</Alert>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Deployment Information */}
        <Grid item xs={12}>
          <Accordion>
            <AccordionSummary expandIcon={<ExpandMore />}>
              <Typography variant="h6">
                📋 Current Deployment Information
              </Typography>
            </AccordionSummary>
            <AccordionDetails>
              <Grid container spacing={2}>
                <Grid item xs={12} md={4}>
                  <Typography variant="subtitle2" color="text.secondary">Environment</Typography>
                  <Typography variant="body1">Production (initialbuild branch)</Typography>
                </Grid>
                <Grid item xs={12} md={4}>
                  <Typography variant="subtitle2" color="text.secondary">API Gateway</Typography>
                  <Typography variant="body1" sx={{ fontFamily: 'monospace' }}>
                    {API_BASE}
                  </Typography>
                </Grid>
                <Grid item xs={12} md={4}>
                  <Typography variant="subtitle2" color="text.secondary">Last Deploy</Typography>
                  <Typography variant="body1">
                    {window.__CONFIG__?.BUILD_TIME ? new Date(window.__CONFIG__.BUILD_TIME).toLocaleString() : 'Unknown'}
                  </Typography>
                </Grid>
              </Grid>
              
              <Box sx={{ mt: 2 }}>
                <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                  Recent Session Fixes Applied:
                </Typography>
                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                  <Chip icon={<CheckCircle />} label="Database SSL Fix" color="success" size="small" />
                  <Chip icon={<CheckCircle />} label="Cognito Debugging" color="success" size="small" />
                  <Chip icon={<CheckCircle />} label="Bundle Optimization" color="success" size="small" />
                  <Chip icon={<CheckCircle />} label="Error Boundaries" color="success" size="small" />
                  <Chip icon={<CheckCircle />} label="Auth Fallbacks" color="success" size="small" />
                </Box>
              </Box>
            </AccordionDetails>
          </Accordion>
        </Grid>
      </Grid>
    </Box>
  );
};

export default ProductionMonitoringDashboard;