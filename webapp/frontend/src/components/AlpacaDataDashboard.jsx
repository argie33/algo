import React, { useState, useEffect, useCallback } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Grid,
  Button,
  TextField,
  Chip,
  Alert,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Tabs,
  Tab,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  IconButton,
  Tooltip,
  Switch,
  FormControlLabel,
  Divider,
  LinearProgress,
  Badge
} from '@mui/material';
import {
  TrendingUp,
  TrendingDown,
  Circle,
  Wifi,
  WifiOff,
  Add,
  Delete,
  Refresh,
  ShowChart,
  Speed,
  NewReleases,
  CurrencyBitcoin,
  Timeline,
  PlayArrow,
  Stop,
  Settings
} from '@mui/icons-material';
import simpleAlpacaWebSocket from '../services/simpleAlpacaWebSocket';

const AlpacaDataDashboard = () => {
  // Connection state
  const [connectionStatus, setConnectionStatus] = useState('DISCONNECTED');
  const [error, setError] = useState(null);
  const [metrics, setMetrics] = useState({});
  
  // Data state
  const [marketData, setMarketData] = useState({});
  const [subscriptions, setSubscriptions] = useState([]);
  const [availableFeeds, setAvailableFeeds] = useState(null);
  
  // UI state
  const [activeTab, setActiveTab] = useState(0);
  const [newSymbol, setNewSymbol] = useState('');
  const [selectedDataType, setSelectedDataType] = useState('quotes');
  const [selectedFrequency, setSelectedFrequency] = useState('1Min');
  const [autoReconnect, setAutoReconnect] = useState(true);
  const [logs, setLogs] = useState([]);

  // Add log entry
  const addLog = useCallback((message, type = 'info') => {
    const timestamp = new Date().toLocaleTimeString();
    setLogs(prev => [...prev.slice(-29), { timestamp, message, type }]);
  }, []);

  // Setup event listeners
  useEffect(() => {
    const handleConnected = () => {
      setConnectionStatus('CONNECTED');
      setError(null);
      addLog('🟢 Connected to Alpaca WebSocket', 'success');
    };

    const handleDisconnected = () => {
      setConnectionStatus('DISCONNECTED');
      addLog('🔴 Disconnected from Alpaca WebSocket', 'warning');
    };

    const handleConnecting = () => {
      setConnectionStatus('CONNECTING');
      addLog('🔄 Connecting to Alpaca WebSocket...', 'info');
    };

    const handleError = (error) => {
      setError(error.message || 'Connection error');
      addLog(`❌ Error: ${error.message}`, 'error');
    };

    const handleMarketData = ({ symbol, dataType, data }) => {
      setMarketData(prev => ({
        ...prev,
        [`${symbol}:${dataType}`]: {
          symbol,
          dataType,
          ...data,
          lastUpdate: new Date().toLocaleTimeString()
        }
      }));
      
      // Different log messages for different data types
      if (dataType === 'quotes') {
        addLog(`📊 ${symbol} Quote: Bid $${data.bid}, Ask $${data.ask}`, 'info');
      } else if (dataType === 'trades') {
        addLog(`💰 ${symbol} Trade: $${data.price} (${data.size} shares)`, 'info');
      } else if (dataType === 'bars') {
        addLog(`📈 ${symbol} Bar: O$${data.open} H$${data.high} L$${data.low} C$${data.close}`, 'info');
      } else if (dataType === 'news') {
        addLog(`📰 ${symbol} News: ${data.headline}`, 'info');
      }
    };

    const handleSubscribed = (data) => {
      addLog(`✅ Subscribed to ${data.dataType} for ${data.symbols?.join(', ')}`, 'success');
      refreshSubscriptions();
    };

    const handleUnsubscribed = (data) => {
      addLog(`🔄 Unsubscribed from ${data.subscriptionId}`, 'info');
      refreshSubscriptions();
    };

    const handleAvailableFeeds = (feeds) => {
      setAvailableFeeds(feeds);
      addLog(`📡 Available feeds loaded: ${Object.keys(feeds).join(', ')}`, 'info');
    };

    const handleSubscriptionsList = (subscriptions) => {
      setSubscriptions(subscriptions);
    };

    // Subscribe to events
    simpleAlpacaWebSocket.on('connected', handleConnected);
    simpleAlpacaWebSocket.on('disconnected', handleDisconnected);
    simpleAlpacaWebSocket.on('error', handleError);
    simpleAlpacaWebSocket.on('data', ({ type, data }) => {
      handleMarketData({ symbol: data.symbol, dataType: type, data });
    });
    simpleAlpacaWebSocket.on('subscribed', handleSubscribed);

    // Set initial state
    setConnectionStatus(simpleAlpacaWebSocket.isConnected ? 'CONNECTED' : 'DISCONNECTED');
    setMarketData(simpleAlpacaWebSocket.getAllData());

    // Cleanup
    return () => {
      simpleAlpacaWebSocket.off('connected', handleConnected);
      simpleAlpacaWebSocket.off('disconnected', handleDisconnected);
      simpleAlpacaWebSocket.off('error', handleError);
      simpleAlpacaWebSocket.off('data', ({ type, data }) => {
        handleMarketData({ symbol: data.symbol, dataType: type, data });
      });
      simpleAlpacaWebSocket.off('subscribed', handleSubscribed);
    };
  }, [addLog]);

  // Update metrics periodically
  useEffect(() => {
    const updateMetrics = () => {
      setMetrics(simpleAlpacaWebSocket.getMetrics());
    };

    updateMetrics();
    const interval = setInterval(updateMetrics, 1000);
    return () => clearInterval(interval);
  }, []);

  // Connection controls
  const handleConnect = () => {
    simpleAlpacaWebSocket.connect();
  };

  const handleDisconnect = () => {
    simpleAlpacaWebSocket.disconnect();
  };

  const refreshSubscriptions = () => {
    if (simpleAlpacaWebSocket.isConnected) {
      // simpleAlpacaWebSocket doesn't have getSubscriptions method
      // subscriptions are managed locally
    }
  };

  // Subscription management
  const handleSubscribe = () => {
    if (!newSymbol.trim()) return;
    
    const symbol = newSymbol.trim().toUpperCase();
    
    try {
      switch (selectedDataType) {
        case 'quotes':
          simpleAlpacaWebSocket.subscribeToQuotes([symbol]);
          setSubscriptions(prev => [...prev, { symbol, type: 'quotes', createdAt: new Date() }]);
          break;
        case 'trades':
          simpleAlpacaWebSocket.subscribeToTrades([symbol]);
          setSubscriptions(prev => [...prev, { symbol, type: 'trades', createdAt: new Date() }]);
          break;
        case 'bars':
          simpleAlpacaWebSocket.subscribeToBars([symbol]);
          setSubscriptions(prev => [...prev, { symbol, type: 'bars', createdAt: new Date() }]);
          break;
        default:
          simpleAlpacaWebSocket.subscribeToQuotes([symbol]);
          setSubscriptions(prev => [...prev, { symbol, type: selectedDataType, createdAt: new Date() }]);
      }
      
      setNewSymbol('');
    } catch (error) {
      setError(error.message);
    }
  };

  const handleUnsubscribe = (index) => {
    // Remove from local state
    setSubscriptions(prev => prev.filter((_, i) => i !== index));
  };

  const handleUnsubscribeAll = () => {
    simpleAlpacaWebSocket.unsubscribeAll();
    setSubscriptions([]);
  };

  // Status helpers
  const getStatusColor = () => {
    switch (connectionStatus) {
      case 'CONNECTED': return 'success';
      case 'CONNECTING': return 'warning';
      case 'DISCONNECTED': return 'error';
      default: return 'default';
    }
  };

  const getStatusIcon = () => {
    switch (connectionStatus) {
      case 'CONNECTED': return <Wifi color="success" />;
      case 'CONNECTING': return <Circle color="warning" />;
      case 'DISCONNECTED': return <WifiOff color="error" />;
      default: return <Circle />;
    }
  };

  const getDataTypeIcon = (dataType) => {
    switch (dataType) {
      case 'quotes': return <ShowChart />;
      case 'trades': return <TrendingUp />;
      case 'bars': return <Timeline />;
      case 'news': return <NewReleases />;
      case 'crypto': return <CurrencyBitcoin />;
      default: return <Circle />;
    }
  };

  // Format helpers
  const formatPrice = (price) => {
    return typeof price === 'number' ? `$${price.toFixed(2)}` : 'N/A';
  };

  const formatNumber = (num) => {
    return typeof num === 'number' ? num.toLocaleString() : 'N/A';
  };

  const formatLatency = (latency) => {
    if (typeof latency !== 'number') return 'N/A';
    return `${latency.toFixed(1)}ms`;
  };

  // Quick subscription buttons
  const quickSubscriptions = [
    { symbols: ['AAPL', 'MSFT', 'GOOGL', 'AMZN'], dataType: 'quotes', label: 'Big Tech Quotes' },
    { symbols: ['TSLA', 'NVDA', 'META', 'NFLX'], dataType: 'trades', label: 'Growth Stocks Trades' },
    { symbols: ['SPY', 'QQQ', 'IWM', 'VTI'], dataType: 'bars', label: 'ETF Bars' },
    { symbols: ['BTCUSD', 'ETHUSD', 'LTCUSD'], dataType: 'crypto', label: 'Crypto' }
  ];

  const handleQuickSubscribe = (quickSub) => {
    quickSub.symbols.forEach(symbol => {
      switch (quickSub.dataType) {
        case 'quotes':
          simpleAlpacaWebSocket.subscribeToQuotes([symbol]);
          setSubscriptions(prev => [...prev, { symbol, type: 'quotes', createdAt: new Date() }]);
          break;
        case 'trades':
          simpleAlpacaWebSocket.subscribeToTrades([symbol]);
          setSubscriptions(prev => [...prev, { symbol, type: 'trades', createdAt: new Date() }]);
          break;
        case 'bars':
          simpleAlpacaWebSocket.subscribeToBars([symbol]);
          setSubscriptions(prev => [...prev, { symbol, type: 'bars', createdAt: new Date() }]);
          break;
        case 'crypto':
          // Crypto not supported in simpleAlpacaWebSocket - treat as quotes
          simpleAlpacaWebSocket.subscribeToQuotes([symbol]);
          setSubscriptions(prev => [...prev, { symbol, type: 'crypto', createdAt: new Date() }]);
          break;
      }
    });
  };

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" gutterBottom>
        Alpaca Real-time Data Dashboard
      </Typography>
      <Typography variant="subtitle1" color="text.secondary" gutterBottom>
        Professional-grade market data streaming with HFT capabilities
      </Typography>

      {/* Connection Status & Controls */}
      <Grid container spacing={3} sx={{ mb: 3 }}>
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
                <Box sx={{ display: 'flex', alignItems: 'center' }}>
                  {getStatusIcon()}
                  <Typography variant="h6" sx={{ ml: 1 }}>
                    Connection Status
                  </Typography>
                </Box>
                <FormControlLabel
                  control={
                    <Switch
                      checked={autoReconnect}
                      onChange={(e) => setAutoReconnect(e.target.checked)}
                      size="small"
                    />
                  }
                  label="Auto-reconnect"
                />
              </Box>
              
              <Chip 
                label={connectionStatus} 
                color={getStatusColor()} 
                variant="outlined"
                sx={{ mb: 2 }}
              />
              
              <Box sx={{ display: 'flex', gap: 1 }}>
                <Button 
                  variant="contained" 
                  startIcon={<PlayArrow />}
                  onClick={handleConnect}
                  disabled={connectionStatus === 'CONNECTED' || connectionStatus === 'CONNECTING'}
                >
                  Connect
                </Button>
                <Button 
                  variant="outlined" 
                  startIcon={<Stop />}
                  onClick={handleDisconnect}
                  disabled={connectionStatus === 'DISCONNECTED'}
                >
                  Disconnect
                </Button>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Performance Metrics
              </Typography>
              <Grid container spacing={2}>
                <Grid item xs={6}>
                  <Typography variant="body2" color="text.secondary">
                    Latency (Avg)
                  </Typography>
                  <Typography variant="h6" color="primary">
                    {formatLatency(metrics.avgLatency)}
                  </Typography>
                </Grid>
                <Grid item xs={6}>
                  <Typography variant="body2" color="text.secondary">
                    Messages/sec
                  </Typography>
                  <Typography variant="h6" color="primary">
                    {Math.round((metrics.messagesReceived || 0) / Math.max(1, (metrics.connectionUptime || 1) / 1000))}
                  </Typography>
                </Grid>
                <Grid item xs={6}>
                  <Typography variant="body2" color="text.secondary">
                    Uptime
                  </Typography>
                  <Typography variant="h6">
                    {Math.round((metrics.connectionUptime || 0) / 1000)}s
                  </Typography>
                </Grid>
                <Grid item xs={6}>
                  <Typography variant="body2" color="text.secondary">
                    Subscriptions
                  </Typography>
                  <Typography variant="h6">
                    {metrics.subscriptionsCount || 0}
                  </Typography>
                </Grid>
              </Grid>
              
              {/* Data type specific metrics */}
              <Divider sx={{ my: 1 }} />
              <Grid container spacing={1}>
                <Grid item xs={3}>
                  <Typography variant="caption" color="text.secondary">
                    Quotes: {metrics.quotesReceived || 0}
                  </Typography>
                </Grid>
                <Grid item xs={3}>
                  <Typography variant="caption" color="text.secondary">
                    Trades: {metrics.tradesReceived || 0}
                  </Typography>
                </Grid>
                <Grid item xs={3}>
                  <Typography variant="caption" color="text.secondary">
                    Bars: {metrics.barsReceived || 0}
                  </Typography>
                </Grid>
                <Grid item xs={3}>
                  <Typography variant="caption" color="text.secondary">
                    News: {metrics.newsReceived || 0}
                  </Typography>
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Error Alert */}
      {error && (
        <Alert severity="error" sx={{ mb: 3 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {/* Main Content Tabs */}
      <Card sx={{ mb: 3 }}>
        <Tabs 
          value={activeTab} 
          onChange={(e, newValue) => setActiveTab(newValue)}
          sx={{ borderBottom: 1, borderColor: 'divider' }}
        >
          <Tab label="Subscriptions" />
          <Tab label="Market Data" />
          <Tab label="Available Feeds" />
          <Tab label="Activity Log" />
        </Tabs>

        {/* Subscriptions Tab */}
        {activeTab === 0 && (
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Manage Data Subscriptions
            </Typography>
            
            {/* Quick Subscription Buttons */}
            <Box sx={{ mb: 3 }}>
              <Typography variant="subtitle2" gutterBottom>
                Quick Subscriptions:
              </Typography>
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                {quickSubscriptions.map((quickSub, index) => (
                  <Button
                    key={index}
                    variant="outlined"
                    size="small"
                    onClick={() => handleQuickSubscribe(quickSub)}
                    disabled={connectionStatus !== 'CONNECTED'}
                  >
                    {quickSub.label}
                  </Button>
                ))}
              </Box>
            </Box>

            {/* Custom Subscription Form */}
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2, mb: 3 }}>
              <TextField
                size="small"
                label="Symbol (e.g., AAPL)"
                value={newSymbol}
                onChange={(e) => setNewSymbol(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && handleSubscribe()}
                disabled={connectionStatus !== 'CONNECTED'}
                sx={{ minWidth: 150 }}
              />
              
              <FormControl size="small" sx={{ minWidth: 120 }}>
                <InputLabel>Data Type</InputLabel>
                <Select
                  value={selectedDataType}
                  onChange={(e) => setSelectedDataType(e.target.value)}
                  label="Data Type"
                >
                  <MenuItem value="quotes">Quotes</MenuItem>
                  <MenuItem value="trades">Trades</MenuItem>
                  <MenuItem value="bars">Bars</MenuItem>
                  <MenuItem value="news">News</MenuItem>
                  <MenuItem value="crypto">Crypto</MenuItem>
                </Select>
              </FormControl>
              
              {selectedDataType === 'bars' && (
                <FormControl size="small" sx={{ minWidth: 100 }}>
                  <InputLabel>Frequency</InputLabel>
                  <Select
                    value={selectedFrequency}
                    onChange={(e) => setSelectedFrequency(e.target.value)}
                    label="Frequency"
                  >
                    <MenuItem value="1Min">1 Min</MenuItem>
                    <MenuItem value="5Min">5 Min</MenuItem>
                    <MenuItem value="15Min">15 Min</MenuItem>
                    <MenuItem value="1Hour">1 Hour</MenuItem>
                    <MenuItem value="1Day">1 Day</MenuItem>
                  </Select>
                </FormControl>
              )}
              
              <Button 
                variant="contained" 
                startIcon={<Add />}
                onClick={handleSubscribe}
                disabled={connectionStatus !== 'CONNECTED' || !newSymbol.trim()}
              >
                Subscribe
              </Button>
            </Box>

            {/* Active Subscriptions */}
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
              <Typography variant="h6">
                Active Subscriptions ({subscriptions.length})
              </Typography>
              <Box>
                <IconButton onClick={refreshSubscriptions} size="small">
                  <Refresh />
                </IconButton>
                <Button
                  variant="outlined"
                  size="small"
                  startIcon={<Delete />}
                  onClick={handleUnsubscribeAll}
                  disabled={subscriptions.length === 0}
                  sx={{ ml: 1 }}
                >
                  Unsubscribe All
                </Button>
              </Box>
            </Box>

            {subscriptions.length === 0 ? (
              <Typography color="text.secondary">
                No active subscriptions. Subscribe to symbols to see live data.
              </Typography>
            ) : (
              <TableContainer component={Paper} variant="outlined">
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Type</TableCell>
                      <TableCell>Symbols</TableCell>
                      <TableCell>Frequency</TableCell>
                      <TableCell>Created</TableCell>
                      <TableCell align="center">Actions</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {subscriptions.map((sub, index) => (
                      <TableRow key={index}>
                        <TableCell>
                          <Box sx={{ display: 'flex', alignItems: 'center' }}>
                            {getDataTypeIcon(sub.type)}
                            <Typography sx={{ ml: 1 }} variant="body2">
                              {sub.type}
                            </Typography>
                          </Box>
                        </TableCell>
                        <TableCell>
                          <Chip label={sub.symbol} size="small" />
                        </TableCell>
                        <TableCell>
                          <Typography variant="body2">
                            Real-time
                          </Typography>
                        </TableCell>
                        <TableCell>
                          <Typography variant="body2" color="text.secondary">
                            {new Date(sub.createdAt).toLocaleTimeString()}
                          </Typography>
                        </TableCell>
                        <TableCell align="center">
                          <IconButton
                            size="small"
                            onClick={() => handleUnsubscribe(index)}
                            color="error"
                          >
                            <Delete />
                          </IconButton>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
          </CardContent>
        )}

        {/* Market Data Tab */}
        {activeTab === 1 && (
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Live Market Data
            </Typography>
            
            {Object.keys(marketData).length === 0 ? (
              <Typography color="text.secondary">
                No market data available. Subscribe to symbols to see live data.
              </Typography>
            ) : (
              <TableContainer component={Paper} variant="outlined">
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Symbol</TableCell>
                      <TableCell>Type</TableCell>
                      <TableCell>Data</TableCell>
                      <TableCell>Last Update</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {Object.entries(marketData).map(([key, data]) => (
                      <TableRow key={key}>
                        <TableCell>
                          <Typography variant="body2" fontWeight="bold">
                            {data.symbol}
                          </Typography>
                        </TableCell>
                        <TableCell>
                          <Box sx={{ display: 'flex', alignItems: 'center' }}>
                            {getDataTypeIcon(data.dataType)}
                            <Typography sx={{ ml: 1 }} variant="body2">
                              {data.dataType}
                            </Typography>
                          </Box>
                        </TableCell>
                        <TableCell>
                          {data.dataType === 'quotes' && (
                            <Typography variant="body2">
                              Bid: {formatPrice(data.bid)} | Ask: {formatPrice(data.ask)}
                            </Typography>
                          )}
                          {data.dataType === 'trades' && (
                            <Typography variant="body2">
                              Price: {formatPrice(data.price)} | Size: {formatNumber(data.size)}
                            </Typography>
                          )}
                          {data.dataType === 'bars' && (
                            <Typography variant="body2">
                              O: {formatPrice(data.open)} | H: {formatPrice(data.high)} | L: {formatPrice(data.low)} | C: {formatPrice(data.close)}
                            </Typography>
                          )}
                          {data.dataType === 'news' && (
                            <Typography variant="body2">
                              {data.headline || 'News update'}
                            </Typography>
                          )}
                        </TableCell>
                        <TableCell>
                          <Typography variant="body2" color="text.secondary">
                            {data.lastUpdate}
                          </Typography>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
          </CardContent>
        )}

        {/* Available Feeds Tab */}
        {activeTab === 2 && (
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Available Data Feeds
            </Typography>
            
            {!availableFeeds ? (
              <Box>
                <Typography color="text.secondary" gutterBottom>
                  Loading available feeds...
                </Typography>
                <Button
                  variant="outlined"
                  onClick={() => setAvailableFeeds({
                    quotes: { description: 'Real-time quotes', symbols: 'All US stocks', frequency: 'Real-time' },
                    trades: { description: 'Live trades', symbols: 'All US stocks', frequency: 'Real-time' },
                    bars: { description: 'OHLCV bars', symbols: 'All US stocks', frequency: ['1Min', '5Min', '1Day'] }
                  })}
                  disabled={connectionStatus !== 'CONNECTED'}
                >
                  Load Feeds
                </Button>
              </Box>
            ) : (
              <Grid container spacing={2}>
                {Object.entries(availableFeeds).map(([feedType, feedInfo]) => (
                  <Grid item xs={12} md={6} key={feedType}>
                    <Card variant="outlined">
                      <CardContent>
                        <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                          {getDataTypeIcon(feedType)}
                          <Typography variant="h6" sx={{ ml: 1 }}>
                            {feedType.charAt(0).toUpperCase() + feedType.slice(1)}
                          </Typography>
                        </Box>
                        
                        <Typography variant="body2" color="text.secondary" paragraph>
                          {feedInfo.description}
                        </Typography>
                        
                        <Typography variant="body2">
                          <strong>Symbols:</strong> {feedInfo.symbols}
                        </Typography>
                        
                        <Typography variant="body2">
                          <strong>Frequency:</strong> {
                            Array.isArray(feedInfo.frequency) 
                              ? feedInfo.frequency.join(', ')
                              : feedInfo.frequency
                          }
                        </Typography>
                      </CardContent>
                    </Card>
                  </Grid>
                ))}
              </Grid>
            )}
          </CardContent>
        )}

        {/* Activity Log Tab */}
        {activeTab === 3 && (
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Activity Log
            </Typography>
            
            <Box sx={{ height: 400, overflow: 'auto', border: 1, borderColor: 'divider', borderRadius: 1, p: 1 }}>
              {logs.length === 0 ? (
                <Typography color="text.secondary">
                  No activity yet.
                </Typography>
              ) : (
                logs.map((log, index) => (
                  <Typography 
                    key={index} 
                    variant="body2" 
                    sx={{ 
                      mb: 0.5,
                      fontFamily: 'monospace',
                      color: log.type === 'error' ? 'error.main' : 
                             log.type === 'success' ? 'success.main' :
                             log.type === 'warning' ? 'warning.main' : 'text.primary'
                    }}
                  >
                    <strong>{log.timestamp}</strong> {log.message}
                  </Typography>
                ))
              )}
            </Box>
          </CardContent>
        )}
      </Card>
    </Box>
  );
};

export default AlpacaDataDashboard;