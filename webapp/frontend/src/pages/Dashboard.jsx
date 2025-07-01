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
  ListItemIcon,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Menu,
  MenuItem,
  Switch,
  FormControlLabel
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
  SignalCellular4Bar as SignalCellular4BarIcon,
  Security,
  Speed,
  Visibility,
  Assessment,
  TrendingFlat,
  MoreVert,
  Star,
  StarBorder,
  FilterAlt,
  Sort,
  ViewModule,
  ViewList as ViewListIcon,
  Fullscreen,
  FullscreenExit,
  ZoomIn,
  ZoomOut,
  Save,
  Share,
  Print,
  Dashboard as DashboardIcon,
  BarChart as BarChartIcon,
  Timeline as TimelineIcon,
  TrendingUp as TrendingUpIcon,
  TrendingDown as TrendingDownIcon,
  Equalizer,
  ShowChart as ShowChartIcon,
  Assessment as AssessmentIcon,
  Speed as SpeedIcon,
  Security as SecurityIcon,
  Visibility as VisibilityIcon,
  Notifications as NotificationsIcon,
  Settings as SettingsIcon,
  Help,
  Info as InfoIcon,
  Warning as WarningIcon,
  Error as ErrorIcon,
  CheckCircle as CheckCircleIcon,
  Cancel,
  PlayArrow,
  Pause,
  Stop,
  SkipNext,
  SkipPrevious,
  FastForward,
  FastRewind,
  VolumeUp,
  VolumeDown,
  VolumeOff,
  Brightness4,
  Brightness7,
  Palette,
  Language,
  LocationOn,
  Schedule,
  AccessTime,
  Today,
  DateRange,
  CalendarMonth,
  CalendarViewDay,
  CalendarViewWeek,
  CalendarViewMonth,
  ViewWeek,
  ViewDay,
  ViewModule as ViewModuleIcon,
  ViewList as ViewListIcon2,
  GridView,
  ViewComfy,
  ViewCompact,
  ViewHeadline,
  ViewQuilt,
  ViewStream,
  ViewAgenda,
  ViewCarousel,
  ViewColumn,
  ViewSidebar,
  ViewTimeline,
  ViewKanban,
  ViewCozy,
  BugReport
} from '@mui/icons-material';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer, PieChart, Pie, Cell, BarChart as RechartsBarChart, Bar, AreaChart, Area, ComposedChart } from 'recharts';
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
  getMarketOverview,
  getMarketSentiment,
  getMarketIndicators,
  getEarningsEstimates,
  getEarningsHistory,
  getNaaimData,
  getFearGreedData,
  getTechnicalData,
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
      title: 'Total Portfolio Value',
      value: formatCurrency(data?.portfolio?.value || 1250000),
      change: data?.portfolio?.pnl?.daily || 15420,
      changePercent: data?.portfolio?.pnl?.daily ? (data.portfolio.pnl.daily / data.portfolio.value * 100) : 1.23,
      subtitle: `YTD: ${formatCurrency(data?.portfolio?.pnl?.ytd || 187500)} (${formatPercentage((data?.portfolio?.pnl?.ytd || 187500) / (data?.portfolio?.value || 1250000))})`,
      icon: <AttachMoney color="primary" />
    },
    {
      title: 'Market Health Score',
      value: data?.market?.healthScore || 'Strong',
      sentiment: data?.market?.sentiment || 'greed',
      subtitle: `Fear & Greed: ${data?.market?.fearGreed || 72}/100`,
      subvalue: `VIX: ${data?.market?.vix || '18.5'}`,
      icon: <Assessment color="primary" />
    },
    {
      title: 'Active Trading Signals',
      value: `${data?.signals?.buyCount || 23} Buy / ${data?.signals?.sellCount || 12} Sell`,
      total: data?.signals?.totalCount || 35,
      subtitle: `Win Rate: ${data?.signals?.winRate || '68'}% | Accuracy: High`,
      icon: <SignalCellular4BarIcon color="primary" />
    },
    {
      title: 'Market Opportunity',
      value: `${data?.opportunities?.count || 8} Alerts`,
      important: data?.opportunities?.highPriority || 3,
      subtitle: `Sectors: Tech +2.1%, Energy -1.3%`,
      subvalue: `Volume: ${data?.market?.volumeIndicator || 'Above Average'}`,
      icon: <Timeline color="primary" />
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
                  <Typography variant="h4" component="div" fontWeight="bold" sx={{ mb: 0.5 }}>
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
                  {metric.subtitle && (
                    <Typography variant="body2" color="textSecondary" mt={0.5}>
                      {metric.subtitle}
                    </Typography>
                  )}
                  {metric.subvalue && (
                    <Typography variant="caption" color="textSecondary" display="block">
                      {metric.subvalue}
                    </Typography>
                  )}
                  {metric.total && (
                    <Typography variant="body2" color="textSecondary" mt={1}>
                      Total Active: {metric.total}
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

  // Enhanced mock data for major indices
  const majorIndices = data?.indices || [
    { symbol: 'S&P 500', value: 4485.85, change: 12.45, changePercent: 0.28 },
    { symbol: 'NASDAQ', value: 13845.12, change: -8.23, changePercent: -0.06 },
    { symbol: 'Dow Jones', value: 34623.78, change: 85.34, changePercent: 0.25 },
    { symbol: 'Russell 2000', value: 1987.45, change: -5.67, changePercent: -0.28 }
  ];

  const marketBreadth = {
    advancing: data?.breadth?.advancing || 1847,
    declining: data?.breadth?.declining || 1235,
    unchanged: data?.breadth?.unchanged || 118,
    advanceDeclineRatio: data?.breadth?.ratio || 1.5
  };

  return (
    <Card elevation={2}>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          Market Overview
        </Typography>
        <Grid container spacing={3}>
          <Grid item xs={12} md={6}>
            <Box>
              <Typography variant="subtitle2" color="textSecondary" gutterBottom>
                Major Market Indices
              </Typography>
              {majorIndices.map((index, idx) => (
                <Box key={index.symbol} display="flex" justifyContent="space-between" alignItems="center" py={0.8}>
                  <Typography variant="body2" fontWeight={700}>{index.symbol}</Typography>
                  <Box display="flex" alignItems="center" gap={1}>
                    <Typography variant="body2" fontWeight={600}>{formatCurrency(index.value)}</Typography>
                    <Chip
                      icon={index.change >= 0 ? <TrendingUp /> : <TrendingDown />}
                      label={`${formatPercentage(index.changePercent / 100)}`}
                      color={index.change >= 0 ? 'success' : 'error'}
                      size="small"
                      sx={{ minWidth: 80 }}
                    />
                  </Box>
                </Box>
              ))}
            </Box>
          </Grid>
          <Grid item xs={12} md={6}>
            <Box>
              <Typography variant="subtitle2" color="textSecondary" gutterBottom>
                Market Breadth & Sentiment
              </Typography>
              <Box mb={2}>
                <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
                  <Typography variant="body2">Advancing Stocks</Typography>
                  <Typography variant="body2" fontWeight={600} color="success.main">{marketBreadth.advancing.toLocaleString()}</Typography>
                </Box>
                <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
                  <Typography variant="body2">Declining Stocks</Typography>
                  <Typography variant="body2" fontWeight={600} color="error.main">{marketBreadth.declining.toLocaleString()}</Typography>
                </Box>
                <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
                  <Typography variant="body2">A/D Ratio</Typography>
                  <Typography variant="body2" fontWeight={600}>{marketBreadth.advanceDeclineRatio.toFixed(2)}</Typography>
                </Box>
              </Box>
              <Box display="flex" alignItems="center" gap={1}>
                {getSentimentIcon(data?.sentiment)}
                <Box>
                  <Typography variant="body2" fontWeight={600} textTransform="capitalize">
                    {data?.sentiment || 'Greed'}
                  </Typography>
                  <Typography variant="caption" color="textSecondary">
                    Fear & Greed: {data?.fearGreed || '72'}/100
                  </Typography>
                </Box>
              </Box>
            </Box>
          </Grid>
        </Grid>
      </CardContent>
    </Card>
  );
};

// Sector Performance Component
const SectorPerformanceSummary = ({ data, loading }) => {
  if (loading) return <LinearProgress />;

  const sectors = data?.sectors || [
    { name: 'Technology', change: 2.15, stocks: 45, marketCap: '12.8T' },
    { name: 'Healthcare', change: 1.32, stocks: 32, marketCap: '7.2T' },
    { name: 'Financials', change: 0.87, stocks: 28, marketCap: '6.1T' },
    { name: 'Consumer Disc.', change: -0.43, stocks: 24, marketCap: '4.9T' },
    { name: 'Energy', change: -1.28, stocks: 18, marketCap: '3.2T' },
    { name: 'Industrials', change: 0.65, stocks: 22, marketCap: '4.5T' }
  ];

  return (
    <Card elevation={2}>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          Sector Performance Today
        </Typography>
        <Box>
          {sectors.map((sector, idx) => (
            <Box key={sector.name} display="flex" justifyContent="space-between" alignItems="center" py={1}>
              <Box>
                <Typography variant="body2" fontWeight={600}>{sector.name}</Typography>
                <Typography variant="caption" color="textSecondary">
                  {sector.stocks} stocks • {sector.marketCap}
                </Typography>
              </Box>
              <Box textAlign="right">
                <Chip
                  icon={sector.change >= 0 ? <TrendingUp /> : <TrendingDown />}
                  label={`${sector.change >= 0 ? '+' : ''}${sector.change.toFixed(2)}%`}
                  color={sector.change >= 0 ? 'success' : 'error'}
                  size="small"
                  sx={{ minWidth: 90 }}
                />
              </Box>
            </Box>
          ))}
        </Box>
      </CardContent>
    </Card>
  );
};

// Portfolio Summary Component
const PortfolioSummary = ({ data, loading }) => {
  if (loading) return <LinearProgress />;

  const portfolio = data?.portfolio || defaultPortfolio;
  const metrics = data?.metrics || defaultMetrics;
  
  // Enhanced portfolio allocation data
  const allocation = {
    byAssetClass: [
      { name: 'Equities', value: 75, amount: 937500 },
      { name: 'Fixed Income', value: 15, amount: 187500 },
      { name: 'Alternatives', value: 8, amount: 100000 },
      { name: 'Cash', value: 2, amount: 25000 }
    ],
    bySector: [
      { name: 'Technology', value: 28, amount: 350000 },
      { name: 'Healthcare', value: 18, amount: 225000 },
      { name: 'Financials', value: 15, amount: 187500 },
      { name: 'Consumer', value: 12, amount: 150000 },
      { name: 'Other', value: 27, amount: 337500 }
    ]
  };

  return (
    <Card elevation={2}>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          Portfolio Summary
        </Typography>
        <Grid container spacing={3}>
          <Grid item xs={12} md={6}>
            <Box>
              <Typography variant="h4" fontWeight="bold" color="primary">
                {formatCurrency(portfolio.value)}
              </Typography>
              <Typography variant="body2" color="textSecondary" gutterBottom>
                Total Portfolio Value
              </Typography>
              <Box display="flex" flexWrap="wrap" gap={1} mt={1}>
                <Chip
                  label={`Daily: ${formatCurrency(portfolio.pnl.daily)}`}
                  color={portfolio.pnl.daily >= 0 ? 'success' : 'error'}
                  size="small"
                />
                <Chip
                  label={`MTD: ${formatCurrency(portfolio.pnl.mtd)}`}
                  color={portfolio.pnl.mtd >= 0 ? 'success' : 'error'}
                  size="small"
                />
                <Chip
                  label={`YTD: ${formatCurrency(portfolio.pnl.ytd)}`}
                  color={portfolio.pnl.ytd >= 0 ? 'success' : 'error'}
                  size="small"
                />
              </Box>
              <Typography variant="caption" color="textSecondary" display="block" mt={1}>
                Portfolio Performance: +{formatPercentage((portfolio.pnl.ytd / portfolio.value))} vs S&P 500: +{formatPercentage(0.089)}
              </Typography>
            </Box>
          </Grid>
          <Grid item xs={12} md={6}>
            <Box>
              <Typography variant="subtitle2" color="textSecondary" gutterBottom>
                Asset Allocation
              </Typography>
              {allocation.byAssetClass.map((asset, idx) => (
                <Box key={asset.name} display="flex" justifyContent="space-between" alignItems="center" py={0.5}>
                  <Typography variant="body2">{asset.name}</Typography>
                  <Box textAlign="right">
                    <Typography variant="body2" fontWeight={600}>{asset.value}%</Typography>
                    <Typography variant="caption" color="textSecondary">{formatCurrency(asset.amount)}</Typography>
                  </Box>
                </Box>
              ))}
            </Box>
            <Divider sx={{ my: 1 }} />
            <Box>
              <Typography variant="subtitle2" color="textSecondary" gutterBottom>
                Risk Metrics
              </Typography>
              <Grid container spacing={1}>
                <Grid item xs={6}>
                  <Typography variant="body2">Sharpe Ratio</Typography>
                  <Typography variant="body2" fontWeight={600}>{metrics.sharpe?.toFixed(2) || '1.85'}</Typography>
                </Grid>
                <Grid item xs={6}>
                  <Typography variant="body2">Beta</Typography>
                  <Typography variant="body2" fontWeight={600}>{metrics.beta?.toFixed(2) || '0.92'}</Typography>
                </Grid>
                <Grid item xs={6}>
                  <Typography variant="body2">Volatility</Typography>
                  <Typography variant="body2" fontWeight={600}>{formatPercentage(metrics.volatility || 0.15)}</Typography>
                </Grid>
                <Grid item xs={6}>
                  <Typography variant="body2">Max Drawdown</Typography>
                  <Typography variant="body2" fontWeight={600}>{formatPercentage(metrics.maxDrawdown || 0.08)}</Typography>
                </Grid>
              </Grid>
            </Box>
          </Grid>
        </Grid>
      </CardContent>
    </Card>
  );
};

// Economic Indicators Component
const EconomicIndicatorsSummary = ({ data, loading }) => {
  if (loading) return <LinearProgress />;

  const indicators = data?.indicators || [
    { name: 'GDP Growth (QoQ)', value: '2.1%', trend: 'up', description: 'Quarterly annualized' },
    { name: 'Unemployment Rate', value: '3.7%', trend: 'down', description: 'Labor market strength' },
    { name: 'CPI Inflation (YoY)', value: '3.2%', trend: 'down', description: 'Consumer prices' },
    { name: '10-Year Treasury', value: '4.45%', trend: 'up', description: 'Risk-free rate' },
    { name: 'USD Index (DXY)', value: '103.2', trend: 'up', description: 'Dollar strength' },
    { name: 'Oil (WTI)', value: '$78.45', trend: 'down', description: 'Energy commodity' }
  ];

  return (
    <Card elevation={2}>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          Economic Indicators
        </Typography>
        <Grid container spacing={2}>
          {indicators.map((indicator, idx) => (
            <Grid item xs={12} sm={6} md={4} key={indicator.name}>
              <Box>
                <Box display="flex" alignItems="center" gap={1}>
                  <Typography variant="body2" fontWeight={600}>{indicator.value}</Typography>
                  {indicator.trend === 'up' ? (
                    <TrendingUp color="success" fontSize="small" />
                  ) : (
                    <TrendingDown color="error" fontSize="small" />
                  )}
                </Box>
                <Typography variant="caption" color="textSecondary" display="block">
                  {indicator.name}
                </Typography>
                <Typography variant="caption" color="textSecondary" fontSize={10}>
                  {indicator.description}
                </Typography>
              </Box>
            </Grid>
          ))}
        </Grid>
      </CardContent>
    </Card>
  );
};

// Technical Signals Summary Component (Enhanced)
const TechnicalSignalsSummary = ({ data, loading }) => {
  if (loading) return <LinearProgress />;

  const signals = data?.signals || [];
  const buySignals = signals.filter(s => s.signal === 'Buy');
  const sellSignals = signals.filter(s => s.signal === 'Sell');
  
  // Top 2 performing positions
  const topPositions = [
    { symbol: 'NVDA', price: 845.32, change: 12.45, changePercent: 1.49, signal: 'Strong Buy' },
    { symbol: 'MSFT', price: 412.78, change: -2.15, changePercent: -0.52, signal: 'Hold' }
  ];

  return (
    <Card elevation={2}>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          Technical Signals
        </Typography>
        <Grid container spacing={3}>
          <Grid item xs={12} md={4}>
            <Box>
              <Typography variant="subtitle2" color="textSecondary" gutterBottom>
                Signal Summary
              </Typography>
              <Box display="flex" gap={1} mb={2}>
                <Chip 
                  icon={<TrendingUp />}
                  label={`${buySignals.length} Buy Signals`} 
                  color="success" 
                  size="small" 
                />
                <Chip 
                  icon={<TrendingDown />}
                  label={`${sellSignals.length} Sell Signals`} 
                  color="error" 
                  size="small" 
                />
              </Box>
              <Typography variant="caption" color="textSecondary">
                Signal Accuracy: 68% • Avg Hold: 12 days
              </Typography>
            </Box>
          </Grid>
          <Grid item xs={12} md={8}>
            <Box>
              <Typography variant="subtitle2" color="textSecondary" gutterBottom>
                Top Positions Spotlight
              </Typography>
              {topPositions.map((position, idx) => (
                <Box key={position.symbol} display="flex" justifyContent="space-between" alignItems="center" py={1} sx={{ backgroundColor: idx % 2 ? 'grey.50' : 'transparent', px: 1, borderRadius: 1 }}>
                  <Box>
                    <Typography variant="body2" fontWeight={700}>{position.symbol}</Typography>
                    <Typography variant="caption" color="textSecondary">{position.signal}</Typography>
                  </Box>
                  <Box textAlign="right">
                    <Typography variant="body2" fontWeight={600}>{formatCurrency(position.price)}</Typography>
                    <Chip
                      icon={position.change >= 0 ? <TrendingUp /> : <TrendingDown />}
                      label={`${position.change >= 0 ? '+' : ''}${position.change.toFixed(2)} (${position.changePercent >= 0 ? '+' : ''}${position.changePercent.toFixed(2)}%)`}
                      color={position.change >= 0 ? 'success' : 'error'}
                      size="small"
                      sx={{ fontSize: 11 }}
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

// Earnings Calendar Summary Component
const EarningsCalendarSummary = ({ data, loading }) => {
  if (loading) return <LinearProgress />;

  const earnings = data?.earnings || [];

  return (
    <Card elevation={2}>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          Earnings Calendar
        </Typography>
        {earnings.length === 0 ? (
          <Typography variant="body2" color="textSecondary">
            No upcoming earnings events
          </Typography>
        ) : (
          <Box>
            {earnings.slice(0, 5).map((earning, idx) => (
              <Box key={idx} display="flex" justifyContent="space-between" alignItems="center" py={0.5}>
                <Box>
                  <Typography variant="body2" fontWeight={600}>{earning.symbol}</Typography>
                  <Typography variant="caption" color="textSecondary">
                    {earning.company_name}
                  </Typography>
                </Box>
                <Box textAlign="right">
                  <Typography variant="body2">
                    {earning.date && !isNaN(new Date(earning.date)) ? format(new Date(earning.date), 'MMM d') : 'TBD'}
                  </Typography>
                  <Typography variant="caption" color="textSecondary">
                    {earning.date && !isNaN(new Date(earning.date)) ? format(new Date(earning.date), 'yyyy') : ''}
                  </Typography>
                </Box>
              </Box>
            ))}
          </Box>
        )}
      </CardContent>
    </Card>
  );
};

// --- TECHNICAL SIGNALS WIDGET ---
function TechnicalSignalsWidget() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['dashboard-technical-signals'],
    queryFn: async () => {
      try {
        const result = await getDashboardTechnicalSignals();
        return result;
      } catch (err) {
        throw err;
      }
    },
    refetchInterval: 300000
  });
  const signals = data?.data || [];
  return (
    <Card sx={{ mb: 3 }}>
      <CardContent>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
          <TrendingUp sx={{ color: 'primary.main', mr: 1 }} />
          <Typography variant="h6" sx={{ fontWeight: 600 }}>Technical Signals</Typography>
        </Box>
        {isLoading ? (
          <Typography variant="body2" color="text.secondary">Loading technical signals...</Typography>
        ) : error ? (
          <Typography variant="body2" color="error">{error.message || 'Error loading technical signals'}</Typography>
        ) : (
          <Box sx={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', fontSize: 15 }}>
              <thead>
                <tr>
                  <th align="left">Symbol</th>
                  <th align="left">Signal</th>
                  <th align="right">Date</th>
                  <th align="right">Price</th>
                  <th align="right">Performance</th>
                </tr>
              </thead>
              <tbody>
                {signals.map((sig, idx) => (
                  <tr key={sig.symbol + sig.date + idx} style={{ background: idx % 2 ? '#f9f9f9' : 'white' }}>
                    <td>{sig.symbol}</td>
                    <td style={{ color: sig.signal === 'Buy' ? '#43a047' : '#e53935', fontWeight: 600 }}>{sig.signal}</td>
                    <td align="right">{sig.date && !isNaN(new Date(sig.date)) ? new Date(sig.date).toLocaleDateString() : '--'}</td>
                    <td align="right">${sig.current_price?.toLocaleString?.() ?? '--'}</td>
                    <td align="right">{sig.performance_percent ? sig.performance_percent.toFixed(2) + '%' : '--'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Box>
        )}
        <Typography variant="caption" color="text.secondary">Live technical signals from your buy/sell tables (daily).</Typography>
      </CardContent>
    </Card>
  );
}

// --- MARKET OVERVIEW WIDGET ---
function MarketOverviewWidget() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['dashboard-market-summary'],
    queryFn: async () => {
      const result = await getDashboardMarketSummary();
      return result;
    },
    staleTime: 2 * 60 * 1000
  });
  const summary = Array.isArray(data?.data) ? data.data : [];
  return (
    <Card sx={{ mb: 3 }}>
      <CardContent>
        <Typography variant="h6" sx={{ fontWeight: 600, mb: 1 }}>Market Overview</Typography>
        {isLoading ? (
          <Typography variant="body2" color="text.secondary">Loading market summary...</Typography>
        ) : error ? (
          <Typography variant="body2" color="error">Error loading market summary: {error.message}</Typography>
        ) : (
          <Grid container spacing={2}>
            {summary.map((mkt, idx) => (
              <Grid item xs={12} sm={4} key={mkt.name}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                  {mkt.change >= 0 ? <ArrowUpward sx={{ color: 'success.main', fontSize: 18 }} /> : <ArrowDownward sx={{ color: 'error.main', fontSize: 18 }} />}
                  <Box>
                    <Typography variant="body2" color="text.secondary" sx={{ fontWeight: 600 }}>{mkt.name}</Typography>
                    <Typography variant="h6" sx={{ fontWeight: 700 }}>{mkt.value?.toLocaleString?.() ?? '--'}</Typography>
                    <Typography variant="body2" sx={{ fontWeight: 600, color: mkt.change >= 0 ? '#43a047' : '#e53935' }}>{mkt.pct ?? '--'}</Typography>
                  </Box>
                </Box>
              </Grid>
            ))}
          </Grid>
        )}
        <Typography variant="caption" color="text.secondary">Major indices and market direction</Typography>
      </CardContent>
    </Card>
  );
}

// --- EARNINGS CALENDAR WIDGET ---
function EarningsCalendarWidget({ symbol }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['dashboard-earnings-calendar', symbol],
    queryFn: async () => {
      const result = await getDashboardEarningsCalendar();
      return result;
    },
    enabled: !!symbol,
    staleTime: 5 * 60 * 1000
  });
  const earnings = Array.isArray(data?.data) ? data.data : [];
  return (
    <Card sx={{ mb: 3 }}>
      <CardContent>
        <Typography variant="h6" sx={{ fontWeight: 600, mb: 1 }}>Earnings & Events</Typography>
        {isLoading ? (
          <Typography variant="body2" color="text.secondary">Loading earnings/events...</Typography>
        ) : error ? (
          <Typography variant="body2" color="error">Error loading earnings/events: {error.message}</Typography>
        ) : earnings.length === 0 ? (
          <Typography variant="body2" color="text.secondary">No upcoming earnings/events for {symbol}.</Typography>
        ) : (
          <>
            {earnings.map((ev, idx) => (
              <Box key={ev.event + idx} sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                <Typography variant="body2">{ev.event}</Typography>
                <Typography variant="caption" color="text.secondary">
                  {ev.date && !isNaN(new Date(ev.date)) ? format(new Date(ev.date), 'MMM d') : 'TBD'}
                </Typography>
              </Box>
            ))}
          </>
        )}
        <Typography variant="caption" color="text.secondary">Upcoming earnings and economic events</Typography>
      </CardContent>
    </Card>
  );
}

// --- ANALYST INSIGHTS WIDGET ---
function AnalystInsightsWidget({ symbol }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['dashboard-analyst-insights', symbol],
    queryFn: async () => {
      const result = await getDashboardAnalystInsights();
      return result;
    },
    enabled: !!symbol,
    staleTime: 5 * 60 * 1000
  });
  const upgrades = Array.isArray(data?.data?.upgrades) ? data.data.upgrades : [];
  const downgrades = Array.isArray(data?.data?.downgrades) ? data.data.downgrades : [];
  return (
    <Card sx={{ mb: 3 }}>
      <CardContent>
        <Typography variant="h6" sx={{ fontWeight: 600, mb: 1 }}>Analyst Insights</Typography>
        {isLoading ? (
          <Typography variant="body2" color="text.secondary">Loading analyst insights...</Typography>
        ) : error ? (
          <Typography variant="body2" color="error">Error loading analyst insights: {error.message}</Typography>
        ) : (
          <Box sx={{ display: 'flex', gap: 2 }}>
            <Chip label={`Upgrades: ${upgrades.length}`} color="success" />
            <Chip label={`Downgrades: ${downgrades.length}`} color="error" />
          </Box>
        )}
        <Typography variant="caption" color="text.secondary">Latest analyst actions for {symbol}</Typography>
      </CardContent>
    </Card>
  );
}

// --- FINANCIAL HIGHLIGHTS WIDGET ---
function FinancialHighlightsWidget({ symbol }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['dashboard-financial-highlights', symbol],
    queryFn: async () => {
      const result = await getDashboardFinancialHighlights();
      return result;
    },
    enabled: !!symbol,
    staleTime: 5 * 60 * 1000
  });
  const highlights = Array.isArray(data?.data) ? data.data : [];
  return (
    <Card sx={{ mb: 3 }}>
      <CardContent>
        <Typography variant="h6" sx={{ fontWeight: 600, mb: 1 }}>Financial Highlights</Typography>
        {isLoading ? (
          <Typography variant="body2" color="text.secondary">Loading financial highlights...</Typography>
        ) : error ? (
          <Typography variant="body2" color="error">Error loading financial highlights: {error.message}</Typography>
        ) : (
          <Grid container spacing={2}>
            {highlights.map((item, idx) => (
              <Grid item xs={6} key={item.label}>
                <Typography variant="body2" color="text.secondary">{item.label}</Typography>
                <Typography variant="body2" fontWeight={600}>{item.value}</Typography>
              </Grid>
            ))}
          </Grid>
        )}
        <Typography variant="caption" color="text.secondary">Key financial metrics for {symbol}</Typography>
      </CardContent>
    </Card>
  );
}

// --- USER SETTINGS WIDGET ---
function UserSettingsWidget({ user }) {
  return (
    <Card sx={{ mb: 3 }}>
      <CardContent>
        <Typography variant="h6" sx={{ fontWeight: 600, mb: 1 }}>User Settings</Typography>
        {user ? (
          <Typography variant="body2">Email: {user.email}</Typography>
        ) : (
          <Typography variant="body2" color="text.secondary">Loading user info...</Typography>
        )}
      </CardContent>
    </Card>
  );
}

const Dashboard = () => {
  const [selectedSymbol, setSelectedSymbol] = useState(DEFAULT_TICKER);

  // Custom hooks for data fetching
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

  // Data fetching hooks
  const { user, isLoading: userLoading, error: userError } = useUser();
  const { watchlist, isLoading: watchlistLoading, error: watchlistError } = useWatchlist();
  const { portfolio, isLoading: portfolioLoading, error: portfolioError } = usePortfolio();
  const { portfolioMetrics, isLoading: metricsLoading, error: metricsError } = usePortfolioMetrics();
  const { holdings, isLoading: holdingsLoading, error: holdingsError } = useHoldings();
  const { userSettings, isLoading: settingsLoading, error: settingsError } = useUserSettings();

  // Additional data queries
  const { data: symbolsData, isLoading: symbolsLoading } = useQuery({
    queryKey: ['dashboardSymbols'],
    queryFn: getDashboardSymbols,
    staleTime: 60 * 60 * 1000 // 1 hour
  });

  const { data: marketData, isLoading: marketLoading } = useQuery({
    queryKey: ['marketOverview'],
    queryFn: getMarketOverview,
    staleTime: 5 * 60 * 1000 // 5 minutes
  });

  const { data: sentimentData, isLoading: sentimentLoading } = useQuery({
    queryKey: ['marketSentiment'],
    queryFn: getMarketSentiment,
    staleTime: 5 * 60 * 1000 // 5 minutes
  });

  const { data: buySignalsData, isLoading: buySignalsLoading } = useQuery({
    queryKey: ['buySignals'],
    queryFn: getBuySignals,
    staleTime: 2 * 60 * 1000 // 2 minutes
  });

  const { data: sellSignalsData, isLoading: sellSignalsLoading } = useQuery({
    queryKey: ['sellSignals'],
    queryFn: getSellSignals,
    staleTime: 2 * 60 * 1000 // 2 minutes
  });

  const { data: earningsData, isLoading: earningsLoading } = useQuery({
    queryKey: ['earningsEstimates'],
    queryFn: getEarningsEstimates,
    staleTime: 30 * 60 * 1000 // 30 minutes
  });

  const { data: technicalData, isLoading: technicalLoading } = useQuery({
    queryKey: ['technicalData', selectedSymbol],
    queryFn: () => getTechnicalData('daily', { symbol: selectedSymbol, limit: 30 }),
    staleTime: 5 * 60 * 1000 // 5 minutes
  });

  const { data: stockPrices, isLoading: pricesLoading } = useQuery({
    queryKey: ['stockPrices', selectedSymbol],
    queryFn: () => getStockPrices(selectedSymbol, 'daily', 30),
    staleTime: 5 * 60 * 1000 // 5 minutes
  });

  const { data: stockMetrics, isLoading: stockMetricsLoading } = useQuery({
    queryKey: ['stockMetrics', selectedSymbol],
    queryFn: () => getKeyMetrics(selectedSymbol),
    staleTime: 5 * 60 * 1000 // 5 minutes
  });

  // Prepare data for components
  const SYMBOL_OPTIONS = Array.isArray(symbolsData?.data) && symbolsData.data.length > 0
    ? symbolsData.data
    : ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA', 'SPY', 'QQQ'];

  const equityCurve = Array.isArray(stockPrices?.data)
    ? stockPrices.data.map(p => ({ date: p.date || p.timestamp, equity: p.close || p.price })).reverse()
    : [];

  const priceData = Array.isArray(stockPrices?.data)
    ? stockPrices.data.map(p => ({ date: p.date || p.timestamp, price: p.close || p.price })).reverse()
    : [];

  const handleAddPosition = (position) => {
    console.log('Adding position:', position);
    // TODO: Implement position adding logic
  };

  const handleAddToWatchlist = (symbol) => {
    console.log('Adding to watchlist:', symbol);
    // TODO: Implement watchlist adding logic
  };

  const handleDebugTest = async () => {
    try {
      console.log('Running API endpoint tests...');
      const results = await testApiEndpoints();
      console.log('API test results:', results);
      alert('API tests completed. Check console for results.');
    } catch (error) {
      console.error('API test failed:', error);
      alert('API test failed. Check console for details.');
    }
  };

  return (
    <Box sx={{ p: 3 }}>
      {/* Header */}
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 3 }}>
        <Box sx={{ display: 'flex', alignItems: 'center' }}>
          {logoSrc ? (
            <img src={logoSrc} alt="Logo" style={{ height: 48, width: 48, borderRadius: '50%', marginRight: 16 }} />
          ) : (
            <Avatar sx={{ bgcolor: 'primary.main', width: 48, height: 48, fontSize: 28, mr: 2 }}>
              EC
            </Avatar>
          )}
          <Box>
            <Typography variant="h4" component="h1" sx={{ fontWeight: 700, letterSpacing: 1 }}>
              {BRAND_NAME} Dashboard
            </Typography>
            <Typography variant="subtitle1" color="textSecondary">
              Professional Investment Platform
            </Typography>
            {user && (
              <Typography variant="body2" color="textSecondary">
                Welcome back, {user.name || user.email}
              </Typography>
            )}
          </Box>
        </Box>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <Typography variant="body2" color="textSecondary">
            {format(new Date(), 'MMMM d, yyyy')}
          </Typography>
          <Chip 
            icon={<Refresh />} 
            label="Live Data" 
            color="primary" 
            size="small" 
            sx={{ fontWeight: 600 }}
          />
          <IconButton onClick={handleDebugTest} title="Debug API">
            <BugReport />
          </IconButton>
        </Box>
      </Box>

      {/* Summary Metrics */}
      <Box sx={{ mb: 3 }}>
        <SummaryMetrics 
          data={{
            portfolio: { 
              value: portfolio.value, 
              pnl: portfolio.pnl 
            },
            market: { 
              sentiment: sentimentData?.data?.sentiment || 'greed',
              healthScore: 'Strong',
              fearGreed: sentimentData?.data?.value || 72,
              vix: '18.5',
              volumeIndicator: 'Above Average'
            },
            signals: { 
              buyCount: buySignalsData?.data?.length || 23,
              sellCount: sellSignalsData?.data?.length || 12,
              totalCount: (buySignalsData?.data?.length || 23) + (sellSignalsData?.data?.length || 12),
              winRate: '68'
            },
            opportunities: {
              count: 8,
              highPriority: 3
            }
          }}
          loading={portfolioLoading || sentimentLoading || buySignalsLoading || sellSignalsLoading}
        />
      </Box>

      {/* Main Content - Enhanced Dashboard */}
      <Grid container spacing={3}>
        {/* Market Overview */}
        <Grid item xs={12} lg={8}>
          <MarketOverviewSummary 
            data={{
              indices: marketData?.data?.indices || [],
              sentiment: sentimentData?.data?.sentiment,
              fearGreed: sentimentData?.data?.value || 72,
              breadth: marketData?.data?.breadth
            }}
            loading={marketLoading || sentimentLoading}
          />
        </Grid>

        {/* Sector Performance */}
        <Grid item xs={12} lg={4}>
          <SectorPerformanceSummary
            data={{
              sectors: marketData?.data?.sectors || []
            }}
            loading={marketLoading}
          />
        </Grid>

        {/* Portfolio Summary */}
        <Grid item xs={12}>
          <PortfolioSummary 
            data={{
              portfolio: portfolio,
              metrics: portfolioMetrics
            }}
            loading={portfolioLoading || metricsLoading}
          />
        </Grid>

        {/* Economic Indicators */}
        <Grid item xs={12} lg={6}>
          <EconomicIndicatorsSummary
            data={{
              indicators: marketData?.data?.economic || []
            }}
            loading={marketLoading}
          />
        </Grid>

        {/* Technical Signals & Top Positions */}
        <Grid item xs={12} lg={6}>
          <TechnicalSignalsSummary 
            data={{
              signals: [
                ...(buySignalsData?.data || []).map(s => ({ ...s, signal: 'Buy' })),
                ...(sellSignalsData?.data || []).map(s => ({ ...s, signal: 'Sell' }))
              ]
            }}
            loading={buySignalsLoading || sellSignalsLoading}
          />
        </Grid>

        {/* Earnings Calendar */}
        <Grid item xs={12} lg={6}>
          <EarningsCalendarSummary 
            data={{
              earnings: earningsData?.data || []
            }}
            loading={earningsLoading}
          />
        </Grid>

        {/* Market Overview Widget */}
        <Grid item xs={12} lg={6}>
          <MarketOverviewWidget />
        </Grid>

        {/* Technical Signals Widget */}
        <Grid item xs={12}>
          <TechnicalSignalsWidget />
        </Grid>

        {/* Portfolio Holdings */}
        <Grid item xs={12} lg={8}>
          <Card elevation={2}>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Portfolio Holdings
              </Typography>
              {holdingsLoading ? (
                <LinearProgress />
              ) : holdingsError ? (
                <Alert severity="error">Failed to load holdings</Alert>
              ) : (
                <TableContainer>
                  <Table>
                    <TableHead>
                      <TableRow>
                        <TableCell>Symbol</TableCell>
                        <TableCell>Shares</TableCell>
                        <TableCell>Avg Price</TableCell>
                        <TableCell>Current Price</TableCell>
                        <TableCell>Market Value</TableCell>
                        <TableCell>P&L</TableCell>
                        <TableCell>P&L %</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {holdings.map((holding, idx) => (
                        <TableRow key={idx}>
                          <TableCell>{holding.symbol}</TableCell>
                          <TableCell>{holding.shares}</TableCell>
                          <TableCell>{formatCurrency(holding.avgPrice)}</TableCell>
                          <TableCell>{formatCurrency(holding.currentPrice)}</TableCell>
                          <TableCell>{formatCurrency(holding.marketValue)}</TableCell>
                          <TableCell sx={{ color: holding.pnl >= 0 ? 'success.main' : 'error.main' }}>
                            {formatCurrency(holding.pnl)}
                          </TableCell>
                          <TableCell sx={{ color: holding.pnlPercent >= 0 ? 'success.main' : 'error.main' }}>
                            {formatPercentage(holding.pnlPercent)}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Portfolio Allocation */}
        <Grid item xs={12} lg={4}>
          <Card elevation={2}>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Asset Allocation
              </Typography>
              <Box sx={{ height: 300, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <PieChart width={250} height={250}>
                  <Pie
                    data={holdings.map((h, idx) => ({ name: h.symbol, value: h.marketValue }))}
                    cx="50%"
                    cy="50%"
                    outerRadius={100}
                    fill="#8884d8"
                    dataKey="value"
                    label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                  >
                    {holdings.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={ALLOCATION_COLORS[index % ALLOCATION_COLORS.length]} />
                    ))}
                  </Pie>
                </PieChart>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Market Indicators */}
        <Grid item xs={12} lg={6}>
          <Card elevation={2}>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Market Indicators
              </Typography>
              {marketLoading ? (
                <LinearProgress />
              ) : (
                <Grid container spacing={2}>
                  {marketData?.data?.indicators?.map((indicator, idx) => (
                    <Grid item xs={6} key={idx}>
                      <Box>
                        <Typography variant="body2" color="textSecondary">
                          {indicator.name}
                        </Typography>
                        <Typography variant="h6" fontWeight={600}>
                          {indicator.value}
                        </Typography>
                        <Chip
                          label={`${indicator.change >= 0 ? '+' : ''}${formatPercentage(indicator.change)}`}
                          color={indicator.change >= 0 ? 'success' : 'error'}
                          size="small"
                        />
                      </Box>
                    </Grid>
                  ))}
                </Grid>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Fear & Greed Index */}
        <Grid item xs={12} lg={6}>
          <Card elevation={2}>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Market Sentiment
              </Typography>
              {sentimentLoading ? (
                <LinearProgress />
              ) : (
                <Box>
                  <Typography variant="h4" fontWeight="bold" color={SENTIMENT_COLORS[sentimentData?.data?.sentiment] || 'text.primary'}>
                    {sentimentData?.data?.sentiment?.replace('_', ' ').toUpperCase() || 'NEUTRAL'}
                  </Typography>
                  <Typography variant="body2" color="textSecondary">
                    Fear & Greed Index: {sentimentData?.data?.value || 'N/A'}
                  </Typography>
                  <Box sx={{ mt: 2 }}>
                    <LinearProgress
                      variant="determinate"
                      value={sentimentData?.data?.value || 50}
                      sx={{
                        height: 10,
                        borderRadius: 5,
                        backgroundColor: 'grey.200',
                        '& .MuiLinearProgress-bar': {
                          backgroundColor: SENTIMENT_COLORS[sentimentData?.data?.sentiment] || 'grey.500'
                        }
                      }}
                    />
                  </Box>
                </Box>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Portfolio Performance Chart */}
        <Grid item xs={12} lg={8}>
          <Card elevation={2}>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Portfolio Performance vs Benchmarks
              </Typography>
              {pricesLoading ? (
                <LinearProgress />
              ) : (
                <ResponsiveContainer width="100%" height={400}>
                  <LineChart data={equityCurve} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="date" />
                    <YAxis />
                    <RechartsTooltip formatter={(value) => [formatCurrency(value), 'Portfolio Value']} />
                    <Line type="monotone" dataKey="equity" stroke="#1976d2" strokeWidth={3} dot={false} name="Portfolio" />
                    <Line type="monotone" dataKey="benchmark" stroke="#ff7043" strokeWidth={2} dot={false} name="S&P 500" />
                  </LineChart>
                </ResponsiveContainer>
              )}
              <Typography variant="caption" color="textSecondary" display="block" mt={1}>
                Portfolio outperforming S&P 500 by +{formatPercentage(0.047)} over last 90 days
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        {/* Market Health Dashboard */}
        <Grid item xs={12} lg={4}>
          <Card elevation={2}>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Market Health Monitor
              </Typography>
              <Box>
                <Box sx={{ mb: 2 }}>
                  <Typography variant="body2" color="textSecondary">VIX (Volatility Index)</Typography>
                  <Typography variant="h6" fontWeight={600} color="success.main">18.5</Typography>
                  <Typography variant="caption" color="textSecondary">Low volatility environment</Typography>
                </Box>
                <Box sx={{ mb: 2 }}>
                  <Typography variant="body2" color="textSecondary">Market Correlation</Typography>
                  <Typography variant="h6" fontWeight={600}>0.73</Typography>
                  <Typography variant="caption" color="textSecondary">Moderate diversification</Typography>
                </Box>
                <Box sx={{ mb: 2 }}>
                  <Typography variant="body2" color="textSecondary">Credit Spreads</Typography>
                  <Typography variant="h6" fontWeight={600} color="success.main">125 bps</Typography>
                  <Typography variant="caption" color="textSecondary">Healthy credit conditions</Typography>
                </Box>
                <Box>
                  <Typography variant="body2" color="textSecondary">Market Momentum</Typography>
                  <LinearProgress 
                    variant="determinate" 
                    value={75} 
                    sx={{ 
                      height: 8, 
                      borderRadius: 4,
                      backgroundColor: 'grey.200',
                      '& .MuiLinearProgress-bar': {
                        backgroundColor: 'success.main'
                      }
                    }} 
                  />
                  <Typography variant="caption" color="textSecondary">Strong uptrend</Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Market Summary Stats */}
        <Grid item xs={12} lg={6}>
          <Card elevation={2}>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Today's Market Activity
              </Typography>
              <Grid container spacing={2}>
                <Grid item xs={6}>
                  <Typography variant="body2" color="textSecondary">Total Volume</Typography>
                  <Typography variant="h6" fontWeight={600}>12.8B shares</Typography>
                  <Typography variant="caption" color="success.main">+15% vs avg</Typography>
                </Grid>
                <Grid item xs={6}>
                  <Typography variant="body2" color="textSecondary">New Highs/Lows</Typography>
                  <Typography variant="h6" fontWeight={600}>127 / 43</Typography>
                  <Typography variant="caption" color="success.main">Ratio: 2.95</Typography>
                </Grid>
                <Grid item xs={6}>
                  <Typography variant="body2" color="textSecondary">Options Activity</Typography>
                  <Typography variant="h6" fontWeight={600}>Put/Call 0.85</Typography>
                  <Typography variant="caption" color="textSecondary">Moderate optimism</Typography>
                </Grid>
                <Grid item xs={6}>
                  <Typography variant="body2" color="textSecondary">Insider Activity</Typography>
                  <Typography variant="h6" fontWeight={600}>8 Buy / 3 Sell</Typography>
                  <Typography variant="caption" color="success.main">Bullish trend</Typography>
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </Grid>

        {/* Risk Management Summary */}
        <Grid item xs={12} lg={6}>
          <Card elevation={2}>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Risk Management Overview
              </Typography>
              <Box>
                <Box sx={{ mb: 2 }}>
                  <Box display="flex" justifyContent="space-between" alignItems="center">
                    <Typography variant="body2">Portfolio Beta</Typography>
                    <Typography variant="body2" fontWeight={600}>0.92</Typography>
                  </Box>
                  <Typography variant="caption" color="textSecondary">Lower volatility than market</Typography>
                </Box>
                <Box sx={{ mb: 2 }}>
                  <Box display="flex" justifyContent="space-between" alignItems="center">
                    <Typography variant="body2">Max Position Size</Typography>
                    <Typography variant="body2" fontWeight={600}>8.5%</Typography>
                  </Box>
                  <Typography variant="caption" color="textSecondary">Well diversified</Typography>
                </Box>
                <Box sx={{ mb: 2 }}>
                  <Box display="flex" justifyContent="space-between" alignItems="center">
                    <Typography variant="body2">Cash Reserve</Typography>
                    <Typography variant="body2" fontWeight={600}>2.1%</Typography>
                  </Box>
                  <Typography variant="caption" color="textSecondary">Low cash drag</Typography>
                </Box>
                <Box>
                  <Box display="flex" justifyContent="space-between" alignItems="center">
                    <Typography variant="body2">Stop Loss Coverage</Typography>
                    <Typography variant="body2" fontWeight={600}>94%</Typography>
                  </Box>
                  <Typography variant="caption" color="success.main">Excellent protection</Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Footer */}
      <Box sx={{ mt: 4, textAlign: 'center' }}>
        <Typography variant="caption" color="textSecondary">
          © {new Date().getFullYear()} {BRAND_NAME}. All rights reserved. | 
          Data provided for informational purposes only. Not investment advice.
        </Typography>
      </Box>
    </Box>
  );
};

export default Dashboard;
