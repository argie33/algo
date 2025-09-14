import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Box,
  Card,
  CardContent,
  Chip,
  Typography,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Grid,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Switch,
  FormControlLabel,
  Alert,
  CircularProgress,
  IconButton,
  Tabs,
  Tab,
  LinearProgress,
  Avatar,
  ListItem,
  ListItemAvatar,
  ListItemText,
  List,
} from '@mui/material';
import {
  TrendingUp,
  TrendingDown,
  Refresh,
  Assessment,
  ShowChart,
  Timeline,
  Speed,
  NotificationsActive,
  CheckCircle,
  Warning,
  Info,
  Tune,
} from '@mui/icons-material';
import { formatCurrency, formatPercentage } from '../utils/formatters';
import realTimeDataService from '../services/realTimeDataService';

const TradingSignals = ({ onSignalAction, selectedSymbol = null }) => {
  const [signals, setSignals] = useState([]);
  const [loading, setLoading] = useState(false);
  const [lastUpdate, setLastUpdate] = useState(null);
  const [signalType, setSignalType] = useState('all');
  const [timeframe, setTimeframe] = useState('1h');
  const [isRealTime, setIsRealTime] = useState(false);
  const [selectedTab, setSelectedTab] = useState(0);
  const [selectedSignal, setSelectedSignal] = useState(null);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [signalSettings] = useState({
    minConfidence: 70,
    maxRisk: 5,
    enableAlerts: true,
    autoExecute: false
  });
  
  // Real-time signal updates
  const [realtimeUpdates, setRealtimeUpdates] = useState({});

  // Signal types configuration
  const signalTypes = {
    all: { name: 'All Signals', color: 'primary' },
    buy: { name: 'Buy Signals', color: 'success' },
    sell: { name: 'Sell Signals', color: 'error' },
    hold: { name: 'Hold Signals', color: 'warning' },
    momentum: { name: 'Momentum', color: 'info' },
    reversal: { name: 'Reversal', color: 'secondary' },
    breakout: { name: 'Breakout', color: 'primary' }
  };

  // Timeframe options
  const timeframes = {
    '5m': '5 Minutes',
    '15m': '15 Minutes', 
    '1h': '1 Hour',
    '4h': '4 Hours',
    '1d': 'Daily',
    '1w': 'Weekly'
  };

  // Fetch trading signals
  const fetchSignals = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        type: signalType,
        timeframe: timeframe,
        limit: 50
      });
      
      if (selectedSymbol) {
        params.append('symbol', selectedSymbol);
      }

      const response = await fetch(`/api/signals/ai-signals?${params}`);
      const data = await response.json();
      
      if (data.success) {
        setSignals(data.data.signals || []);
        setLastUpdate(new Date());
        
        // Subscribe to real-time updates
        if (isRealTime && data.data.signals) {
          const symbols = data.data.signals.map(s => s.symbol);
          symbols.forEach(symbol => {
            realTimeDataService.subscribe('signals', (signalData) => {
              if (signalData[symbol]) {
                setRealtimeUpdates(prev => ({
                  ...prev,
                  [symbol]: signalData[symbol]
                }));
              }
            });
          });
        }
      }
    } catch (error) {
      console.error('Failed to fetch signals:', error);
    }
    setLoading(false);
  }, [signalType, timeframe, selectedSymbol, isRealTime]);

  // Auto-refresh for real-time mode
  useEffect(() => {
    let interval;
    if (isRealTime) {
      fetchSignals(); // Initial fetch
      interval = setInterval(fetchSignals, 30000); // Every 30 seconds
    }
    return () => clearInterval(interval);
  }, [isRealTime, fetchSignals]);

  // Calculate signal strength based on multiple factors
  const calculateSignalStrength = (signal) => {
    let strength = 50; // Base strength

    // Technical indicators weight
    strength += (signal.rsi_score || 0) * 0.2;
    strength += (signal.macd_score || 0) * 0.2;
    strength += (signal.bollinger_score || 0) * 0.15;
    
    // Volume confirmation
    if (signal.volume_confirmation) strength += 10;
    
    // News sentiment
    strength += (signal.news_sentiment || 0) * 0.15;
    
    // Market conditions
    strength += (signal.market_score || 0) * 0.1;
    
    // Pattern recognition
    if (signal.pattern_match) strength += 15;

    return Math.max(0, Math.min(100, Math.round(strength)));
  };

  // Enhanced signals with real-time data
  const enhancedSignals = useMemo(() => {
    return signals.map(signal => {
      const realtimeData = realtimeUpdates[signal.symbol];
      return {
        ...signal,
        strength: calculateSignalStrength(signal),
        isRealTime: !!realtimeData,
        currentPrice: realtimeData?.price || signal.price,
        priceChange: realtimeData?.change || signal.price_change
      };
    });
  }, [signals, realtimeUpdates]);

  // Filter signals based on settings
  const filteredSignals = useMemo(() => {
    return enhancedSignals.filter(signal => {
      const meetsConfidence = signal.confidence >= signalSettings.minConfidence;
      const meetsRisk = signal.risk_level <= signalSettings.maxRisk;
      return meetsConfidence && meetsRisk;
    });
  }, [enhancedSignals, signalSettings]);

  // Group signals by type for tabs
  const signalGroups = useMemo(() => {
    const groups = {
      active: filteredSignals.filter(s => s.status === 'active'),
      executed: filteredSignals.filter(s => s.status === 'executed'),
      expired: filteredSignals.filter(s => s.status === 'expired'),
      watching: filteredSignals.filter(s => s.status === 'watching')
    };
    return groups;
  }, [filteredSignals]);

  // Handle signal action
  const handleSignalAction = (signal, action) => {
    if (onSignalAction) {
      onSignalAction(signal, action);
    }
  };

  // Get signal color based on type and strength
  const getSignalColor = (signal) => {
    if (signal.strength >= 80) return 'success';
    if (signal.strength >= 60) return 'info';
    if (signal.strength >= 40) return 'warning';
    return 'error';
  };

  // Get signal icon
  const getSignalIcon = (signal) => {
    const iconProps = { fontSize: 'small' };
    
    switch (signal.signal_type) {
      case 'buy': return <TrendingUp color="success" {...iconProps} />;
      case 'sell': return <TrendingDown color="error" {...iconProps} />;
      case 'momentum': return <Speed color="info" {...iconProps} />;
      case 'reversal': return <Timeline color="secondary" {...iconProps} />;
      case 'breakout': return <ShowChart color="primary" {...iconProps} />;
      default: return <Assessment {...iconProps} />;
    }
  };

  return (
    <Box>
      {/* Signal Controls */}
      <Card sx={{ mb: 2 }}>
        <CardContent>
          <Grid container spacing={2} alignItems="center">
            <Grid item xs={12} md={2}>
              <FormControl fullWidth size="small">
                <InputLabel>Signal Type</InputLabel>
                <Select
                  value={signalType}
                  onChange={(e) => setSignalType(e.target.value)}
                  label="Signal Type"
                >
                  {Object.entries(signalTypes).map(([key, config]) => (
                    <MenuItem key={key} value={key}>
                      <Chip
                        label={config.name}
                        color={config.color}
                        size="small"
                        sx={{ mr: 1 }}
                      />
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            
            <Grid item xs={12} md={2}>
              <FormControl fullWidth size="small">
                <InputLabel>Timeframe</InputLabel>
                <Select
                  value={timeframe}
                  onChange={(e) => setTimeframe(e.target.value)}
                  label="Timeframe"
                >
                  {Object.entries(timeframes).map(([key, name]) => (
                    <MenuItem key={key} value={key}>{name}</MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            
            <Grid item xs={12} md={2}>
              <FormControlLabel
                control={
                  <Switch
                    checked={isRealTime}
                    onChange={(e) => setIsRealTime(e.target.checked)}
                    color="primary"
                  />
                }
                label="Real-Time"
              />
            </Grid>
            
            <Grid item xs={12} md={3}>
              <Button
                variant="contained"
                onClick={fetchSignals}
                disabled={loading}
                startIcon={loading ? <CircularProgress size={16} /> : <Refresh />}
                fullWidth
              >
                {loading ? 'Updating...' : 'Refresh Signals'}
              </Button>
            </Grid>
            
            <Grid item xs={12} md={3}>
              <Button
                variant="outlined"
                startIcon={<Tune />}
                onClick={() => setDetailsOpen(true)}
                fullWidth
              >
                Settings
              </Button>
            </Grid>
          </Grid>
          
          {/* Signal Summary */}
          <Box mt={2}>
            <Grid container spacing={2}>
              <Grid item xs={6} md={3}>
                <Typography variant="h6" color="success.main">
                  {signalGroups.active.length}
                </Typography>
                <Typography variant="caption">Active Signals</Typography>
              </Grid>
              <Grid item xs={6} md={3}>
                <Typography variant="h6" color="info.main">
                  {signalGroups.watching.length}
                </Typography>
                <Typography variant="caption">Watching</Typography>
              </Grid>
              <Grid item xs={6} md={3}>
                <Typography variant="h6" color="primary.main">
                  {signalGroups.executed.length}
                </Typography>
                <Typography variant="caption">Executed</Typography>
              </Grid>
              <Grid item xs={6} md={3}>
                <Typography variant="h6" color="text.secondary">
                  {lastUpdate && `Last: ${lastUpdate.toLocaleTimeString()}`}
                </Typography>
                {isRealTime && <Chip label="LIVE" color="success" size="small" />}
              </Grid>
            </Grid>
          </Box>
        </CardContent>
      </Card>

      {/* Signal Tabs */}
      <Card>
        <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
          <Tabs value={selectedTab} onChange={(e, newValue) => setSelectedTab(newValue)}>
            <Tab 
              label={`Active (${signalGroups.active.length})`}
              icon={<NotificationsActive />}
            />
            <Tab 
              label={`Watching (${signalGroups.watching.length})`}
              icon={<Info />}
            />
            <Tab 
              label={`Executed (${signalGroups.executed.length})`}
              icon={<CheckCircle />}
            />
            <Tab 
              label={`Expired (${signalGroups.expired.length})`}
              icon={<Warning />}
            />
          </Tabs>
        </Box>

        <CardContent>
          {/* Active Signals */}
          {selectedTab === 0 && (
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Signal</TableCell>
                    <TableCell>Symbol</TableCell>
                    <TableCell>Price</TableCell>
                    <TableCell>Target</TableCell>
                    <TableCell>Strength</TableCell>
                    <TableCell>Risk</TableCell>
                    <TableCell>Time</TableCell>
                    <TableCell>Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {signalGroups.active.map((signal) => (
                    <TableRow 
                      key={signal.id}
                      hover
                      sx={{
                        backgroundColor: signal.isRealTime ? 'rgba(76, 175, 80, 0.05)' : 'inherit'
                      }}
                    >
                      <TableCell>
                        <Box display="flex" alignItems="center" gap={1}>
                          {getSignalIcon(signal)}
                          <Typography variant="body2" fontWeight="bold">
                            {signal.signal_type.toUpperCase()}
                          </Typography>
                          {signal.isRealTime && <Chip label="LIVE" size="small" color="success" />}
                        </Box>
                      </TableCell>
                      
                      <TableCell>
                        <Typography variant="body2" fontWeight="bold">
                          {signal.symbol}
                        </Typography>
                      </TableCell>
                      
                      <TableCell>
                        <Box>
                          <Typography variant="body2">
                            {formatCurrency(signal.currentPrice)}
                          </Typography>
                          {signal.priceChange !== 0 && (
                            <Typography 
                              variant="caption" 
                              color={signal.priceChange > 0 ? 'success.main' : 'error.main'}
                            >
                              {formatPercentage(signal.priceChange)}
                            </Typography>
                          )}
                        </Box>
                      </TableCell>
                      
                      <TableCell>
                        <Typography variant="body2">
                          {formatCurrency(signal.target_price)}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          {formatPercentage(((signal.target_price - signal.currentPrice) / signal.currentPrice) * 100)}
                        </Typography>
                      </TableCell>
                      
                      <TableCell>
                        <Box display="flex" alignItems="center" gap={1}>
                          <Typography 
                            variant="body2" 
                            fontWeight="bold"
                            color={getSignalColor(signal) + '.main'}
                          >
                            {signal.strength}%
                          </Typography>
                          <LinearProgress
                            variant="determinate"
                            value={signal.strength}
                            color={getSignalColor(signal)}
                            sx={{ width: 40, height: 6 }}
                          />
                        </Box>
                      </TableCell>
                      
                      <TableCell>
                        <Chip
                          label={`${signal.risk_level}/10`}
                          color={signal.risk_level <= 3 ? 'success' : signal.risk_level <= 6 ? 'warning' : 'error'}
                          size="small"
                        />
                      </TableCell>
                      
                      <TableCell>
                        <Typography variant="caption">
                          {new Date(signal.timestamp).toLocaleTimeString()}
                        </Typography>
                      </TableCell>
                      
                      <TableCell>
                        <Box display="flex" gap={1}>
                          <Button
                            size="small"
                            variant="contained"
                            color={signal.signal_type === 'buy' ? 'success' : 'error'}
                            onClick={() => handleSignalAction(signal, 'execute')}
                          >
                            Execute
                          </Button>
                          <Button
                            size="small"
                            variant="outlined"
                            onClick={() => {
                              setSelectedSignal(signal);
                              setDetailsOpen(true);
                            }}
                          >
                            Details
                          </Button>
                          <IconButton
                            size="small"
                            onClick={() => handleSignalAction(signal, 'watch')}
                          >
                            <Info />
                          </IconButton>
                        </Box>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}

          {/* Other tabs content */}
          {selectedTab === 1 && (
            <List>
              {signalGroups.watching.map((signal) => (
                <ListItem key={signal.id}>
                  <ListItemAvatar>
                    <Avatar sx={{ bgcolor: getSignalColor(signal) + '.main' }}>
                      {getSignalIcon(signal)}
                    </Avatar>
                  </ListItemAvatar>
                  <ListItemText
                    primary={`${signal.symbol} - ${signal.signal_type.toUpperCase()}`}
                    secondary={`Target: ${formatCurrency(signal.target_price)} | Strength: ${signal.strength}%`}
                  />
                  <Button
                    variant="outlined"
                    size="small"
                    onClick={() => handleSignalAction(signal, 'activate')}
                  >
                    Activate
                  </Button>
                </ListItem>
              ))}
            </List>
          )}
          
          {/* Similar layouts for executed and expired tabs */}
          {(selectedTab === 2 || selectedTab === 3) && (
            <Typography color="text.secondary" textAlign="center" py={4}>
              {selectedTab === 2 ? 'Executed signals history' : 'Expired signals history'}
            </Typography>
          )}
          
          {filteredSignals.length === 0 && !loading && (
            <Alert severity="info" sx={{ mt: 2 }}>
              No signals found matching your criteria. Try adjusting the filters or refreshing.
            </Alert>
          )}
        </CardContent>
      </Card>

      {/* Signal Details Dialog */}
      <Dialog 
        open={detailsOpen} 
        onClose={() => setDetailsOpen(false)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>
          {selectedSignal ? `${selectedSignal.symbol} Signal Details` : 'Signal Settings'}
        </DialogTitle>
        <DialogContent>
          {selectedSignal ? (
            <Grid container spacing={2}>
              <Grid item xs={12} md={6}>
                <Typography variant="h6" gutterBottom>Signal Information</Typography>
                <Typography>Type: {selectedSignal.signal_type}</Typography>
                <Typography>Strength: {selectedSignal.strength}%</Typography>
                <Typography>Confidence: {selectedSignal.confidence}%</Typography>
                <Typography>Risk Level: {selectedSignal.risk_level}/10</Typography>
              </Grid>
              <Grid item xs={12} md={6}>
                <Typography variant="h6" gutterBottom>Price Targets</Typography>
                <Typography>Current: {formatCurrency(selectedSignal.currentPrice)}</Typography>
                <Typography>Target: {formatCurrency(selectedSignal.target_price)}</Typography>
                <Typography>Stop Loss: {formatCurrency(selectedSignal.stop_loss)}</Typography>
              </Grid>
              <Grid item xs={12}>
                <Typography variant="h6" gutterBottom>Technical Analysis</Typography>
                <Typography>RSI: {selectedSignal.rsi_score}</Typography>
                <Typography>MACD: {selectedSignal.macd_score}</Typography>
                <Typography>Bollinger: {selectedSignal.bollinger_score}</Typography>
                <Typography>Pattern: {selectedSignal.pattern_match}</Typography>
              </Grid>
            </Grid>
          ) : (
            <Box>
              <Typography variant="h6" gutterBottom>Signal Settings</Typography>
              <Typography>Configure minimum confidence, risk levels, and alerts</Typography>
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDetailsOpen(false)}>Close</Button>
          {selectedSignal && (
            <Button 
              variant="contained"
              onClick={() => {
                handleSignalAction(selectedSignal, 'execute');
                setDetailsOpen(false);
              }}
            >
              Execute Signal
            </Button>
          )}
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default TradingSignals;