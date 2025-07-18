/**
 * Enhanced LiveData Page with Real-Time WebSocket Integration
 * Implements REQ-002: Real-Time Market Data Streaming with WebSocket connections
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Box,
  Paper,
  Typography,
  Grid,
  Card,
  CardContent,
  Button,
  Chip,
  Alert,
  IconButton,
  Tooltip,
  Stack,
  TextField,
  Switch,
  FormControlLabel,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  Divider,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Badge,
  CircularProgress,
  LinearProgress
} from '@mui/material';
import {
  TrendingUp,
  TrendingDown,
  PlayArrow,
  Stop,
  Add,
  Remove,
  Settings,
  Refresh,
  NetworkCheck,
  Speed,
  DataUsage,
  Error as ErrorIcon,
  CheckCircle,
  Warning
} from '@mui/icons-material';
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip as RechartsTooltip } from 'recharts';
import { useAuth } from '../contexts/AuthContext';
import useRealTimeWebSocket from '../hooks/useRealTimeWebSocket';
import ApiKeyStatusIndicator from '../components/ApiKeyStatusIndicator';

const LiveDataEnhanced = () => {
  const { user, isAuthenticated } = useAuth();
  
  // WebSocket hook integration
  const {
    connectionStatus,
    isStreaming,
    isConnected,
    liveData,
    subscribedSymbols,
    connectionStats,
    errors,
    connect,
    disconnect,
    subscribe,
    unsubscribe,
    clearErrors,
    wsUrl
  } = useRealTimeWebSocket();

  // Local state
  const [symbolInput, setSymbolInput] = useState('');
  const [selectedSymbols, setSelectedSymbols] = useState(['AAPL', 'GOOGL', 'MSFT', 'TSLA']);
  const [autoConnect, setAutoConnect] = useState(true);
  const [showErrors, setShowErrors] = useState(true);
  const [chartTimeframe, setChartTimeframe] = useState(60); // seconds
  
  // Chart data processing
  const [chartData, setChartData] = useState({});
  
  // Connection status color mapping
  const getStatusColor = (status) => {
    switch (status) {
      case 'connected': return 'success';
      case 'connecting': return 'warning';
      case 'disconnected': return 'default';
      case 'error': return 'error';
      default: return 'default';
    }
  };

  // Auto-connect on component mount
  useEffect(() => {
    if (autoConnect && isAuthenticated && !isConnected) {
      console.log('🚀 Auto-connecting to WebSocket...');
      connect();
    }
  }, [autoConnect, isAuthenticated, isConnected, connect]);

  // Subscribe to default symbols when connected
  useEffect(() => {
    if (isConnected && selectedSymbols.length > 0) {
      console.log('📈 Auto-subscribing to symbols:', selectedSymbols);
      subscribe(selectedSymbols);
    }
  }, [isConnected, selectedSymbols, subscribe]);

  // Process live data for charts
  useEffect(() => {
    liveData.forEach(dataPoint => {
      if (dataPoint.symbol && dataPoint.price) {
        setChartData(prev => {
          const symbolData = prev[dataPoint.symbol] || [];
          const newPoint = {
            timestamp: new Date(dataPoint.timestamp).getTime(),
            price: parseFloat(dataPoint.price),
            volume: dataPoint.volume || 0
          };
          
          // Keep only last N minutes of data
          const cutoffTime = Date.now() - (chartTimeframe * 1000);
          const filteredData = symbolData.filter(point => point.timestamp > cutoffTime);
          
          return {
            ...prev,
            [dataPoint.symbol]: [...filteredData, newPoint].slice(-100) // Max 100 points
          };
        });
      }
    });
  }, [liveData, chartTimeframe]);

  // Add symbol to subscription
  const addSymbol = useCallback(() => {
    const symbol = symbolInput.trim().toUpperCase();
    if (symbol && !selectedSymbols.includes(symbol)) {
      setSelectedSymbols(prev => [...prev, symbol]);
      if (isConnected) {
        subscribe([symbol]);
      }
      setSymbolInput('');
    }
  }, [symbolInput, selectedSymbols, isConnected, subscribe]);

  // Remove symbol from subscription
  const removeSymbol = useCallback((symbol) => {
    setSelectedSymbols(prev => prev.filter(s => s !== symbol));
    if (isConnected) {
      unsubscribe([symbol]);
    }
  }, [isConnected, unsubscribe]);

  // Handle symbol input enter key
  const handleSymbolKeyPress = (event) => {
    if (event.key === 'Enter') {
      addSymbol();
    }
  };

  // Format price with appropriate decimals
  const formatPrice = (price) => {
    if (!price) return 'N/A';
    return typeof price === 'number' ? price.toFixed(2) : parseFloat(price).toFixed(2);
  };

  // Format change percentage
  const formatChangePercent = (changePercent) => {
    if (!changePercent) return 'N/A';
    const value = typeof changePercent === 'number' ? changePercent : parseFloat(changePercent);
    return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;
  };

  if (!isAuthenticated) {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="warning">
          Please log in to access real-time market data.
        </Alert>
      </Box>
    );
  }

  return (
    <Box sx={{ p: 3, maxWidth: 1400, mx: 'auto' }}>
      {/* Header */}
      <Paper sx={{ p: 3, mb: 3 }}>
        <Grid container alignItems="center" spacing={2}>
          <Grid item xs={12} md={6}>
            <Typography variant="h4" gutterBottom>
              📈 Real-Time Market Data
            </Typography>
            <Typography variant="body1" color="text.secondary">
              Live streaming data via WebSocket connection
            </Typography>
          </Grid>
          <Grid item xs={12} md={6}>
            <Stack direction="row" spacing={2} justifyContent="flex-end" alignItems="center">
              <ApiKeyStatusIndicator />
              <Chip 
                label={connectionStatus.toUpperCase()}
                color={getStatusColor(connectionStatus)}
                icon={isConnected ? <CheckCircle /> : <Warning />}
              />
              <Button
                variant={isStreaming ? "outlined" : "contained"}
                onClick={isStreaming ? disconnect : connect}
                startIcon={isStreaming ? <Stop /> : <PlayArrow />}
                color={isStreaming ? "error" : "primary"}
              >
                {isStreaming ? 'Disconnect' : 'Connect'}
              </Button>
            </Stack>
          </Grid>
        </Grid>
      </Paper>

      {/* Connection Info & Controls */}
      <Grid container spacing={3} sx={{ mb: 3 }}>
        {/* Connection Statistics */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                <NetworkCheck sx={{ mr: 1, verticalAlign: 'middle' }} />
                Connection Stats
              </Typography>
              <Stack spacing={1}>
                <Box display="flex" justifyContent="space-between">
                  <Typography variant="body2">WebSocket URL:</Typography>
                  <Typography variant="body2" color="primary" fontFamily="monospace">
                    {wsUrl.replace('wss://', '').split('.')[0]}...
                  </Typography>
                </Box>
                <Box display="flex" justifyContent="space-between">
                  <Typography variant="body2">Connected Since:</Typography>
                  <Typography variant="body2">
                    {connectionStats.connectedAt ? 
                      new Date(connectionStats.connectedAt).toLocaleTimeString() : 'N/A'}
                  </Typography>
                </Box>
                <Box display="flex" justifyContent="space-between">
                  <Typography variant="body2">Messages Received:</Typography>
                  <Typography variant="body2">{connectionStats.messagesReceived}</Typography>
                </Box>
                <Box display="flex" justifyContent="space-between">
                  <Typography variant="body2">Latency:</Typography>
                  <Typography variant="body2">{connectionStats.latency}ms</Typography>
                </Box>
                <Box display="flex" justifyContent="space-between">
                  <Typography variant="body2">Reconnections:</Typography>
                  <Typography variant="body2">{connectionStats.reconnectCount}</Typography>
                </Box>
              </Stack>
            </CardContent>
          </Card>
        </Grid>

        {/* Symbol Management */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                <Settings sx={{ mr: 1, verticalAlign: 'middle' }} />
                Symbol Management
              </Typography>
              <Stack spacing={2}>
                <Box display="flex" gap={1}>
                  <TextField
                    label="Add Symbol"
                    value={symbolInput}
                    onChange={(e) => setSymbolInput(e.target.value.toUpperCase())}
                    onKeyPress={handleSymbolKeyPress}
                    placeholder="e.g., AAPL"
                    size="small"
                    sx={{ flexGrow: 1 }}
                  />
                  <Button
                    variant="contained"
                    onClick={addSymbol}
                    disabled={!symbolInput.trim()}
                    startIcon={<Add />}
                    size="small"
                  >
                    Add
                  </Button>
                </Box>
                
                <FormControlLabel
                  control={
                    <Switch
                      checked={autoConnect}
                      onChange={(e) => setAutoConnect(e.target.checked)}
                    />
                  }
                  label="Auto-connect on load"
                />
                
                <Typography variant="body2">
                  Subscribed Symbols: {subscribedSymbols.length}
                </Typography>
              </Stack>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Error Display */}
      {showErrors && errors.length > 0 && (
        <Alert 
          severity="error" 
          sx={{ mb: 3 }}
          action={
            <Button color="inherit" size="small" onClick={clearErrors}>
              Clear
            </Button>
          }
        >
          <Typography variant="body2">
            Latest Error: {errors[0]?.message} ({errors.length} total)
          </Typography>
        </Alert>
      )}

      {/* Live Data Table */}
      <Paper sx={{ mb: 3 }}>
        <Box sx={{ p: 2, borderBottom: 1, borderColor: 'divider' }}>
          <Typography variant="h6">
            <DataUsage sx={{ mr: 1, verticalAlign: 'middle' }} />
            Live Market Data ({liveData.length} updates)
          </Typography>
        </Box>
        <TableContainer sx={{ maxHeight: 400 }}>
          <Table stickyHeader size="small">
            <TableHead>
              <TableRow>
                <TableCell>Symbol</TableCell>
                <TableCell align="right">Price</TableCell>
                <TableCell align="right">Change</TableCell>
                <TableCell align="right">Change %</TableCell>
                <TableCell align="right">Volume</TableCell>
                <TableCell align="right">Time</TableCell>
                <TableCell align="center">Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {liveData.map((item) => (
                <TableRow key={item.id} hover>
                  <TableCell>
                    <Stack direction="row" alignItems="center" spacing={1}>
                      <Typography fontWeight="bold">{item.symbol}</Typography>
                      <Chip 
                        label={item.dataType} 
                        size="small" 
                        color="primary" 
                        variant="outlined" 
                      />
                    </Stack>
                  </TableCell>
                  <TableCell align="right">
                    <Typography fontFamily="monospace">
                      ${formatPrice(item.price)}
                    </Typography>
                  </TableCell>
                  <TableCell align="right">
                    <Typography 
                      color={item.change >= 0 ? 'success.main' : 'error.main'}
                      fontFamily="monospace"
                    >
                      {item.change >= 0 ? '+' : ''}{formatPrice(item.change)}
                    </Typography>
                  </TableCell>
                  <TableCell align="right">
                    <Stack direction="row" alignItems="center" justifyContent="flex-end" spacing={0.5}>
                      {item.changePercent >= 0 ? <TrendingUp color="success" /> : <TrendingDown color="error" />}
                      <Typography 
                        color={item.changePercent >= 0 ? 'success.main' : 'error.main'}
                        fontFamily="monospace"
                      >
                        {formatChangePercent(item.changePercent)}
                      </Typography>
                    </Stack>
                  </TableCell>
                  <TableCell align="right">
                    <Typography fontFamily="monospace">
                      {item.volume?.toLocaleString() || 'N/A'}
                    </Typography>
                  </TableCell>
                  <TableCell align="right">
                    <Typography variant="body2" color="text.secondary">
                      {new Date(item.timestamp).toLocaleTimeString()}
                    </Typography>
                  </TableCell>
                  <TableCell align="center">
                    <IconButton
                      size="small"
                      onClick={() => removeSymbol(item.symbol)}
                      color="error"
                    >
                      <Remove />
                    </IconButton>
                  </TableCell>
                </TableRow>
              ))}
              {liveData.length === 0 && (
                <TableRow>
                  <TableCell colSpan={7} align="center">
                    <Typography color="text.secondary" sx={{ py: 3 }}>
                      {isConnected ? 'Waiting for market data...' : 'Connect to start receiving data'}
                    </Typography>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </TableContainer>
      </Paper>

      {/* Real-Time Charts */}
      <Grid container spacing={3}>
        {selectedSymbols.map(symbol => (
          <Grid item xs={12} md={6} lg={4} key={symbol}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  {symbol} Price Chart
                </Typography>
                <Box sx={{ height: 200, width: '100%' }}>
                  {chartData[symbol] && chartData[symbol].length > 0 ? (
                    <ResponsiveContainer>
                      <LineChart data={chartData[symbol]}>
                        <XAxis 
                          dataKey="timestamp" 
                          type="number"
                          scale="time"
                          domain={['dataMin', 'dataMax']}
                          tickFormatter={(value) => new Date(value).toLocaleTimeString()}
                        />
                        <YAxis 
                          domain={['dataMin', 'dataMax']}
                          tickFormatter={(value) => `$${value.toFixed(2)}`}
                        />
                        <RechartsTooltip
                          labelFormatter={(value) => new Date(value).toLocaleTimeString()}
                          formatter={(value) => [`$${value.toFixed(2)}`, 'Price']}
                        />
                        <Line 
                          type="monotone" 
                          dataKey="price" 
                          stroke="#1976d2" 
                          strokeWidth={2}
                          dot={false}
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  ) : (
                    <Box 
                      display="flex" 
                      alignItems="center" 
                      justifyContent="center" 
                      height="100%"
                    >
                      <Typography color="text.secondary">
                        {isConnected ? 'Waiting for data...' : 'Connect to view chart'}
                      </Typography>
                    </Box>
                  )}
                </Box>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>

      {/* Loading indicator */}
      {connectionStatus === 'connecting' && (
        <Box sx={{ position: 'fixed', top: 0, left: 0, right: 0, zIndex: 1300 }}>
          <LinearProgress />
        </Box>
      )}
    </Box>
  );
};

export default LiveDataEnhanced;