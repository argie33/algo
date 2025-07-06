import React, { useState, useEffect } from 'react';
import {
  Box,
  Container,
  Typography,
  Grid,
  Card,
  CardContent,
  CardHeader,
  Tabs,
  Tab,
  Chip,
  CircularProgress,
  Alert,
  Button,
  TextField,
  IconButton,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Divider,
  Stack,
  Paper,
  ToggleButton,
  ToggleButtonGroup,
  useTheme,
  alpha
} from '@mui/material';
import {
  TrendingUp,
  TrendingDown,
  Analytics,
  ShowChart,
  FilterList,
  Refresh,
  ViewModule,
  ViewList,
  Search,
  Clear,
  Assessment,
  AccountBalance
} from '@mui/icons-material';
import { api } from '../utils/api';
import MarketTimingPanel from '../components/trading/MarketTimingPanel';
import PositionManager from '../components/trading/PositionManager';
import SignalCardEnhanced from '../components/trading/SignalCardEnhanced';
import ExitZoneVisualizer from '../components/trading/ExitZoneVisualizer';

function TabPanel({ children, value, index, ...other }) {
  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`trading-tabpanel-${index}`}
      aria-labelledby={`trading-tab-${index}`}
      {...other}
    >
      {value === index && (
        <Box sx={{ py: 3 }}>
          {children}
        </Box>
      )}
    </div>
  );
}

const TradingSignalsEnhanced = () => {
  const theme = useTheme();
  const [activeTab, setActiveTab] = useState(0);
  const [loading, setLoading] = useState(false);
  const [signals, setSignals] = useState([]);
  const [positions, setPositions] = useState([]);
  const [marketData, setMarketData] = useState({});
  const [filters, setFilters] = useState({
    signalType: 'all',
    minStrength: 60,
    sector: 'all',
    inBuyZone: false,
    searchTerm: ''
  });
  const [viewMode, setViewMode] = useState('cards');
  const [watchlist, setWatchlist] = useState(new Set());

  // Load trading signals with enhanced O'Neill methodology
  const loadSignals = async () => {
    setLoading(true);
    try {
      const response = await api.get('/trading/signals/enhanced');
      const signalsData = response.data?.signals || [];
      
      // Process signals to include O'Neill specific fields
      const processedSignals = signalsData.map(signal => ({
        ...signal,
        pivot_price: signal.pivot_price || signal.entry_price,
        buy_zone_start: signal.pivot_price || signal.entry_price,
        buy_zone_end: (signal.pivot_price || signal.entry_price) * 1.05,
        exit_zone_1_price: (signal.entry_price || signal.pivot_price) * 1.20,
        exit_zone_2_price: (signal.entry_price || signal.pivot_price) * 1.25,
        initial_stop: (signal.entry_price || signal.pivot_price) * 0.93,
        volume_surge_pct: ((signal.volume / signal.avg_volume_50d) - 1) * 100,
        is_in_buy_zone: signal.current_price >= signal.pivot_price && 
                       signal.current_price <= signal.pivot_price * 1.05
      }));
      
      setSignals(processedSignals);
    } catch (error) {
      console.error('Error loading signals:', error);
    } finally {
      setLoading(false);
    }
  };

  // Load active positions
  const loadPositions = async () => {
    try {
      const response = await api.get('/trading/positions/active');
      setPositions(response.data?.positions || []);
    } catch (error) {
      console.error('Error loading positions:', error);
    }
  };

  // Load market timing data
  const loadMarketData = async () => {
    try {
      const response = await api.get('/trading/market-timing');
      setMarketData(response.data || {});
    } catch (error) {
      console.error('Error loading market data:', error);
    }
  };

  useEffect(() => {
    loadSignals();
    loadPositions();
    loadMarketData();
  }, []);

  // Filter signals based on criteria
  const filteredSignals = signals.filter(signal => {
    if (filters.signalType !== 'all' && signal.signal !== filters.signalType) return false;
    if (signal.signal_strength * 100 < filters.minStrength) return false;
    if (filters.sector !== 'all' && signal.sector !== filters.sector) return false;
    if (filters.inBuyZone && !signal.is_in_buy_zone) return false;
    if (filters.searchTerm && !signal.symbol.toLowerCase().includes(filters.searchTerm.toLowerCase()) &&
        !signal.company_name?.toLowerCase().includes(filters.searchTerm.toLowerCase())) return false;
    return true;
  });

  const buySignals = filteredSignals.filter(s => s.signal === 'Buy');
  const sellSignals = filteredSignals.filter(s => s.signal === 'Sell');

  const handleUpdatePosition = (positionData) => {
    // Handle position updates
    console.log('Updating position:', positionData);
  };

  const handleClosePosition = (exitData) => {
    // Handle position closure
    console.log('Closing position:', exitData);
  };

  const handleTrade = (signal) => {
    // Handle trade execution
    console.log('Executing trade:', signal);
  };

  const toggleWatchlist = (symbol) => {
    const newWatchlist = new Set(watchlist);
    if (newWatchlist.has(symbol)) {
      newWatchlist.delete(symbol);
    } else {
      newWatchlist.add(symbol);
    }
    setWatchlist(newWatchlist);
  };

  return (
    <Container maxWidth="xl" sx={{ mt: 4, mb: 4 }}>
      {/* Header */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h4" gutterBottom fontWeight={700}>
          Swing Trading Signals
        </Typography>
        <Typography variant="body1" color="text.secondary">
          Professional swing trading using William O'Neill's proven methodology
        </Typography>
      </Box>

      {/* Market Timing Panel - Always visible */}
      <Box sx={{ mb: 3 }}>
        <MarketTimingPanel marketData={marketData} />
      </Box>

      {/* Main Tabs */}
      <Card>
        <CardHeader
          title={
            <Tabs value={activeTab} onChange={(e, v) => setActiveTab(v)}>
              <Tab label="Trading Signals" icon={<ShowChart />} iconPosition="start" />
              <Tab label="Active Positions" icon={<AccountBalance />} iconPosition="start" />
              <Tab label="Analytics" icon={<Assessment />} iconPosition="start" />
            </Tabs>
          }
          action={
            <Stack direction="row" spacing={1}>
              <ToggleButtonGroup
                value={viewMode}
                exclusive
                onChange={(e, v) => v && setViewMode(v)}
                size="small"
              >
                <ToggleButton value="cards">
                  <ViewModule />
                </ToggleButton>
                <ToggleButton value="table">
                  <ViewList />
                </ToggleButton>
              </ToggleButtonGroup>
              <Button
                startIcon={<Refresh />}
                onClick={() => {
                  loadSignals();
                  loadPositions();
                  loadMarketData();
                }}
              >
                Refresh
              </Button>
            </Stack>
          }
        />
        <Divider />
        
        {/* Trading Signals Tab */}
        <TabPanel value={activeTab} index={0}>
          {/* Filters */}
          <Paper sx={{ p: 2, mb: 3 }}>
            <Grid container spacing={2} alignItems="center">
              <Grid item xs={12} md={3}>
                <TextField
                  fullWidth
                  size="small"
                  placeholder="Search symbols..."
                  value={filters.searchTerm}
                  onChange={(e) => setFilters({ ...filters, searchTerm: e.target.value })}
                  InputProps={{
                    startAdornment: <Search sx={{ mr: 1, color: 'text.secondary' }} />,
                    endAdornment: filters.searchTerm && (
                      <IconButton size="small" onClick={() => setFilters({ ...filters, searchTerm: '' })}>
                        <Clear />
                      </IconButton>
                    )
                  }}
                />
              </Grid>
              <Grid item xs={12} md={2}>
                <FormControl fullWidth size="small">
                  <InputLabel>Signal Type</InputLabel>
                  <Select
                    value={filters.signalType}
                    onChange={(e) => setFilters({ ...filters, signalType: e.target.value })}
                    label="Signal Type"
                  >
                    <MenuItem value="all">All Signals</MenuItem>
                    <MenuItem value="Buy">Buy Only</MenuItem>
                    <MenuItem value="Sell">Sell Only</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
              <Grid item xs={12} md={2}>
                <FormControl fullWidth size="small">
                  <InputLabel>Min Strength</InputLabel>
                  <Select
                    value={filters.minStrength}
                    onChange={(e) => setFilters({ ...filters, minStrength: e.target.value })}
                    label="Min Strength"
                  >
                    <MenuItem value={0}>All</MenuItem>
                    <MenuItem value={60}>60%+</MenuItem>
                    <MenuItem value={70}>70%+</MenuItem>
                    <MenuItem value={80}>80%+</MenuItem>
                    <MenuItem value={90}>90%+</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
              <Grid item xs={12} md={2}>
                <FormControl fullWidth size="small">
                  <InputLabel>Sector</InputLabel>
                  <Select
                    value={filters.sector}
                    onChange={(e) => setFilters({ ...filters, sector: e.target.value })}
                    label="Sector"
                  >
                    <MenuItem value="all">All Sectors</MenuItem>
                    <MenuItem value="Technology">Technology</MenuItem>
                    <MenuItem value="Healthcare">Healthcare</MenuItem>
                    <MenuItem value="Financial">Financial</MenuItem>
                    <MenuItem value="Consumer">Consumer</MenuItem>
                    <MenuItem value="Industrial">Industrial</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
              <Grid item xs={12} md={3}>
                <Button
                  fullWidth
                  variant={filters.inBuyZone ? 'contained' : 'outlined'}
                  onClick={() => setFilters({ ...filters, inBuyZone: !filters.inBuyZone })}
                  startIcon={<FilterList />}
                >
                  In Buy Zone Only
                </Button>
              </Grid>
            </Grid>
          </Paper>

          {/* Signal Statistics */}
          <Grid container spacing={2} sx={{ mb: 3 }}>
            <Grid item xs={12} sm={4}>
              <Paper sx={{ p: 2, textAlign: 'center' }}>
                <Typography variant="h4" fontWeight={700} color="success.main">
                  {buySignals.length}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Buy Signals
                </Typography>
              </Paper>
            </Grid>
            <Grid item xs={12} sm={4}>
              <Paper sx={{ p: 2, textAlign: 'center' }}>
                <Typography variant="h4" fontWeight={700} color="error.main">
                  {sellSignals.length}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Sell Signals
                </Typography>
              </Paper>
            </Grid>
            <Grid item xs={12} sm={4}>
              <Paper sx={{ p: 2, textAlign: 'center' }}>
                <Typography variant="h4" fontWeight={700} color="primary.main">
                  {buySignals.filter(s => s.is_in_buy_zone).length}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  In Buy Zone
                </Typography>
              </Paper>
            </Grid>
          </Grid>

          {/* Signals Display */}
          {loading ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
              <CircularProgress />
            </Box>
          ) : filteredSignals.length === 0 ? (
            <Alert severity="info">
              No signals match your current filters. Try adjusting the criteria.
            </Alert>
          ) : (
            <Grid container spacing={3}>
              {viewMode === 'cards' ? (
                filteredSignals.map((signal, index) => (
                  <Grid item xs={12} md={6} lg={4} key={`${signal.symbol}-${index}`}>
                    <SignalCardEnhanced
                      signal={signal}
                      onBookmark={toggleWatchlist}
                      isBookmarked={watchlist.has(signal.symbol)}
                      onTrade={handleTrade}
                    />
                  </Grid>
                ))
              ) : (
                <Grid item xs={12}>
                  {/* Table view implementation would go here */}
                  <Alert severity="info">Table view coming soon</Alert>
                </Grid>
              )}
            </Grid>
          )}
        </TabPanel>

        {/* Active Positions Tab */}
        <TabPanel value={activeTab} index={1}>
          <PositionManager
            positions={positions}
            onUpdatePosition={handleUpdatePosition}
            onClosePosition={handleClosePosition}
          />
        </TabPanel>

        {/* Analytics Tab */}
        <TabPanel value={activeTab} index={2}>
          <Grid container spacing={3}>
            <Grid item xs={12}>
              <Alert severity="info">
                Advanced analytics and backtesting coming soon. This will include:
                <ul>
                  <li>Win rate analysis by signal type and quality</li>
                  <li>Exit zone effectiveness metrics</li>
                  <li>Sector rotation analysis</li>
                  <li>Historical performance by market conditions</li>
                </ul>
              </Alert>
            </Grid>
          </Grid>
        </TabPanel>
      </Card>
    </Container>
  );
};

export default TradingSignalsEnhanced;