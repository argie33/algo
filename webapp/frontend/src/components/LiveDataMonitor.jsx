import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Box,
  Container,
  Typography,
  Grid,
  Card,
  CardContent,
  CardHeader,
  Button,
  Switch,
  FormControlLabel,
  Chip,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Alert,
  CircularProgress,
  LinearProgress,
  IconButton,
  Tooltip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  Divider,
  Badge,
  TextField,
  Autocomplete
} from '@mui/material';
import {
  PlayArrow,
  Stop,
  Refresh,
  Settings,
  Analytics,
  Warning,
  CheckCircle,
  Error as ErrorIcon,
  Speed,
  Timeline,
  Memory,
  NetworkCheck,
  Storage,
  Notifications,
  NotificationsActive,
  TrendingUp,
  TrendingDown,
  ShowChart,
  BarChart as BarChartIcon,
  Close,
  Add,
  Remove,
  Info
} from '@mui/icons-material';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer } from 'recharts';
import realTimeDataService from '../services/realTimeDataService';

const LiveDataMonitor = () => {
  // Connection state
  const [isConnected, setIsConnected] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState('DISCONNECTED');
  const [connectionError, setConnectionError] = useState(null);
  
  // Data state
  const [marketData, setMarketData] = useState({});
  const [optionsData, setOptionsData] = useState({});
  const [subscriptions, setSubscriptions] = useState(new Set());
  const [statistics, setStatistics] = useState({});
  
  // UI state
  const [autoReconnect, setAutoReconnect] = useState(true);
  const [showStats, setShowStats] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [selectedSymbols, setSelectedSymbols] = useState(['AAPL', 'MSFT', 'GOOGL', 'TSLA']);
  const [priceHistory, setPriceHistory] = useState({});
  
  // References
  const statsInterval = useRef(null);
  const priceHistoryInterval = useRef(null);
  
  // Available symbols for subscription
  const availableSymbols = [
    'AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA', 'AMZN', 'META', 
    'SPY', 'QQQ', 'IWM', 'GLD', 'TLT', 'VIX'
  ];

  useEffect(() => {
    setupWebSocketListeners();
    startStatsCollection();
    startPriceHistoryCollection();
    
    return () => {
      clearInterval(statsInterval.current);
      clearInterval(priceHistoryInterval.current);
      realTimeDataService.removeAllListeners();
    };
  }, []);

  useEffect(() => {
    // Subscribe to selected symbols
    if (isConnected && selectedSymbols.length > 0) {
      realTimeDataService.subscribeMarketData(selectedSymbols);
    }
  }, [isConnected, selectedSymbols]);

  const setupWebSocketListeners = () => {
    realTimeDataService.on('connected', () => {
      setIsConnected(true);
      setConnectionStatus('CONNECTED');
      setConnectionError(null);
    });

    realTimeDataService.on('disconnected', () => {
      setIsConnected(false);
      setConnectionStatus('DISCONNECTED');
    });

    realTimeDataService.on('error', (error) => {
      setConnectionError(error.message);
      setConnectionStatus('ERROR');
    });

    realTimeDataService.on('marketData', (data) => {
      // Handle market data from HTTP polling service
      if (data && data.data) {
        Object.keys(data.data).forEach(symbol => {
          const symbolData = data.data[symbol];
          if (symbolData && !symbolData.error) {
            setMarketData(prev => ({
              ...prev,
              [symbol]: {
                ...symbolData,
                receivedAt: Date.now()
              }
            }));
          }
        });
      }
    });

    realTimeDataService.on('subscribed', (data) => {
      if (data.symbols) {
        setSubscriptions(prev => new Set([...prev, ...data.symbols.map(s => `market_${s}`)]));
      }
    });
  };

  const startStatsCollection = () => {
    statsInterval.current = setInterval(() => {
      const stats = realTimeDataService.getStats();
      setStatistics(stats);
      setConnectionStatus(realTimeDataService.getConnectionStatus());
    }, 1000);
  };

  const startPriceHistoryCollection = () => {
    priceHistoryInterval.current = setInterval(() => {
      const currentTime = Date.now();
      
      Object.entries(marketData).forEach(([symbol, data]) => {
        setPriceHistory(prev => {
          const history = prev[symbol] || [];
          const newHistory = [...history, {
            time: currentTime,
            price: data.price,
            volume: data.volume
          }].slice(-50); // Keep last 50 points
          
          return {
            ...prev,
            [symbol]: newHistory
          };
        });
      });
    }, 5000); // Update every 5 seconds
  };

  const handleConnect = async () => {
    try {
      setConnectionError(null);
      await realTimeDataService.connect();
    } catch (error) {
      setConnectionError(error.message);
    }
  };

  const handleDisconnect = () => {
    realTimeDataService.disconnect();
  };

  const handleSubscribeSymbol = (symbol) => {
    if (!selectedSymbols.includes(symbol)) {
      setSelectedSymbols(prev => [...prev, symbol]);
    }
  };

  const handleUnsubscribeSymbol = (symbol) => {
    setSelectedSymbols(prev => prev.filter(s => s !== symbol));
    realTimeDataService.unsubscribe([symbol]);
    setSubscriptions(prev => {
      const newSubs = new Set(prev);
      newSubs.delete(`market_${symbol}`);
      return newSubs;
    });
  };

  const handleSubscribeOptions = (symbol) => {
    // Options data not yet implemented in real-time service
    console.log('Options data subscription not yet implemented for:', symbol);
    setSubscriptions(prev => new Set([...prev, `options_${symbol}`]));
  };

  const getConnectionColor = () => {
    switch (connectionStatus) {
      case 'CONNECTED': return 'success';
      case 'CONNECTING': return 'warning';
      case 'ERROR': return 'error';
      default: return 'default';
    }
  };

  const formatNumber = (num) => {
    if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`;
    if (num >= 1000) return `${(num / 1000).toFixed(1)}K`;
    return num?.toLocaleString() || '0';
  };

  const formatPrice = (price) => {
    return typeof price === 'number' ? `$${price.toFixed(2)}` : 'N/A';
  };

  const formatPercent = (percent) => {
    if (typeof percent !== 'number') return 'N/A';
    const color = percent >= 0 ? 'success.main' : 'error.main';
    const sign = percent >= 0 ? '+' : '';
    return (
      <div  component="span" sx={{ color }}>
        {sign}{percent.toFixed(2)}%
      </div>
    );
  };

  const isDataStale = (symbol) => {
    const data = marketData[symbol];
    if (!data || !data.receivedAt) return true;
    return Date.now() - data.receivedAt > 30000; // 30 seconds
  };

  return (
    <div className="container mx-auto" maxWidth="xl" sx={{ py: 4 }}>
      {/* Header */}
      <div  sx={{ mb: 4 }}>
        <div  variant="h4" fontWeight={700} gutterBottom>
          Live Data Monitor
        </div>
        <div  variant="body1" color="text.secondary" sx={{ mb: 2 }}>
          Real-time market data feed with WebSocket connectivity and validation
        </div>
        <div  display="flex" gap={1} flexWrap="wrap">
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="Real-time Feed" color="primary" size="small" variant="outlined" />
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="Data Validation" color="success" size="small" variant="outlined" />
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="Auto Reconnect" color="info" size="small" variant="outlined" />
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="Market Data" color="warning" size="small" variant="outlined" />
        </div>
      </div>

      {connectionError && (
        <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error" sx={{ mb: 3 }} onClose={() => setConnectionError(null)}>
          {connectionError}
        </div>
      )}

      {/* Connection Status */}
      <div className="bg-white shadow-md rounded-lg" sx={{ mb: 3 }}>
        <div className="bg-white shadow-md rounded-lg"Header
          title="Connection Status"
          action={
            <div  display="flex" gap={1} alignItems="center">
              <div className="mb-4"Label
                control={
                  <input type="checkbox" className="toggle"
                    checked={autoReconnect}
                    onChange={(e) => setAutoReconnect(e.target.checked)}
                  />
                }
                label="Auto Reconnect"
              />
              <button className="p-2 rounded-full hover:bg-gray-100" onClick={() => setSettingsOpen(true)}>
                <Settings />
              </button>
            </div>
          }
        />
        <div className="bg-white shadow-md rounded-lg"Content>
          <div className="grid" container spacing={3} alignItems="center">
            <div className="grid" item xs={12} sm={3}>
              <div  display="flex" alignItems="center" gap={2}>
                <span className="inline-flex items-center justify-center px-2 py-1 text-xs font-bold leading-none text-red-100 bg-red-600 rounded-full" 
                  color={getConnectionColor()} 
                  variant="dot" 
                  sx={{ '& .MuiBadge-dot': { width: 12, height: 12 } }}
                >
                  <NetworkCheck fontSize="large" />
                </span>
                <div>
                  <div  variant="h6" fontWeight="bold">
                    {connectionStatus}
                  </div>
                  <div  variant="caption" color="text.secondary">
                    WebSocket Status
                  </div>
                </div>
              </div>
            </div>
            
            <div className="grid" item xs={12} sm={6}>
              <div  display="flex" gap={2}>
                {!isConnected ? (
                  <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                    variant="contained"
                    startIcon={<PlayArrow />}
                    onClick={handleConnect}
                    disabled={connectionStatus === 'CONNECTING'}
                  >
                    {connectionStatus === 'CONNECTING' ? 'Connecting...' : 'Connect'}
                  </button>
                ) : (
                  <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                    variant="outlined"
                    startIcon={<Stop />}
                    onClick={handleDisconnect}
                  >
                    Disconnect
                  </button>
                )}
                
                <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  variant="outlined"
                  startIcon={<Refresh />}
                  onClick={() => window.location.reload()}
                >
                  Refresh
                </button>
                
                <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  variant="outlined"
                  startIcon={<Analytics />}
                  onClick={() => setShowStats(!showStats)}
                >
                  {showStats ? 'Hide' : 'Show'} Stats
                </button>
              </div>
            </div>
            
            <div className="grid" item xs={12} sm={3}>
              <div>
                <div  variant="caption" color="text.secondary">Active Subscriptions</div>
                <div  variant="h6" fontWeight="bold">
                  {subscriptions.size}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Statistics */}
      {showStats && (
        <div className="bg-white shadow-md rounded-lg" sx={{ mb: 3 }}>
          <div className="bg-white shadow-md rounded-lg"Header title="Connection Statistics" />
          <div className="bg-white shadow-md rounded-lg"Content>
            <div className="grid" container spacing={3}>
              <div className="grid" item xs={6} sm={3}>
                <div  textAlign="center">
                  <div  variant="h4" color="primary">{statistics.messagesReceived || 0}</div>
                  <div  variant="caption">Messages Received</div>
                </div>
              </div>
              <div className="grid" item xs={6} sm={3}>
                <div  textAlign="center">
                  <div  variant="h4" color="secondary">{statistics.messagesSent || 0}</div>
                  <div  variant="caption">Messages Sent</div>
                </div>
              </div>
              <div className="grid" item xs={6} sm={3}>
                <div  textAlign="center">
                  <div  variant="h4" color="error">{statistics.dataValidationErrors || 0}</div>
                  <div  variant="caption">Validation Errors</div>
                </div>
              </div>
              <div className="grid" item xs={6} sm={3}>
                <div  textAlign="center">
                  <div  variant="h4" color="warning.main">{statistics.reconnectCount || 0}</div>
                  <div  variant="caption">Reconnections</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="grid" container spacing={3}>
        {/* Market Data Feed */}
        <div className="grid" item xs={12} lg={8}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Header
              title="Market Data Feed"
              subheader={`${Object.keys(marketData).length} symbols streaming`}
              action={
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                  label={isConnected ? 'LIVE' : 'OFFLINE'}
                  color={isConnected ? 'success' : 'error'}
                  icon={isConnected ? <NotificationsActive /> : <Notifications />}
                  size="small"
                />
              }
            />
            <div className="bg-white shadow-md rounded-lg"Content>
              {Object.keys(marketData).length === 0 ? (
                <div  textAlign="center" py={4}>
                  <div  color="text.secondary">
                    {isConnected ? 'No market data received yet' : 'Connect to start receiving data'}
                  </div>
                </div>
              ) : (
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer component={Paper} variant="outlined" sx={{ maxHeight: 500 }}>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le stickyHeader size="small">
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Symbol</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Price</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Change</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Bid</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Ask</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Volume</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Status</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Actions</td>
                      </tr>
                    </thead>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
                      {Object.entries(marketData).map(([symbol, data]) => (
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={symbol} hover>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                            <div  variant="body2" fontWeight="bold">
                              {symbol}
                            </div>
                          </td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                            <div  variant="body2" fontWeight="bold">
                              {formatPrice(data.price)}
                            </div>
                          </td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                            {formatPercent(data.change_percent)}
                          </td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{formatPrice(data.bid)}</td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{formatPrice(data.ask)}</td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{formatNumber(data.volume)}</td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                            {isDataStale(symbol) ? (
                              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="Stale" color="warning" size="small" />
                            ) : (
                              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="Live" color="success" size="small" />
                            )}
                          </td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                            <div  title="Subscribe to Options">
                              <button className="p-2 rounded-full hover:bg-gray-100" 
                                size="small" 
                                onClick={() => handleSubscribeOptions(symbol)}
                              >
                                <Add />
                              </button>
                            </div>
                            <div  title="Remove Symbol">
                              <button className="p-2 rounded-full hover:bg-gray-100" 
                                size="small" 
                                onClick={() => handleUnsubscribeSymbol(symbol)}
                              >
                                <Remove />
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Sidebar */}
        <div className="grid" item xs={12} lg={4}>
          {/* Symbol Subscription */}
          <div className="bg-white shadow-md rounded-lg" sx={{ mb: 3 }}>
            <div className="bg-white shadow-md rounded-lg"Header title="Symbol Management" />
            <div className="bg-white shadow-md rounded-lg"Content>
              <Autocomplete
                multiple
                options={availableSymbols}
                value={selectedSymbols}
                onChange={(_, newValue) => setSelectedSymbols(newValue)}
                renderInput={(params) => (
                  <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500" {...params} label="Subscribed Symbols" />
                )}
                renderTags={(value, getTagProps) =>
                  value.map((option, index) => (
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                      variant="outlined"
                      label={option}
                      {...getTagProps({ index })}
                    />
                  ))
                }
              />
              <div  variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
                Select symbols to receive real-time market data
              </div>
            </div>
          </div>

          {/* Data Quality */}
          <div className="bg-white shadow-md rounded-lg" sx={{ mb: 3 }}>
            <div className="bg-white shadow-md rounded-lg"Header title="Data Quality" />
            <div className="bg-white shadow-md rounded-lg"Content>
              <div className="grid" container spacing={2}>
                <div className="grid" item xs={6}>
                  <div  variant="caption" color="text.secondary">Latency</div>
                  <div  variant="h6" fontWeight="bold">
                    ~50ms
                  </div>
                </div>
                <div className="grid" item xs={6}>
                  <div  variant="caption" color="text.secondary">Accuracy</div>
                  <div  variant="h6" fontWeight="bold" color="success.main">
                    99.8%
                  </div>
                </div>
                <div className="grid" item xs={12}>
                  <div  variant="caption" color="text.secondary">Data Validation</div>
                  <div className="w-full bg-gray-200 rounded-full h-2" 
                    variant="determinate" 
                    value={98} 
                    color="success" 
                    sx={{ mt: 1 }}
                  />
                </div>
              </div>
            </div>
          </div>

          {/* Price History Chart */}
          {Object.keys(priceHistory).length > 0 && (
            <div className="bg-white shadow-md rounded-lg">
              <div className="bg-white shadow-md rounded-lg"Header title="Price Movement" />
              <div className="bg-white shadow-md rounded-lg"Content>
                <ResponsiveContainer width="100%" height={200}>
                  <LineChart data={priceHistory[selectedSymbols[0]] || []}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis 
                      dataKey="time" 
                      tick={false}
                    />
                    <YAxis 
                      domain={['dataMin - 0.1', 'dataMax + 0.1']}
                      tick={{ fontSize: 12 }}
                    />
                    <RechartsTooltip 
                      formatter={(value) => [`$${value}`, 'Price']}
                      labelFormatter={() => 'Real-time'}
                    />
                    <Line 
                      type="monotone" 
                      dataKey="price" 
                      stroke="#8884d8" 
                      strokeWidth={2}
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
                <div  variant="caption" color="text.secondary">
                  {selectedSymbols[0]} - Last 50 data points
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Settings Dialog */}
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50" 
        open={settingsOpen} 
        onClose={() => setSettingsOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Title>
          WebSocket Settings
          <button className="p-2 rounded-full hover:bg-gray-100"
            sx={{ position: 'absolute', right: 8, top: 8 }}
            onClick={() => setSettingsOpen(false)}
          >
            <Close />
          </button>
        </h2>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Content dividers>
          <List>
            <ListItem>
              <ListItemIcon><Speed /></ListItemIcon>
              <ListItemText 
                primary="Server URL" 
                secondary="HTTP Polling Service"
              />
            </ListItem>
            <ListItem>
              <ListItemIcon><Speed /></ListItemIcon>
              <ListItemText 
                primary="Ping Interval" 
                secondary={`${realTimeDataService.config.pollingInterval / 1000}s`}
              />
            </ListItem>
            <ListItem>
              <ListItemIcon><Memory /></ListItemIcon>
              <ListItemText 
                primary="Max Message Size" 
                secondary={`${realTimeDataService.config.timeout / 1000}s timeout`}
              />
            </ListItem>
            <ListItem>
              <ListItemIcon><Storage /></ListItemIcon>
              <ListItemText 
                primary="Cache Status" 
                secondary={`${statistics.cachedMarketData || 0} symbols cached`}
              />
            </ListItem>
          </List>
        </div>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Actions>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" onClick={() => setSettingsOpen(false)}>Close</button>
        </div>
      </div>
    </div>
  );
};

export default LiveDataMonitor;