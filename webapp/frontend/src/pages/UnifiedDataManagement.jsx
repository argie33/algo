import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Box,
  Paper,
  Typography,
  Grid,
  Card,
  CardContent,
  Switch,
  FormControlLabel,
  Button,
  Chip,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Autocomplete,
  Alert,
  LinearProgress,
  IconButton,
  Tooltip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Tabs,
  Tab,
  Badge,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  Divider,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  CircularProgress,
  Avatar,
  Snackbar,
  AlertTitle
} from '@mui/material';
import {
  TrendingUp,
  TrendingDown,
  PlayArrow,
  Stop,
  Settings,
  Analytics,
  Speed,
  SignalWifi4Bar,
  SignalWifiOff,
  Refresh,
  Add,
  Delete,
  Timeline,
  ShowChart,
  MonetizationOn,
  Assessment,
  Warning,
  CheckCircle,
  Error,
  Info,
  AdminPanelSettings,
  Dashboard,
  Storage,
  NetworkCheck,
  CloudSync,
  DataUsage,
  Security,
  Notifications,
  Schedule,
  ExpandMore,
  MoreVert,
  Power,
  PowerOff,
  Restore,
  ClearAll,
  Build,
  HealthAndSafety,
  TrendingFlat,
  SyncAlt,
  AutoFixHigh,
  ReportProblem,
  OnlinePrediction
} from '@mui/icons-material';
import liveDataIntegration from '../services/liveDataIntegration';
import webSocketService from '../services/webSocketService';

const UnifiedDataManagement = () => {
  const [activeTab, setActiveTab] = useState(0);
  const [systemStatus, setSystemStatus] = useState({
    overall: 'healthy',
    database: 'connected',
    webSocket: 'connected',
    dataProviders: 'active',
    lastUpdate: new Date()
  });
  const [dataStreams, setDataStreams] = useState([]);
  const [apiKeys, setApiKeys] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [snackbar, setSnackbar] = useState({ open: false, message: '', severity: 'info' });

  // Mock data for demonstration
  const mockDataStreams = [
    {
      id: 1,
      name: 'Real-time Stock Prices',
      provider: 'Alpaca',
      status: 'active',
      symbols: 4567,
      latency: 45,
      throughput: '1.2K/s',
      cost: '$89.50',
      quality: 98.5
    },
    {
      id: 2,
      name: 'Options Data',
      provider: 'Yahoo Finance',
      status: 'active',
      symbols: 1234,
      latency: 120,
      throughput: '456/s',
      cost: '$34.20',
      quality: 96.8
    },
    {
      id: 3,
      name: 'Economic Data',
      provider: 'FRED',
      status: 'active',
      symbols: 89,
      latency: 5000,
      throughput: '2/s',
      cost: '$0.00',
      quality: 99.9
    },
    {
      id: 4,
      name: 'Crypto Data',
      provider: 'Binance',
      status: 'warning',
      symbols: 567,
      latency: 89,
      throughput: '890/s',
      cost: '$45.67',
      quality: 94.2
    }
  ];

  const mockApiKeys = [
    { id: 1, provider: 'Alpaca', status: 'active', lastUsed: '2 mins ago', usage: '78%' },
    { id: 2, provider: 'Yahoo Finance', status: 'active', lastUsed: '5 mins ago', usage: '23%' },
    { id: 3, provider: 'FRED', status: 'active', lastUsed: '1 hour ago', usage: '5%' },
    { id: 4, provider: 'Binance', status: 'warning', lastUsed: '10 mins ago', usage: '89%' }
  ];

  const mockAlerts = [
    { id: 1, type: 'warning', message: 'Binance API usage approaching limit', timestamp: '2 mins ago' },
    { id: 2, type: 'info', message: 'Data quality check completed successfully', timestamp: '15 mins ago' },
    { id: 3, type: 'error', message: 'WebSocket connection interrupted briefly', timestamp: '1 hour ago' }
  ];

  useEffect(() => {
    setDataStreams(mockDataStreams);
    setApiKeys(mockApiKeys);
    setAlerts(mockAlerts);
  }, []);

  const handleTabChange = (event, newValue) => {
    setActiveTab(newValue);
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'active':
      case 'healthy':
      case 'connected':
        return 'success';
      case 'warning':
        return 'warning';
      case 'error':
      case 'disconnected':
        return 'error';
      default:
        return 'default';
    }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'active':
      case 'healthy':
      case 'connected':
        return <CheckCircle color="success" />;
      case 'warning':
        return <Warning color="warning" />;
      case 'error':
      case 'disconnected':
        return <Error color="error" />;
      default:
        return <Info />;
    }
  };

  const handleStreamAction = (streamId, action) => {
    setSnackbar({
      open: true,
      message: `${action} applied to stream ${streamId}`,
      severity: 'success'
    });
  };

  const SystemOverview = () => (
    <Grid container spacing={3}>
      {/* System Status Cards */}
      <Grid item xs={12} md={3}>
        <Card>
          <CardContent>
            <Box display="flex" alignItems="center" mb={2}>
              <HealthAndSafety sx={{ mr: 1, color: 'success.main' }} />
              <Typography variant="h6">System Health</Typography>
            </Box>
            <Box display="flex" alignItems="center" justifyContent="space-between">
              <Typography variant="h4" color="success.main">98.5%</Typography>
              <Chip label="Healthy" color="success" size="small" />
            </Box>
          </CardContent>
        </Card>
      </Grid>

      <Grid item xs={12} md={3}>
        <Card>
          <CardContent>
            <Box display="flex" alignItems="center" mb={2}>
              <DataUsage sx={{ mr: 1, color: 'info.main' }} />
              <Typography variant="h6">Data Throughput</Typography>
            </Box>
            <Box display="flex" alignItems="center" justifyContent="space-between">
              <Typography variant="h4" color="info.main">2.5K/s</Typography>
              <Chip label="Normal" color="info" size="small" />
            </Box>
          </CardContent>
        </Card>
      </Grid>

      <Grid item xs={12} md={3}>
        <Card>
          <CardContent>
            <Box display="flex" alignItems="center" mb={2}>
              <MonetizationOn sx={{ mr: 1, color: 'warning.main' }} />
              <Typography variant="h6">Daily Cost</Typography>
            </Box>
            <Box display="flex" alignItems="center" justifyContent="space-between">
              <Typography variant="h4" color="warning.main">$169.37</Typography>
              <Chip label="Budget OK" color="success" size="small" />
            </Box>
          </CardContent>
        </Card>
      </Grid>

      <Grid item xs={12} md={3}>
        <Card>
          <CardContent>
            <Box display="flex" alignItems="center" mb={2}>
              <Speed sx={{ mr: 1, color: 'success.main' }} />
              <Typography variant="h6">Avg Latency</Typography>
            </Box>
            <Box display="flex" alignItems="center" justifyContent="space-between">
              <Typography variant="h4" color="success.main">63ms</Typography>
              <Chip label="Excellent" color="success" size="small" />
            </Box>
          </CardContent>
        </Card>
      </Grid>

      {/* Recent Alerts */}
      <Grid item xs={12}>
        <Card>
          <CardContent>
            <Box display="flex" alignItems="center" justifyContent="space-between" mb={2}>
              <Typography variant="h6">Recent Alerts</Typography>
              <Button size="small" startIcon={<ClearAll />}>Clear All</Button>
            </Box>
            <List>
              {alerts.map((alert) => (
                <ListItem key={alert.id}>
                  <ListItemIcon>
                    {alert.type === 'warning' && <Warning color="warning" />}
                    {alert.type === 'error' && <Error color="error" />}
                    {alert.type === 'info' && <Info color="info" />}
                  </ListItemIcon>
                  <ListItemText
                    primary={alert.message}
                    secondary={alert.timestamp}
                  />
                </ListItem>
              ))}
            </List>
          </CardContent>
        </Card>
      </Grid>
    </Grid>
  );

  const DataStreams = () => (
    <Grid container spacing={3}>
      <Grid item xs={12}>
        <Card>
          <CardContent>
            <Box display="flex" alignItems="center" justifyContent="space-between" mb={2}>
              <Typography variant="h6">Active Data Streams</Typography>
              <Button startIcon={<Add />} variant="contained" size="small">
                Add Stream
              </Button>
            </Box>
            <TableContainer>
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell>Stream Name</TableCell>
                    <TableCell>Provider</TableCell>
                    <TableCell>Status</TableCell>
                    <TableCell>Symbols</TableCell>
                    <TableCell>Latency</TableCell>
                    <TableCell>Throughput</TableCell>
                    <TableCell>Quality</TableCell>
                    <TableCell>Cost</TableCell>
                    <TableCell>Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {dataStreams.map((stream) => (
                    <TableRow key={stream.id}>
                      <TableCell>{stream.name}</TableCell>
                      <TableCell>{stream.provider}</TableCell>
                      <TableCell>
                        <Chip
                          label={stream.status}
                          color={getStatusColor(stream.status)}
                          size="small"
                          icon={getStatusIcon(stream.status)}
                        />
                      </TableCell>
                      <TableCell>{stream.symbols.toLocaleString()}</TableCell>
                      <TableCell>{stream.latency}ms</TableCell>
                      <TableCell>{stream.throughput}</TableCell>
                      <TableCell>
                        <Box display="flex" alignItems="center">
                          <LinearProgress
                            variant="determinate"
                            value={stream.quality}
                            sx={{ width: 60, mr: 1 }}
                          />
                          <Typography variant="body2">{stream.quality}%</Typography>
                        </Box>
                      </TableCell>
                      <TableCell>{stream.cost}</TableCell>
                      <TableCell>
                        <IconButton
                          size="small"
                          onClick={() => handleStreamAction(stream.id, 'pause')}
                        >
                          <Stop />
                        </IconButton>
                        <IconButton
                          size="small"
                          onClick={() => handleStreamAction(stream.id, 'restart')}
                        >
                          <Refresh />
                        </IconButton>
                        <IconButton
                          size="small"
                          onClick={() => handleStreamAction(stream.id, 'configure')}
                        >
                          <Settings />
                        </IconButton>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </CardContent>
        </Card>
      </Grid>
    </Grid>
  );

  const ApiManagement = () => (
    <Grid container spacing={3}>
      <Grid item xs={12}>
        <Card>
          <CardContent>
            <Box display="flex" alignItems="center" justifyContent="space-between" mb={2}>
              <Typography variant="h6">API Keys & Providers</Typography>
              <Button startIcon={<Add />} variant="contained" size="small">
                Add API Key
              </Button>
            </Box>
            <TableContainer>
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell>Provider</TableCell>
                    <TableCell>Status</TableCell>
                    <TableCell>Last Used</TableCell>
                    <TableCell>Usage</TableCell>
                    <TableCell>Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {apiKeys.map((key) => (
                    <TableRow key={key.id}>
                      <TableCell>{key.provider}</TableCell>
                      <TableCell>
                        <Chip
                          label={key.status}
                          color={getStatusColor(key.status)}
                          size="small"
                          icon={getStatusIcon(key.status)}
                        />
                      </TableCell>
                      <TableCell>{key.lastUsed}</TableCell>
                      <TableCell>
                        <Box display="flex" alignItems="center">
                          <LinearProgress
                            variant="determinate"
                            value={parseInt(key.usage)}
                            sx={{ width: 60, mr: 1 }}
                            color={parseInt(key.usage) > 80 ? 'warning' : 'primary'}
                          />
                          <Typography variant="body2">{key.usage}</Typography>
                        </Box>
                      </TableCell>
                      <TableCell>
                        <IconButton size="small">
                          <Settings />
                        </IconButton>
                        <IconButton size="small">
                          <Refresh />
                        </IconButton>
                        <IconButton size="small" color="error">
                          <Delete />
                        </IconButton>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </CardContent>
        </Card>
      </Grid>
    </Grid>
  );

  const SystemControls = () => (
    <Grid container spacing={3}>
      <Grid item xs={12} md={6}>
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              System Controls
            </Typography>
            <Box display="flex" flexDirection="column" gap={2}>
              <FormControlLabel
                control={<Switch defaultChecked />}
                label="Real-time Data Streaming"
              />
              <FormControlLabel
                control={<Switch defaultChecked />}
                label="Data Quality Monitoring"
              />
              <FormControlLabel
                control={<Switch />}
                label="Maintenance Mode"
              />
              <FormControlLabel
                control={<Switch defaultChecked />}
                label="Alert Notifications"
              />
            </Box>
          </CardContent>
        </Card>
      </Grid>

      <Grid item xs={12} md={6}>
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Quick Actions
            </Typography>
            <Box display="flex" flexDirection="column" gap={2}>
              <Button
                variant="outlined"
                startIcon={<Refresh />}
                fullWidth
              >
                Refresh All Data Streams
              </Button>
              <Button
                variant="outlined"
                startIcon={<Build />}
                fullWidth
              >
                Run System Diagnostics
              </Button>
              <Button
                variant="outlined"
                startIcon={<CloudSync />}
                fullWidth
              >
                Sync with External Sources
              </Button>
              <Button
                variant="outlined"
                startIcon={<AutoFixHigh />}
                color="warning"
                fullWidth
              >
                Auto-Repair Data Issues
              </Button>
            </Box>
          </CardContent>
        </Card>
      </Grid>
    </Grid>
  );

  const tabContent = [
    { label: 'Overview', component: <SystemOverview /> },
    { label: 'Data Streams', component: <DataStreams /> },
    { label: 'API Management', component: <ApiManagement /> },
    { label: 'System Controls', component: <SystemControls /> }
  ];

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" gutterBottom>
        <AdminPanelSettings sx={{ mr: 2, verticalAlign: 'middle' }} />
        Unified Data Management
      </Typography>
      <Typography variant="subtitle1" color="text.secondary" gutterBottom>
        Centralized control panel for all data operations, monitoring, and management
      </Typography>

      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
        <Tabs value={activeTab} onChange={handleTabChange}>
          {tabContent.map((tab, index) => (
            <Tab key={index} label={tab.label} />
          ))}
        </Tabs>
      </Box>

      {tabContent[activeTab].component}

      <Snackbar
        open={snackbar.open}
        autoHideDuration={6000}
        onClose={() => setSnackbar({ ...snackbar, open: false })}
      >
        <Alert
          onClose={() => setSnackbar({ ...snackbar, open: false })}
          severity={snackbar.severity}
        >
          {snackbar.message}
        </Alert>
      </Snackbar>
    </Box>
  );
};

export default UnifiedDataManagement;