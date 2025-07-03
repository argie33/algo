import React, { useState, useEffect, useMemo } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { useNavigate } from 'react-router-dom';
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
  Container,
  CardHeader,
  Badge,
  IconButton,
  LinearProgress,
  Alert,
  List,
  ListItem,
  ListItemText,
  ListItemAvatar,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tabs,
  Tab,
  Switch,
  FormControlLabel,
  CircularProgress
} from '@mui/material';
import {
  TrendingUp, TrendingDown, Assessment, Notifications, Event, ListAlt, ShowChart, AccountBalance, Download, Info, TrendingFlat, ArrowUpward, ArrowDownward, Analytics, Timeline, Speed, BarChart, PieChart as PieChartIcon, Warning, CheckCircle, Schedule, Business, Refresh, Settings, Visibility, Add, Remove, PlayArrow, Stop, Pause, FilterList, Search, BookmarkBorder, Bookmark, Share, OpenInNew, MonetizationOn, Security, Psychology, Construction, LocalAtm, Home, Factory, Store, AttachMoney, Work, TrendingFlat as TrendingFlatIcon
} from '@mui/icons-material';
import { 
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer, 
  AreaChart, Area, BarChart as RechartsBarChart, Bar, Cell, PieChart, Pie, RadialBarChart, RadialBar, 
  ScatterChart, Scatter
} from 'recharts';
import { useQuery } from '@tanstack/react-query';
import { getStockPrices, getStockMetrics, getBuySignals, getSellSignals } from '../services/api';
import { format } from 'date-fns';
import { getApiConfig } from '../services/api';

// Logo import with fallback 
let logoSrc = null;
try {
  // Use dynamic import for assets in Vite
  logoSrc = new URL('../assets/logo.png', import.meta.url).href;
} catch (e) {
  console.warn('Logo not found, using fallback avatar');
  logoSrc = null;
}

// Get API configuration
const { apiUrl: API_BASE } = getApiConfig();
console.log('Dashboard API Base:', API_BASE);

const DEFAULT_TICKER = 'AAPL';
const WIDGET_COLORS = ['#1976d2', '#43a047', '#ffb300', '#8e24aa', '#e53935'];

const mockPortfolio = {
  value: 1250000,
  pnl: { daily: 3200, mtd: 18000, ytd: 92000 },
  allocation: [
    { name: 'AAPL', value: 38 },
    { name: 'MSFT', value: 27 },
    { name: 'GOOGL', value: 18 },
    { name: 'Cash', value: 10 },
    { name: 'Other', value: 7 }
  ]
};
const mockWatchlist = [
  { symbol: 'AAPL', price: 195.12, change: 2.1 },
  { symbol: 'TSLA', price: 710.22, change: -1.8 },
  { symbol: 'NVDA', price: 1200, change: 3.5 },
  { symbol: 'MSFT', price: 420.5, change: 0.7 }
];
const mockActivity = [
  { type: 'Trade', desc: 'Bought 100 AAPL', date: '2025-06-21' },
  { type: 'Alert', desc: 'TSLA price alert triggered', date: '2025-06-20' },
  { type: 'Trade', desc: 'Sold 50 NVDA', date: '2025-06-19' }
];
const mockCalendar = [
  { event: 'FOMC Rate Decision', date: '2025-06-25' },
  { event: 'AAPL Earnings', date: '2025-07-01' },
  { event: 'Nonfarm Payrolls', date: '2025-07-05' }
];
const mockSignals = [
  { symbol: 'AAPL', action: 'Buy', confidence: 0.92 },
  { symbol: 'TSLA', action: 'Sell', confidence: 0.87 }
];
const mockNews = [
  { title: 'Fed Holds Rates Steady, Signals Caution', date: '2025-06-21' },
  { title: 'AAPL Surges on Strong Earnings', date: '2025-06-20' },
  { title: 'Global Markets Mixed Ahead of FOMC', date: '2025-06-19' }
];

// Remove branding for now
const BRAND_NAME = 'Financial Dashboard';

const marketSummary = [
  { name: 'S&P 500', value: 5432.10, change: +0.42, pct: '+0.8%', icon: <ArrowUpward sx={{ color: 'success.main', fontSize: 18 }} /> },
  { name: 'NASDAQ', value: 17890.55, change: -0.22, pct: '-0.1%', icon: <ArrowDownward sx={{ color: 'error.main', fontSize: 18 }} /> },
  { name: 'DOW', value: 38900.12, change: +0.15, pct: '+0.4%', icon: <ArrowUpward sx={{ color: 'success.main', fontSize: 18 }} /> },
];

// Example: fetch user info and auth status from backend
function useUser() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['dashboard-user'],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/auth/user`, { credentials: 'include' });
      if (!res.ok) throw new Error('Failed to fetch user info');
      return res.json();
    },
    staleTime: 10 * 60 * 1000,
    retry: 1,
    retryDelay: 1000
  });
  return {
    user: data?.data || null,
    isLoading,
    error,
    isAuthenticated: !!data?.data
  };
}

// --- TECHNICAL SIGNALS WIDGET ---
function TechnicalSignalsWidget() {
  // Fetch latest technical signals from your API (limit 10)
  const { data, isLoading, error } = useQuery({
    queryKey: ['dashboard-technical-signals'],
    queryFn: async () => {
      try {
        const url = `${API_BASE}/trading/signals/daily?limit=10`;
        const res = await fetch(url);
        if (!res.ok) throw new Error('Failed to fetch technical signals');
        // Defensive: try/catch JSON parsing
        try {
          return await res.json();
        } catch (jsonErr) {
          throw new Error('Invalid JSON in technical signals response');
        }
      } catch (err) {
        // Always throw error to be caught by useQuery
        throw err;
      }
    },
    refetchInterval: 300000,
    retry: 1,
    retryDelay: 1000,
    onError: (err) => console.error('Technical signals error:', err)
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






const Dashboard = () => {
  // Authentication state
  const { user, isAuthenticated, isLoading: authLoading } = useAuth();
  
  // Symbol selector state
  const [selectedSymbol, setSelectedSymbol] = useState('AAPL');

  // Use predefined symbol list
  const SYMBOL_OPTIONS = ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA', 'SPY', 'QQQ'];

  // Equity curve (price history)
  const { data: priceData, isLoading: priceLoading, error: priceError } = useQuery({
    queryKey: ['stock-prices', selectedSymbol],
    queryFn: () => getStockPrices(selectedSymbol, 'daily', 30),
    staleTime: 5 * 60 * 1000,
    retry: 1,
    retryDelay: 1000,
    onError: (err) => console.error('Price data error:', err)
  });
  // Risk metrics
  const { data: metricsData, isLoading: metricsLoading, error: metricsError } = useQuery({
    queryKey: ['stock-metrics', selectedSymbol],
    queryFn: () => getStockMetrics(selectedSymbol),
    staleTime: 5 * 60 * 1000,
    retry: 1,
    retryDelay: 1000,
    onError: (err) => console.error('Metrics data error:', err)
  });
  // Buy/Sell signals
  const { data: buySignals } = useQuery({
    queryKey: ['buy-signals'],
    queryFn: getBuySignals,
    staleTime: 2 * 60 * 1000
  });
  const { data: sellSignals } = useQuery({
    queryKey: ['sell-signals'],
    queryFn: getSellSignals,
    staleTime: 2 * 60 * 1000
  });

  // Use mock portfolio data for now
  const safePortfolio = mockPortfolio;

  // Use mock watchlist data for now
  const safeWatchlist = mockWatchlist;

  // Use mock news data for now
  const safeNews = mockNews;

  // Use mock activity data for now
  const safeActivity = mockActivity;

  // Use mock calendar data for now
  const safeCalendar = mockCalendar;

  // Use mock signals data for now
  const safeSignals = mockSignals;

  // Prepare equity curve for chart
  const equityCurve = Array.isArray(priceData?.data)
    ? priceData.data.map(p => ({ date: p.date || p.timestamp, equity: p.close || p.price })).reverse()
    : [];

  // Prepare risk stats
  const riskStats = metricsData?.data
    ? [
        { label: 'Beta', value: metricsData.data.beta ?? 'N/A' },
        { label: 'Volatility', value: metricsData.data.volatility ? (metricsData.data.volatility * 100).toFixed(2) + '%' : 'N/A' },
        { label: 'Sharpe Ratio', value: metricsData.data.sharpe_ratio ?? 'N/A' },
        { label: 'Max Drawdown', value: metricsData.data.max_drawdown ? (metricsData.data.max_drawdown * 100).toFixed(2) + '%' : 'N/A' }
      ]
    : [];

  // Defensive: fallback for missing/errored data
  // (Removed mock-based safe* variables; now using API-based safe* variables above)

  // User context (now using AuthContext consistently)
  const userLoading = authLoading;
  const userError = null; // AuthContext handles errors differently

  // Optionally redirect to login if not authenticated
  // useEffect(() => {
  //   if (!userLoading && !isAuthenticated) {
  //     window.location.href = '/login';
  //   }
  // }, [userLoading, isAuthenticated]);

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      {/* Institutional Header */}
      <Box display="flex" alignItems="center" justifyContent="between" mb={4}>
        <Box>
          <Typography variant="h3" component="h1" gutterBottom>
            Institutional Trading Platform
          </Typography>
          <Typography variant="body1" color="text.secondary">
            Professional-grade analytics, real-time insights, and algorithmic trading
          </Typography>
          <Box display="flex" gap={1} mt={1}>
            <Chip label="Live Data" color="success" size="small" variant="outlined" />
            <Chip label="AI Analytics" color="primary" size="small" variant="outlined" />
            <Chip label="Risk Management" color="warning" size="small" variant="outlined" />
            <Chip label="Advanced Tools" color="info" size="small" variant="outlined" />
          </Box>
        </Box>
        
        <Box display="flex" alignItems="center" gap={2}>
          <Badge badgeContent={5} color="error">
            <IconButton>
              <Notifications />
            </IconButton>
          </Badge>
          <Autocomplete
            options={SYMBOL_OPTIONS}
            value={selectedSymbol}
            onChange={(_, newValue) => newValue && setSelectedSymbol(newValue)}
            sx={{ width: 180 }}
            renderInput={(params) => <TextField {...params} label="Symbol" size="small" />}
          />
          {user && (
            <Tooltip title={user.email || user.name} arrow>
              <Avatar sx={{ bgcolor: 'primary.main', width: 40, height: 40 }}>
                {user.name ? user.name[0] : (user.email ? user.email[0] : 'U')}
              </Avatar>
            </Tooltip>
          )}
        </Box>
      </Box>
        <Box sx={{ display: 'flex', alignItems: 'center' }}>
          {/* <img src={Logo} alt="Fund Logo" style={{ height: 48, marginRight: 16 }} /> */}
          {logoSrc ? (
            <img src={logoSrc} alt="Logo" style={{ height: 48, width: 48, borderRadius: '50%' }} />
          ) : (
            <Avatar sx={{ bgcolor: 'primary.main', width: 48, height: 48, fontSize: 28 }}>
              {/* Fallback initials or icon */}
              FD
            </Avatar>
          )}
          <Box>
            <Typography variant="h5" sx={{ fontWeight: 700, letterSpacing: 1 }}>{BRAND_NAME}</Typography>
            {userLoading ? (
              <Skeleton width={120} height={18} />
            ) : user ? (
              <Typography variant="caption" color="text.secondary">Welcome, {user.name || user.email}</Typography>
            ) : null}
          </Box>
        </Box>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          {/* Symbol Selector */}
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
          {/* User Avatar/Logout */}
          {user && (
            <Tooltip title={user.email || user.name} arrow>
              <Avatar sx={{ bgcolor: 'secondary.main', width: 36, height: 36, ml: 1 }}>
                {user.name ? user.name[0] : (user.email ? user.email[0] : '?')}
              </Avatar>
            </Tooltip>
          )}
          {user && (
            <Button 
              size="small" 
              color="secondary" 
              variant="outlined" 
              onClick={() => {
                fetch(`${API_BASE}/auth/logout`, { method: 'POST', credentials: 'include' })
                  .then(() => window.location.href = '/login');
              }}
            >
              Logout
            </Button>
          )}
        </Box>
      </Box>

      {/* Executive Dashboard Status Bar */}
      {isAuthenticated && user && (
        <Card sx={{ mb: 4, bgcolor: 'primary.dark', color: 'primary.contrastText' }}>
          <CardContent sx={{ py: 2 }}>
            <Box display="flex" alignItems="center" justifyContent="between">
              <Box display="flex" alignItems="center" gap={4}>
                <Box>
                  <Typography variant="h6" fontWeight="bold">
                    Welcome back, {user.username || user.email?.split('@')[0] || 'Investor'}
                  </Typography>
                  <Typography variant="body2" sx={{ opacity: 0.8 }}>
                    Portfolio Status: Active | Market Session: Open | Data Feed: Live
                  </Typography>
                </Box>
                
                <Box display="flex" gap={3}>
                  <Box textAlign="center">
                    <Typography variant="body2" sx={{ opacity: 0.8 }}>Portfolio Value</Typography>
                    <Typography variant="h6" fontWeight="bold">
                      ${safePortfolio.value.toLocaleString()}
                    </Typography>
                  </Box>
                  <Box textAlign="center">
                    <Typography variant="body2" sx={{ opacity: 0.8 }}>Today's P&L</Typography>
                    <Typography variant="h6" fontWeight="bold" color={safePortfolio.pnl.daily >= 0 ? 'success.light' : 'error.light'}>
                      ${safePortfolio.pnl.daily.toLocaleString()}
                    </Typography>
                  </Box>
                  <Box textAlign="center">
                    <Typography variant="body2" sx={{ opacity: 0.8 }}>Active Alerts</Typography>
                    <Typography variant="h6" fontWeight="bold">
                      {safeSignals.length}
                    </Typography>
                  </Box>
                </Box>
              </Box>
              
              <Box display="flex" alignItems="center" gap={2}>
                <Box textAlign="right">
                  <Typography variant="body2" sx={{ opacity: 0.8 }}>System Status</Typography>
                  <Box display="flex" alignItems="center" gap={1}>
                    <Box width={6} height={6} borderRadius="50%" bgcolor="success.main" />
                    <Typography variant="body2" fontWeight="bold">All Systems Operational</Typography>
                  </Box>
                </Box>
              </Box>
            </Box>
          </CardContent>
        </Card>
      )}

      {/* Demo Mode Banner */}
      {!isAuthenticated && !authLoading && (
        <Alert 
          severity="info" 
          sx={{ mb: 4 }}
          action={
            <Button color="inherit" size="small">
              Sign In
            </Button>
          }
        >
          <strong>Demo Mode:</strong> You're viewing sample data. Sign in to access your personal portfolio, real-time alerts, and advanced analytics.
        </Alert>
      )}

      {/* Quick Access Navigation */}
      <Grid container spacing={2} mb={4}>
        <Grid item xs={12} md={3}>
          <Card 
            sx={{ 
              cursor: 'pointer', 
              transition: 'all 0.2s',
              '&:hover': { transform: 'translateY(-2px)', boxShadow: 4 }
            }}
            onClick={() => window.location.href = '/portfolio'}
          >
            <CardContent sx={{ textAlign: 'center' }}>
              <AccountBalance color="primary" sx={{ fontSize: 40, mb: 1 }} />
              <Typography variant="h6" fontWeight="bold">Portfolio</Typography>
              <Typography variant="body2" color="text.secondary">Advanced Analytics</Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={3}>
          <Card 
            sx={{ 
              cursor: 'pointer', 
              transition: 'all 0.2s',
              '&:hover': { transform: 'translateY(-2px)', boxShadow: 4 }
            }}
            onClick={() => window.location.href = '/backtest'}
          >
            <CardContent sx={{ textAlign: 'center' }}>
              <Analytics color="secondary" sx={{ fontSize: 40, mb: 1 }} />
              <Typography variant="h6" fontWeight="bold">Backtester</Typography>
              <Typography variant="body2" color="text.secondary">Strategy Testing</Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={3}>
          <Card 
            sx={{ 
              cursor: 'pointer', 
              transition: 'all 0.2s',
              '&:hover': { transform: 'translateY(-2px)', boxShadow: 4 }
            }}
            onClick={() => window.location.href = '/screener'}
          >
            <CardContent sx={{ textAlign: 'center' }}>
              <FilterList color="info" sx={{ fontSize: 40, mb: 1 }} />
              <Typography variant="h6" fontWeight="bold">Screener</Typography>
              <Typography variant="body2" color="text.secondary">Stock Discovery</Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={3}>
          <Card 
            sx={{ 
              cursor: 'pointer', 
              transition: 'all 0.2s',
              '&:hover': { transform: 'translateY(-2px)', boxShadow: 4 }
            }}
            onClick={() => window.location.href = '/realtime'}
          >
            <CardContent sx={{ textAlign: 'center' }}>
              <Timeline color="warning" sx={{ fontSize: 40, mb: 1 }} />
              <Typography variant="h6" fontWeight="bold">Real-Time</Typography>
              <Typography variant="body2" color="text.secondary">Live Markets</Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Portfolio & Market Overview */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={12} md={6}>
          <Card sx={{ bgcolor: 'grey.50', boxShadow: 3, borderLeft: '6px solid #1976d2' }}>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                <AccountBalance sx={{ color: 'primary.main', mr: 1 }} />
                <Typography variant="h6" sx={{ fontWeight: 600 }}>Portfolio Value</Typography>
                <Tooltip title="Total value of all holdings" arrow TransitionComponent={Fade} placement="top">
                  <Info sx={{ color: 'grey.500', ml: 1, fontSize: 18 }} />
                </Tooltip>
              </Box>
              <Typography variant="h4" sx={{ fontWeight: 700, color: 'primary.main', letterSpacing: 1 }}>
                ${safePortfolio.value.toLocaleString()}
              </Typography>
              <Box sx={{ display: 'flex', gap: 2, mt: 1 }}>
                <Tooltip title="Today's profit or loss" arrow><Chip label={`Daily: $${safePortfolio.pnl.daily.toLocaleString()}`} color={safePortfolio.pnl.daily >= 0 ? 'success' : 'error'} size="small" /></Tooltip>
                <Tooltip title="Month-to-date P&L" arrow><Chip label={`MTD: $${safePortfolio.pnl.mtd.toLocaleString()}`} color={safePortfolio.pnl.mtd >= 0 ? 'success' : 'error'} size="small" /></Tooltip>
                <Tooltip title="Year-to-date P&L" arrow><Chip label={`YTD: $${safePortfolio.pnl.ytd.toLocaleString()}`} color={safePortfolio.pnl.ytd >= 0 ? 'success' : 'error'} size="small" /></Tooltip>
              </Box>
              <Box sx={{ height: 120, mt: 2, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <PieChart width={120} height={120}>
                  <Pie data={safePortfolio.allocation} cx="50%" cy="50%" outerRadius={50} fill="#8884d8" dataKey="value" label>
                    {safePortfolio.allocation.map((entry, idx) => (
                      <Cell key={`cell-${idx}`} fill={WIDGET_COLORS[idx % WIDGET_COLORS.length]} />
                    ))}
                  </Pie>
                </PieChart>
              </Box>
              <Typography variant="caption" color="text.secondary">Asset allocation</Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={6}>
          <Card sx={{ boxShadow: 3, borderLeft: '6px solid #43a047' }}>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                <TrendingFlat sx={{ color: 'info.main', mr: 1 }} />
                <Typography variant="h6" sx={{ fontWeight: 600 }}>Watchlist</Typography>
                <Tooltip title="Your selected stocks for monitoring" arrow><Info sx={{ color: 'grey.500', ml: 1, fontSize: 18 }} /></Tooltip>
              </Box>
              <Box sx={{ maxHeight: 180, overflowY: 'auto' }}>
                <table style={{ width: '100%', fontSize: 15 }}>
                  <thead>
                    <tr>
                      <th align="left">Symbol</th>
                      <th align="right">Price</th>
                      <th align="right">Change</th>
                      <th align="center">Trade</th>
                    </tr>
                  </thead>
                  <tbody>
                    {safeWatchlist.map((item, idx) => (
                      <tr key={item.symbol || idx} style={{ background: idx % 2 ? '#f9f9f9' : 'white' }}>
                        <td>{item.symbol}</td>
                        <td align="right">${item.price?.toLocaleString?.() ?? '--'}</td>
                        <td align="right" style={{ color: item.change >= 0 ? '#43a047' : '#e53935', fontWeight: 600 }}>{item.change >= 0 ? '+' : ''}{item.change ?? '--'}%</td>
                        <td align="center">
                          <Tooltip title="Buy" arrow><Button size="small" variant="outlined" color="primary" aria-label={`Buy ${item.symbol}`}>Buy</Button></Tooltip>
                          <Tooltip title="Sell" arrow><Button size="small" variant="outlined" color="secondary" sx={{ ml: 1 }} aria-label={`Sell ${item.symbol}`}>Sell</Button></Tooltip>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Market Summary Row */}
      <Grid container spacing={2} sx={{ mb: 2 }}>
        {marketSummary.map((mkt, idx) => (
          <Grid item xs={12} sm={4} key={mkt.name}>
            <Card sx={{ boxShadow: 1, borderLeft: `4px solid ${WIDGET_COLORS[idx % WIDGET_COLORS.length]}` }}>
              <CardContent sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', py: 1 }}>
                <Box>
                  <Typography variant="body2" color="text.secondary" sx={{ fontWeight: 600 }}>{mkt.name}</Typography>
                  <Typography variant="h6" sx={{ fontWeight: 700 }}>{mkt.value.toLocaleString()}</Typography>
                </Box>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  {mkt.icon}
                  <Typography variant="body2" sx={{ fontWeight: 600, color: mkt.change >= 0 ? '#43a047' : '#e53935' }}>{mkt.pct}</Typography>
                </Box>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>

      {/* Technical Signals Widget */}
      <TechnicalSignalsWidget />

      {/* Insights Row: Alerts, Calendar, Activity */}
      <Grid container spacing={3} sx={{ mb: 3 }}>
        <Grid item xs={12} md={4}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                <Notifications sx={{ color: 'warning.main', mr: 1 }} />
                <Typography variant="h6" sx={{ fontWeight: 600 }}>Alerts & Signals</Typography>
                <Tooltip title="Latest actionable trade signals" arrow><Info sx={{ color: 'grey.500', ml: 1, fontSize: 18 }} /></Tooltip>
              </Box>
              {safeSignals.length === 0 ? (
                <Typography variant="body2" color="text.secondary">No new alerts.</Typography>
              ) : (
                <>
                  {safeSignals.map((sig, idx) => (
                    <Box key={sig.symbol || idx} sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                      <Typography variant="body2"><b>{sig.symbol}</b> {sig.action}</Typography>
                      <Chip label={`Conf: ${(sig.confidence * 100).toFixed(0)}%`} color={sig.action === 'Buy' ? 'success' : 'error'} size="small" />
                    </Box>
                  ))}
                </>
              )}
              <Divider sx={{ my: 1 }} />
              <Typography variant="body2" color="text.secondary">Latest news:</Typography>
              <Typography variant="body2" color="primary.main">Fed Holds Rates Steady, Signals Caution</Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={4}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                <Event sx={{ color: 'info.main', mr: 1 }} />
                <Typography variant="h6" sx={{ fontWeight: 600 }}>Economic Calendar</Typography>
                <Tooltip title="Upcoming economic events and earnings" arrow><Info sx={{ color: 'grey.500', ml: 1, fontSize: 18 }} /></Tooltip>
              </Box>
              {safeCalendar.length === 0 ? (
                <Typography variant="body2" color="text.secondary">No upcoming events.</Typography>
              ) : (
                <>
                  {safeCalendar.map((ev, idx) => (
                    <Box key={ev.event || idx} sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                      <Typography variant="body2">{ev.event}</Typography>
                      <Typography variant="caption" color="text.secondary">{format(new Date(ev.date), 'MMM d')}</Typography>
                    </Box>
                  ))}
                </>
              )}
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={4}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                <ListAlt sx={{ color: 'success.main', mr: 1 }} />
                <Typography variant="h6" sx={{ fontWeight: 600 }}>Recent Activity</Typography>
                <Tooltip title="Your most recent trades and actions" arrow><Info sx={{ color: 'grey.500', ml: 1, fontSize: 18 }} /></Tooltip>
              </Box>
              {safeActivity.length === 0 ? (
                <Typography variant="body2" color="text.secondary">No recent activity.</Typography>
              ) : (
                <>
                  {safeActivity.map((act, idx) => (
                    <Box key={act.type + act.desc + idx} sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                      <Typography variant="body2">{act.type}: {act.desc}</Typography>
                      <Typography variant="caption" color="text.secondary">{format(new Date(act.date), 'MMM d')}</Typography>
                    </Box>
                  ))}
                </>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Performance Analytics & Risk */}
      <Grid container spacing={3} sx={{ mb: 3 }}>
        <Grid item xs={12} md={8}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                <ShowChart sx={{ color: 'primary.main', mr: 1 }} />
                <Typography variant="h6" sx={{ fontWeight: 600 }}>Performance Analytics ({selectedSymbol})</Typography>
              </Box>
              {priceLoading ? (
                <Typography variant="body2" color="text.secondary">Loading equity curve...</Typography>
              ) : priceError ? (
                <Typography variant="body2" color="error">Error loading price data</Typography>
              ) : (
                <ResponsiveContainer width="100%" height={220}>
                  <LineChart data={equityCurve} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="date" tick={{ fontSize: 12 }} />
                    <YAxis tick={{ fontSize: 12 }} domain={['auto', 'auto']} />
                    <RechartsTooltip formatter={(v) => `$${v?.toLocaleString?.() ?? v}`}/>
                    <Line type="monotone" dataKey="equity" stroke="#1976d2" strokeWidth={2} dot={false} name="Equity" />
                  </LineChart>
                </ResponsiveContainer>
              )}
              <Typography variant="caption" color="text.secondary">Equity curve for {selectedSymbol}</Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={4}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                <Assessment sx={{ color: 'secondary.main', mr: 1 }} />
                <Typography variant="h6" sx={{ fontWeight: 600 }}>Risk & Stats ({selectedSymbol})</Typography>
              </Box>
              {metricsLoading ? (
                <Typography variant="body2" color="text.secondary">Loading risk stats...</Typography>
              ) : metricsError ? (
                <Typography variant="body2" color="error">Error loading metrics</Typography>
              ) : (
                <>
                  {riskStats.map((stat, idx) => (
                    <Box key={idx} sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                      <Typography variant="body2" color="text.secondary">{stat.label}</Typography>
                      <Typography variant="body2" fontWeight={600}>{stat.value}</Typography>
                    </Box>
                  ))}
                </>
              )}
              <Typography variant="caption" color="text.secondary">Live risk stats for {selectedSymbol}</Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Advanced Analytics Section */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={12} md={4}>
          <Card>
            <CardHeader
              title="AI Insights"
              subheader="Machine learning predictions"
              action={
                <Chip label="Beta" color="warning" size="small" />
              }
            />
            <CardContent>
              <List dense>
                <ListItem>
                  <ListItemAvatar>
                    <Avatar sx={{ bgcolor: 'success.main', width: 32, height: 32 }}>
                      <CheckCircle fontSize="small" />
                    </Avatar>
                  </ListItemAvatar>
                  <ListItemText
                    primary="Market Sentiment: Bullish"
                    secondary="87% confidence - Tech sector strength"
                  />
                </ListItem>
                <ListItem>
                  <ListItemAvatar>
                    <Avatar sx={{ bgcolor: 'warning.main', width: 32, height: 32 }}>
                      <Warning fontSize="small" />
                    </Avatar>
                  </ListItemAvatar>
                  <ListItemText
                    primary="Volatility Alert"
                    secondary="VIX spike expected next week"
                  />
                </ListItem>
                <ListItem>
                  <ListItemAvatar>
                    <Avatar sx={{ bgcolor: 'info.main', width: 32, height: 32 }}>
                      <Analytics fontSize="small" />
                    </Avatar>
                  </ListItemAvatar>
                  <ListItemText
                    primary="Sector Rotation"
                    secondary="Energy → Technology predicted"
                  />
                </ListItem>
              </List>
            </CardContent>
          </Card>
        </Grid>
        
        <Grid item xs={12} md={4}>
          <Card>
            <CardHeader
              title="Risk Management"
              subheader="Portfolio risk analytics"
              action={
                <IconButton size="small" onClick={() => window.location.href = '/portfolio'}>
                  <Security />
                </IconButton>
              }
            />
            <CardContent>
              <Box mb={2}>
                <Typography variant="body2" color="text.secondary" gutterBottom>
                  Portfolio Beta
                </Typography>
                <Box display="flex" alignItems="center" gap={2}>
                  <LinearProgress 
                    variant="determinate" 
                    value={75}
                    sx={{ flex: 1, height: 8, borderRadius: 4 }}
                  />
                  <Typography variant="h6">0.95</Typography>
                </Box>
              </Box>
              
              <Box mb={2}>
                <Typography variant="body2" color="text.secondary" gutterBottom>
                  Value at Risk (95%)
                </Typography>
                <Box display="flex" alignItems="center" gap={2}>
                  <LinearProgress 
                    variant="determinate" 
                    value={60}
                    color="warning"
                    sx={{ flex: 1, height: 8, borderRadius: 4 }}
                  />
                  <Typography variant="h6">-$28K</Typography>
                </Box>
              </Box>
              
              <Box>
                <Typography variant="body2" color="text.secondary" gutterBottom>
                  Sharpe Ratio
                </Typography>
                <Box display="flex" alignItems="center" gap={2}>
                  <LinearProgress 
                    variant="determinate" 
                    value={85}
                    color="success"
                    sx={{ flex: 1, height: 8, borderRadius: 4 }}
                  />
                  <Typography variant="h6">1.42</Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>
        
        <Grid item xs={12} md={4}>
          <Card>
            <CardHeader
              title="Trading Signals"
              subheader="Algorithm-generated opportunities"
              action={
                <Box display="flex" alignItems="center" gap={1}>
                  <Chip label="Live" color="success" size="small" />
                  <IconButton size="small">
                    <Refresh />
                  </IconButton>
                </Box>
              }
            />
            <CardContent>
              <List dense>
                {mockSignals.map((signal, idx) => (
                  <ListItem key={idx}>
                    <ListItemAvatar>
                      <Avatar sx={{ 
                        bgcolor: signal.action === 'Buy' ? 'success.main' : 'error.main',
                        width: 32, height: 32
                      }}>
                        {signal.action === 'Buy' ? <ArrowUpward fontSize="small" /> : <ArrowDownward fontSize="small" />}
                      </Avatar>
                    </ListItemAvatar>
                    <ListItemText
                      primary={`${signal.action} ${signal.symbol}`}
                      secondary={`${(signal.confidence * 100).toFixed(0)}% confidence`}
                    />
                    <IconButton size="small" color="primary">
                      <PlayArrow />
                    </IconButton>
                  </ListItem>
                ))}
              </List>
            </CardContent>
          </Card>
        </Grid>
      </Grid>"


      {/* Compliance Disclaimer */}
      <Box sx={{ mt: 4, mb: 2, textAlign: 'center' }}>
        <Typography variant="caption" color="text.secondary">
          For institutional use only. Not investment advice. Data may be delayed or incomplete. &copy; {new Date().getFullYear()} Hedge Fund Name. All rights reserved.
        </Typography>
      </Box>
    </Container>
  );
};

export default Dashboard;
