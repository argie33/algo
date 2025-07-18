import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Box,
  Paper,
  Typography,
  Grid,
  Card,
  CardContent,
  CardHeader,
  Switch,
  FormControlLabel,
  Button,
  Chip,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Autocomplete,
  Alert,
  LinearProgress,
  IconButton,
  Tooltip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Tabs,
  Tab,
  Badge,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  Divider,
  Avatar,
  CircularProgress
} from '@mui/material';
import {
  TrendingUp,
  TrendingDown,
  PlayArrow,
  Stop,
  Settings,
  Analytics,
  Speed,
  SignalWifi4Bar,
  SignalWifiOff,
  Refresh,
  Add,
  Delete,
  Timeline,
  ShowChart,
  MonetizationOn,
  Assessment,
  Warning,
  CheckCircle,
  Error,
  Info,
  Dashboard,
  CloudDone,
  Storage,
  PeopleAlt,
  Router,
  DataUsage,
  Memory
} from '@mui/icons-material';
import {
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer
} from 'recharts';
import { useAuth } from '../contexts/AuthContext';
import api from '../services/api';

// Chart.js registration removed - using recharts instead

/**
 * Centralized Live Data Service Dashboard
 * 
 * Based on FINANCIAL_PLATFORM_BLUEPRINT.md centralized architecture:
 * - Single websocket connection per symbol (not per user)
 * - Admin-managed data feeds for cost efficiency
 * - Centralized caching and distribution
 * - Real-time service health monitoring
 */

const LiveDataCentralized = () => {
  // Auth context
  const { user } = useAuth();

  // Service monitoring state
  const [serviceMetrics, setServiceMetrics] = useState({
    activeConnections: 0,
    totalSubscribers: 0,
    dataLatency: 0,
    errorRate: 0,
    connectionHealth: 'unknown',
    lastUpdate: null
  });

  // Admin configuration state
  const [adminConfig, setAdminConfig] = useState({
    enabledFeeds: ['stocks', 'options', 'crypto'],
    symbols: ['AAPL', 'MSFT', 'GOOGL', 'SPY', 'QQQ', 'TSLA'],
    providers: ['alpaca', 'polygon']
  });

  // Live data streams state
  const [liveStreams, setLiveStreams] = useState(new Map());
  const [subscribedSymbols, setSubscribedSymbols] = useState(new Set());

  // UI state
  const [activeTab, setActiveTab] = useState(0);
  const [isServiceRunning, setIsServiceRunning] = useState(false);
  const [newSymbol, setNewSymbol] = useState('');
  const [selectedProvider, setSelectedProvider] = useState('alpaca');

  // Refs for real-time updates
  const metricsInterval = useRef(null);
  const dataInterval = useRef(null);

  // Popular symbols for quick selection
  const POPULAR_SYMBOLS = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'NVDA', 'META', 'NFLX',
    'SPY', 'QQQ', 'IWM', 'VTI', 'AMD', 'CRM', 'ORCL', 'ADBE'
  ];

  // Initialize service monitoring
  useEffect(() => {
    fetchServiceMetrics();
    
    // Set up periodic metrics refresh
    metricsInterval.current = setInterval(fetchServiceMetrics, 5000);
    
    return () => {
      if (metricsInterval.current) clearInterval(metricsInterval.current);
      if (dataInterval.current) clearInterval(dataInterval.current);
    };
  }, []);

  // Fetch service health metrics
  const fetchServiceMetrics = async () => {
    try {
      const response = await api.get('/api/live-data/metrics');
      if (response.success) {
        setServiceMetrics(response.data);
        setIsServiceRunning(response.data.connectionHealth === 'healthy');
      }
    } catch (error) {
      console.error('Failed to fetch service metrics:', error);
      setServiceMetrics(prev => ({
        ...prev,
        connectionHealth: 'error',
        lastUpdate: new Date().toISOString()
      }));
    }
  };

  // Subscribe to symbol data
  const subscribeToSymbol = async (symbol) => {
    try {
      const response = await api.post('/api/live-data/subscribe', {
        symbol,
        provider: selectedProvider
      });
      
      if (response.success) {
        setSubscribedSymbols(prev => new Set([...prev, symbol]));
        console.log(`✅ Subscribed to ${symbol} via ${selectedProvider}`);
      }
    } catch (error) {
      console.error(`Failed to subscribe to ${symbol}:`, error);
    }
  };

  // Unsubscribe from symbol data
  const unsubscribeFromSymbol = async (symbol) => {
    try {
      const response = await api.post('/api/live-data/unsubscribe', {
        symbol
      });
      
      if (response.success) {
        setSubscribedSymbols(prev => {
          const newSet = new Set(prev);
          newSet.delete(symbol);
          return newSet;
        });
        
        setLiveStreams(prev => {
          const newMap = new Map(prev);
          newMap.delete(symbol);
          return newMap;
        });
        
        console.log(`✅ Unsubscribed from ${symbol}`);
      }
    } catch (error) {
      console.error(`Failed to unsubscribe from ${symbol}:`, error);
    }
  };

  // Add new symbol subscription
  const handleAddSymbol = () => {
    if (newSymbol.trim() && !subscribedSymbols.has(newSymbol.toUpperCase())) {
      subscribeToSymbol(newSymbol.toUpperCase());
      setNewSymbol('');
    }
  };

  // Service control functions
  const startLiveDataService = async () => {
    try {
      const response = await api.post('/api/live-data/start');
      if (response.success) {
        setIsServiceRunning(true);
        console.log('✅ Live data service started');
      }
    } catch (error) {
      console.error('Failed to start live data service:', error);
    }
  };

  const stopLiveDataService = async () => {
    try {
      const response = await api.post('/api/live-data/stop');
      if (response.success) {
        setIsServiceRunning(false);
        setLiveStreams(new Map());
        setSubscribedSymbols(new Set());
        console.log('✅ Live data service stopped');
      }
    } catch (error) {
      console.error('Failed to stop live data service:', error);
    }
  };

  // Get status color based on service health
  const getStatusColor = (health) => {
    switch (health) {
      case 'healthy': return 'success';
      case 'degraded': return 'warning';
      case 'error': return 'error';
      default: return 'default';
    }
  };

  // Metrics visualization data for recharts
  const connectionMetricsData = [
    { name: 'Active Connections', value: serviceMetrics.activeConnections, color: '#1976d2' },
    { name: 'Total Subscribers', value: serviceMetrics.totalSubscribers, color: '#2e7d32' },
    { name: 'Cached Symbols', value: subscribedSymbols.size, color: '#ed6c02' }
  ];

  const latencyData = Array.from({length: 10}, (_, i) => ({
    time: i + 1,
    latency: [45, 38, 42, 35, 48, 41, 39, 44, 37, serviceMetrics.dataLatency || 40][i]
  }));

  return (
    <div  sx={{ p: 3 }}>
      {/* Page Header */}
      <div  sx={{ mb: 4 }}>
        <div  variant="h3" component="h1" gutterBottom sx={{ fontWeight: 600 }}>
          Centralized Live Data Service
        </div>
        <div  variant="h6" color="text.secondary" sx={{ mb: 2 }}>
          Revolutionary architecture with single API connections per symbol for maximum efficiency
        </div>
        
        {/* Service Status Bar */}
        <div className="bg-white shadow-md rounded-lg" sx={{ mb: 3, backgroundColor: isServiceRunning ? 'success.main' : 'error.main', color: 'white' }}>
          <div className="bg-white shadow-md rounded-lg"Content sx={{ py: 2 }}>
            <div  sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div  sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                {isServiceRunning ? <CloudDone /> : <SignalWifiOff />}
                <div  variant="h6">
                  Service Status: {isServiceRunning ? 'OPERATIONAL' : 'STOPPED'}
                </div>
              </div>
              
              <div  sx={{ display: 'flex', gap: 1 }}>
                <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  variant="contained"
                  color={isServiceRunning ? "error" : "success"}
                  onClick={isServiceRunning ? stopLiveDataService : startLiveDataService}
                  startIcon={isServiceRunning ? <Stop /> : <PlayArrow />}
                  sx={{ color: 'white', bgcolor: 'rgba(255,255,255,0.2)' }}
                >
                  {isServiceRunning ? 'Stop Service' : 'Start Service'}
                </button>
                
                <button className="p-2 rounded-full hover:bg-gray-100" onClick={fetchServiceMetrics} sx={{ color: 'white' }}>
                  <Refresh />
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Main Navigation Tabs */}
      <div  sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
        <div className="border-b border-gray-200" value={activeTab} onChange={(e, v) => setActiveTab(v)} variant="scrollable" scrollButtons="auto">
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Service Metrics" icon={<Analytics />} />
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Live Streams" icon={<Timeline />} />
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Admin Config" icon={<Settings />} />
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Cost Analysis" icon={<MonetizationOn />} />
        </div>
      </div>

      {/* Tab Content */}
      {activeTab === 0 && (
        <div className="grid" container spacing={3}>
          {/* Key Metrics Cards */}
          <div className="grid" item xs={12} md={3}>
            <div className="bg-white shadow-md rounded-lg">
              <div className="bg-white shadow-md rounded-lg"Content>
                <div  sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div>
                    <div  color="text.secondary" gutterBottom>
                      Active Connections
                    </div>
                    <div  variant="h4" color="primary">
                      {serviceMetrics.activeConnections}
                    </div>
                    <div  variant="body2" color="text.secondary">
                      Websocket connections to providers
                    </div>
                  </div>
                  <Router color="primary" fontSize="large" />
                </div>
              </div>
            </div>
          </div>

          <div className="grid" item xs={12} md={3}>
            <div className="bg-white shadow-md rounded-lg">
              <div className="bg-white shadow-md rounded-lg"Content>
                <div  sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div>
                    <div  color="text.secondary" gutterBottom>
                      Total Subscribers
                    </div>
                    <div  variant="h4" color="success.main">
                      {serviceMetrics.totalSubscribers}
                    </div>
                    <div  variant="body2" color="text.secondary">
                      User sessions receiving data
                    </div>
                  </div>
                  <PeopleAlt color="success" fontSize="large" />
                </div>
              </div>
            </div>
          </div>

          <div className="grid" item xs={12} md={3}>
            <div className="bg-white shadow-md rounded-lg">
              <div className="bg-white shadow-md rounded-lg"Content>
                <div  sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div>
                    <div  color="text.secondary" gutterBottom>
                      Avg Latency
                    </div>
                    <div  variant="h4" color="warning.main">
                      {serviceMetrics.dataLatency}ms
                    </div>
                    <div  variant="body2" color="text.secondary">
                      Data delivery latency
                    </div>
                  </div>
                  <Speed color="warning" fontSize="large" />
                </div>
              </div>
            </div>
          </div>

          <div className="grid" item xs={12} md={3}>
            <div className="bg-white shadow-md rounded-lg">
              <div className="bg-white shadow-md rounded-lg"Content>
                <div  sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div>
                    <div  color="text.secondary" gutterBottom>
                      Error Rate
                    </div>
                    <div  variant="h4" color={serviceMetrics.errorRate > 0.05 ? "error" : "success"}>
                      {(serviceMetrics.errorRate * 100).toFixed(2)}%
                    </div>
                    <div  variant="body2" color="text.secondary">
                      Connection failure rate
                    </div>
                  </div>
                  <Assessment color={serviceMetrics.errorRate > 0.05 ? "error" : "success"} fontSize="large" />
                </div>
              </div>
            </div>
          </div>

          {/* Charts */}
          <div className="grid" item xs={12} md={6}>
            <div className="bg-white shadow-md rounded-lg">
              <div className="bg-white shadow-md rounded-lg"Header title="Connection Distribution" />
              <div className="bg-white shadow-md rounded-lg"Content>
                <div  sx={{ height: 300 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={connectionMetricsData}
                        cx="50%"
                        cy="50%"
                        outerRadius={80}
                        dataKey="value"
                        label={({name, value}) => `${name}: ${value}`}
                      >
                        {connectionMetricsData.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={entry.color} />
                        ))}
                      </Pie>
                      <div  />
                      <Legend />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>
          </div>

          <div className="grid" item xs={12} md={6}>
            <div className="bg-white shadow-md rounded-lg">
              <div className="bg-white shadow-md rounded-lg"Header title="Real-time Latency" />
              <div className="bg-white shadow-md rounded-lg"Content>
                <div  sx={{ height: 300 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={latencyData}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="time" />
                      <YAxis label={{ value: 'Latency (ms)', angle: -90, position: 'insideLeft' }} />
                      <div  />
                      <Legend />
                      <Line 
                        type="monotone" 
                        dataKey="latency" 
                        stroke="#1976d2" 
                        strokeWidth={2}
                        dot={{ fill: '#1976d2' }}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {activeTab === 1 && (
        <div className="grid" container spacing={3}>
          {/* Symbol Subscription Management */}
          <div className="grid" item xs={12}>
            <div className="bg-white shadow-md rounded-lg">
              <div className="bg-white shadow-md rounded-lg"Header 
                title="Symbol Subscriptions"
                subheader="Manage live data streams for specific symbols"
              />
              <div className="bg-white shadow-md rounded-lg"Content>
                <div  sx={{ display: 'flex', gap: 2, mb: 3, alignItems: 'center' }}>
                  <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    label="Symbol"
                    value={newSymbol}
                    onChange={(e) => setNewSymbol(e.target.value.toUpperCase())}
                    placeholder="AAPL"
                    size="small"
                    sx={{ minWidth: 120 }}
                  />
                  
                  <Autocomplete
                    value={selectedProvider}
                    onChange={(e, v) => setSelectedProvider(v)}
                    options={adminConfig.providers}
                    size="small"
                    sx={{ minWidth: 120 }}
                    renderInput={(params) => <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500" {...params} label="Provider" />}
                  />
                  
                  <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                    variant="contained"
                    onClick={handleAddSymbol}
                    startIcon={<Add />}
                    disabled={!newSymbol.trim() || subscribedSymbols.has(newSymbol.toUpperCase())}
                  >
                    Subscribe
                  </button>
                </div>

                {/* Quick Symbol Selection */}
                <div  sx={{ mb: 3 }}>
                  <div  variant="subtitle2" gutterBottom>Quick Subscribe:</div>
                  <div  sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                    {POPULAR_SYMBOLS.map(symbol => (
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                        key={symbol}
                        label={symbol}
                        variant={subscribedSymbols.has(symbol) ? "filled" : "outlined"}
                        color={subscribedSymbols.has(symbol) ? "primary" : "default"}
                        onClick={() => subscribedSymbols.has(symbol) ? unsubscribeFromSymbol(symbol) : subscribeToSymbol(symbol)}
                        icon={subscribedSymbols.has(symbol) ? <CheckCircle /> : <Add />}
                      />
                    ))}
                  </div>
                </div>

                {/* Active Subscriptions */}
                <div  variant="h6" gutterBottom>
                  Active Subscriptions ({subscribedSymbols.size})
                </div>
                
                {subscribedSymbols.size === 0 ? (
                  <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="info">
                    No active subscriptions. Add symbols to start receiving live data.
                  </div>
                ) : (
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer component={Paper} variant="outlined">
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le size="small">
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Symbol</td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Last Price</td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Change</td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Volume</td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Provider</td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Actions</td>
                        </tr>
                      </thead>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
                        {Array.from(subscribedSymbols).map(symbol => {
                          const data = liveStreams.get(symbol) || {};
                          return (
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={symbol}>
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                                <div  variant="subtitle2" fontWeight="bold">
                                  {symbol}
                                </div>
                              </td>
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>${data.price || '--'}</td>
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                                <div  sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                                  {data.change > 0 ? <TrendingUp color="success" /> : <TrendingDown color="error" />}
                                  <div  color={data.change > 0 ? 'success.main' : 'error.main'}>
                                    {data.change || '--'}%
                                  </div>
                                </div>
                              </td>
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>{data.volume?.toLocaleString() || '--'}</td>
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label={data.provider || selectedProvider} size="small" />
                              </td>
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                                <button className="p-2 rounded-full hover:bg-gray-100" 
                                  size="small" 
                                  color="error"
                                  onClick={() => unsubscribeFromSymbol(symbol)}
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
          </div>
        </div>
      )}

      {activeTab === 2 && (
        <div className="grid" container spacing={3}>
          <div className="grid" item xs={12}>
            <div className="bg-white shadow-md rounded-lg">
              <div className="bg-white shadow-md rounded-lg"Header 
                title="Service Configuration"
                subheader="Admin controls for centralized live data service"
              />
              <div className="bg-white shadow-md rounded-lg"Content>
                <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="info" sx={{ mb: 3 }}>
                  <div  variant="subtitle2" gutterBottom>Centralized Architecture Benefits:</div>
                  <div  variant="body2">
                    • Single API connection per symbol (not per user)<br/>
                    • Massive cost reduction vs per-user websockets<br/>
                    • Better performance through centralized caching<br/>
                    • Easier management and monitoring<br/>
                    • Can serve unlimited customers from same data streams
                  </div>
                </div>

                <div  variant="h6" gutterBottom>Enabled Data Feeds</div>
                <div  sx={{ display: 'flex', gap: 2, mb: 3 }}>
                  {adminConfig.enabledFeeds.map(feed => (
                    <div className="mb-4"Label
                      key={feed}
                      control={<input type="checkbox" className="toggle" defaultChecked />}
                      label={feed.charAt(0).toUpperCase() + feed.slice(1)}
                    />
                  ))}
                </div>

                <div  variant="h6" gutterBottom>Data Providers</div>
                <div  sx={{ display: 'flex', gap: 2, mb: 3 }}>
                  {adminConfig.providers.map(provider => (
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                      key={provider} 
                      label={provider.charAt(0).toUpperCase() + provider.slice(1)}
                      variant="filled"
                      color="primary"
                    />
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {activeTab === 3 && (
        <div className="grid" container spacing={3}>
          <div className="grid" item xs={12}>
            <div className="bg-white shadow-md rounded-lg">
              <div className="bg-white shadow-md rounded-lg"Header 
                title="Cost Analysis"
                subheader="Efficiency gains from centralized architecture"
              />
              <div className="bg-white shadow-md rounded-lg"Content>
                <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="success" sx={{ mb: 3 }}>
                  <div  variant="subtitle2" gutterBottom>Cost Optimization Achieved:</div>
                  <div  variant="body2">
                    Previous architecture: Each user ran their own websockets (expensive, redundant)<br/>
                    New architecture: Single connection per symbol shared across all users (efficient, scalable)
                  </div>
                </div>

                <div className="grid" container spacing={2}>
                  <div className="grid" item xs={12} md={6}>
                    <div  variant="h6" gutterBottom>Previous vs Current</div>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer component={Paper} variant="outlined">
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le size="small">
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Active Symbols</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{subscribedSymbols.size}</td>
                          </tr>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Connected Users</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{serviceMetrics.totalSubscribers}</td>
                          </tr>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Old Model: Connections</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right" sx={{ color: 'error.main' }}>
                              {subscribedSymbols.size * serviceMetrics.totalSubscribers}
                            </td>
                          </tr>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>New Model: Connections</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right" sx={{ color: 'success.main' }}>
                              {serviceMetrics.activeConnections}
                            </td>
                          </tr>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell><div  variant="subtitle2">Efficiency Gain</div></td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right" sx={{ color: 'success.main' }}>
                              <div  variant="subtitle2">
                                {subscribedSymbols.size * serviceMetrics.totalSubscribers > 0 
                                  ? `${Math.round((1 - serviceMetrics.activeConnections / (subscribedSymbols.size * serviceMetrics.totalSubscribers || 1)) * 100)}%`
                                  : '0%'
                                } reduction
                              </div>
                            </td>
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default LiveDataCentralized;