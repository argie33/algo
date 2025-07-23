import React, { useState, useEffect, useMemo } from 'react';
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
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
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
  Tooltip,
  Badge,
  LinearProgress,
  Divider,
  Switch,
  FormControlLabel,
  TablePagination,
  TableSortLabel,
  Avatar,
  Stack,
  List,
  ListItem,
  ListItemText,
  ListItemAvatar,
  Skeleton,
  alpha,
  Fade,
  Zoom,
  Collapse,
  ToggleButton,
  ToggleButtonGroup,
  Autocomplete
} from '@mui/material';
import {
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  LineChart,
  Line,
  Area,
  AreaChart,
  ScatterChart,
  Scatter,
  ComposedChart,
  Legend
} from 'recharts';
import {
  TrendingUp,
  TrendingDown,
  Analytics,
  Assessment,
  ShowChart,
  Timeline,
  Warning,
  CheckCircle,
  Info,
  Speed,
  Psychology,
  FilterList,
  Refresh,
  Download,
  Share,
  BookmarkBorder,
  Bookmark,
  Visibility,
  VisibilityOff,
  ExpandMore,
  Search,
  Clear,
  CompareArrows,
  ArrowUpward,
  ArrowDownward,
  Remove,
  NewReleases,
  History,
  SignalWifi4Bar,
  SignalWifi0Bar,
  FlashOn,
  Whatshot,
  Star,
  StarBorder,
  NotificationsActive,
  Schedule,
  CalendarToday,
  ViewList,
  ViewModule,
  PlayArrow,
  Pause
} from '@mui/icons-material';
import { api } from '../services/api';
import { formatPercentage, formatNumber, formatCurrency } from '../utils/formatters';
import ApiKeyStatusIndicator from '../components/ApiKeyStatusIndicator';

// CSS keyframes - replaced MUI keyframes with CSS
const pulseAnimation = 'pulse 2s ease-in-out infinite';
const pulseKeyframes = `
  @keyframes pulse {
    0% { opacity: 1; }
    50% { opacity: 0.7; }
    100% { opacity: 1; }
  }
`;

// Trading signal strength indicator
const SignalStrength = ({ strength, type = 'buy' }) => {
  const getStrengthColor = (value) => {
    if (value >= 0.8) return '#4caf50';
    if (value >= 0.6) return '#ff9800';
    if (value >= 0.4) return '#2196f3';
    return '#f44336';
  };

  const getStrengthLabel = (value) => {
    if (value >= 0.8) return 'Strong';
    if (value >= 0.6) return 'Moderate';
    if (value >= 0.4) return 'Weak';
    return 'Very Weak';
  };

  const bars = 5;
  const activeBars = Math.ceil(strength * bars);

  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
      <Box sx={{ display: 'flex', gap: 0.5 }}>
        {[...Array(bars)].map((_, index) => (
          <Box
            key={index}
            sx={{
              width: 4,
              height: 16 - (index * 2),
              backgroundColor: index < activeBars ? getStrengthColor(strength) : 'rgba(0, 0, 0, 0.26)',
              borderRadius: 1
            }}
          />
        ))}
      </Box>
      <Typography variant="caption" sx={{ color: getStrengthColor(strength), fontWeight: 600 }}>
        {getStrengthLabel(strength)}
      </Typography>
    </Box>
  );
};

// Signal type chip
const SignalTypeChip = ({ signal, strength, signalType }) => {
  const isPositive = signalType === 'buy' || (signal && parseFloat(signal) > 0);
  
  return (
    <Chip
      icon={isPositive ? <TrendingUp /> : <TrendingDown />}
      label={isPositive ? 'BUY' : 'SELL'}
      color={isPositive ? 'success' : 'error'}
      variant="filled"
      size="small"
      sx={{
        fontWeight: 700,
        fontSize: '0.75rem',
        '& .MuiChip-icon': {
          fontSize: '1rem'
        }
      }}
    />
  );
};

// Performance indicator
const PerformanceIndicator = ({ performance, status }) => {
  const getStatusColor = (status) => {
    switch (status) {
      case 'WINNING': return '#4caf50';
      case 'STOPPED': return '#f44336';
      case 'ACTIVE': return '#2196f3';
      default: return 'rgba(0, 0, 0, 0.6)';
    }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'WINNING': return <CheckCircle />;
      case 'STOPPED': return <Warning />;
      case 'ACTIVE': return <Timeline />;
      default: return <Info />;
    }
  };

  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
        {React.cloneElement(getStatusIcon(status), { 
          sx: { fontSize: '1rem', color: getStatusColor(status) } 
        })}
        <Typography 
          variant="body2" 
          sx={{ 
            color: getStatusColor(status),
            fontWeight: 600
          }}
        >
          {performance ? `${performance > 0 ? '+' : ''}${performance.toFixed(1)}%` : '0.0%'}
        </Typography>
      </Box>
      <Chip
        label={status}
        size="small"
        sx={{
          fontSize: '0.65rem',
          height: 20,
          backgroundColor: getStatusColor(status) + '1A',
          color: getStatusColor(status),
          border: `1px solid ${getStatusColor(status)}4D`
        }}
      />
    </Box>
  );
};

// Current period badge
const CurrentPeriodBadge = ({ isCurrentPeriod, daysSince }) => {
  if (!isCurrentPeriod) return null;
  
  return (
    <Chip
      icon={<NewReleases />}
      label={`${daysSince}d ago`}
      size="small"
      sx={{
        fontSize: '0.65rem',
        height: 20,
        backgroundColor: '#1976d21A',
        color: '#1976d2',
        border: '1px solid #1976d24D',
        animation: pulseAnimation
      }}
    />
  );
};

// Market cap chip
const MarketCapChip = ({ marketCap }) => {
  const getMarketCapCategory = (cap) => {
    if (!cap || cap === 0) return { label: 'N/A', color: 'default' };
    if (cap >= 200e9) return { label: 'Mega Cap', color: 'primary' };
    if (cap >= 10e9) return { label: 'Large Cap', color: 'secondary' };
    if (cap >= 2e9) return { label: 'Mid Cap', color: 'info' };
    if (cap >= 300e6) return { label: 'Small Cap', color: 'warning' };
    return { label: 'Micro Cap', color: 'error' };
  };

  const category = getMarketCapCategory(marketCap);
  
  return (
    <Chip
      label={category.label}
      color={category.color}
      variant="outlined"
      size="small"
      sx={{ fontSize: '0.7rem' }}
    />
  );
};

// Sector chip
const SectorChip = ({ sector }) => {
  const getSectorColor = (sectorName) => {
    const sectorColors = {
      'Technology': 'primary',
      'Healthcare': 'success',
      'Financial Services': 'info',
      'Consumer Discretionary': 'warning',
      'Communication Services': 'secondary',
      'Industrials': 'error',
      'Consumer Staples': 'default',
      'Energy': 'warning',
      'Utilities': 'info',
      'Real Estate': 'success',
      'Materials': 'error'
    };
    return sectorColors[sectorName] || 'default';
  };

  return (
    <Chip
      label={sector || 'Unknown'}
      color={getSectorColor(sector)}
      variant="outlined"
      size="small"
      sx={{ fontSize: '0.7rem' }}
    />
  );
};

function TabPanel({ children, value, index, ...other }) {
  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`signals-tabpanel-${index}`}
      aria-labelledby={`signals-tab-${index}`}
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

const TradingSignals = () => {
  // Inject CSS keyframes
  React.useEffect(() => {
    const style = document.createElement('style');
    style.textContent = pulseKeyframes;
    document.head.appendChild(style);
    return () => document.head.removeChild(style);
  }, []);

  const [activeTab, setActiveTab] = useState(0);
  const [timeframe, setTimeframe] = useState('daily');
  const [aggregateSignals, setAggregateSignals] = useState([]);
  const [signalType, setSignalType] = useState('all');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [buySignals, setBuySignals] = useState([]);
  const [sellSignals, setSellSignals] = useState([]);
  const [allSignals, setAllSignals] = useState([]);
  const [filteredSignals, setFilteredSignals] = useState([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [sortBy, setSortBy] = useState('date');
  const [sortOrder, setSortOrder] = useState('desc');
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);
  const [selectedSector, setSelectedSector] = useState('all');
  const [minSignalStrength, setMinSignalStrength] = useState(0);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [watchlist, setWatchlist] = useState(new Set());
  const [viewMode, setViewMode] = useState('table'); // 'table' or 'cards'
  const [analytics, setAnalytics] = useState({});
  const [showCurrentPeriodOnly, setShowCurrentPeriodOnly] = useState(true);

  // Load signals data with enhanced current period focus
  const loadSignals = async () => {
    setLoading(true);
    try {
      console.log(`📊 Loading signals for timeframe: ${timeframe}`);
      
      // Handle aggregate/summary view
      if (timeframe === 'summary') {
        const aggregateResponse = await api.get('/trading/aggregate?limit=100&min_confidence=50');
        const aggregateData = aggregateResponse.data?.data || [];
        
        // Process aggregate signals
        const processedAggregateSignals = aggregateData.map(signal => ({
          ...signal,
          signal_type: signal.aggregate_signal === 'Buy' ? 'buy' : signal.aggregate_signal === 'Sell' ? 'sell' : 'hold',
          signal_strength: signal.confidence / 100,
          timestamp: new Date(),
          is_aggregate: true,
          performance_percent: 0,
          signal_status: 'AGGREGATE'
        }));

        setAggregateSignals(processedAggregateSignals);
        setAllSignals(processedAggregateSignals);
        setFilteredSignals(processedAggregateSignals);
        
        const buySignals = processedAggregateSignals.filter(s => s.signal_type === 'buy');
        const sellSignals = processedAggregateSignals.filter(s => s.signal_type === 'sell');
        setBuySignals(buySignals);
        setSellSignals(sellSignals);
        
        console.log(`📊 Loaded ${processedAggregateSignals.length} aggregate signals`);
        setLoading(false);
        return;
      }
      
      // Load current period signals with analytics
      const [currentSignalsResponse, analyticsResponse] = await Promise.all([
        api.get(`/trading/signals/current/${timeframe}?limit=100&min_strength=0.3`),
        api.get(`/trading/analytics/${timeframe}`)
      ]);

      const currentSignalsData = currentSignalsResponse.data?.data || [];
      const analyticsData = analyticsResponse.data?.summary || {};

      // Process current period signals with enhanced data
      const processedSignals = currentSignalsData.map(signal => ({
        ...signal,
        signal_type: signal.signal === 'Buy' ? 'buy' : 'sell',
        signal_strength: signal.signal_strength || 0,
        timestamp: new Date(signal.date),
        market_cap_billions: (signal.market_cap || 0) / 1e9,
        is_current_period: true,
        performance_percent: signal.performance_percent || 0,
        days_since_signal: signal.days_since_signal || 0,
        signal_status: signal.signal_status || 'ACTIVE',
        entry_price: signal.entry_price || signal.buylevel,
        stop_loss: signal.stop_loss || signal.stoplevel,
        current_price: signal.current_price || signal.regular_market_price
      }));

      // Separate buy and sell signals
      const buySignals = processedSignals.filter(s => s.signal_type === 'buy');
      const sellSignals = processedSignals.filter(s => s.signal_type === 'sell');

      setBuySignals(buySignals);
      setSellSignals(sellSignals);
      setAllSignals(processedSignals);
      setFilteredSignals(processedSignals);

      // Store analytics for display
      setAnalytics(analyticsData);

      console.log(`📊 Loaded ${processedSignals.length} current period signals (${buySignals.length} buy, ${sellSignals.length} sell)`);
    } catch (error) {
      console.error('Error loading signals:', error);
      // Fallback to basic signals API
      try {
        const [buyResponse, sellResponse] = await Promise.all([
          api.get(`/signals/buy?timeframe=${timeframe}&limit=100`),
          api.get(`/signals/sell?timeframe=${timeframe}&limit=100`)
        ]);

        const buyData = buyResponse.data?.data || [];
        const sellData = sellResponse.data?.data || [];

        const processedBuyData = buyData.map(signal => ({
          ...signal,
          signal_type: 'buy',
          signal_strength: Math.abs(parseFloat(signal.signal) || 0) / 100,
          timestamp: new Date(signal.date),
          market_cap_billions: (signal.market_cap || 0) / 1e9,
          is_current_period: false
        }));

        const processedSellData = sellData.map(signal => ({
          ...signal,
          signal_type: 'sell',
          signal_strength: Math.abs(parseFloat(signal.signal) || 0) / 100,
          timestamp: new Date(signal.date),
          market_cap_billions: (signal.market_cap || 0) / 1e9,
          is_current_period: false
        }));

        setBuySignals(processedBuyData);
        setSellSignals(processedSellData);
        
        const combined = [...processedBuyData, ...processedSellData];
        setAllSignals(combined);
        setFilteredSignals(combined);
      } catch (fallbackError) {
        console.error('Fallback also failed:', fallbackError);
        setError(`Failed to load trading signals: ${fallbackError.message}`);
        // Set empty arrays instead of mock data
        setBuySignals([]);
        setSellSignals([]);
        setAllSignals([]);
        setFilteredSignals([]);
      }
    } finally {
      setLoading(false);
    }
  };


  // Load data on component mount and when timeframe changes
  useEffect(() => {
    loadSignals();
  }, [timeframe]);

  // Auto-refresh functionality
  useEffect(() => {
    let interval;
    if (autoRefresh) {
      interval = setInterval(loadSignals, 60000); // Refresh every minute
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [autoRefresh, timeframe]);

  // Filter and sort signals
  useEffect(() => {
    let filtered = [...allSignals];

    // Filter by signal type
    if (signalType !== 'all') {
      filtered = filtered.filter(signal => signal.signal_type === signalType);
    }

    // Filter by search term
    if (searchTerm) {
      const search = searchTerm.toLowerCase();
      filtered = filtered.filter(signal => 
        signal.symbol.toLowerCase().includes(search) ||
        signal.company_name.toLowerCase().includes(search) ||
        signal.sector.toLowerCase().includes(search)
      );
    }

    // Filter by sector
    if (selectedSector !== 'all') {
      filtered = filtered.filter(signal => signal.sector === selectedSector);
    }

    // Filter by signal strength
    filtered = filtered.filter(signal => signal.signal_strength >= minSignalStrength);

    // Sort signals
    filtered.sort((a, b) => {
      let aValue = a[sortBy];
      let bValue = b[sortBy];

      if (sortBy === 'date' || sortBy === 'timestamp') {
        aValue = new Date(aValue);
        bValue = new Date(bValue);
      } else if (typeof aValue === 'string') {
        aValue = aValue.toLowerCase();
        bValue = bValue.toLowerCase();
      }

      if (sortOrder === 'asc') {
        return aValue > bValue ? 1 : -1;
      } else {
        return aValue < bValue ? 1 : -1;
      }
    });

    setFilteredSignals(filtered);
    setPage(0); // Reset to first page when filters change
  }, [allSignals, signalType, searchTerm, selectedSector, minSignalStrength, sortBy, sortOrder]);

  // Get unique sectors for filter
  const uniqueSectors = useMemo(() => {
    const sectors = [...new Set(allSignals.map(signal => signal.sector))];
    return sectors.filter(Boolean);
  }, [allSignals]);

  // Pagination
  const paginatedSignals = useMemo(() => {
    const start = page * rowsPerPage;
    return filteredSignals.slice(start, start + rowsPerPage);
  }, [filteredSignals, page, rowsPerPage]);

  // Statistics with analytics integration
  const stats = useMemo(() => {
    if (analytics && Object.keys(analytics).length > 0) {
      // Use analytics data when available
      return {
        total: analytics.total_signals || 0,
        buy: analytics.buy_signals || 0,
        sell: analytics.sell_signals || 0,
        winning: analytics.winning_signals || 0,
        winRate: analytics.win_rate || 0,
        avgWinning: analytics.avg_winning_performance || 0,
        avgLosing: analytics.avg_losing_performance || 0,
        bestPerformance: analytics.best_performance || 0,
        worstPerformance: analytics.worst_performance || 0,
        sectors: analytics.sectors_covered || 0,
        uniqueSymbols: analytics.unique_symbols || 0,
        buyPercentage: analytics.total_signals ? (analytics.buy_signals / analytics.total_signals) * 100 : 0,
        sellPercentage: analytics.total_signals ? (analytics.sell_signals / analytics.total_signals) * 100 : 0
      };
    } else {
      // Fallback to calculated stats
      const totalSignals = allSignals.length;
      const buyCount = allSignals.filter(s => s.signal_type === 'buy').length;
      const sellCount = allSignals.filter(s => s.signal_type === 'sell').length;
      const strongSignals = allSignals.filter(s => s.signal_strength >= 0.7).length;
      const winningSignals = allSignals.filter(s => s.signal_status === 'WINNING').length;
      const avgStrength = allSignals.length ? allSignals.reduce((sum, s) => sum + s.signal_strength, 0) / allSignals.length : 0;

      return {
        total: totalSignals,
        buy: buyCount,
        sell: sellCount,
        strong: strongSignals,
        winning: winningSignals,
        winRate: totalSignals ? (winningSignals / totalSignals) * 100 : 0,
        avgStrength: avgStrength,
        buyPercentage: totalSignals ? (buyCount / totalSignals) * 100 : 0,
        sellPercentage: totalSignals ? (sellCount / totalSignals) * 100 : 0
      };
    }
  }, [allSignals, analytics]);

  // Watchlist functions
  const toggleWatchlist = (symbol) => {
    setWatchlist(prev => {
      const newWatchlist = new Set(prev);
      if (newWatchlist.has(symbol)) {
        newWatchlist.delete(symbol);
      } else {
        newWatchlist.add(symbol);
      }
      return newWatchlist;
    });
  };

  // Render enhanced statistics cards
  const renderStatsCards = () => (
    <Grid container spacing={3} sx={{ mb: 3 }}>
      <Grid item xs={12} sm={6} md={3}>
        <Card sx={{ 
          background: 'linear-gradient(135deg, #1976d21A 0%, #1976d233 100%)',
          border: '1px solid #1976d233'
        }}>
          <CardContent>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              <Avatar sx={{ bgcolor: '#1976d2' }}>
                <SignalWifi4Bar />
              </Avatar>
              <Box>
                <Typography variant="h4" fontWeight={700}>
                  {stats.total}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Active Signals
                </Typography>
                {stats.uniqueSymbols > 0 && (
                  <Typography variant="caption" color="text.secondary">
                    {stats.uniqueSymbols} symbols, {stats.sectors} sectors
                  </Typography>
                )}
              </Box>
            </Box>
          </CardContent>
        </Card>
      </Grid>

      <Grid item xs={12} sm={6} md={3}>
        <Card sx={{ 
          background: 'linear-gradient(135deg, #4caf501A 0%, #4caf5033 100%)',
          border: '1px solid #4caf5033'
        }}>
          <CardContent>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              <Avatar sx={{ bgcolor: '#4caf50' }}>
                <TrendingUp />
              </Avatar>
              <Box>
                <Typography variant="h4" fontWeight={700} color="success.main">
                  {stats.buy}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Buy Signals ({stats.buyPercentage.toFixed(1)}%)
                </Typography>
                {stats.avgWinning > 0 && (
                  <Typography variant="caption" color="success.main">
                    Avg Win: +{stats.avgWinning.toFixed(1)}%
                  </Typography>
                )}
              </Box>
            </Box>
          </CardContent>
        </Card>
      </Grid>

      <Grid item xs={12} sm={6} md={3}>
        <Card sx={{ 
          background: 'linear-gradient(135deg, #f443361A 0%, #f4433633 100%)',
          border: '1px solid #f4433633'
        }}>
          <CardContent>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              <Avatar sx={{ bgcolor: '#f44336' }}>
                <TrendingDown />
              </Avatar>
              <Box>
                <Typography variant="h4" fontWeight={700} color="error.main">
                  {stats.sell}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Sell Signals ({stats.sellPercentage.toFixed(1)}%)
                </Typography>
                {stats.avgLosing < 0 && (
                  <Typography variant="caption" color="error.main">
                    Avg Loss: {stats.avgLosing.toFixed(1)}%
                  </Typography>
                )}
              </Box>
            </Box>
          </CardContent>
        </Card>
      </Grid>

      <Grid item xs={12} sm={6} md={3}>
        <Card sx={{ 
          background: 'linear-gradient(135deg, #2196f31A 0%, #2196f333 100%)',
          border: '1px solid #2196f333'
        }}>
          <CardContent>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              <Avatar sx={{ bgcolor: '#2196f3' }}>
                <CheckCircle />
              </Avatar>
              <Box>
                <Typography variant="h4" fontWeight={700} color="info.main">
                  {stats.winning || stats.strong}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {stats.winning ? 'Winning' : 'Strong'} Signals
                </Typography>
                {stats.winRate > 0 && (
                  <Typography variant="caption" color="info.main">
                    Win Rate: {stats.winRate.toFixed(1)}%
                  </Typography>
                )}
              </Box>
            </Box>
          </CardContent>
        </Card>
      </Grid>
    </Grid>
  );

  // Render filters
  const renderFilters = () => (
    <Card sx={{ mb: 3 }}>
      <CardContent>
        <Grid container spacing={3} alignItems="center">
          <Grid item xs={12} md={3}>
            <TextField
              fullWidth
              variant="outlined"
              placeholder="Search symbols, companies..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              InputProps={{
                startAdornment: <Search sx={{ mr: 1, color: 'action.active' }} />,
                endAdornment: searchTerm && (
                  <IconButton onClick={() => setSearchTerm('')} size="small">
                    <Clear />
                  </IconButton>
                )
              }}
            />
          </Grid>

          <Grid item xs={12} md={2}>
            <FormControl fullWidth>
              <InputLabel>Timeframe</InputLabel>
              <Select
                value={timeframe}
                label="Timeframe"
                onChange={(e) => setTimeframe(e.target.value)}
              >
                <MenuItem value="daily">Daily</MenuItem>
                <MenuItem value="weekly">Weekly</MenuItem>
                <MenuItem value="monthly">Monthly</MenuItem>
                <MenuItem value="summary">
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <Analytics sx={{ fontSize: '1rem' }} />
                    Summary
                  </Box>
                </MenuItem>
              </Select>
            </FormControl>
          </Grid>

          <Grid item xs={12} md={2}>
            <FormControl fullWidth>
              <InputLabel>Signal Type</InputLabel>
              <Select
                value={signalType}
                label="Signal Type"
                onChange={(e) => setSignalType(e.target.value)}
              >
                <MenuItem value="all">All Signals</MenuItem>
                <MenuItem value="buy">Buy Only</MenuItem>
                <MenuItem value="sell">Sell Only</MenuItem>
              </Select>
            </FormControl>
          </Grid>

          <Grid item xs={12} md={2}>
            <FormControl fullWidth>
              <InputLabel>Sector</InputLabel>
              <Select
                value={selectedSector}
                label="Sector"
                onChange={(e) => setSelectedSector(e.target.value)}
              >
                <MenuItem value="all">All Sectors</MenuItem>
                {uniqueSectors.map(sector => (
                  <MenuItem key={sector} value={sector}>{sector}</MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>

          <Grid item xs={12} md={3}>
            <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
              <ToggleButtonGroup
                value={viewMode}
                exclusive
                onChange={(e, value) => value && setViewMode(value)}
                size="small"
              >
                <ToggleButton value="table">
                  <ViewList />
                </ToggleButton>
                <ToggleButton value="cards">
                  <ViewModule />
                </ToggleButton>
              </ToggleButtonGroup>

              <FormControlLabel
                control={
                  <Switch 
                    checked={autoRefresh} 
                    onChange={(e) => setAutoRefresh(e.target.checked)}
                    size="small"
                  />
                }
                label="Auto"
              />

              <IconButton onClick={loadSignals} disabled={loading}>
                <Refresh />
              </IconButton>
            </Box>
          </Grid>
        </Grid>
      </CardContent>
    </Card>
  );

  // Render table view
  const renderTableView = () => (
    <Card>
      <CardContent>
        <TableContainer>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>
                  <TableSortLabel
                    active={sortBy === 'symbol'}
                    direction={sortBy === 'symbol' ? sortOrder : 'asc'}
                    onClick={() => {
                      setSortBy('symbol');
                      setSortOrder(sortBy === 'symbol' && sortOrder === 'asc' ? 'desc' : 'asc');
                    }}
                  >
                    Stock
                  </TableSortLabel>
                </TableCell>
                <TableCell>Signal</TableCell>
                {timeframe === 'summary' && <TableCell>Confidence</TableCell>}
                <TableCell>Performance</TableCell>
                <TableCell>Strength</TableCell>
                {timeframe === 'summary' && <TableCell>Recommendation</TableCell>}
                <TableCell>
                  <TableSortLabel
                    active={sortBy === 'date'}
                    direction={sortBy === 'date' ? sortOrder : 'asc'}
                    onClick={() => {
                      setSortBy('date');
                      setSortOrder(sortBy === 'date' && sortOrder === 'asc' ? 'desc' : 'asc');
                    }}
                  >
                    Date
                  </TableSortLabel>
                </TableCell>
                <TableCell>Entry/Current</TableCell>
                <TableCell>Market Cap</TableCell>
                <TableCell>P/E</TableCell>
                <TableCell>Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {loading ? (
                [...Array(5)].map((_, index) => (
                  <TableRow key={index}>
                    {[...Array(timeframe === 'summary' ? 11 : 9)].map((_, cellIndex) => (
                      <TableCell key={cellIndex}>
                        <Skeleton animation="wave" />
                      </TableCell>
                    ))}
                  </TableRow>
                ))
              ) : (
                paginatedSignals.map((signal, index) => (
                  <TableRow 
                    key={`${signal.symbol}-${signal.date}-${index}`} 
                    hover
                    sx={{
                      backgroundColor: signal.is_aggregate 
                        ? '#9c27b014'
                        : signal.is_current_period 
                          ? '#1976d20D' 
                          : 'inherit',
                      borderLeft: signal.is_aggregate 
                        ? '4px solid #9c27b0'
                        : signal.is_current_period 
                          ? '4px solid #1976d2' 
                          : 'none'
                    }}
                  >
                    <TableCell>
                      <Box>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                          <Typography variant="subtitle2" fontWeight={600}>
                            {signal.symbol}
                          </Typography>
                          <CurrentPeriodBadge 
                            isCurrentPeriod={signal.is_current_period} 
                            daysSince={signal.days_since_signal} 
                          />
                        </Box>
                        <Typography variant="caption" color="text.secondary">
                          {signal.company_name}
                        </Typography>
                        <Box sx={{ mt: 0.5 }}>
                          <SectorChip sector={signal.sector} />
                        </Box>
                      </Box>
                    </TableCell>
                    <TableCell>
                      <SignalTypeChip 
                        signal={signal.signal} 
                        strength={signal.signal_strength} 
                        signalType={signal.signal_type}
                      />
                    </TableCell>
                    {timeframe === 'summary' && (
                      <TableCell>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                          <Typography variant="body2" fontWeight={600}>
                            {Math.round(signal.confidence || 0)}%
                          </Typography>
                          <LinearProgress 
                            variant="determinate" 
                            value={signal.confidence || 0} 
                            sx={{ width: 60, height: 6, borderRadius: 3 }}
                            color={signal.confidence >= 70 ? 'success' : signal.confidence >= 50 ? 'warning' : 'error'}
                          />
                        </Box>
                      </TableCell>
                    )}
                    <TableCell>
                      <PerformanceIndicator 
                        performance={signal.performance_percent} 
                        status={signal.signal_status} 
                      />
                    </TableCell>
                    <TableCell>
                      <SignalStrength strength={signal.signal_strength} type={signal.signal_type} />
                    </TableCell>
                    {timeframe === 'summary' && (
                      <TableCell>
                        <Typography variant="body2" sx={{ maxWidth: 200 }}>
                          {signal.recommendation || 'No recommendation'}
                        </Typography>
                      </TableCell>
                    )}
                    <TableCell>
                      <Typography variant="body2">
                        {new Date(signal.date).toLocaleDateString()}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {new Date(signal.date).toLocaleDateString('en-US', { weekday: 'short' })}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Box>
                        <Typography variant="caption" color="text.secondary">
                          Entry: {formatCurrency(signal.entry_price || signal.current_price)}
                        </Typography>
                        <Typography variant="subtitle2">
                          Current: {formatCurrency(signal.current_price)}
                        </Typography>
                        {signal.stop_loss && (
                          <Typography variant="caption" color="error.main">
                            Stop: {formatCurrency(signal.stop_loss)}
                          </Typography>
                        )}
                      </Box>
                    </TableCell>
                    <TableCell>
                      <Box>
                        <Typography variant="body2">
                          {formatCurrency(signal.market_cap, { notation: 'compact' })}
                        </Typography>
                        <MarketCapChip marketCap={signal.market_cap} />
                      </Box>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2">
                        {signal.trailing_pe ? signal.trailing_pe.toFixed(1) : 'N/A'}
                      </Typography>
                      {signal.beta && (
                        <Typography variant="caption" color="text.secondary" display="block">
                          β: {signal.beta.toFixed(2)}
                        </Typography>
                      )}
                    </TableCell>
                    <TableCell>
                      <IconButton
                        onClick={() => toggleWatchlist(signal.symbol)}
                        size="small"
                        color={watchlist.has(signal.symbol) ? 'primary' : 'default'}
                      >
                        {watchlist.has(signal.symbol) ? <Bookmark /> : <BookmarkBorder />}
                      </IconButton>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </TableContainer>

        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mt: 2 }}>
          <Typography variant="body2" color="text.secondary">
            Showing {Math.min(page * rowsPerPage + 1, filteredSignals.length)} - {Math.min((page + 1) * rowsPerPage, filteredSignals.length)} of {filteredSignals.length} signals
          </Typography>
          <TablePagination
            component="div"
            count={filteredSignals.length}
            page={page}
            onPageChange={(e, newPage) => setPage(newPage)}
            rowsPerPage={rowsPerPage}
            onRowsPerPageChange={(e) => {
              setRowsPerPage(parseInt(e.target.value, 10));
              setPage(0);
            }}
            rowsPerPageOptions={[10, 25, 50, 100]}
          />
        </Box>
      </CardContent>
    </Card>
  );

  // Render card view
  const renderCardView = () => (
    <Grid container spacing={3}>
      {loading ? (
        [...Array(6)].map((_, index) => (
          <Grid item xs={12} sm={6} md={4} key={index}>
            <Card>
              <CardContent>
                <Skeleton variant="text" width="60%" height={32} />
                <Skeleton variant="text" width="40%" height={24} />
                <Skeleton variant="rectangular" width="100%" height={60} sx={{ mt: 1 }} />
                <Box sx={{ display: 'flex', gap: 1, mt: 2 }}>
                  <Skeleton variant="rounded" width={80} height={24} />
                  <Skeleton variant="rounded" width={60} height={24} />
                </Box>
              </CardContent>
            </Card>
          </Grid>
        ))
      ) : (
        paginatedSignals.map((signal, index) => (
          <Grid item xs={12} sm={6} md={4} key={`${signal.symbol}-${signal.date}-${index}`}>
            <Card sx={{ 
              height: '100%',
              transition: 'all 0.3s ease',
              '&:hover': { 
                transform: 'translateY(-4px)',
                boxShadow: '0px 12px 17px 2px rgba(0,0,0,0.14), 0px 5px 22px 4px rgba(0,0,0,0.12), 0px 7px 8px -4px rgba(0,0,0,0.2)'
              }
            }}>
              <CardHeader
                avatar={
                  <Avatar sx={{ 
                    bgcolor: signal.signal_type === 'buy' ? '#4caf50' : '#f44336',
                    color: 'white'
                  }}>
                    {signal.signal_type === 'buy' ? <TrendingUp /> : <TrendingDown />}
                  </Avatar>
                }
                action={
                  <IconButton
                    onClick={() => toggleWatchlist(signal.symbol)}
                    size="small"
                    color={watchlist.has(signal.symbol) ? 'primary' : 'default'}
                  >
                    {watchlist.has(signal.symbol) ? <Bookmark /> : <BookmarkBorder />}
                  </IconButton>
                }
                title={
                  <Typography variant="h6" fontWeight={600}>
                    {signal.symbol}
                  </Typography>
                }
                subheader={
                  <Typography variant="body2" color="text.secondary">
                    {signal.company_name}
                  </Typography>
                }
              />
              <CardContent>
                <Box sx={{ mb: 2 }}>
                  <SignalTypeChip signal={signal.signal} strength={signal.signal_strength} />
                  <Box sx={{ mt: 1 }}>
                    <SignalStrength strength={signal.signal_strength} type={signal.signal_type} />
                  </Box>
                </Box>

                <Divider sx={{ my: 2 }} />

                <Grid container spacing={2}>
                  <Grid item xs={6}>
                    <Typography variant="caption" color="text.secondary">
                      Price
                    </Typography>
                    <Typography variant="subtitle2">
                      {formatCurrency(signal.current_price)}
                    </Typography>
                  </Grid>
                  <Grid item xs={6}>
                    <Typography variant="caption" color="text.secondary">
                      P/E Ratio
                    </Typography>
                    <Typography variant="subtitle2">
                      {signal.trailing_pe ? signal.trailing_pe.toFixed(1) : 'N/A'}
                    </Typography>
                  </Grid>
                  <Grid item xs={6}>
                    <Typography variant="caption" color="text.secondary">
                      Market Cap
                    </Typography>
                    <Typography variant="subtitle2">
                      {formatCurrency(signal.market_cap, { notation: 'compact' })}
                    </Typography>
                  </Grid>
                  <Grid item xs={6}>
                    <Typography variant="caption" color="text.secondary">
                      Dividend
                    </Typography>
                    <Typography variant="subtitle2">
                      {signal.dividend_yield ? formatPercentage(signal.dividend_yield / 100) : 'N/A'}
                    </Typography>
                  </Grid>
                </Grid>

                <Box sx={{ mt: 2, display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                  <SectorChip sector={signal.sector} />
                  <MarketCapChip marketCap={signal.market_cap} />
                </Box>

                <Box sx={{ mt: 2 }}>
                  <Typography variant="caption" color="text.secondary">
                    Signal Date: {new Date(signal.date).toLocaleDateString()}
                  </Typography>
                </Box>
              </CardContent>
            </Card>
          </Grid>
        ))
      )}
    </Grid>
  );

  return (
    <Container maxWidth="xl">
      {/* API Key Status */}
      <Box sx={{ mb: 3 }}>
        <ApiKeyStatusIndicator 
          showSetupDialog={true}
          onStatusChange={(status) => {
            console.log('Trading Signals - API Key Status:', status);
          }}
        />
      </Box>

      <Box sx={{ mb: 4 }}>
        <Typography variant="h3" fontWeight={700} gutterBottom>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            {timeframe === 'summary' ? (
              <Analytics sx={{ fontSize: '2.5rem', color: 'secondary.main' }} />
            ) : (
              <FlashOn sx={{ fontSize: '2.5rem', color: 'primary.main' }} />
            )}
            {timeframe === 'summary' ? 'Aggregate Signal Summary' : 'Trading Signals'}
          </Box>
        </Typography>
        <Typography variant="h6" color="text.secondary" paragraph>
          {timeframe === 'summary' 
            ? 'Cross-timeframe aggregate signals with confidence scoring and recommendations'
            : 'Current period active signals with real-time performance tracking and technical analysis'
          }
        </Typography>
        
        <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap', mb: 3 }}>
          {timeframe === 'summary' ? (
            <>
              <Chip
                icon={<Analytics />}
                label="Multi-Timeframe Analysis"
                color="secondary"
                variant="filled"
              />
              <Chip
                icon={<CompareArrows />}
                label="Cross-Signal Validation"
                color="info"
                variant="outlined"
              />
              <Chip
                icon={<Psychology />}
                label="Confidence Scoring"
                variant="outlined"
              />
              <Chip
                icon={<Assessment />}
                label="Smart Recommendations"
                variant="outlined"
              />
            </>
          ) : (
            <>
              <Chip
                icon={<NewReleases />}
                label="Current Period Focus"
                color="primary"
                variant="filled"
              />
              <Chip
                icon={<Timeline />}
                label="Performance Tracking"
                color="success"
                variant="outlined"
              />
              <Chip
                icon={<Schedule />}
                label={timeframe === 'daily' ? 'Last 30 Days' : 
                       timeframe === 'weekly' ? 'Last 12 Weeks' : 'Last 6 Months'}
                variant="outlined"
              />
              <Chip
                icon={<Analytics />}
                label="Technical Analysis"
                variant="outlined"
              />
              {stats.winRate > 0 && (
                <Chip
                  icon={<CheckCircle />}
                  label={`${stats.winRate.toFixed(1)}% Win Rate`}
                  color="info"
                  variant="outlined"
                />
              )}
            </>
          )}
        </Box>
      </Box>

      {renderStatsCards()}
      {renderFilters()}
      
      {filteredSignals.length === 0 && !loading ? (
        <Alert severity="info" sx={{ mb: 3 }}>
          No signals found matching your criteria. Try adjusting your filters.
        </Alert>
      ) : null}

      {viewMode === 'table' ? renderTableView() : renderCardView()}
    </Container>
  );
};

export default TradingSignals;