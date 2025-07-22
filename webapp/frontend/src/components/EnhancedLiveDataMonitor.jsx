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
  Autocomplete,
  Tabs,
  Tab,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  ToggleButton,
  ToggleButtonGroup
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
  Info,
  VpnKey,
  Assessment,
  DataUsage,
  Security,
  CloudSync,
  FilterList,
  ViewModule,
  ViewList,
  Fullscreen,
  FullscreenExit
} from '@mui/icons-material';
import { 
  LineChart, 
  Line, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip as RechartsTooltip, 
  ResponsiveContainer,
  AreaChart,
  Area,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell
} from 'recharts';
import realTimeDataService from '../services/realTimeDataService';
import { useApiKeys } from './ApiKeyProvider';
import RequiresApiKeys from './RequiresApiKeys';

const EnhancedLiveDataMonitor = () => {
  const { apiKeys, hasValidProvider } = useApiKeys();
  
  // Connection state
  const [isConnected, setIsConnected] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState('DISCONNECTED');
  const [connectionError, setConnectionError] = useState(null);
  
  // Data state
  const [marketData, setMarketData] = useState({});
  const [optionsData, setOptionsData] = useState({});
  const [subscriptions, setSubscriptions] = useState(new Set());
  const [statistics, setStatistics] = useState({});
  const [advancedSignals, setAdvancedSignals] = useState({});
  const [portfolioData, setPortfolioData] = useState({});
  
  // UI state
  const [activeTab, setActiveTab] = useState(0);
  const [viewMode, setViewMode] = useState('table');
  const [autoReconnect, setAutoReconnect] = useState(true);
  const [showStats, setShowStats] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [selectedSymbols, setSelectedSymbols] = useState(['AAPL', 'MSFT', 'GOOGL', 'TSLA']);
  const [priceHistory, setPriceHistory] = useState({});
  const [fullscreen, setFullscreen] = useState(false);
  const [filterCriteria, setFilterCriteria] = useState('all');
  const [refreshInterval, setRefreshInterval] = useState(5000);
  
  // Advanced features
  const [enableAdvancedSignals, setEnableAdvancedSignals] = useState(false);
  const [enablePortfolioIntegration, setEnablePortfolioIntegration] = useState(false);
  const [enableRiskAlerts, setEnableRiskAlerts] = useState(false);
  
  // References
  const statsInterval = useRef(null);
  const priceHistoryInterval = useRef(null);
  const signalInterval = useRef(null);
  
  // Available symbols for subscription
  const availableSymbols = [
    'AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA', 'AMZN', 'META', 'NFLX', 'BABA', 'CRM',
    'SPY', 'QQQ', 'IWM', 'DIA', 'VTI', 'ARKK', 'SQQQ', 'TQQQ',
    'GLD', 'SLV', 'TLT', 'HYG', 'VIX', 'UVXY', 'SOXL', 'LABU'
  ];

  useEffect(() => {
    setupWebSocketListeners();
    startStatsCollection();
    startPriceHistoryCollection();
    
    if (enableAdvancedSignals) {
      startAdvancedSignalProcessing();
    }
    
    return () => {
      clearInterval(statsInterval.current);
      clearInterval(priceHistoryInterval.current);
      clearInterval(signalInterval.current);
      realTimeDataService.removeAllListeners();
    };
  }, [enableAdvancedSignals]);

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
      if (data && data.data) {
        Object.keys(data.data).forEach(symbol => {
          const symbolData = data.data[symbol];
          if (symbolData && !symbolData.error) {
            setMarketData(prev => ({
              ...prev,
              [symbol]: {
                ...symbolData,
                receivedAt: Date.now(),
                trend: calculateTrend(prev[symbol], symbolData)
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
            volume: data.volume,
            timestamp: new Date(currentTime).toLocaleTimeString()
          }].slice(-100); // Keep last 100 points
          
          return {
            ...prev,
            [symbol]: newHistory
          };
        });
      });
    }, refreshInterval);
  };

  const startAdvancedSignalProcessing = () => {
    signalInterval.current = setInterval(async () => {
      if (hasValidProvider('alpaca')) {
        for (const symbol of selectedSymbols) {
          try {
            const response = await fetch('/api/advanced/signals/generate', {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${localStorage.getItem('token')}`
              },
              body: JSON.stringify({
                symbol,
                timeframe: '1d',
                lookback: 50
              })
            });
            
            if (response.ok) {
              const data = await response.json();
              if (data.success) {
                setAdvancedSignals(prev => ({
                  ...prev,
                  [symbol]: data.data.signals
                }));
              }
            }
          } catch (error) {
            console.warn('Failed to generate advanced signal for', symbol, error);
          }
        }
      }
    }, 30000); // Every 30 seconds
  };

  const calculateTrend = (prevData, currentData) => {
    if (!prevData || !currentData) return 'neutral';
    
    const priceDiff = currentData.price - prevData.price;
    const percentChange = (priceDiff / prevData.price) * 100;
    
    if (percentChange > 0.1) return 'bullish';
    if (percentChange < -0.1) return 'bearish';
    return 'neutral';
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

  const handleGenerateAdvancedSignal = async (symbol) => {
    try {
      const response = await fetch('/api/advanced/signals/generate', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        },
        body: JSON.stringify({
          symbol,
          timeframe: '1d',
          lookback: 100
        })
      });
      
      if (response.ok) {
        const data = await response.json();
        if (data.success) {
          setAdvancedSignals(prev => ({
            ...prev,
            [symbol]: data.data.signals
          }));
        }
      }
    } catch (error) {
      console.error('Failed to generate advanced signal:', error);
    }
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
      <Typography component="span" sx={{ color }}>
        {sign}{percent.toFixed(2)}%
      </Typography>
    );
  };

  const isDataStale = (symbol) => {
    const data = marketData[symbol];
    if (!data || !data.receivedAt) return true;
    return Date.now() - data.receivedAt > 30000; // 30 seconds
  };

  const getFilteredData = () => {
    const filteredData = Object.entries(marketData);
    
    switch (filterCriteria) {
      case 'gainers':
        return filteredData.filter(([_, data]) => data.change_percent > 0);
      case 'losers':
        return filteredData.filter(([_, data]) => data.change_percent < 0);
      case 'volume':
        return filteredData.filter(([_, data]) => data.volume > 1000000);
      default:
        return filteredData;
    }
  };

  const getTrendIcon = (trend) => {
    switch (trend) {
      case 'bullish': return <TrendingUp sx={{ color: 'success.main' }} />;
      case 'bearish': return <TrendingDown sx={{ color: 'error.main' }} />;
      default: return <ShowChart sx={{ color: 'grey.500' }} />;
    }
  };

  const renderMarketDataTable = () => (
    <TableContainer component={Paper} variant="outlined" sx={{ maxHeight: 600 }}>
      <Table stickyHeader size="small">
        <TableHead>
          <TableRow>
            <TableCell>Symbol</TableCell>
            <TableCell align="right">Price</TableCell>
            <TableCell align="right">Change</TableCell>
            <TableCell align="right">Bid/Ask</TableCell>
            <TableCell align="right">Volume</TableCell>
            <TableCell>Trend</TableCell>
            <TableCell>Signal</TableCell>
            <TableCell>Status</TableCell>
            <TableCell>Actions</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {getFilteredData().map(([symbol, data]) => (
            <TableRow key={symbol} hover>
              <TableCell>
                <Typography variant="body2" fontWeight="bold">
                  {symbol}
                </Typography>
              </TableCell>
              <TableCell align="right">
                <Typography variant="body2" fontWeight="bold">
                  {formatPrice(data.price)}
                </Typography>
              </TableCell>
              <TableCell align="right">
                {formatPercent(data.change_percent)}
              </TableCell>
              <TableCell align="right">
                <Typography variant="caption">
                  {formatPrice(data.bid)} / {formatPrice(data.ask)}
                </Typography>
              </TableCell>
              <TableCell align="right">{formatNumber(data.volume)}</TableCell>
              <TableCell>
                <Tooltip title={`Trend: ${data.trend || 'neutral'}`}>
                  {getTrendIcon(data.trend)}
                </Tooltip>
              </TableCell>
              <TableCell>
                {advancedSignals[symbol] && (
                  <Chip
                    label={advancedSignals[symbol].recommendation?.action || 'HOLD'}
                    color={
                      advancedSignals[symbol].recommendation?.action === 'buy' ? 'success' :
                      advancedSignals[symbol].recommendation?.action === 'sell' ? 'error' : 'default'
                    }
                    size="small"
                  />
                )}
              </TableCell>
              <TableCell>
                {isDataStale(symbol) ? (
                  <Chip label="Stale" color="warning" size="small" />
                ) : (
                  <Chip label="Live" color="success" size="small" />
                )}
              </TableCell>
              <TableCell>
                <Tooltip title="Generate Advanced Signal">
                  <IconButton 
                    size="small" 
                    onClick={() => handleGenerateAdvancedSignal(symbol)}
                    disabled={!hasValidProvider('alpaca')}
                  >
                    <Assessment />
                  </IconButton>
                </Tooltip>
                <Tooltip title="Remove Symbol">
                  <IconButton 
                    size="small" 
                    onClick={() => handleUnsubscribeSymbol(symbol)}
                  >
                    <Remove />
                  </IconButton>
                </Tooltip>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );

  const renderMarketDataCards = () => (
    <Grid container spacing={2}>
      {getFilteredData().map(([symbol, data]) => (
        <Grid item xs={12} sm={6} md={4} key={symbol}>
          <Card>
            <CardContent>
              <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
                <Typography variant="h6" fontWeight="bold">
                  {symbol}
                </Typography>
                {getTrendIcon(data.trend)}
              </Box>
              <Typography variant="h4" fontWeight="bold" gutterBottom>
                {formatPrice(data.price)}
              </Typography>
              <Typography variant="body2" gutterBottom>
                {formatPercent(data.change_percent)}
              </Typography>
              <Box display="flex" justifyContent="space-between" mt={2}>
                <Typography variant="caption">
                  Vol: {formatNumber(data.volume)}
                </Typography>
                <Chip 
                  label={isDataStale(symbol) ? 'Stale' : 'Live'} 
                  color={isDataStale(symbol) ? 'warning' : 'success'} 
                  size="small" 
                />
              </Box>
              {advancedSignals[symbol] && (
                <Box mt={1}>
                  <Chip
                    label={`${advancedSignals[symbol].recommendation?.action || 'HOLD'} (${((advancedSignals[symbol].recommendation?.confidence || 0) * 100).toFixed(0)}%)`}
                    color={
                      advancedSignals[symbol].recommendation?.action === 'buy' ? 'success' :
                      advancedSignals[symbol].recommendation?.action === 'sell' ? 'error' : 'default'
                    }
                    size="small"
                  />
                </Box>
              )}
            </CardContent>
          </Card>
        </Grid>
      ))}
    </Grid>
  );

  const renderChartView = () => (
    <Grid container spacing={3}>
      {selectedSymbols.slice(0, 4).map(symbol => (
        <Grid item xs={12} md={6} key={symbol}>
          <Card>
            <CardHeader title={`${symbol} Price Movement`} />
            <CardContent>
              <ResponsiveContainer width="100%" height={200}>
                <AreaChart data={priceHistory[symbol] || []}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="timestamp" tick={{ fontSize: 10 }} />
                  <YAxis domain={['dataMin - 0.1', 'dataMax + 0.1']} tick={{ fontSize: 10 }} />
                  <RechartsTooltip 
                    formatter={(value) => [`$${value}`, 'Price']}
                    labelFormatter={(label) => `Time: ${label}`}
                  />
                  <Area 
                    type="monotone" 
                    dataKey="price" 
                    stroke="#8884d8" 
                    fill="#8884d8"
                    fillOpacity={0.6}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </Grid>
      ))}
    </Grid>
  );

  const renderTabContent = () => {
    switch (activeTab) {
      case 0:
        return viewMode === 'table' ? renderMarketDataTable() : renderMarketDataCards();
      case 1:
        return renderChartView();
      case 2:
        return (
          <Card>
            <CardHeader title="Advanced Signals" />
            <CardContent>
              {Object.entries(advancedSignals).map(([symbol, signals]) => (
                <Box key={symbol} mb={2}>
                  <Typography variant="h6">{symbol}</Typography>
                  <Typography variant="body2">
                    Action: {signals.recommendation?.action || 'HOLD'}
                  </Typography>
                  <Typography variant="body2">
                    Confidence: {((signals.recommendation?.confidence || 0) * 100).toFixed(1)}%
                  </Typography>
                  <Typography variant="body2">
                    Rationale: {signals.recommendation?.rationale || 'N/A'}
                  </Typography>
                  <Divider sx={{ my: 1 }} />
                </Box>
              ))}
            </CardContent>
          </Card>
        );
      default:
        return null;
    }
  };

  return (
    <RequiresApiKeys 
      requiredProviders={['alpaca']} 
      allowSkip={true}
      message="Live data monitoring requires Alpaca API keys for real-time market data access."
    >
      <Container maxWidth="xl" sx={{ py: 4 }}>
        {/* Header */}
        <Box sx={{ mb: 4 }}>
          <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
            <Box>
              <Typography variant="h4" fontWeight={700} gutterBottom>
                🚀 Enhanced Live Data Monitor
              </Typography>
              <Typography variant="body1" color="text.secondary">
                Real-time market data with advanced signal processing and portfolio integration
              </Typography>
            </Box>
            <Box>
              <IconButton onClick={() => setFullscreen(!fullscreen)}>
                {fullscreen ? <FullscreenExit /> : <Fullscreen />}
              </IconButton>
            </Box>
          </Box>
          <Box display="flex" gap={1} flexWrap="wrap">
            <Chip label="Real-time Feed" color="primary" size="small" variant="outlined" />
            <Chip label="Advanced Signals" color="success" size="small" variant="outlined" />
            <Chip label="Portfolio Integration" color="info" size="small" variant="outlined" />
            <Chip label="Risk Alerts" color="warning" size="small" variant="outlined" />
          </Box>
        </Box>

        {connectionError && (
          <Alert severity="error" sx={{ mb: 3 }} onClose={() => setConnectionError(null)}>
            {connectionError}
          </Alert>
        )}

        {/* Connection Status */}
        <Card sx={{ mb: 3 }}>
          <CardHeader
            title="Enhanced Connection Status"
            action={
              <Box display="flex" gap={1} alignItems="center">
                <FormControlLabel
                  control={
                    <Switch
                      checked={enableAdvancedSignals}
                      onChange={(e) => setEnableAdvancedSignals(e.target.checked)}
                    />
                  }
                  label="Advanced Signals"
                />
                <FormControlLabel
                  control={
                    <Switch
                      checked={autoReconnect}
                      onChange={(e) => setAutoReconnect(e.target.checked)}
                    />
                  }
                  label="Auto Reconnect"
                />
                <IconButton onClick={() => setSettingsOpen(true)}>
                  <Settings />
                </IconButton>
              </Box>
            }
          />
          <CardContent>
            <Grid container spacing={3} alignItems="center">
              <Grid item xs={12} sm={3}>
                <Box display="flex" alignItems="center" gap={2}>
                  <Badge 
                    color={getConnectionColor()} 
                    variant="dot" 
                    sx={{ '& .MuiBadge-dot': { width: 12, height: 12 } }}
                  >
                    <NetworkCheck fontSize="large" />
                  </Badge>
                  <Box>
                    <Typography variant="h6" fontWeight="bold">
                      {connectionStatus}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      WebSocket Status
                    </Typography>
                  </Box>
                </Box>
              </Grid>
              
              <Grid item xs={12} sm={6}>
                <Box display="flex" gap={2} flexWrap="wrap">
                  {!isConnected ? (
                    <Button
                      variant="contained"
                      startIcon={<PlayArrow />}
                      onClick={handleConnect}
                      disabled={connectionStatus === 'CONNECTING'}
                    >
                      {connectionStatus === 'CONNECTING' ? 'Connecting...' : 'Connect'}
                    </Button>
                  ) : (
                    <Button
                      variant="outlined"
                      startIcon={<Stop />}
                      onClick={handleDisconnect}
                    >
                      Disconnect
                    </Button>
                  )}
                  
                  <Button
                    variant="outlined"
                    startIcon={<Refresh />}
                    onClick={() => window.location.reload()}
                  >
                    Refresh
                  </Button>
                  
                  <Button
                    variant="outlined"
                    startIcon={<Analytics />}
                    onClick={() => setShowStats(!showStats)}
                  >
                    {showStats ? 'Hide' : 'Show'} Stats
                  </Button>
                </Box>
              </Grid>
              
              <Grid item xs={12} sm={3}>
                <Box>
                  <Typography variant="caption" color="text.secondary">Active Subscriptions</Typography>
                  <Typography variant="h6" fontWeight="bold">
                    {subscriptions.size}
                  </Typography>
                </Box>
              </Grid>
            </Grid>
          </CardContent>
        </Card>

        {/* Enhanced Statistics */}
        {showStats && (
          <Card sx={{ mb: 3 }}>
            <CardHeader title="Enhanced Statistics" />
            <CardContent>
              <Grid container spacing={3}>
                <Grid item xs={6} sm={3}>
                  <Box textAlign="center">
                    <Typography variant="h4" color="primary">{statistics.messagesReceived || 0}</Typography>
                    <Typography variant="caption">Messages Received</Typography>
                  </Box>
                </Grid>
                <Grid item xs={6} sm={3}>
                  <Box textAlign="center">
                    <Typography variant="h4" color="secondary">{statistics.messagesSent || 0}</Typography>
                    <Typography variant="caption">Messages Sent</Typography>
                  </Box>
                </Grid>
                <Grid item xs={6} sm={3}>
                  <Box textAlign="center">
                    <Typography variant="h4" color="success.main">{Object.keys(advancedSignals).length}</Typography>
                    <Typography variant="caption">Advanced Signals</Typography>
                  </Box>
                </Grid>
                <Grid item xs={6} sm={3}>
                  <Box textAlign="center">
                    <Typography variant="h4" color="warning.main">{statistics.reconnectCount || 0}</Typography>
                    <Typography variant="caption">Reconnections</Typography>
                  </Box>
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        )}

        {/* Controls */}
        <Card sx={{ mb: 3 }}>
          <CardContent>
            <Grid container spacing={3} alignItems="center">
              <Grid item xs={12} md={4}>
                <Autocomplete
                  multiple
                  options={availableSymbols}
                  value={selectedSymbols}
                  onChange={(_, newValue) => setSelectedSymbols(newValue)}
                  renderInput={(params) => (
                    <TextField {...params} label="Subscribed Symbols" size="small" />
                  )}
                  renderTags={(value, getTagProps) =>
                    value.map((option, index) => (
                      <Chip
                        key={index}
                        variant="outlined"
                        label={option}
                        size="small"
                        {...getTagProps({ index })}
                      />
                    ))
                  }
                />
              </Grid>
              
              <Grid item xs={12} md={2}>
                <FormControl fullWidth size="small">
                  <InputLabel>Filter</InputLabel>
                  <Select
                    value={filterCriteria}
                    onChange={(e) => setFilterCriteria(e.target.value)}
                    label="Filter"
                  >
                    <MenuItem value="all">All Symbols</MenuItem>
                    <MenuItem value="gainers">Gainers</MenuItem>
                    <MenuItem value="losers">Losers</MenuItem>
                    <MenuItem value="volume">High Volume</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
              
              <Grid item xs={12} md={2}>
                <FormControl fullWidth size="small">
                  <InputLabel>Refresh</InputLabel>
                  <Select
                    value={refreshInterval}
                    onChange={(e) => setRefreshInterval(e.target.value)}
                    label="Refresh"
                  >
                    <MenuItem value={1000}>1 Second</MenuItem>
                    <MenuItem value={5000}>5 Seconds</MenuItem>
                    <MenuItem value={10000}>10 Seconds</MenuItem>
                    <MenuItem value={30000}>30 Seconds</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
              
              <Grid item xs={12} md={2}>
                <ToggleButtonGroup
                  value={viewMode}
                  exclusive
                  onChange={(_, newMode) => newMode && setViewMode(newMode)}
                  size="small"
                >
                  <ToggleButton value="table">
                    <ViewList />
                  </ToggleButton>
                  <ToggleButton value="cards">
                    <ViewModule />
                  </ToggleButton>
                </ToggleButtonGroup>
              </Grid>
              
              <Grid item xs={12} md={2}>
                <Button
                  variant="contained"
                  startIcon={<CloudSync />}
                  onClick={() => {
                    selectedSymbols.forEach(symbol => {
                      if (hasValidProvider('alpaca')) {
                        handleGenerateAdvancedSignal(symbol);
                      }
                    });
                  }}
                  disabled={!hasValidProvider('alpaca')}
                  fullWidth
                >
                  Sync Signals
                </Button>
              </Grid>
            </Grid>
          </CardContent>
        </Card>

        {/* Tabs */}
        <Card>
          <CardHeader
            title={
              <Tabs value={activeTab} onChange={(_, newValue) => setActiveTab(newValue)}>
                <Tab label="Market Data" />
                <Tab label="Charts" />
                <Tab label="Advanced Signals" />
              </Tabs>
            }
            action={
              <Chip
                label={isConnected ? 'LIVE' : 'OFFLINE'}
                color={isConnected ? 'success' : 'error'}
                icon={isConnected ? <NotificationsActive /> : <Notifications />}
                size="small"
              />
            }
          />
          <CardContent>
            {renderTabContent()}
          </CardContent>
        </Card>

        {/* Settings Dialog */}
        <Dialog 
          open={settingsOpen} 
          onClose={() => setSettingsOpen(false)}
          maxWidth="md"
          fullWidth
        >
          <DialogTitle>
            Enhanced Settings
            <IconButton
              sx={{ position: 'absolute', right: 8, top: 8 }}
              onClick={() => setSettingsOpen(false)}
            >
              <Close />
            </IconButton>
          </DialogTitle>
          <DialogContent dividers>
            <Grid container spacing={3}>
              <Grid item xs={12} md={6}>
                <Typography variant="h6" gutterBottom>Connection Settings</Typography>
                <List>
                  <ListItem>
                    <ListItemIcon><Speed /></ListItemIcon>
                    <ListItemText 
                      primary="Refresh Interval" 
                      secondary={`${refreshInterval / 1000}s`}
                    />
                  </ListItem>
                  <ListItem>
                    <ListItemIcon><NetworkCheck /></ListItemIcon>
                    <ListItemText 
                      primary="Auto Reconnect" 
                      secondary={autoReconnect ? 'Enabled' : 'Disabled'}
                    />
                  </ListItem>
                </List>
              </Grid>
              
              <Grid item xs={12} md={6}>
                <Typography variant="h6" gutterBottom>Advanced Features</Typography>
                <List>
                  <ListItem>
                    <ListItemIcon><Assessment /></ListItemIcon>
                    <ListItemText 
                      primary="Advanced Signals" 
                      secondary={enableAdvancedSignals ? 'Enabled' : 'Disabled'}
                    />
                    <Switch
                      checked={enableAdvancedSignals}
                      onChange={(e) => setEnableAdvancedSignals(e.target.checked)}
                    />
                  </ListItem>
                  <ListItem>
                    <ListItemIcon><Security /></ListItemIcon>
                    <ListItemText 
                      primary="Risk Alerts" 
                      secondary={enableRiskAlerts ? 'Enabled' : 'Disabled'}
                    />
                    <Switch
                      checked={enableRiskAlerts}
                      onChange={(e) => setEnableRiskAlerts(e.target.checked)}
                    />
                  </ListItem>
                </List>
              </Grid>
            </Grid>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setSettingsOpen(false)}>Close</Button>
          </DialogActions>
        </Dialog>
      </Container>
    </RequiresApiKeys>
  );
};

export default EnhancedLiveDataMonitor;