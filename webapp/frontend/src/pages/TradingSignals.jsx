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
  useTheme,
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

// Trading signal strength indicator
const SignalStrength = ({ strength, type = 'buy' }) => {
  const theme = useTheme();
  const getStrengthColor = (value) => {
    if (value >= 0.8) return theme.palette.success.main;
    if (value >= 0.6) return theme.palette.warning.main;
    if (value >= 0.4) return theme.palette.info.main;
    return theme.palette.error.main;
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
              backgroundColor: index < activeBars ? getStrengthColor(strength) : alpha(theme.palette.action.disabled, 0.3),
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
const SignalTypeChip = ({ signal, strength }) => {
  const theme = useTheme();
  const isPositive = parseFloat(signal) > 0;
  
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
  const theme = useTheme();
  const [activeTab, setActiveTab] = useState(0);
  const [timeframe, setTimeframe] = useState('daily');
  const [signalType, setSignalType] = useState('all');
  const [loading, setLoading] = useState(false);
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

  // Load signals data
  const loadSignals = async () => {
    setLoading(true);
    try {
      console.log(`📊 Loading signals for timeframe: ${timeframe}`);
      
      // Load both buy and sell signals
      const [buyResponse, sellResponse] = await Promise.all([
        api.get(`/signals/buy?timeframe=${timeframe}&limit=100`),
        api.get(`/signals/sell?timeframe=${timeframe}&limit=100`)
      ]);

      const buyData = buyResponse.data?.data || [];
      const sellData = sellResponse.data?.data || [];

      // Add signal type and strength to the data
      const processedBuyData = buyData.map(signal => ({
        ...signal,
        signal_type: 'buy',
        signal_strength: Math.abs(parseFloat(signal.signal) || 0) / 100, // Normalize to 0-1
        timestamp: new Date(signal.date),
        market_cap_billions: (signal.market_cap || 0) / 1e9
      }));

      const processedSellData = sellData.map(signal => ({
        ...signal,
        signal_type: 'sell',
        signal_strength: Math.abs(parseFloat(signal.signal) || 0) / 100, // Normalize to 0-1
        timestamp: new Date(signal.date),
        market_cap_billions: (signal.market_cap || 0) / 1e9
      }));

      setBuySignals(processedBuyData);
      setSellSignals(processedSellData);
      
      // Combine all signals
      const combined = [...processedBuyData, ...processedSellData];
      setAllSignals(combined);
      setFilteredSignals(combined);

      console.log(`📊 Loaded ${buyData.length} buy signals and ${sellData.length} sell signals`);
    } catch (error) {
      console.error('Error loading signals:', error);
      // Use mock data for development
      const mockSignals = generateMockSignals();
      setBuySignals(mockSignals.filter(s => s.signal_type === 'buy'));
      setSellSignals(mockSignals.filter(s => s.signal_type === 'sell'));
      setAllSignals(mockSignals);
      setFilteredSignals(mockSignals);
    } finally {
      setLoading(false);
    }
  };

  // Generate mock signals for development
  const generateMockSignals = () => {
    const symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA', 'JPM', 'V', 'JNJ'];
    const sectors = ['Technology', 'Healthcare', 'Financial Services', 'Consumer Discretionary'];
    const companies = {
      'AAPL': 'Apple Inc.',
      'MSFT': 'Microsoft Corporation',
      'GOOGL': 'Alphabet Inc.',
      'AMZN': 'Amazon.com Inc.',
      'NVDA': 'NVIDIA Corporation',
      'META': 'Meta Platforms Inc.',
      'TSLA': 'Tesla Inc.',
      'JPM': 'JPMorgan Chase & Co.',
      'V': 'Visa Inc.',
      'JNJ': 'Johnson & Johnson'
    };

    return symbols.map((symbol, index) => ({
      symbol,
      company_name: companies[symbol],
      sector: sectors[index % sectors.length],
      signal: (Math.random() - 0.5) * 100, // Random signal between -50 and 50
      signal_type: Math.random() > 0.5 ? 'buy' : 'sell',
      signal_strength: Math.random() * 0.8 + 0.2, // Random strength 0.2-1.0
      date: new Date(Date.now() - Math.random() * 7 * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
      timestamp: new Date(Date.now() - Math.random() * 7 * 24 * 60 * 60 * 1000),
      current_price: Math.random() * 300 + 50,
      market_cap: Math.random() * 2000e9 + 10e9,
      market_cap_billions: (Math.random() * 2000 + 10),
      trailing_pe: Math.random() * 30 + 10,
      dividend_yield: Math.random() * 5
    }));
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

  // Statistics
  const stats = useMemo(() => {
    const totalSignals = allSignals.length;
    const buyCount = allSignals.filter(s => s.signal_type === 'buy').length;
    const sellCount = allSignals.filter(s => s.signal_type === 'sell').length;
    const strongSignals = allSignals.filter(s => s.signal_strength >= 0.7).length;
    const avgStrength = allSignals.length ? allSignals.reduce((sum, s) => sum + s.signal_strength, 0) / allSignals.length : 0;

    return {
      total: totalSignals,
      buy: buyCount,
      sell: sellCount,
      strong: strongSignals,
      avgStrength: avgStrength,
      buyPercentage: totalSignals ? (buyCount / totalSignals) * 100 : 0,
      sellPercentage: totalSignals ? (sellCount / totalSignals) * 100 : 0
    };
  }, [allSignals]);

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

  // Render statistics cards
  const renderStatsCards = () => (
    <Grid container spacing={3} sx={{ mb: 3 }}>
      <Grid item xs={12} sm={6} md={3}>
        <Card sx={{ 
          background: `linear-gradient(135deg, ${alpha(theme.palette.primary.main, 0.1)} 0%, ${alpha(theme.palette.primary.main, 0.2)} 100%)`,
          border: `1px solid ${alpha(theme.palette.primary.main, 0.2)}`
        }}>
          <CardContent>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              <Avatar sx={{ bgcolor: theme.palette.primary.main }}>
                <SignalWifi4Bar />
              </Avatar>
              <Box>
                <Typography variant="h4" fontWeight={700}>
                  {stats.total}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Total Signals
                </Typography>
              </Box>
            </Box>
          </CardContent>
        </Card>
      </Grid>

      <Grid item xs={12} sm={6} md={3}>
        <Card sx={{ 
          background: `linear-gradient(135deg, ${alpha(theme.palette.success.main, 0.1)} 0%, ${alpha(theme.palette.success.main, 0.2)} 100%)`,
          border: `1px solid ${alpha(theme.palette.success.main, 0.2)}`
        }}>
          <CardContent>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              <Avatar sx={{ bgcolor: theme.palette.success.main }}>
                <TrendingUp />
              </Avatar>
              <Box>
                <Typography variant="h4" fontWeight={700} color="success.main">
                  {stats.buy}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Buy Signals ({stats.buyPercentage.toFixed(1)}%)
                </Typography>
              </Box>
            </Box>
          </CardContent>
        </Card>
      </Grid>

      <Grid item xs={12} sm={6} md={3}>
        <Card sx={{ 
          background: `linear-gradient(135deg, ${alpha(theme.palette.error.main, 0.1)} 0%, ${alpha(theme.palette.error.main, 0.2)} 100%)`,
          border: `1px solid ${alpha(theme.palette.error.main, 0.2)}`
        }}>
          <CardContent>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              <Avatar sx={{ bgcolor: theme.palette.error.main }}>
                <TrendingDown />
              </Avatar>
              <Box>
                <Typography variant="h4" fontWeight={700} color="error.main">
                  {stats.sell}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Sell Signals ({stats.sellPercentage.toFixed(1)}%)
                </Typography>
              </Box>
            </Box>
          </CardContent>
        </Card>
      </Grid>

      <Grid item xs={12} sm={6} md={3}>
        <Card sx={{ 
          background: `linear-gradient(135deg, ${alpha(theme.palette.warning.main, 0.1)} 0%, ${alpha(theme.palette.warning.main, 0.2)} 100%)`,
          border: `1px solid ${alpha(theme.palette.warning.main, 0.2)}`
        }}>
          <CardContent>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              <Avatar sx={{ bgcolor: theme.palette.warning.main }}>
                <Whatshot />
              </Avatar>
              <Box>
                <Typography variant="h4" fontWeight={700} color="warning.main">
                  {stats.strong}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Strong Signals
                </Typography>
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
                <TableCell>Strength</TableCell>
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
                <TableCell>Price</TableCell>
                <TableCell>Market Cap</TableCell>
                <TableCell>P/E</TableCell>
                <TableCell>Dividend</TableCell>
                <TableCell>Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {loading ? (
                [...Array(5)].map((_, index) => (
                  <TableRow key={index}>
                    {[...Array(9)].map((_, cellIndex) => (
                      <TableCell key={cellIndex}>
                        <Skeleton animation="wave" />
                      </TableCell>
                    ))}
                  </TableRow>
                ))
              ) : (
                paginatedSignals.map((signal, index) => (
                  <TableRow key={`${signal.symbol}-${signal.date}-${index}`} hover>
                    <TableCell>
                      <Box>
                        <Typography variant="subtitle2" fontWeight={600}>
                          {signal.symbol}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          {signal.company_name}
                        </Typography>
                        <Box sx={{ mt: 0.5 }}>
                          <SectorChip sector={signal.sector} />
                        </Box>
                      </Box>
                    </TableCell>
                    <TableCell>
                      <SignalTypeChip signal={signal.signal} strength={signal.signal_strength} />
                    </TableCell>
                    <TableCell>
                      <SignalStrength strength={signal.signal_strength} type={signal.signal_type} />
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2">
                        {new Date(signal.date).toLocaleDateString()}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {new Date(signal.date).toLocaleDateString('en-US', { weekday: 'short' })}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="subtitle2">
                        {formatCurrency(signal.current_price)}
                      </Typography>
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
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2">
                        {signal.dividend_yield ? formatPercentage(signal.dividend_yield / 100) : 'N/A'}
                      </Typography>
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
                boxShadow: theme.shadows[8]
              }
            }}>
              <CardHeader
                avatar={
                  <Avatar sx={{ 
                    bgcolor: signal.signal_type === 'buy' ? theme.palette.success.main : theme.palette.error.main,
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
      <Box sx={{ mb: 4 }}>
        <Typography variant="h3" fontWeight={700} gutterBottom>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <FlashOn sx={{ fontSize: '2.5rem', color: 'primary.main' }} />
            Trading Signals
          </Box>
        </Typography>
        <Typography variant="h6" color="text.secondary" paragraph>
          Real-time buy and sell signals based on advanced technical analysis and market data
        </Typography>
        
        <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap', mb: 3 }}>
          <Chip
            icon={<NotificationsActive />}
            label="Live Signals"
            color="primary"
            variant="outlined"
          />
          <Chip
            icon={<Schedule />}
            label="Multi-Timeframe"
            variant="outlined"
          />
          <Chip
            icon={<Analytics />}
            label="Technical Analysis"
            variant="outlined"
          />
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