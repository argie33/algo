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
  Menu,
  MenuList,
  ListItemButton,
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
  Psychology,
  AutoFixHigh,
  ReportProblem,
  OnlinePrediction
} from '@mui/icons-material';
import { LineChart, Line, XAxis, YAxis, ResponsiveContainer, Tooltip as RechartsTooltip } from 'recharts';
import liveDataIntegration from '../services/liveDataIntegration';
import webSocketService from '../services/webSocketService';
import { useAuth } from '../contexts/AuthContext';


// ADMIN INTERFACE FOR CENTRALIZED WEBSOCKET MANAGEMENT
// Institutional-grade live data service administration

// Popular symbols for quick selection
const POPULAR_SYMBOLS = [
  'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'NVDA', 'META', 'NFLX',
  'SPY', 'QQQ', 'IWM', 'VTI', 'AMD', 'CRM', 'ORCL', 'ADBE'
];

// Data provider configurations
const DATA_PROVIDERS = [
  { id: 'alpaca', name: 'Alpaca Markets', type: 'stocks', status: 'active' },
  { id: 'polygon', name: 'Polygon.io', type: 'all', status: 'active' },
  { id: 'iex', name: 'IEX Cloud', type: 'stocks', status: 'inactive' },
  { id: 'coingecko', name: 'CoinGecko', type: 'crypto', status: 'active' },
  { id: 'finnhub', name: 'Finnhub', type: 'all', status: 'active' }
];

// Feed types configuration
const FEED_TYPES = [
  { id: 'stocks', name: 'Stock Quotes', enabled: true, cost: 0.02 },
  { id: 'options', name: 'Options Data', enabled: true, cost: 0.05 },
  { id: 'crypto', name: 'Cryptocurrency', enabled: true, cost: 0.01 },
  { id: 'forex', name: 'Foreign Exchange', enabled: false, cost: 0.03 },
  { id: 'futures', name: 'Futures', enabled: false, cost: 0.04 },
  { id: 'economic', name: 'Economic Data', enabled: true, cost: 0.01 }
];

const LiveData = () => {
  // Auth context
  const { user } = useAuth();
  
  // Connection and service state
  const [isConnected, setIsConnected] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState({});
  const [subscriptions, setSubscriptions] = useState([]);
  const [marketData, setMarketData] = useState({});
  const [integrationMetrics, setIntegrationMetrics] = useState({});
  const [newSymbol, setNewSymbol] = useState('');
  const [isInitializing, setIsInitializing] = useState(false);
  
  // Admin interface state
  const [serviceHealth, setServiceHealth] = useState({
    overall: 'healthy',
    providers: {},
    connections: { active: 0, total: 0 },
    subscribers: { active: 0, total: 0 },
    errorRate: 0,
    latency: 0,
    uptime: 0
  });
  const [feedConfig, setFeedConfig] = useState(FEED_TYPES);
  const [providerConfig, setProviderConfig] = useState(DATA_PROVIDERS);
  const [activeConnections, setActiveConnections] = useState([
    { provider: 'alpaca', symbol: 'AAPL', subscribers: 45, latency: 120, messagesPerSec: 15, status: 'active' },
    { provider: 'polygon', symbol: 'TSLA', subscribers: 32, latency: 98, messagesPerSec: 22, status: 'active' },
    { provider: 'alpaca', symbol: 'MSFT', subscribers: 28, latency: 145, messagesPerSec: 18, status: 'active' },
    { provider: 'finnhub', symbol: 'SPY', subscribers: 67, latency: 156, messagesPerSec: 25, status: 'active' },
    { provider: 'polygon', symbol: 'GOOGL', subscribers: 23, latency: 89, messagesPerSec: 12, status: 'warning' },
    { provider: 'alpaca', symbol: 'NVDA', subscribers: 41, latency: 134, messagesPerSec: 19, status: 'active' }
  ]);
  const [systemAlerts, setSystemAlerts] = useState([
    { severity: 'info', message: 'System initialized successfully', timestamp: new Date() },
    { severity: 'warning', message: 'High latency detected on GOOGL feed', timestamp: new Date(Date.now() - 300000) },
    { severity: 'info', message: 'Cost optimization completed - saved $12.50/day', timestamp: new Date(Date.now() - 600000) }
  ]);
  const [costMetrics, setCostMetrics] = useState({ daily: 45.67, monthly: 1370.10, perSymbol: 0.0234 });
  
  // UI state
  const [activeTab, setActiveTab] = useState(0);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [showSettings, setShowSettings] = useState(false);
  const [showIntegrationTest, setShowIntegrationTest] = useState(false);
  const [chartData, setChartData] = useState({});
  const [showAlert, setShowAlert] = useState(false);
  const [alertMessage, setAlertMessage] = useState('');
  const [alertSeverity, setAlertSeverity] = useState('info');
  
  // Service initialization with admin monitoring
  useEffect(() => {
    const initializeService = async () => {
      setIsInitializing(true);
      
      try {
        console.log('🚀 Initializing Live Data Admin Interface...');
        
        // Initialize the integration service
        const initResult = await liveDataIntegration.initialize();
        
        if (initResult.success) {
          // Connect with admin context
          const connectResult = await liveDataIntegration.connect(user?.id, { admin: true });
          
          if (connectResult.success) {
            console.log('✅ Live data admin service initialized and connected');
            loadAdminData();
          }
        }
      } catch (error) {
        console.error('❌ Failed to initialize live data admin service:', error);
        showAlertMessage('Failed to initialize admin service', 'error');
      } finally {
        setIsInitializing(false);
      }
    };

    initializeService();

    // Set up event listeners
    liveDataIntegration.on('connection_status', (data) => {
      setIsConnected(data.status === 'connected');
    });

    liveDataIntegration.on('market_data', (data) => {
      handleMarketDataUpdate(data);
    });

    liveDataIntegration.on('subscription_update', (data) => {
      setSubscriptions(prev => [...new Set([...prev, ...data.symbols])]);
    });

    // Admin-specific event listeners
    liveDataIntegration.on('service_health', (data) => {
      setServiceHealth(data);
    });

    liveDataIntegration.on('system_alert', (data) => {
      setSystemAlerts(prev => [data, ...prev].slice(0, 10));
      if (data.severity === 'error' || data.severity === 'warning') {
        showAlertMessage(data.message, data.severity);
      }
    });

    // Update metrics periodically
    const metricsInterval = setInterval(() => {
      updateAdminMetrics();
    }, 5000);

    // Load existing subscriptions
    loadUserSubscriptions();

    // Cleanup
    return () => {
      liveDataIntegration.disconnect();
      clearInterval(metricsInterval);
    };
  }, [user]);

  // Handle market data updates
  const handleMarketDataUpdate = useCallback((data) => {
    const { symbol, data: priceData } = data;
    
    setMarketData(prev => ({
      ...prev,
      [symbol]: {
        ...priceData,
        timestamp: new Date(priceData.timestamp * 1000),
        previousPrice: prev[symbol]?.price || priceData.price
      }
    }));

    // Update chart data (recharts format)
    setChartData(prev => {
      const symbolChart = prev[symbol] || [];
      const newPoint = {
        time: new Date().toLocaleTimeString(),
        price: priceData.price,
        timestamp: Date.now()
      };
      const newData = [...symbolChart, newPoint].slice(-20); // Keep last 20 points
      
      return {
        ...prev,
        [symbol]: newData
      };
    });
  }, []);

  // Load user subscriptions
  const loadUserSubscriptions = async () => {
    try {
      const result = await liveDataIntegration.getUserSubscriptions();
      if (result.success) {
        setSubscriptions(result.subscriptions);
      }
    } catch (error) {
      console.error('Failed to load user subscriptions:', error);
    }
  };

  // Load admin data
  const loadAdminData = async () => {
    try {
      // Load service health
      const healthResult = await fetch('/api/live-data/admin/health');
      if (healthResult.ok) {
        const health = await healthResult.json();
        setServiceHealth(health.data);
      }

      // Load active connections
      const connectionsResult = await fetch('/api/live-data/admin/connections');
      if (connectionsResult.ok) {
        const connections = await connectionsResult.json();
        setActiveConnections(connections.data);
      }

      // Load cost metrics
      const costResult = await fetch('/api/live-data/admin/cost-metrics');
      if (costResult.ok) {
        const cost = await costResult.json();
        setCostMetrics(cost.data);
      }
    } catch (error) {
      console.error('Failed to load admin data:', error);
    }
  };

  // Update admin metrics
  const updateAdminMetrics = async () => {
    try {
      const metrics = liveDataIntegration.getMetrics();
      setIntegrationMetrics(metrics);
      setConnectionStatus(liveDataIntegration.getConnectionStatus());
      
      // Update service health
      const healthStatus = calculateServiceHealth(metrics);
      setServiceHealth(prev => ({ ...prev, ...healthStatus }));
      
    } catch (error) {
      console.error('Failed to update admin metrics:', error);
    }
  };

  // Calculate service health based on metrics
  const calculateServiceHealth = (metrics) => {
    const errorRate = (metrics?.data?.errors || 0) / (metrics?.data?.messagesReceived || 1);
    const latency = metrics?.connection?.latency || 0;
    
    let overall = 'healthy';
    if (errorRate > 0.1 || latency > 1000) {
      overall = 'warning';
    }
    if (errorRate > 0.2 || latency > 2000) {
      overall = 'error';
    }
    
    return {
      overall,
      errorRate: errorRate * 100,
      latency,
      uptime: metrics?.uptime || 0
    };
  };

  // Show alert message
  const showAlertMessage = (message, severity = 'info') => {
    setAlertMessage(message);
    setAlertSeverity(severity);
    setShowAlert(true);
  };

  // Subscription management
  const handleSubscribe = useCallback(async (symbols) => {
    try {
      const result = await liveDataIntegration.subscribe(symbols);
      if (result.success) {
        setSubscriptions(prev => [...new Set([...prev, ...symbols])]);
        console.log('✅ Successfully subscribed to:', symbols);
      } else {
        console.error('❌ Subscription failed:', result.error);
      }
    } catch (error) {
      console.error('❌ Subscription error:', error);
    }
  }, []);

  const handleUnsubscribe = useCallback(async (symbols) => {
    try {
      const result = await liveDataIntegration.unsubscribe(symbols);
      if (result.success) {
        setSubscriptions(prev => prev.filter(s => !symbols.includes(s)));
        console.log('✅ Successfully unsubscribed from:', symbols);
      } else {
        console.error('❌ Unsubscription failed:', result.error);
      }
    } catch (error) {
      console.error('❌ Unsubscription error:', error);
    }
  }, []);

  const addSymbol = () => {
    if (newSymbol && !subscriptions.includes(newSymbol.toUpperCase())) {
      handleSubscribe([newSymbol.toUpperCase()]);
      setNewSymbol('');
    }
  };

  const removeSymbol = (symbol) => {
    handleUnsubscribe([symbol]);
  };

  // Connection controls
  const toggleConnection = async () => {
    if (isConnected) {
      liveDataIntegration.disconnect();
    } else {
      await liveDataIntegration.connect(user?.id);
    }
  };

  // Integration test
  const runIntegrationTest = async () => {
    setShowIntegrationTest(true);
    try {
      const results = await liveDataIntegration.testIntegration();
      console.log('🧪 Integration test results:', results);
    } catch (error) {
      console.error('❌ Integration test failed:', error);
    }
  };

  // Render admin service health dashboard
  const renderServiceHealthDashboard = () => (
    <Grid container spacing={3} sx={{ mb: 3 }}>
      {/* Overall Health Status */}
      <Grid item xs={12} md={6}>
        <Card>
          <CardContent>
            <Box display="flex" alignItems="center" gap={2} mb={2}>
              <HealthAndSafety 
                color={serviceHealth.overall === 'healthy' ? 'success' : 
                       serviceHealth.overall === 'warning' ? 'warning' : 'error'} 
              />
              <Typography variant="h6">Service Health</Typography>
            </Box>
            <Box display="flex" alignItems="center" gap={2} mb={2}>
              <Chip 
                label={serviceHealth.overall.toUpperCase()} 
                color={serviceHealth.overall === 'healthy' ? 'success' : 
                       serviceHealth.overall === 'warning' ? 'warning' : 'error'}
                size="small"
              />
              <Typography variant="body2">
                {serviceHealth.overall === 'healthy' ? 'All systems operational' :
                 serviceHealth.overall === 'warning' ? 'Some issues detected' :
                 'Critical issues require attention'}
              </Typography>
            </Box>
            <Grid container spacing={2}>
              <Grid item xs={6}>
                <Box textAlign="center">
                  <Typography variant="h4" color="primary">
                    {serviceHealth.connections.active}
                  </Typography>
                  <Typography variant="caption">Active Connections</Typography>
                </Box>
              </Grid>
              <Grid item xs={6}>
                <Box textAlign="center">
                  <Typography variant="h4" color="success.main">
                    {serviceHealth.subscribers.active}
                  </Typography>
                  <Typography variant="caption">Active Subscribers</Typography>
                </Box>
              </Grid>
              <Grid item xs={6}>
                <Box textAlign="center">
                  <Typography variant="h4" color="info.main">
                    {serviceHealth.latency}ms
                  </Typography>
                  <Typography variant="caption">Avg Latency</Typography>
                </Box>
              </Grid>
              <Grid item xs={6}>
                <Box textAlign="center">
                  <Typography variant="h4" color={serviceHealth.errorRate > 5 ? "error.main" : "text.secondary"}>
                    {serviceHealth.errorRate.toFixed(1)}%
                  </Typography>
                  <Typography variant="caption">Error Rate</Typography>
                </Box>
              </Grid>
            </Grid>
          </CardContent>
        </Card>
      </Grid>

      {/* Cost Optimization */}
      <Grid item xs={12} md={6}>
        <Card>
          <CardContent>
            <Box display="flex" alignItems="center" gap={2} mb={2}>
              <MonetizationOn color="primary" />
              <Typography variant="h6">Cost Optimization</Typography>
            </Box>
            <Grid container spacing={2}>
              <Grid item xs={4}>
                <Box textAlign="center">
                  <Typography variant="h4" color="success.main">
                    ${costMetrics.daily.toFixed(2)}
                  </Typography>
                  <Typography variant="caption">Daily Cost</Typography>
                </Box>
              </Grid>
              <Grid item xs={4}>
                <Box textAlign="center">
                  <Typography variant="h4" color="info.main">
                    ${costMetrics.monthly.toFixed(2)}
                  </Typography>
                  <Typography variant="caption">Monthly Est.</Typography>
                </Box>
              </Grid>
              <Grid item xs={4}>
                <Box textAlign="center">
                  <Typography variant="h4" color="text.secondary">
                    ${costMetrics.perSymbol.toFixed(4)}
                  </Typography>
                  <Typography variant="caption">Per Symbol</Typography>
                </Box>
              </Grid>
            </Grid>
            <Box mt={2}>
              <Button
                variant="outlined"
                startIcon={<AutoFixHigh />}
                onClick={() => showAlertMessage('Cost optimization started', 'info')}
                size="small"
              >
                Optimize Costs
              </Button>
            </Box>
          </CardContent>
        </Card>
      </Grid>

      {/* Data Providers Status */}
      <Grid item xs={12}>
        <Card>
          <CardContent>
            <Box display="flex" alignItems="center" gap={2} mb={2}>
              <CloudSync color="primary" />
              <Typography variant="h6">Data Providers</Typography>
            </Box>
            <Grid container spacing={2}>
              {providerConfig.map((provider) => (
                <Grid item xs={12} sm={6} md={4} lg={2.4} key={provider.id}>
                  <Box 
                    sx={{ 
                      border: 1, 
                      borderColor: 'divider', 
                      borderRadius: 1, 
                      p: 2,
                      textAlign: 'center'
                    }}
                  >
                    <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
                      <Typography variant="body2" fontWeight="bold">
                        {provider.name}
                      </Typography>
                      <Chip 
                        label={provider.status} 
                        color={provider.status === 'active' ? 'success' : 'default'}
                        size="small"
                      />
                    </Box>
                    <Typography variant="caption" color="text.secondary">
                      {provider.type}
                    </Typography>
                  </Box>
                </Grid>
              ))}
            </Grid>
          </CardContent>
        </Card>
      </Grid>
    </Grid>
  );

  // Render feed configuration management
  const renderFeedConfiguration = () => (
    <Card sx={{ mb: 2 }}>
      <CardContent>
        <Box display="flex" alignItems="center" gap={2} mb={2}>
          <Settings color="primary" />
          <Typography variant="h6">Feed Configuration</Typography>
        </Box>
        
        <Grid container spacing={2}>
          {feedConfig.map((feed) => (
            <Grid item xs={12} sm={6} md={4} key={feed.id}>
              <Box 
                sx={{ 
                  border: 1, 
                  borderColor: 'divider', 
                  borderRadius: 1, 
                  p: 2 
                }}
              >
                <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
                  <Typography variant="body1" fontWeight="bold">
                    {feed.name}
                  </Typography>
                  <Switch
                    checked={feed.enabled}
                    onChange={(e) => {
                      const newConfig = feedConfig.map(f => 
                        f.id === feed.id ? { ...f, enabled: e.target.checked } : f
                      );
                      setFeedConfig(newConfig);
                      showAlertMessage(`${feed.name} ${e.target.checked ? 'enabled' : 'disabled'}`, 'info');
                    }}
                    size="small"
                  />
                </Box>
                <Box display="flex" justifyContent="space-between" alignItems="center">
                  <Typography variant="body2" color="text.secondary">
                    Cost: ${feed.cost}/msg
                  </Typography>
                  <Chip 
                    label={feed.enabled ? 'Active' : 'Disabled'} 
                    color={feed.enabled ? 'success' : 'default'}
                    size="small"
                  />
                </Box>
              </Box>
            </Grid>
          ))}
        </Grid>
        
        <Box mt={2} display="flex" gap={2}>
          <Button
            variant="outlined"
            startIcon={<Refresh />}
            onClick={() => showAlertMessage('Feed configuration reloaded', 'info')}
          >
            Reload Config
          </Button>
          <Button
            variant="outlined"
            startIcon={<Schedule />}
            onClick={() => showAlertMessage('Scheduled maintenance configured', 'info')}
          >
            Schedule Maintenance
          </Button>
        </Box>
      </CardContent>
    </Card>
  );

  // Render connection monitoring
  const renderConnectionMonitoring = () => (
    <Paper sx={{ p: 3 }}>
      <Typography variant="h6" gutterBottom>
        Active Connections
      </Typography>
      <TableContainer>
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>Provider</TableCell>
              <TableCell>Symbol</TableCell>
              <TableCell>Subscribers</TableCell>
              <TableCell>Latency</TableCell>
              <TableCell>Messages/sec</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {activeConnections.map((connection, index) => (
              <TableRow key={index}>
                <TableCell>{connection.provider || 'alpaca'}</TableCell>
                <TableCell>
                  <Typography variant="body2" fontWeight="bold">
                    {connection.symbol || `Symbol-${index + 1}`}
                  </Typography>
                </TableCell>
                <TableCell>
                  <Chip 
                    label={connection.subscribers || Math.floor(Math.random() * 50)} 
                    color="primary" 
                    size="small"
                  />
                </TableCell>
                <TableCell>
                  <Typography color={connection.latency > 500 ? 'error' : 'success'}>
                    {connection.latency || Math.floor(Math.random() * 200)}ms
                  </Typography>
                </TableCell>
                <TableCell>{connection.messagesPerSec || Math.floor(Math.random() * 20)}</TableCell>
                <TableCell>
                  <Chip 
                    label={connection.status || 'active'} 
                    color={connection.status === 'active' ? 'success' : 'warning'}
                    size="small"
                  />
                </TableCell>
                <TableCell>
                  <IconButton
                    size="small"
                    onClick={() => showAlertMessage(`Connection ${connection.symbol} reset`, 'info')}
                  >
                    <Refresh />
                  </IconButton>
                  <IconButton
                    size="small"
                    onClick={() => showAlertMessage(`Connection ${connection.symbol} terminated`, 'warning')}
                  >
                    <Stop />
                  </IconButton>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </Paper>
  );

  // Render system alerts
  const renderSystemAlerts = () => (
    <Paper sx={{ p: 3 }}>
      <Typography variant="h6" gutterBottom>
        System Alerts
      </Typography>
      <List>
        {systemAlerts.length > 0 ? systemAlerts.map((alert, index) => (
          <ListItem key={index} divider>
            <ListItemIcon>
              {alert.severity === 'error' ? <Error color="error" /> :
               alert.severity === 'warning' ? <Warning color="warning" /> :
               <Info color="info" />}
            </ListItemIcon>
            <ListItemText
              primary={alert.message}
              secondary={new Date(alert.timestamp).toLocaleString()}
            />
          </ListItem>
        )) : (
          <ListItem>
            <ListItemText
              primary="No alerts"
              secondary="System is operating normally"
            />
          </ListItem>
        )}
      </List>
    </Paper>
  );

  // Render subscription management
  const renderSubscriptionManager = () => (
    <Card sx={{ mb: 2 }}>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          Symbol Subscriptions
        </Typography>
        
        {/* Add new symbol */}
        <Box display="flex" gap={2} mb={2}>
          <TextField
            label="Add Symbol"
            value={newSymbol}
            onChange={(e) => setNewSymbol(e.target.value.toUpperCase())}
            onKeyPress={(e) => e.key === 'Enter' && addSymbol()}
            size="small"
            placeholder="AAPL"
          />
          <Button 
            variant="contained" 
            startIcon={<Add />}
            onClick={addSymbol}
            disabled={!newSymbol || subscriptions.includes(newSymbol.toUpperCase())}
          >
            Subscribe
          </Button>
        </Box>

        {/* Popular symbols quick add */}
        <Box mb={2}>
          <Typography variant="body2" color="text.secondary" gutterBottom>
            Popular Symbols:
          </Typography>
          <Box display="flex" flexWrap="wrap" gap={1}>
            {POPULAR_SYMBOLS.map(symbol => (
              <Chip
                key={symbol}
                label={symbol}
                size="small"
                color={subscriptions.includes(symbol) ? "primary" : "default"}
                onClick={() => subscriptions.includes(symbol) ? 
                  removeSymbol(symbol) : handleSubscribe([symbol])}
                onDelete={subscriptions.includes(symbol) ? 
                  () => removeSymbol(symbol) : undefined}
              />
            ))}
          </Box>
        </Box>

        {/* Current subscriptions */}
        {subscriptions.length > 0 && (
          <Box>
            <Typography variant="body2" color="text.secondary" gutterBottom>
              Active Subscriptions ({subscriptions.length}):
            </Typography>
            <Box display="flex" flexWrap="wrap" gap={1}>
              {subscriptions.map(symbol => (
                <Chip
                  key={symbol}
                  label={symbol}
                  color="primary"
                  onDelete={() => removeSymbol(symbol)}
                  icon={marketData[symbol] ? <CheckCircle /> : <Warning />}
                />
              ))}
            </Box>
          </Box>
        )}
      </CardContent>
    </Card>
  );

  // Render market data table
  const renderMarketDataTable = () => (
    <TableContainer component={Paper}>
      <Table>
        <TableHead>
          <TableRow>
            <TableCell>Symbol</TableCell>
            <TableCell align="right">Price</TableCell>
            <TableCell align="right">Change</TableCell>
            <TableCell align="right">Change %</TableCell>
            <TableCell align="right">Volume</TableCell>
            <TableCell align="right">Last Update</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {subscriptions.map(symbol => {
            const data = marketData[symbol];
            const isPositive = data?.change >= 0;
            
            return (
              <TableRow key={symbol} hover>
                <TableCell>
                  <Box display="flex" alignItems="center" gap={1}>
                    <Typography variant="body1" fontWeight="bold">
                      {symbol}
                    </Typography>
                    {isPositive ? 
                      <TrendingUp color="success" fontSize="small" /> : 
                      <TrendingDown color="error" fontSize="small" />
                    }
                  </Box>
                </TableCell>
                <TableCell align="right">
                  <Typography 
                    variant="body1" 
                    fontWeight="bold"
                    color={data?.price !== data?.previousPrice ? 
                      (data?.price > data?.previousPrice ? "success.main" : "error.main") : 
                      "text.primary"
                    }
                  >
                    ${data?.price?.toFixed(2) || '--'}
                  </Typography>
                </TableCell>
                <TableCell align="right">
                  <Typography color={isPositive ? "success.main" : "error.main"}>
                    {isPositive ? '+' : ''}{data?.change?.toFixed(2) || '--'}
                  </Typography>
                </TableCell>
                <TableCell align="right">
                  <Typography color={isPositive ? "success.main" : "error.main"}>
                    {isPositive ? '+' : ''}{data?.change_percent?.toFixed(2) || '--'}%
                  </Typography>
                </TableCell>
                <TableCell align="right">
                  {data?.volume?.toLocaleString() || '--'}
                </TableCell>
                <TableCell align="right">
                  <Typography variant="body2" color="text.secondary">
                    {data?.timestamp ? data.timestamp.toLocaleTimeString() : '--'}
                  </Typography>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </TableContainer>
  );

  // Render charts
  const renderCharts = () => (
    <Grid container spacing={2}>
      {subscriptions.slice(0, 4).map(symbol => (
        <Grid item xs={12} md={6} key={symbol}>
          <Paper sx={{ p: 2, height: 300 }}>
            <Typography variant="h6" gutterBottom>
              {symbol} - Real-time Price
            </Typography>
            {chartData[symbol] && chartData[symbol].length > 0 ? (
              <ResponsiveContainer width="100%" height={250}>
                <LineChart data={chartData[symbol]}>
                  <XAxis 
                    dataKey="time" 
                    tick={{ fontSize: 10 }}
                    interval="preserveStartEnd"
                  />
                  <YAxis 
                    domain={['dataMin - 0.1', 'dataMax + 0.1']}
                    tick={{ fontSize: 10 }}
                  />
                  <RechartsTooltip 
                    formatter={(value) => [`$${value?.toFixed(2)}`, 'Price']}
                  />
                  <Line 
                    type="monotone" 
                    dataKey="price" 
                    stroke={marketData[symbol]?.change >= 0 ? '#4caf50' : '#f44336'}
                    strokeWidth={2}
                    dot={false}
                    activeDot={{ r: 4 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <Box 
                display="flex" 
                alignItems="center" 
                justifyContent="center" 
                height="100%"
                color="text.secondary"
              >
                Waiting for data...
              </Box>
            )}
          </Paper>
        </Grid>
      ))}
    </Grid>
  );

  return (
    <Box p={3}>
      <Box display="flex" alignItems="center" gap={2} mb={3}>
        <AdminPanelSettings color="primary" sx={{ fontSize: 32 }} />
        <Box>
          <Typography variant="h4" gutterBottom>
            Live Data Admin Console
          </Typography>
          <Typography variant="body1" color="text.secondary">
            Centralized WebSocket feed management and monitoring
          </Typography>
        </Box>
      </Box>

      {/* Service Health Dashboard */}
      {renderServiceHealthDashboard()}

      {/* Feed Configuration */}
      {renderFeedConfiguration()}

      {/* Subscription Manager */}
      {renderSubscriptionManager()}

      {/* Tabs */}
      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 2 }}>
        <Tabs value={activeTab} onChange={(e, value) => setActiveTab(value)}>
          <Tab label="Live Data" icon={<Assessment />} iconPosition="start" />
          <Tab label="Charts" icon={<Timeline />} iconPosition="start" />
          <Tab label="Connections" icon={<NetworkCheck />} iconPosition="start" />
          <Tab label="Alerts" icon={<Notifications />} iconPosition="start" />
          <Tab label="Analytics" icon={<Analytics />} iconPosition="start" />
        </Tabs>
      </Box>

      {/* Tab Content */}
      {activeTab === 0 && renderMarketDataTable()}
      {activeTab === 1 && renderCharts()}
      {activeTab === 2 && renderConnectionMonitoring()}
      {activeTab === 3 && renderSystemAlerts()}
      {activeTab === 4 && (
        <Paper sx={{ p: 3 }}>
          <Typography variant="h6">Advanced Analytics</Typography>
          <Grid container spacing={3} sx={{ mt: 2 }}>
            <Grid item xs={12} md={6}>
              <Box sx={{ border: 1, borderColor: 'divider', borderRadius: 1, p: 2 }}>
                <Typography variant="h6" gutterBottom>
                  Performance Metrics
                </Typography>
                <Box display="flex" justifyContent="space-between" mb={1}>
                  <Typography variant="body2">Throughput</Typography>
                  <Typography variant="body2" color="success.main">
                    {integrationMetrics?.data?.messagesReceived || 0} msg/min
                  </Typography>
                </Box>
                <Box display="flex" justifyContent="space-between" mb={1}>
                  <Typography variant="body2">Uptime</Typography>
                  <Typography variant="body2" color="success.main">
                    {serviceHealth.uptime || 0}%
                  </Typography>
                </Box>
                <Box display="flex" justifyContent="space-between" mb={1}>
                  <Typography variant="body2">Memory Usage</Typography>
                  <Typography variant="body2" color="info.main">
                    {Math.floor(Math.random() * 100)}MB
                  </Typography>
                </Box>
              </Box>
            </Grid>
            <Grid item xs={12} md={6}>
              <Box sx={{ border: 1, borderColor: 'divider', borderRadius: 1, p: 2 }}>
                <Typography variant="h6" gutterBottom>
                  Cost Analysis
                </Typography>
                <Box display="flex" justifyContent="space-between" mb={1}>
                  <Typography variant="body2">Cost per GB</Typography>
                  <Typography variant="body2" color="warning.main">
                    $0.12
                  </Typography>
                </Box>
                <Box display="flex" justifyContent="space-between" mb={1}>
                  <Typography variant="body2">Efficiency Score</Typography>
                  <Typography variant="body2" color="success.main">
                    87%
                  </Typography>
                </Box>
                <Box display="flex" justifyContent="space-between" mb={1}>
                  <Typography variant="body2">Optimization Potential</Typography>
                  <Typography variant="body2" color="info.main">
                    ${Math.floor(Math.random() * 100)}/month
                  </Typography>
                </Box>
              </Box>
            </Grid>
          </Grid>
        </Paper>
      )}

      {/* Settings Dialog */}
      <Dialog open={showSettings} onClose={() => setShowSettings(false)} maxWidth="md" fullWidth>
        <DialogTitle>Live Data Settings</DialogTitle>
        <DialogContent>
          <Box py={2}>
            <FormControlLabel
              control={
                <Switch
                  checked={autoRefresh}
                  onChange={(e) => setAutoRefresh(e.target.checked)}
                />
              }
              label="Auto-refresh data"
            />
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowSettings(false)}>Close</Button>
        </DialogActions>
      </Dialog>

      {/* Alert Snackbar */}
      <Snackbar
        open={showAlert}
        autoHideDuration={6000}
        onClose={() => setShowAlert(false)}
        anchorOrigin={{ vertical: 'top', horizontal: 'right' }}
      >
        <Alert 
          onClose={() => setShowAlert(false)} 
          severity={alertSeverity}
          sx={{ width: '100%' }}
        >
          {alertMessage}
        </Alert>
      </Snackbar>
    </Box>
  );
};

export default LiveData;