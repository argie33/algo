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
    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer component={Paper} variant="outlined" sx={{ maxHeight: 600 }}>
      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le stickyHeader size="small">
        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Symbol</td>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Price</td>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Change</td>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Bid/Ask</td>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Volume</td>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Trend</td>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Signal</td>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Status</td>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Actions</td>
          </tr>
        </thead>
        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
          {getFilteredData().map(([symbol, data]) => (
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
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                <div  variant="caption">
                  {formatPrice(data.bid)} / {formatPrice(data.ask)}
                </div>
              </td>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{formatNumber(data.volume)}</td>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                <div  title={`Trend: ${data.trend || 'neutral'}`}>
                  {getTrendIcon(data.trend)}
                </div>
              </td>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                {advancedSignals[symbol] && (
                  <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                    label={advancedSignals[symbol].recommendation?.action || 'HOLD'}
                    color={
                      advancedSignals[symbol].recommendation?.action === 'buy' ? 'success' :
                      advancedSignals[symbol].recommendation?.action === 'sell' ? 'error' : 'default'
                    }
                    size="small"
                  />
                )}
              </td>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                {isDataStale(symbol) ? (
                  <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="Stale" color="warning" size="small" />
                ) : (
                  <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="Live" color="success" size="small" />
                )}
              </td>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                <div  title="Generate Advanced Signal">
                  <button className="p-2 rounded-full hover:bg-gray-100" 
                    size="small" 
                    onClick={() => handleGenerateAdvancedSignal(symbol)}
                    disabled={!hasValidProvider('alpaca')}
                  >
                    <Assessment />
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
  );

  const renderMarketDataCards = () => (
    <div className="grid" container spacing={2}>
      {getFilteredData().map(([symbol, data]) => (
        <div className="grid" item xs={12} sm={6} md={4} key={symbol}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  display="flex" justifyContent="space-between" alignItems="center" mb={1}>
                <div  variant="h6" fontWeight="bold">
                  {symbol}
                </div>
                {getTrendIcon(data.trend)}
              </div>
              <div  variant="h4" fontWeight="bold" gutterBottom>
                {formatPrice(data.price)}
              </div>
              <div  variant="body2" gutterBottom>
                {formatPercent(data.change_percent)}
              </div>
              <div  display="flex" justifyContent="space-between" mt={2}>
                <div  variant="caption">
                  Vol: {formatNumber(data.volume)}
                </div>
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                  label={isDataStale(symbol) ? 'Stale' : 'Live'} 
                  color={isDataStale(symbol) ? 'warning' : 'success'} 
                  size="small" 
                />
              </div>
              {advancedSignals[symbol] && (
                <div  mt={1}>
                  <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                    label={`${advancedSignals[symbol].recommendation?.action || 'HOLD'} (${((advancedSignals[symbol].recommendation?.confidence || 0) * 100).toFixed(0)}%)`}
                    color={
                      advancedSignals[symbol].recommendation?.action === 'buy' ? 'success' :
                      advancedSignals[symbol].recommendation?.action === 'sell' ? 'error' : 'default'
                    }
                    size="small"
                  />
                </div>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );

  const renderChartView = () => (
    <div className="grid" container spacing={3}>
      {selectedSymbols.slice(0, 4).map(symbol => (
        <div className="grid" item xs={12} md={6} key={symbol}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Header title={`${symbol} Price Movement`} />
            <div className="bg-white shadow-md rounded-lg"Content>
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
            </div>
          </div>
        </div>
      ))}
    </div>
  );

  const renderTabContent = () => {
    switch (activeTab) {
      case 0:
        return viewMode === 'table' ? renderMarketDataTable() : renderMarketDataCards();
      case 1:
        return renderChartView();
      case 2:
        return (
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Header title="Advanced Signals" />
            <div className="bg-white shadow-md rounded-lg"Content>
              {Object.entries(advancedSignals).map(([symbol, signals]) => (
                <div  key={symbol} mb={2}>
                  <div  variant="h6">{symbol}</div>
                  <div  variant="body2">
                    Action: {signals.recommendation?.action || 'HOLD'}
                  </div>
                  <div  variant="body2">
                    Confidence: {((signals.recommendation?.confidence || 0) * 100).toFixed(1)}%
                  </div>
                  <div  variant="body2">
                    Rationale: {signals.recommendation?.rationale || 'N/A'}
                  </div>
                  <hr className="border-gray-200" sx={{ my: 1 }} />
                </div>
              ))}
            </div>
          </div>
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
      <div className="container mx-auto" maxWidth="xl" sx={{ py: 4 }}>
        {/* Header */}
        <div  sx={{ mb: 4 }}>
          <div  display="flex" justifyContent="space-between" alignItems="center" mb={2}>
            <div>
              <div  variant="h4" fontWeight={700} gutterBottom>
                🚀 Enhanced Live Data Monitor
              </div>
              <div  variant="body1" color="text.secondary">
                Real-time market data with advanced signal processing and portfolio integration
              </div>
            </div>
            <div>
              <button className="p-2 rounded-full hover:bg-gray-100" onClick={() => setFullscreen(!fullscreen)}>
                {fullscreen ? <FullscreenExit /> : <Fullscreen />}
              </button>
            </div>
          </div>
          <div  display="flex" gap={1} flexWrap="wrap">
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="Real-time Feed" color="primary" size="small" variant="outlined" />
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="Advanced Signals" color="success" size="small" variant="outlined" />
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="Portfolio Integration" color="info" size="small" variant="outlined" />
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="Risk Alerts" color="warning" size="small" variant="outlined" />
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
            title="Enhanced Connection Status"
            action={
              <div  display="flex" gap={1} alignItems="center">
                <div className="mb-4"Label
                  control={
                    <input type="checkbox" className="toggle"
                      checked={enableAdvancedSignals}
                      onChange={(e) => setEnableAdvancedSignals(e.target.checked)}
                    />
                  }
                  label="Advanced Signals"
                />
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
                <div  display="flex" gap={2} flexWrap="wrap">
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

        {/* Enhanced Statistics */}
        {showStats && (
          <div className="bg-white shadow-md rounded-lg" sx={{ mb: 3 }}>
            <div className="bg-white shadow-md rounded-lg"Header title="Enhanced Statistics" />
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
                    <div  variant="h4" color="success.main">{Object.keys(advancedSignals).length}</div>
                    <div  variant="caption">Advanced Signals</div>
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

        {/* Controls */}
        <div className="bg-white shadow-md rounded-lg" sx={{ mb: 3 }}>
          <div className="bg-white shadow-md rounded-lg"Content>
            <div className="grid" container spacing={3} alignItems="center">
              <div className="grid" item xs={12} md={4}>
                <Autocomplete
                  multiple
                  options={availableSymbols}
                  value={selectedSymbols}
                  onChange={(_, newValue) => setSelectedSymbols(newValue)}
                  renderInput={(params) => (
                    <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500" {...params} label="Subscribed Symbols" size="small" />
                  )}
                  renderTags={(value, getTagProps) =>
                    value.map((option, index) => (
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                        variant="outlined"
                        label={option}
                        size="small"
                        {...getTagProps({ index })}
                      />
                    ))
                  }
                />
              </div>
              
              <div className="grid" item xs={12} md={2}>
                <div className="mb-4" fullWidth size="small">
                  <label className="block text-sm font-medium text-gray-700 mb-1">Filter</label>
                  <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={filterCriteria}
                    onChange={(e) => setFilterCriteria(e.target.value)}
                    label="Filter"
                  >
                    <option  value="all">All Symbols</option>
                    <option  value="gainers">Gainers</option>
                    <option  value="losers">Losers</option>
                    <option  value="volume">High Volume</option>
                  </select>
                </div>
              </div>
              
              <div className="grid" item xs={12} md={2}>
                <div className="mb-4" fullWidth size="small">
                  <label className="block text-sm font-medium text-gray-700 mb-1">Refresh</label>
                  <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={refreshInterval}
                    onChange={(e) => setRefreshInterval(e.target.value)}
                    label="Refresh"
                  >
                    <option  value={1000}>1 Second</option>
                    <option  value={5000}>5 Seconds</option>
                    <option  value={10000}>10 Seconds</option>
                    <option  value={30000}>30 Seconds</option>
                  </select>
                </div>
              </div>
              
              <div className="grid" item xs={12} md={2}>
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
              </div>
              
              <div className="grid" item xs={12} md={2}>
                <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
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
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Tabs */}
        <div className="bg-white shadow-md rounded-lg">
          <div className="bg-white shadow-md rounded-lg"Header
            title={
              <div className="border-b border-gray-200" value={activeTab} onChange={(_, newValue) => setActiveTab(newValue)}>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Market Data" />
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Charts" />
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Advanced Signals" />
              </div>
            }
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
            {renderTabContent()}
          </div>
        </div>

        {/* Settings Dialog */}
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50" 
          open={settingsOpen} 
          onClose={() => setSettingsOpen(false)}
          maxWidth="md"
          fullWidth
        >
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Title>
            Enhanced Settings
            <button className="p-2 rounded-full hover:bg-gray-100"
              sx={{ position: 'absolute', right: 8, top: 8 }}
              onClick={() => setSettingsOpen(false)}
            >
              <Close />
            </button>
          </h2>
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Content dividers>
            <div className="grid" container spacing={3}>
              <div className="grid" item xs={12} md={6}>
                <div  variant="h6" gutterBottom>Connection Settings</div>
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
              </div>
              
              <div className="grid" item xs={12} md={6}>
                <div  variant="h6" gutterBottom>Advanced Features</div>
                <List>
                  <ListItem>
                    <ListItemIcon><Assessment /></ListItemIcon>
                    <ListItemText 
                      primary="Advanced Signals" 
                      secondary={enableAdvancedSignals ? 'Enabled' : 'Disabled'}
                    />
                    <input type="checkbox" className="toggle"
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
                    <input type="checkbox" className="toggle"
                      checked={enableRiskAlerts}
                      onChange={(e) => setEnableRiskAlerts(e.target.checked)}
                    />
                  </ListItem>
                </List>
              </div>
            </div>
          </div>
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Actions>
            <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" onClick={() => setSettingsOpen(false)}>Close</button>
          </div>
        </div>
      </div>
    </RequiresApiKeys>
  );
};

export default EnhancedLiveDataMonitor;