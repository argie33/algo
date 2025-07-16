import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Box,
  Paper,
  Typography,
  Grid,
  Card,
  CardContent,
  CardHeader,
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
  Avatar,
  CircularProgress
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
  Dashboard,
  CloudDone,
  Storage,
  PeopleAlt,
  Router,
  DataUsage,
  Memory
} from '@mui/icons-material';
import {
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer
} from 'recharts';
import { useAuth } from '../contexts/AuthContext';
import api from '../services/api';

// Chart.js registration removed - using recharts instead

/**
 * Centralized Live Data Service Dashboard
 * 
 * Based on FINANCIAL_PLATFORM_BLUEPRINT.md centralized architecture:
 * - Single websocket connection per symbol (not per user)
 * - Admin-managed data feeds for cost efficiency
 * - Centralized caching and distribution
 * - Real-time service health monitoring
 */

const LiveDataCentralized = () => {
  // Auth context
  const { user } = useAuth();

  // Service monitoring state
  const [serviceMetrics, setServiceMetrics] = useState({
    activeConnections: 0,
    totalSubscribers: 0,
    dataLatency: 0,
    errorRate: 0,
    connectionHealth: 'unknown',
    lastUpdate: null
  });

  // Admin configuration state
  const [adminConfig, setAdminConfig] = useState({
    enabledFeeds: ['stocks', 'options', 'crypto'],
    symbols: ['AAPL', 'MSFT', 'GOOGL', 'SPY', 'QQQ', 'TSLA'],
    providers: ['alpaca', 'polygon']
  });

  // Live data streams state
  const [liveStreams, setLiveStreams] = useState(new Map());
  const [subscribedSymbols, setSubscribedSymbols] = useState(new Set());

  // UI state
  const [activeTab, setActiveTab] = useState(0);
  const [isServiceRunning, setIsServiceRunning] = useState(false);
  const [newSymbol, setNewSymbol] = useState('');
  const [selectedProvider, setSelectedProvider] = useState('alpaca');

  // Refs for real-time updates
  const metricsInterval = useRef(null);
  const dataInterval = useRef(null);

  // Popular symbols for quick selection
  const POPULAR_SYMBOLS = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'NVDA', 'META', 'NFLX',
    'SPY', 'QQQ', 'IWM', 'VTI', 'AMD', 'CRM', 'ORCL', 'ADBE'
  ];

  // Initialize service monitoring
  useEffect(() => {
    fetchServiceMetrics();
    
    // Set up periodic metrics refresh
    metricsInterval.current = setInterval(fetchServiceMetrics, 5000);
    
    return () => {
      if (metricsInterval.current) clearInterval(metricsInterval.current);
      if (dataInterval.current) clearInterval(dataInterval.current);
    };
  }, []);

  // Fetch service health metrics
  const fetchServiceMetrics = async () => {
    try {
      const response = await api.get('/api/live-data/metrics');
      if (response.success) {
        setServiceMetrics(response.data);
        setIsServiceRunning(response.data.connectionHealth === 'healthy');
      }
    } catch (error) {
      console.error('Failed to fetch service metrics:', error);
      setServiceMetrics(prev => ({
        ...prev,
        connectionHealth: 'error',
        lastUpdate: new Date().toISOString()
      }));
    }
  };

  // Subscribe to symbol data
  const subscribeToSymbol = async (symbol) => {
    try {
      const response = await api.post('/api/live-data/subscribe', {
        symbol,
        provider: selectedProvider
      });
      
      if (response.success) {
        setSubscribedSymbols(prev => new Set([...prev, symbol]));
        console.log(`✅ Subscribed to ${symbol} via ${selectedProvider}`);
      }
    } catch (error) {
      console.error(`Failed to subscribe to ${symbol}:`, error);
    }
  };

  // Unsubscribe from symbol data
  const unsubscribeFromSymbol = async (symbol) => {
    try {
      const response = await api.post('/api/live-data/unsubscribe', {
        symbol
      });
      
      if (response.success) {
        setSubscribedSymbols(prev => {
          const newSet = new Set(prev);
          newSet.delete(symbol);
          return newSet;
        });
        
        setLiveStreams(prev => {
          const newMap = new Map(prev);
          newMap.delete(symbol);
          return newMap;
        });
        
        console.log(`✅ Unsubscribed from ${symbol}`);
      }
    } catch (error) {
      console.error(`Failed to unsubscribe from ${symbol}:`, error);
    }
  };

  // Add new symbol subscription
  const handleAddSymbol = () => {
    if (newSymbol.trim() && !subscribedSymbols.has(newSymbol.toUpperCase())) {
      subscribeToSymbol(newSymbol.toUpperCase());
      setNewSymbol('');
    }
  };

  // Service control functions
  const startLiveDataService = async () => {
    try {
      const response = await api.post('/api/live-data/start');
      if (response.success) {
        setIsServiceRunning(true);
        console.log('✅ Live data service started');
      }
    } catch (error) {
      console.error('Failed to start live data service:', error);
    }
  };

  const stopLiveDataService = async () => {
    try {
      const response = await api.post('/api/live-data/stop');
      if (response.success) {
        setIsServiceRunning(false);
        setLiveStreams(new Map());
        setSubscribedSymbols(new Set());
        console.log('✅ Live data service stopped');
      }
    } catch (error) {
      console.error('Failed to stop live data service:', error);
    }
  };

  // Get status color based on service health
  const getStatusColor = (health) => {
    switch (health) {
      case 'healthy': return 'success';
      case 'degraded': return 'warning';
      case 'error': return 'error';
      default: return 'default';
    }
  };

  // Metrics visualization data for recharts
  const connectionMetricsData = [
    { name: 'Active Connections', value: serviceMetrics.activeConnections, color: '#1976d2' },
    { name: 'Total Subscribers', value: serviceMetrics.totalSubscribers, color: '#2e7d32' },
    { name: 'Cached Symbols', value: subscribedSymbols.size, color: '#ed6c02' }
  ];

  const latencyData = Array.from({length: 10}, (_, i) => ({
    time: i + 1,
    latency: [45, 38, 42, 35, 48, 41, 39, 44, 37, serviceMetrics.dataLatency || 40][i]
  }));

  return (
    <Box sx={{ p: 3 }}>
      {/* Page Header */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h3" component="h1" gutterBottom sx={{ fontWeight: 600 }}>
          Centralized Live Data Service
        </Typography>
        <Typography variant="h6" color="text.secondary" sx={{ mb: 2 }}>
          Revolutionary architecture with single API connections per symbol for maximum efficiency
        </Typography>
        
        {/* Service Status Bar */}
        <Card sx={{ mb: 3, backgroundColor: isServiceRunning ? 'success.main' : 'error.main', color: 'white' }}>
          <CardContent sx={{ py: 2 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                {isServiceRunning ? <CloudDone /> : <SignalWifiOff />}
                <Typography variant="h6">
                  Service Status: {isServiceRunning ? 'OPERATIONAL' : 'STOPPED'}
                </Typography>
              </Box>
              
              <Box sx={{ display: 'flex', gap: 1 }}>
                <Button
                  variant="contained"
                  color={isServiceRunning ? "error" : "success"}
                  onClick={isServiceRunning ? stopLiveDataService : startLiveDataService}
                  startIcon={isServiceRunning ? <Stop /> : <PlayArrow />}
                  sx={{ color: 'white', bgcolor: 'rgba(255,255,255,0.2)' }}
                >
                  {isServiceRunning ? 'Stop Service' : 'Start Service'}
                </Button>
                
                <IconButton onClick={fetchServiceMetrics} sx={{ color: 'white' }}>
                  <Refresh />
                </IconButton>
              </Box>
            </Box>
          </CardContent>
        </Card>
      </Box>

      {/* Main Navigation Tabs */}
      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
        <Tabs value={activeTab} onChange={(e, v) => setActiveTab(v)} variant="scrollable" scrollButtons="auto">
          <Tab label="Service Metrics" icon={<Analytics />} />
          <Tab label="Live Streams" icon={<Timeline />} />
          <Tab label="Admin Config" icon={<Settings />} />
          <Tab label="Cost Analysis" icon={<MonetizationOn />} />
        </Tabs>
      </Box>

      {/* Tab Content */}
      {activeTab === 0 && (
        <Grid container spacing={3}>
          {/* Key Metrics Cards */}
          <Grid item xs={12} md={3}>
            <Card>
              <CardContent>
                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <Box>
                    <Typography color="text.secondary" gutterBottom>
                      Active Connections
                    </Typography>
                    <Typography variant="h4" color="primary">
                      {serviceMetrics.activeConnections}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      Websocket connections to providers
                    </Typography>
                  </Box>
                  <Router color="primary" fontSize="large" />
                </Box>
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} md={3}>
            <Card>
              <CardContent>
                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <Box>
                    <Typography color="text.secondary" gutterBottom>
                      Total Subscribers
                    </Typography>
                    <Typography variant="h4" color="success.main">
                      {serviceMetrics.totalSubscribers}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      User sessions receiving data
                    </Typography>
                  </Box>
                  <PeopleAlt color="success" fontSize="large" />
                </Box>
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} md={3}>
            <Card>
              <CardContent>
                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <Box>
                    <Typography color="text.secondary" gutterBottom>
                      Avg Latency
                    </Typography>
                    <Typography variant="h4" color="warning.main">
                      {serviceMetrics.dataLatency}ms
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      Data delivery latency
                    </Typography>
                  </Box>
                  <Speed color="warning" fontSize="large" />
                </Box>
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} md={3}>
            <Card>
              <CardContent>
                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <Box>
                    <Typography color="text.secondary" gutterBottom>
                      Error Rate
                    </Typography>
                    <Typography variant="h4" color={serviceMetrics.errorRate > 0.05 ? "error" : "success"}>
                      {(serviceMetrics.errorRate * 100).toFixed(2)}%
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      Connection failure rate
                    </Typography>
                  </Box>
                  <Assessment color={serviceMetrics.errorRate > 0.05 ? "error" : "success"} fontSize="large" />
                </Box>
              </CardContent>
            </Card>
          </Grid>

          {/* Charts */}
          <Grid item xs={12} md={6}>
            <Card>
              <CardHeader title="Connection Distribution" />
              <CardContent>
                <Box sx={{ height: 300 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={connectionMetricsData}
                        cx="50%"
                        cy="50%"
                        outerRadius={80}
                        dataKey="value"
                        label={({name, value}) => `${name}: ${value}`}
                      >
                        {connectionMetricsData.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={entry.color} />
                        ))}
                      </Pie>
                      <Tooltip />
                      <Legend />
                    </PieChart>
                  </ResponsiveContainer>
                </Box>
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} md={6}>
            <Card>
              <CardHeader title="Real-time Latency" />
              <CardContent>
                <Box sx={{ height: 300 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={latencyData}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="time" />
                      <YAxis label={{ value: 'Latency (ms)', angle: -90, position: 'insideLeft' }} />
                      <Tooltip />
                      <Legend />
                      <Line 
                        type="monotone" 
                        dataKey="latency" 
                        stroke="#1976d2" 
                        strokeWidth={2}
                        dot={{ fill: '#1976d2' }}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </Box>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      )}

      {activeTab === 1 && (
        <Grid container spacing={3}>
          {/* Symbol Subscription Management */}
          <Grid item xs={12}>
            <Card>
              <CardHeader 
                title="Symbol Subscriptions"
                subheader="Manage live data streams for specific symbols"
              />
              <CardContent>
                <Box sx={{ display: 'flex', gap: 2, mb: 3, alignItems: 'center' }}>
                  <TextField
                    label="Symbol"
                    value={newSymbol}
                    onChange={(e) => setNewSymbol(e.target.value.toUpperCase())}
                    placeholder="AAPL"
                    size="small"
                    sx={{ minWidth: 120 }}
                  />
                  
                  <Autocomplete
                    value={selectedProvider}
                    onChange={(e, v) => setSelectedProvider(v)}
                    options={adminConfig.providers}
                    size="small"
                    sx={{ minWidth: 120 }}
                    renderInput={(params) => <TextField {...params} label="Provider" />}
                  />
                  
                  <Button
                    variant="contained"
                    onClick={handleAddSymbol}
                    startIcon={<Add />}
                    disabled={!newSymbol.trim() || subscribedSymbols.has(newSymbol.toUpperCase())}
                  >
                    Subscribe
                  </Button>
                </Box>

                {/* Quick Symbol Selection */}
                <Box sx={{ mb: 3 }}>
                  <Typography variant="subtitle2" gutterBottom>Quick Subscribe:</Typography>
                  <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                    {POPULAR_SYMBOLS.map(symbol => (
                      <Chip
                        key={symbol}
                        label={symbol}
                        variant={subscribedSymbols.has(symbol) ? "filled" : "outlined"}
                        color={subscribedSymbols.has(symbol) ? "primary" : "default"}
                        onClick={() => subscribedSymbols.has(symbol) ? unsubscribeFromSymbol(symbol) : subscribeToSymbol(symbol)}
                        icon={subscribedSymbols.has(symbol) ? <CheckCircle /> : <Add />}
                      />
                    ))}
                  </Box>
                </Box>

                {/* Active Subscriptions */}
                <Typography variant="h6" gutterBottom>
                  Active Subscriptions ({subscribedSymbols.size})
                </Typography>
                
                {subscribedSymbols.size === 0 ? (
                  <Alert severity="info">
                    No active subscriptions. Add symbols to start receiving live data.
                  </Alert>
                ) : (
                  <TableContainer component={Paper} variant="outlined">
                    <Table size="small">
                      <TableHead>
                        <TableRow>
                          <TableCell>Symbol</TableCell>
                          <TableCell>Last Price</TableCell>
                          <TableCell>Change</TableCell>
                          <TableCell>Volume</TableCell>
                          <TableCell>Provider</TableCell>
                          <TableCell>Actions</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {Array.from(subscribedSymbols).map(symbol => {
                          const data = liveStreams.get(symbol) || {};
                          return (
                            <TableRow key={symbol}>
                              <TableCell>
                                <Typography variant="subtitle2" fontWeight="bold">
                                  {symbol}
                                </Typography>
                              </TableCell>
                              <TableCell>${data.price || '--'}</TableCell>
                              <TableCell>
                                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                                  {data.change > 0 ? <TrendingUp color="success" /> : <TrendingDown color="error" />}
                                  <Typography color={data.change > 0 ? 'success.main' : 'error.main'}>
                                    {data.change || '--'}%
                                  </Typography>
                                </Box>
                              </TableCell>
                              <TableCell>{data.volume?.toLocaleString() || '--'}</TableCell>
                              <TableCell>
                                <Chip label={data.provider || selectedProvider} size="small" />
                              </TableCell>
                              <TableCell>
                                <IconButton 
                                  size="small" 
                                  color="error"
                                  onClick={() => unsubscribeFromSymbol(symbol)}
                                >
                                  <Delete />
                                </IconButton>
                              </TableCell>
                            </TableRow>
                          );
                        })}
                      </TableBody>
                    </Table>
                  </TableContainer>
                )}
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      )}

      {activeTab === 2 && (
        <Grid container spacing={3}>
          <Grid item xs={12}>
            <Card>
              <CardHeader 
                title="Service Configuration"
                subheader="Admin controls for centralized live data service"
              />
              <CardContent>
                <Alert severity="info" sx={{ mb: 3 }}>
                  <Typography variant="subtitle2" gutterBottom>Centralized Architecture Benefits:</Typography>
                  <Typography variant="body2">
                    • Single API connection per symbol (not per user)<br/>
                    • Massive cost reduction vs per-user websockets<br/>
                    • Better performance through centralized caching<br/>
                    • Easier management and monitoring<br/>
                    • Can serve unlimited customers from same data streams
                  </Typography>
                </Alert>

                <Typography variant="h6" gutterBottom>Enabled Data Feeds</Typography>
                <Box sx={{ display: 'flex', gap: 2, mb: 3 }}>
                  {adminConfig.enabledFeeds.map(feed => (
                    <FormControlLabel
                      key={feed}
                      control={<Switch defaultChecked />}
                      label={feed.charAt(0).toUpperCase() + feed.slice(1)}
                    />
                  ))}
                </Box>

                <Typography variant="h6" gutterBottom>Data Providers</Typography>
                <Box sx={{ display: 'flex', gap: 2, mb: 3 }}>
                  {adminConfig.providers.map(provider => (
                    <Chip 
                      key={provider} 
                      label={provider.charAt(0).toUpperCase() + provider.slice(1)}
                      variant="filled"
                      color="primary"
                    />
                  ))}
                </Box>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      )}

      {activeTab === 3 && (
        <Grid container spacing={3}>
          <Grid item xs={12}>
            <Card>
              <CardHeader 
                title="Cost Analysis"
                subheader="Efficiency gains from centralized architecture"
              />
              <CardContent>
                <Alert severity="success" sx={{ mb: 3 }}>
                  <Typography variant="subtitle2" gutterBottom>Cost Optimization Achieved:</Typography>
                  <Typography variant="body2">
                    Previous architecture: Each user ran their own websockets (expensive, redundant)<br/>
                    New architecture: Single connection per symbol shared across all users (efficient, scalable)
                  </Typography>
                </Alert>

                <Grid container spacing={2}>
                  <Grid item xs={12} md={6}>
                    <Typography variant="h6" gutterBottom>Previous vs Current</Typography>
                    <TableContainer component={Paper} variant="outlined">
                      <Table size="small">
                        <TableBody>
                          <TableRow>
                            <TableCell>Active Symbols</TableCell>
                            <TableCell align="right">{subscribedSymbols.size}</TableCell>
                          </TableRow>
                          <TableRow>
                            <TableCell>Connected Users</TableCell>
                            <TableCell align="right">{serviceMetrics.totalSubscribers}</TableCell>
                          </TableRow>
                          <TableRow>
                            <TableCell>Old Model: Connections</TableCell>
                            <TableCell align="right" sx={{ color: 'error.main' }}>
                              {subscribedSymbols.size * serviceMetrics.totalSubscribers}
                            </TableCell>
                          </TableRow>
                          <TableRow>
                            <TableCell>New Model: Connections</TableCell>
                            <TableCell align="right" sx={{ color: 'success.main' }}>
                              {serviceMetrics.activeConnections}
                            </TableCell>
                          </TableRow>
                          <TableRow>
                            <TableCell><Typography variant="subtitle2">Efficiency Gain</Typography></TableCell>
                            <TableCell align="right" sx={{ color: 'success.main' }}>
                              <Typography variant="subtitle2">
                                {subscribedSymbols.size * serviceMetrics.totalSubscribers > 0 
                                  ? `${Math.round((1 - serviceMetrics.activeConnections / (subscribedSymbols.size * serviceMetrics.totalSubscribers || 1)) * 100)}%`
                                  : '0%'
                                } reduction
                              </Typography>
                            </TableCell>
                          </TableRow>
                        </TableBody>
                      </Table>
                    </TableContainer>
                  </Grid>
                </Grid>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      )}
    </Box>
  );
};

export default LiveDataCentralized;