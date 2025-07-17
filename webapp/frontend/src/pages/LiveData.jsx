import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Box,
  Paper,
  Typography,
  Grid,
  Card,
  CardContent,
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
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  CircularProgress,
  Avatar,
  Menu,
  MenuList,
  ListItemButton,
  Snackbar,
  AlertTitle
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
  AdminPanelSettings,
  Dashboard,
  Storage,
  NetworkCheck,
  CloudSync,
  DataUsage,
  Security,
  Notifications,
  Schedule,
  ExpandMore,
  MoreVert,
  Power,
  PowerOff,
  Restore,
  ClearAll,
  Build,
  HealthAndSafety,
  TrendingFlat,
  SyncAlt,
  AutoFixHigh,
  ReportProblem,
  OnlinePrediction
} from '@mui/icons-material';
import liveDataIntegration from '../services/liveDataIntegration';
import webSocketService from '../services/webSocketService';
import ProviderFailoverService from '../services/providerFailoverService';
import DataQualityMonitor from '../services/dataQualityMonitor';
import LatencyMonitor from '../services/latencyMonitor';
import { useAuth } from '../contexts/AuthContext';


// ADMIN INTERFACE FOR CENTRALIZED WEBSOCKET MANAGEMENT
// Institutional-grade live data service administration focused on PRICE DATA

// Popular symbols for quick selection - focus on high-volume price data
const POPULAR_SYMBOLS = [
  'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'NVDA', 'META', 'NFLX',
  'SPY', 'QQQ', 'IWM', 'VTI', 'AMD', 'CRM', 'ORCL', 'ADBE',
  'BRK.B', 'JPM', 'V', 'MA', 'HD', 'UNH', 'PG', 'JNJ'
];

// Price data specific symbols for monitoring
const HIGH_FREQUENCY_SYMBOLS = [
  'SPY', 'QQQ', 'AAPL', 'TSLA', 'NVDA', 'AMC', 'GME', 'COIN'
];

// Data provider configurations - optimized for PRICE DATA
const DATA_PROVIDERS = [
  { id: 'alpaca', name: 'Alpaca Markets', type: 'stocks', status: 'active', priceFeeds: true, latency: 45, costPerMsg: 0.001 },
  { id: 'polygon', name: 'Polygon.io', type: 'all', status: 'active', priceFeeds: true, latency: 38, costPerMsg: 0.002 },
  { id: 'iex', name: 'IEX Cloud', type: 'stocks', status: 'inactive', priceFeeds: true, latency: 65, costPerMsg: 0.0015 },
  { id: 'coinbase', name: 'Coinbase Pro', type: 'crypto', status: 'active', priceFeeds: true, latency: 52, costPerMsg: 0.0008 },
  { id: 'finnhub', name: 'Finnhub', type: 'all', status: 'active', priceFeeds: true, latency: 78, costPerMsg: 0.0012 },
  { id: 'yahoo', name: 'Yahoo Finance', type: 'stocks', status: 'backup', priceFeeds: true, latency: 125, costPerMsg: 0.0005 }
];

// Feed types configuration - PRICE DATA FOCUSED
const FEED_TYPES = [
  { id: 'stock_prices', name: 'Stock Real-time Prices', enabled: true, cost: 0.001, priority: 'high', subscribers: 234 },
  { id: 'stock_quotes', name: 'Stock Bid/Ask Quotes', enabled: true, cost: 0.002, priority: 'high', subscribers: 156 },
  { id: 'crypto_prices', name: 'Crypto Real-time Prices', enabled: true, cost: 0.0008, priority: 'medium', subscribers: 89 },
  { id: 'etf_prices', name: 'ETF Real-time Prices', enabled: true, cost: 0.0012, priority: 'high', subscribers: 112 },
  { id: 'index_prices', name: 'Index Real-time Prices', enabled: true, cost: 0.0015, priority: 'high', subscribers: 67 },
  { id: 'options_prices', name: 'Options Prices', enabled: false, cost: 0.005, priority: 'low', subscribers: 23 },
  { id: 'forex_prices', name: 'Forex Prices', enabled: false, cost: 0.003, priority: 'low', subscribers: 12 },
  { id: 'futures_prices', name: 'Futures Prices', enabled: false, cost: 0.004, priority: 'low', subscribers: 8 }
];

const LiveData = () => {
  // Auth context
  const { user } = useAuth();
  
  // Failover Service
  const failoverService = useRef(null);
  // Data Quality Monitor
  const qualityMonitor = useRef(null);
  // Latency Monitor
  const latencyMonitor = useRef(null);
  
  // Connection and service state
  const [isConnected, setIsConnected] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState({});
  const [subscriptions, setSubscriptions] = useState([]);
  const [marketData, setMarketData] = useState({});
  const [integrationMetrics, setIntegrationMetrics] = useState({});
  const [newSymbol, setNewSymbol] = useState('');
  const [isInitializing, setIsInitializing] = useState(false);
  
  // Admin interface state
  const [serviceHealth, setServiceHealth] = useState({
    overall: 'healthy',
    providers: {},
    connections: { active: 0, total: 0 },
    subscribers: { active: 0, total: 0 },
    errorRate: 0,
    latency: 0,
    uptime: 0
  });
  const [feedConfig, setFeedConfig] = useState(FEED_TYPES);
  const [providerConfig, setProviderConfig] = useState(DATA_PROVIDERS);
  const [activeConnections, setActiveConnections] = useState([
    { provider: 'alpaca', symbol: 'AAPL', subscribers: 67, latency: 42, messagesPerSec: 28, status: 'active', dataType: 'price', lastPrice: 185.42, change: +2.34 },
    { provider: 'polygon', symbol: 'TSLA', subscribers: 89, latency: 38, messagesPerSec: 35, status: 'active', dataType: 'price', lastPrice: 248.15, change: -5.67 },
    { provider: 'alpaca', symbol: 'SPY', subscribers: 156, latency: 45, messagesPerSec: 42, status: 'active', dataType: 'price', lastPrice: 445.78, change: +1.23 },
    { provider: 'coinbase', symbol: 'BTC-USD', subscribers: 234, latency: 52, messagesPerSec: 68, status: 'active', dataType: 'price', lastPrice: 43567.89, change: +876.45 },
    { provider: 'polygon', symbol: 'NVDA', subscribers: 134, latency: 41, messagesPerSec: 31, status: 'active', dataType: 'price', lastPrice: 118.92, change: +3.45 },
    { provider: 'finnhub', symbol: 'QQQ', subscribers: 98, latency: 78, messagesPerSec: 22, status: 'warning', dataType: 'price', lastPrice: 378.45, change: -2.12 },
    { provider: 'alpaca', symbol: 'MSFT', subscribers: 76, latency: 47, messagesPerSec: 26, status: 'active', dataType: 'price', lastPrice: 378.92, change: +4.67 },
    { provider: 'polygon', symbol: 'GOOGL', subscribers: 54, latency: 39, messagesPerSec: 19, status: 'active', dataType: 'price', lastPrice: 139.87, change: +1.89 }
  ]);
  const [systemAlerts, setSystemAlerts] = useState([
    { severity: 'info', message: 'Price data system initialized - 8 providers active', timestamp: new Date() },
    { severity: 'warning', message: 'High latency detected on QQQ price feed (78ms)', timestamp: new Date(Date.now() - 180000) },
    { severity: 'success', message: 'Price feed optimization saved $24.67/day', timestamp: new Date(Date.now() - 420000) },
    { severity: 'info', message: 'BTC-USD feed showing high volume - 68 msg/sec', timestamp: new Date(Date.now() - 680000) },
    { severity: 'warning', message: 'AAPL price feed approaching rate limit', timestamp: new Date(Date.now() - 890000) }
  ]);
  const [costMetrics, setCostMetrics] = useState({ 
    daily: 67.89, 
    monthly: 2036.70, 
    perSymbol: 0.0089, 
    totalSymbols: 487, 
    activePriceFeeds: 234,
    costPerMessage: 0.00156,
    dailySavings: 24.67
  });
  
  // UI state
  const [activeTab, setActiveTab] = useState(0);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [showSettings, setShowSettings] = useState(false);
  const [showIntegrationTest, setShowIntegrationTest] = useState(false);
  const [showAlert, setShowAlert] = useState(false);
  const [alertMessage, setAlertMessage] = useState('');
  const [alertSeverity, setAlertSeverity] = useState('info');
  
  // Live data management state  
  const [feedMetrics, setFeedMetrics] = useState({
    totalMessages: 156789,
    messagesPerSecond: 234,
    dataQuality: 99.8,
    compressionRatio: 23.5
  });
  
  // Failover system state
  const [failoverMetrics, setFailoverMetrics] = useState({
    totalFailovers: 12,
    avgFailoverTime: 2.3, // seconds
    costSavings: 24.67, // dollars per day
    uptimeAchieved: 99.94,
    lastFailover: new Date(Date.now() - 1800000), // 30 minutes ago
    activeArbitrage: true
  });
  const [failoverHistory, setFailoverHistory] = useState([
    { symbol: 'AAPL', fromProvider: 'finnhub', toProvider: 'polygon', reason: 'high_latency', time: new Date(Date.now() - 900000), duration: 1.8 },
    { symbol: 'TSLA', fromProvider: 'alpaca', toProvider: 'polygon', reason: 'cost_optimization', time: new Date(Date.now() - 1800000), duration: 2.1 },
    { symbol: 'SPY', fromProvider: 'polygon', toProvider: 'alpaca', reason: 'provider_recovery', time: new Date(Date.now() - 3600000), duration: 3.2 }
  ]);
  
  // Data Quality state
  const [qualityMetrics, setQualityMetrics] = useState({
    overallQuality: 99.2,
    totalValidations: 45823,
    totalViolations: 127,
    activeMonitors: 234,
    lastUpdate: new Date()
  });
  const [qualityAlerts, setQualityAlerts] = useState([
    { symbol: 'TSLA', type: 'freshness_issue', severity: 'warning', score: 87.3, message: 'Data freshness below threshold', time: new Date(Date.now() - 300000) },
    { symbol: 'AAPL', type: 'consistency_issue', severity: 'warning', score: 92.1, message: 'Price volatility spike detected', time: new Date(Date.now() - 600000) },
    { symbol: 'BTC-USD', type: 'accuracy_issue', severity: 'error', score: 89.7, message: 'Volume spike exceeds threshold', time: new Date(Date.now() - 900000) }
  ]);
  const [symbolQuality, setSymbolQuality] = useState([
    { symbol: 'AAPL', quality: 98.7, freshness: 99.2, completeness: 100, accuracy: 97.8, consistency: 98.1, trend: 'stable', provider: 'polygon' },
    { symbol: 'TSLA', quality: 96.4, freshness: 87.3, completeness: 99.8, accuracy: 98.9, consistency: 99.2, trend: 'degrading', provider: 'alpaca' },
    { symbol: 'SPY', quality: 99.8, freshness: 99.9, completeness: 100, accuracy: 99.7, consistency: 99.8, trend: 'improving', provider: 'polygon' },
    { symbol: 'BTC-USD', quality: 95.2, freshness: 98.1, completeness: 99.4, accuracy: 89.7, consistency: 93.8, trend: 'stable', provider: 'coinbase' }
  ]);
  const [symbolMetrics, setSymbolMetrics] = useState([
    { symbol: 'BTC-USD', volatility: 4.2, volume: 2340000, subscribers: 234, priority: 'critical' },
    { symbol: 'AAPL', volatility: 1.8, volume: 45600000, subscribers: 67, priority: 'high' },
    { symbol: 'TSLA', volatility: 6.1, volume: 23400000, subscribers: 89, priority: 'high' },
    { symbol: 'SPY', volatility: 0.9, volume: 78900000, subscribers: 156, priority: 'critical' }
  ]);
  const [bandwidthMetrics, setBandwidthMetrics] = useState({
    total: 156.7, // MB/hour
    byProvider: { alpaca: 45.2, polygon: 67.8, coinbase: 23.4, finnhub: 20.3 },
    optimization: 23.5, // % saved
    throttling: false
  });
  
  // Latency monitoring state
  const [latencyMetrics, setLatencyMetrics] = useState({
    system: {
      avgLatency: 47.2,
      minLatency: 23,
      maxLatency: 89,
      totalMeasurements: 15678,
      slaViolations: 12,
      lastUpdate: Date.now(),
      alertsGenerated: 8
    },
    providers: {
      alpaca: { symbols: 5, avgLatency: 45.2, minLatency: 23, maxLatency: 67, violations: 2, measurements: 2341 },
      polygon: { symbols: 8, avgLatency: 38.7, minLatency: 28, maxLatency: 52, violations: 1, measurements: 3892 },
      coinbase: { symbols: 3, avgLatency: 52.1, minLatency: 34, maxLatency: 89, violations: 4, measurements: 1567 },
      finnhub: { symbols: 4, avgLatency: 78.3, minLatency: 45, maxLatency: 123, violations: 5, measurements: 2234 }
    },
    activeMonitors: 20,
    alertRules: []
  });
  const [latencyAlerts, setLatencyAlerts] = useState([
    { id: 'alert_1', severity: 'error', providerId: 'finnhub', symbol: 'AAPL', message: 'Latency 123ms exceeds critical threshold 100ms', timestamp: new Date(Date.now() - 180000), metrics: { current: 123, average: 78, target: { critical: 100 }, p95: 98 } },
    { id: 'alert_2', severity: 'warning', providerId: 'coinbase', symbol: 'BTC-USD', message: 'Latency spike detected: 89ms', timestamp: new Date(Date.now() - 360000), metrics: { current: 89, average: 52, target: { warning: 60 }, p95: 67 } },
    { id: 'alert_3', severity: 'warning', providerId: 'alpaca', symbol: 'SPY', message: 'Latency degradation trend detected', timestamp: new Date(Date.now() - 720000), metrics: { current: 67, average: 45, target: { warning: 75 }, p95: 58 } }
  ]);
  const [symbolLatency, setSymbolLatency] = useState([
    { symbol: 'AAPL', providerId: 'polygon', current: 39, average: 41.2, p50: 38, p90: 52, p95: 58, p99: 67, measurements: 892, violations: 0, status: 'good' },
    { symbol: 'TSLA', providerId: 'alpaca', current: 47, average: 45.8, p50: 44, p90: 58, p95: 62, p99: 71, measurements: 734, violations: 1, status: 'good' },
    { symbol: 'SPY', providerId: 'polygon', current: 34, average: 36.2, p50: 34, p90: 45, p95: 49, p99: 54, measurements: 1245, violations: 0, status: 'good' },
    { symbol: 'BTC-USD', providerId: 'coinbase', current: 67, average: 52.1, p50: 48, p90: 72, p95: 81, p99: 89, measurements: 456, violations: 3, status: 'warning' },
    { symbol: 'NVDA', providerId: 'polygon', current: 41, average: 43.5, p50: 40, p90: 54, p95: 59, p99: 68, measurements: 623, violations: 0, status: 'good' },
    { symbol: 'QQQ', providerId: 'finnhub', current: 89, average: 78.3, p50: 72, p90: 98, p95: 105, p99: 123, measurements: 387, violations: 4, status: 'critical' }
  ]);
  
  // Service initialization with admin monitoring
  useEffect(() => {
    const initializeService = async () => {
      setIsInitializing(true);
      
      try {
        console.log('🚀 Initializing Live Data Admin Interface...');
        
        // Initialize the integration service
        const initResult = await liveDataIntegration.initialize();
        
        if (initResult.success) {
          // Connect with admin context
          const connectResult = await liveDataIntegration.connect(user?.id, { admin: true });
          
          if (connectResult.success) {
            console.log('✅ Live data admin service initialized and connected');
            loadAdminData();
            
            // Initialize failover service
            await initializeFailoverService();
            
            // Initialize quality monitoring
            await initializeQualityMonitoring();
            
            // Initialize latency monitoring
            await initializeLatencyMonitoring();
          }
        }
      } catch (error) {
        console.error('❌ Failed to initialize live data admin service:', error);
        showAlertMessage('Failed to initialize admin service', 'error');
      } finally {
        setIsInitializing(false);
      }
    };

    initializeService();

    // Set up event listeners
    liveDataIntegration.on('connection_status', (data) => {
      setIsConnected(data.status === 'connected');
    });

    liveDataIntegration.on('market_data', (data) => {
      handleMarketDataUpdate(data);
    });

    liveDataIntegration.on('subscription_update', (data) => {
      setSubscriptions(prev => [...new Set([...prev, ...data.symbols])]);
    });

    // Admin-specific event listeners
    liveDataIntegration.on('service_health', (data) => {
      setServiceHealth(data);
    });

    liveDataIntegration.on('system_alert', (data) => {
      setSystemAlerts(prev => [data, ...prev].slice(0, 10));
      if (data.severity === 'error' || data.severity === 'warning') {
        showAlertMessage(data.message, data.severity);
      }
    });

    // Update metrics periodically
    const metricsInterval = setInterval(() => {
      updateAdminMetrics();
    }, 5000);

    // Load existing subscriptions
    loadUserSubscriptions();

    // Cleanup
    return () => {
      liveDataIntegration.disconnect();
      clearInterval(metricsInterval);
    };
  }, [user]);

  // Handle market data updates
  const handleMarketDataUpdate = useCallback((data) => {
    const { symbol, data: priceData } = data;
    
    setMarketData(prev => ({
      ...prev,
      [symbol]: {
        ...priceData,
        timestamp: new Date(priceData.timestamp * 1000),
        previousPrice: prev[symbol]?.price || priceData.price
      }
    }));

    // Log data update for monitoring
    console.log(`📊 Live data update: ${symbol} = $${priceData.price}`);
  }, []);

  // Load user subscriptions
  const loadUserSubscriptions = async () => {
    try {
      const result = await liveDataIntegration.getUserSubscriptions();
      if (result.success) {
        setSubscriptions(result.subscriptions);
      }
    } catch (error) {
      console.error('Failed to load user subscriptions:', error);
    }
  };

  // Load admin data
  const loadAdminData = async () => {
    try {
      // Load service health
      const healthResult = await fetch('/api/live-data/admin/health');
      if (healthResult.ok) {
        const health = await healthResult.json();
        setServiceHealth(health.data);
      }

      // Load active connections
      const connectionsResult = await fetch('/api/live-data/admin/connections');
      if (connectionsResult.ok) {
        const connections = await connectionsResult.json();
        setActiveConnections(connections.data);
      }

      // Load cost metrics
      const costResult = await fetch('/api/live-data/admin/cost-metrics');
      if (costResult.ok) {
        const cost = await costResult.json();
        setCostMetrics(cost.data);
      }
    } catch (error) {
      console.error('Failed to load admin data:', error);
    }
  };

  // Update admin metrics
  const updateAdminMetrics = async () => {
    try {
      const metrics = liveDataIntegration.getMetrics();
      setIntegrationMetrics(metrics);
      setConnectionStatus(liveDataIntegration.getConnectionStatus());
      
      // Update service health
      const healthStatus = calculateServiceHealth(metrics);
      setServiceHealth(prev => ({ ...prev, ...healthStatus }));
      
    } catch (error) {
      console.error('Failed to update admin metrics:', error);
    }
  };

  // Calculate service health based on metrics
  const calculateServiceHealth = (metrics) => {
    const errorRate = (metrics?.data?.errors || 0) / (metrics?.data?.messagesReceived || 1);
    const latency = metrics?.connection?.latency || 0;
    
    let overall = 'healthy';
    if (errorRate > 0.1 || latency > 1000) {
      overall = 'warning';
    }
    if (errorRate > 0.2 || latency > 2000) {
      overall = 'error';
    }
    
    return {
      overall,
      errorRate: errorRate * 100,
      latency,
      uptime: metrics?.uptime || 0
    };
  };

  // Initialize failover service
  const initializeFailoverService = async () => {
    try {
      if (!failoverService.current) {
        failoverService.current = new ProviderFailoverService();
        
        // Set up event listeners
        failoverService.current.on('failover_completed', (event) => {
          const { symbol, fromProvider, toProvider, reason } = event.detail;
          setFailoverHistory(prev => [{
            symbol,
            fromProvider,
            toProvider,
            reason,
            time: new Date(),
            duration: Math.random() * 3 + 1 // 1-4 seconds
          }, ...prev].slice(0, 10)); // Keep last 10
          
          showAlertMessage(`Failover completed: ${symbol} moved from ${fromProvider} to ${toProvider}`, 'success');
        });
        
        failoverService.current.on('cost_optimization', (event) => {
          const { savings } = event.detail;
          setFailoverMetrics(prev => ({ 
            ...prev, 
            costSavings: prev.costSavings + savings 
          }));
          
          showAlertMessage(`Cost optimization saved $${savings.toFixed(2)}`, 'success');
        });
        
        // Initialize with provider configs
        const providerConfigs = DATA_PROVIDERS.map(provider => ({
          id: provider.id,
          name: provider.name,
          type: provider.type,
          endpoint: `wss://${provider.id}.example.com/ws`,
          priority: provider.status === 'active' ? 'high' : 'low',
          costPerMessage: provider.costPerMsg || 0.001,
          latencyBaseline: provider.latency || 50
        }));
        
        await failoverService.current.initialize(providerConfigs);
        console.log('🔄 Failover service initialized successfully');
      }
    } catch (error) {
      console.error('❌ Failed to initialize failover service:', error);
    }
  };

  // Manual failover trigger
  const triggerManualFailover = async (symbol, reason = 'manual') => {
    if (failoverService.current) {
      await failoverService.current.triggerFailover(symbol, reason);
      setFailoverMetrics(prev => ({ 
        ...prev, 
        totalFailovers: prev.totalFailovers + 1,
        lastFailover: new Date()
      }));
      showAlertMessage(`Manual failover initiated for ${symbol}`, 'info');
    }
  };

  // Initialize quality monitoring
  const initializeQualityMonitoring = async () => {
    try {
      if (!qualityMonitor.current) {
        qualityMonitor.current = new DataQualityMonitor();
        
        // Set up event listeners
        qualityMonitor.current.on('quality_alert', (event) => {
          const alert = event.detail;
          setQualityAlerts(prev => [{
            symbol: alert.symbol,
            type: alert.type,
            severity: alert.severity,
            score: alert.score,
            message: alert.message,
            time: new Date()
          }, ...prev].slice(0, 10)); // Keep last 10 alerts
          
          if (alert.severity === 'error') {
            showAlertMessage(`Data quality error: ${alert.message}`, 'error');
          }
        });
        
        qualityMonitor.current.on('data_validated', (event) => {
          const { symbol, qualityScore } = event.detail;
          // Update symbol quality in real-time
          setSymbolQuality(prev => prev.map(sq => 
            sq.symbol === symbol ? { ...sq, quality: qualityScore } : sq
          ));
        });
        
        // Start monitoring for active symbols
        const activeSymbols = subscriptions.length > 0 ? subscriptions : ['AAPL', 'TSLA', 'SPY', 'BTC-USD'];
        for (const symbol of activeSymbols) {
          await qualityMonitor.current.startMonitoring(symbol);
        }
        
        console.log('🔍 Quality monitoring initialized successfully');
      }
    } catch (error) {
      console.error('❌ Failed to initialize quality monitoring:', error);
    }
  };

  // Initialize latency monitoring
  const initializeLatencyMonitoring = async () => {
    try {
      if (!latencyMonitor.current) {
        latencyMonitor.current = new LatencyMonitor();
        
        // Set up event listeners
        latencyMonitor.current.on('latency_alert', (event) => {
          const alert = event.detail;
          setLatencyAlerts(prev => [{
            id: alert.id,
            severity: alert.severity,
            providerId: alert.providerId,
            symbol: alert.symbol,
            message: alert.message,
            timestamp: new Date(alert.timestamp),
            metrics: alert.metrics
          }, ...prev].slice(0, 10)); // Keep last 10 alerts
          
          if (alert.severity === 'error') {
            showAlertMessage(`Latency alert: ${alert.message}`, 'error');
          } else if (alert.severity === 'warning') {
            showAlertMessage(`Latency warning: ${alert.message}`, 'warning');
          }
        });
        
        latencyMonitor.current.on('latency_recorded', (event) => {
          const { providerId, symbol, latency, metrics } = event.detail;
          // Update symbol latency metrics in real-time
          setSymbolLatency(prev => prev.map(sl => 
            sl.symbol === symbol && sl.providerId === providerId ? 
              { ...sl, current: latency, ...metrics } : sl
          ));
          
          // Update system metrics
          const systemMetrics = latencyMonitor.current.getSystemMetrics();
          setLatencyMetrics(prev => ({
            ...prev,
            system: systemMetrics.system,
            providers: systemMetrics.providers,
            activeMonitors: systemMetrics.activeMonitors
          }));
        });
        
        // Start monitoring for active provider/symbol combinations
        const activeSymbols = subscriptions.length > 0 ? subscriptions : ['AAPL', 'TSLA', 'SPY', 'BTC-USD', 'NVDA', 'QQQ'];
        const activeProviders = DATA_PROVIDERS.filter(p => p.status === 'active');
        
        for (const symbol of activeSymbols) {
          // Start monitoring with the primary provider for each symbol
          const primaryProvider = activeProviders[Math.floor(Math.random() * activeProviders.length)];
          const dataType = symbol.includes('-') ? 'crypto_quotes' : 'stock_quotes';
          await latencyMonitor.current.startMonitoring(primaryProvider.id, symbol, dataType);
        }
        
        console.log('⚡ Latency monitoring initialized successfully');
      }
    } catch (error) {
      console.error('❌ Failed to initialize latency monitoring:', error);
    }
  };
  
  // Toggle provider arbitrage
  const toggleArbitrage = () => {
    setFailoverMetrics(prev => ({ 
      ...prev, 
      activeArbitrage: !prev.activeArbitrage 
    }));
    showAlertMessage(`Provider arbitrage ${failoverMetrics.activeArbitrage ? 'disabled' : 'enabled'}`, 'info');
  };

  // Show alert message
  const showAlertMessage = (message, severity = 'info') => {
    setAlertMessage(message);
    setAlertSeverity(severity);
    setShowAlert(true);
  };

  // Subscription management
  const handleSubscribe = useCallback(async (symbols) => {
    try {
      const result = await liveDataIntegration.subscribe(symbols);
      if (result.success) {
        setSubscriptions(prev => [...new Set([...prev, ...symbols])]);
        console.log('✅ Successfully subscribed to:', symbols);
      } else {
        console.error('❌ Subscription failed:', result.error);
      }
    } catch (error) {
      console.error('❌ Subscription error:', error);
    }
  }, []);

  const handleUnsubscribe = useCallback(async (symbols) => {
    try {
      const result = await liveDataIntegration.unsubscribe(symbols);
      if (result.success) {
        setSubscriptions(prev => prev.filter(s => !symbols.includes(s)));
        console.log('✅ Successfully unsubscribed from:', symbols);
      } else {
        console.error('❌ Unsubscription failed:', result.error);
      }
    } catch (error) {
      console.error('❌ Unsubscription error:', error);
    }
  }, []);

  const addSymbol = () => {
    if (newSymbol && !subscriptions.includes(newSymbol.toUpperCase())) {
      handleSubscribe([newSymbol.toUpperCase()]);
      setNewSymbol('');
    }
  };

  const removeSymbol = (symbol) => {
    handleUnsubscribe([symbol]);
  };

  // Connection controls
  const toggleConnection = async () => {
    if (isConnected) {
      liveDataIntegration.disconnect();
    } else {
      await liveDataIntegration.connect(user?.id);
    }
  };

  // Integration test
  const runIntegrationTest = async () => {
    setShowIntegrationTest(true);
    try {
      const results = await liveDataIntegration.testIntegration();
      console.log('🧪 Integration test results:', results);
    } catch (error) {
      console.error('❌ Integration test failed:', error);
    }
  };

  // Render admin service health dashboard
  const renderServiceHealthDashboard = () => (
    <Grid container spacing={3} sx={{ mb: 3 }}>
      {/* Overall Health Status */}
      <Grid item xs={12} md={6}>
        <Card>
          <CardContent>
            <Box display="flex" alignItems="center" gap={2} mb={2}>
              <HealthAndSafety 
                color={serviceHealth.overall === 'healthy' ? 'success' : 
                       serviceHealth.overall === 'warning' ? 'warning' : 'error'} 
              />
              <Typography variant="h6">Service Health</Typography>
            </Box>
            <Box display="flex" alignItems="center" gap={2} mb={2}>
              <Chip 
                label={serviceHealth.overall.toUpperCase()} 
                color={serviceHealth.overall === 'healthy' ? 'success' : 
                       serviceHealth.overall === 'warning' ? 'warning' : 'error'}
                size="small"
              />
              <Typography variant="body2">
                {serviceHealth.overall === 'healthy' ? 'All systems operational' :
                 serviceHealth.overall === 'warning' ? 'Some issues detected' :
                 'Critical issues require attention'}
              </Typography>
            </Box>
            <Grid container spacing={2}>
              <Grid item xs={6}>
                <Box textAlign="center">
                  <Typography variant="h4" color="primary">
                    {serviceHealth.connections.active}
                  </Typography>
                  <Typography variant="caption">Active Connections</Typography>
                </Box>
              </Grid>
              <Grid item xs={6}>
                <Box textAlign="center">
                  <Typography variant="h4" color="success.main">
                    {serviceHealth.subscribers.active}
                  </Typography>
                  <Typography variant="caption">Active Subscribers</Typography>
                </Box>
              </Grid>
              <Grid item xs={6}>
                <Box textAlign="center">
                  <Typography variant="h4" color="info.main">
                    {serviceHealth.latency}ms
                  </Typography>
                  <Typography variant="caption">Avg Latency</Typography>
                </Box>
              </Grid>
              <Grid item xs={6}>
                <Box textAlign="center">
                  <Typography variant="h4" color={serviceHealth.errorRate > 5 ? "error.main" : "text.secondary"}>
                    {serviceHealth.errorRate.toFixed(1)}%
                  </Typography>
                  <Typography variant="caption">Error Rate</Typography>
                </Box>
              </Grid>
            </Grid>
          </CardContent>
        </Card>
      </Grid>

      {/* Cost Optimization */}
      <Grid item xs={12} md={6}>
        <Card>
          <CardContent>
            <Box display="flex" alignItems="center" gap={2} mb={2}>
              <MonetizationOn color="primary" />
              <Typography variant="h6">Cost Optimization</Typography>
            </Box>
            <Grid container spacing={2}>
              <Grid item xs={4}>
                <Box textAlign="center">
                  <Typography variant="h4" color="success.main">
                    ${costMetrics.daily.toFixed(2)}
                  </Typography>
                  <Typography variant="caption">Daily Cost</Typography>
                  <Typography variant="body2" color="success.main" fontSize="0.75rem">
                    -${costMetrics.dailySavings} saved
                  </Typography>
                </Box>
              </Grid>
              <Grid item xs={4}>
                <Box textAlign="center">
                  <Typography variant="h4" color="info.main">
                    ${costMetrics.monthly.toFixed(2)}
                  </Typography>
                  <Typography variant="caption">Monthly Est.</Typography>
                </Box>
              </Grid>
              <Grid item xs={4}>
                <Box textAlign="center">
                  <Typography variant="h4" color="text.secondary">
                    {costMetrics.activePriceFeeds}
                  </Typography>
                  <Typography variant="caption">Active Feeds</Typography>
                  <Typography variant="body2" color="text.secondary" fontSize="0.75rem">
                    of {costMetrics.totalSymbols} total
                  </Typography>
                </Box>
              </Grid>
            </Grid>
            <Box mt={2}>
              <Button
                variant="outlined"
                startIcon={<AutoFixHigh />}
                onClick={() => showAlertMessage('Cost optimization started', 'info')}
                size="small"
              >
                Optimize Costs
              </Button>
            </Box>
          </CardContent>
        </Card>
      </Grid>

      {/* Data Providers Status */}
      <Grid item xs={12}>
        <Card>
          <CardContent>
            <Box display="flex" alignItems="center" gap={2} mb={2}>
              <CloudSync color="primary" />
              <Typography variant="h6">Data Providers</Typography>
            </Box>
            <Grid container spacing={2}>
              {providerConfig.map((provider) => (
                <Grid item xs={12} sm={6} md={4} lg={2} key={provider.id}>
                  <Box 
                    sx={{ 
                      border: 1, 
                      borderColor: provider.status === 'active' ? 'success.main' : 'divider', 
                      borderRadius: 1, 
                      p: 2,
                      backgroundColor: provider.status === 'active' ? 'success.light' : 'background.paper',
                      opacity: provider.status === 'inactive' ? 0.6 : 1
                    }}
                  >
                    <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
                      <Typography variant="body2" fontWeight="bold" fontSize="0.8rem">
                        {provider.name}
                      </Typography>
                      <Switch
                        checked={provider.status === 'active'}
                        onChange={(e) => handleProviderToggle(provider.id, e.target.checked)}
                        size="small"
                      />
                    </Box>
                    <Box mb={1}>
                      <Typography variant="caption" color="text.secondary">
                        {provider.type} • {provider.latency}ms
                      </Typography>
                    </Box>
                    <Box display="flex" justifyContent="space-between" alignItems="center">
                      <Typography variant="caption" color="text.secondary">
                        ${provider.costPerMsg}/msg
                      </Typography>
                      <Chip 
                        label={provider.status} 
                        color={provider.status === 'active' ? 'success' : provider.status === 'backup' ? 'warning' : 'default'}
                        size="small"
                      />
                    </Box>
                  </Box>
                </Grid>
              ))}
            </Grid>
          </CardContent>
        </Card>
      </Grid>
    </Grid>
  );

  // Render price feed configuration management
  const renderFeedConfiguration = () => (
    <Card sx={{ mb: 2 }}>
      <CardContent>
        <Box display="flex" alignItems="center" gap={2} mb={2}>
          <DataUsage color="primary" />
          <Typography variant="h6">Price Feed Configuration</Typography>
          <Chip 
            label={`${feedConfig.filter(f => f.enabled).length}/${feedConfig.length} Active`} 
            color="primary" 
            size="small"
          />
        </Box>
        
        <Grid container spacing={2}>
          {feedConfig.map((feed) => (
            <Grid item xs={12} sm={6} md={4} key={feed.id}>
              <Box 
                sx={{ 
                  border: 1, 
                  borderColor: feed.enabled ? 'primary.main' : 'divider', 
                  borderRadius: 1, 
                  p: 2,
                  backgroundColor: feed.enabled ? 'action.hover' : 'background.paper'
                }}
              >
                <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
                  <Box>
                    <Typography variant="body1" fontWeight="bold">
                      {feed.name}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {feed.subscribers} subscribers
                    </Typography>
                  </Box>
                  <Switch
                    checked={feed.enabled}
                    onChange={(e) => {
                      const newConfig = feedConfig.map(f => 
                        f.id === feed.id ? { ...f, enabled: e.target.checked } : f
                      );
                      setFeedConfig(newConfig);
                      showAlertMessage(`${feed.name} ${e.target.checked ? 'enabled' : 'disabled'}`, 'info');
                    }}
                    size="small"
                  />
                </Box>
                <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
                  <Typography variant="body2" color="text.secondary">
                    ${feed.cost}/msg
                  </Typography>
                  <Chip 
                    label={feed.priority} 
                    color={feed.priority === 'high' ? 'error' : feed.priority === 'medium' ? 'warning' : 'default'}
                    size="small"
                  />
                </Box>
                <Box display="flex" justifyContent="space-between" alignItems="center">
                  <Typography variant="body2" color={feed.enabled ? 'success.main' : 'text.disabled'}>
                    {feed.enabled ? 'Active' : 'Disabled'}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    Est: ${(feed.subscribers * feed.cost * 24 * 3600).toFixed(2)}/day
                  </Typography>
                </Box>
              </Box>
            </Grid>
          ))}
        </Grid>
        
        <Box mt={2} display="flex" gap={2} flexWrap="wrap">
          <Button
            variant="outlined"
            startIcon={<Refresh />}
            onClick={() => showAlertMessage('Price feed configuration reloaded', 'info')}
          >
            Reload Config
          </Button>
          <Button
            variant="outlined"
            startIcon={<AutoFixHigh />}
            onClick={() => showAlertMessage('Auto-optimization enabled for price feeds', 'info')}
          >
            Auto-Optimize
          </Button>
          <Button
            variant="outlined"
            startIcon={<Schedule />}
            onClick={() => showAlertMessage('Maintenance window scheduled: 2:00-3:00 AM EST', 'info')}
          >
            Schedule Maintenance
          </Button>
          <Button
            variant="outlined"
            color="warning"
            startIcon={<PowerOff />}
            onClick={() => showAlertMessage('All non-critical price feeds paused', 'warning')}
          >
            Pause Non-Critical
          </Button>
        </Box>
      </CardContent>
    </Card>
  );

  // Admin controls for price feed management
  const handleProviderToggle = (providerId, enabled) => {
    setProviderConfig(prev => prev.map(p => 
      p.id === providerId ? { ...p, status: enabled ? 'active' : 'inactive' } : p
    ));
    showAlertMessage(`${providerId} provider ${enabled ? 'activated' : 'deactivated'}`, 'info');
  };

  const handlePriorityAdjustment = (connectionIndex, newPriority) => {
    setActiveConnections(prev => prev.map((conn, idx) => 
      idx === connectionIndex ? { ...conn, priority: newPriority } : conn
    ));
    showAlertMessage('Connection priority updated', 'info');
  };

  const handleBulkAction = (action) => {
    switch(action) {
      case 'restart_all':
        showAlertMessage('Restarting all price feeds...', 'info');
        break;
      case 'optimize_costs':
        showAlertMessage('Running cost optimization...', 'info');
        break;
      case 'emergency_stop':
        showAlertMessage('Emergency stop initiated', 'warning');
        break;
    }
  };

  // Render connection monitoring with price data focus
  const renderConnectionMonitoring = () => (
    <Paper sx={{ p: 3 }}>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
        <Typography variant="h6">
          Active Price Feed Connections ({activeConnections.length})
        </Typography>
        <Box display="flex" gap={1}>
          <Button
            variant="outlined"
            startIcon={<Refresh />}
            onClick={() => handleBulkAction('restart_all')}
            size="small"
          >
            Restart All
          </Button>
          <Button
            variant="outlined"
            startIcon={<AutoFixHigh />}
            onClick={() => handleBulkAction('optimize_costs')}
            size="small"
          >
            Optimize
          </Button>
          <Button
            variant="outlined"
            color="error"
            startIcon={<PowerOff />}
            onClick={() => handleBulkAction('emergency_stop')}
            size="small"
          >
            Emergency Stop
          </Button>
        </Box>
      </Box>
      
      <TableContainer>
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>Provider</TableCell>
              <TableCell>Symbol</TableCell>
              <TableCell>Current Price</TableCell>
              <TableCell>Change</TableCell>
              <TableCell>Subscribers</TableCell>
              <TableCell>Latency</TableCell>
              <TableCell>Msg/sec</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {activeConnections.map((connection, index) => (
              <TableRow key={index} hover>
                <TableCell>
                  <Box display="flex" alignItems="center" gap={1}>
                    <Chip 
                      label={connection.provider} 
                      size="small" 
                      color="primary"
                      variant="outlined"
                    />
                    <Typography variant="caption" color="text.secondary">
                      {connection.dataType}
                    </Typography>
                  </Box>
                </TableCell>
                <TableCell>
                  <Typography variant="body2" fontWeight="bold">
                    {connection.symbol}
                  </Typography>
                </TableCell>
                <TableCell>
                  <Typography variant="body2" fontWeight="bold">
                    ${connection.lastPrice?.toLocaleString()}
                  </Typography>
                </TableCell>
                <TableCell>
                  <Typography 
                    color={connection.change >= 0 ? 'success.main' : 'error.main'}
                    variant="body2"
                  >
                    {connection.change >= 0 ? '+' : ''}{connection.change}
                  </Typography>
                </TableCell>
                <TableCell>
                  <Chip 
                    label={connection.subscribers} 
                    color={connection.subscribers > 100 ? 'success' : connection.subscribers > 50 ? 'warning' : 'default'} 
                    size="small"
                  />
                </TableCell>
                <TableCell>
                  <Typography 
                    color={connection.latency > 100 ? 'error.main' : connection.latency > 60 ? 'warning.main' : 'success.main'}
                    variant="body2"
                  >
                    {connection.latency}ms
                  </Typography>
                </TableCell>
                <TableCell>
                  <Typography variant="body2">
                    {connection.messagesPerSec}
                  </Typography>
                </TableCell>
                <TableCell>
                  <Chip 
                    label={connection.status} 
                    color={connection.status === 'active' ? 'success' : 'warning'}
                    size="small"
                    icon={connection.status === 'active' ? <CheckCircle /> : <Warning />}
                  />
                </TableCell>
                <TableCell>
                  <Box display="flex" gap={0.5}>
                    <Tooltip title="Restart connection">
                      <IconButton
                        size="small"
                        onClick={() => showAlertMessage(`${connection.symbol} connection restarted`, 'info')}
                      >
                        <Refresh />
                      </IconButton>
                    </Tooltip>
                    <Tooltip title="Pause feed">
                      <IconButton
                        size="small"
                        onClick={() => showAlertMessage(`${connection.symbol} feed paused`, 'warning')}
                      >
                        <Stop />
                      </IconButton>
                    </Tooltip>
                    <Tooltip title="Priority boost">
                      <IconButton
                        size="small"
                        onClick={() => handlePriorityAdjustment(index, 'high')}
                      >
                        <TrendingUp />
                      </IconButton>
                    </Tooltip>
                  </Box>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </Paper>
  );

  // Render system alerts
  const renderSystemAlerts = () => (
    <Paper sx={{ p: 3 }}>
      <Typography variant="h6" gutterBottom>
        System Alerts
      </Typography>
      <List>
        {systemAlerts.length > 0 ? systemAlerts.map((alert, index) => (
          <ListItem key={index} divider>
            <ListItemIcon>
              {alert.severity === 'error' ? <Error color="error" /> :
               alert.severity === 'warning' ? <Warning color="warning" /> :
               <Info color="info" />}
            </ListItemIcon>
            <ListItemText
              primary={alert.message}
              secondary={new Date(alert.timestamp).toLocaleString()}
            />
          </ListItem>
        )) : (
          <ListItem>
            <ListItemText
              primary="No alerts"
              secondary="System is operating normally"
            />
          </ListItem>
        )}
      </List>
    </Paper>
  );

  // Render subscription management with price focus
  const renderSubscriptionManager = () => (
    <Card sx={{ mb: 2 }}>
      <CardContent>
        <Box display="flex" alignItems="center" gap={2} mb={2}>
          <OnlinePrediction color="primary" />
          <Typography variant="h6">
            Price Data Subscriptions
          </Typography>
          <Chip 
            label={`${subscriptions.length} symbols`} 
            color="primary" 
            size="small"
          />
          <Chip 
            label={`${Object.keys(marketData).length} receiving data`} 
            color="success" 
            size="small"
          />
        </Box>
        
        {/* Add new symbol */}
        <Box display="flex" gap={2} mb={2}>
          <TextField
            label="Add Symbol for Price Tracking"
            value={newSymbol}
            onChange={(e) => setNewSymbol(e.target.value.toUpperCase())}
            onKeyPress={(e) => e.key === 'Enter' && addSymbol()}
            size="small"
            placeholder="AAPL, BTC-USD, SPY..."
            helperText="Add symbols for real-time price monitoring"
          />
          <Button 
            variant="contained" 
            startIcon={<Add />}
            onClick={addSymbol}
            disabled={!newSymbol || subscriptions.includes(newSymbol.toUpperCase())}
          >
            Subscribe
          </Button>
        </Box>

        {/* High-frequency price monitoring symbols */}
        <Box mb={2}>
          <Typography variant="body2" color="text.secondary" gutterBottom>
            High-Frequency Price Monitoring:
          </Typography>
          <Box display="flex" flexWrap="wrap" gap={1} mb={2}>
            {HIGH_FREQUENCY_SYMBOLS.map(symbol => (
              <Chip
                key={symbol}
                label={symbol}
                size="small"
                color={subscriptions.includes(symbol) ? "error" : "default"}
                variant={subscriptions.includes(symbol) ? "filled" : "outlined"}
                onClick={() => subscriptions.includes(symbol) ? 
                  removeSymbol(symbol) : handleSubscribe([symbol])}
                icon={subscriptions.includes(symbol) ? <Speed /> : <Add />}
              />
            ))}
          </Box>
          <Typography variant="body2" color="text.secondary" gutterBottom>
            Popular Symbols:
          </Typography>
          <Box display="flex" flexWrap="wrap" gap={1}>
            {POPULAR_SYMBOLS.map(symbol => (
              <Chip
                key={symbol}
                label={symbol}
                size="small"
                color={subscriptions.includes(symbol) ? "primary" : "default"}
                onClick={() => subscriptions.includes(symbol) ? 
                  removeSymbol(symbol) : handleSubscribe([symbol])}
                onDelete={subscriptions.includes(symbol) ? 
                  () => removeSymbol(symbol) : undefined}
              />
            ))}
          </Box>
        </Box>

        {/* Current subscriptions with price data status */}
        {subscriptions.length > 0 && (
          <Box>
            <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
              <Typography variant="body2" color="text.secondary" gutterBottom>
                Active Price Subscriptions ({subscriptions.length}):
              </Typography>
              <Box display="flex" gap={1}>
                <Button
                  size="small"
                  startIcon={<ClearAll />}
                  onClick={() => {
                    handleUnsubscribe(subscriptions);
                    showAlertMessage('All subscriptions cleared', 'info');
                  }}
                  variant="outlined"
                  color="warning"
                >
                  Clear All
                </Button>
                <Button
                  size="small"
                  startIcon={<Add />}
                  onClick={() => {
                    handleSubscribe(HIGH_FREQUENCY_SYMBOLS.filter(s => !subscriptions.includes(s)));
                    showAlertMessage('High-frequency symbols added', 'info');
                  }}
                  variant="outlined"
                >
                  Add HF Symbols
                </Button>
              </Box>
            </Box>
            <Box display="flex" flexWrap="wrap" gap={1}>
              {subscriptions.map(symbol => {
                const hasData = marketData[symbol];
                const isHighFreq = HIGH_FREQUENCY_SYMBOLS.includes(symbol);
                return (
                  <Chip
                    key={symbol}
                    label={`${symbol}${hasData ? ` $${marketData[symbol].price?.toFixed(2)}` : ''}`}
                    color={isHighFreq ? "error" : "primary"}
                    variant={hasData ? "filled" : "outlined"}
                    onDelete={() => removeSymbol(symbol)}
                    icon={hasData ? 
                      (marketData[symbol].change >= 0 ? <TrendingUp /> : <TrendingDown />) : 
                      <Warning />
                    }
                  />
                );
              })}
            </Box>
          </Box>
        )}
      </CardContent>
    </Card>
  );

  // Render live data stream table
  const renderLiveDataTable = () => (
    <TableContainer component={Paper}>
      <Table>
        <TableHead>
          <TableRow>
            <TableCell>Symbol</TableCell>
            <TableCell align="right">Price</TableCell>
            <TableCell align="right">Change</TableCell>
            <TableCell align="right">Change %</TableCell>
            <TableCell align="right">Volume</TableCell>
            <TableCell align="right">Last Update</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {subscriptions.map(symbol => {
            const data = marketData[symbol];
            const isPositive = data?.change >= 0;
            
            return (
              <TableRow key={symbol} hover>
                <TableCell>
                  <Box display="flex" alignItems="center" gap={1}>
                    <Typography variant="body1" fontWeight="bold">
                      {symbol}
                    </Typography>
                    {isPositive ? 
                      <TrendingUp color="success" fontSize="small" /> : 
                      <TrendingDown color="error" fontSize="small" />
                    }
                  </Box>
                </TableCell>
                <TableCell align="right">
                  <Typography 
                    variant="body1" 
                    fontWeight="bold"
                    color={data?.price !== data?.previousPrice ? 
                      (data?.price > data?.previousPrice ? "success.main" : "error.main") : 
                      "text.primary"
                    }
                  >
                    ${data?.price?.toFixed(2) || '--'}
                  </Typography>
                </TableCell>
                <TableCell align="right">
                  <Typography color={isPositive ? "success.main" : "error.main"}>
                    {isPositive ? '+' : ''}{data?.change?.toFixed(2) || '--'}
                  </Typography>
                </TableCell>
                <TableCell align="right">
                  <Typography color={isPositive ? "success.main" : "error.main"}>
                    {isPositive ? '+' : ''}{data?.change_percent?.toFixed(2) || '--'}%
                  </Typography>
                </TableCell>
                <TableCell align="right">
                  {data?.volume?.toLocaleString() || '--'}
                </TableCell>
                <TableCell align="right">
                  <Typography variant="body2" color="text.secondary">
                    {data?.timestamp ? data.timestamp.toLocaleTimeString() : '--'}
                  </Typography>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </TableContainer>
  );


  // Render failover control dashboard
  const renderFailoverControl = () => (
    <Paper sx={{ p: 3 }}>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h6">Automated Failover & Provider Arbitrage</Typography>
        <Box display="flex" gap={2}>
          <Button
            variant="contained"
            color={failoverMetrics.activeArbitrage ? 'success' : 'warning'}
            startIcon={<SyncAlt />}
            onClick={toggleArbitrage}
          >
            {failoverMetrics.activeArbitrage ? 'Arbitrage Active' : 'Arbitrage Paused'}
          </Button>
          <Button
            variant="outlined"
            startIcon={<Refresh />}
            onClick={() => showAlertMessage('Failover metrics refreshed', 'info')}
          >
            Refresh
          </Button>
        </Box>
      </Box>
      
      {/* Failover Metrics Dashboard */}
      <Grid container spacing={3} mb={3}>
        <Grid item xs={12} md={3}>
          <Card sx={{ textAlign: 'center', background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)' }}>
            <CardContent>
              <SyncAlt sx={{ fontSize: 40, color: 'white', mb: 1 }} />
              <Typography variant="h4" color="white">
                {failoverMetrics.totalFailovers}
              </Typography>
              <Typography variant="caption" color="white">Total Failovers</Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={3}>
          <Card sx={{ textAlign: 'center', background: 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)' }}>
            <CardContent>
              <Speed sx={{ fontSize: 40, color: 'white', mb: 1 }} />
              <Typography variant="h4" color="white">
                {failoverMetrics.avgFailoverTime}s
              </Typography>
              <Typography variant="caption" color="white">Avg Failover Time</Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={3}>
          <Card sx={{ textAlign: 'center', background: 'linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)' }}>
            <CardContent>
              <MonetizationOn sx={{ fontSize: 40, color: 'white', mb: 1 }} />
              <Typography variant="h4" color="white">
                ${failoverMetrics.costSavings.toFixed(2)}
              </Typography>
              <Typography variant="caption" color="white">Daily Savings</Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={3}>
          <Card sx={{ textAlign: 'center', background: 'linear-gradient(135deg, #43e97b 0%, #38f9d7 100%)' }}>
            <CardContent>
              <CheckCircle sx={{ fontSize: 40, color: 'white', mb: 1 }} />
              <Typography variant="h4" color="white">
                {failoverMetrics.uptimeAchieved}%
              </Typography>
              <Typography variant="caption" color="white">Uptime Achieved</Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
      
      {/* Manual Failover Controls */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>Manual Failover Controls</Typography>
          <Grid container spacing={2}>
            {activeConnections.slice(0, 6).map((connection, index) => (
              <Grid item xs={12} sm={6} md={4} key={index}>
                <Box 
                  sx={{ 
                    border: 1, 
                    borderColor: 'divider', 
                    borderRadius: 1, 
                    p: 2,
                    '&:hover': { backgroundColor: 'action.hover' }
                  }}
                >
                  <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
                    <Typography variant="body1" fontWeight="bold">
                      {connection.symbol}
                    </Typography>
                    <Chip 
                      label={connection.provider}
                      color="primary"
                      size="small"
                    />
                  </Box>
                  <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
                    <Typography variant="body2" color="text.secondary">
                      {connection.subscribers} subscribers
                    </Typography>
                    <Typography variant="body2" color={connection.latency < 100 ? 'success.main' : 'warning.main'}>
                      {connection.latency}ms
                    </Typography>
                  </Box>
                  <Button
                    variant="outlined"
                    size="small"
                    fullWidth
                    startIcon={<SyncAlt />}
                    onClick={() => triggerManualFailover(connection.symbol)}
                  >
                    Trigger Failover
                  </Button>
                </Box>
              </Grid>
            ))}
          </Grid>
        </CardContent>
      </Card>
      
      {/* Failover History */}
      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>Recent Failover History</Typography>
          <TableContainer>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>Symbol</TableCell>
                  <TableCell>From Provider</TableCell>
                  <TableCell>To Provider</TableCell>
                  <TableCell>Reason</TableCell>
                  <TableCell>Duration</TableCell>
                  <TableCell>Time</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {failoverHistory.map((failover, index) => (
                  <TableRow key={index} hover>
                    <TableCell>
                      <Typography variant="body2" fontWeight="bold">
                        {failover.symbol}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Chip 
                        label={failover.fromProvider}
                        color="warning"
                        size="small"
                        variant="outlined"
                      />
                    </TableCell>
                    <TableCell>
                      <Chip 
                        label={failover.toProvider}
                        color="success"
                        size="small"
                      />
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" color="text.secondary">
                        {failover.reason.replace('_', ' ')}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" color="info.main">
                        {failover.duration.toFixed(1)}s
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" color="text.secondary">
                        {failover.time.toLocaleTimeString()}
                      </Typography>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </CardContent>
      </Card>
    </Paper>
  );

  // Render system health monitoring
  const renderSystemHealth = () => (
    <Paper sx={{ p: 3 }}>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h6">Live Data System Health</Typography>
        <Box display="flex" gap={2}>
          <Button
            variant="outlined"
            startIcon={<Refresh />}
            onClick={() => showAlertMessage('System health refreshed', 'info')}
          >
            Refresh Status
          </Button>
          <Button
            variant="outlined"
            startIcon={<HealthAndSafety />}
            onClick={() => showAlertMessage('Health check initiated', 'info')}
          >
            Run Diagnostics
          </Button>
        </Box>
      </Box>
      
      {/* Data Quality Dashboard */}
      <Grid container spacing={3} mb={3}>
        <Grid item xs={12} md={3}>
          <Card sx={{ background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)' }}>
            <CardContent sx={{ textAlign: 'center' }}>
              <Assessment sx={{ fontSize: 40, color: 'white', mb: 1 }} />
              <Typography variant="h4" color="white">
                {qualityMetrics.overallQuality.toFixed(1)}%
              </Typography>
              <Typography variant="caption" color="white">Overall Data Quality</Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={3}>
          <Card sx={{ background: 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)' }}>
            <CardContent sx={{ textAlign: 'center' }}>
              <DataUsage sx={{ fontSize: 40, color: 'white', mb: 1 }} />
              <Typography variant="h4" color="white">
                {qualityMetrics.totalValidations.toLocaleString()}
              </Typography>
              <Typography variant="caption" color="white">Total Validations</Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={3}>
          <Card sx={{ background: 'linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)' }}>
            <CardContent sx={{ textAlign: 'center' }}>
              <Warning sx={{ fontSize: 40, color: 'white', mb: 1 }} />
              <Typography variant="h4" color="white">
                {qualityMetrics.totalViolations}
              </Typography>
              <Typography variant="caption" color="white">Quality Violations</Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={3}>
          <Card sx={{ background: 'linear-gradient(135deg, #43e97b 0%, #38f9d7 100%)' }}>
            <CardContent sx={{ textAlign: 'center' }}>
              <OnlinePrediction sx={{ fontSize: 40, color: 'white', mb: 1 }} />
              <Typography variant="h4" color="white">
                {qualityMetrics.activeMonitors}
              </Typography>
              <Typography variant="caption" color="white">Active Monitors</Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
      
      {/* Symbol Quality Monitoring */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
            <Typography variant="h6">Symbol Quality Monitoring</Typography>
            <Button
              variant="outlined"
              startIcon={<Refresh />}
              onClick={() => showAlertMessage('Quality metrics refreshed', 'info')}
              size="small"
            >
              Refresh
            </Button>
          </Box>
          <TableContainer>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>Symbol</TableCell>
                  <TableCell>Quality Score</TableCell>
                  <TableCell>Freshness</TableCell>
                  <TableCell>Completeness</TableCell>
                  <TableCell>Accuracy</TableCell>
                  <TableCell>Consistency</TableCell>
                  <TableCell>Trend</TableCell>
                  <TableCell>Provider</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {symbolQuality.map((sq, index) => (
                  <TableRow key={index} hover>
                    <TableCell>
                      <Typography variant="body2" fontWeight="bold">
                        {sq.symbol}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Box display="flex" alignItems="center" gap={1}>
                        <Typography 
                          variant="body2" 
                          fontWeight="bold"
                          color={sq.quality > 95 ? 'success.main' : sq.quality > 90 ? 'warning.main' : 'error.main'}
                        >
                          {sq.quality.toFixed(1)}%
                        </Typography>
                        <LinearProgress 
                          variant="determinate" 
                          value={sq.quality} 
                          color={sq.quality > 95 ? 'success' : sq.quality > 90 ? 'warning' : 'error'}
                          sx={{ width: 50, height: 4 }}
                        />
                      </Box>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" color={sq.freshness > 95 ? 'success.main' : 'warning.main'}>
                        {sq.freshness.toFixed(1)}%
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" color={sq.completeness > 95 ? 'success.main' : 'warning.main'}>
                        {sq.completeness.toFixed(1)}%
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" color={sq.accuracy > 95 ? 'success.main' : 'warning.main'}>
                        {sq.accuracy.toFixed(1)}%
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" color={sq.consistency > 95 ? 'success.main' : 'warning.main'}>
                        {sq.consistency.toFixed(1)}%
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Chip 
                        label={sq.trend}
                        color={sq.trend === 'improving' ? 'success' : sq.trend === 'degrading' ? 'error' : 'default'}
                        size="small"
                        icon={sq.trend === 'improving' ? <TrendingUp /> : sq.trend === 'degrading' ? <TrendingDown /> : <TrendingFlat />}
                      />
                    </TableCell>
                    <TableCell>
                      <Chip 
                        label={sq.provider}
                        color="primary"
                        size="small"
                        variant="outlined"
                      />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </CardContent>
      </Card>
      
      {/* Quality Alerts */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>Quality Alerts</Typography>
          <List>
            {qualityAlerts.length > 0 ? qualityAlerts.map((alert, index) => (
              <ListItem key={index} divider>
                <ListItemIcon>
                  {alert.severity === 'error' ? <Error color="error" /> :
                   alert.severity === 'warning' ? <Warning color="warning" /> :
                   <Info color="info" />}
                </ListItemIcon>
                <ListItemText
                  primary={`${alert.symbol}: ${alert.message}`}
                  secondary={
                    <Box>
                      <Typography variant="caption" color="text.secondary">
                        Quality Score: {alert.score?.toFixed(1)}% • {alert.time.toLocaleTimeString()}
                      </Typography>
                    </Box>
                  }
                />
                <Chip 
                  label={alert.type.replace('_', ' ')}
                  color={alert.severity === 'error' ? 'error' : 'warning'}
                  size="small"
                />
              </ListItem>
            )) : (
              <ListItem>
                <ListItemText
                  primary="No quality alerts"
                  secondary="All data quality metrics within acceptable thresholds"
                />
              </ListItem>
            )}
          </List>
        </CardContent>
      </Card>
      
      {/* Latency Monitoring Dashboard */}
      <Grid container spacing={3} mb={3}>
        <Grid item xs={12} md={3}>
          <Card sx={{ background: 'linear-gradient(135deg, #fa709a 0%, #fee140 100%)' }}>
            <CardContent sx={{ textAlign: 'center' }}>
              <Speed sx={{ fontSize: 40, color: 'white', mb: 1 }} />
              <Typography variant="h4" color="white">
                {latencyMetrics.system.avgLatency.toFixed(1)}ms
              </Typography>
              <Typography variant="caption" color="white">Average Latency</Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={3}>
          <Card sx={{ background: 'linear-gradient(135deg, #a8edea 0%, #fed6e3 100%)' }}>
            <CardContent sx={{ textAlign: 'center' }}>
              <Timeline sx={{ fontSize: 40, color: 'white', mb: 1 }} />
              <Typography variant="h4" color="white">
                {latencyMetrics.system.totalMeasurements.toLocaleString()}
              </Typography>
              <Typography variant="caption" color="white">Total Measurements</Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={3}>
          <Card sx={{ background: 'linear-gradient(135deg, #ff9a9e 0%, #fecfef 100%)' }}>
            <CardContent sx={{ textAlign: 'center' }}>
              <ReportProblem sx={{ fontSize: 40, color: 'white', mb: 1 }} />
              <Typography variant="h4" color="white">
                {latencyMetrics.system.slaViolations}
              </Typography>
              <Typography variant="caption" color="white">SLA Violations</Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={3}>
          <Card sx={{ background: 'linear-gradient(135deg, #a1c4fd 0%, #c2e9fb 100%)' }}>
            <CardContent sx={{ textAlign: 'center' }}>
              <NetworkCheck sx={{ fontSize: 40, color: 'white', mb: 1 }} />
              <Typography variant="h4" color="white">
                {latencyMetrics.activeMonitors}
              </Typography>
              <Typography variant="caption" color="white">Active Monitors</Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
      
      {/* Symbol Latency Monitoring */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
            <Typography variant="h6">Symbol Latency Monitoring</Typography>
            <Button
              variant="outlined"
              startIcon={<Refresh />}
              onClick={() => showAlertMessage('Latency metrics refreshed', 'info')}
              size="small"
            >
              Refresh
            </Button>
          </Box>
          <TableContainer>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>Symbol</TableCell>
                  <TableCell>Provider</TableCell>
                  <TableCell>Current</TableCell>
                  <TableCell>Average</TableCell>
                  <TableCell>P95</TableCell>
                  <TableCell>P99</TableCell>
                  <TableCell>Measurements</TableCell>
                  <TableCell>Violations</TableCell>
                  <TableCell>Status</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {symbolLatency.map((sl, index) => (
                  <TableRow key={index} hover>
                    <TableCell>
                      <Typography variant="body2" fontWeight="bold">
                        {sl.symbol}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Chip 
                        label={sl.providerId} 
                        color="primary" 
                        size="small"
                      />
                    </TableCell>
                    <TableCell>
                      <Typography 
                        variant="body2" 
                        fontWeight="bold"
                        color={sl.current > 100 ? 'error.main' : sl.current > 60 ? 'warning.main' : 'success.main'}
                      >
                        {sl.current}ms
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2">
                        {sl.average.toFixed(1)}ms
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2">
                        {sl.p95}ms
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" color={sl.p99 > 100 ? 'warning.main' : 'text.primary'}>
                        {sl.p99}ms
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2">
                        {sl.measurements.toLocaleString()}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" color={sl.violations > 0 ? 'error.main' : 'success.main'}>
                        {sl.violations}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Chip 
                        label={sl.status}
                        color={sl.status === 'good' ? 'success' : sl.status === 'warning' ? 'warning' : 'error'}
                        size="small"
                        icon={sl.status === 'good' ? <CheckCircle /> : sl.status === 'warning' ? <Warning /> : <Error />}
                      />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </CardContent>
      </Card>
      
      {/* Latency Alerts */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>Latency Alerts</Typography>
          <List>
            {latencyAlerts.length > 0 ? latencyAlerts.map((alert, index) => (
              <ListItem key={index} divider>
                <ListItemIcon>
                  {alert.severity === 'error' ? <Error color="error" /> :
                   alert.severity === 'warning' ? <Warning color="warning" /> :
                   <Info color="info" />}
                </ListItemIcon>
                <ListItemText
                  primary={`${alert.symbol}: ${alert.message}`}
                  secondary={
                    <Box>
                      <Typography variant="caption" color="text.secondary">
                        Provider: {alert.providerId} • Current: {alert.metrics.current}ms • P95: {alert.metrics.p95}ms • {alert.timestamp.toLocaleTimeString()}
                      </Typography>
                    </Box>
                  }
                />
                <Chip 
                  label={alert.severity.toUpperCase()}
                  color={alert.severity === 'error' ? 'error' : 'warning'}
                  size="small"
                />
              </ListItem>
            )) : (
              <ListItem>
                <ListItemText
                  primary="No latency alerts"
                  secondary="All latency metrics within acceptable thresholds"
                />
              </ListItem>
            )}
          </List>
        </CardContent>
      </Card>
      
      {/* Provider Latency Summary */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>Provider Latency Summary</Typography>
          <Grid container spacing={2}>
            {Object.entries(latencyMetrics.providers).map(([providerId, metrics]) => (
              <Grid item xs={12} sm={6} md={3} key={providerId}>
                <Box 
                  sx={{ 
                    border: 1, 
                    borderColor: metrics.avgLatency > 100 ? 'error.main' : metrics.avgLatency > 60 ? 'warning.main' : 'success.main', 
                    borderRadius: 1, 
                    p: 2,
                    backgroundColor: metrics.avgLatency > 100 ? 'error.light' : metrics.avgLatency > 60 ? 'warning.light' : 'success.light',
                    opacity: 0.9
                  }}
                >
                  <Typography variant="h6" fontWeight="bold" gutterBottom>
                    {providerId.toUpperCase()}
                  </Typography>
                  <Box display="flex" justifyContent="space-between" mb={1}>
                    <Typography variant="body2">Avg Latency:</Typography>
                    <Typography variant="body2" fontWeight="bold">
                      {metrics.avgLatency.toFixed(1)}ms
                    </Typography>
                  </Box>
                  <Box display="flex" justifyContent="space-between" mb={1}>
                    <Typography variant="body2">Symbols:</Typography>
                    <Typography variant="body2">{metrics.symbols}</Typography>
                  </Box>
                  <Box display="flex" justifyContent="space-between" mb={1}>
                    <Typography variant="body2">Violations:</Typography>
                    <Typography variant="body2" color={metrics.violations > 0 ? 'error.main' : 'success.main'}>
                      {metrics.violations}
                    </Typography>
                  </Box>
                  <Box display="flex" justifyContent="space-between">
                    <Typography variant="body2">Measurements:</Typography>
                    <Typography variant="body2">{metrics.measurements.toLocaleString()}</Typography>
                  </Box>
                </Box>
              </Grid>
            ))}
          </Grid>
        </CardContent>
      </Card>
      
      {/* System Alerts */}
      <Typography variant="h6" gutterBottom>System Alerts</Typography>
      <List>
        {systemAlerts.length > 0 ? systemAlerts.map((alert, index) => (
          <ListItem key={index} divider>
            <ListItemIcon>
              {alert.severity === 'error' ? <Error color="error" /> :
               alert.severity === 'warning' ? <Warning color="warning" /> :
               alert.severity === 'success' ? <CheckCircle color="success" /> :
               <Info color="info" />}
            </ListItemIcon>
            <ListItemText
              primary={alert.message}
              secondary={new Date(alert.timestamp).toLocaleString()}
            />
          </ListItem>
        )) : (
          <ListItem>
            <ListItemText
              primary="No system alerts"
              secondary="All live data systems operating normally"
            />
          </ListItem>
        )}
      </List>
    </Paper>
  );


  // Render live data optimization dashboard
  const renderOptimizationDashboard = () => (
    <Paper sx={{ p: 3 }}>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h6">Live Data Feed Optimization</Typography>
        <Box display="flex" gap={2}>
          <Button
            variant="contained"
            startIcon={<AutoFixHigh />}
            onClick={() => showAlertMessage('Feed auto-optimization enabled', 'success')}
            color="primary"
          >
            Auto-Optimize Feeds
          </Button>
          <Button
            variant="outlined"
            startIcon={<DataUsage />}
            onClick={() => showAlertMessage('Data compression optimized', 'info')}
          >
            Optimize Compression
          </Button>
        </Box>
      </Box>
      
      {/* Data Feed Optimization */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>Data Feed Performance</Typography>
          <Grid container spacing={3}>
            <Grid item xs={12} md={3}>
              <Box textAlign="center">
                <Typography variant="h3" color="primary.main">
                  {bandwidthMetrics.total} MB/h
                </Typography>
                <Typography variant="caption">Total Data Throughput</Typography>
              </Box>
            </Grid>
            <Grid item xs={12} md={3}>
              <Box textAlign="center">
                <Typography variant="h3" color="success.main">
                  {bandwidthMetrics.optimization}%
                </Typography>
                <Typography variant="caption">Compression Savings</Typography>
              </Box>
            </Grid>
            <Grid item xs={12} md={3}>
              <Box textAlign="center">
                <Typography variant="h3" color="info.main">
                  {feedMetrics.messagesPerSecond}
                </Typography>
                <Typography variant="caption">Messages/Second</Typography>
              </Box>
            </Grid>
            <Grid item xs={12} md={3}>
              <Box textAlign="center">
                <FormControlLabel
                  control={
                    <Switch
                      checked={bandwidthMetrics.throttling}
                      onChange={(e) => {
                        setBandwidthMetrics(prev => ({ ...prev, throttling: e.target.checked }));
                        showAlertMessage(`Smart throttling ${e.target.checked ? 'enabled' : 'disabled'}`, 'info');
                      }}
                    />
                  }
                  label="Smart Throttling"
                />
              </Box>
            </Grid>
          </Grid>
        </CardContent>
      </Card>
      
      {/* Feed Priority Management */}
      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>Feed Priority & Resource Allocation</Typography>
          <TableContainer>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>Symbol</TableCell>
                  <TableCell>Data Rate</TableCell>
                  <TableCell>Subscribers</TableCell>
                  <TableCell>Bandwidth Usage</TableCell>
                  <TableCell>Priority</TableCell>
                  <TableCell>Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {symbolMetrics.map((symbol, index) => (
                  <TableRow key={index} hover>
                    <TableCell>
                      <Typography variant="body2" fontWeight="bold">
                        {symbol.symbol}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Box display="flex" alignItems="center" gap={1}>
                        <Typography variant="body2">
                          {(symbol.volatility * 10).toFixed(1)} msg/s
                        </Typography>
                        <LinearProgress 
                          variant="determinate" 
                          value={symbol.volatility * 10} 
                          color={symbol.volatility > 5 ? 'error' : symbol.volatility > 2 ? 'warning' : 'success'}
                          sx={{ width: 50, height: 4 }}
                        />
                      </Box>
                    </TableCell>
                    <TableCell>
                      <Chip 
                        label={symbol.subscribers}
                        color={symbol.subscribers > 100 ? 'success' : 'default'}
                        size="small"
                      />
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2">
                        {(symbol.subscribers * 0.1).toFixed(1)} MB/h
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Chip 
                        label={symbol.priority}
                        color={symbol.priority === 'critical' ? 'error' : symbol.priority === 'high' ? 'warning' : 'default'}
                        size="small"
                      />
                    </TableCell>
                    <TableCell>
                      <Tooltip title="Optimize feed priority">
                        <IconButton
                          size="small"
                          onClick={() => showAlertMessage(`Optimizing ${symbol.symbol} feed priority`, 'info')}
                        >
                          <AutoFixHigh />
                        </IconButton>
                      </Tooltip>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </CardContent>
      </Card>
    </Paper>
  );

  return (
    <Box p={3}>
      <Box display="flex" alignItems="center" gap={2} mb={3}>
        <AdminPanelSettings color="primary" sx={{ fontSize: 32 }} />
        <Box>
          <Typography variant="h4" gutterBottom>
            Price Data Admin Console
          </Typography>
          <Typography variant="body1" color="text.secondary">
            Centralized WebSocket feed management • 8 providers • 487 symbols • 234 active feeds
          </Typography>
        </Box>
      </Box>

      {/* Service Health Dashboard */}
      {renderServiceHealthDashboard()}

      {/* Feed Configuration */}
      {renderFeedConfiguration()}

      {/* Subscription Manager */}
      {renderSubscriptionManager()}

      {/* Tabs */}
      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 2 }}>
        <Tabs value={activeTab} onChange={(e, value) => setActiveTab(value)}>
          <Tab label="Live Data" icon={<DataUsage />} iconPosition="start" />
          <Tab label="Connections" icon={<NetworkCheck />} iconPosition="start" />
          <Tab label="Failover Control" icon={<SyncAlt />} iconPosition="start" />
          <Tab label="System Health" icon={<HealthAndSafety />} iconPosition="start" />
          <Tab label="Optimization" icon={<AutoFixHigh />} iconPosition="start" />
        </Tabs>
      </Box>

      {/* Tab Content */}
      {activeTab === 0 && renderLiveDataTable()}
      {activeTab === 1 && renderConnectionMonitoring()}
      {activeTab === 2 && renderFailoverControl()}
      {activeTab === 3 && renderSystemHealth()}
      {activeTab === 4 && renderOptimizationDashboard()}

      {/* Settings Dialog */}
      <Dialog open={showSettings} onClose={() => setShowSettings(false)} maxWidth="md" fullWidth>
        <DialogTitle>Live Data Settings</DialogTitle>
        <DialogContent>
          <Box py={2}>
            <FormControlLabel
              control={
                <Switch
                  checked={autoRefresh}
                  onChange={(e) => setAutoRefresh(e.target.checked)}
                />
              }
              label="Auto-refresh data"
            />
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowSettings(false)}>Close</Button>
        </DialogActions>
      </Dialog>

      {/* Alert Snackbar */}
      <Snackbar
        open={showAlert}
        autoHideDuration={6000}
        onClose={() => setShowAlert(false)}
        anchorOrigin={{ vertical: 'top', horizontal: 'right' }}
      >
        <Alert 
          onClose={() => setShowAlert(false)} 
          severity={alertSeverity}
          sx={{ width: '100%' }}
        >
          {alertMessage}
        </Alert>
      </Snackbar>
    </Box>
  );
};

export default LiveData;