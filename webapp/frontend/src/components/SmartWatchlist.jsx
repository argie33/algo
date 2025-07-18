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
    <Box sx={{ p: 3 }}>
      <Typography variant="h4" gutterBottom>
        Smart Watchlists
      </Typography>
      <Typography variant="subtitle1" color="text.secondary" gutterBottom>
        Track your favorite stocks with real-time data and price alerts
      </Typography>

      {/* Connection Status */}
      <Alert 
        severity={isConnected ? 'success' : 'warning'} 
        sx={{ mb: 3 }}
        action={
          <Button 
            color="inherit" 
            size="small"
            onClick={() => simpleAlpacaWebSocket.connect()}
            disabled={isConnected}
          >
            {isConnected ? 'Connected' : 'Connect'}
          </Button>
        }
      >
        {isConnected 
          ? 'Connected to real-time data feed' 
          : 'Not connected to real-time data feed'
        }
      </Alert>

      {/* Watchlist Tabs */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
            <Tabs 
              value={activeWatchlist} 
              onChange={(e, newValue) => setActiveWatchlist(newValue)}
              variant="scrollable"
              scrollButtons="auto"
            >
              {watchlists.map((watchlist, index) => (
                <Tab
                  key={watchlist.id}
                  label={
                    <Box sx={{ display: 'flex', alignItems: 'center' }}>
                      <Box 
                        sx={{ 
                          width: 8, 
                          height: 8, 
                          borderRadius: '50%', 
                          backgroundColor: watchlist.color, 
                          mr: 1 
                        }} 
                      />
                      {watchlist.name}
                      <Badge 
                        badgeContent={watchlist.symbols.length} 
                        color="primary" 
                        sx={{ ml: 1 }}
                      />
                    </Box>
                  }
                />
              ))}
            </Tabs>
            
            <Box sx={{ display: 'flex', gap: 1 }}>
              <Button
                variant="outlined"
                startIcon={<Add />}
                onClick={() => setWatchlistDialog(true)}
              >
                New Watchlist
              </Button>
              <Button
                variant="outlined"
                startIcon={<Refresh />}
                onClick={subscribeToCurrentWatchlist}
                disabled={!isConnected}
              >
                Refresh
              </Button>
            </Box>
          </Box>

          {/* Add Symbol */}
          <Box sx={{ display: 'flex', gap: 2, mb: 2 }}>
            <TextField
              size="small"
              label="Add Symbol (e.g., AAPL)"
              value={newSymbol}
              onChange={(e) => setNewSymbol(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && addSymbol()}
              disabled={!currentWatchlist}
            />
            <Button
              variant="contained"
              startIcon={<Add />}
              onClick={addSymbol}
              disabled={!currentWatchlist || !newSymbol.trim()}
            >
              Add Symbol
            </Button>
          </Box>

          {/* Controls */}
          <Box sx={{ display: 'flex', gap: 2, alignItems: 'center' }}>
            <FormControl size="small" sx={{ minWidth: 120 }}>
              <InputLabel>Sort by</InputLabel>
              <Select
                value={sortBy}
                label="Sort by"
                onChange={(e) => setSortBy(e.target.value)}
              >
                <MenuItem value="symbol">Symbol</MenuItem>
                <MenuItem value="price">Price</MenuItem>
                <MenuItem value="change">Change</MenuItem>
              </Select>
            </FormControl>
            
            <Button
              variant="outlined"
              size="small"
              onClick={() => setSortDirection(prev => prev === 'asc' ? 'desc' : 'asc')}
            >
              {sortDirection === 'asc' ? '↑' : '↓'}
            </Button>
          </Box>
        </CardContent>
      </Card>

      {/* Watchlist Content */}
      {currentWatchlist && (
        <Card>
          <CardContent>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
              <Typography variant="h6">
                {currentWatchlist.name} ({currentWatchlist.symbols.length} symbols)
              </Typography>
              <Box sx={{ display: 'flex', gap: 1 }}>
                <Switch
                  checked={currentWatchlist.notifications}
                  onChange={(e) => {
                    const updated = [...watchlists];
                    updated[activeWatchlist].notifications = e.target.checked;
                    setWatchlists(updated);
                  }}
                />
                <Typography variant="body2">Notifications</Typography>
              </Box>
            </Box>

            {sortedSymbols.length === 0 ? (
              <Typography color="text.secondary">
                No symbols in this watchlist. Add some symbols to get started.
              </Typography>
            ) : (
              <TableContainer component={Paper} variant="outlined">
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Symbol</TableCell>
                      <TableCell align="right">Price</TableCell>
                      <TableCell align="right">Change</TableCell>
                      <TableCell align="right">Bid/Ask</TableCell>
                      <TableCell align="right">Volume</TableCell>
                      <TableCell align="center">Alerts</TableCell>
                      <TableCell align="center">Actions</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {sortedSymbols.map((symbol) => {
                      const data = marketData[symbol] || {};
                      const alerts = priceAlerts[symbol] || [];
                      const activeAlerts = alerts.filter(a => !a.triggered);
                      
                      return (
                        <TableRow key={symbol}>
                          <TableCell>
                            <Box sx={{ display: 'flex', alignItems: 'center' }}>
                              <Typography variant="body2" fontWeight="bold">
                                {symbol}
                              </Typography>
                              {data.lastUpdate && (
                                <Chip
                                  label="LIVE"
                                  size="small"
                                  color="success"
                                  sx={{ ml: 1, height: 16 }}
                                />
                              )}
                            </Box>
                          </TableCell>
                          <TableCell align="right">
                            <Typography variant="body2">
                              {formatPrice(data.price || data.ask)}
                            </Typography>
                          </TableCell>
                          <TableCell align="right">
                            <Typography
                              variant="body2"
                              color={getPriceColor(data.change)}
                            >
                              {formatChange(data.change, data.changePercent)}
                            </Typography>
                          </TableCell>
                          <TableCell align="right">
                            <Typography variant="body2">
                              {formatPrice(data.bid)} / {formatPrice(data.ask)}
                            </Typography>
                          </TableCell>
                          <TableCell align="right">
                            <Typography variant="body2">
                              {data.volume ? data.volume.toLocaleString() : 'N/A'}
                            </Typography>
                          </TableCell>
                          <TableCell align="center">
                            <Badge badgeContent={activeAlerts.length} color="primary">
                              <IconButton
                                size="small"
                                onClick={() => {
                                  setSelectedSymbol(symbol);
                                  setAlertDialog(true);
                                }}
                              >
                                <NotificationsActive />
                              </IconButton>
                            </Badge>
                          </TableCell>
                          <TableCell align="center">
                            <IconButton
                              size="small"
                              onClick={() => {
                                setSymbolToDelete(symbol);
                                setDeleteConfirmOpen(true);
                              }}
                            >
                              <Delete />
                            </IconButton>
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
          </CardContent>
        </Card>
      )}

      {/* New Watchlist Dialog */}
      <Dialog open={watchlistDialog} onClose={() => setWatchlistDialog(false)}>
        <DialogTitle>Create New Watchlist</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            label="Watchlist Name"
            fullWidth
            variant="outlined"
            value={newWatchlistName}
            onChange={(e) => setNewWatchlistName(e.target.value)}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setWatchlistDialog(false)}>Cancel</Button>
          <Button onClick={addWatchlist} variant="contained">Create</Button>
        </DialogActions>
      </Dialog>

      {/* Price Alert Dialog */}
      <Dialog open={alertDialog} onClose={() => setAlertDialog(false)}>
        <DialogTitle>Set Price Alert for {selectedSymbol}</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={6}>
              <FormControl fullWidth>
                <InputLabel>Alert Type</InputLabel>
                <Select
                  value={alertType}
                  label="Alert Type"
                  onChange={(e) => setAlertType(e.target.value)}
                >
                  <MenuItem value="above">Above</MenuItem>
                  <MenuItem value="below">Below</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={6}>
              <TextField
                fullWidth
                label="Price"
                type="number"
                value={alertPrice}
                onChange={(e) => setAlertPrice(e.target.value)}
                inputProps={{ step: 0.01 }}
              />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAlertDialog(false)}>Cancel</Button>
          <Button onClick={addPriceAlert} variant="contained">Add Alert</Button>
        </DialogActions>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteConfirmOpen} onClose={() => setDeleteConfirmOpen(false)}>
        <DialogTitle>Remove Symbol</DialogTitle>
        <DialogContent>
          <Typography>
            Are you sure you want to remove {symbolToDelete} from this watchlist?
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteConfirmOpen(false)}>Cancel</Button>
          <Button onClick={() => removeSymbol(symbolToDelete)} color="error">Remove</Button>
        </DialogActions>
      </Dialog>

      {/* Snackbar */}
      <Snackbar
        open={snackbar.open}
        autoHideDuration={6000}
        onClose={() => setSnackbar(prev => ({ ...prev, open: false }))}
      >
        <Alert 
          onClose={() => setSnackbar(prev => ({ ...prev, open: false }))} 
          severity={snackbar.severity}
        >
          {snackbar.message}
        </Alert>
      </Snackbar>
    </Box>
  );
};

export default SmartWatchlist;