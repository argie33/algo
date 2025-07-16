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
  Divider
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
  Info
} from '@mui/icons-material';
import { LineChart, Line, XAxis, YAxis, ResponsiveContainer, Tooltip as RechartsTooltip } from 'recharts';
import liveDataIntegration from '../services/liveDataIntegration';
import webSocketService from '../services/webSocketService';
import { useAuth } from '../contexts/AuthContext';


// Professional Live Data Management - Integrated with deployed WebSocket infrastructure

// Popular symbols for quick selection
const POPULAR_SYMBOLS = [
  'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'NVDA', 'META', 'NFLX',
  'SPY', 'QQQ', 'IWM', 'VTI', 'AMD', 'CRM', 'ORCL', 'ADBE'
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
  
  // UI state
  const [activeTab, setActiveTab] = useState(0);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [showSettings, setShowSettings] = useState(false);
  const [showIntegrationTest, setShowIntegrationTest] = useState(false);
  const [chartData, setChartData] = useState({});
  
  // Service initialization
  useEffect(() => {
    const initializeService = async () => {
      setIsInitializing(true);
      
      try {
        console.log('🚀 Initializing Live Data Integration...');
        
        // Initialize the integration service
        const initResult = await liveDataIntegration.initialize();
        
        if (initResult.success) {
          // Connect with user context
          const connectResult = await liveDataIntegration.connect(user?.id);
          
          if (connectResult.success) {
            console.log('✅ Live data service initialized and connected');
          }
        }
      } catch (error) {
        console.error('❌ Failed to initialize live data service:', error);
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

    // Update metrics periodically
    const metricsInterval = setInterval(() => {
      const metrics = liveDataIntegration.getMetrics();
      setIntegrationMetrics(metrics);
      setConnectionStatus(liveDataIntegration.getConnectionStatus());
    }, 2000);

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

  // Render connection status
  const renderConnectionStatus = () => (
    <Card sx={{ mb: 2 }}>
      <CardContent>
        <Box display="flex" justifyContent="space-between" alignItems="center">
          <Box display="flex" alignItems="center" gap={2}>
            <Badge 
              color={isConnected ? "success" : "error"} 
              variant="dot"
              sx={{ '& .MuiBadge-badge': { width: 12, height: 12 } }}
            >
              {isConnected ? <SignalWifi4Bar color="success" /> : <SignalWifiOff color="error" />}
            </Badge>
            <Box>
              <Typography variant="h6">
                Live Data Connection
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {isConnected ? 'Connected' : 'Disconnected'} • 
                {integrationMetrics?.data?.messagesReceived || 0} messages received • 
                {integrationMetrics?.connection?.latency || 0}ms latency
              </Typography>
            </Box>
          </Box>
          <Box display="flex" gap={1}>
            <Button
              variant={isConnected ? "outlined" : "contained"}
              color={isConnected ? "error" : "primary"}
              startIcon={isConnected ? <Stop /> : <PlayArrow />}
              onClick={toggleConnection}
              disabled={isInitializing}
            >
              {isInitializing ? 'Initializing...' : isConnected ? 'Disconnect' : 'Connect'}
            </Button>
            <Button
              variant="outlined"
              startIcon={<Assessment />}
              onClick={runIntegrationTest}
            >
              Test Integration
            </Button>
            <IconButton onClick={() => setShowSettings(true)}>
              <Settings />
            </IconButton>
          </Box>
        </Box>
        
        {/* Connection metrics */}
        <Box mt={2}>
          <Grid container spacing={2}>
            <Grid item xs={3}>
              <Box textAlign="center">
                <Typography variant="h4" color="primary">
                  {subscriptions.length}
                </Typography>
                <Typography variant="caption">Active Subscriptions</Typography>
              </Box>
            </Grid>
            <Grid item xs={3}>
              <Box textAlign="center">
                <Typography variant="h4" color="success.main">
                  {integrationMetrics?.data?.messagesReceived || 0}
                </Typography>
                <Typography variant="caption">Messages Received</Typography>
              </Box>
            </Grid>
            <Grid item xs={3}>
              <Box textAlign="center">
                <Typography variant="h4" color="info.main">
                  {integrationMetrics?.connection?.latency || 0}ms
                </Typography>
                <Typography variant="caption">Latency</Typography>
              </Box>
            </Grid>
            <Grid item xs={3}>
              <Box textAlign="center">
                <Typography variant="h4" color={integrationMetrics?.data?.errors > 0 ? "error.main" : "text.secondary"}>
                  {integrationMetrics?.data?.errors || 0}
                </Typography>
                <Typography variant="caption">Errors</Typography>
              </Box>
            </Grid>
          </Grid>
        </Box>
      </CardContent>
    </Card>
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
      <Typography variant="h4" gutterBottom>
        Live Market Data
      </Typography>
      <Typography variant="body1" color="text.secondary" gutterBottom>
        Professional real-time market data streaming with WebSocket connectivity
      </Typography>

      {/* Connection Status */}
      {renderConnectionStatus()}

      {/* Subscription Manager */}
      {renderSubscriptionManager()}

      {/* Tabs */}
      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 2 }}>
        <Tabs value={activeTab} onChange={(e, value) => setActiveTab(value)}>
          <Tab label="Data Table" icon={<Assessment />} iconPosition="start" />
          <Tab label="Real-time Charts" icon={<Timeline />} iconPosition="start" />
          <Tab label="Analytics" icon={<Analytics />} iconPosition="start" />
        </Tabs>
      </Box>

      {/* Tab Content */}
      {activeTab === 0 && renderMarketDataTable()}
      {activeTab === 1 && renderCharts()}
      {activeTab === 2 && (
        <Paper sx={{ p: 3 }}>
          <Typography variant="h6">Analytics Dashboard</Typography>
          <Typography variant="body2" color="text.secondary">
            Advanced analytics features coming soon...
          </Typography>
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
    </Box>
  );
};

export default LiveData;