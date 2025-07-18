import React, { useState, useEffect, useCallback } from 'react';
import {
  Card,
  CardContent,
  Typography,
  Grid,
  Chip,
  Box,
  Button,
  TextField,
  Alert,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  LinearProgress,
  Divider
} from '@mui/material';
import {
  TrendingUp,
  TrendingDown,
  Circle,
  Speed,
  ShowChart,
  Wifi,
  WifiOff
} from '@mui/icons-material';
import liveDataService from '../services/liveDataService';

const LiveDataDashboard = () => {
  const [connectionStatus, setConnectionStatus] = useState('DISCONNECTED');
  const [marketData, setMarketData] = useState({});
  const [subscriptions, setSubscriptions] = useState([]);
  const [metrics, setMetrics] = useState({});
  const [newSymbol, setNewSymbol] = useState('');
  const [error, setError] = useState(null);
  const [logs, setLogs] = useState([]);

  // Add log entry
  const addLog = useCallback((message, type = 'info') => {
    const timestamp = new Date().toLocaleTimeString();
    setLogs(prev => [...prev.slice(-19), { timestamp, message, type }]);
  }, []);

  // Setup event listeners
  useEffect(() => {
    const handleConnected = () => {
      setConnectionStatus('CONNECTED');
      setError(null);
      addLog('Connected to WebSocket', 'success');
    };

    const handleDisconnected = () => {
      setConnectionStatus('DISCONNECTED');
      addLog('Disconnected from WebSocket', 'warning');
    };

    const handleConnecting = () => {
      setConnectionStatus('CONNECTING');
      addLog('Connecting to WebSocket...', 'info');
    };

    const handleError = (error) => {
      setError(error.message || 'Connection error');
      addLog(`Error: ${error.message}`, 'error');
    };

    const handleMarketData = ({ symbol, data }) => {
      setMarketData(prev => ({
        ...prev,
        [symbol]: {
          ...data,
          lastUpdate: new Date().toLocaleTimeString()
        }
      }));
      addLog(`Market data for ${symbol}: $${data.price}`, 'info');
    };

    const handleSubscribed = (data) => {
      addLog(`Subscribed to ${data.symbols?.join(', ') || 'symbols'}`, 'success');
    };

    // Subscribe to events
    liveDataService.on('connected', handleConnected);
    liveDataService.on('disconnected', handleDisconnected);
    liveDataService.on('connecting', handleConnecting);
    liveDataService.on('error', handleError);
    liveDataService.on('marketData', handleMarketData);
    liveDataService.on('subscribed', handleSubscribed);

    // Set initial state
    setConnectionStatus(liveDataService.getConnectionStatus());
    setMarketData(liveDataService.getAllMarketData());
    setSubscriptions(liveDataService.getSubscriptions());

    // Cleanup
    return () => {
      liveDataService.off('connected', handleConnected);
      liveDataService.off('disconnected', handleDisconnected);
      liveDataService.off('connecting', handleConnecting);
      liveDataService.off('error', handleError);
      liveDataService.off('marketData', handleMarketData);
      liveDataService.off('subscribed', handleSubscribed);
    };
  }, [addLog]);

  // Update metrics periodically
  useEffect(() => {
    const updateMetrics = () => {
      setMetrics(liveDataService.getMetrics());
      setSubscriptions(liveDataService.getSubscriptions());
    };

    updateMetrics();
    const interval = setInterval(updateMetrics, 1000);
    return () => clearInterval(interval);
  }, []);

  // Connection controls
  const handleConnect = () => {
    liveDataService.connect();
  };

  const handleDisconnect = () => {
    liveDataService.disconnect();
  };

  // Subscription management
  const handleSubscribe = () => {
    if (newSymbol.trim()) {
      liveDataService.subscribe([newSymbol.trim().toUpperCase()]);
      setNewSymbol('');
    }
  };

  const handleUnsubscribe = (symbol) => {
    liveDataService.unsubscribe([symbol]);
    setMarketData(prev => {
      const updated = { ...prev };
      delete updated[symbol];
      return updated;
    });
  };

  // Status indicator
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

  // Format numbers
  const formatPrice = (price) => {
    return typeof price === 'number' ? `$${price.toFixed(2)}` : 'N/A';
  };

  const formatPercent = (percent) => {
    if (typeof percent !== 'number') return 'N/A';
    const formatted = percent.toFixed(2);
    return `${percent > 0 ? '+' : ''}${formatted}%`;
  };

  const formatLatency = (latency) => {
    if (typeof latency !== 'number') return 'N/A';
    return `${latency.toFixed(1)}ms`;
  };

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" gutterBottom>
        Live Market Data Dashboard
      </Typography>

      {/* Connection Status */}
      <Grid container spacing={3} sx={{ mb: 3 }}>
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                {getStatusIcon()}
                <Typography variant="h6" sx={{ ml: 1 }}>
                  Connection Status
                </Typography>
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
                  onClick={handleConnect}
                  disabled={connectionStatus === 'CONNECTED' || connectionStatus === 'CONNECTING'}
                >
                  Connect
                </Button>
                <Button 
                  variant="outlined" 
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
                    Latency
                  </Typography>
                  <Typography variant="h6">
                    {formatLatency(metrics.lastLatency)}
                  </Typography>
                </Grid>
                <Grid item xs={6}>
                  <Typography variant="body2" color="text.secondary">
                    Messages
                  </Typography>
                  <Typography variant="h6">
                    {metrics.messagesReceived || 0}
                  </Typography>
                </Grid>
                <Grid item xs={6}>
                  <Typography variant="body2" color="text.secondary">
                    Avg Latency
                  </Typography>
                  <Typography variant="h6">
                    {formatLatency(metrics.avgLatency)}
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

      {/* Symbol Subscription */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Subscribe to Symbols
          </Typography>
          <Box sx={{ display: 'flex', gap: 1, mb: 2 }}>
            <TextField
              size="small"
              label="Symbol (e.g., AAPL)"
              value={newSymbol}
              onChange={(e) => setNewSymbol(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && handleSubscribe()}
              disabled={connectionStatus !== 'CONNECTED'}
            />
            <Button 
              variant="contained" 
              onClick={handleSubscribe}
              disabled={connectionStatus !== 'CONNECTED' || !newSymbol.trim()}
            >
              Subscribe
            </Button>
          </Box>
          <Typography variant="body2" color="text.secondary">
            Active subscriptions: {subscriptions.join(', ') || 'None'}
          </Typography>
        </CardContent>
      </Card>

      {/* Market Data Table */}
      <Card sx={{ mb: 3 }}>
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
                    <TableCell align="right">Price</TableCell>
                    <TableCell align="right">Change</TableCell>
                    <TableCell align="right">Change %</TableCell>
                    <TableCell align="right">Volume</TableCell>
                    <TableCell align="right">Last Update</TableCell>
                    <TableCell align="center">Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {Object.entries(marketData).map(([symbol, data]) => (
                    <TableRow key={symbol}>
                      <TableCell component="th" scope="row">
                        <Box sx={{ display: 'flex', alignItems: 'center' }}>
                          {data.change > 0 ? (
                            <TrendingUp color="success" fontSize="small" />
                          ) : (
                            <TrendingDown color="error" fontSize="small" />
                          )}
                          <Typography sx={{ ml: 1 }} variant="body2">
                            {symbol}
                          </Typography>
                        </Box>
                      </TableCell>
                      <TableCell align="right">
                        <Typography variant="body2" fontWeight="bold">
                          {formatPrice(data.price)}
                        </Typography>
                      </TableCell>
                      <TableCell align="right">
                        <Typography 
                          variant="body2"
                          color={data.change > 0 ? 'success.main' : 'error.main'}
                        >
                          {formatPrice(data.change)}
                        </Typography>
                      </TableCell>
                      <TableCell align="right">
                        <Typography 
                          variant="body2"
                          color={data.change_percent > 0 ? 'success.main' : 'error.main'}
                        >
                          {formatPercent(data.change_percent)}
                        </Typography>
                      </TableCell>
                      <TableCell align="right">
                        <Typography variant="body2">
                          {data.volume?.toLocaleString() || 'N/A'}
                        </Typography>
                      </TableCell>
                      <TableCell align="right">
                        <Typography variant="body2" color="text.secondary">
                          {data.lastUpdate}
                        </Typography>
                      </TableCell>
                      <TableCell align="center">
                        <Button
                          size="small"
                          onClick={() => handleUnsubscribe(symbol)}
                          color="error"
                        >
                          Unsubscribe
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </CardContent>
      </Card>

      {/* Activity Log */}
      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Activity Log
          </Typography>
          <Box sx={{ height: 200, overflow: 'auto' }}>
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
                    color: log.type === 'error' ? 'error.main' : 
                           log.type === 'success' ? 'success.main' :
                           log.type === 'warning' ? 'warning.main' : 'text.primary'
                  }}
                >
                  <strong>{log.timestamp}</strong>: {log.message}
                </Typography>
              ))
            )}
          </Box>
        </CardContent>
      </Card>
    </Box>
  );
};

export default LiveDataDashboard;