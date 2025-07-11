import React, { useState, useEffect } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Button,
  TextField,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Grid,
  Chip,
  Alert,
  IconButton,
  Tabs,
  Tab
} from '@mui/material';
import {
  TrendingUp,
  TrendingDown,
  PlayArrow,
  Stop,
  Add,
  Delete,
  Refresh
} from '@mui/icons-material';
import simpleAlpacaWebSocket from '../services/simpleAlpacaWebSocket';

const SimpleAlpacaData = () => {
  const [connected, setConnected] = useState(false);
  const [data, setData] = useState({});
  const [newSymbol, setNewSymbol] = useState('');
  const [subscriptions, setSubscriptions] = useState([]);
  const [error, setError] = useState('');
  const [metrics, setMetrics] = useState({});
  const [activeTab, setActiveTab] = useState(0);

  useEffect(() => {
    // Event handlers
    const handleConnected = () => {
      setConnected(true);
      setError('');
    };

    const handleDisconnected = () => {
      setConnected(false);
    };

    const handleError = (error) => {
      setError(error.message);
    };

    const handleData = ({ type, data }) => {
      setData(prev => ({
        ...prev,
        [`${data.symbol}:${type}`]: {
          ...data,
          type,
          lastUpdate: new Date().toLocaleTimeString()
        }
      }));
    };

    // Subscribe to events
    simpleAlpacaWebSocket.on('connected', handleConnected);
    simpleAlpacaWebSocket.on('disconnected', handleDisconnected);
    simpleAlpacaWebSocket.on('error', handleError);
    simpleAlpacaWebSocket.on('data', handleData);

    // Update metrics every second
    const metricsInterval = setInterval(() => {
      setMetrics(simpleAlpacaWebSocket.getMetrics());
    }, 1000);

    // Cleanup
    return () => {
      simpleAlpacaWebSocket.off('connected', handleConnected);
      simpleAlpacaWebSocket.off('disconnected', handleDisconnected);
      simpleAlpacaWebSocket.off('error', handleError);
      simpleAlpacaWebSocket.off('data', handleData);
      clearInterval(metricsInterval);
    };
  }, []);

  const handleConnect = () => {
    simpleAlpacaWebSocket.connect();
  };

  const handleDisconnect = () => {
    simpleAlpacaWebSocket.disconnect();
  };

  const handleSubscribeQuotes = () => {
    if (newSymbol.trim()) {
      simpleAlpacaWebSocket.subscribeToQuotes([newSymbol.toUpperCase()]);
      setSubscriptions(prev => [...prev, { symbol: newSymbol.toUpperCase(), type: 'quotes' }]);
      setNewSymbol('');
    }
  };

  const handleSubscribeTrades = () => {
    if (newSymbol.trim()) {
      simpleAlpacaWebSocket.subscribeToTrades([newSymbol.toUpperCase()]);
      setSubscriptions(prev => [...prev, { symbol: newSymbol.toUpperCase(), type: 'trades' }]);
      setNewSymbol('');
    }
  };

  const handleSubscribeBars = () => {
    if (newSymbol.trim()) {
      simpleAlpacaWebSocket.subscribeToBars([newSymbol.toUpperCase()]);
      setSubscriptions(prev => [...prev, { symbol: newSymbol.toUpperCase(), type: 'bars' }]);
      setNewSymbol('');
    }
  };

  const handleUnsubscribeAll = () => {
    simpleAlpacaWebSocket.unsubscribeAll();
    setSubscriptions([]);
  };

  const quickSubscribe = (symbols, type) => {
    symbols.forEach(symbol => {
      if (type === 'quotes') {
        simpleAlpacaWebSocket.subscribeToQuotes([symbol]);
      } else if (type === 'trades') {
        simpleAlpacaWebSocket.subscribeToTrades([symbol]);
      } else if (type === 'bars') {
        simpleAlpacaWebSocket.subscribeToBars([symbol]);
      }
      setSubscriptions(prev => [...prev, { symbol, type }]);
    });
  };

  const formatPrice = (price) => {
    return typeof price === 'number' ? `$${price.toFixed(2)}` : 'N/A';
  };

  const formatNumber = (num) => {
    return typeof num === 'number' ? num.toLocaleString() : 'N/A';
  };

  const getStatusColor = () => {
    return connected ? 'success' : 'error';
  };

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" gutterBottom>
        Simple Alpaca Live Data
      </Typography>
      <Typography variant="subtitle1" color="text.secondary" gutterBottom>
        Direct WebSocket connection to Alpaca for real-time stock data
      </Typography>

      {/* Connection Status */}
      <Grid container spacing={3} sx={{ mb: 3 }}>
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
                <Typography variant="h6">Connection</Typography>
                <Chip 
                  label={connected ? 'Connected' : 'Disconnected'} 
                  color={getStatusColor()} 
                  variant="outlined" 
                />
              </Box>
              
              <Box sx={{ display: 'flex', gap: 1 }}>
                <Button 
                  variant="contained" 
                  startIcon={<PlayArrow />}
                  onClick={handleConnect}
                  disabled={connected}
                >
                  Connect
                </Button>
                <Button 
                  variant="outlined" 
                  startIcon={<Stop />}
                  onClick={handleDisconnect}
                  disabled={!connected}
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
              <Typography variant="h6" gutterBottom>Metrics</Typography>
              <Grid container spacing={2}>
                <Grid item xs={6}>
                  <Typography variant="body2" color="text.secondary">Messages</Typography>
                  <Typography variant="h6">{metrics.messagesReceived || 0}</Typography>
                </Grid>
                <Grid item xs={6}>
                  <Typography variant="body2" color="text.secondary">Subscriptions</Typography>
                  <Typography variant="h6">{subscriptions.length}</Typography>
                </Grid>
                <Grid item xs={6}>
                  <Typography variant="body2" color="text.secondary">Uptime</Typography>
                  <Typography variant="h6">
                    {metrics.uptime ? `${Math.floor(metrics.uptime / 1000)}s` : '0s'}
                  </Typography>
                </Grid>
                <Grid item xs={6}>
                  <Typography variant="body2" color="text.secondary">Data Points</Typography>
                  <Typography variant="h6">{Object.keys(data).length}</Typography>
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Error Alert */}
      {error && (
        <Alert severity="error" sx={{ mb: 3 }} onClose={() => setError('')}>
          {error}
        </Alert>
      )}

      {/* Main Content */}
      <Card>
        <Tabs value={activeTab} onChange={(e, newValue) => setActiveTab(newValue)}>
          <Tab label="Subscribe" />
          <Tab label="Live Data" />
        </Tabs>

        {/* Subscribe Tab */}
        {activeTab === 0 && (
          <CardContent>
            <Typography variant="h6" gutterBottom>Subscribe to Symbols</Typography>
            
            {/* Quick Subscribe Buttons */}
            <Box sx={{ mb: 3 }}>
              <Typography variant="subtitle2" gutterBottom>Quick Subscribe:</Typography>
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mb: 2 }}>
                <Button 
                  variant="outlined" 
                  size="small"
                  onClick={() => quickSubscribe(['AAPL', 'MSFT', 'GOOGL', 'AMZN'], 'quotes')}
                  disabled={!connected}
                >
                  Big Tech Quotes
                </Button>
                <Button 
                  variant="outlined" 
                  size="small"
                  onClick={() => quickSubscribe(['TSLA', 'NVDA', 'META'], 'trades')}
                  disabled={!connected}
                >
                  Growth Stocks Trades
                </Button>
                <Button 
                  variant="outlined" 
                  size="small"
                  onClick={() => quickSubscribe(['SPY', 'QQQ', 'IWM'], 'bars')}
                  disabled={!connected}
                >
                  ETF Bars
                </Button>
              </Box>
            </Box>

            {/* Manual Subscribe */}
            <Box sx={{ display: 'flex', gap: 2, mb: 3 }}>
              <TextField
                size="small"
                label="Symbol (e.g., AAPL)"
                value={newSymbol}
                onChange={(e) => setNewSymbol(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && handleSubscribeQuotes()}
                disabled={!connected}
              />
              <Button 
                variant="contained" 
                onClick={handleSubscribeQuotes}
                disabled={!connected || !newSymbol.trim()}
              >
                Quotes
              </Button>
              <Button 
                variant="contained" 
                onClick={handleSubscribeTrades}
                disabled={!connected || !newSymbol.trim()}
              >
                Trades
              </Button>
              <Button 
                variant="contained" 
                onClick={handleSubscribeBars}
                disabled={!connected || !newSymbol.trim()}
              >
                Bars
              </Button>
            </Box>

            {/* Active Subscriptions */}
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
              <Typography variant="h6">Active Subscriptions ({subscriptions.length})</Typography>
              <Button
                variant="outlined"
                size="small"
                startIcon={<Delete />}
                onClick={handleUnsubscribeAll}
                disabled={subscriptions.length === 0}
              >
                Unsubscribe All
              </Button>
            </Box>

            {subscriptions.length === 0 ? (
              <Typography color="text.secondary">No active subscriptions</Typography>
            ) : (
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                {subscriptions.map((sub, index) => (
                  <Chip 
                    key={index} 
                    label={`${sub.symbol} (${sub.type})`} 
                    variant="outlined" 
                  />
                ))}
              </Box>
            )}
          </CardContent>
        )}

        {/* Live Data Tab */}
        {activeTab === 1 && (
          <CardContent>
            <Typography variant="h6" gutterBottom>Live Market Data</Typography>
            
            {Object.keys(data).length === 0 ? (
              <Typography color="text.secondary">
                No live data yet. Subscribe to symbols to see real-time data.
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
                    {Object.entries(data).map(([key, item]) => (
                      <TableRow key={key}>
                        <TableCell>
                          <Typography variant="body2" fontWeight="bold">
                            {item.symbol}
                          </Typography>
                        </TableCell>
                        <TableCell>
                          <Chip label={item.type} size="small" variant="outlined" />
                        </TableCell>
                        <TableCell>
                          {item.type === 'quote' && (
                            <Typography variant="body2">
                              Bid: {formatPrice(item.bid)} | Ask: {formatPrice(item.ask)}
                            </Typography>
                          )}
                          {item.type === 'trade' && (
                            <Typography variant="body2">
                              Price: {formatPrice(item.price)} | Size: {formatNumber(item.size)}
                            </Typography>
                          )}
                          {item.type === 'bar' && (
                            <Typography variant="body2">
                              O: {formatPrice(item.open)} | H: {formatPrice(item.high)} | 
                              L: {formatPrice(item.low)} | C: {formatPrice(item.close)}
                            </Typography>
                          )}
                        </TableCell>
                        <TableCell>
                          <Typography variant="body2" color="text.secondary">
                            {item.lastUpdate}
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
      </Card>
    </Box>
  );
};

export default SimpleAlpacaData;