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
import { Line } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip as ChartTooltip,
  Legend,
  TimeScale
} from 'chart.js';
import 'chartjs-adapter-date-fns';
import adminLiveDataService from '../services/adminLiveDataService';
import { useAuth } from '../contexts/AuthContext';

// Register Chart.js components
ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  ChartTooltip,
  Legend,
  TimeScale
);

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
    <Grid container spacing={3}>
      <Grid item xs={12} md={6} lg={4}>
        <Card>
          <CardContent>
            <Box display="flex" alignItems="center" mb={2}>
              <SignalWifi4Bar color="primary" />
              <Typography variant="h6" ml={1}>Active Connections</Typography>
            </Box>
            <Typography variant="h3" color="primary">
              {systemMetrics.totalConnections}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {systemMetrics.activeSymbols} symbols
            </Typography>
          </CardContent>
        </Card>
      </Grid>
      
      <Grid item xs={12} md={6} lg={4}>
        <Card>
          <CardContent>
            <Box display="flex" alignItems="center" mb={2}>
              <Group color="primary" />
              <Typography variant="h6" ml={1}>Active Users</Typography>
            </Box>
            <Typography variant="h3" color="primary">
              {systemMetrics.totalUsers}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              subscribers
            </Typography>
          </CardContent>
        </Card>
      </Grid>
      
      <Grid item xs={12} md={6} lg={4}>
        <Card>
          <CardContent>
            <Box display="flex" alignItems="center" mb={2}>
              <AttachMoney color="success" />
              <Typography variant="h6" ml={1}>Cost Savings</Typography>
            </Box>
            <Typography variant="h3" color="success.main">
              ${systemMetrics.costSavings}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              vs individual feeds
            </Typography>
          </CardContent>
        </Card>
      </Grid>
      
      <Grid item xs={12} md={6} lg={4}>
        <Card>
          <CardContent>
            <Box display="flex" alignItems="center" mb={2}>
              <Speed color="primary" />
              <Typography variant="h6" ml={1}>Data Throughput</Typography>
            </Box>
            <Typography variant="h3" color="primary">
              {systemMetrics.messagesPerSecond}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              messages/second
            </Typography>
          </CardContent>
        </Card>
      </Grid>
      
      <Grid item xs={12} md={6} lg={4}>
        <Card>
          <CardContent>
            <Box display="flex" alignItems="center" mb={2}>
              <Timeline color="primary" />
              <Typography variant="h6" ml={1}>Latency</Typography>
            </Box>
            <Typography variant="h3" color="primary">
              {systemMetrics.dataLatency}ms
            </Typography>
            <Typography variant="body2" color="text.secondary">
              average
            </Typography>
          </CardContent>
        </Card>
      </Grid>
      
      <Grid item xs={12} md={6} lg={4}>
        <Card>
          <CardContent>
            <Box display="flex" alignItems="center" mb={2}>
              <CheckCircle color="success" />
              <Typography variant="h6" ml={1}>Uptime</Typography>
            </Box>
            <Typography variant="h3" color="success.main">
              {systemMetrics.uptime}%
            </Typography>
            <Typography variant="body2" color="text.secondary">
              last 30 days
            </Typography>
          </CardContent>
        </Card>
      </Grid>
    </Grid>
  );
  
  const renderActiveFeeds = () => (
    <Box>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h6">Active Data Feeds</Typography>
        <Button
          variant="contained"
          startIcon={<Add />}
          onClick={() => setShowAddFeedDialog(true)}
        >
          Add Feed
        </Button>
      </Box>
      
      <TableContainer component={Paper}>
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>Asset Type</TableCell>
              <TableCell>Data Types</TableCell>
              <TableCell>Symbols</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Subscribers</TableCell>
              <TableCell>Messages/sec</TableCell>
              <TableCell>Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {activeFeeds.map((feed) => (
              <TableRow key={feed.id}>
                <TableCell>
                  <Box display="flex" alignItems="center">
                    <span style={{ marginRight: 8 }}>
                      {ASSET_TYPES.find(t => t.value === feed.assetType)?.icon}
                    </span>
                    {feed.assetType}
                  </Box>
                </TableCell>
                <TableCell>
                  <Box display="flex" gap={1}>
                    {feed.dataTypes.map(type => (
                      <Chip key={type} label={type} size="small" />
                    ))}
                  </Box>
                </TableCell>
                <TableCell>
                  <Typography variant="body2">
                    {feed.symbols.length} symbols
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {feed.symbols.slice(0, 3).join(', ')}
                    {feed.symbols.length > 3 && '...'}
                  </Typography>
                </TableCell>
                <TableCell>
                  <Chip
                    label={feed.status}
                    color={feed.status === 'running' ? 'success' : 'default'}
                    size="small"
                  />
                </TableCell>
                <TableCell>{feed.subscriberCount}</TableCell>
                <TableCell>{feed.messagesPerSecond}</TableCell>
                <TableCell>
                  <ButtonGroup size="small">
                    <Tooltip title="Stop Feed">
                      <IconButton
                        onClick={() => stopFeed(feed.id)}
                        color="error"
                        size="small"
                      >
                        <Stop />
                      </IconButton>
                    </Tooltip>
                    <Tooltip title="Settings">
                      <IconButton size="small">
                        <Settings />
                      </IconButton>
                    </Tooltip>
                  </ButtonGroup>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </Box>
  );
  
  const renderSubscribers = () => (
    <Box>
      <Typography variant="h6" mb={3}>Active Subscribers</Typography>
      
      <TableContainer component={Paper}>
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>User</TableCell>
              <TableCell>Subscribed Symbols</TableCell>
              <TableCell>Connected Since</TableCell>
              <TableCell>Data Usage</TableCell>
              <TableCell>Status</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {subscribers.map((subscriber) => (
              <TableRow key={subscriber.userId}>
                <TableCell>
                  <Typography variant="body2">{subscriber.userId}</Typography>
                  <Typography variant="caption" color="text.secondary">
                    {subscriber.userEmail}
                  </Typography>
                </TableCell>
                <TableCell>
                  <Typography variant="body2">
                    {subscriber.subscribedSymbols.length} symbols
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {subscriber.subscribedSymbols.slice(0, 3).join(', ')}
                    {subscriber.subscribedSymbols.length > 3 && '...'}
                  </Typography>
                </TableCell>
                <TableCell>
                  <Typography variant="body2">
                    {new Date(subscriber.connectedSince).toLocaleString()}
                  </Typography>
                </TableCell>
                <TableCell>
                  <Typography variant="body2">
                    {subscriber.messagesReceived} messages
                  </Typography>
                </TableCell>
                <TableCell>
                  <Chip
                    label={subscriber.status}
                    color={subscriber.status === 'active' ? 'success' : 'default'}
                    size="small"
                  />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </Box>
  );
  
  return (
    <Box>
      <Box display="flex" alignItems="center" mb={3}>
        <AdminPanelSettings sx={{ mr: 2, fontSize: 40 }} color="primary" />
        <Box>
          <Typography variant="h4" gutterBottom>
            Live Data Administration
          </Typography>
          <Typography variant="body1" color="text.secondary">
            Centralized management of real-time data feeds for all users
          </Typography>
        </Box>
      </Box>
      
      {/* Status Banner */}
      <Alert 
        severity={connectionStatus === 'connected' ? 'success' : 'warning'}
        sx={{ mb: 3 }}
      >
        <Box display="flex" alignItems="center" justifyContent="space-between">
          <Box>
            <Typography variant="body2">
              System Status: {connectionStatus === 'connected' ? 'Active' : 'Disconnected'}
            </Typography>
            {lastUpdate && (
              <Typography variant="caption">
                Last update: {new Date(lastUpdate).toLocaleTimeString()}
              </Typography>
            )}
          </Box>
          <Box display="flex" gap={1}>
            <Chip
              label={`${systemMetrics.totalUsers} users`}
              size="small"
              color="primary"
            />
            <Chip
              label={`${systemMetrics.activeSymbols} symbols`}
              size="small"
              color="primary"
            />
            <Chip
              label={`$${systemMetrics.costSavings} saved`}
              size="small"
              color="success"
            />
          </Box>
        </Box>
      </Alert>
      
      {/* Tabs */}
      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
        <Tabs value={selectedTab} onChange={(e, v) => setSelectedTab(v)}>
          <Tab label="System Metrics" />
          <Tab label="Active Feeds" />
          <Tab label="Subscribers" />
        </Tabs>
      </Box>
      
      {/* Tab Content */}
      {selectedTab === 0 && renderSystemMetrics()}
      {selectedTab === 1 && renderActiveFeeds()}
      {selectedTab === 2 && renderSubscribers()}
      
      {/* Add Feed Dialog */}
      <Dialog
        open={showAddFeedDialog}
        onClose={() => setShowAddFeedDialog(false)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>Add New Data Feed</DialogTitle>
        <DialogContent>
          <Box sx={{ mt: 2 }}>
            <FormControl fullWidth sx={{ mb: 3 }}>
              <InputLabel>Asset Type</InputLabel>
              <Select
                value={selectedAssetType}
                onChange={(e) => setSelectedAssetType(e.target.value)}
              >
                {ASSET_TYPES.map(type => (
                  <MenuItem key={type.value} value={type.value}>
                    {type.icon} {type.label}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            
            <FormControl fullWidth sx={{ mb: 3 }}>
              <InputLabel>Data Types</InputLabel>
              <Select
                multiple
                value={selectedDataTypes}
                onChange={(e) => setSelectedDataTypes(e.target.value)}
                renderValue={(selected) => (
                  <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                    {selected.map((value) => (
                      <Chip key={value} label={value} size="small" />
                    ))}
                  </Box>
                )}
              >
                {DATA_TYPES.map(type => (
                  <MenuItem key={type.value} value={type.value}>
                    <Box>
                      <Typography variant="body2">{type.label}</Typography>
                      <Typography variant="caption" color="text.secondary">
                        {type.description}
                      </Typography>
                    </Box>
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            
            <TextField
              fullWidth
              label="Symbols (comma-separated)"
              value={symbolInput}
              onChange={(e) => setSymbolInput(e.target.value)}
              placeholder="AAPL, MSFT, GOOGL"
              sx={{ mb: 2 }}
            />
            
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              Popular symbols:
            </Typography>
            <Box display="flex" flexWrap="wrap" gap={1}>
              {POPULAR_SYMBOLS[selectedAssetType]?.map(symbol => (
                <Chip
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
            </Box>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowAddFeedDialog(false)}>Cancel</Button>
          <Button
            onClick={handleAddFeed}
            variant="contained"
            disabled={!symbolInput.trim()}
          >
            Start Feed
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default AdminLiveData;