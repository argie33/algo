// Real-Time Data Stream Component
// Displays live market data with real-time charts and updates

import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Grid,
  Chip,
  Alert,
  Button,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  IconButton,
  Tooltip,
  CircularProgress,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper
} from '@mui/material';
import {
  PlayArrow,
  Pause,
  Stop,
  Refresh,
  Settings,
  TrendingUp,
  TrendingDown,
  Remove,
  Add
} from '@mui/icons-material';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  RealtimeChart
} from 'recharts';

const RealTimeDataStream = () => {
  // State management
  const [isConnected, setIsConnected] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState({});
  const [subscribedSymbols, setSubscribedSymbols] = useState(['AAPL', 'GOOGL', 'MSFT']);
  const [newSymbol, setNewSymbol] = useState('');
  const [selectedProvider, setSelectedProvider] = useState('alpaca');
  const [realtimeData, setRealtimeData] = useState(new Map());
  const [trades, setTrades] = useState([]);
  const [quotes, setQuotes] = useState(new Map());
  const [chartData, setChartData] = useState(new Map());
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  // References
  const pollInterval = useRef(null);
  const dataBuffer = useRef(new Map());

  // Configuration
  const providers = ['alpaca', 'polygon', 'finnhub'];
  const maxTradeHistory = 100;
  const maxChartPoints = 50;
  const pollIntervalMs = 1000; // 1 second

  // Initialize connection status
  useEffect(() => {
    checkConnectionStatus();
  }, []);

  // Check connection status
  const checkConnectionStatus = async () => {
    try {
      const response = await fetch('/api/realtime/status');
      const result = await response.json();
      
      if (result.success) {
        setConnectionStatus(result.data);
        setIsConnected(result.data.connectedProviders.length > 0);
      }
    } catch (error) {
      console.error('Failed to check connection status:', error);
      setError('Failed to check connection status');
    }
  };

  // Connect to real-time providers
  const connectProviders = async () => {
    setLoading(true);
    setError(null);
    
    try {
      // This would need to get API keys from the API key service
      const response = await fetch('/api/realtime/connect', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          providers: {
            [selectedProvider]: {
              keyId: 'demo-key', // Would be real API key
              secretKey: 'demo-secret'
            }
          }
        })
      });
      
      const result = await response.json();
      
      if (result.success) {
        setIsConnected(true);
        await checkConnectionStatus();
      } else {
        setError(result.message || 'Failed to connect to providers');
      }
    } catch (error) {
      console.error('Connection failed:', error);
      setError('Failed to connect to real-time providers');
    } finally {
      setLoading(false);
    }
  };

  // Subscribe to symbols
  const subscribeToSymbols = async (symbols = subscribedSymbols) => {
    if (!isConnected) {
      setError('Not connected to any providers');
      return;
    }

    try {
      const response = await fetch('/api/realtime/subscribe', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          symbols: symbols.map(s => s.toUpperCase()),
          providers: [selectedProvider]
        })
      });
      
      const result = await response.json();
      
      if (result.success) {
        console.log('Subscribed to symbols:', result.results);
      } else {
        setError(result.message || 'Failed to subscribe to symbols');
      }
    } catch (error) {
      console.error('Subscription failed:', error);
      setError('Failed to subscribe to symbols');
    }
  };

  // Start real-time data streaming
  const startStreaming = () => {
    if (!isConnected) {
      connectProviders();
      return;
    }

    setIsStreaming(true);
    subscribeToSymbols();
    
    // Start polling for real-time data
    pollInterval.current = setInterval(pollRealtimeData, pollIntervalMs);
  };

  // Stop streaming
  const stopStreaming = () => {
    setIsStreaming(false);
    
    if (pollInterval.current) {
      clearInterval(pollInterval.current);
      pollInterval.current = null;
    }
  };

  // Poll for real-time data
  const pollRealtimeData = async () => {
    try {
      for (const symbol of subscribedSymbols) {
        const response = await fetch(`/api/realtime/data/${symbol}?count=10`);
        const result = await response.json();
        
        if (result.success && result.data) {
          processRealtimeData(result.data);
        }
      }
    } catch (error) {
      console.error('Failed to poll real-time data:', error);
    }
  };

  // Process incoming real-time data
  const processRealtimeData = (data) => {
    const { symbol, lastData, recentData } = data;
    
    if (lastData) {
      // Update latest data
      setRealtimeData(prev => new Map(prev.set(symbol, lastData)));
      
      // Update based on data type
      if (lastData.type === 'trade') {
        addTrade(lastData);
        updateChartData(lastData);
      } else if (lastData.type === 'quote') {
        setQuotes(prev => new Map(prev.set(symbol, lastData)));
      }
    }
    
    if (recentData && recentData.length > 0) {
      recentData.forEach(item => {
        if (item.type === 'trade') {
          updateChartData(item);
        }
      });
    }
  };

  // Add trade to history
  const addTrade = (trade) => {
    setTrades(prev => {
      const newTrades = [trade, ...prev].slice(0, maxTradeHistory);
      return newTrades;
    });
  };

  // Update chart data
  const updateChartData = (trade) => {
    setChartData(prev => {
      const symbolChart = prev.get(trade.symbol) || [];
      const newDataPoint = {
        time: new Date(trade.timestamp).getTime(),
        price: trade.price,
        size: trade.size,
        timeLabel: new Date(trade.timestamp).toLocaleTimeString()
      };
      
      const updatedChart = [...symbolChart, newDataPoint].slice(-maxChartPoints);
      return new Map(prev.set(trade.symbol, updatedChart));
    });
  };

  // Add new symbol
  const addSymbol = () => {
    if (newSymbol && !subscribedSymbols.includes(newSymbol.toUpperCase())) {
      const updatedSymbols = [...subscribedSymbols, newSymbol.toUpperCase()];
      setSubscribedSymbols(updatedSymbols);
      setNewSymbol('');
      
      if (isStreaming) {
        subscribeToSymbols([newSymbol.toUpperCase()]);
      }
    }
  };

  // Remove symbol
  const removeSymbol = (symbol) => {
    const updatedSymbols = subscribedSymbols.filter(s => s !== symbol);
    setSubscribedSymbols(updatedSymbols);
    
    // Clean up data
    setRealtimeData(prev => {
      const newMap = new Map(prev);
      newMap.delete(symbol);
      return newMap;
    });
    setQuotes(prev => {
      const newMap = new Map(prev);
      newMap.delete(symbol);
      return newMap;
    });
    setChartData(prev => {
      const newMap = new Map(prev);
      newMap.delete(symbol);
      return newMap;
    });
  };

  // Format price
  const formatPrice = (price) => {
    return typeof price === 'number' ? price.toFixed(2) : 'N/A';
  };

  // Format timestamp
  const formatTime = (timestamp) => {
    return new Date(timestamp).toLocaleTimeString();
  };

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (pollInterval.current) {
        clearInterval(pollInterval.current);
      }
    };
  }, []);

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" gutterBottom>
        Real-Time Market Data Stream
      </Typography>

      {/* Connection Status */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Connection Status
          </Typography>
          
          <Grid container spacing={2} alignItems="center">
            <Grid item>
              <Chip
                label={isConnected ? 'Connected' : 'Disconnected'}
                color={isConnected ? 'success' : 'error'}
                icon={isConnected ? <TrendingUp /> : <TrendingDown />}
              />
            </Grid>
            
            <Grid item>
              <FormControl size="small" sx={{ minWidth: 120 }}>
                <InputLabel>Provider</InputLabel>
                <Select
                  value={selectedProvider}
                  onChange={(e) => setSelectedProvider(e.target.value)}
                  disabled={isStreaming}
                >
                  {providers.map(provider => (
                    <MenuItem key={provider} value={provider}>
                      {provider.charAt(0).toUpperCase() + provider.slice(1)}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            
            <Grid item>
              <Button
                variant="contained"
                color={isStreaming ? "error" : "primary"}
                onClick={isStreaming ? stopStreaming : startStreaming}
                disabled={loading}
                startIcon={loading ? <CircularProgress size={20} /> : (isStreaming ? <Pause /> : <PlayArrow />)}
              >
                {loading ? 'Connecting...' : (isStreaming ? 'Stop Stream' : 'Start Stream')}
              </Button>
            </Grid>
            
            <Grid item>
              <Tooltip title="Refresh Status">
                <IconButton onClick={checkConnectionStatus}>
                  <Refresh />
                </IconButton>
              </Tooltip>
            </Grid>
          </Grid>

          {connectionStatus.connectedProviders && (
            <Box sx={{ mt: 2 }}>
              <Typography variant="body2" color="text.secondary">
                Connected Providers: {connectionStatus.connectedProviders.join(', ')}
              </Typography>
            </Box>
          )}
        </CardContent>
      </Card>

      {/* Error Display */}
      {error && (
        <Alert severity="error" sx={{ mb: 3 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {/* Symbol Management */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Symbols
          </Typography>
          
          <Grid container spacing={2} alignItems="center" sx={{ mb: 2 }}>
            <Grid item>
              <TextField
                size="small"
                label="Add Symbol"
                value={newSymbol}
                onChange={(e) => setNewSymbol(e.target.value.toUpperCase())}
                onKeyPress={(e) => e.key === 'Enter' && addSymbol()}
                placeholder="AAPL"
              />
            </Grid>
            <Grid item>
              <Button variant="outlined" onClick={addSymbol} startIcon={<Add />}>
                Add
              </Button>
            </Grid>
          </Grid>

          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
            {subscribedSymbols.map(symbol => (
              <Chip
                key={symbol}
                label={symbol}
                onDelete={() => removeSymbol(symbol)}
                deleteIcon={<Remove />}
                color={realtimeData.has(symbol) ? 'primary' : 'default'}
              />
            ))}
          </Box>
        </CardContent>
      </Card>

      {/* Real-Time Charts */}
      {Array.from(chartData.entries()).map(([symbol, data]) => (
        <Card key={symbol} sx={{ mb: 3 }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              {symbol} - Real-Time Price Chart
            </Typography>
            
            {data.length > 0 ? (
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={data}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="timeLabel" />
                  <YAxis domain={['dataMin - 0.1', 'dataMax + 0.1']} />
                  <RechartsTooltip 
                    labelFormatter={(value) => `Time: ${value}`}
                    formatter={(value, name) => [formatPrice(value), 'Price']}
                  />
                  <Line 
                    type="monotone" 
                    dataKey="price" 
                    stroke="#2196f3" 
                    strokeWidth={2}
                    dot={false}
                    connectNulls={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <Box sx={{ height: 300, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Typography color="text.secondary">
                  Waiting for real-time data...
                </Typography>
              </Box>
            )}
          </CardContent>
        </Card>
      ))}

      {/* Latest Quotes */}
      {quotes.size > 0 && (
        <Card sx={{ mb: 3 }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Latest Quotes
            </Typography>
            
            <TableContainer component={Paper}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Symbol</TableCell>
                    <TableCell align="right">Bid</TableCell>
                    <TableCell align="right">Ask</TableCell>
                    <TableCell align="right">Spread</TableCell>
                    <TableCell align="right">Time</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {Array.from(quotes.entries()).map(([symbol, quote]) => (
                    <TableRow key={symbol}>
                      <TableCell component="th" scope="row">
                        {symbol}
                      </TableCell>
                      <TableCell align="right">{formatPrice(quote.bid)}</TableCell>
                      <TableCell align="right">{formatPrice(quote.ask)}</TableCell>
                      <TableCell align="right">
                        {formatPrice(quote.ask - quote.bid)}
                      </TableCell>
                      <TableCell align="right">
                        {formatTime(quote.timestamp)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </CardContent>
        </Card>
      )}

      {/* Recent Trades */}
      {trades.length > 0 && (
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Recent Trades
            </Typography>
            
            <TableContainer component={Paper} sx={{ maxHeight: 400 }}>
              <Table stickyHeader size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Symbol</TableCell>
                    <TableCell align="right">Price</TableCell>
                    <TableCell align="right">Size</TableCell>
                    <TableCell align="right">Time</TableCell>
                    <TableCell>Provider</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {trades.map((trade, index) => (
                    <TableRow key={index}>
                      <TableCell component="th" scope="row">
                        {trade.symbol}
                      </TableCell>
                      <TableCell align="right">{formatPrice(trade.price)}</TableCell>
                      <TableCell align="right">{trade.size}</TableCell>
                      <TableCell align="right">
                        {formatTime(trade.timestamp)}
                      </TableCell>
                      <TableCell>{trade.provider}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </CardContent>
        </Card>
      )}
    </Box>
  );
};

export default RealTimeDataStream;