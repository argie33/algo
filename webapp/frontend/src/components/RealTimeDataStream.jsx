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
    <div  sx={{ p: 3 }}>
      <div  variant="h4" gutterBottom>
        Real-Time Market Data Stream
      </div>

      {/* Connection Status */}
      <div className="bg-white shadow-md rounded-lg" sx={{ mb: 3 }}>
        <div className="bg-white shadow-md rounded-lg"Content>
          <div  variant="h6" gutterBottom>
            Connection Status
          </div>
          
          <div className="grid" container spacing={2} alignItems="center">
            <div className="grid" item>
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                label={isConnected ? 'Connected' : 'Disconnected'}
                color={isConnected ? 'success' : 'error'}
                icon={isConnected ? <TrendingUp /> : <TrendingDown />}
              />
            </div>
            
            <div className="grid" item>
              <div className="mb-4" size="small" sx={{ minWidth: 120 }}>
                <label className="block text-sm font-medium text-gray-700 mb-1">Provider</label>
                <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={selectedProvider}
                  onChange={(e) => setSelectedProvider(e.target.value)}
                  disabled={isStreaming}
                >
                  {providers.map(provider => (
                    <option  key={provider} value={provider}>
                      {provider.charAt(0).toUpperCase() + provider.slice(1)}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            
            <div className="grid" item>
              <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                variant="contained"
                color={isStreaming ? "error" : "primary"}
                onClick={isStreaming ? stopStreaming : startStreaming}
                disabled={loading}
                startIcon={loading ? <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" size={20} /> : (isStreaming ? <Pause /> : <PlayArrow />)}
              >
                {loading ? 'Connecting...' : (isStreaming ? 'Stop Stream' : 'Start Stream')}
              </button>
            </div>
            
            <div className="grid" item>
              <div  title="Refresh Status">
                <button className="p-2 rounded-full hover:bg-gray-100" onClick={checkConnectionStatus}>
                  <Refresh />
                </button>
              </div>
            </div>
          </div>

          {connectionStatus.connectedProviders && (
            <div  sx={{ mt: 2 }}>
              <div  variant="body2" color="text.secondary">
                Connected Providers: {connectionStatus.connectedProviders.join(', ')}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Error Display */}
      {error && (
        <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error" sx={{ mb: 3 }} onClose={() => setError(null)}>
          {error}
        </div>
      )}

      {/* Symbol Management */}
      <div className="bg-white shadow-md rounded-lg" sx={{ mb: 3 }}>
        <div className="bg-white shadow-md rounded-lg"Content>
          <div  variant="h6" gutterBottom>
            Symbols
          </div>
          
          <div className="grid" container spacing={2} alignItems="center" sx={{ mb: 2 }}>
            <div className="grid" item>
              <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                size="small"
                label="Add Symbol"
                value={newSymbol}
                onChange={(e) => setNewSymbol(e.target.value.toUpperCase())}
                onKeyPress={(e) => e.key === 'Enter' && addSymbol()}
                placeholder="AAPL"
              />
            </div>
            <div className="grid" item>
              <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" variant="outlined" onClick={addSymbol} startIcon={<Add />}>
                Add
              </button>
            </div>
          </div>

          <div  sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
            {subscribedSymbols.map(symbol => (
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                key={symbol}
                label={symbol}
                onDelete={() => removeSymbol(symbol)}
                deleteIcon={<Remove />}
                color={realtimeData.has(symbol) ? 'primary' : 'default'}
              />
            ))}
          </div>
        </div>
      </div>

      {/* Real-Time Charts */}
      {Array.from(chartData.entries()).map(([symbol, data]) => (
        <div className="bg-white shadow-md rounded-lg" key={symbol} sx={{ mb: 3 }}>
          <div className="bg-white shadow-md rounded-lg"Content>
            <div  variant="h6" gutterBottom>
              {symbol} - Real-Time Price Chart
            </div>
            
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
              <div  sx={{ height: 300, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <div  color="text.secondary">
                  Waiting for real-time data...
                </div>
              </div>
            )}
          </div>
        </div>
      ))}

      {/* Latest Quotes */}
      {quotes.size > 0 && (
        <div className="bg-white shadow-md rounded-lg" sx={{ mb: 3 }}>
          <div className="bg-white shadow-md rounded-lg"Content>
            <div  variant="h6" gutterBottom>
              Latest Quotes
            </div>
            
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer component={Paper}>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le size="small">
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Symbol</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Bid</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Ask</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Spread</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Time</td>
                  </tr>
                </thead>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
                  {Array.from(quotes.entries()).map(([symbol, quote]) => (
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={symbol}>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell component="th" scope="row">
                        {symbol}
                      </td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{formatPrice(quote.bid)}</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{formatPrice(quote.ask)}</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                        {formatPrice(quote.ask - quote.bid)}
                      </td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                        {formatTime(quote.timestamp)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* Recent Trades */}
      {trades.length > 0 && (
        <div className="bg-white shadow-md rounded-lg">
          <div className="bg-white shadow-md rounded-lg"Content>
            <div  variant="h6" gutterBottom>
              Recent Trades
            </div>
            
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer component={Paper} sx={{ maxHeight: 400 }}>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le stickyHeader size="small">
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Symbol</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Price</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Size</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Time</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Provider</td>
                  </tr>
                </thead>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
                  {trades.map((trade, index) => (
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={index}>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell component="th" scope="row">
                        {trade.symbol}
                      </td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{formatPrice(trade.price)}</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{trade.size}</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                        {formatTime(trade.timestamp)}
                      </td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>{trade.provider}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default RealTimeDataStream;