import React, { useState, useEffect, useCallback } from 'react';
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
  IconButton,
  Tooltip,
  Chip,
  Alert,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Grid,
  MenuItem,
  Select,
  FormControl,
  InputLabel,
  Tabs,
  Tab,
  Badge,
  Divider,
  List,
  ListItem,
  ListItemText,
  ListItemSecondaryAction,
  Switch,
  Snackbar
} from '@mui/material';
import {
  Add,
  Delete,
  Edit,
  Star,
  StarBorder,
  TrendingUp,
  TrendingDown,
  Refresh,
  NotificationsActive,
  NotificationsOff,
  ShowChart,
  FilterList,
  Sort,
  MoreVert,
  PlaylistAdd,
  Share,
  Download,
  CloudSync,
  Visibility,
  VisibilityOff
} from '@mui/icons-material';
import simpleAlpacaWebSocket from '../services/simpleAlpacaWebSocket';

const SmartWatchlist = () => {
  const [watchlists, setWatchlists] = useState([]);
  const [activeWatchlist, setActiveWatchlist] = useState(0);
  const [newSymbol, setNewSymbol] = useState('');
  const [newWatchlistName, setNewWatchlistName] = useState('');
  const [editingWatchlist, setEditingWatchlist] = useState(null);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [symbolToDelete, setSymbolToDelete] = useState(null);
  const [watchlistDialog, setWatchlistDialog] = useState(false);
  const [priceAlerts, setPriceAlerts] = useState({});
  const [alertDialog, setAlertDialog] = useState(false);
  const [selectedSymbol, setSelectedSymbol] = useState(null);
  const [alertPrice, setAlertPrice] = useState('');
  const [alertType, setAlertType] = useState('above');
  const [marketData, setMarketData] = useState({});
  const [sortBy, setSortBy] = useState('symbol');
  const [sortDirection, setSortDirection] = useState('asc');
  const [filterBy, setFilterBy] = useState('all');
  const [snackbar, setSnackbar] = useState({ open: false, message: '', severity: 'success' });
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [isConnected, setIsConnected] = useState(false);

  // Load saved watchlists from localStorage
  useEffect(() => {
    const savedWatchlists = localStorage.getItem('smart_watchlists');
    const savedAlerts = localStorage.getItem('price_alerts');
    
    if (savedWatchlists) {
      setWatchlists(JSON.parse(savedWatchlists));
    } else {
      // Create default watchlists
      const defaultWatchlists = [
        {
          id: 1,
          name: 'My Stocks',
          symbols: ['AAPL', 'MSFT', 'GOOGL', 'TSLA'],
          color: '#1976d2',
          notifications: true,
          autoRefresh: true,
          createdAt: new Date().toISOString()
        },
        {
          id: 2,
          name: 'Tech Giants',
          symbols: ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA'],
          color: '#9c27b0',
          notifications: true,
          autoRefresh: true,
          createdAt: new Date().toISOString()
        },
        {
          id: 3,
          name: 'ETFs',
          symbols: ['SPY', 'QQQ', 'IWM', 'VTI', 'VOO'],
          color: '#f57c00',
          notifications: false,
          autoRefresh: true,
          createdAt: new Date().toISOString()
        }
      ];
      setWatchlists(defaultWatchlists);
      localStorage.setItem('smart_watchlists', JSON.stringify(defaultWatchlists));
    }

    if (savedAlerts) {
      setPriceAlerts(JSON.parse(savedAlerts));
    }
  }, []);

  // Save watchlists to localStorage whenever they change
  useEffect(() => {
    if (watchlists.length > 0) {
      localStorage.setItem('smart_watchlists', JSON.stringify(watchlists));
    }
  }, [watchlists]);

  // Save price alerts to localStorage
  useEffect(() => {
    localStorage.setItem('price_alerts', JSON.stringify(priceAlerts));
  }, [priceAlerts]);

  // Connect to Alpaca WebSocket
  useEffect(() => {
    const handleConnected = () => {
      setIsConnected(true);
      subscribeTo(currentWatchlist);
    };

    const handleDisconnected = () => {
      setIsConnected(false);
    };

    const handleData = ({ type, data }) => {
      if (type === 'quote' || type === 'trade') {
        setMarketData(prev => ({
          ...prev,
          [data.symbol]: {
            ...prev[data.symbol],
            ...data,
            lastUpdate: new Date().toLocaleTimeString()
          }
        }));

        // Check price alerts
        checkPriceAlerts(data.symbol, data.price || data.ask || data.bid);
      }
    };

    simpleAlpacaWebSocket.on('connected', handleConnected);
    simpleAlpacaWebSocket.on('disconnected', handleDisconnected);
    simpleAlpacaWebSocket.on('data', handleData);

    // Auto-connect if not connected
    if (!isConnected) {
      simpleAlpacaWebSocket.connect();
    }

    return () => {
      simpleAlpacaWebSocket.off('connected', handleConnected);
      simpleAlpacaWebSocket.off('disconnected', handleDisconnected);
      simpleAlpacaWebSocket.off('data', handleData);
    };
  }, [isConnected]);

  // Subscribe to current watchlist symbols
  const subscribeToCurrentWatchlist = useCallback(() => {
    if (isConnected && watchlists[activeWatchlist]) {
      const symbols = watchlists[activeWatchlist].symbols;
      if (symbols.length > 0) {
        simpleAlpacaWebSocket.subscribeToQuotes(symbols);
        simpleAlpacaWebSocket.subscribeToTrades(symbols);
      }
    }
  }, [isConnected, watchlists, activeWatchlist]);

  // Subscribe when watchlist changes
  useEffect(() => {
    subscribeToCurrentWatchlist();
  }, [subscribeToCurrentWatchlist]);

  // Check price alerts
  const checkPriceAlerts = (symbol, currentPrice) => {
    const alerts = priceAlerts[symbol];
    if (!alerts || alerts.length === 0) return;

    alerts.forEach(alert => {
      if (!alert.triggered) {
        const shouldTrigger = 
          (alert.type === 'above' && currentPrice >= alert.price) ||
          (alert.type === 'below' && currentPrice <= alert.price);

        if (shouldTrigger) {
          // Trigger alert
          alert.triggered = true;
          alert.triggeredAt = new Date().toISOString();
          
          // Show notification
          showSnackbar(
            `Price Alert: ${symbol} is ${alert.type} $${alert.price} (Current: $${currentPrice.toFixed(2)})`,
            'warning'
          );

          // Browser notification if supported
          if ('Notification' in window && Notification.permission === 'granted') {
            new Notification(`Price Alert: ${symbol}`, {
              body: `${symbol} is ${alert.type} $${alert.price} (Current: $${currentPrice.toFixed(2)})`,
              icon: '/favicon.ico'
            });
          }
        }
      }
    });

    setPriceAlerts(prev => ({ ...prev, [symbol]: alerts }));
  };

  // Add new watchlist
  const addWatchlist = () => {
    if (!newWatchlistName.trim()) return;

    const newWatchlist = {
      id: Date.now(),
      name: newWatchlistName,
      symbols: [],
      color: '#1976d2',
      notifications: true,
      autoRefresh: true,
      createdAt: new Date().toISOString()
    };

    setWatchlists(prev => [...prev, newWatchlist]);
    setNewWatchlistName('');
    setWatchlistDialog(false);
    setActiveWatchlist(watchlists.length);
    showSnackbar('Watchlist created successfully', 'success');
  };

  // Add symbol to watchlist
  const addSymbol = () => {
    if (!newSymbol.trim()) return;

    const symbol = newSymbol.trim().toUpperCase();
    const currentWatchlist = watchlists[activeWatchlist];
    
    if (currentWatchlist.symbols.includes(symbol)) {
      showSnackbar('Symbol already in watchlist', 'error');
      return;
    }

    const updatedWatchlists = [...watchlists];
    updatedWatchlists[activeWatchlist].symbols.push(symbol);
    setWatchlists(updatedWatchlists);
    setNewSymbol('');
    
    // Subscribe to new symbol
    if (isConnected) {
      simpleAlpacaWebSocket.subscribeToQuotes([symbol]);
      simpleAlpacaWebSocket.subscribeToTrades([symbol]);
    }

    showSnackbar(`Added ${symbol} to watchlist`, 'success');
  };

  // Remove symbol from watchlist
  const removeSymbol = (symbol) => {
    const updatedWatchlists = [...watchlists];
    updatedWatchlists[activeWatchlist].symbols = updatedWatchlists[activeWatchlist].symbols.filter(s => s !== symbol);
    setWatchlists(updatedWatchlists);
    setDeleteConfirmOpen(false);
    setSymbolToDelete(null);
    showSnackbar(`Removed ${symbol} from watchlist`, 'success');
  };

  // Delete watchlist
  const deleteWatchlist = (index) => {
    const updatedWatchlists = watchlists.filter((_, i) => i !== index);
    setWatchlists(updatedWatchlists);
    setActiveWatchlist(Math.max(0, activeWatchlist - 1));
    showSnackbar('Watchlist deleted', 'success');
  };

  // Add price alert
  const addPriceAlert = () => {
    if (!selectedSymbol || !alertPrice) return;

    const alert = {
      id: Date.now(),
      symbol: selectedSymbol,
      price: parseFloat(alertPrice),
      type: alertType,
      triggered: false,
      createdAt: new Date().toISOString()
    };

    setPriceAlerts(prev => ({
      ...prev,
      [selectedSymbol]: [...(prev[selectedSymbol] || []), alert]
    }));

    setAlertDialog(false);
    setAlertPrice('');
    setSelectedSymbol(null);
    showSnackbar('Price alert added', 'success');
  };

  // Format price
  const formatPrice = (price) => {
    return typeof price === 'number' ? `$${price.toFixed(2)}` : 'N/A';
  };

  // Format change
  const formatChange = (change, changePercent) => {
    if (typeof change !== 'number') return 'N/A';
    
    const sign = change >= 0 ? '+' : '';
    const percentStr = changePercent ? ` (${sign}${changePercent.toFixed(2)}%)` : '';
    return `${sign}${change.toFixed(2)}${percentStr}`;
  };

  // Get price change color
  const getPriceColor = (change) => {
    if (typeof change !== 'number') return 'text.primary';
    return change >= 0 ? 'success.main' : 'error.main';
  };

  // Sort symbols
  const sortSymbols = (symbols) => {
    return [...symbols].sort((a, b) => {
      let aValue, bValue;
      
      switch (sortBy) {
        case 'symbol':
          aValue = a;
          bValue = b;
          break;
        case 'price':
          aValue = marketData[a]?.price || marketData[a]?.ask || 0;
          bValue = marketData[b]?.price || marketData[b]?.ask || 0;
          break;
        case 'change':
          aValue = marketData[a]?.change || 0;
          bValue = marketData[b]?.change || 0;
          break;
        default:
          aValue = a;
          bValue = b;
      }

      if (sortDirection === 'asc') {
        return aValue < bValue ? -1 : aValue > bValue ? 1 : 0;
      } else {
        return aValue > bValue ? -1 : aValue < bValue ? 1 : 0;
      }
    });
  };

  // Show snackbar
  const showSnackbar = (message, severity = 'success') => {
    setSnackbar({ open: true, message, severity });
  };

  const currentWatchlist = watchlists[activeWatchlist];
  const sortedSymbols = currentWatchlist ? sortSymbols(currentWatchlist.symbols) : [];

  return (
    <div  sx={{ p: 3 }}>
      <div  variant="h4" gutterBottom>
        Smart Watchlists
      </div>
      <div  variant="subtitle1" color="text.secondary" gutterBottom>
        Track your favorite stocks with real-time data and price alerts
      </div>

      {/* Connection Status */}
      <div className="p-4 rounded-md bg-blue-50 border border-blue-200" 
        severity={isConnected ? 'success' : 'warning'} 
        sx={{ mb: 3 }}
        action={
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
            color="inherit" 
            size="small"
            onClick={() => simpleAlpacaWebSocket.connect()}
            disabled={isConnected}
          >
            {isConnected ? 'Connected' : 'Connect'}
          </button>
        }
      >
        {isConnected 
          ? 'Connected to real-time data feed' 
          : 'Not connected to real-time data feed'
        }
      </div>

      {/* Watchlist Tabs */}
      <div className="bg-white shadow-md rounded-lg" sx={{ mb: 3 }}>
        <div className="bg-white shadow-md rounded-lg"Content>
          <div  sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
            <div className="border-b border-gray-200" 
              value={activeWatchlist} 
              onChange={(e, newValue) => setActiveWatchlist(newValue)}
              variant="scrollable"
              scrollButtons="auto"
            >
              {watchlists.map((watchlist, index) => (
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"
                  key={watchlist.id}
                  label={
                    <div  sx={{ display: 'flex', alignItems: 'center' }}>
                      <div  
                        sx={{ 
                          width: 8, 
                          height: 8, 
                          borderRadius: '50%', 
                          backgroundColor: watchlist.color, 
                          mr: 1 
                        }} 
                      />
                      {watchlist.name}
                      <span className="inline-flex items-center justify-center px-2 py-1 text-xs font-bold leading-none text-red-100 bg-red-600 rounded-full" 
                        badgeContent={watchlist.symbols.length} 
                        color="primary" 
                        sx={{ ml: 1 }}
                      />
                    </div>
                  }
                />
              ))}
            </div>
            
            <div  sx={{ display: 'flex', gap: 1 }}>
              <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                variant="outlined"
                startIcon={<Add />}
                onClick={() => setWatchlistDialog(true)}
              >
                New Watchlist
              </button>
              <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                variant="outlined"
                startIcon={<Refresh />}
                onClick={subscribeToCurrentWatchlist}
                disabled={!isConnected}
              >
                Refresh
              </button>
            </div>
          </div>

          {/* Add Symbol */}
          <div  sx={{ display: 'flex', gap: 2, mb: 2 }}>
            <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              size="small"
              label="Add Symbol (e.g., AAPL)"
              value={newSymbol}
              onChange={(e) => setNewSymbol(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && addSymbol()}
              disabled={!currentWatchlist}
            />
            <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
              variant="contained"
              startIcon={<Add />}
              onClick={addSymbol}
              disabled={!currentWatchlist || !newSymbol.trim()}
            >
              Add Symbol
            </button>
          </div>

          {/* Controls */}
          <div  sx={{ display: 'flex', gap: 2, alignItems: 'center' }}>
            <div className="mb-4" size="small" sx={{ minWidth: 120 }}>
              <label className="block text-sm font-medium text-gray-700 mb-1">Sort by</label>
              <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={sortBy}
                label="Sort by"
                onChange={(e) => setSortBy(e.target.value)}
              >
                <option  value="symbol">Symbol</option>
                <option  value="price">Price</option>
                <option  value="change">Change</option>
              </select>
            </div>
            
            <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
              variant="outlined"
              size="small"
              onClick={() => setSortDirection(prev => prev === 'asc' ? 'desc' : 'asc')}
            >
              {sortDirection === 'asc' ? '↑' : '↓'}
            </button>
          </div>
        </div>
      </div>

      {/* Watchlist Content */}
      {currentWatchlist && (
        <div className="bg-white shadow-md rounded-lg">
          <div className="bg-white shadow-md rounded-lg"Content>
            <div  sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
              <div  variant="h6">
                {currentWatchlist.name} ({currentWatchlist.symbols.length} symbols)
              </div>
              <div  sx={{ display: 'flex', gap: 1 }}>
                <input type="checkbox" className="toggle"
                  checked={currentWatchlist.notifications}
                  onChange={(e) => {
                    const updated = [...watchlists];
                    updated[activeWatchlist].notifications = e.target.checked;
                    setWatchlists(updated);
                  }}
                />
                <div  variant="body2">Notifications</div>
              </div>
            </div>

            {sortedSymbols.length === 0 ? (
              <div  color="text.secondary">
                No symbols in this watchlist. Add some symbols to get started.
              </div>
            ) : (
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer component={Paper} variant="outlined">
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le size="small">
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Symbol</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Price</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Change</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Bid/Ask</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Volume</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center">Alerts</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center">Actions</td>
                    </tr>
                  </thead>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
                    {sortedSymbols.map((symbol) => {
                      const data = marketData[symbol] || {};
                      const alerts = priceAlerts[symbol] || [];
                      const activeAlerts = alerts.filter(a => !a.triggered);
                      
                      return (
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={symbol}>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                            <div  sx={{ display: 'flex', alignItems: 'center' }}>
                              <div  variant="body2" fontWeight="bold">
                                {symbol}
                              </div>
                              {data.lastUpdate && (
                                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                                  label="LIVE"
                                  size="small"
                                  color="success"
                                  sx={{ ml: 1, height: 16 }}
                                />
                              )}
                            </div>
                          </td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                            <div  variant="body2">
                              {formatPrice(data.price || data.ask)}
                            </div>
                          </td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                            <div 
                              variant="body2"
                              color={getPriceColor(data.change)}
                            >
                              {formatChange(data.change, data.changePercent)}
                            </div>
                          </td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                            <div  variant="body2">
                              {formatPrice(data.bid)} / {formatPrice(data.ask)}
                            </div>
                          </td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                            <div  variant="body2">
                              {data.volume ? data.volume.toLocaleString() : 'N/A'}
                            </div>
                          </td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center">
                            <span className="inline-flex items-center justify-center px-2 py-1 text-xs font-bold leading-none text-red-100 bg-red-600 rounded-full" badgeContent={activeAlerts.length} color="primary">
                              <button className="p-2 rounded-full hover:bg-gray-100"
                                size="small"
                                onClick={() => {
                                  setSelectedSymbol(symbol);
                                  setAlertDialog(true);
                                }}
                              >
                                <NotificationsActive />
                              </button>
                            </span>
                          </td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center">
                            <button className="p-2 rounded-full hover:bg-gray-100"
                              size="small"
                              onClick={() => {
                                setSymbolToDelete(symbol);
                                setDeleteConfirmOpen(true);
                              }}
                            >
                              <Delete />
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {/* New Watchlist Dialog */}
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50" open={watchlistDialog} onClose={() => setWatchlistDialog(false)}>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Title>Create New Watchlist</h2>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Content>
          <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            autoFocus
            margin="dense"
            label="Watchlist Name"
            fullWidth
            variant="outlined"
            value={newWatchlistName}
            onChange={(e) => setNewWatchlistName(e.target.value)}
          />
        </div>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Actions>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" onClick={() => setWatchlistDialog(false)}>Cancel</button>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" onClick={addWatchlist} variant="contained">Create</button>
        </div>
      </div>

      {/* Price Alert Dialog */}
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50" open={alertDialog} onClose={() => setAlertDialog(false)}>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Title>Set Price Alert for {selectedSymbol}</h2>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Content>
          <div className="grid" container spacing={2} sx={{ mt: 1 }}>
            <div className="grid" item xs={6}>
              <div className="mb-4" fullWidth>
                <label className="block text-sm font-medium text-gray-700 mb-1">Alert Type</label>
                <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={alertType}
                  label="Alert Type"
                  onChange={(e) => setAlertType(e.target.value)}
                >
                  <option  value="above">Above</option>
                  <option  value="below">Below</option>
                </select>
              </div>
            </div>
            <div className="grid" item xs={6}>
              <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                fullWidth
                label="Price"
                type="number"
                value={alertPrice}
                onChange={(e) => setAlertPrice(e.target.value)}
                inputProps={{ step: 0.01 }}
              />
            </div>
          </div>
        </div>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Actions>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" onClick={() => setAlertDialog(false)}>Cancel</button>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" onClick={addPriceAlert} variant="contained">Add Alert</button>
        </div>
      </div>

      {/* Delete Confirmation Dialog */}
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50" open={deleteConfirmOpen} onClose={() => setDeleteConfirmOpen(false)}>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Title>Remove Symbol</h2>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Content>
          <div>
            Are you sure you want to remove {symbolToDelete} from this watchlist?
          </div>
        </div>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Actions>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" onClick={() => setDeleteConfirmOpen(false)}>Cancel</button>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" onClick={() => removeSymbol(symbolToDelete)} color="error">Remove</button>
        </div>
      </div>

      {/* Snackbar */}
      <div className="fixed bottom-4 right-4 bg-gray-800 text-white p-4 rounded-md shadow-lg"
        open={snackbar.open}
        autoHideDuration={6000}
        onClose={() => setSnackbar(prev => ({ ...prev, open: false }))}
      >
        <div className="p-4 rounded-md bg-blue-50 border border-blue-200" 
          onClose={() => setSnackbar(prev => ({ ...prev, open: false }))} 
          severity={snackbar.severity}
        >
          {snackbar.message}
        </div>
      </div>
    </div>
  );
};

export default SmartWatchlist;