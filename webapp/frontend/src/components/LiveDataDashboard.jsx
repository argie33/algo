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
    <div  sx={{ p: 3 }}>
      <div  variant="h4" gutterBottom>
        Live Market Data Dashboard
      </div>

      {/* Connection Status */}
      <div className="grid" container spacing={3} sx={{ mb: 3 }}>
        <div className="grid" item xs={12} md={6}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                {getStatusIcon()}
                <div  variant="h6" sx={{ ml: 1 }}>
                  Connection Status
                </div>
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
                  onClick={handleConnect}
                  disabled={connectionStatus === 'CONNECTED' || connectionStatus === 'CONNECTING'}
                >
                  Connect
                </button>
                <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
                  variant="outlined" 
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
                    Latency
                  </div>
                  <div  variant="h6">
                    {formatLatency(metrics.lastLatency)}
                  </div>
                </div>
                <div className="grid" item xs={6}>
                  <div  variant="body2" color="text.secondary">
                    Messages
                  </div>
                  <div  variant="h6">
                    {metrics.messagesReceived || 0}
                  </div>
                </div>
                <div className="grid" item xs={6}>
                  <div  variant="body2" color="text.secondary">
                    Avg Latency
                  </div>
                  <div  variant="h6">
                    {formatLatency(metrics.avgLatency)}
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

      {/* Symbol Subscription */}
      <div className="bg-white shadow-md rounded-lg" sx={{ mb: 3 }}>
        <div className="bg-white shadow-md rounded-lg"Content>
          <div  variant="h6" gutterBottom>
            Subscribe to Symbols
          </div>
          <div  sx={{ display: 'flex', gap: 1, mb: 2 }}>
            <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              size="small"
              label="Symbol (e.g., AAPL)"
              value={newSymbol}
              onChange={(e) => setNewSymbol(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && handleSubscribe()}
              disabled={connectionStatus !== 'CONNECTED'}
            />
            <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
              variant="contained" 
              onClick={handleSubscribe}
              disabled={connectionStatus !== 'CONNECTED' || !newSymbol.trim()}
            >
              Subscribe
            </button>
          </div>
          <div  variant="body2" color="text.secondary">
            Active subscriptions: {subscriptions.join(', ') || 'None'}
          </div>
        </div>
      </div>

      {/* Market Data Table */}
      <div className="bg-white shadow-md rounded-lg" sx={{ mb: 3 }}>
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
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Price</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Change</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Change %</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Volume</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Last Update</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center">Actions</td>
                  </tr>
                </thead>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
                  {Object.entries(marketData).map(([symbol, data]) => (
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={symbol}>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell component="th" scope="row">
                        <div  sx={{ display: 'flex', alignItems: 'center' }}>
                          {data.change > 0 ? (
                            <TrendingUp color="success" fontSize="small" />
                          ) : (
                            <TrendingDown color="error" fontSize="small" />
                          )}
                          <div  sx={{ ml: 1 }} variant="body2">
                            {symbol}
                          </div>
                        </div>
                      </td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                        <div  variant="body2" fontWeight="bold">
                          {formatPrice(data.price)}
                        </div>
                      </td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                        <div  
                          variant="body2"
                          color={data.change > 0 ? 'success.main' : 'error.main'}
                        >
                          {formatPrice(data.change)}
                        </div>
                      </td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                        <div  
                          variant="body2"
                          color={data.change_percent > 0 ? 'success.main' : 'error.main'}
                        >
                          {formatPercent(data.change_percent)}
                        </div>
                      </td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                        <div  variant="body2">
                          {data.volume?.toLocaleString() || 'N/A'}
                        </div>
                      </td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                        <div  variant="body2" color="text.secondary">
                          {data.lastUpdate}
                        </div>
                      </td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center">
                        <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                          size="small"
                          onClick={() => handleUnsubscribe(symbol)}
                          color="error"
                        >
                          Unsubscribe
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* Activity Log */}
      <div className="bg-white shadow-md rounded-lg">
        <div className="bg-white shadow-md rounded-lg"Content>
          <div  variant="h6" gutterBottom>
            Activity Log
          </div>
          <div  sx={{ height: 200, overflow: 'auto' }}>
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
                    color: log.type === 'error' ? 'error.main' : 
                           log.type === 'success' ? 'success.main' :
                           log.type === 'warning' ? 'warning.main' : 'text.primary'
                  }}
                >
                  <strong>{log.timestamp}</strong>: {log.message}
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default LiveDataDashboard;