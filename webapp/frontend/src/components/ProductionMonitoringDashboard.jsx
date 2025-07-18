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
import { useQuery } from '@tanstack/react-query';
import { getApiConfig } from '../services/api';

const { apiUrl: API_BASE } = getApiConfig();

const ProductionMonitoringDashboard = ({ compact = false }) => {
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [refreshInterval, setRefreshInterval] = useState(30000); // 30 seconds

  // System Health Query
  const { data: systemHealth, isLoading: healthLoading, refetch: refetchHealth } = useQuery({
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
  const { data: dbHealth, isLoading: dbLoading } = useQuery({
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
  const { data: performanceMetrics, isLoading: perfLoading } = useQuery({
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
  const { data: deploymentStatus, isLoading: deployLoading } = useQuery({
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
      <div  sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        {healthLoading ? (
          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" size={16} />
        ) : (
          <>
            <MonitorHeart 
              sx={{ 
                color: systemHealth?.status === 'healthy' ? 'success.main' : 'error.main',
                fontSize: 20 
              }} 
            />
            <div  variant="caption" color="text.secondary">
              {systemHealth?.status || 'Unknown'}
            </div>
          </>
        )}
      </div>
    );
  }

  return (
    <div  sx={{ p: 3 }}>
      {/* Header */}
      <div  sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <div  variant="h4" fontWeight="bold">
          🚀 Production Monitoring Dashboard
        </div>
        <div  sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <div className="mb-4"Label
            control={
              <input type="checkbox" className="toggle"
                checked={autoRefresh}
                onChange={(e) => setAutoRefresh(e.target.checked)}
                size="small"
              />
            }
            label="Auto Refresh"
          />
          <button className="p-2 rounded-full hover:bg-gray-100" onClick={() => {
            refetchHealth();
            window.location.reload();
          }}>
            <Refresh />
          </button>
        </div>
      </div>

      <div className="grid" container spacing={3}>
        {/* System Overview */}
        <div className="grid" item xs={12} lg={8}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  variant="h6" gutterBottom>
                System Health Overview
              </div>
              
              {healthLoading ? (
                <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" />
              ) : systemHealth ? (
                <div className="grid" container spacing={2}>
                  <div className="grid" item xs={6} md={3}>
                    <div  textAlign="center">
                      <CheckCircle sx={{ fontSize: 40, color: 'success.main', mb: 1 }} />
                      <div  variant="h6">{systemHealth.uptime ? formatUptime(systemHealth.uptime) : 'N/A'}</div>
                      <div  variant="caption" color="text.secondary">Uptime</div>
                    </div>
                  </div>
                  <div className="grid" item xs={6} md={3}>
                    <div  textAlign="center">
                      <Speed sx={{ fontSize: 40, color: 'info.main', mb: 1 }} />
                      <div  variant="h6">{systemHealth.responseTime || 'N/A'}ms</div>
                      <div  variant="caption" color="text.secondary">Avg Response</div>
                    </div>
                  </div>
                  <div className="grid" item xs={6} md={3}>
                    <div  textAlign="center">
                      <Memory sx={{ fontSize: 40, color: 'warning.main', mb: 1 }} />
                      <div  variant="h6">{systemHealth.memoryUsage || 'N/A'}MB</div>
                      <div  variant="caption" color="text.secondary">Memory Usage</div>
                    </div>
                  </div>
                  <div className="grid" item xs={6} md={3}>
                    <div  textAlign="center">
                      <NetworkCheck sx={{ fontSize: 40, color: 'success.main', mb: 1 }} />
                      <div  variant="h6">{systemHealth.activeConnections || '0'}</div>
                      <div  variant="caption" color="text.secondary">Active Connections</div>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error">Failed to load system health data</div>
              )}
            </div>
          </div>
        </div>

        {/* Quick Status */}
        <div className="grid" item xs={12} lg={4}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  variant="h6" gutterBottom>
                Service Status
              </div>
              
              {deployLoading ? (
                <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" size={24} />
              ) : deploymentStatus ? (
                <div>
                  <div  sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                    <div className="w-full bg-gray-200 rounded-full h-2" 
                      variant="determinate" 
                      value={deploymentStatus.overallHealth * 100}
                      sx={{ flexGrow: 1, mr: 2 }}
                      color={deploymentStatus.overallHealth > 0.8 ? 'success' : 'error'}
                    />
                    <div  variant="body2">
                      {Math.round(deploymentStatus.overallHealth * 100)}%
                    </div>
                  </div>
                  
                  {deploymentStatus.endpoints.slice(0, 5).map((endpoint, index) => (
                    <div  key={index} sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                      <div  variant="body2">{endpoint.endpoint}</div>
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                        size="small" 
                        label={endpoint.success ? 'OK' : 'ERROR'} 
                        color={endpoint.success ? 'success' : 'error'}
                      />
                    </div>
                  ))}
                </div>
              ) : (
                <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="warning">Deployment status unavailable</div>
              )}
            </div>
          </div>
        </div>

        {/* Database Health */}
        <div className="grid" item xs={12} lg={6}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  variant="h6" gutterBottom>
                Database Health
              </div>
              
              {dbLoading ? (
                <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" size={24} />
              ) : dbHealth ? (
                <div>
                  <div  sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                    <Storage sx={{ mr: 1, color: dbHealth.connected ? 'success.main' : 'error.main' }} />
                    <div  variant="body1">
                      {dbHealth.connected ? 'Connected' : 'Disconnected'}
                    </div>
                  </div>
                  
                  {dbHealth.tables && (
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer component={Paper} sx={{ maxHeight: 200 }}>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le size="small">
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Table</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Records</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Status</td>
                          </tr>
                        </thead>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
                          {Object.entries(dbHealth.tables).slice(0, 5).map(([table, data]) => (
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={table}>
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>{table}</td>
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{data.count || 0}</td>
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                                  size="small" 
                                  label={data.status || 'unknown'} 
                                  color={data.status === 'healthy' ? 'success' : 'warning'}
                                />
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              ) : (
                <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error">Database health check failed</div>
              )}
            </div>
          </div>
        </div>

        {/* Performance Trends */}
        <div className="grid" item xs={12} lg={6}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  variant="h6" gutterBottom>
                Performance Trends
              </div>
              
              {perfLoading ? (
                <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" size={24} />
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
                <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="info">Performance data loading...</div>
              )}
            </div>
          </div>
        </div>

        {/* Deployment Information */}
        <div className="grid" item xs={12}>
          <Accordion>
            <AccordionSummary expandIcon={<ExpandMore />}>
              <div  variant="h6">
                📋 Current Deployment Information
              </div>
            </AccordionSummary>
            <AccordionDetails>
              <div className="grid" container spacing={2}>
                <div className="grid" item xs={12} md={4}>
                  <div  variant="subtitle2" color="text.secondary">Environment</div>
                  <div  variant="body1">Production (initialbuild branch)</div>
                </div>
                <div className="grid" item xs={12} md={4}>
                  <div  variant="subtitle2" color="text.secondary">API Gateway</div>
                  <div  variant="body1" sx={{ fontFamily: 'monospace' }}>
                    {API_BASE}
                  </div>
                </div>
                <div className="grid" item xs={12} md={4}>
                  <div  variant="subtitle2" color="text.secondary">Last Deploy</div>
                  <div  variant="body1">
                    {window.__CONFIG__?.BUILD_TIME ? new Date(window.__CONFIG__.BUILD_TIME).toLocaleString() : 'Unknown'}
                  </div>
                </div>
              </div>
              
              <div  sx={{ mt: 2 }}>
                <div  variant="subtitle2" color="text.secondary" gutterBottom>
                  Recent Session Fixes Applied:
                </div>
                <div  sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                  <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" icon={<CheckCircle />} label="Database SSL Fix" color="success" size="small" />
                  <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" icon={<CheckCircle />} label="Cognito Debugging" color="success" size="small" />
                  <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" icon={<CheckCircle />} label="Bundle Optimization" color="success" size="small" />
                  <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" icon={<CheckCircle />} label="Error Boundaries" color="success" size="small" />
                  <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" icon={<CheckCircle />} label="Auth Fallbacks" color="success" size="small" />
                </div>
              </div>
            </AccordionDetails>
          </Accordion>
        </div>
      </div>
    </div>
  );
};

export default ProductionMonitoringDashboard;