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
import useRealTimeLiveData from '../hooks/useRealTimeLiveData';
import ApiKeyStatusIndicator from '../components/ApiKeyStatusIndicator';

const LiveDataEnhanced = () => {
  const { user, isAuthenticated } = useAuth();
  
  // Real-time live data hook integration
  const {
    connectionStatus,
    isStreaming,
    isConnected,
    liveData,
    subscribedSymbols,
    connectionStats,
    errors,
    startStreaming,
    stopStreaming,
    subscribe,
    unsubscribe,
    refresh,
    clearErrors,
    pollingInterval,
    updatePollingInterval,
    formatPrice,
    formatChangePercent
  } = useRealTimeLiveData();

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
      case 'streaming': return 'success';
      case 'stopped': return 'default';
      case 'error': return 'error';
      default: return 'default';
    }
  };

  // Auto-connect is handled by the hook itself

  // Subscribe to default symbols when needed
  useEffect(() => {
    if (selectedSymbols.length > 0 && subscribedSymbols.length === 0) {
      console.log('📈 Auto-subscribing to symbols:', selectedSymbols);
      subscribe(selectedSymbols);
    }
  }, [selectedSymbols, subscribedSymbols.length, subscribe]);

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

  // Format functions provided by the hook

  if (!isAuthenticated) {
    return (
      <div  sx={{ p: 3 }}>
        <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="warning">
          Please log in to access real-time market data.
        </div>
      </div>
    );
  }

  return (
    <div  sx={{ p: 3, maxWidth: 1400, mx: 'auto' }}>
      {/* Header */}
      <div className="bg-white shadow-md rounded-lg p-4" sx={{ p: 3, mb: 3 }}>
        <div className="grid" container alignItems="center" spacing={2}>
          <div className="grid" item xs={12} md={6}>
            <div  variant="h4" gutterBottom>
              📈 Real-Time Market Data
            </div>
            <div  variant="body1" color="text.secondary">
              Live streaming data via WebSocket connection
            </div>
          </div>
          <div className="grid" item xs={12} md={6}>
            <div className="flex flex-col space-y-2" direction="row" spacing={2} justifyContent="flex-end" alignItems="center">
              <ApiKeyStatusIndicator />
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                label={connectionStatus.toUpperCase()}
                color={getStatusColor(connectionStatus)}
                icon={isConnected ? <CheckCircle /> : <Warning />}
              />
              <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                variant={isStreaming ? "outlined" : "contained"}
                onClick={isStreaming ? stopStreaming : startStreaming}
                startIcon={isStreaming ? <Stop /> : <PlayArrow />}
                color={isStreaming ? "error" : "primary"}
              >
                {isStreaming ? 'Stop Stream' : 'Start Stream'}
              </button>
              <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                variant="outlined"
                onClick={refresh}
                startIcon={<Refresh />}
                disabled={!isAuthenticated}
              >
                Refresh
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Connection Info & Controls */}
      <div className="grid" container spacing={3} sx={{ mb: 3 }}>
        {/* Connection Statistics */}
        <div className="grid" item xs={12} md={6}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  variant="h6" gutterBottom>
                <NetworkCheck sx={{ mr: 1, verticalAlign: 'middle' }} />
                Live Data Stats
              </div>
              <div className="flex flex-col space-y-2" spacing={1}>
                <div  display="flex" justifyContent="space-between">
                  <div  variant="body2">API Endpoint:</div>
                  <div  variant="body2" color="primary" fontFamily="monospace">
                    /api/live-data/stream
                  </div>
                </div>
                <div  display="flex" justifyContent="space-between">
                  <div  variant="body2">Started:</div>
                  <div  variant="body2">
                    {connectionStats.startedAt ? 
                      new Date(connectionStats.startedAt).toLocaleTimeString() : 'N/A'}
                  </div>
                </div>
                <div  display="flex" justifyContent="space-between">
                  <div  variant="body2">Requests:</div>
                  <div  variant="body2">{connectionStats.requestCount}</div>
                </div>
                <div  display="flex" justifyContent="space-between">
                  <div  variant="body2">Success Rate:</div>
                  <div  variant="body2">
                    {connectionStats.requestCount > 0 ? 
                      Math.round((connectionStats.successCount / connectionStats.requestCount) * 100) : 0}%
                  </div>
                </div>
                <div  display="flex" justifyContent="space-between">
                  <div  variant="body2">Latency:</div>
                  <div  variant="body2">{connectionStats.latency}ms</div>
                </div>
                <div  display="flex" justifyContent="space-between">
                  <div  variant="body2">Polling Interval:</div>
                  <div  variant="body2">{pollingInterval / 1000}s</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Symbol Management */}
        <div className="grid" item xs={12} md={6}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  variant="h6" gutterBottom>
                <Settings sx={{ mr: 1, verticalAlign: 'middle' }} />
                Symbol Management
              </div>
              <div className="flex flex-col space-y-2" spacing={2}>
                <div  display="flex" gap={1}>
                  <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    label="Add Symbol"
                    value={symbolInput}
                    onChange={(e) => setSymbolInput(e.target.value.toUpperCase())}
                    onKeyPress={handleSymbolKeyPress}
                    placeholder="e.g., AAPL"
                    size="small"
                    sx={{ flexGrow: 1 }}
                  />
                  <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                    variant="contained"
                    onClick={addSymbol}
                    disabled={!symbolInput.trim()}
                    startIcon={<Add />}
                    size="small"
                  >
                    Add
                  </button>
                </div>
                
                <div className="mb-4"Label
                  control={
                    <input type="checkbox" className="toggle"
                      checked={autoConnect}
                      onChange={(e) => setAutoConnect(e.target.checked)}
                    />
                  }
                  label="Auto-connect on load"
                />
                
                <div  variant="body2">
                  Subscribed Symbols: {subscribedSymbols.length}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Error Display */}
      {showErrors && errors.length > 0 && (
        <div className="p-4 rounded-md bg-blue-50 border border-blue-200" 
          severity="error" 
          sx={{ mb: 3 }}
          action={
            <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" color="inherit" size="small" onClick={clearErrors}>
              Clear
            </button>
          }
        >
          <div  variant="body2">
            Latest Error: {errors[0]?.message} ({errors.length} total)
          </div>
        </div>
      )}

      {/* Live Data Table */}
      <div className="bg-white shadow-md rounded-lg p-4" sx={{ mb: 3 }}>
        <div  sx={{ p: 2, borderBottom: 1, borderColor: 'divider' }}>
          <div  variant="h6">
            <DataUsage sx={{ mr: 1, verticalAlign: 'middle' }} />
            Live Market Data ({liveData.length} updates)
          </div>
        </div>
        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer sx={{ maxHeight: 400 }}>
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le stickyHeader size="small">
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Symbol</td>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Price</td>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Change</td>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Change %</td>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Volume</td>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Time</td>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center">Actions</td>
              </tr>
            </thead>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
              {liveData.map((item) => (
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={item.id} hover>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                    <div className="flex flex-col space-y-2" direction="row" alignItems="center" spacing={1}>
                      <div  fontWeight="bold">{item.symbol}</div>
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                        label={item.dataType} 
                        size="small" 
                        color="primary" 
                        variant="outlined" 
                      />
                    </div>
                  </td>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                    <div  fontFamily="monospace">
                      ${formatPrice(item.price)}
                    </div>
                  </td>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                    <div  
                      color={item.change >= 0 ? 'success.main' : 'error.main'}
                      fontFamily="monospace"
                    >
                      {item.change >= 0 ? '+' : ''}{formatPrice(item.change)}
                    </div>
                  </td>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                    <div className="flex flex-col space-y-2" direction="row" alignItems="center" justifyContent="flex-end" spacing={0.5}>
                      {item.changePercent >= 0 ? <TrendingUp color="success" /> : <TrendingDown color="error" />}
                      <div  
                        color={item.changePercent >= 0 ? 'success.main' : 'error.main'}
                        fontFamily="monospace"
                      >
                        {formatChangePercent(item.changePercent)}
                      </div>
                    </div>
                  </td>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                    <div  fontFamily="monospace">
                      {item.volume?.toLocaleString() || 'N/A'}
                    </div>
                  </td>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                    <div  variant="body2" color="text.secondary">
                      {new Date(item.timestamp).toLocaleTimeString()}
                    </div>
                  </td>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center">
                    <button className="p-2 rounded-full hover:bg-gray-100"
                      size="small"
                      onClick={() => removeSymbol(item.symbol)}
                      color="error"
                    >
                      <Remove />
                    </button>
                  </td>
                </tr>
              ))}
              {liveData.length === 0 && (
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell colSpan={7} align="center">
                    <div  color="text.secondary" sx={{ py: 3 }}>
                      {isConnected ? 'Waiting for market data...' : 'Connect to start receiving data'}
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Real-Time Charts */}
      <div className="grid" container spacing={3}>
        {selectedSymbols.map(symbol => (
          <div className="grid" item xs={12} md={6} lg={4} key={symbol}>
            <div className="bg-white shadow-md rounded-lg">
              <div className="bg-white shadow-md rounded-lg"Content>
                <div  variant="h6" gutterBottom>
                  {symbol} Price Chart
                </div>
                <div  sx={{ height: 200, width: '100%' }}>
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
                    <div  
                      display="flex" 
                      alignItems="center" 
                      justifyContent="center" 
                      height="100%"
                    >
                      <div  color="text.secondary">
                        {isConnected ? 'Waiting for data...' : 'Connect to view chart'}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Loading indicator */}
      {isStreaming && (
        <div  sx={{ position: 'fixed', top: 0, left: 0, right: 0, zIndex: 1300 }}>
          <div className="w-full bg-gray-200 rounded-full h-2" />
        </div>
      )}
    </div>
  );
};

export default LiveDataEnhanced;