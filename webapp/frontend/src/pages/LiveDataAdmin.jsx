/**
 * Live Data Feed Administration Dashboard
 * Comprehensive admin interface for managing live data feeds, API limits, and HFT integration
 */

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Box,
  Paper,
  Typography,
  Grid,
  Card,
  CardContent,
  CardHeader,
  Button,
  Switch,
  FormControlLabel,
  Chip,
  Alert,
  LinearProgress,
  Tabs,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  TextField,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Badge,
  Tooltip,
  CircularProgress
} from '@mui/material';
import {
  PlayArrow,
  Stop,
  Settings,
  TrendingUp,
  Error,
  CheckCircle,
  Warning,
  Add,
  Delete,
  Edit,
  Refresh,
  Timeline,
  Speed,
  DataUsage,
  NetworkCheck,
  PriorityHigh
} from '@mui/icons-material';
import { Line, Doughnut, Bar } from 'react-chartjs-2';
import liveDataService from '../services/liveDataService';
import adminLiveDataService from '../services/adminLiveDataService';

const LiveDataAdmin = () => {
  // Core State
  const [currentTab, setCurrentTab] = useState(0);
  const [feedsData, setFeedsData] = useState(new Map());
  const [apiQuotas, setApiQuotas] = useState({});
  const [systemHealth, setSystemHealth] = useState({});
  const [hftEligibleSymbols, setHftEligibleSymbols] = useState(new Set());
  
  // Dialog State
  const [addFeedDialog, setAddFeedDialog] = useState(false);
  const [configDialog, setConfigDialog] = useState(false);
  const [selectedFeed, setSelectedFeed] = useState(null);
  
  // Form State
  const [newFeedSymbol, setNewFeedSymbol] = useState('');
  const [newFeedPriority, setNewFeedPriority] = useState('standard');
  const [newFeedChannels, setNewFeedChannels] = useState(['trades']);
  
  // Real-time Updates
  useEffect(() => {
    loadDashboardData();
    const interval = setInterval(loadDashboardData, 5000);
    return () => clearInterval(interval);
  }, []);

  const loadDashboardData = useCallback(async () => {
    try {
      // Load feed status
      const feedStatus = await adminLiveDataService.getFeedStatus();
      setFeedsData(new Map(Object.entries(feedStatus.feeds || {})));
      
      // Load API quotas
      const quotas = await adminLiveDataService.getStatistics();
      setApiQuotas(quotas.apiUsage || {});
      
      // Load system health
      const health = await adminLiveDataService.getHealthStatus();
      setSystemHealth(health);
      
      // Update HFT eligible symbols
      const hftSymbols = new Set(
        Object.entries(feedStatus.feeds || {})
          .filter(([_, config]) => config.hftEligible)
          .map(([symbol]) => symbol)
      );
      setHftEligibleSymbols(hftSymbols);
      
    } catch (error) {
      console.error('Failed to load dashboard data:', error);
    }
  }, []);

  // API Quota Management Component
  const ApiQuotaOverview = () => {
    const quotaData = useMemo(() => {
      return Object.entries(apiQuotas).map(([provider, quota]) => ({
        provider,
        used: quota.used || 0,
        limit: quota.limit || 1000,
        percentage: Math.round(((quota.used || 0) / (quota.limit || 1000)) * 100),
        resetTime: quota.resetTime
      }));
    }, [apiQuotas]);

    return (
      <Grid container spacing={3}>
        <Grid item xs={12}>
          <Typography variant="h6" gutterBottom>
            API Usage & Limits
          </Typography>
        </Grid>
        
        {quotaData.map((quota) => (
          <Grid item xs={12} md={4} key={quota.provider}>
            <Card>
              <CardContent>
                <Box display="flex" alignItems="center" mb={2}>
                  <DataUsage color="primary" />
                  <Typography variant="h6" ml={1} textTransform="capitalize">
                    {quota.provider}
                  </Typography>
                </Box>
                
                <Box mb={2}>
                  <Typography variant="body2" color="textSecondary">
                    {quota.used} / {quota.limit} requests
                  </Typography>
                  <LinearProgress
                    variant="determinate"
                    value={quota.percentage}
                    color={quota.percentage > 80 ? 'error' : quota.percentage > 60 ? 'warning' : 'primary'}
                    sx={{ mt: 1, height: 8, borderRadius: 4 }}
                  />
                  <Typography variant="caption" color="textSecondary">
                    {quota.percentage}% used
                  </Typography>
                </Box>
                
                {quota.resetTime && (
                  <Typography variant="caption" color="textSecondary">
                    Resets: {new Date(quota.resetTime).toLocaleTimeString()}
                  </Typography>
                )}
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>
    );
  };

  // Active Feeds Management Component
  const ActiveFeedsManager = () => {
    const handleToggleFeed = async (symbol, currentStatus) => {
      try {
        if (currentStatus === 'active') {
          await adminLiveDataService.stopFeed(symbol);
        } else {
          await adminLiveDataService.startFeed(symbol);
        }
        loadDashboardData();
      } catch (error) {
        console.error(`Failed to toggle feed for ${symbol}:`, error);
      }
    };

    const handleToggleHFT = async (symbol, isHftEligible) => {
      try {
        const updatedConfig = {
          symbol,
          hftEligible: !isHftEligible,
          priority: !isHftEligible ? 'high' : 'standard'
        };
        await adminLiveDataService.updateConfig(updatedConfig);
        loadDashboardData();
      } catch (error) {
        console.error(`Failed to toggle HFT for ${symbol}:`, error);
      }
    };

    return (
      <Box>
        <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
          <Typography variant="h6">
            Active Data Feeds ({feedsData.size})
          </Typography>
          <Button
            variant="contained"
            startIcon={<Add />}
            onClick={() => setAddFeedDialog(true)}
          >
            Add Feed
          </Button>
        </Box>

        <TableContainer component={Paper}>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>Symbol</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Priority</TableCell>
                <TableCell>Channels</TableCell>
                <TableCell>HFT Eligible</TableCell>
                <TableCell>Health</TableCell>
                <TableCell>Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {Array.from(feedsData.entries()).map(([symbol, config]) => (
                <TableRow key={symbol}>
                  <TableCell>
                    <Box display="flex" alignItems="center">
                      <Typography variant="body2" fontWeight="bold">
                        {symbol}
                      </Typography>
                      {hftEligibleSymbols.has(symbol) && (
                        <Chip
                          size="small"
                          label="HFT"
                          color="primary"
                          icon={<Speed />}
                          sx={{ ml: 1 }}
                        />
                      )}
                    </Box>
                  </TableCell>
                  
                  <TableCell>
                    <Chip
                      size="small"
                      label={config.status}
                      color={config.status === 'active' ? 'success' : 'default'}
                      icon={config.status === 'active' ? <CheckCircle /> : <Stop />}
                    />
                  </TableCell>
                  
                  <TableCell>
                    <Chip
                      size="small"
                      label={config.priority}
                      color={config.priority === 'critical' ? 'error' : 
                             config.priority === 'high' ? 'warning' : 'default'}
                    />
                  </TableCell>
                  
                  <TableCell>
                    <Box display="flex" gap={0.5}>
                      {config.channels?.map((channel) => (
                        <Chip key={channel} size="small" label={channel} variant="outlined" />
                      ))}
                    </Box>
                  </TableCell>
                  
                  <TableCell>
                    <FormControlLabel
                      control={
                        <Switch
                          checked={config.hftEligible || false}
                          onChange={() => handleToggleHFT(symbol, config.hftEligible)}
                          size="small"
                        />
                      }
                      label=""
                    />
                  </TableCell>
                  
                  <TableCell>
                    <Box display="flex" alignItems="center">
                      {config.health === 'healthy' ? (
                        <CheckCircle color="success" fontSize="small" />
                      ) : config.health === 'warning' ? (
                        <Warning color="warning" fontSize="small" />
                      ) : (
                        <Error color="error" fontSize="small" />
                      )}
                      <Typography variant="caption" ml={0.5}>
                        {config.latency}ms
                      </Typography>
                    </Box>
                  </TableCell>
                  
                  <TableCell>
                    <Box display="flex" gap={1}>
                      <IconButton
                        size="small"
                        onClick={() => handleToggleFeed(symbol, config.status)}
                        color={config.status === 'active' ? 'error' : 'success'}
                      >
                        {config.status === 'active' ? <Stop /> : <PlayArrow />}
                      </IconButton>
                      <IconButton
                        size="small"
                        onClick={() => {
                          setSelectedFeed({ symbol, ...config });
                          setConfigDialog(true);
                        }}
                      >
                        <Settings />
                      </IconButton>
                      <IconButton
                        size="small"
                        color="error"
                        onClick={() => handleToggleFeed(symbol, 'remove')}
                      >
                        <Delete />
                      </IconButton>
                    </Box>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </Box>
    );
  };

  // WebSocket Health Monitor Component
  const WebSocketHealthMonitor = () => {
    const healthMetrics = useMemo(() => {
      if (!systemHealth.websockets) return [];
      
      return Object.entries(systemHealth.websockets).map(([symbol, health]) => ({
        symbol,
        connected: health.connected,
        latency: health.latency || 0,
        messageRate: health.messageRate || 0,
        lastUpdate: health.lastUpdate,
        errors: health.errors || 0
      }));
    }, [systemHealth]);

    return (
      <Box>
        <Typography variant="h6" gutterBottom>
          WebSocket Health Monitor
        </Typography>
        
        <Grid container spacing={2} mb={3}>
          <Grid item xs={12} md={3}>
            <Card>
              <CardContent>
                <Box display="flex" alignItems="center">
                  <NetworkCheck color="primary" />
                  <Box ml={1}>
                    <Typography variant="h4">
                      {healthMetrics.filter(m => m.connected).length}
                    </Typography>
                    <Typography variant="caption" color="textSecondary">
                      Active Connections
                    </Typography>
                  </Box>
                </Box>
              </CardContent>
            </Card>
          </Grid>
          
          <Grid item xs={12} md={3}>
            <Card>
              <CardContent>
                <Box display="flex" alignItems="center">
                  <Timeline color="primary" />
                  <Box ml={1}>
                    <Typography variant="h4">
                      {Math.round(healthMetrics.reduce((sum, m) => sum + m.latency, 0) / healthMetrics.length || 0)}ms
                    </Typography>
                    <Typography variant="caption" color="textSecondary">
                      Avg Latency
                    </Typography>
                  </Box>
                </Box>
              </CardContent>
            </Card>
          </Grid>
          
          <Grid item xs={12} md={3}>
            <Card>
              <CardContent>
                <Box display="flex" alignItems="center">
                  <Speed color="primary" />
                  <Box ml={1}>
                    <Typography variant="h4">
                      {Math.round(healthMetrics.reduce((sum, m) => sum + m.messageRate, 0))}
                    </Typography>
                    <Typography variant="caption" color="textSecondary">
                      Msg/sec Total
                    </Typography>
                  </Box>
                </Box>
              </CardContent>
            </Card>
          </Grid>
          
          <Grid item xs={12} md={3}>
            <Card>
              <CardContent>
                <Box display="flex" alignItems="center">
                  <Error color="error" />
                  <Box ml={1}>
                    <Typography variant="h4">
                      {healthMetrics.reduce((sum, m) => sum + m.errors, 0)}
                    </Typography>
                    <Typography variant="caption" color="textSecondary">
                      Total Errors
                    </Typography>
                  </Box>
                </Box>
              </CardContent>
            </Card>
          </Grid>
        </Grid>

        <TableContainer component={Paper}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Symbol</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Latency</TableCell>
                <TableCell>Message Rate</TableCell>
                <TableCell>Last Update</TableCell>
                <TableCell>Errors</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {healthMetrics.map((metric) => (
                <TableRow key={metric.symbol}>
                  <TableCell>{metric.symbol}</TableCell>
                  <TableCell>
                    <Chip
                      size="small"
                      label={metric.connected ? 'Connected' : 'Disconnected'}
                      color={metric.connected ? 'success' : 'error'}
                    />
                  </TableCell>
                  <TableCell>{metric.latency}ms</TableCell>
                  <TableCell>{metric.messageRate}/sec</TableCell>
                  <TableCell>
                    {metric.lastUpdate ? new Date(metric.lastUpdate).toLocaleTimeString() : 'Never'}
                  </TableCell>
                  <TableCell>
                    {metric.errors > 0 ? (
                      <Chip size="small" label={metric.errors} color="error" />
                    ) : (
                      '0'
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </Box>
    );
  };

  // Live Data Preview Component
  const LiveDataPreview = () => {
    const [previewSymbol, setPreviewSymbol] = useState('AAPL');
    const [liveData, setLiveData] = useState(null);

    useEffect(() => {
      if (!previewSymbol) return;

      const handleMarketData = (data) => {
        if (data.symbol === previewSymbol) {
          setLiveData(data.data);
        }
      };

      liveDataService.on(`marketData:${previewSymbol}`, handleMarketData);
      liveDataService.subscribe([previewSymbol]);

      return () => {
        liveDataService.off(`marketData:${previewSymbol}`, handleMarketData);
        liveDataService.unsubscribe([previewSymbol]);
      };
    }, [previewSymbol]);

    return (
      <Box>
        <Box display="flex" alignItems="center" gap={2} mb={3}>
          <Typography variant="h6">Live Data Preview</Typography>
          <FormControl size="small" sx={{ minWidth: 120 }}>
            <InputLabel>Symbol</InputLabel>
            <Select
              value={previewSymbol}
              label="Symbol"
              onChange={(e) => setPreviewSymbol(e.target.value)}
            >
              {Array.from(feedsData.keys()).map((symbol) => (
                <MenuItem key={symbol} value={symbol}>{symbol}</MenuItem>
              ))}
            </Select>
          </FormControl>
        </Box>

        {liveData ? (
          <Grid container spacing={2}>
            <Grid item xs={12} md={6}>
              <Card>
                <CardContent>
                  <Typography variant="h6" gutterBottom>Current Price</Typography>
                  <Typography variant="h3" color="primary">
                    ${liveData.price?.toFixed(2) || 'N/A'}
                  </Typography>
                  <Typography variant="body2" color="textSecondary">
                    Last updated: {liveData.timestamp ? new Date(liveData.timestamp).toLocaleTimeString() : 'Unknown'}
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
            
            <Grid item xs={12} md={6}>
              <Card>
                <CardContent>
                  <Typography variant="h6" gutterBottom>Volume</Typography>
                  <Typography variant="h4">
                    {liveData.volume?.toLocaleString() || 'N/A'}
                  </Typography>
                  <Typography variant="body2" color="textSecondary">
                    Daily volume
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
            
            <Grid item xs={12}>
              <Card>
                <CardContent>
                  <Typography variant="h6" gutterBottom>Raw Data</Typography>
                  <Box
                    component="pre"
                    sx={{
                      bgcolor: 'grey.100',
                      p: 2,
                      borderRadius: 1,
                      overflow: 'auto',
                      fontSize: '0.875rem'
                    }}
                  >
                    {JSON.stringify(liveData, null, 2)}
                  </Box>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        ) : (
          <Box display="flex" justifyContent="center" p={4}>
            <CircularProgress />
          </Box>
        )}
      </Box>
    );
  };

  // Add Feed Dialog
  const AddFeedDialog = () => {
    const handleAddFeed = async () => {
      try {
        const config = {
          symbol: newFeedSymbol.toUpperCase(),
          priority: newFeedPriority,
          channels: newFeedChannels,
          hftEligible: newFeedPriority === 'high' || newFeedPriority === 'critical'
        };
        
        await adminLiveDataService.updateConfig(config);
        await adminLiveDataService.startFeed(config.symbol);
        
        setAddFeedDialog(false);
        setNewFeedSymbol('');
        setNewFeedPriority('standard');
        setNewFeedChannels(['trades']);
        loadDashboardData();
      } catch (error) {
        console.error('Failed to add feed:', error);
      }
    };

    return (
      <Dialog open={addFeedDialog} onClose={() => setAddFeedDialog(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Add New Data Feed</DialogTitle>
        <DialogContent>
          <Box sx={{ pt: 1 }}>
            <TextField
              fullWidth
              label="Symbol"
              value={newFeedSymbol}
              onChange={(e) => setNewFeedSymbol(e.target.value.toUpperCase())}
              placeholder="AAPL"
              sx={{ mb: 2 }}
            />
            
            <FormControl fullWidth sx={{ mb: 2 }}>
              <InputLabel>Priority</InputLabel>
              <Select
                value={newFeedPriority}
                label="Priority"
                onChange={(e) => setNewFeedPriority(e.target.value)}
              >
                <MenuItem value="low">Low</MenuItem>
                <MenuItem value="standard">Standard</MenuItem>
                <MenuItem value="high">High (HFT Eligible)</MenuItem>
                <MenuItem value="critical">Critical (HFT Priority)</MenuItem>
              </Select>
            </FormControl>
            
            <Box sx={{ mt: 2, display: 'flex', gap: 1, justifyContent: 'flex-end' }}>
              <Button onClick={() => setAddFeedDialog(false)}>Cancel</Button>
              <Button
                variant="contained"
                onClick={handleAddFeed}
                disabled={!newFeedSymbol}
              >
                Add Feed
              </Button>
            </Box>
          </Box>
        </DialogContent>
      </Dialog>
    );
  };

  return (
    <Box sx={{ p: 3 }}>
      {/* Header */}
      <Box mb={3}>
        <Typography variant="h4" gutterBottom>
          Live Data Administration
        </Typography>
        <Typography variant="body1" color="textSecondary">
          Manage live data feeds, API limits, and HFT integration
        </Typography>
      </Box>

      {/* Quick Stats */}
      <Grid container spacing={2} mb={3}>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center">
                <PlayArrow color="success" />
                <Box ml={1}>
                  <Typography variant="h4">
                    {Array.from(feedsData.values()).filter(f => f.status === 'active').length}
                  </Typography>
                  <Typography variant="caption" color="textSecondary">
                    Active Feeds
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>
        
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center">
                <Speed color="primary" />
                <Box ml={1}>
                  <Typography variant="h4">{hftEligibleSymbols.size}</Typography>
                  <Typography variant="caption" color="textSecondary">
                    HFT Symbols
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>
        
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center">
                <DataUsage color="warning" />
                <Box ml={1}>
                  <Typography variant="h4">
                    {Math.round((apiQuotas.alpaca?.used || 0) / (apiQuotas.alpaca?.limit || 1000) * 100)}%
                  </Typography>
                  <Typography variant="caption" color="textSecondary">
                    API Usage
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>
        
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center">
                <NetworkCheck color={systemHealth.overall === 'healthy' ? 'success' : 'error'} />
                <Box ml={1}>
                  <Typography variant="h4">
                    {systemHealth.overall === 'healthy' ? '✓' : '✗'}
                  </Typography>
                  <Typography variant="caption" color="textSecondary">
                    System Health
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Main Content Tabs */}
      <Paper>
        <Tabs
          value={currentTab}
          onChange={(_, newValue) => setCurrentTab(newValue)}
          variant="scrollable"
          scrollButtons="auto"
        >
          <Tab label="Feed Management" />
          <Tab label="API Quotas" />
          <Tab label="Health Monitor" />
          <Tab label="Live Preview" />
        </Tabs>

        <Box sx={{ p: 3 }}>
          {currentTab === 0 && <ActiveFeedsManager />}
          {currentTab === 1 && <ApiQuotaOverview />}
          {currentTab === 2 && <WebSocketHealthMonitor />}
          {currentTab === 3 && <LiveDataPreview />}
        </Box>
      </Paper>

      {/* Dialogs */}
      <AddFeedDialog />
    </Box>
  );
};

export default LiveDataAdmin;