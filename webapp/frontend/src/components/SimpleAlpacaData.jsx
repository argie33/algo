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
  Tab,
  FormControlLabel,
  Switch
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
  const [selectedFeeds, setSelectedFeeds] = useState({
    quotes: true,
    trades: true,
    bars: false,
    news: false,
    crypto: false
  });

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
      if (type === 'quotes' && selectedFeeds.quotes) {
        simpleAlpacaWebSocket.subscribeToQuotes([symbol]);
        setSubscriptions(prev => [...prev, { symbol, type }]);
      }
      if (type === 'trades' && selectedFeeds.trades) {
        simpleAlpacaWebSocket.subscribeToTrades([symbol]);
        setSubscriptions(prev => [...prev, { symbol, type }]);
      }
      if (type === 'bars' && selectedFeeds.bars) {
        simpleAlpacaWebSocket.subscribeToBars([symbol]);
        setSubscriptions(prev => [...prev, { symbol, type }]);
      }
      if (type === 'crypto' && selectedFeeds.crypto) {
        simpleAlpacaWebSocket.subscribeToCrypto([symbol]);
        setSubscriptions(prev => [...prev, { symbol, type }]);
      }
    });
  };

  const handleSubscribeWithSelectedFeeds = () => {
    if (!newSymbol.trim()) return;
    
    const symbol = newSymbol.trim().toUpperCase();
    
    // Subscribe to all selected feed types
    Object.entries(selectedFeeds).forEach(([feedType, isSelected]) => {
      if (isSelected) {
        switch (feedType) {
          case 'quotes':
            simpleAlpacaWebSocket.subscribeToQuotes([symbol]);
            setSubscriptions(prev => [...prev, { symbol, type: 'quotes' }]);
            break;
          case 'trades':
            simpleAlpacaWebSocket.subscribeToTrades([symbol]);
            setSubscriptions(prev => [...prev, { symbol, type: 'trades' }]);
            break;
          case 'bars':
            simpleAlpacaWebSocket.subscribeToBars([symbol]);
            setSubscriptions(prev => [...prev, { symbol, type: 'bars' }]);
            break;
          case 'news':
            simpleAlpacaWebSocket.subscribeToNews([symbol]);
            setSubscriptions(prev => [...prev, { symbol, type: 'news' }]);
            break;
          case 'crypto':
            simpleAlpacaWebSocket.subscribeToCrypto([symbol]);
            setSubscriptions(prev => [...prev, { symbol, type: 'crypto' }]);
            break;
        }
      }
    });
    
    setNewSymbol('');
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
    <div  sx={{ p: 3 }}>
      <div  variant="h4" gutterBottom>
        Live Data Feed
      </div>
      <div  variant="subtitle1" color="text.secondary" gutterBottom>
        Real-time market data streaming with WebSocket connections
      </div>

      {/* Connection Status */}
      <div className="grid" container spacing={3} sx={{ mb: 3 }}>
        <div className="grid" item xs={12} md={6}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
                <div  variant="h6">Connection</div>
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                  label={connected ? 'Connected' : 'Disconnected'} 
                  color={getStatusColor()} 
                  variant="outlined" 
                />
              </div>
              
              <div  sx={{ display: 'flex', gap: 1 }}>
                <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
                  variant="contained" 
                  startIcon={<PlayArrow />}
                  onClick={handleConnect}
                  disabled={connected}
                >
                  Connect
                </button>
                <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
                  variant="outlined" 
                  startIcon={<Stop />}
                  onClick={handleDisconnect}
                  disabled={!connected}
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
              <div  variant="h6" gutterBottom>Metrics</div>
              <div className="grid" container spacing={2}>
                <div className="grid" item xs={6}>
                  <div  variant="body2" color="text.secondary">Messages</div>
                  <div  variant="h6">{metrics.messagesReceived || 0}</div>
                </div>
                <div className="grid" item xs={6}>
                  <div  variant="body2" color="text.secondary">Subscriptions</div>
                  <div  variant="h6">{subscriptions.length}</div>
                </div>
                <div className="grid" item xs={6}>
                  <div  variant="body2" color="text.secondary">Uptime</div>
                  <div  variant="h6">
                    {metrics.uptime ? `${Math.floor(metrics.uptime / 1000)}s` : '0s'}
                  </div>
                </div>
                <div className="grid" item xs={6}>
                  <div  variant="body2" color="text.secondary">Data Points</div>
                  <div  variant="h6">{Object.keys(data).length}</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Error Alert */}
      {error && (
        <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error" sx={{ mb: 3 }} onClose={() => setError('')}>
          {String(error)}
        </div>
      )}

      {/* Main Content */}
      <div className="bg-white shadow-md rounded-lg">
        <div className="border-b border-gray-200" value={activeTab} onChange={(e, newValue) => setActiveTab(newValue)}>
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Subscribe" />
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Live Data" />
        </div>

        {/* Subscribe Tab */}
        {activeTab === 0 && (
          <div className="bg-white shadow-md rounded-lg"Content>
            <div  variant="h6" gutterBottom>Subscribe to Symbols</div>
            
            {/* Feed Selection */}
            <div  sx={{ mb: 3 }}>
              <div  variant="subtitle2" gutterBottom>Select Data Feeds:</div>
              <div className="grid" container spacing={1}>
                {Object.entries(selectedFeeds).map(([feed, isSelected]) => (
                  <div className="grid" item key={feed}>
                    <div className="mb-4"Label
                      control={
                        <input type="checkbox" className="toggle"
                          checked={isSelected}
                          onChange={(e) => setSelectedFeeds(prev => ({
                            ...prev,
                            [feed]: e.target.checked
                          }))}
                          size="small"
                        />
                      }
                      label={feed.charAt(0).toUpperCase() + feed.slice(1)}
                    />
                  </div>
                ))}
              </div>
            </div>
            
            {/* Quick Subscribe Buttons */}
            <div  sx={{ mb: 3 }}>
              <div  variant="subtitle2" gutterBottom>Quick Subscribe:</div>
              <div  sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mb: 2 }}>
                <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
                  variant="outlined" 
                  size="small"
                  onClick={() => quickSubscribe(['AAPL', 'MSFT', 'GOOGL', 'AMZN'], 'quotes')}
                  disabled={!connected || !selectedFeeds.quotes}
                >
                  Big Tech (Quotes)
                </button>
                <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
                  variant="outlined" 
                  size="small"
                  onClick={() => quickSubscribe(['TSLA', 'NVDA', 'META'], 'trades')}
                  disabled={!connected || !selectedFeeds.trades}
                >
                  Growth Stocks (Trades)
                </button>
                <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
                  variant="outlined" 
                  size="small"
                  onClick={() => quickSubscribe(['SPY', 'QQQ', 'IWM'], 'bars')}
                  disabled={!connected || !selectedFeeds.bars}
                >
                  ETFs (Bars)
                </button>
                <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
                  variant="outlined" 
                  size="small"
                  onClick={() => quickSubscribe(['BTCUSD', 'ETHUSD'], 'crypto')}
                  disabled={!connected || !selectedFeeds.crypto}
                >
                  Crypto
                </button>
              </div>
            </div>

            {/* Manual Subscribe */}
            <div  sx={{ mb: 3 }}>
              <div  variant="subtitle2" gutterBottom>Manual Subscribe:</div>
              <div  sx={{ display: 'flex', gap: 2, mb: 2 }}>
                <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  size="small"
                  label="Symbol (e.g., AAPL)"
                  value={newSymbol}
                  onChange={(e) => setNewSymbol(e.target.value)}
                  onKeyPress={(e) => e.key === 'Enter' && handleSubscribeWithSelectedFeeds()}
                  disabled={!connected}
                />
                <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
                  variant="contained" 
                  onClick={handleSubscribeWithSelectedFeeds}
                  disabled={!connected || !newSymbol.trim() || Object.values(selectedFeeds).every(v => !v)}
                >
                  Subscribe to Selected Feeds
                </button>
              </div>
              <div  variant="caption" color="text.secondary">
                Will subscribe to all selected feed types for this symbol
              </div>
            </div>

            {/* Active Subscriptions */}
            <div  sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
              <div  variant="h6">Active Subscriptions ({subscriptions.length})</div>
              <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                variant="outlined"
                size="small"
                startIcon={<Delete />}
                onClick={handleUnsubscribeAll}
                disabled={subscriptions.length === 0}
              >
                Unsubscribe All
              </button>
            </div>

            {subscriptions.length === 0 ? (
              <div  color="text.secondary">No active subscriptions</div>
            ) : (
              <div  sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                {subscriptions.map((sub, index) => (
                  <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                    key={index} 
                    label={`${sub.symbol} (${sub.type})`} 
                    variant="outlined" 
                  />
                ))}
              </div>
            )}
          </div>
        )}

        {/* Live Data Tab */}
        {activeTab === 1 && (
          <div className="bg-white shadow-md rounded-lg"Content>
            <div  variant="h6" gutterBottom>Live Market Data</div>
            
            {Object.keys(data).length === 0 ? (
              <div  color="text.secondary">
                No live data yet. Subscribe to symbols to see real-time data.
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
                    {Object.entries(data).map(([key, item]) => (
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={key}>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                          <div  variant="body2" fontWeight="bold">
                            {item.symbol}
                          </div>
                        </td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label={item.type} size="small" variant="outlined" />
                        </td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                          {item.type === 'quote' && (
                            <div  variant="body2">
                              Bid: {formatPrice(item.bid)} | Ask: {formatPrice(item.ask)}
                            </div>
                          )}
                          {item.type === 'trade' && (
                            <div  variant="body2">
                              Price: {formatPrice(item.price)} | Size: {formatNumber(item.size)}
                            </div>
                          )}
                          {item.type === 'bar' && (
                            <div  variant="body2">
                              O: {formatPrice(item.open)} | H: {formatPrice(item.high)} | 
                              L: {formatPrice(item.low)} | C: {formatPrice(item.close)}
                            </div>
                          )}
                        </td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                          <div  variant="body2" color="text.secondary">
                            {item.lastUpdate}
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
      </div>
    </div>
  );
};

export default SimpleAlpacaData;