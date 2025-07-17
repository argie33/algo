import React, { useState, useEffect, useRef } from 'react';
import {
  Box,
  Grid,
  Card,
  CardContent,
  Typography,
  Button,
  Chip,
  LinearProgress,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Alert,
  AlertTitle,
  IconButton,
  Tooltip,
  Switch,
  FormControlLabel,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Divider,
  Fab,
  CircularProgress,
  Tabs,
  Tab
} from '@mui/material';
import {
  Speed as SpeedIcon,
  NetworkCheck as NetworkIcon,
  AttachMoney as CostIcon,
  Timeline as MetricsIcon,
  Settings as SettingsIcon,
  Refresh as RefreshIcon,
  PlayArrow as StartIcon,
  Stop as StopIcon,
  Warning as WarningIcon,
  CheckCircle as SuccessIcon,
  Error as ErrorIcon,
  TrendingUp as TrendingUpIcon,
  TrendingDown as TrendingDownIcon,
  Analytics as AnalyticsIcon,
  Memory as MemoryIcon
} from '@mui/icons-material';
import { useAuth } from '../../contexts/AuthContext';
import ProviderMetrics from './ProviderMetrics';
import ConnectionMonitor from './ConnectionMonitor';
import RealTimeAnalytics from './RealTimeAnalytics';
import CostOptimizer from './CostOptimizer';
import AlertMonitor from './AlertMonitor';

const LiveDataAdmin = () => {
  const { user } = useAuth();
  const [dashboardData, setDashboardData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [selectedProvider, setSelectedProvider] = useState('');
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [activeTab, setActiveTab] = useState('overview');
  const intervalRef = useRef(null);

  // Fetch dashboard data from liveDataAdmin
  const fetchDashboardData = async () => {
    try {
      const response = await fetch('/api/liveDataAdmin/dashboard', {
        headers: {
          'Authorization': `Bearer ${user?.token}`,
          'Content-Type': 'application/json'
        }
      });

      if (!response.ok) {
        throw new Error(`Failed to fetch dashboard data: ${response.status}`);
      }

      const result = await response.json();
      setDashboardData(result.data);
      setError(null);
    } catch (err) {
      console.error('Dashboard fetch error:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // Auto-refresh functionality
  useEffect(() => {
    fetchDashboardData();

    if (autoRefresh) {
      intervalRef.current = setInterval(fetchDashboardData, 5000);
    }

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [autoRefresh]);

  // Status color mapping
  const getStatusColor = (status) => {
    switch (status) {
      case 'operational': return 'success';
      case 'connected': return 'success';
      case 'warning': return 'warning';
      case 'error': return 'error';
      case 'disconnected': return 'error';
      default: return 'default';
    }
  };

  // Performance indicator
  const getPerformanceIndicator = (value, threshold) => {
    if (value < threshold * 0.7) return { color: 'success', icon: <TrendingUpIcon /> };
    if (value < threshold * 0.9) return { color: 'warning', icon: <TrendingUpIcon /> };
    return { color: 'error', icon: <TrendingDownIcon /> };
  };

  const handleProviderUpdate = (providerId, settings) => {
    console.log('Provider updated:', providerId, settings);
    fetchDashboardData(); // Refresh data
  };

  const handleConnectionAction = (action, data) => {
    console.log('Connection action:', action, data);
    fetchDashboardData(); // Refresh data
  };

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight="400px">
        <CircularProgress size={60} />
        <Typography variant="h6" sx={{ ml: 2 }}>
          Loading Live Data Dashboard...
        </Typography>
      </Box>
    );
  }

  if (error) {
    return (
      <Alert severity="error" sx={{ m: 2 }}>
        <AlertTitle>Dashboard Error</AlertTitle>
        {error}
        <Button onClick={fetchDashboardData} sx={{ mt: 1 }}>
          Retry
        </Button>
      </Alert>
    );
  }

  return (
    <Box sx={{ p: 3, bgcolor: '#f5f5f5', minHeight: '100vh' }}>
      {/* Header */}
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h4" component="h1" fontWeight="bold">
          Live Data Control Center
        </Typography>
        <Box display="flex" gap={2}>
          <FormControlLabel
            control={
              <Switch
                checked={autoRefresh}
                onChange={(e) => setAutoRefresh(e.target.checked)}
                color="primary"
              />
            }
            label="Auto Refresh"
          />
          <Button
            variant="contained"
            startIcon={<RefreshIcon />}
            onClick={fetchDashboardData}
            disabled={loading}
          >
            Refresh
          </Button>
          <Button
            variant="outlined"
            startIcon={<SettingsIcon />}
            onClick={() => setSettingsOpen(true)}
          >
            Settings
          </Button>
        </Box>
      </Box>

      {/* Navigation Tabs */}
      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
        <Tabs 
          value={activeTab} 
          onChange={(e, newValue) => setActiveTab(newValue)}
          variant="scrollable"
          scrollButtons="auto"
        >
          <Tab label="Overview" value="overview" />
          <Tab label="Providers" value="providers" />
          <Tab label="Connections" value="connections" />
          <Tab label="Analytics" value="analytics" />
          <Tab label="Cost Optimizer" value="costs" />
          <Tab label="Alerts" value="alerts" />
        </Tabs>
      </Box>

      {/* Tab Content */}
      {activeTab === 'overview' && (
        <>
          {/* Global Metrics Cards */}
      <Grid container spacing={3} mb={3}>
        <Grid item xs={12} sm={6} md={3}>
          <Card elevation={3}>
            <CardContent>
              <Box display="flex" alignItems="center" justifyContent="space-between">
                <Box>
                  <Typography color="textSecondary" gutterBottom>
                    Active Connections
                  </Typography>
                  <Typography variant="h4" component="div">
                    {dashboardData?.global?.totalConnections || 0}
                  </Typography>
                  <Typography variant="body2" color="textSecondary">
                    of {dashboardData?.limits?.connections?.max || 10} max
                  </Typography>
                </Box>
                <NetworkIcon color="primary" fontSize="large" />
              </Box>
              <LinearProgress
                variant="determinate"
                value={dashboardData?.limits?.connections?.usage || 0}
                color={dashboardData?.limits?.connections?.usage > 80 ? 'error' : 'primary'}
                sx={{ mt: 1 }}
              />
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card elevation={3}>
            <CardContent>
              <Box display="flex" alignItems="center" justifyContent="space-between">
                <Box>
                  <Typography color="textSecondary" gutterBottom>
                    Daily Cost
                  </Typography>
                  <Typography variant="h4" component="div">
                    ${(dashboardData?.global?.dailyCost || 0).toFixed(2)}
                  </Typography>
                  <Typography variant="body2" color="textSecondary">
                    of ${dashboardData?.limits?.cost?.max || 50} budget
                  </Typography>
                </Box>
                <CostIcon color="primary" fontSize="large" />
              </Box>
              <LinearProgress
                variant="determinate"
                value={dashboardData?.limits?.cost?.usage || 0}
                color={dashboardData?.limits?.cost?.usage > 80 ? 'error' : 'primary'}
                sx={{ mt: 1 }}
              />
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card elevation={3}>
            <CardContent>
              <Box display="flex" alignItems="center" justifyContent="space-between">
                <Box>
                  <Typography color="textSecondary" gutterBottom>
                    Tracked Symbols
                  </Typography>
                  <Typography variant="h4" component="div">
                    {dashboardData?.global?.totalSymbols || 0}
                  </Typography>
                  <Typography variant="body2" color="textSecondary">
                    subscribers: {dashboardData?.global?.totalSubscribers || 0}
                  </Typography>
                </Box>
                <AnalyticsIcon color="primary" fontSize="large" />
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card elevation={3}>
            <CardContent>
              <Box display="flex" alignItems="center" justifyContent="space-between">
                <Box>
                  <Typography color="textSecondary" gutterBottom>
                    Avg Latency
                  </Typography>
                  <Typography variant="h4" component="div">
                    {(dashboardData?.global?.performance?.avg || 0).toFixed(0)}ms
                  </Typography>
                  <Typography variant="body2" color="textSecondary">
                    P95: {(dashboardData?.global?.performance?.p95 || 0).toFixed(0)}ms
                  </Typography>
                </Box>
                <SpeedIcon color="primary" fontSize="large" />
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Alerts Section */}
      {dashboardData?.alerts && dashboardData.alerts.length > 0 && (
        <Card elevation={3} sx={{ mb: 3 }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Active Alerts
            </Typography>
            {dashboardData.alerts.map((alert, index) => (
              <Alert
                key={index}
                severity={alert.type}
                sx={{ mb: 1 }}
                action={
                  <Button color="inherit" size="small">
                    {alert.action}
                  </Button>
                }
              >
                {alert.message}
              </Alert>
            ))}
          </CardContent>
        </Card>
      )}

      {/* Provider Status Table */}
      <Card elevation={3} sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Data Provider Status
          </Typography>
          <TableContainer>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>Provider</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell align="right">Connections</TableCell>
                  <TableCell align="right">Symbols</TableCell>
                  <TableCell align="right">Latency</TableCell>
                  <TableCell align="right">Success Rate</TableCell>
                  <TableCell align="right">Daily Cost</TableCell>
                  <TableCell>Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {dashboardData?.providers && Object.entries(dashboardData.providers).map(([key, provider]) => (
                  <TableRow key={key}>
                    <TableCell>
                      <Box display="flex" alignItems="center" gap={1}>
                        <Typography variant="body1" fontWeight="bold">
                          {provider.name}
                        </Typography>
                      </Box>
                    </TableCell>
                    <TableCell>
                      <Chip
                        label={provider.status}
                        color={getStatusColor(provider.status)}
                        size="small"
                      />
                    </TableCell>
                    <TableCell align="right">{provider.connections}</TableCell>
                    <TableCell align="right">{provider.symbols}</TableCell>
                    <TableCell align="right">
                      <Box display="flex" alignItems="center" justifyContent="flex-end" gap={1}>
                        {provider.latency.toFixed(0)}ms
                        {getPerformanceIndicator(provider.latency, 100).icon}
                      </Box>
                    </TableCell>
                    <TableCell align="right">
                      <Typography
                        color={provider.successRate > 95 ? 'success.main' : 'error.main'}
                      >
                        {provider.successRate.toFixed(1)}%
                      </Typography>
                    </TableCell>
                    <TableCell align="right">${provider.costToday.toFixed(2)}</TableCell>
                    <TableCell>
                      <IconButton
                        size="small"
                        onClick={() => {
                          setSelectedProvider(key);
                          setSettingsOpen(true);
                        }}
                      >
                        <SettingsIcon />
                      </IconButton>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </CardContent>
      </Card>

      {/* Performance Recommendations */}
      {dashboardData?.recommendations && dashboardData.recommendations.length > 0 && (
        <Card elevation={3}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Optimization Recommendations
            </Typography>
            {dashboardData.recommendations.map((rec, index) => (
              <Alert
                key={index}
                severity="info"
                sx={{ mb: 1 }}
                action={
                  <Button
                    color="inherit"
                    size="small"
                    variant="outlined"
                  >
                    Apply
                  </Button>
                }
              >
                <AlertTitle>{rec.message}</AlertTitle>
                {rec.action}
                {rec.estimatedSavings && (
                  <Typography variant="body2" sx={{ mt: 1 }}>
                    Estimated savings: ${rec.estimatedSavings}/day
                  </Typography>
                )}
              </Alert>
            ))}
          </CardContent>
        </Card>
        </>
      )}

      {/* Providers Tab */}
      {activeTab === 'providers' && (
        <ProviderMetrics
          providersData={dashboardData?.providers}
          onProviderUpdate={handleProviderUpdate}
          onRefresh={fetchDashboardData}
        />
      )}

      {/* Connections Tab */}
      {activeTab === 'connections' && (
        <ConnectionMonitor
          connectionsData={dashboardData?.connections || []}
          onConnectionAction={handleConnectionAction}
          onRefresh={fetchDashboardData}
        />
      )}

      {/* Analytics Tab */}
      {activeTab === 'analytics' && (
        <RealTimeAnalytics
          analyticsData={dashboardData}
          onRefresh={fetchDashboardData}
        />
      )}

      {/* Cost Optimizer Tab */}
      {activeTab === 'costs' && (
        <CostOptimizer
          costData={dashboardData}
          onOptimize={() => console.log('Optimizing costs...')}
          onApplyRecommendation={(id) => console.log('Applying recommendation:', id)}
        />
      )}

      {/* Alerts Tab */}
      {activeTab === 'alerts' && (
        <AlertMonitor
          alertData={dashboardData?.alerts}
          onConfigUpdate={(config) => console.log('Alert config updated:', config)}
          onRefresh={fetchDashboardData}
        />
      )}

      {/* Settings Dialog */}
      <Dialog
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>
          Live Data Settings
          {selectedProvider && ` - ${selectedProvider}`}
        </DialogTitle>
        <DialogContent>
          <Box sx={{ pt: 2 }}>
            <Grid container spacing={3}>
              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  label="Max Connections"
                  type="number"
                  defaultValue={10}
                  variant="outlined"
                />
              </Grid>
              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  label="Daily Budget ($)"
                  type="number"
                  defaultValue={50}
                  variant="outlined"
                />
              </Grid>
              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  label="Rate Limit (req/min)"
                  type="number"
                  defaultValue={200}
                  variant="outlined"
                />
              </Grid>
              <Grid item xs={12} sm={6}>
                <FormControl fullWidth>
                  <InputLabel>Auto Optimization</InputLabel>
                  <Select defaultValue="conservative" label="Auto Optimization">
                    <MenuItem value="disabled">Disabled</MenuItem>
                    <MenuItem value="conservative">Conservative</MenuItem>
                    <MenuItem value="aggressive">Aggressive</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
            </Grid>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSettingsOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            onClick={() => setSettingsOpen(false)}
          >
            Save Settings
          </Button>
        </DialogActions>
      </Dialog>

      {/* Floating Action Button for Quick Actions */}
      <Fab
        color="primary"
        sx={{
          position: 'fixed',
          bottom: 16,
          right: 16
        }}
        onClick={fetchDashboardData}
      >
        <RefreshIcon />
      </Fab>
    </Box>
  );
};

export default LiveDataAdmin;