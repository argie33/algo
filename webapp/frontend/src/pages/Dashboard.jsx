import React, { useState, useEffect } from 'react';
import {
  Box,
  Grid,
  Card,
  CardContent,
  Typography,
  Divider,
  Chip,
  Button,
  Avatar,
  Tooltip,
  Fade,
  Skeleton,
  TextField,
  Autocomplete,
  CircularProgress,
  Alert,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  IconButton,
  List,
  ListItem,
  ListItemText,
  ListItemSecondaryAction,
  Fab,
  Link,
  LinearProgress,
  Stack,
  Badge,
  Tabs,
  Tab,
  ListItemIcon
} from '@mui/material';
import {
  TrendingUp,
  TrendingDown,
  HorizontalRule,
  ArrowUpward,
  ArrowDownward,
  Business,
  AccountBalance,
  Analytics,
  Timeline,
  ShowChart,
  BookmarkBorder,
  Bookmark,
  ExpandMore,
  FilterList,
  Clear,
  Search,
  ViewList,
  Tune,
  InfoOutlined,
  Notifications,
  Event,
  ListAlt,
  Download,
  ContactSupport,
  Info,
  Add,
  Remove,
  Settings,
  Person,
  Link as LinkIcon,
  Close,
  AttachMoney,
  Insights,
  SignalCellular4Bar,
  CalendarToday,
  PieChart as PieChartIcon,
  BarChart,
  Refresh,
  Warning,
  CheckCircle,
  Error,
  SignalCellular0Bar,
  SignalCellular1Bar,
  SignalCellular2Bar,
  SignalCellular3Bar,
  SignalCellular4Bar as SignalCellular4BarIcon
} from '@mui/icons-material';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer, PieChart, Pie, Cell, BarChart as RechartsBarChart, Bar } from 'recharts';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { 
  getStockPrices, 
  getStockMetrics, 
  getBuySignals, 
  getSellSignals, 
  getRecentAnalystActions, 
  getKeyMetrics, 
  api,
  getDashboardUser,
  getDashboardWatchlist,
  getDashboardPortfolio,
  getDashboardPortfolioMetrics,
  getDashboardHoldings,
  getDashboardUserSettings,
  getDashboardMarketSummary,
  getDashboardEarningsCalendar,
  getDashboardAnalystInsights,
  getDashboardFinancialHighlights,
  getDashboardSymbols,
  getDashboardTechnicalSignals,
  testApiEndpoints
} from '../services/api';
import { format } from 'date-fns';
import { getApiConfig } from '../services/api';
import { formatCurrency, formatNumber, formatPercentage } from '../utils/formatters';

// Logo import with fallback
let logoSrc = null;
try {
  logoSrc = new URL('../assets/logo.png', import.meta.url).href;
} catch (e) {
  logoSrc = null;
}

const { apiUrl: API_BASE } = getApiConfig();
const DEFAULT_TICKER = 'AAPL';
const WIDGET_COLORS = ['#1976d2', '#43a047', '#ffb300', '#8e24aa', '#e53935'];

const BRAND_NAME = 'Edgebrooke Capital';

const ALLOCATION_COLORS = ['#1976d2', '#43a047', '#ffb300', '#8e24aa', '#e53935', '#00bcd4', '#ff7043', '#9e9e9e'];

// Default data structures
const defaultPortfolio = {
  value: 1250000,
  pnl: {
    daily: 12500,
    mtd: 45000,
    ytd: 180000
  },
  positions: []
};

const defaultMetrics = {
  sharpe: 1.85,
  beta: 0.92,
  maxDrawdown: 0.08,
  volatility: 0.15
};

const defaultSettings = {
  theme: 'light',
  notifications: true,
  refreshInterval: 30000
};

// Color schemes for professional dashboard
const POSITIVE_COLOR = '#4caf50';
const NEGATIVE_COLOR = '#f44336';
const NEUTRAL_COLOR = '#9e9e9e';
const PRIMARY_COLOR = '#1976d2';
const SECONDARY_COLOR = '#dc004e';

const SENTIMENT_COLORS = {
  extreme_fear: '#d32f2f',
  fear: '#f44336', 
  neutral: '#ff9800',
  greed: '#4caf50',
  extreme_greed: '#2e7d32'
};

// Summary Metrics Component
const SummaryMetrics = ({ data, loading }) => {
  if (loading) return <LinearProgress />;
  
  const metrics = [
    {
      title: 'Portfolio Value',
      value: formatCurrency(data?.portfolio?.value || 0),
      change: data?.portfolio?.pnl?.daily || 0,
      changePercent: data?.portfolio?.pnl?.daily ? (data.portfolio.pnl.daily / data.portfolio.value * 100) : 0,
      icon: <AttachMoney color="primary" />
    },
    {
      title: 'Market Sentiment',
      value: data?.market?.sentiment || 'Neutral',
      sentiment: data?.market?.sentiment || 'neutral',
      icon: <Insights color="primary" />
    },
    {
      title: 'Active Signals',
      value: data?.signals?.buyCount || 0,
      total: data?.signals?.totalCount || 0,
      icon: <SignalCellular4BarIcon color="primary" />
    },
    {
      title: 'Earnings Today',
      value: data?.earnings?.todayCount || 0,
      important: data?.earnings?.importantCount || 0,
      icon: <CalendarToday color="primary" />
    }
  ];

  return (
    <Grid container spacing={2}>
      {metrics.map((metric, index) => (
        <Grid item xs={12} sm={6} md={3} key={index}>
          <Card elevation={2} sx={{ height: '100%' }}>
            <CardContent>
              <Box display="flex" alignItems="center" justifyContent="space-between">
                <Box>
                  <Typography variant="h6" color="textSecondary" gutterBottom>
                    {metric.title}
                  </Typography>
                  <Typography variant="h4" component="div" fontWeight="bold">
                    {metric.value}
                  </Typography>
                  {metric.change !== undefined && (
                    <Box display="flex" alignItems="center" mt={1}>
                      <Chip
                        icon={metric.change >= 0 ? <TrendingUp /> : <TrendingDown />}
                        label={`${formatCurrency(metric.change)} (${formatPercentage(metric.changePercent)})`}
                        color={metric.change >= 0 ? 'success' : 'error'}
                        size="small"
                      />
                    </Box>
                  )}
                  {metric.sentiment && (
                    <Chip
                      label={metric.value}
                      color={metric.sentiment === 'greed' || metric.sentiment === 'extreme_greed' ? 'success' : 
                             metric.sentiment === 'fear' || metric.sentiment === 'extreme_fear' ? 'error' : 'warning'}
                      size="small"
                      sx={{ mt: 1 }}
                    />
                  )}
                  {metric.total && (
                    <Typography variant="body2" color="textSecondary" mt={1}>
                      {metric.value} of {metric.total} total
                    </Typography>
                  )}
                  {metric.important && (
                    <Typography variant="body2" color="textSecondary" mt={1}>
                      {metric.important} important
                    </Typography>
                  )}
                </Box>
                <Box>
                  {metric.icon}
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      ))}
    </Grid>
  );
};

// Market Overview Summary Component
const MarketOverviewSummary = ({ data, loading }) => {
  if (loading) return <LinearProgress />;

  const getSentimentIcon = (sentiment) => {
    switch (sentiment) {
      case 'extreme_greed': return <SignalCellular4Bar color="success" />;
      case 'greed': return <SignalCellular3Bar color="success" />;
      case 'neutral': return <SignalCellular2Bar color="warning" />;
      case 'fear': return <SignalCellular1Bar color="error" />;
      case 'extreme_fear': return <SignalCellular0Bar color="error" />;
      default: return <SignalCellular2Bar color="warning" />;
    }
  };

  return (
    <Card elevation={2}>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          Market Overview
        </Typography>
        <Grid container spacing={2}>
          <Grid item xs={12} md={6}>
            <Box>
              <Typography variant="subtitle2" color="textSecondary">
                Major Indices
              </Typography>
              {data?.indices?.slice(0, 3).map((index, i) => (
                <Box key={i} display="flex" justifyContent="space-between" alignItems="center" py={0.5}>
                  <Typography variant="body2">{index.symbol}</Typography>
                  <Box display="flex" alignItems="center" gap={1}>
                    <Typography variant="body2" fontWeight="bold">
                      {formatNumber(index.price)}
                    </Typography>
                    <Chip
                      label={`${formatPercentage(index.changePercent)}`}
                      color={index.changePercent >= 0 ? 'success' : 'error'}
                      size="small"
                    />
                  </Box>
                </Box>
              ))}
            </Box>
          </Grid>
          <Grid item xs={12} md={6}>
            <Box>
              <Typography variant="subtitle2" color="textSecondary">
                Market Sentiment
              </Typography>
              <Box display="flex" alignItems="center" gap={1} mt={1}>
                {getSentimentIcon(data?.sentiment)}
                <Typography variant="body1" fontWeight="bold">
                  {data?.sentiment?.replace('_', ' ').toUpperCase() || 'NEUTRAL'}
                </Typography>
              </Box>
              <Typography variant="body2" color="textSecondary" mt={1}>
                Fear & Greed Index: {data?.fearGreedIndex || 'N/A'}
              </Typography>
              <Typography variant="body2" color="textSecondary">
                Market Breadth: {data?.breadth?.advancing || 0} advancing, {data?.breadth?.declining || 0} declining
              </Typography>
            </Box>
          </Grid>
        </Grid>
      </CardContent>
    </Card>
  );
};

// Portfolio Summary Component
const PortfolioSummary = ({ data, loading }) => {
  if (loading) return <LinearProgress />;

  const portfolio = data?.portfolio || {};
  const holdings = data?.holdings || [];

  // Calculate allocation data for pie chart
  const allocationData = holdings.slice(0, 8).map((h, i) => ({
    name: h.symbol,
    value: h.value,
    color: ALLOCATION_COLORS[i % ALLOCATION_COLORS.length]
  }));

  return (
    <Card elevation={2}>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          Portfolio Summary
        </Typography>
        <Grid container spacing={2}>
          <Grid item xs={12} md={6}>
            <Box>
              <Typography variant="h4" fontWeight="bold" color="primary">
                {formatCurrency(portfolio.value || 0)}
              </Typography>
              <Box display="flex" gap={1} mt={1}>
                <Chip
                  icon={portfolio.pnl?.daily >= 0 ? <TrendingUp /> : <TrendingDown />}
                  label={`Daily: ${formatCurrency(portfolio.pnl?.daily || 0)} (${formatPercentage(portfolio.pnl?.daily ? (portfolio.pnl.daily / portfolio.value * 100) : 0)})`}
                  color={portfolio.pnl?.daily >= 0 ? 'success' : 'error'}
                />
                <Chip
                  icon={portfolio.pnl?.mtd >= 0 ? <TrendingUp /> : <TrendingDown />}
                  label={`MTD: ${formatPercentage(portfolio.pnl?.mtd ? (portfolio.pnl.mtd / portfolio.value * 100) : 0)}`}
                  color={portfolio.pnl?.mtd >= 0 ? 'success' : 'error'}
                />
              </Box>
              <Box mt={2}>
                <Typography variant="subtitle2" color="textSecondary">
                  Key Metrics
                </Typography>
                <Grid container spacing={1} mt={1}>
                  <Grid item xs={6}>
                    <Typography variant="body2">Sharpe Ratio</Typography>
                    <Typography variant="body1" fontWeight="bold">
                      {portfolio.metrics?.sharpe ? portfolio.metrics.sharpe.toFixed(2) : 'N/A'}
                    </Typography>
                  </Grid>
                  <Grid item xs={6}>
                    <Typography variant="body2">Beta</Typography>
                    <Typography variant="body1" fontWeight="bold">
                      {portfolio.metrics?.beta ? portfolio.metrics.beta.toFixed(2) : 'N/A'}
                    </Typography>
                  </Grid>
                  <Grid item xs={6}>
                    <Typography variant="body2">Max Drawdown</Typography>
                    <Typography variant="body1" fontWeight="bold" color="error">
                      {portfolio.metrics?.maxDrawdown ? formatPercentage(portfolio.metrics.maxDrawdown) : 'N/A'}
                    </Typography>
                  </Grid>
                  <Grid item xs={6}>
                    <Typography variant="body2">Volatility</Typography>
                    <Typography variant="body1" fontWeight="bold">
                      {portfolio.metrics?.volatility ? formatPercentage(portfolio.metrics.volatility) : 'N/A'}
                    </Typography>
                  </Grid>
                </Grid>
              </Box>
            </Box>
          </Grid>
          <Grid item xs={12} md={6}>
            <Box>
              <Typography variant="subtitle2" color="textSecondary" gutterBottom>
                Top Holdings
              </Typography>
              {holdings.slice(0, 5).map((holding, i) => (
                <Box key={i} display="flex" justifyContent="space-between" alignItems="center" py={0.5}>
                  <Box>
                    <Typography variant="body2" fontWeight="bold">{holding.symbol}</Typography>
                    <Typography variant="caption" color="textSecondary">{holding.name}</Typography>
                  </Box>
                  <Box textAlign="right">
                    <Typography variant="body2" fontWeight="bold">
                      {formatCurrency(holding.value)}
                    </Typography>
                    <Chip
                      label={formatPercentage(holding.changePercent)}
                      color={holding.changePercent >= 0 ? 'success' : 'error'}
                      size="small"
                    />
                  </Box>
                </Box>
              ))}
            </Box>
          </Grid>
        </Grid>
      </CardContent>
    </Card>
  );
};

// Technical Signals Summary Component
const TechnicalSignalsSummary = ({ data, loading }) => {
  if (loading) return <LinearProgress />;

  const signals = data?.signals || [];
  const buySignals = signals.filter(s => s.signal === 'BUY');
  const sellSignals = signals.filter(s => s.signal === 'SELL');
  const holdSignals = signals.filter(s => s.signal === 'HOLD');

  return (
    <Card elevation={2}>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          Technical Signals
        </Typography>
        <Grid container spacing={2}>
          <Grid item xs={12} md={4}>
            <Box textAlign="center">
              <Typography variant="h4" color="success.main" fontWeight="bold">
                {buySignals.length}
              </Typography>
              <Typography variant="subtitle2" color="textSecondary">
                Buy Signals
              </Typography>
            </Box>
          </Grid>
          <Grid item xs={12} md={4}>
            <Box textAlign="center">
              <Typography variant="h4" color="error.main" fontWeight="bold">
                {sellSignals.length}
              </Typography>
              <Typography variant="subtitle2" color="textSecondary">
                Sell Signals
              </Typography>
            </Box>
          </Grid>
          <Grid item xs={12} md={4}>
            <Box textAlign="center">
              <Typography variant="h4" color="warning.main" fontWeight="bold">
                {holdSignals.length}
              </Typography>
              <Typography variant="subtitle2" color="textSecondary">
                Hold Signals
              </Typography>
            </Box>
          </Grid>
        </Grid>
        <Divider sx={{ my: 2 }} />
        <Typography variant="subtitle2" color="textSecondary" gutterBottom>
          Recent Signals
        </Typography>
        {signals.slice(0, 5).map((signal, i) => (
          <Box key={i} display="flex" justifyContent="space-between" alignItems="center" py={0.5}>
            <Box>
              <Typography variant="body2" fontWeight="bold">{signal.symbol}</Typography>
              <Typography variant="caption" color="textSecondary">{signal.strategy}</Typography>
            </Box>
            <Chip
              label={signal.signal}
              color={signal.signal === 'BUY' ? 'success' : signal.signal === 'SELL' ? 'error' : 'warning'}
              size="small"
            />
          </Box>
        ))}
      </CardContent>
    </Card>
  );
};

// Earnings Calendar Summary Component
const EarningsCalendarSummary = ({ data, loading }) => {
  if (loading) return <LinearProgress />;

  const earnings = data?.earnings || [];
  const todayEarnings = earnings.filter(e => e.date === new Date().toISOString().split('T')[0]);
  const importantEarnings = earnings.filter(e => e.importance === 'high');

  return (
    <Card elevation={2}>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          Earnings Calendar
        </Typography>
        <Grid container spacing={2}>
          <Grid item xs={12} md={6}>
            <Box>
              <Typography variant="subtitle2" color="textSecondary">
                Today's Earnings
              </Typography>
              <Typography variant="h4" color="primary" fontWeight="bold">
                {todayEarnings.length}
              </Typography>
              {todayEarnings.slice(0, 3).map((earning, i) => (
                <Box key={i} display="flex" justifyContent="space-between" alignItems="center" py={0.5}>
                  <Typography variant="body2" fontWeight="bold">{earning.symbol}</Typography>
                  <Typography variant="body2" color="textSecondary">{earning.time}</Typography>
                </Box>
              ))}
            </Box>
          </Grid>
          <Grid item xs={12} md={6}>
            <Box>
              <Typography variant="subtitle2" color="textSecondary">
                Important Earnings
              </Typography>
              <Typography variant="h4" color="warning.main" fontWeight="bold">
                {importantEarnings.length}
              </Typography>
              {importantEarnings.slice(0, 3).map((earning, i) => (
                <Box key={i} display="flex" justifyContent="space-between" alignItems="center" py={0.5}>
                  <Typography variant="body2" fontWeight="bold">{earning.symbol}</Typography>
                  <Typography variant="body2" color="textSecondary">{earning.date}</Typography>
                </Box>
              ))}
            </Box>
          </Grid>
        </Grid>
      </CardContent>
    </Card>
  );
};

// Main Dashboard Component
const Dashboard = () => {
  console.log('🚀 Dashboard: Component rendering...');
  
  const [selectedSymbol, setSelectedSymbol] = useState('AAPL');
  const [addPositionOpen, setAddPositionOpen] = useState(false);
  const [addWatchlistOpen, setAddWatchlistOpen] = useState(false);
  const [debugResults, setDebugResults] = useState(null);

  // User data
  const { user, isLoading: userLoading, error: userError } = useUser();

  // Watchlist data
  const { watchlist, isLoading: watchlistLoading, error: watchlistError } = useWatchlist();

  // Portfolio data
  const { portfolio, isLoading: portfolioLoading, error: portfolioError } = usePortfolio();

  // Portfolio metrics
  const { portfolioMetrics, isLoading: metricsLoading, error: metricsError } = usePortfolioMetrics();

  // Holdings data
  const { holdings, isLoading: holdingsLoading, error: holdingsError } = useHoldings();

  // User settings
  const { userSettings, isLoading: settingsLoading, error: settingsError } = useUserSettings();

  // Market summary
  const { data: marketSummary, isLoading: marketLoading, error: marketError } = useQuery({
    queryKey: ['dashboardMarketSummary'],
    queryFn: getDashboardMarketSummary,
    staleTime: 5 * 60 * 1000, // 5 minutes
    onSuccess: (data) => console.log('✅ Dashboard: Market summary loaded:', data),
    onError: (error) => console.error('❌ Dashboard: Market summary error:', error)
  });

  // Technical signals
  const { data: technicalSignals, isLoading: signalsLoading, error: signalsError } = useQuery({
    queryKey: ['dashboardTechnicalSignals'],
    queryFn: getDashboardTechnicalSignals,
    staleTime: 5 * 60 * 1000, // 5 minutes
    onSuccess: (data) => console.log('✅ Dashboard: Technical signals loaded:', data),
    onError: (error) => console.error('❌ Dashboard: Technical signals error:', error)
  });

  // Earnings calendar
  const { data: earningsCalendar, isLoading: earningsLoading, error: earningsError } = useQuery({
    queryKey: ['dashboardEarningsCalendar'],
    queryFn: getDashboardEarningsCalendar,
    staleTime: 5 * 60 * 1000, // 5 minutes
    onSuccess: (data) => console.log('✅ Dashboard: Earnings calendar loaded:', data),
    onError: (error) => console.error('❌ Dashboard: Earnings calendar error:', error)
  });

  // Placeholder mutations (to be implemented later)
  const updatePositions = useMutation({
    mutationFn: (positions) => Promise.resolve(positions),
    onSuccess: () => console.log('Positions updated')
  });

  const addSymbol = useMutation({
    mutationFn: (symbol) => Promise.resolve(symbol),
    onSuccess: () => console.log('Symbol added to watchlist')
  });

  const removeSymbol = useMutation({
    mutationFn: (symbol) => Promise.resolve(symbol),
    onSuccess: () => console.log('Symbol removed from watchlist')
  });

  console.log('📊 Dashboard: Data summary:', {
    user: { hasData: !!user, isLoading: userLoading, hasError: !!userError },
    watchlist: { hasData: !!watchlist, isLoading: watchlistLoading, hasError: !!watchlistError },
    portfolio: { hasData: !!portfolio, isLoading: portfolioLoading, hasError: !!portfolioError },
    portfolioMetrics: { hasData: !!portfolioMetrics, isLoading: metricsLoading, hasError: !!metricsError },
    holdings: { hasData: !!holdings, isLoading: holdingsLoading, hasError: !!holdingsError },
    userSettings: { hasData: !!userSettings, isLoading: settingsLoading, hasError: !!settingsError },
    marketSummary: { hasData: !!marketSummary, isLoading: marketLoading, hasError: !!marketError },
    technicalSignals: { hasData: !!technicalSignals, isLoading: signalsLoading, hasError: !!signalsError },
    earningsCalendar: { hasData: !!earningsCalendar, isLoading: earningsLoading, hasError: !!earningsError }
  });

  // Get available symbols for dropdown
  const { data: symbolsData } = useQuery({
    queryKey: ['dashboard-symbols'],
    queryFn: async () => {
      const response = await getDashboardSymbols();
      return response;
    },
    staleTime: 5 * 60 * 1000
  });
  
  const SYMBOL_OPTIONS = Array.isArray(symbolsData?.data) && symbolsData.data.length > 0
    ? symbolsData.data
    : ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA', 'SPY', 'QQQ'];

  // Price data for selected symbol
  const { data: priceData } = useQuery({
    queryKey: ['stock-prices', selectedSymbol],
    queryFn: () => getStockPrices(selectedSymbol, 'daily', 30),
    staleTime: 5 * 60 * 1000
  });

  // Prepare equity curve for chart
  const equityCurve = Array.isArray(priceData?.data)
    ? priceData.data.map(p => ({ date: p.date || p.timestamp, equity: p.close || p.price })).reverse()
    : [];

  // Portfolio allocation data for pie chart
  const allocationData = Array.isArray(holdings)
    ? holdings.map((h, i) => ({ name: h.symbol, value: h.value, color: ALLOCATION_COLORS[i % ALLOCATION_COLORS.length] }))
    : [];

  // Portfolio drawdown (mocked for now)
  const maxDrawdown = portfolioMetrics.maxDrawdown ? (portfolioMetrics.maxDrawdown * 100).toFixed(2) : 'N/A';
  const volatility = portfolioMetrics.volatility ? (portfolioMetrics.volatility * 100).toFixed(2) : 'N/A';

  // Watchlist price data (mocked for now)
  const watchlistPrices = watchlist.map(symbol => ({ symbol, price: Math.random() * 200 + 50, change: (Math.random() - 0.5) * 2 }));

  // Combine all data for summary metrics
  const summaryData = {
    portfolio: portfolio,
    market: marketSummary?.data,
    signals: technicalSignals?.data,
    earnings: earningsCalendar?.data
  };

  const isLoading = portfolioLoading || watchlistLoading || marketLoading || signalsLoading || holdingsLoading || earningsLoading;

  // Handle adding position
  const handleAddPosition = (position) => {
    const newPositions = [...portfolio.positions, position];
    updatePositions.mutate(newPositions);
  };

  // Handle adding to watchlist
  const handleAddToWatchlist = (symbol) => {
    addSymbol.mutate(symbol);
  };

  // Debug function to test API endpoints
  const handleDebugTest = async () => {
    try {
      const results = await testApiEndpoints();
      setDebugResults(results);
      console.log('Debug test completed:', results);
    } catch (error) {
      console.error('Debug test failed:', error);
      setDebugResults({ error: error.message });
    }
  };

  return (
    <Box sx={{ p: 3 }}>
      {/* Header */}
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 3 }}>
        <Box sx={{ display: 'flex', alignItems: 'center' }}>
          {logoSrc ? (
            <img src={logoSrc} alt="Logo" style={{ height: 48, width: 48, borderRadius: '50%' }} />
          ) : (
            <Avatar sx={{ bgcolor: 'primary.main', width: 48, height: 48, fontSize: 28 }}>
              EC
            </Avatar>
          )}
          <Box>
            <Typography variant="h4" sx={{ fontWeight: 700, letterSpacing: 1 }}>
              {BRAND_NAME} Dashboard
            </Typography>
            <Typography variant="caption" color="text.secondary">
              Professional Investment Management Platform
            </Typography>
            {userLoading ? (
              <Skeleton width={120} height={18} />
            ) : user ? (
              <Typography variant="caption" color="text.secondary">
                Welcome, {user.name || user.email}
              </Typography>
            ) : null}
          </Box>
        </Box>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <Autocomplete
            options={SYMBOL_OPTIONS}
            value={selectedSymbol}
            onChange={(_, newValue) => newValue && setSelectedSymbol(newValue)}
            sx={{ width: 180, mr: 2 }}
            renderInput={(params) => <TextField {...params} label="Symbol" size="small" />}
          />
          <Typography variant="caption" color="text.secondary" sx={{ fontStyle: 'italic' }}>
            {format(new Date(), 'MMMM d, yyyy')}
          </Typography>
          <Tooltip title="Refresh Data">
            <IconButton onClick={() => window.location.reload()}>
              <Refresh />
            </IconButton>
          </Tooltip>
          {user && (
            <Tooltip title={user.email || user.name} arrow>
              <Avatar sx={{ bgcolor: 'secondary.main', width: 36, height: 36, ml: 1 }}>
                {user.name ? user.name[0] : (user.email ? user.email[0] : '?')}
              </Avatar>
            </Tooltip>
          )}
          {user && (
            <Button size="small" color="secondary" variant="outlined" onClick={() => {
              api.post('/auth/logout')
                .then(() => window.location.href = '/login')
                .catch(error => {
                  console.error('Logout error:', error);
                  window.location.href = '/login';
                });
            }}>
              Logout
            </Button>
          )}
          {/* Debug button */}
          {import.meta.env.DEV && (
            <Button 
              size="small" 
              variant="outlined" 
              onClick={handleDebugTest}
              sx={{ ml: 1 }}
            >
              Debug API
            </Button>
          )}
        </Box>
      </Box>

      {/* Debug Results */}
      {debugResults && (
        <Alert severity="info" sx={{ mb: 2 }}>
          <Typography variant="subtitle2" gutterBottom>API Debug Results:</Typography>
          <pre style={{ fontSize: '12px', overflow: 'auto', maxHeight: '200px' }}>
            {JSON.stringify(debugResults, null, 2)}
          </pre>
        </Alert>
      )}

      {/* Summary Metrics */}
      <Box mb={3}>
        <SummaryMetrics data={summaryData} loading={isLoading} />
      </Box>

      {/* Main Dashboard Grid */}
      <Grid container spacing={3}>
        {/* Market Overview */}
        <Grid item xs={12} lg={6}>
          <MarketOverviewSummary data={marketSummary?.data} loading={marketLoading} />
        </Grid>

        {/* Portfolio Summary */}
        <Grid item xs={12} lg={6}>
          <PortfolioSummary data={{ portfolio, holdings }} loading={portfolioLoading || holdingsLoading} />
        </Grid>

        {/* Technical Signals */}
        <Grid item xs={12} lg={6}>
          <TechnicalSignalsSummary data={technicalSignals?.data} loading={signalsLoading} />
        </Grid>

        {/* Earnings Calendar */}
        <Grid item xs={12} lg={6}>
          <EarningsCalendarSummary data={earningsCalendar?.data} loading={earningsLoading} />
        </Grid>

        {/* Performance Analytics */}
        <Grid item xs={12} lg={8}>
          <Card elevation={2}>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Performance Analytics ({selectedSymbol})
              </Typography>
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={equityCurve} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="date" tick={{ fontSize: 12 }} />
                  <YAxis tick={{ fontSize: 12 }} domain={['auto', 'auto']} />
                  <RechartsTooltip formatter={(v) => `$${v?.toLocaleString?.() ?? v}`}/>
                  <Line type="monotone" dataKey="equity" stroke="#1976d2" strokeWidth={2} dot={false} name="Equity" />
                </LineChart>
              </ResponsiveContainer>
              <Typography variant="caption" color="textSecondary">Equity curve for {selectedSymbol}</Typography>
            </CardContent>
          </Card>
        </Grid>

        {/* Watchlist Summary */}
        <Grid item xs={12} lg={4}>
          <Card elevation={2}>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Watchlist Summary
              </Typography>
              <Grid container spacing={2}>
                <Grid item xs={12} md={6}>
                  <Typography variant="subtitle2" color="textSecondary" gutterBottom>
                    Top Gainers
                  </Typography>
                  {watchlistPrices.filter(item => item.change > 0).slice(0, 3).map((item, i) => (
                    <Box key={i} display="flex" justifyContent="space-between" alignItems="center" py={0.5}>
                      <Typography variant="body2" fontWeight="bold">{item.symbol}</Typography>
                      <Box textAlign="right">
                        <Typography variant="body2" fontWeight="bold">
                          {formatCurrency(item.price)}
                        </Typography>
                        <Chip
                          label={`+${formatPercentage(item.change)}`}
                          color="success"
                          size="small"
                        />
                      </Box>
                    </Box>
                  ))}
                </Grid>
                <Grid item xs={12} md={6}>
                  <Typography variant="subtitle2" color="textSecondary" gutterBottom>
                    Top Losers
                  </Typography>
                  {watchlistPrices.filter(item => item.change < 0).slice(0, 3).map((item, i) => (
                    <Box key={i} display="flex" justifyContent="space-between" alignItems="center" py={0.5}>
                      <Typography variant="body2" fontWeight="bold">{item.symbol}</Typography>
                      <Box textAlign="right">
                        <Typography variant="body2" fontWeight="bold">
                          {formatCurrency(item.price)}
                        </Typography>
                        <Chip
                          label={formatPercentage(item.change)}
                          color="error"
                          size="small"
                        />
                      </Box>
                    </Box>
                  ))}
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Compliance Disclaimer */}
      <Box sx={{ mt: 4, mb: 2, textAlign: 'center' }}>
        <Typography variant="caption" color="text.secondary">
          For institutional use only. Not investment advice. Data may be delayed or incomplete. &copy; {new Date().getFullYear()} {BRAND_NAME}. All rights reserved.
        </Typography>
      </Box>
    </Box>
  );
};

function useUser() {
  console.log('🔍 useUser: Hook called');
  const { data, isLoading, error } = useQuery({
    queryKey: ['dashboardUser'],
    queryFn: getDashboardUser,
    staleTime: 5 * 60 * 1000, // 5 minutes
    onSuccess: (data) => console.log('✅ useUser: Data loaded successfully:', data),
    onError: (error) => console.error('❌ useUser: Error loading data:', error)
  });
  
  console.log('📊 useUser: Hook result:', { hasData: !!data, isLoading, hasError: !!error });
  return { user: data?.data, isLoading, error };
}

function useWatchlist() {
  console.log('🔍 useWatchlist: Hook called');
  const { data, isLoading, error } = useQuery({
    queryKey: ['dashboardWatchlist'],
    queryFn: getDashboardWatchlist,
    staleTime: 5 * 60 * 1000, // 5 minutes
    onSuccess: (data) => console.log('✅ useWatchlist: Data loaded successfully:', data),
    onError: (error) => console.error('❌ useWatchlist: Error loading data:', error)
  });
  
  console.log('📊 useWatchlist: Hook result:', { hasData: !!data, isLoading, hasError: !!error });
  return { watchlist: data?.data || [], isLoading, error };
}

function usePortfolio() {
  console.log('🔍 usePortfolio: Hook called');
  const { data, isLoading, error } = useQuery({
    queryKey: ['dashboardPortfolio'],
    queryFn: getDashboardPortfolio,
    staleTime: 5 * 60 * 1000, // 5 minutes
    onSuccess: (data) => console.log('✅ usePortfolio: Data loaded successfully:', data),
    onError: (error) => console.error('❌ usePortfolio: Error loading data:', error)
  });
  
  console.log('📊 usePortfolio: Hook result:', { hasData: !!data, isLoading, hasError: !!error });
  return { portfolio: data?.data || defaultPortfolio, isLoading, error };
}

function usePortfolioMetrics() {
  console.log('🔍 usePortfolioMetrics: Hook called');
  const { data, isLoading, error } = useQuery({
    queryKey: ['dashboardPortfolioMetrics'],
    queryFn: getDashboardPortfolioMetrics,
    staleTime: 5 * 60 * 1000, // 5 minutes
    onSuccess: (data) => console.log('✅ usePortfolioMetrics: Data loaded successfully:', data),
    onError: (error) => console.error('❌ usePortfolioMetrics: Error loading data:', error)
  });
  
  console.log('📊 usePortfolioMetrics: Hook result:', { hasData: !!data, isLoading, hasError: !!error });
  return { portfolioMetrics: data?.data || defaultMetrics, isLoading, error };
}

function useHoldings() {
  console.log('🔍 useHoldings: Hook called');
  const { data, isLoading, error } = useQuery({
    queryKey: ['dashboardHoldings'],
    queryFn: getDashboardHoldings,
    staleTime: 5 * 60 * 1000, // 5 minutes
    onSuccess: (data) => console.log('✅ useHoldings: Data loaded successfully:', data),
    onError: (error) => console.error('❌ useHoldings: Error loading data:', error)
  });
  
  console.log('📊 useHoldings: Hook result:', { hasData: !!data, isLoading, hasError: !!error });
  return { holdings: data?.data || [], isLoading, error };
}

function useUserSettings() {
  console.log('🔍 useUserSettings: Hook called');
  const { data, isLoading, error } = useQuery({
    queryKey: ['dashboardUserSettings'],
    queryFn: getDashboardUserSettings,
    staleTime: 5 * 60 * 1000, // 5 minutes
    onSuccess: (data) => console.log('✅ useUserSettings: Data loaded successfully:', data),
    onError: (error) => console.error('❌ useUserSettings: Error loading data:', error)
  });
  
  console.log('📊 useUserSettings: Hook result:', { hasData: !!data, isLoading, hasError: !!error });
  return { userSettings: data?.data || defaultSettings, isLoading, error };
}

// Placeholder Widget Components (to be implemented later)
const MarketOverviewWidget = () => (
  <Card elevation={2}>
    <CardContent>
      <Typography variant="h6" gutterBottom>
        Market Overview
      </Typography>
      <Typography variant="body2" color="textSecondary">
        Market overview data will be displayed here
      </Typography>
    </CardContent>
  </Card>
);

const TechnicalSignalsWidget = () => (
  <Card elevation={2}>
    <CardContent>
      <Typography variant="h6" gutterBottom>
        Technical Signals
      </Typography>
      <Typography variant="body2" color="textSecondary">
        Technical signals data will be displayed here
      </Typography>
    </CardContent>
  </Card>
);

const HoldingsWidget = () => (
  <Card elevation={2}>
    <CardContent>
      <Typography variant="h6" gutterBottom>
        Holdings
      </Typography>
      <Typography variant="body2" color="textSecondary">
        Holdings data will be displayed here
      </Typography>
    </CardContent>
  </Card>
);

const EarningsCalendarWidget = ({ symbol }) => (
  <Card elevation={2}>
    <CardContent>
      <Typography variant="h6" gutterBottom>
        Earnings Calendar
      </Typography>
      <Typography variant="body2" color="textSecondary">
        Earnings calendar for {symbol} will be displayed here
      </Typography>
    </CardContent>
  </Card>
);

const AnalystInsightsWidget = ({ symbol }) => (
  <Card elevation={2}>
    <CardContent>
      <Typography variant="h6" gutterBottom>
        Analyst Insights
      </Typography>
      <Typography variant="body2" color="textSecondary">
        Analyst insights for {symbol} will be displayed here
      </Typography>
    </CardContent>
  </Card>
);

const FinancialHighlightsWidget = ({ symbol }) => (
  <Card elevation={2}>
    <CardContent>
      <Typography variant="h6" gutterBottom>
        Financial Highlights
      </Typography>
      <Typography variant="body2" color="textSecondary">
        Financial highlights for {symbol} will be displayed here
      </Typography>
    </CardContent>
  </Card>
);

const UserSettingsWidget = ({ user }) => (
  <Card elevation={2}>
    <CardContent>
      <Typography variant="h6" gutterBottom>
        User Settings
      </Typography>
      <Typography variant="body2" color="textSecondary">
        User settings for {user?.name || 'User'} will be displayed here
      </Typography>
    </CardContent>
  </Card>
);

const AddPositionDialog = ({ open, onClose, onAdd }) => (
  <Dialog open={open} onClose={onClose}>
    <DialogTitle>Add Position</DialogTitle>
    <DialogContent>
      <Typography variant="body2" color="textSecondary">
        Add position dialog will be implemented here
      </Typography>
    </DialogContent>
    <DialogActions>
      <Button onClick={onClose}>Cancel</Button>
      <Button onClick={onClose} variant="contained">Add</Button>
    </DialogActions>
  </Dialog>
);

const AddToWatchlistDialog = ({ open, onClose, onAdd }) => (
  <Dialog open={open} onClose={onClose}>
    <DialogTitle>Add to Watchlist</DialogTitle>
    <DialogContent>
      <Typography variant="body2" color="textSecondary">
        Add to watchlist dialog will be implemented here
      </Typography>
    </DialogContent>
    <DialogActions>
      <Button onClick={onClose}>Cancel</Button>
      <Button onClick={onClose} variant="contained">Add</Button>
    </DialogActions>
  </Dialog>
);

export default Dashboard;
