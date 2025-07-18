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
  ButtonGroup
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
  DataUsage,
  Storage,
  CloudSync,
  Group,
  AttachMoney
} from '@mui/icons-material';
// Chart.js replaced with recharts for better React integration
import adminLiveDataService from '../services/adminLiveDataService';
import { useAuth } from '../contexts/AuthContext';

// Chart.js registration removed - using recharts instead

/**
 * Admin Live Data Management
 * 
 * Centralized admin interface for managing live data feeds
 * - Admin runs one set of connections to Alpaca
 * - Serves data to all users through centralized feed
 * - Manages costs and data quality centrally
 * - Supports stocks, crypto, options from Alpaca
 */

const ASSET_TYPES = [
  { value: 'stocks', label: 'Stocks', icon: '📈' },
  { value: 'crypto', label: 'Crypto', icon: '₿' },
  { value: 'options', label: 'Options', icon: '⚡' }
];

const DATA_TYPES = [
  { value: 'trades', label: 'Trades', description: 'Real-time trade executions' },
  { value: 'quotes', label: 'Quotes', description: 'Bid/ask spreads' },
  { value: 'bars', label: 'Bars', description: 'OHLCV minute bars' },
  { value: 'dailyBars', label: 'Daily Bars', description: 'Daily OHLCV data' },
  { value: 'status', label: 'Status', description: 'Market status updates' }
];

const POPULAR_SYMBOLS = {
  stocks: ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'NVDA', 'META', 'NFLX', 'SPY', 'QQQ'],
  crypto: ['BTC/USD', 'ETH/USD', 'LTC/USD', 'BCH/USD', 'DOGE/USD', 'SHIB/USD', 'AVAX/USD'],
  options: ['AAPL240119C00150000', 'SPY240119C00450000', 'TSLA240119C00200000']
};

const AdminLiveData = () => {
  const { user } = useAuth();
  
  // Admin state
  const [activeFeeds, setActiveFeeds] = useState([]);
  const [subscribers, setSubscribers] = useState([]);
  const [systemMetrics, setSystemMetrics] = useState({
    totalConnections: 0,
    activeSymbols: 0,
    messagesPerSecond: 0,
    totalUsers: 0,
    costSavings: 0,
    dataLatency: 0,
    uptime: 0
  });
  
  // Feed management state
  const [selectedAssetType, setSelectedAssetType] = useState('stocks');
  const [selectedDataTypes, setSelectedDataTypes] = useState(['trades', 'quotes']);
  const [symbolInput, setSymbolInput] = useState('');
  const [feedStatus, setFeedStatus] = useState('stopped'); // stopped, starting, running, stopping
  
  // Real-time data state
  const [liveData, setLiveData] = useState({});
  const [connectionStatus, setConnectionStatus] = useState('disconnected');
  const [lastUpdate, setLastUpdate] = useState(null);
  
  // UI state
  const [selectedTab, setSelectedTab] = useState(0);
  const [showAddFeedDialog, setShowAddFeedDialog] = useState(false);
  
  // Initialize admin service
  useEffect(() => {
    loadSystemMetrics();
    loadActiveFeeds();
    loadSubscribers();
    
    // Set up real-time updates
    const metricsInterval = setInterval(loadSystemMetrics, 5000);
    const feedsInterval = setInterval(loadActiveFeeds, 10000);
    
    return () => {
      clearInterval(metricsInterval);
      clearInterval(feedsInterval);
    };
  }, []);
  
  const loadSystemMetrics = async () => {
    try {
      const metrics = await adminLiveDataService.getSystemMetrics();
      setSystemMetrics(metrics);
    } catch (error) {
      console.error('Failed to load system metrics:', error);
    }
  };
  
  const loadActiveFeeds = async () => {
    try {
      const feeds = await adminLiveDataService.getActiveFeeds();
      setActiveFeeds(feeds);
    } catch (error) {
      console.error('Failed to load active feeds:', error);
    }
  };
  
  const loadSubscribers = async () => {
    try {
      const subs = await adminLiveDataService.getSubscribers();
      setSubscribers(subs);
    } catch (error) {
      console.error('Failed to load subscribers:', error);
    }
  };
  
  const startFeed = async (assetType, dataTypes, symbols) => {
    try {
      setFeedStatus('starting');
      await adminLiveDataService.startFeed({
        assetType,
        dataTypes,
        symbols
      });
      setFeedStatus('running');
      setConnectionStatus('connected');
      loadActiveFeeds();
    } catch (error) {
      console.error('Failed to start feed:', error);
      setFeedStatus('stopped');
    }
  };
  
  const stopFeed = async (feedId) => {
    try {
      setFeedStatus('stopping');
      await adminLiveDataService.stopFeed(feedId);
      setFeedStatus('stopped');
      loadActiveFeeds();
    } catch (error) {
      console.error('Failed to stop feed:', error);
    }
  };
  
  const addSymbolToFeed = async (feedId, symbol) => {
    try {
      await adminLiveDataService.addSymbol(feedId, symbol);
      loadActiveFeeds();
    } catch (error) {
      console.error('Failed to add symbol:', error);
    }
  };
  
  const removeSymbolFromFeed = async (feedId, symbol) => {
    try {
      await adminLiveDataService.removeSymbol(feedId, symbol);
      loadActiveFeeds();
    } catch (error) {
      console.error('Failed to remove symbol:', error);
    }
  };
  
  const handleAddFeed = () => {
    const symbols = symbolInput.split(',').map(s => s.trim().toUpperCase()).filter(s => s);
    if (symbols.length > 0) {
      startFeed(selectedAssetType, selectedDataTypes, symbols);
      setSymbolInput('');
      setShowAddFeedDialog(false);
    }
  };
  
  const renderSystemMetrics = () => (
    <div className="grid" container spacing={3}>
      <div className="grid" item xs={12} md={6} lg={4}>
        <div className="bg-white shadow-md rounded-lg">
          <div className="bg-white shadow-md rounded-lg"Content>
            <div  display="flex" alignItems="center" mb={2}>
              <SignalWifi4Bar color="primary" />
              <div  variant="h6" ml={1}>Active Connections</div>
            </div>
            <div  variant="h3" color="primary">
              {systemMetrics.totalConnections}
            </div>
            <div  variant="body2" color="text.secondary">
              {systemMetrics.activeSymbols} symbols
            </div>
          </div>
        </div>
      </div>
      
      <div className="grid" item xs={12} md={6} lg={4}>
        <div className="bg-white shadow-md rounded-lg">
          <div className="bg-white shadow-md rounded-lg"Content>
            <div  display="flex" alignItems="center" mb={2}>
              <Group color="primary" />
              <div  variant="h6" ml={1}>Active Users</div>
            </div>
            <div  variant="h3" color="primary">
              {systemMetrics.totalUsers}
            </div>
            <div  variant="body2" color="text.secondary">
              subscribers
            </div>
          </div>
        </div>
      </div>
      
      <div className="grid" item xs={12} md={6} lg={4}>
        <div className="bg-white shadow-md rounded-lg">
          <div className="bg-white shadow-md rounded-lg"Content>
            <div  display="flex" alignItems="center" mb={2}>
              <AttachMoney color="success" />
              <div  variant="h6" ml={1}>Cost Savings</div>
            </div>
            <div  variant="h3" color="success.main">
              ${systemMetrics.costSavings}
            </div>
            <div  variant="body2" color="text.secondary">
              vs individual feeds
            </div>
          </div>
        </div>
      </div>
      
      <div className="grid" item xs={12} md={6} lg={4}>
        <div className="bg-white shadow-md rounded-lg">
          <div className="bg-white shadow-md rounded-lg"Content>
            <div  display="flex" alignItems="center" mb={2}>
              <Speed color="primary" />
              <div  variant="h6" ml={1}>Data Throughput</div>
            </div>
            <div  variant="h3" color="primary">
              {systemMetrics.messagesPerSecond}
            </div>
            <div  variant="body2" color="text.secondary">
              messages/second
            </div>
          </div>
        </div>
      </div>
      
      <div className="grid" item xs={12} md={6} lg={4}>
        <div className="bg-white shadow-md rounded-lg">
          <div className="bg-white shadow-md rounded-lg"Content>
            <div  display="flex" alignItems="center" mb={2}>
              <Timeline color="primary" />
              <div  variant="h6" ml={1}>Latency</div>
            </div>
            <div  variant="h3" color="primary">
              {systemMetrics.dataLatency}ms
            </div>
            <div  variant="body2" color="text.secondary">
              average
            </div>
          </div>
        </div>
      </div>
      
      <div className="grid" item xs={12} md={6} lg={4}>
        <div className="bg-white shadow-md rounded-lg">
          <div className="bg-white shadow-md rounded-lg"Content>
            <div  display="flex" alignItems="center" mb={2}>
              <CheckCircle color="success" />
              <div  variant="h6" ml={1}>Uptime</div>
            </div>
            <div  variant="h3" color="success.main">
              {systemMetrics.uptime}%
            </div>
            <div  variant="body2" color="text.secondary">
              last 30 days
            </div>
          </div>
        </div>
      </div>
    </div>
  );
  
  const renderActiveFeeds = () => (
    <div>
      <div  display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <div  variant="h6">Active Data Feeds</div>
        <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
          variant="contained"
          startIcon={<Add />}
          onClick={() => setShowAddFeedDialog(true)}
        >
          Add Feed
        </button>
      </div>
      
      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer component={Paper}>
        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le>
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Asset Type</td>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Data Types</td>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Symbols</td>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Status</td>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Subscribers</td>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Messages/sec</td>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Actions</td>
            </tr>
          </thead>
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
            {activeFeeds.map((feed) => (
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={feed.id}>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                  <div  display="flex" alignItems="center">
                    <span style={{ marginRight: 8 }}>
                      {ASSET_TYPES.find(t => t.value === feed.assetType)?.icon}
                    </span>
                    {feed.assetType}
                  </div>
                </td>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                  <div  display="flex" gap={1}>
                    {feed.dataTypes.map(type => (
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" key={type} label={type} size="small" />
                    ))}
                  </div>
                </td>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                  <div  variant="body2">
                    {feed.symbols.length} symbols
                  </div>
                  <div  variant="caption" color="text.secondary">
                    {feed.symbols.slice(0, 3).join(', ')}
                    {feed.symbols.length > 3 && '...'}
                  </div>
                </td>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                  <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                    label={feed.status}
                    color={feed.status === 'running' ? 'success' : 'default'}
                    size="small"
                  />
                </td>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>{feed.subscriberCount}</td>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>{feed.messagesPerSecond}</td>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                  <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"Group size="small">
                    <div  title="Stop Feed">
                      <button className="p-2 rounded-full hover:bg-gray-100"
                        onClick={() => stopFeed(feed.id)}
                        color="error"
                        size="small"
                      >
                        <Stop />
                      </button>
                    </div>
                    <div  title="Settings">
                      <button className="p-2 rounded-full hover:bg-gray-100" size="small">
                        <Settings />
                      </button>
                    </div>
                  </ButtonGroup>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
  
  const renderSubscribers = () => (
    <div>
      <div  variant="h6" mb={3}>Active Subscribers</div>
      
      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer component={Paper}>
        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le>
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>User</td>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Subscribed Symbols</td>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Connected Since</td>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Data Usage</td>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Status</td>
            </tr>
          </thead>
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
            {subscribers.map((subscriber) => (
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={subscriber.userId}>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                  <div  variant="body2">{subscriber.userId}</div>
                  <div  variant="caption" color="text.secondary">
                    {subscriber.userEmail}
                  </div>
                </td>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                  <div  variant="body2">
                    {subscriber.subscribedSymbols.length} symbols
                  </div>
                  <div  variant="caption" color="text.secondary">
                    {subscriber.subscribedSymbols.slice(0, 3).join(', ')}
                    {subscriber.subscribedSymbols.length > 3 && '...'}
                  </div>
                </td>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                  <div  variant="body2">
                    {new Date(subscriber.connectedSince).toLocaleString()}
                  </div>
                </td>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                  <div  variant="body2">
                    {subscriber.messagesReceived} messages
                  </div>
                </td>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                  <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                    label={subscriber.status}
                    color={subscriber.status === 'active' ? 'success' : 'default'}
                    size="small"
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
  
  return (
    <div>
      <div  display="flex" alignItems="center" mb={3}>
        <AdminPanelSettings sx={{ mr: 2, fontSize: 40 }} color="primary" />
        <div>
          <div  variant="h4" gutterBottom>
            Live Data Administration
          </div>
          <div  variant="body1" color="text.secondary">
            Centralized management of real-time data feeds for all users
          </div>
        </div>
      </div>
      
      {/* Status Banner */}
      <div className="p-4 rounded-md bg-blue-50 border border-blue-200" 
        severity={connectionStatus === 'connected' ? 'success' : 'warning'}
        sx={{ mb: 3 }}
      >
        <div  display="flex" alignItems="center" justifyContent="space-between">
          <div>
            <div  variant="body2">
              System Status: {connectionStatus === 'connected' ? 'Active' : 'Disconnected'}
            </div>
            {lastUpdate && (
              <div  variant="caption">
                Last update: {new Date(lastUpdate).toLocaleTimeString()}
              </div>
            )}
          </div>
          <div  display="flex" gap={1}>
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
              label={`${systemMetrics.totalUsers} users`}
              size="small"
              color="primary"
            />
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
              label={`${systemMetrics.activeSymbols} symbols`}
              size="small"
              color="primary"
            />
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
              label={`$${systemMetrics.costSavings} saved`}
              size="small"
              color="success"
            />
          </div>
        </div>
      </div>
      
      {/* Tabs */}
      <div  sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
        <div className="border-b border-gray-200" value={selectedTab} onChange={(e, v) => setSelectedTab(v)}>
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="System Metrics" />
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Active Feeds" />
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Subscribers" />
        </div>
      </div>
      
      {/* Tab Content */}
      {selectedTab === 0 && renderSystemMetrics()}
      {selectedTab === 1 && renderActiveFeeds()}
      {selectedTab === 2 && renderSubscribers()}
      
      {/* Add Feed Dialog */}
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"
        open={showAddFeedDialog}
        onClose={() => setShowAddFeedDialog(false)}
        maxWidth="md"
        fullWidth
      >
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Title>Add New Data Feed</h2>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Content>
          <div  sx={{ mt: 2 }}>
            <div className="mb-4" fullWidth sx={{ mb: 3 }}>
              <label className="block text-sm font-medium text-gray-700 mb-1">Asset Type</label>
              <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={selectedAssetType}
                onChange={(e) => setSelectedAssetType(e.target.value)}
              >
                {ASSET_TYPES.map(type => (
                  <option  key={type.value} value={type.value}>
                    {type.icon} {type.label}
                  </option>
                ))}
              </select>
            </div>
            
            <div className="mb-4" fullWidth sx={{ mb: 3 }}>
              <label className="block text-sm font-medium text-gray-700 mb-1">Data Types</label>
              <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                multiple
                value={selectedDataTypes}
                onChange={(e) => setSelectedDataTypes(e.target.value)}
                renderValue={(selected) => (
                  <div  sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                    {selected.map((value) => (
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" key={value} label={value} size="small" />
                    ))}
                  </div>
                )}
              >
                {DATA_TYPES.map(type => (
                  <option  key={type.value} value={type.value}>
                    <div>
                      <div  variant="body2">{type.label}</div>
                      <div  variant="caption" color="text.secondary">
                        {type.description}
                      </div>
                    </div>
                  </option>
                ))}
              </select>
            </div>
            
            <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              fullWidth
              label="Symbols (comma-separated)"
              value={symbolInput}
              onChange={(e) => setSymbolInput(e.target.value)}
              placeholder="AAPL, MSFT, GOOGL"
              sx={{ mb: 2 }}
            />
            
            <div  variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              Popular symbols:
            </div>
            <div  display="flex" flexWrap="wrap" gap={1}>
              {POPULAR_SYMBOLS[selectedAssetType]?.map(symbol => (
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                  key={symbol}
                  label={symbol}
                  size="small"
                  clickable
                  onClick={() => {
                    const symbols = symbolInput.split(',').map(s => s.trim()).filter(s => s);
                    if (!symbols.includes(symbol)) {
                      setSymbolInput(symbols.concat(symbol).join(', '));
                    }
                  }}
                />
              ))}
            </div>
          </div>
        </div>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Actions>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" onClick={() => setShowAddFeedDialog(false)}>Cancel</button>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
            onClick={handleAddFeed}
            variant="contained"
            disabled={!symbolInput.trim()}
          >
            Start Feed
          </button>
        </div>
      </div>
    </div>
  );
};

export default AdminLiveData;