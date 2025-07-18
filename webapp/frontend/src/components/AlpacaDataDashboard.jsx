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
    <div  sx={{ p: 3 }}>
      <div  variant="h4" gutterBottom>
        Alpaca Real-time Data Dashboard
      </div>
      <div  variant="subtitle1" color="text.secondary" gutterBottom>
        Professional-grade market data streaming with HFT capabilities
      </div>

      {/* Connection Status & Controls */}
      <div className="grid" container spacing={3} sx={{ mb: 3 }}>
        <div className="grid" item xs={12} md={6}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
                <div  sx={{ display: 'flex', alignItems: 'center' }}>
                  {getStatusIcon()}
                  <div  variant="h6" sx={{ ml: 1 }}>
                    Connection Status
                  </div>
                </div>
                <div className="mb-4"Label
                  control={
                    <input type="checkbox" className="toggle"
                      checked={autoReconnect}
                      onChange={(e) => setAutoReconnect(e.target.checked)}
                      size="small"
                    />
                  }
                  label="Auto-reconnect"
                />
              </div>
              
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                label={connectionStatus} 
                color={getStatusColor()} 
                variant="outlined"
                sx={{ mb: 2 }}
              />
              
              <div  sx={{ display: 'flex', gap: 1 }}>
                <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
                  variant="contained" 
                  startIcon={<PlayArrow />}
                  onClick={handleConnect}
                  disabled={connectionStatus === 'CONNECTED' || connectionStatus === 'CONNECTING'}
                >
                  Connect
                </button>
                <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
                  variant="outlined" 
                  startIcon={<Stop />}
                  onClick={handleDisconnect}
                  disabled={connectionStatus === 'DISCONNECTED'}
                >
                  Disconnect
                </button>
              </div>
            </div>
          </div>
        </div>

        <div className="grid" item xs={12} md={6}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  variant="h6" gutterBottom>
                Performance Metrics
              </div>
              <div className="grid" container spacing={2}>
                <div className="grid" item xs={6}>
                  <div  variant="body2" color="text.secondary">
                    Latency (Avg)
                  </div>
                  <div  variant="h6" color="primary">
                    {formatLatency(metrics.avgLatency)}
                  </div>
                </div>
                <div className="grid" item xs={6}>
                  <div  variant="body2" color="text.secondary">
                    Messages/sec
                  </div>
                  <div  variant="h6" color="primary">
                    {Math.round((metrics.messagesReceived || 0) / Math.max(1, (metrics.connectionUptime || 1) / 1000))}
                  </div>
                </div>
                <div className="grid" item xs={6}>
                  <div  variant="body2" color="text.secondary">
                    Uptime
                  </div>
                  <div  variant="h6">
                    {Math.round((metrics.connectionUptime || 0) / 1000)}s
                  </div>
                </div>
                <div className="grid" item xs={6}>
                  <div  variant="body2" color="text.secondary">
                    Subscriptions
                  </div>
                  <div  variant="h6">
                    {metrics.subscriptionsCount || 0}
                  </div>
                </div>
              </div>
              
              {/* Data type specific metrics */}
              <hr className="border-gray-200" sx={{ my: 1 }} />
              <div className="grid" container spacing={1}>
                <div className="grid" item xs={3}>
                  <div  variant="caption" color="text.secondary">
                    Quotes: {metrics.quotesReceived || 0}
                  </div>
                </div>
                <div className="grid" item xs={3}>
                  <div  variant="caption" color="text.secondary">
                    Trades: {metrics.tradesReceived || 0}
                  </div>
                </div>
                <div className="grid" item xs={3}>
                  <div  variant="caption" color="text.secondary">
                    Bars: {metrics.barsReceived || 0}
                  </div>
                </div>
                <div className="grid" item xs={3}>
                  <div  variant="caption" color="text.secondary">
                    News: {metrics.newsReceived || 0}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Error Alert */}
      {error && (
        <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error" sx={{ mb: 3 }} onClose={() => setError(null)}>
          {error}
        </div>
      )}

      {/* Main Content Tabs */}
      <div className="bg-white shadow-md rounded-lg" sx={{ mb: 3 }}>
        <div className="border-b border-gray-200" 
          value={activeTab} 
          onChange={(e, newValue) => setActiveTab(newValue)}
          sx={{ borderBottom: 1, borderColor: 'divider' }}
        >
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Subscriptions" />
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Market Data" />
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Available Feeds" />
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Activity Log" />
        </div>

        {/* Subscriptions Tab */}
        {activeTab === 0 && (
          <div className="bg-white shadow-md rounded-lg"Content>
            <div  variant="h6" gutterBottom>
              Manage Data Subscriptions
            </div>
            
            {/* Quick Subscription Buttons */}
            <div  sx={{ mb: 3 }}>
              <div  variant="subtitle2" gutterBottom>
                Quick Subscriptions:
              </div>
              <div  sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                {quickSubscriptions.map((quickSub, index) => (
                  <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                    key={index}
                    variant="outlined"
                    size="small"
                    onClick={() => handleQuickSubscribe(quickSub)}
                    disabled={connectionStatus !== 'CONNECTED'}
                  >
                    {quickSub.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Custom Subscription Form */}
            <div  sx={{ display: 'flex', flexWrap: 'wrap', gap: 2, mb: 3 }}>
              <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                size="small"
                label="Symbol (e.g., AAPL)"
                value={newSymbol}
                onChange={(e) => setNewSymbol(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && handleSubscribe()}
                disabled={connectionStatus !== 'CONNECTED'}
                sx={{ minWidth: 150 }}
              />
              
              <div className="mb-4" size="small" sx={{ minWidth: 120 }}>
                <label className="block text-sm font-medium text-gray-700 mb-1">Data Type</label>
                <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={selectedDataType}
                  onChange={(e) => setSelectedDataType(e.target.value)}
                  label="Data Type"
                >
                  <option  value="quotes">Quotes</option>
                  <option  value="trades">Trades</option>
                  <option  value="bars">Bars</option>
                  <option  value="news">News</option>
                  <option  value="crypto">Crypto</option>
                </select>
              </div>
              
              {selectedDataType === 'bars' && (
                <div className="mb-4" size="small" sx={{ minWidth: 100 }}>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Frequency</label>
                  <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={selectedFrequency}
                    onChange={(e) => setSelectedFrequency(e.target.value)}
                    label="Frequency"
                  >
                    <option  value="1Min">1 Min</option>
                    <option  value="5Min">5 Min</option>
                    <option  value="15Min">15 Min</option>
                    <option  value="1Hour">1 Hour</option>
                    <option  value="1Day">1 Day</option>
                  </select>
                </div>
              )}
              
              <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
                variant="contained" 
                startIcon={<Add />}
                onClick={handleSubscribe}
                disabled={connectionStatus !== 'CONNECTED' || !newSymbol.trim()}
              >
                Subscribe
              </button>
            </div>

            {/* Active Subscriptions */}
            <div  sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
              <div  variant="h6">
                Active Subscriptions ({subscriptions.length})
              </div>
              <div>
                <button className="p-2 rounded-full hover:bg-gray-100" onClick={refreshSubscriptions} size="small">
                  <Refresh />
                </button>
                <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  variant="outlined"
                  size="small"
                  startIcon={<Delete />}
                  onClick={handleUnsubscribeAll}
                  disabled={subscriptions.length === 0}
                  sx={{ ml: 1 }}
                >
                  Unsubscribe All
                </button>
              </div>
            </div>

            {subscriptions.length === 0 ? (
              <div  color="text.secondary">
                No active subscriptions. Subscribe to symbols to see live data.
              </div>
            ) : (
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer component={Paper} variant="outlined">
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le size="small">
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Type</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Symbols</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Frequency</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Created</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center">Actions</td>
                    </tr>
                  </thead>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
                    {subscriptions.map((sub, index) => (
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={index}>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                          <div  sx={{ display: 'flex', alignItems: 'center' }}>
                            {getDataTypeIcon(sub.type)}
                            <div  sx={{ ml: 1 }} variant="body2">
                              {sub.type}
                            </div>
                          </div>
                        </td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label={sub.symbol} size="small" />
                        </td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                          <div  variant="body2">
                            Real-time
                          </div>
                        </td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                          <div  variant="body2" color="text.secondary">
                            {new Date(sub.createdAt).toLocaleTimeString()}
                          </div>
                        </td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center">
                          <button className="p-2 rounded-full hover:bg-gray-100"
                            size="small"
                            onClick={() => handleUnsubscribe(index)}
                            color="error"
                          >
                            <Delete />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* Market Data Tab */}
        {activeTab === 1 && (
          <div className="bg-white shadow-md rounded-lg"Content>
            <div  variant="h6" gutterBottom>
              Live Market Data
            </div>
            
            {Object.keys(marketData).length === 0 ? (
              <div  color="text.secondary">
                No market data available. Subscribe to symbols to see live data.
              </div>
            ) : (
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer component={Paper} variant="outlined">
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le size="small">
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Symbol</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Type</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Data</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Last Update</td>
                    </tr>
                  </thead>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
                    {Object.entries(marketData).map(([key, data]) => (
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={key}>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                          <div  variant="body2" fontWeight="bold">
                            {data.symbol}
                          </div>
                        </td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                          <div  sx={{ display: 'flex', alignItems: 'center' }}>
                            {getDataTypeIcon(data.dataType)}
                            <div  sx={{ ml: 1 }} variant="body2">
                              {data.dataType}
                            </div>
                          </div>
                        </td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                          {data.dataType === 'quotes' && (
                            <div  variant="body2">
                              Bid: {formatPrice(data.bid)} | Ask: {formatPrice(data.ask)}
                            </div>
                          )}
                          {data.dataType === 'trades' && (
                            <div  variant="body2">
                              Price: {formatPrice(data.price)} | Size: {formatNumber(data.size)}
                            </div>
                          )}
                          {data.dataType === 'bars' && (
                            <div  variant="body2">
                              O: {formatPrice(data.open)} | H: {formatPrice(data.high)} | L: {formatPrice(data.low)} | C: {formatPrice(data.close)}
                            </div>
                          )}
                          {data.dataType === 'news' && (
                            <div  variant="body2">
                              {data.headline || 'News update'}
                            </div>
                          )}
                        </td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                          <div  variant="body2" color="text.secondary">
                            {data.lastUpdate}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* Available Feeds Tab */}
        {activeTab === 2 && (
          <div className="bg-white shadow-md rounded-lg"Content>
            <div  variant="h6" gutterBottom>
              Available Data Feeds
            </div>
            
            {!availableFeeds ? (
              <div>
                <div  color="text.secondary" gutterBottom>
                  Loading available feeds...
                </div>
                <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  variant="outlined"
                  onClick={() => setAvailableFeeds({
                    quotes: { description: 'Real-time quotes', symbols: 'All US stocks', frequency: 'Real-time' },
                    trades: { description: 'Live trades', symbols: 'All US stocks', frequency: 'Real-time' },
                    bars: { description: 'OHLCV bars', symbols: 'All US stocks', frequency: ['1Min', '5Min', '1Day'] }
                  })}
                  disabled={connectionStatus !== 'CONNECTED'}
                >
                  Load Feeds
                </button>
              </div>
            ) : (
              <div className="grid" container spacing={2}>
                {Object.entries(availableFeeds).map(([feedType, feedInfo]) => (
                  <div className="grid" item xs={12} md={6} key={feedType}>
                    <div className="bg-white shadow-md rounded-lg" variant="outlined">
                      <div className="bg-white shadow-md rounded-lg"Content>
                        <div  sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                          {getDataTypeIcon(feedType)}
                          <div  variant="h6" sx={{ ml: 1 }}>
                            {feedType.charAt(0).toUpperCase() + feedType.slice(1)}
                          </div>
                        </div>
                        
                        <div  variant="body2" color="text.secondary" paragraph>
                          {feedInfo.description}
                        </div>
                        
                        <div  variant="body2">
                          <strong>Symbols:</strong> {feedInfo.symbols}
                        </div>
                        
                        <div  variant="body2">
                          <strong>Frequency:</strong> {
                            Array.isArray(feedInfo.frequency) 
                              ? feedInfo.frequency.join(', ')
                              : feedInfo.frequency
                          }
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Activity Log Tab */}
        {activeTab === 3 && (
          <div className="bg-white shadow-md rounded-lg"Content>
            <div  variant="h6" gutterBottom>
              Activity Log
            </div>
            
            <div  sx={{ height: 400, overflow: 'auto', border: 1, borderColor: 'divider', borderRadius: 1, p: 1 }}>
              {logs.length === 0 ? (
                <div  color="text.secondary">
                  No activity yet.
                </div>
              ) : (
                logs.map((log, index) => (
                  <div  
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
                  </div>
                ))
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default AlpacaDataDashboard;