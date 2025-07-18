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
      <Container maxWidth="xl" sx={{ py: 4 }}>
        <Box display="flex" justifyContent="center" alignItems="center" minHeight="60vh">
          <CircularProgress size={60} />
        </Box>
      </Container>
    );
  }

  if (error) {
    return (
      <Container maxWidth="xl" sx={{ py: 4 }}>
        <Alert severity="error">
          Error loading performance data: {error}
        </Alert>
      </Container>
    );
  }

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      {/* Header */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 4 }}>
        <Typography variant="h4" component="h1">
          Performance Monitoring
        </Typography>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <FormControlLabel
            control={
              <Switch
                checked={autoRefresh}
                onChange={(e) => setAutoRefresh(e.target.checked)}
              />
            }
            label="Auto Refresh"
          />
          <IconButton onClick={fetchPerformanceData} disabled={loading}>
            <Refresh />
          </IconButton>
        </Box>
      </Box>

      {/* Alerts */}
      {alerts.length > 0 && (
        <Card sx={{ mb: 4 }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Active Alerts
            </Typography>
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
          </CardContent>
        </Card>
      )}

      {/* System Overview */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                {getStatusIcon(summary?.status)}
                <Box sx={{ ml: 2 }}>
                  <Typography variant="h6">System Status</Typography>
                  <Chip 
                    label={summary?.status || 'Unknown'} 
                    color={getStatusColor(summary?.status)} 
                    size="small"
                  />
                </Box>
              </Box>
              <Typography variant="body2" color="text.secondary">
                Uptime: {formatDuration(summary?.uptime || 0)}
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                <Speed color="primary" />
                <Box sx={{ ml: 2 }}>
                  <Typography variant="h6">Response Time</Typography>
                  <Typography variant="h4" color="primary">
                    {summary?.avgResponseTime?.toFixed(0) || 0}ms
                  </Typography>
                </Box>
              </Box>
              <Typography variant="body2" color="text.secondary">
                Average response time
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                <Memory color="secondary" />
                <Box sx={{ ml: 2 }}>
                  <Typography variant="h6">Memory Usage</Typography>
                  <Typography variant="h4" color="secondary">
                    {summary?.memoryUsage?.utilization?.toFixed(1) || 0}%
                  </Typography>
                </Box>
              </Box>
              <Typography variant="body2" color="text.secondary">
                {formatBytes(summary?.memoryUsage?.used || 0)} / {formatBytes(summary?.memoryUsage?.total || 0)}
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                <Api color="info" />
                <Box sx={{ ml: 2 }}>
                  <Typography variant="h6">Requests</Typography>
                  <Typography variant="h4" color="info">
                    {summary?.activeRequests || 0}
                  </Typography>
                </Box>
              </Box>
              <Typography variant="body2" color="text.secondary">
                {summary?.totalRequests || 0} total requests
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Error Rate */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Error Rate
              </Typography>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                <Typography variant="h3" color={summary?.errorRate > 0.05 ? 'error' : 'success'}>
                  {((summary?.errorRate || 0) * 100).toFixed(2)}%
                </Typography>
                <Box sx={{ ml: 2 }}>
                  {summary?.errorRate > 0.05 ? (
                    <TrendingUp color="error" />
                  ) : (
                    <TrendingDown color="success" />
                  )}
                </Box>
              </Box>
              <LinearProgress 
                variant="determinate" 
                value={Math.min((summary?.errorRate || 0) * 100, 100)} 
                color={summary?.errorRate > 0.05 ? 'error' : 'success'}
              />
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Memory Utilization
              </Typography>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                <Typography variant="h3" color={(summary?.memoryUsage?.utilization || 0) > 80 ? 'error' : 'primary'}>
                  {(summary?.memoryUsage?.utilization || 0).toFixed(1)}%
                </Typography>
                <Box sx={{ ml: 2 }}>
                  <Memory color={(summary?.memoryUsage?.utilization || 0) > 80 ? 'error' : 'primary'} />
                </Box>
              </Box>
              <LinearProgress 
                variant="determinate" 
                value={Math.min(summary?.memoryUsage?.utilization || 0, 100)} 
                color={(summary?.memoryUsage?.utilization || 0) > 80 ? 'error' : 'primary'}
              />
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* API Endpoints Performance */}
      {metrics && (
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              API Endpoints Performance
            </Typography>
            <TableContainer>
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell>Endpoint</TableCell>
                    <TableCell align="right">Requests</TableCell>
                    <TableCell align="right">Errors</TableCell>
                    <TableCell align="right">Error Rate</TableCell>
                    <TableCell align="right">Avg Response Time</TableCell>
                    <TableCell align="right">Max Response Time</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {Object.entries(metrics.api?.requests || {}).map(([endpoint, stats]) => (
                    <TableRow key={endpoint}>
                      <TableCell>{endpoint}</TableCell>
                      <TableCell align="right">{stats.count}</TableCell>
                      <TableCell align="right">{stats.errors}</TableCell>
                      <TableCell align="right">
                        <Chip 
                          label={`${((stats.errors / stats.count) * 100).toFixed(2)}%`}
                          color={stats.errors / stats.count > 0.05 ? 'error' : 'success'}
                          size="small"
                        />
                      </TableCell>
                      <TableCell align="right">{stats.avgResponseTime?.toFixed(0)}ms</TableCell>
                      <TableCell align="right">{stats.maxResponseTime?.toFixed(0)}ms</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </CardContent>
        </Card>
      )}
    </Container>
  );
};

export default PerformanceMonitoring;