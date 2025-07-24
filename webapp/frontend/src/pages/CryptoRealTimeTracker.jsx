/**
 * Crypto Real-Time Price Tracker
 * Live cryptocurrency price monitoring with alerts
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Card,
  CardContent,
  CardHeader,
  Typography,
  Grid,
  Box,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  MenuItem,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Chip,
  IconButton,
  Tooltip,
  Alert,
  LinearProgress,
  List,
  ListItem,
  ListItemText,
  ListItemSecondaryAction,
  Switch,
  FormControl,
  InputLabel,
  Select
} from '@mui/material';
import {
  Add as AddIcon,
  Delete as DeleteIcon,
  NotificationsActive,
  TrendingUp,
  TrendingDown,
  Refresh,
  Star,
  StarBorder,
  Timeline
} from '@mui/icons-material';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, ResponsiveContainer, AreaChart, Area } from 'recharts';

const CryptoRealTimeTracker = () => {
  const [realTimeData, setRealTimeData] = useState({});
  const [marketPulse, setMarketPulse] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [watchlist, setWatchlist] = useState(['bitcoin', 'ethereum', 'cardano', 'solana', 'chainlink']);
  const [historicalData, setHistoricalData] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  
  // Dialog states
  const [alertDialogOpen, setAlertDialogOpen] = useState(false);
  const [alertForm, setAlertForm] = useState({
    symbol: '',
    target_price: '',
    condition: 'above',
    notification_type: 'price'
  });
  
  const [refreshing, setRefreshing] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);
  
  // Mock user ID
  const userId = 'demo-user';
  
  // Fetch real-time prices
  const fetchRealTimePrices = useCallback(async () => {
    if (watchlist.length === 0) return;
    
    try {
      setRefreshing(true);
      const response = await fetch(`/api/crypto-realtime/prices?symbols=${watchlist.join(',')}&vs_currency=usd`);
      const data = await response.json();
      
      if (data.success) {
        setRealTimeData(data.data);
      } else {
        setError(data.error || 'Failed to fetch real-time prices');
      }
    } catch (err) {
      console.error('Real-time prices fetch error:', err);
      setError('Failed to fetch real-time prices');
    } finally {
      setRefreshing(false);
    }
  }, [watchlist]);
  
  // Fetch market pulse
  const fetchMarketPulse = useCallback(async () => {
    try {
      const response = await fetch('/api/crypto-realtime/market-pulse?limit=10&vs_currency=usd');
      const data = await response.json();
      
      if (data.success) {
        setMarketPulse(data.data);
      }
    } catch (err) {
      console.error('Market pulse fetch error:', err);
    }
  }, []);
  
  // Fetch user alerts
  const fetchAlerts = useCallback(async () => {
    try {
      const response = await fetch(`/api/crypto-realtime/alerts/${userId}`);
      const data = await response.json();
      
      if (data.success) {
        setAlerts(data.data || []);
      }
    } catch (err) {
      console.error('Alerts fetch error:', err);
    }
  }, [userId]);
  
  // Fetch historical data for charts
  const fetchHistoricalData = useCallback(async (symbol, days = 7) => {
    try {
      const response = await fetch(`/api/crypto-realtime/history/${symbol}?days=${days}&vs_currency=usd`);
      const data = await response.json();
      
      if (data.success) {
        setHistoricalData(prev => ({
          ...prev,
          [symbol]: data.data
        }));
      }
    } catch (err) {
      console.error('Historical data fetch error:', err);
    }
  }, []);
  
  // Initial data load
  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      await Promise.all([
        fetchRealTimePrices(),
        fetchMarketPulse(),
        fetchAlerts()
      ]);
      
      // Fetch historical data for watchlist
      for (const symbol of watchlist.slice(0, 3)) { // Limit to first 3 for performance
        await fetchHistoricalData(symbol);
      }
      
      setLoading(false);
    };
    
    loadData();
  }, [fetchRealTimePrices, fetchMarketPulse, fetchAlerts, fetchHistoricalData, watchlist]);
  
  // Auto-refresh effect
  useEffect(() => {
    if (!autoRefresh) return;
    
    const interval = setInterval(() => {
      fetchRealTimePrices();
      fetchMarketPulse();
    }, 15000); // Refresh every 15 seconds
    
    return () => clearInterval(interval);
  }, [fetchRealTimePrices, fetchMarketPulse, autoRefresh]);
  
  // Handle create alert
  const handleCreateAlert = async () => {
    try {
      const response = await fetch('/api/crypto-realtime/alerts', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          user_id: userId,
          ...alertForm,
          target_price: parseFloat(alertForm.target_price)
        })
      });
      
      const data = await response.json();
      
      if (data.success) {
        setAlertForm({
          symbol: '',
          target_price: '',
          condition: 'above',
          notification_type: 'price'
        });
        setAlertDialogOpen(false);
        await fetchAlerts();
      } else {
        setError(data.error || 'Failed to create alert');
      }
    } catch (err) {
      console.error('Create alert error:', err);
      setError('Failed to create alert');
    }
  };
  
  // Handle delete alert
  const handleDeleteAlert = async (alertId) => {
    try {
      const response = await fetch(`/api/crypto-realtime/alerts/${alertId}?user_id=${userId}`, {
        method: 'DELETE'
      });
      
      const data = await response.json();
      
      if (data.success) {
        await fetchAlerts();
      } else {
        setError(data.error || 'Failed to delete alert');
      }
    } catch (err) {
      console.error('Delete alert error:', err);
      setError('Failed to delete alert');
    }
  };
  
  // Handle watchlist toggle
  const handleWatchlistToggle = (symbol) => {
    setWatchlist(prev => {
      if (prev.includes(symbol)) {
        return prev.filter(s => s !== symbol);
      } else {
        return [...prev, symbol];
      }
    });
  };
  
  // Format currency
  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: amount < 1 ? 6 : 2
    }).format(amount);
  };
  
  // Get trend color
  const getTrendColor = (change) => {
    if (change > 0) return '#4caf50';
    if (change < 0) return '#f44336';
    return '#666';
  };
  
  // Get trend icon
  const getTrendIcon = (change) => {
    if (change > 0) return <TrendingUp sx={{ color: '#4caf50' }} />;
    if (change < 0) return <TrendingDown sx={{ color: '#f44336' }} />;
    return <Timeline sx={{ color: '#666' }} />;
  };
  
  if (loading) {
    return (
      <Box sx={{ p: 3 }}>
        <Typography variant="h4" gutterBottom>
          Real-Time Crypto Tracker
        </Typography>
        <LinearProgress />
        <Typography sx={{ mt: 2 }}>Loading real-time data...</Typography>
      </Box>
    );
  }
  
  return (
    <Box sx={{ p: 3 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Typography variant="h4" gutterBottom>
          Real-Time Crypto Tracker
        </Typography>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <Box sx={{ display: 'flex', alignItems: 'center' }}>
            <Typography variant="body2" sx={{ mr: 1 }}>
              Auto-refresh
            </Typography>
            <Switch
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              size="small"
            />
          </Box>
          <IconButton onClick={fetchRealTimePrices} disabled={refreshing}>
            <Refresh />
          </IconButton>
          <Button
            variant="contained"
            startIcon={<AddIcon />}
            onClick={() => setAlertDialogOpen(true)}
          >
            Create Alert
          </Button>
        </Box>
      </Box>
      
      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}
      
      {/* Market Overview Cards */}
      {marketPulse && (
        <Grid container spacing={3} sx={{ mb: 3 }}>
          <Grid item xs={12} sm={6} md={3}>
            <Card>
              <CardContent>
                <Typography color="textSecondary" variant="body2">
                  Market Cap
                </Typography>
                <Typography variant="h6">
                  {new Intl.NumberFormat('en-US', {
                    style: 'currency',
                    currency: 'USD',
                    notation: 'compact',
                    maximumFractionDigits: 2
                  }).format(marketPulse.market_overview.total_market_cap)}
                </Typography>
                <Typography 
                  variant="body2" 
                  sx={{ color: getTrendColor(marketPulse.market_overview.market_cap_change_24h) }}
                >
                  {marketPulse.market_overview.market_cap_change_24h > 0 ? '+' : ''}
                  {marketPulse.market_overview.market_cap_change_24h.toFixed(2)}%
                </Typography>
              </CardContent>
            </Card>
          </Grid>
          
          <Grid item xs={12} sm={6} md={3}>
            <Card>
              <CardContent>
                <Typography color="textSecondary" variant="body2">
                  24h Volume
                </Typography>
                <Typography variant="h6">
                  {new Intl.NumberFormat('en-US', {
                    style: 'currency',
                    currency: 'USD',
                    notation: 'compact',
                    maximumFractionDigits: 2
                  }).format(marketPulse.market_overview.total_volume)}
                </Typography>
              </CardContent>
            </Card>
          </Grid>
          
          <Grid item xs={12} sm={6} md={3}>
            <Card>
              <CardContent>
                <Typography color="textSecondary" variant="body2">
                  BTC Dominance
                </Typography>
                <Typography variant="h6">
                  {marketPulse.market_overview.bitcoin_dominance.toFixed(1)}%
                </Typography>
              </CardContent>
            </Card>
          </Grid>
          
          <Grid item xs={12} sm={6} md={3}>
            <Card>
              <CardContent>
                <Typography color="textSecondary" variant="body2">
                  Active Cryptos
                </Typography>
                <Typography variant="h6">
                  {marketPulse.market_overview.active_cryptocurrencies.toLocaleString()}
                </Typography>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      )}
      
      <Grid container spacing={3}>
        {/* Watchlist */}
        <Grid item xs={12} lg={8}>
          <Card>
            <CardHeader title="Watchlist" />
            <CardContent>
              <TableContainer>
                <Table>
                  <TableHead>
                    <TableRow>
                      <TableCell>Asset</TableCell>
                      <TableCell align="right">Price</TableCell>
                      <TableCell align="right">24h Change</TableCell>
                      <TableCell align="right">Volume</TableCell>
                      <TableCell align="center">Chart</TableCell>
                      <TableCell align="center">Actions</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {watchlist.map((symbol) => {
                      const data = realTimeData[symbol];
                      const historical = historicalData[symbol];
                      
                      if (!data) return null;
                      
                      return (
                        <TableRow key={symbol}>
                          <TableCell>
                            <Box>
                              <Typography variant="body2" fontWeight="bold">
                                {data.symbol}
                              </Typography>
                              <Typography variant="caption" color="textSecondary">
                                {symbol}
                              </Typography>
                            </Box>
                          </TableCell>
                          <TableCell align="right">
                            <Typography variant="body2">
                              {data.formatted_price}
                            </Typography>
                            <Typography variant="caption" color="textSecondary">
                              Updated: {new Date(data.last_updated * 1000).toLocaleTimeString()}
                            </Typography>
                          </TableCell>
                          <TableCell align="right">
                            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end' }}>
                              {getTrendIcon(data.change_24h)}
                              <Box sx={{ ml: 1, color: getTrendColor(data.change_24h) }}>
                                <Typography variant="body2">
                                  {data.formatted_change}
                                </Typography>
                                {data.significant_change && (
                                  <Chip label="Hot" size="small" color="warning" />
                                )}
                              </Box>
                            </Box>
                          </TableCell>
                          <TableCell align="right">
                            {new Intl.NumberFormat('en-US', {
                              style: 'currency',
                              currency: 'USD',
                              notation: 'compact',
                              maximumFractionDigits: 2
                            }).format(data.volume_24h)}
                          </TableCell>
                          <TableCell align="center">
                            {historical && (
                              <Box sx={{ width: 100, height: 40 }}>
                                <ResponsiveContainer width="100%" height="100%">
                                  <AreaChart data={historical.data.slice(-24)}>
                                    <Area
                                      type="monotone"
                                      dataKey="price"
                                      stroke={getTrendColor(data.change_24h)}
                                      fill={getTrendColor(data.change_24h)}
                                      fillOpacity={0.2}
                                    />
                                  </AreaChart>
                                </ResponsiveContainer>
                              </Box>
                            )}
                          </TableCell>
                          <TableCell align="center">
                            <IconButton
                              size="small"
                              onClick={() => handleWatchlistToggle(symbol)}
                              color="primary"
                            >
                              <Star />
                            </IconButton>
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </TableContainer>
            </CardContent>
          </Card>
        </Grid>
        
        {/* Top Movers & Alerts */}
        <Grid item xs={12} lg={4}>
          {/* Top Gainers */}
          {marketPulse && (
            <Card sx={{ mb: 2 }}>
              <CardHeader title="Top Gainers" />
              <CardContent>
                <List dense>
                  {marketPulse.top_gainers.slice(0, 5).map((crypto) => (
                    <ListItem key={crypto.id}>
                      <ListItemText
                        primary={crypto.symbol.toUpperCase()}
                        secondary={crypto.formatted_price}
                      />
                      <ListItemSecondaryAction>
                        <Box sx={{ textAlign: 'right', color: '#4caf50' }}>
                          <Typography variant="body2">
                            +{crypto.price_change_24h.toFixed(2)}%
                          </Typography>
                        </Box>
                      </ListItemSecondaryAction>
                      <IconButton
                        edge="end"
                        size="small"
                        onClick={() => handleWatchlistToggle(crypto.id)}
                      >
                        {watchlist.includes(crypto.id) ? <Star color="primary" /> : <StarBorder />}
                      </IconButton>
                    </ListItem>
                  ))}
                </List>
              </CardContent>
            </Card>
          )}
          
          {/* Price Alerts */}
          <Card>
            <CardHeader 
              title="Price Alerts" 
              action={
                <IconButton onClick={() => setAlertDialogOpen(true)}>
                  <NotificationsActive />
                </IconButton>
              }
            />
            <CardContent>
              {alerts.length > 0 ? (
                <List dense>
                  {alerts.map((alert) => (
                    <ListItem key={alert.id}>
                      <ListItemText
                        primary={`${alert.symbol.toUpperCase()} ${alert.condition} ${formatCurrency(alert.target_price)}`}
                        secondary={`Created: ${new Date(alert.created_at).toLocaleDateString()}`}
                      />
                      <ListItemSecondaryAction>
                        <IconButton
                          edge="end"
                          size="small"
                          onClick={() => handleDeleteAlert(alert.id)}
                          color="error"
                        >
                          <DeleteIcon />
                        </IconButton>
                      </ListItemSecondaryAction>
                    </ListItem>
                  ))}
                </List>
              ) : (
                <Typography color="textSecondary" variant="body2">
                  No price alerts set. Create your first alert to get notified of price movements.
                </Typography>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>
      
      {/* Create Alert Dialog */}
      <Dialog open={alertDialogOpen} onClose={() => setAlertDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Create Price Alert</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 1 }}>
            <Grid item xs={12}>
              <FormControl fullWidth>
                <InputLabel>Cryptocurrency</InputLabel>
                <Select
                  value={alertForm.symbol}
                  onChange={(e) => setAlertForm({...alertForm, symbol: e.target.value})}
                  label="Cryptocurrency"
                >
                  {watchlist.map((symbol) => (
                    <MenuItem key={symbol} value={symbol}>
                      {symbol.toUpperCase()} - {realTimeData[symbol]?.formatted_price || 'N/A'}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={6}>
              <FormControl fullWidth>
                <InputLabel>Condition</InputLabel>
                <Select
                  value={alertForm.condition}
                  onChange={(e) => setAlertForm({...alertForm, condition: e.target.value})}
                  label="Condition"
                >
                  <MenuItem value="above">Price goes above</MenuItem>
                  <MenuItem value="below">Price goes below</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Target Price"
                type="number"
                value={alertForm.target_price}
                onChange={(e) => setAlertForm({...alertForm, target_price: e.target.value})}
                inputProps={{ step: "any", min: "0" }}
              />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAlertDialogOpen(false)}>Cancel</Button>
          <Button 
            onClick={handleCreateAlert} 
            variant="contained"
            disabled={!alertForm.symbol || !alertForm.target_price}
          >
            Create Alert
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default CryptoRealTimeTracker;