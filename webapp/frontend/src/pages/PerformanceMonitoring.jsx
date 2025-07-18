import React, { useState, useEffect } from 'react';
import {
  Container,
  Grid,
  Card,
  CardContent,
  Typography,
  Box,
  Alert,
  LinearProgress,
  Chip,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  IconButton,
  Switch,
  FormControlLabel,
  Divider,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  Tooltip,
  CircularProgress
} from '@mui/material';
import {
  Speed,
  Memory,
  Timeline,
  Error,
  CheckCircle,
  Warning,
  Refresh,
  DataUsage,
  Api,
  Storage,
  NetworkCheck,
  TrendingUp,
  TrendingDown,
  Settings
} from '@mui/icons-material';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer, BarChart, Bar, PieChart, Pie, Cell } from 'recharts';
import { getApiConfig } from '../services/api';

const PerformanceMonitoring = () => {
  const [metrics, setMetrics] = useState(null);
  const [summary, setSummary] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [refreshInterval, setRefreshInterval] = useState(30000); // 30 seconds

  const { apiUrl } = getApiConfig();

  // Fetch performance data
  const fetchPerformanceData = async () => {
    try {
      const [summaryRes, alertsRes] = await Promise.all([
        fetch(`${apiUrl}/api/performance/summary`, {
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('token')}`,
            'Content-Type': 'application/json'
          }
        }),
        fetch(`${apiUrl}/api/performance/alerts`, {
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('token')}`,
            'Content-Type': 'application/json'
          }
        })
      ]);

      if (!summaryRes.ok || !alertsRes.ok) {
        throw new Error('Failed to fetch performance data');
      }

      const summaryData = await summaryRes.json();
      const alertsData = await alertsRes.json();

      setSummary(summaryData.data);
      setAlerts(alertsData.data.alerts || []);
      setError(null);
    } catch (error) {
      console.error('Error fetching performance data:', error);
      setError(error.message);
    } finally {
      setLoading(false);
    }
  };

  // Fetch detailed metrics
  const fetchDetailedMetrics = async () => {
    try {
      const response = await fetch(`${apiUrl}/api/performance/metrics`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json'
        }
      });

      if (!response.ok) {
        throw new Error('Failed to fetch detailed metrics');
      }

      const data = await response.json();
      setMetrics(data.data);
    } catch (error) {
      console.error('Error fetching detailed metrics:', error);
    }
  };

  // Auto-refresh effect
  useEffect(() => {
    fetchPerformanceData();
    fetchDetailedMetrics();
  }, []);

  useEffect(() => {
    if (autoRefresh) {
      const interval = setInterval(() => {
        fetchPerformanceData();
        fetchDetailedMetrics();
      }, refreshInterval);
      return () => clearInterval(interval);
    }
  }, [autoRefresh, refreshInterval]);

  // Helper functions
  const formatBytes = (bytes) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const formatDuration = (ms) => {
    if (ms < 1000) return `${ms}ms`;
    if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
    if (ms < 3600000) return `${(ms / 60000).toFixed(1)}m`;
    return `${(ms / 3600000).toFixed(1)}h`;
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'healthy': return 'success';
      case 'warning': return 'warning';
      case 'critical': return 'error';
      default: return 'default';
    }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'healthy': return <CheckCircle color="success" />;
      case 'warning': return <Warning color="warning" />;
      case 'critical': return <Error color="error" />;
      default: return <Speed />;
    }
  };

  if (loading) {
    return (
      <div className="container mx-auto" maxWidth="xl" sx={{ py: 4 }}>
        <div  display="flex" justifyContent="center" alignItems="center" minHeight="60vh">
          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" size={60} />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="container mx-auto" maxWidth="xl" sx={{ py: 4 }}>
        <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error">
          Error loading performance data: {error}
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto" maxWidth="xl" sx={{ py: 4 }}>
      {/* Header */}
      <div  sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 4 }}>
        <div  variant="h4" component="h1">
          Performance Monitoring
        </div>
        <div  sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <div className="mb-4"Label
            control={
              <input type="checkbox" className="toggle"
                checked={autoRefresh}
                onChange={(e) => setAutoRefresh(e.target.checked)}
              />
            }
            label="Auto Refresh"
          />
          <button className="p-2 rounded-full hover:bg-gray-100" onClick={fetchPerformanceData} disabled={loading}>
            <Refresh />
          </button>
        </div>
      </div>

      {/* Alerts */}
      {alerts.length > 0 && (
        <div className="bg-white shadow-md rounded-lg" sx={{ mb: 4 }}>
          <div className="bg-white shadow-md rounded-lg"Content>
            <div  variant="h6" gutterBottom>
              Active Alerts
            </div>
            <List>
              {alerts.map((alert, index) => (
                <ListItem key={index}>
                  <ListItemIcon>
                    {alert.severity === 'critical' ? <Error color="error" /> : <Warning color="warning" />}
                  </ListItemIcon>
                  <ListItemText
                    primary={alert.message}
                    secondary={`Type: ${alert.type} | Value: ${alert.value} | Threshold: ${alert.threshold}`}
                  />
                </ListItem>
              ))}
            </List>
          </div>
        </div>
      )}

      {/* System Overview */}
      <div className="grid" container spacing={3} sx={{ mb: 4 }}>
        <div className="grid" item xs={12} md={3}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                {getStatusIcon(summary?.status)}
                <div  sx={{ ml: 2 }}>
                  <div  variant="h6">System Status</div>
                  <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                    label={summary?.status || 'Unknown'} 
                    color={getStatusColor(summary?.status)} 
                    size="small"
                  />
                </div>
              </div>
              <div  variant="body2" color="text.secondary">
                Uptime: {formatDuration(summary?.uptime || 0)}
              </div>
            </div>
          </div>
        </div>

        <div className="grid" item xs={12} md={3}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                <Speed color="primary" />
                <div  sx={{ ml: 2 }}>
                  <div  variant="h6">Response Time</div>
                  <div  variant="h4" color="primary">
                    {summary?.avgResponseTime?.toFixed(0) || 0}ms
                  </div>
                </div>
              </div>
              <div  variant="body2" color="text.secondary">
                Average response time
              </div>
            </div>
          </div>
        </div>

        <div className="grid" item xs={12} md={3}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                <Memory color="secondary" />
                <div  sx={{ ml: 2 }}>
                  <div  variant="h6">Memory Usage</div>
                  <div  variant="h4" color="secondary">
                    {summary?.memoryUsage?.utilization?.toFixed(1) || 0}%
                  </div>
                </div>
              </div>
              <div  variant="body2" color="text.secondary">
                {formatBytes(summary?.memoryUsage?.used || 0)} / {formatBytes(summary?.memoryUsage?.total || 0)}
              </div>
            </div>
          </div>
        </div>

        <div className="grid" item xs={12} md={3}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                <Api color="info" />
                <div  sx={{ ml: 2 }}>
                  <div  variant="h6">Requests</div>
                  <div  variant="h4" color="info">
                    {summary?.activeRequests || 0}
                  </div>
                </div>
              </div>
              <div  variant="body2" color="text.secondary">
                {summary?.totalRequests || 0} total requests
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Error Rate */}
      <div className="grid" container spacing={3} sx={{ mb: 4 }}>
        <div className="grid" item xs={12} md={6}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  variant="h6" gutterBottom>
                Error Rate
              </div>
              <div  sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                <div  variant="h3" color={summary?.errorRate > 0.05 ? 'error' : 'success'}>
                  {((summary?.errorRate || 0) * 100).toFixed(2)}%
                </div>
                <div  sx={{ ml: 2 }}>
                  {summary?.errorRate > 0.05 ? (
                    <TrendingUp color="error" />
                  ) : (
                    <TrendingDown color="success" />
                  )}
                </div>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2" 
                variant="determinate" 
                value={Math.min((summary?.errorRate || 0) * 100, 100)} 
                color={summary?.errorRate > 0.05 ? 'error' : 'success'}
              />
            </div>
          </div>
        </div>

        <div className="grid" item xs={12} md={6}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  variant="h6" gutterBottom>
                Memory Utilization
              </div>
              <div  sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                <div  variant="h3" color={(summary?.memoryUsage?.utilization || 0) > 80 ? 'error' : 'primary'}>
                  {(summary?.memoryUsage?.utilization || 0).toFixed(1)}%
                </div>
                <div  sx={{ ml: 2 }}>
                  <Memory color={(summary?.memoryUsage?.utilization || 0) > 80 ? 'error' : 'primary'} />
                </div>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2" 
                variant="determinate" 
                value={Math.min(summary?.memoryUsage?.utilization || 0, 100)} 
                color={(summary?.memoryUsage?.utilization || 0) > 80 ? 'error' : 'primary'}
              />
            </div>
          </div>
        </div>
      </div>

      {/* API Endpoints Performance */}
      {metrics && (
        <div className="bg-white shadow-md rounded-lg">
          <div className="bg-white shadow-md rounded-lg"Content>
            <div  variant="h6" gutterBottom>
              API Endpoints Performance
            </div>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Endpoint</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Requests</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Errors</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Error Rate</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Avg Response Time</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Max Response Time</td>
                  </tr>
                </thead>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
                  {Object.entries(metrics.api?.requests || {}).map(([endpoint, stats]) => (
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={endpoint}>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>{endpoint}</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{stats.count}</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{stats.errors}</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                          label={`${((stats.errors / stats.count) * 100).toFixed(2)}%`}
                          color={stats.errors / stats.count > 0.05 ? 'error' : 'success'}
                          size="small"
                        />
                      </td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{stats.avgResponseTime?.toFixed(0)}ms</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{stats.maxResponseTime?.toFixed(0)}ms</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default PerformanceMonitoring;