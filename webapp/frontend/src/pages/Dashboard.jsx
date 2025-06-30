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
              {data?.indices?.map((index, idx) => (
                <Box key={index.symbol} display="flex" justifyContent="space-between" alignItems="center" py={0.5}>
                  <Typography variant="body2" fontWeight={600}>{index.symbol}</Typography>
                  <Box display="flex" alignItems="center" gap={1}>
                    <Typography variant="body2">{formatCurrency(index.value)}</Typography>
                    <Chip
                      icon={index.change >= 0 ? <TrendingUp /> : <TrendingDown />}
                      label={`${formatPercentage(index.changePercent)}`}
                      color={index.change >= 0 ? 'success' : 'error'}
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
                <Typography variant="body2" fontWeight={600} textTransform="capitalize">
                  {data?.sentiment || 'Neutral'}
                </Typography>
              </Box>
              <Typography variant="caption" color="textSecondary">
                Based on Fear & Greed Index
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

  const portfolio = data?.portfolio || defaultPortfolio;
  const metrics = data?.metrics || defaultMetrics;

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
                {formatCurrency(portfolio.value)}
              </Typography>
              <Typography variant="body2" color="textSecondary">
                Total Portfolio Value
              </Typography>
              <Box display="flex" gap={1} mt={1}>
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
            </Box>
          </Grid>
          <Grid item xs={12} md={6}>
            <Box>
              <Typography variant="subtitle2" color="textSecondary" gutterBottom>
                Risk Metrics
              </Typography>
              <Grid container spacing={1}>
                <Grid item xs={6}>
                  <Typography variant="body2">Sharpe Ratio</Typography>
                  <Typography variant="body2" fontWeight={600}>{metrics.sharpe?.toFixed(2) || 'N/A'}</Typography>
                </Grid>
                <Grid item xs={6}>
                  <Typography variant="body2">Beta</Typography>
                  <Typography variant="body2" fontWeight={600}>{metrics.beta?.toFixed(2) || 'N/A'}</Typography>
                </Grid>
                <Grid item xs={6}>
                  <Typography variant="body2">Volatility</Typography>
                  <Typography variant="body2" fontWeight={600}>{formatPercentage(metrics.volatility)}</Typography>
                </Grid>
                <Grid item xs={6}>
                  <Typography variant="body2">Max Drawdown</Typography>
                  <Typography variant="body2" fontWeight={600}>{formatPercentage(metrics.maxDrawdown)}</Typography>
                </Grid>
              </Grid>
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
  const buySignals = signals.filter(s => s.signal === 'Buy');
  const sellSignals = signals.filter(s => s.signal === 'Sell');

  return (
    <Card elevation={2}>
      <CardContent>
        <Typography variant="h6" gutterBottom>
          Technical Signals
        </Typography>
        <Grid container spacing={2}>
          <Grid item xs={12} md={6}>
            <Box>
              <Typography variant="subtitle2" color="textSecondary">
                Buy Signals ({buySignals.length})
              </Typography>
              {buySignals.slice(0, 5).map((signal, idx) => (
                <Box key={idx} display="flex" justifyContent="space-between" alignItems="center" py={0.5}>
                  <Typography variant="body2" fontWeight={600}>{signal.symbol}</Typography>
                  <Box display="flex" alignItems="center" gap={1}>
                    <Typography variant="body2">{formatCurrency(signal.price)}</Typography>
                    <Chip
                      label={`${formatPercentage(signal.changePercent)}`}
                      color="success"
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
                Sell Signals ({sellSignals.length})
              </Typography>
              {sellSignals.slice(0, 5).map((signal, idx) => (
                <Box key={idx} display="flex" justifyContent="space-between" alignItems="center" py={0.5}>
                  <Typography variant="body2" fontWeight={600}>{signal.symbol}</Typography>
                  <Box display="flex" alignItems="center" gap={1}>
                    <Typography variant="body2">{formatCurrency(signal.price)}</Typography>
                    <Chip
                      label={`${formatPercentage(signal.changePercent)}`}
                      color="error"
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
                  <Typography variant="body2">{format(new Date(earning.date), 'MMM d')}</Typography>
                  <Typography variant="caption" color="textSecondary">
                    {format(new Date(earning.date), 'yyyy')}
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
                    <td align="right">{sig.date ? new Date(sig.date).toLocaleDateString() : ''}</td>
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
                <Typography variant="caption" color="text.secondary">{format(new Date(ev.date), 'MMM d')}</Typography>
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
  const [activeTab, setActiveTab] = useState(0);

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
          <Autocomplete
            options={SYMBOL_OPTIONS}
            value={selectedSymbol}
            onChange={(_, newValue) => newValue && setSelectedSymbol(newValue)}
            sx={{ width: 200 }}
            renderInput={(params) => <TextField {...params} label="Select Symbol" size="small" />}
          />
          <Typography variant="body2" color="textSecondary">
            {format(new Date(), 'MMMM d, yyyy')}
          </Typography>
          <IconButton onClick={handleDebugTest} title="Debug API">
            <BugReport />
          </IconButton>
        </Box>
      </Box>

      {/* Summary Metrics */}
      <Box sx={{ mb: 3 }}>
        <SummaryMetrics 
          data={{
            portfolio: { value: portfolio.value, pnl: portfolio.pnl },
            market: { sentiment: sentimentData?.data?.sentiment },
            signals: { 
              buyCount: buySignalsData?.data?.length || 0,
              totalCount: (buySignalsData?.data?.length || 0) + (sellSignalsData?.data?.length || 0)
            },
            earnings: { 
              todayCount: earningsData?.data?.length || 0,
              importantCount: earningsData?.data?.filter(e => e.importance === 'high')?.length || 0
            }
          }}
          loading={portfolioLoading || sentimentLoading || buySignalsLoading || sellSignalsLoading || earningsLoading}
        />
      </Box>

      {/* Main Content Tabs */}
      <Box sx={{ mb: 3 }}>
        <Tabs value={activeTab} onChange={(_, newValue) => setActiveTab(newValue)}>
          <Tab label="Overview" />
          <Tab label="Portfolio" />
          <Tab label="Market Analysis" />
          <Tab label="Technical Signals" />
          <Tab label="Earnings & Events" />
        </Tabs>
      </Box>

      {/* Tab Content */}
      {activeTab === 0 && (
        <Grid container spacing={3}>
          {/* Market Overview */}
          <Grid item xs={12} lg={6}>
            <MarketOverviewSummary 
              data={{
                indices: marketData?.data?.indices || [],
                sentiment: sentimentData?.data?.sentiment
              }}
              loading={marketLoading || sentimentLoading}
            />
          </Grid>

          {/* Portfolio Summary */}
          <Grid item xs={12} lg={6}>
            <PortfolioSummary 
              data={{
                portfolio: portfolio,
                metrics: portfolioMetrics
              }}
              loading={portfolioLoading || metricsLoading}
            />
          </Grid>

          {/* Technical Signals */}
          <Grid item xs={12}>
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
          <Grid item xs={12}>
            <EarningsCalendarSummary 
              data={{
                earnings: earningsData?.data || []
              }}
              loading={earningsLoading}
            />
          </Grid>
        </Grid>
      )}

      {activeTab === 1 && (
        <Grid container spacing={3}>
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
        </Grid>
      )}

      {activeTab === 2 && (
        <Grid container spacing={3}>
          {/* Market Overview Widget */}
          <Grid item xs={12}>
            <MarketOverviewWidget />
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
        </Grid>
      )}

      {activeTab === 3 && (
        <Grid container spacing={3}>
          {/* Technical Signals Widget */}
          <Grid item xs={12}>
            <TechnicalSignalsWidget />
          </Grid>

          {/* Technical Analysis Chart */}
          <Grid item xs={12} lg={8}>
            <Card elevation={2}>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Technical Analysis - {selectedSymbol}
                </Typography>
                {pricesLoading ? (
                  <LinearProgress />
                ) : (
                  <ResponsiveContainer width="100%" height={400}>
                    <LineChart data={priceData} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="date" />
                      <YAxis />
                      <RechartsTooltip formatter={(value) => [formatCurrency(value), 'Price']} />
                      <Line type="monotone" dataKey="price" stroke="#1976d2" strokeWidth={2} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                )}
              </CardContent>
            </Card>
          </Grid>

          {/* Technical Indicators */}
          <Grid item xs={12} lg={4}>
            <Card elevation={2}>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Technical Indicators
                </Typography>
                {technicalLoading ? (
                  <LinearProgress />
                ) : (
                  <Box>
                    {technicalData?.data?.indicators?.map((indicator, idx) => (
                      <Box key={idx} sx={{ mb: 2 }}>
                        <Typography variant="body2" color="textSecondary">
                          {indicator.name}
                        </Typography>
                        <Typography variant="h6" fontWeight={600}>
                          {indicator.value}
                        </Typography>
                        <Chip
                          label={indicator.signal}
                          color={indicator.signal === 'Buy' ? 'success' : indicator.signal === 'Sell' ? 'error' : 'default'}
                          size="small"
                        />
                      </Box>
                    ))}
                  </Box>
                )}
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      )}

      {activeTab === 4 && (
        <Grid container spacing={3}>
          {/* Earnings Calendar Widget */}
          <Grid item xs={12} lg={6}>
            <EarningsCalendarWidget symbol={selectedSymbol} />
          </Grid>

          {/* Analyst Insights Widget */}
          <Grid item xs={12} lg={6}>
            <AnalystInsightsWidget symbol={selectedSymbol} />
          </Grid>

          {/* Financial Highlights Widget */}
          <Grid item xs={12} lg={6}>
            <FinancialHighlightsWidget symbol={selectedSymbol} />
          </Grid>

          {/* User Settings Widget */}
          <Grid item xs={12} lg={6}>
            <UserSettingsWidget user={user} />
          </Grid>
        </Grid>
      )}

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
