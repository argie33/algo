/**
 * HFT Trading Dashboard - High Frequency Trading Interface
 * Real-time monitoring, strategy management, and performance analytics
 */

import React, { useState, useEffect, useRef } from 'react';
import {
  Box,
  Card,
  CardContent,
  CardHeader,
  Typography,
  Grid,
  Button,
  Switch,
  FormControlLabel,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Chip,
  LinearProgress,
  IconButton,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  TextField,
  Alert,
  Divider,
  Tooltip,
  Badge
} from '@mui/material';
import {
  PlayArrow,
  Stop,
  TrendingUp,
  TrendingDown,
  Speed,
  Timeline,
  Assessment,
  MonetizationOn,
  AccountBalance,
  Settings,
  Refresh,
  Circle,
  CheckCircle,
  Warning,
  Error
} from '@mui/icons-material';
import { 
  Chart as ChartJS, 
  CategoryScale, 
  LinearScale, 
  PointElement, 
  LineElement, 
  Title, 
  Tooltip as ChartTooltip, 
  Legend,
  Filler 
} from 'chart.js';
import { Line } from 'react-chartjs-2';
import hftEngine from '../services/hftEngine.js';
import liveDataService from '../services/liveDataService.js';

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  ChartTooltip,
  Legend,
  Filler
);

const HFTTrading = () => {
  // State management
  const [isEngineRunning, setIsEngineRunning] = useState(false);
  const [metrics, setMetrics] = useState({
    totalTrades: 0,
    profitableTrades: 0,
    totalPnL: 0,
    winRate: 0,
    dailyPnL: 0,
    openPositions: 0,
    signalsGenerated: 0,
    avgExecutionTime: 0,
    uptime: 0
  });
  const [strategies, setStrategies] = useState([]);
  const [positions, setPositions] = useState([]);
  const [recentTrades, setRecentTrades] = useState([]);
  const [performanceData, setPerformanceData] = useState({ labels: [], data: [] });
  const [selectedStrategy, setSelectedStrategy] = useState('scalping');
  const [strategyParams, setStrategyParams] = useState({});
  const [connectionStatus, setConnectionStatus] = useState('disconnected');
  const [marketData, setMarketData] = useState(new Map());
  
  // Refs for real-time updates
  const metricsIntervalRef = useRef();
  const performanceHistoryRef = useRef([]);
  
  // Initialize component
  useEffect(() => {
    loadInitialData();
    setupRealtimeUpdates();
    
    return () => {
      clearInterval(metricsIntervalRef.current);
    };
  }, []);

  const loadInitialData = async () => {
    try {
      // Load strategies
      const strategiesData = hftEngine.getStrategies();
      setStrategies(strategiesData);
      
      // Load initial metrics
      const metricsData = hftEngine.getMetrics();
      setMetrics(metricsData);
      setIsEngineRunning(metricsData.isRunning);
      
      // Set initial strategy params
      if (strategiesData.length > 0) {
        setStrategyParams(strategiesData[0].params || {});
      }
      
      // Check connection status
      setConnectionStatus(liveDataService.getConnectionStatus().toLowerCase());
      
    } catch (error) {
      console.error('Failed to load initial data:', error);
    }
  };

  const setupRealtimeUpdates = () => {
    // Update metrics every second
    metricsIntervalRef.current = setInterval(() => {
      const currentMetrics = hftEngine.getMetrics();
      setMetrics(currentMetrics);
      setPositions(currentMetrics.activePositions || []);
      
      // Update performance chart data
      updatePerformanceChart(currentMetrics);
    }, 1000);
    
    // Listen to live data service events
    liveDataService.on('connected', () => setConnectionStatus('connected'));
    liveDataService.on('disconnected', () => setConnectionStatus('disconnected'));
    liveDataService.on('marketData', handleMarketData);
  };

  const handleMarketData = (data) => {
    setMarketData(prev => new Map(prev.set(data.symbol, data.data)));
  };

  const updatePerformanceChart = (currentMetrics) => {
    const now = new Date();
    const timeLabel = now.toLocaleTimeString();
    
    performanceHistoryRef.current.push({
      time: timeLabel,
      pnl: currentMetrics.totalPnL || 0,
      timestamp: now.getTime()
    });
    
    // Keep only last 50 data points
    if (performanceHistoryRef.current.length > 50) {
      performanceHistoryRef.current.shift();
    }
    
    setPerformanceData({
      labels: performanceHistoryRef.current.map(d => d.time),
      data: performanceHistoryRef.current.map(d => d.pnl)
    });
  };

  const handleStartEngine = async () => {
    try {
      const result = await hftEngine.start([selectedStrategy]);
      if (result.success) {
        setIsEngineRunning(true);
        console.log('✅ HFT Engine started successfully');
      } else {
        console.error('❌ Failed to start HFT Engine:', result.error);
      }
    } catch (error) {
      console.error('❌ Error starting HFT Engine:', error);
    }
  };

  const handleStopEngine = async () => {
    try {
      const result = await hftEngine.stop();
      if (result.success) {
        setIsEngineRunning(false);
        console.log('✅ HFT Engine stopped successfully');
      } else {
        console.error('❌ Failed to stop HFT Engine:', result.error);
      }
    } catch (error) {
      console.error('❌ Error stopping HFT Engine:', error);
    }
  };

  const handleStrategyUpdate = () => {
    const result = hftEngine.updateStrategy(selectedStrategy, {
      params: strategyParams,
      enabled: true
    });
    
    if (result.success) {
      console.log('✅ Strategy updated successfully');
      setStrategies(hftEngine.getStrategies());
    }
  };

  // Chart configuration
  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        display: false
      },
      title: {
        display: true,
        text: 'Real-Time P&L Performance',
        font: { size: 14 }
      }
    },
    scales: {
      y: {
        ticks: { 
          callback: (value) => `$${value.toFixed(2)}`
        }
      }
    },
    elements: {
      line: {
        tension: 0.4
      }
    },
    animation: {
      duration: 0 // Disable animation for real-time updates
    }
  };

  const chartData = {
    labels: performanceData.labels,
    datasets: [
      {
        label: 'P&L',
        data: performanceData.data,
        borderColor: performanceData.data.length > 0 && performanceData.data[performanceData.data.length - 1] >= 0 
          ? '#4caf50' : '#f44336',
        backgroundColor: performanceData.data.length > 0 && performanceData.data[performanceData.data.length - 1] >= 0 
          ? 'rgba(76, 175, 80, 0.1)' : 'rgba(244, 67, 54, 0.1)',
        fill: true,
        borderWidth: 2,
        pointRadius: 1,
        pointHoverRadius: 4
      }
    ]
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'connected': return 'success';
      case 'connecting': return 'warning';
      default: return 'error';
    }
  };

  const formatCurrency = (value) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2
    }).format(value);
  };

  const formatPercentage = (value) => {
    return `${value.toFixed(1)}%`;
  };

  const formatTime = (ms) => {
    const seconds = Math.floor(ms / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);
    
    if (hours > 0) {
      return `${hours}h ${minutes % 60}m`;
    } else if (minutes > 0) {
      return `${minutes}m ${seconds % 60}s`;
    } else {
      return `${seconds}s`;
    }
  };

  return (
    <Box sx={{ p: 3 }}>
      {/* Header */}
      <Box mb={3}>
        <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
          <Box>
            <Typography variant="h4" gutterBottom sx={{ fontWeight: 'bold' }}>
              HFT Trading Dashboard
            </Typography>
            <Typography variant="body1" color="textSecondary">
              High Frequency Trading • Real-time Strategy Execution
            </Typography>
          </Box>
          
          <Box display="flex" alignItems="center" gap={2}>
            <Box display="flex" alignItems="center" gap={1}>
              <Circle 
                color={getStatusColor(connectionStatus)} 
                sx={{ fontSize: 12 }}
              />
              <Typography variant="body2" color={getStatusColor(connectionStatus)}>
                {connectionStatus.toUpperCase()}
              </Typography>
            </Box>
            
            {isEngineRunning ? (
              <Button
                variant="contained"
                color="error"
                startIcon={<Stop />}
                onClick={handleStopEngine}
                sx={{ fontWeight: 'bold' }}
              >
                Stop Engine
              </Button>
            ) : (
              <Button
                variant="contained"
                color="success"
                startIcon={<PlayArrow />}
                onClick={handleStartEngine}
                disabled={connectionStatus !== 'connected'}
                sx={{ fontWeight: 'bold' }}
              >
                Start Engine
              </Button>
            )}
          </Box>
        </Box>
      </Box>

      {/* Key Metrics Dashboard */}
      <Grid container spacing={2} mb={3}>
        <Grid item xs={6} sm={4} md={2}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center">
                <MonetizationOn color="primary" />
                <Box ml={1}>
                  <Typography variant="h4" color="primary">
                    {formatCurrency(metrics.totalPnL)}
                  </Typography>
                  <Typography variant="caption" color="textSecondary">
                    Total P&L
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>
        
        <Grid item xs={6} sm={4} md={2}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center">
                <TrendingUp color="success" />
                <Box ml={1}>
                  <Typography variant="h4" color="success.main">
                    {formatCurrency(metrics.dailyPnL)}
                  </Typography>
                  <Typography variant="caption" color="textSecondary">
                    Daily P&L
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>
        
        <Grid item xs={6} sm={4} md={2}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center">
                <Assessment color="secondary" />
                <Box ml={1}>
                  <Typography variant="h4" color="secondary">
                    {metrics.totalTrades}
                  </Typography>
                  <Typography variant="caption" color="textSecondary">
                    Total Trades
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>
        
        <Grid item xs={6} sm={4} md={2}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center">
                <Timeline color="warning" />
                <Box ml={1}>
                  <Typography variant="h4" color="warning.main">
                    {formatPercentage(metrics.winRate || 0)}
                  </Typography>
                  <Typography variant="caption" color="textSecondary">
                    Win Rate
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>
        
        <Grid item xs={6} sm={4} md={2}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center">
                <AccountBalance color="info" />
                <Box ml={1}>
                  <Typography variant="h4" color="info.main">
                    {metrics.openPositions}
                  </Typography>
                  <Typography variant="caption" color="textSecondary">
                    Open Positions
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>
        
        <Grid item xs={6} sm={4} md={2}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center">
                <Speed color="action" />
                <Box ml={1}>
                  <Typography variant="h4">
                    {metrics.avgExecutionTime?.toFixed(0) || 0}ms
                  </Typography>
                  <Typography variant="caption" color="textSecondary">
                    Avg Execution
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      <Grid container spacing={3} mb={3}>
        {/* Performance Chart */}
        <Grid item xs={12} lg={8}>
          <Card>
            <CardHeader title="Real-Time P&L Performance" />
            <CardContent>
              <Box sx={{ height: 300 }}>
                <Line data={chartData} options={chartOptions} />
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Strategy Controls */}
        <Grid item xs={12} lg={4}>
          <Card>
            <CardHeader title="Strategy Configuration" />
            <CardContent>
              <Box display="flex" flexDirection="column" gap={2}>
                <FormControl fullWidth>
                  <InputLabel>Active Strategy</InputLabel>
                  <Select
                    value={selectedStrategy}
                    label="Active Strategy"
                    onChange={(e) => setSelectedStrategy(e.target.value)}
                  >
                    {strategies.map((strategy) => (
                      <MenuItem key={strategy.name} value={strategy.name}>
                        {strategy.name.charAt(0).toUpperCase() + strategy.name.slice(1)}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>

                {selectedStrategy === 'scalping' && (
                  <>
                    <TextField
                      label="Min Spread (%)"
                      type="number"
                      inputProps={{ step: 0.001 }}
                      value={strategyParams.minSpread || 0.001}
                      onChange={(e) => setStrategyParams(prev => ({ ...prev, minSpread: parseFloat(e.target.value) }))}
                      fullWidth
                      size="small"
                    />
                    
                    <TextField
                      label="Max Spread (%)"
                      type="number"
                      inputProps={{ step: 0.001 }}
                      value={strategyParams.maxSpread || 0.005}
                      onChange={(e) => setStrategyParams(prev => ({ ...prev, maxSpread: parseFloat(e.target.value) }))}
                      fullWidth
                      size="small"
                    />
                    
                    <TextField
                      label="Volume Threshold"
                      type="number"
                      value={strategyParams.volume_threshold || 1000}
                      onChange={(e) => setStrategyParams(prev => ({ ...prev, volume_threshold: parseInt(e.target.value) }))}
                      fullWidth
                      size="small"
                    />
                  </>
                )}

                <Button
                  variant="contained"
                  onClick={handleStrategyUpdate}
                  fullWidth
                  startIcon={<Settings />}
                >
                  Update Strategy
                </Button>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      <Grid container spacing={3}>
        {/* Active Positions */}
        <Grid item xs={12} lg={6}>
          <Card>
            <CardHeader title="Active Positions" />
            <CardContent>
              {positions.length > 0 ? (
                <Box display="flex" flexDirection="column" gap={2}>
                  {positions.map((position, index) => (
                    <Paper key={index} elevation={1} sx={{ p: 2 }}>
                      <Box display="flex" justifyContent="space-between" alignItems="flex-start" mb={1}>
                        <Box>
                          <Typography variant="h6">{position.symbol}</Typography>
                          <Typography variant="body2" color="textSecondary">{position.strategy}</Typography>
                        </Box>
                        <Box textAlign="right">
                          <Chip 
                            label={position.type} 
                            color="success" 
                            size="small" 
                          />
                          <Typography variant="body2" color="textSecondary">
                            {position.quantity} units
                          </Typography>
                        </Box>
                      </Box>
                      
                      <Grid container spacing={2} sx={{ mt: 1 }}>
                        <Grid item xs={6}>
                          <Typography variant="body2" color="textSecondary">Entry:</Typography>
                          <Typography variant="body2">{formatCurrency(position.avgPrice)}</Typography>
                        </Grid>
                        <Grid item xs={6}>
                          <Typography variant="body2" color="textSecondary">Current:</Typography>
                          <Typography variant="body2">
                            {formatCurrency(marketData.get(position.symbol)?.price || position.avgPrice)}
                          </Typography>
                        </Grid>
                        {position.stopLoss && (
                          <Grid item xs={6}>
                            <Typography variant="body2" color="textSecondary">Stop Loss:</Typography>
                            <Typography variant="body2" color="error">{formatCurrency(position.stopLoss)}</Typography>
                          </Grid>
                        )}
                        {position.takeProfit && (
                          <Grid item xs={6}>
                            <Typography variant="body2" color="textSecondary">Take Profit:</Typography>
                            <Typography variant="body2" color="success.main">{formatCurrency(position.takeProfit)}</Typography>
                          </Grid>
                        )}
                      </Grid>
                      
                      <Typography variant="caption" color="textSecondary" sx={{ mt: 1, display: 'block' }}>
                        Opened: {new Date(position.openTime).toLocaleTimeString()}
                      </Typography>
                    </Paper>
                  ))}
                </Box>
              ) : (
                <Box textAlign="center" py={4}>
                  <Typography color="textSecondary">
                    No active positions
                  </Typography>
                </Box>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* System Status */}
        <Grid item xs={12} lg={6}>
          <Card>
            <CardHeader title="System Status" />
            <CardContent>
              <Box display="flex" flexDirection="column" gap={2}>
                <Box display="flex" justifyContent="space-between" alignItems="center">
                  <Typography color="textSecondary">Engine Status</Typography>
                  <Chip 
                    label={isEngineRunning ? 'RUNNING' : 'STOPPED'} 
                    color={isEngineRunning ? 'success' : 'error'}
                    icon={isEngineRunning ? <CheckCircle /> : <Error />}
                  />
                </Box>
                
                <Divider />
                
                <Box display="flex" justifyContent="space-between" alignItems="center">
                  <Typography color="textSecondary">Uptime</Typography>
                  <Typography>{formatTime(metrics.uptime || 0)}</Typography>
                </Box>
                
                <Box display="flex" justifyContent="space-between" alignItems="center">
                  <Typography color="textSecondary">Signals Generated</Typography>
                  <Typography>{metrics.signalsGenerated}</Typography>
                </Box>
                
                <Box display="flex" justifyContent="space-between" alignItems="center">
                  <Typography color="textSecondary">Orders Executed</Typography>
                  <Typography>{metrics.ordersExecuted || 0}</Typography>
                </Box>
                
                <Box display="flex" justifyContent="space-between" alignItems="center">
                  <Typography color="textSecondary">Connection Quality</Typography>
                  <Chip 
                    label={connectionStatus === 'connected' ? 'EXCELLENT' : 'POOR'}
                    color={connectionStatus === 'connected' ? 'success' : 'error'}
                    size="small"
                  />
                </Box>

                <Divider sx={{ my: 2 }} />
                
                {/* Risk Metrics */}
                <Typography variant="h6" gutterBottom>Risk Management</Typography>
                
                <Box>
                  <Box display="flex" justifyContent="space-between" mb={1}>
                    <Typography variant="body2" color="textSecondary">Daily Loss Limit</Typography>
                    <Typography variant="body2">
                      {formatCurrency(Math.abs(metrics.dailyPnL || 0))} / {formatCurrency(500)}
                    </Typography>
                  </Box>
                  <LinearProgress 
                    variant="determinate" 
                    value={Math.min(100, (Math.abs(metrics.dailyPnL || 0) / 500) * 100)}
                    color="error"
                  />
                </Box>
                
                <Box>
                  <Box display="flex" justifyContent="space-between" mb={1}>
                    <Typography variant="body2" color="textSecondary">Open Positions</Typography>
                    <Typography variant="body2">{metrics.openPositions} / 5</Typography>
                  </Box>
                  <LinearProgress 
                    variant="determinate" 
                    value={Math.min(100, (metrics.openPositions / 5) * 100)}
                    color="primary"
                  />
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
};

export default HFTTrading;