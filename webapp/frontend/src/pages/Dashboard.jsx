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
  Autocomplete
} from '@mui/material';
import {
  TrendingUp, TrendingDown, Assessment, Notifications, Event, ListAlt, ShowChart, AccountBalance, Download, ContactSupport, Info, TrendingFlat, ArrowUpward, ArrowDownward
} from '@mui/icons-material';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer } from 'recharts';
import { useQuery } from '@tanstack/react-query';
import { getStockPrices, getStockMetrics, getBuySignals, getSellSignals, api } from '../services/api';
import { PieChart, Pie, Cell } from 'recharts';
import { format } from 'date-fns';
import { getApiConfig } from '../services/api';

// Logo import with fallback
let logoSrc = null;
try {
  // Use dynamic import for assets in Vite
  logoSrc = new URL('../assets/logo.png', import.meta.url).href;
} catch (e) {
  logoSrc = null;
}

// Get API configuration
const { apiUrl: API_BASE } = getApiConfig();

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

const BRAND_NAME = 'Edgebrooke Capital';
// Remove user/advisor names for now 
const USER_NAME = '';
const ADVISOR_NAME = '';
const ADVISOR_EMAIL = '';

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
      const response = await api.get('/auth/user');
      return response.data;
    },
    staleTime: 10 * 60 * 1000
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
      // FIX: Use a working endpoint or implement if missing
      // Try /api/technical/daily?limit=10&sortBy=date
      const response = await api.get('/api/technical/daily?limit=10&sortBy=date');
      return response.data;
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
                  <th align="left">RSI</th>
                  <th align="left">MACD</th>
                  <th align="right">Date</th>
                </tr>
              </thead>
              <tbody>
                {signals.map((sig, idx) => (
                  <tr key={sig.symbol + sig.date + idx} style={{ background: idx % 2 ? '#f9f9f9' : 'white' }}>
                    <td>{sig.symbol}</td>
                    <td>{sig.rsi}</td>
                    <td>{sig.macd}</td>
                    <td align="right">{sig.date ? new Date(sig.date).toLocaleDateString() : ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Box>
        )}
        <Typography variant="caption" color="text.secondary">Live technical signals from your technicals table (daily).</Typography>
      </CardContent>
    </Card>
  );
}

// --- MARKET OVERVIEW WIDGET ---
function MarketOverviewWidget() {
  // Fetch real market summary from backend using API service
  const { data, isLoading, error } = useQuery({
    queryKey: ['dashboard-market-summary'],
    queryFn: async () => {
      // FIX: Use the correct endpoint from market.js
      const response = await api.get('/api/market/overview');
      return response.data;
    },
    staleTime: 2 * 60 * 1000
  });
  // Map the data to the expected structure for the widget
  const summary = [
    {
      name: 'S&P 500',
      value: data?.data?.sp500_level ?? data?.sp500_level ?? '--',
      change: data?.data?.sp500_change ?? data?.sp500_change ?? 0,
      pct: data?.data?.sp500_pct ?? data?.sp500_pct ?? '--'
    },
    {
      name: 'NASDAQ',
      value: data?.data?.nasdaq_level ?? data?.nasdaq_level ?? '--',
      change: data?.data?.nasdaq_change ?? data?.nasdaq_change ?? 0,
      pct: data?.data?.nasdaq_pct ?? data?.nasdaq_pct ?? '--'
    },
    {
      name: 'DOW',
      value: data?.data?.dow_level ?? data?.dow_level ?? '--',
      change: data?.data?.dow_change ?? data?.dow_change ?? 0,
      pct: data?.data?.dow_pct ?? data?.dow_pct ?? '--'
    }
  ];
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
                  {/* Use up/down icon based on change */}
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
  // Fetch real earnings/events for the selected symbol using the correct calendar API
  const { data, isLoading, error } = useQuery({
    queryKey: ['dashboard-earnings-calendar', symbol],
    queryFn: async () => {
      // Use the same endpoint as EarningsCalendar page
      const params = new URLSearchParams({
        type: 'upcoming',
        page: 1,
        limit: 5
      });
      const response = await fetch(`${API_BASE}/calendar/events?${params}`);
      if (!response.ok) {
        const text = await response.text();
        throw new Error(`Failed to fetch calendar data: ${response.status} ${text}`);
      }
      return response.json();
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
          <Typography variant="body2" color="text.secondary">No upcoming earnings/events found.</Typography>
        ) : (
          <>
            {earnings.map((ev, idx) => (
              <Box key={ev.symbol + ev.start_date + idx} sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                <Typography variant="body2">{ev.symbol}: {ev.title}</Typography>
                <Typography variant="caption" color="text.secondary">{format(new Date(ev.start_date), 'MMM d')}</Typography>
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
  // Fetch real analyst insights for the selected symbol using API service
  const { data, isLoading, error } = useQuery({
    queryKey: ['dashboard-analyst-insights', symbol],
    queryFn: async () => {
      // FIX: Use the correct endpoint from analysts.js
      const response = await api.get(`/api/analysts/${encodeURIComponent(symbol)}/overview`);
      return response.data;
    },
    enabled: !!symbol,
    staleTime: 5 * 60 * 1000
  });
  // Map upgrades/downgrades from the overview data
  const upgrades = Array.isArray(data?.data?.earnings_estimates) ? data.data.earnings_estimates.filter(e => e.surprise_percent > 0) : [];
  const downgrades = Array.isArray(data?.data?.earnings_estimates) ? data.data.earnings_estimates.filter(e => e.surprise_percent < 0) : [];
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
  // Fetch real financial highlights for the selected symbol using API service
  const { data, isLoading, error } = useQuery({
    queryKey: ['dashboard-financial-highlights', symbol],
    queryFn: async () => {
      // FIX: Use the correct endpoint from financials.js
      const response = await api.get(`/api/financials/${encodeURIComponent(symbol)}/key-metrics`);
      return response.data;
    },
    enabled: !!symbol,
    staleTime: 5 * 60 * 1000
  });
  // Extract highlights from the key metrics data
  const highlights = [];
  const metrics = data?.data;
  if (metrics) {
    // Pick a few key metrics for highlights
    const categories = ['valuation', 'financial_performance', 'growth', 'dividends'];
    categories.forEach(cat => {
      if (metrics[cat]) {
        Object.entries(metrics[cat].metrics).forEach(([label, value]) => {
          highlights.push({ label, value });
        });
      }
    });
  }
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
            {highlights.slice(0, 8).map((item, idx) => (
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

// --- USER SETTINGS WIDGET (optional, for user personalization) ---
function UserSettingsWidget({ user }) {
  // Example: fetch and update user preferences
  // TODO: Implement backend endpoints for user settings if not present
  return (
    <Card sx={{ mb: 3 }}>
      <CardContent>
        <Typography variant="h6" sx={{ fontWeight: 600, mb: 1 }}>User Settings</Typography>
        {user ? (
          <Typography variant="body2">Email: {user.email}</Typography>
        ) : (
          <Typography variant="body2" color="text.secondary">Loading user info...</Typography>
        )}
        {/* Add more settings here as backend supports */}
      </CardContent>
    </Card>
  );
}

const Dashboard = () => {
  // Symbol selector state
  const [selectedSymbol, setSelectedSymbol] = useState('AAPL');

  // --- SYMBOL OPTIONS: Fetch dynamically from backend ---
  const { data: symbolListData, isLoading: symbolListLoading, error: symbolListError } = useQuery({
    queryKey: ['dashboard-symbol-list'],
    queryFn: async () => {
      const response = await api.get('/api/dashboard/symbols');
      return response.data;
    },
    staleTime: 60 * 60 * 1000
  });
  const SYMBOL_OPTIONS = Array.isArray(symbolListData?.data) && symbolListData.data.length > 0
    ? symbolListData.data
    : ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA', 'SPY', 'QQQ']; // fallback

  // Equity curve (price history)
  const { data: priceData, isLoading: priceLoading, error: priceError } = useQuery({
    queryKey: ['stock-prices', selectedSymbol],
    queryFn: () => getStockPrices(selectedSymbol, 'daily', 30),
    staleTime: 5 * 60 * 1000
  });
  // Risk metrics
  const { data: metricsData, isLoading: metricsLoading, error: metricsError } = useQuery({
    queryKey: ['stock-metrics', selectedSymbol],
    queryFn: () => getStockMetrics(selectedSymbol),
    staleTime: 5 * 60 * 1000
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

  // --- Replace mock data with real API calls ---
  // Portfolio: fetch from backend
  const { data: portfolioData, isLoading: portfolioLoading, error: portfolioError } = useQuery({
    queryKey: ['dashboard-portfolio'],
    queryFn: async () => {
      const response = await api.get('/api/dashboard/portfolio');
      return response.data;
    },
    staleTime: 5 * 60 * 1000
  });
  const safePortfolio = portfolioData?.data && typeof portfolioData.data === 'object'
    ? portfolioData.data
    : { value: 0, pnl: { daily: 0, mtd: 0, ytd: 0 }, allocation: [] };

  // Watchlist: fetch from backend
  const { data: watchlistData, isLoading: watchlistLoading, error: watchlistError } = useQuery({
    queryKey: ['dashboard-watchlist'],
    queryFn: async () => {
      const response = await api.get('/api/dashboard/watchlist');
      return response.data;
    },
    staleTime: 5 * 60 * 1000
  });
  const safeWatchlist = Array.isArray(watchlistData?.data) ? watchlistData.data : [];

  // News: fetch from backend
  const { data: newsData, isLoading: newsLoading, error: newsError } = useQuery({
    queryKey: ['dashboard-news'],
    queryFn: async () => {
      const response = await api.get('/api/dashboard/news');
      return response.data;
    },
    staleTime: 5 * 60 * 1000
  });
  const safeNews = Array.isArray(newsData?.data) ? newsData.data : [];

  // Activity: fetch from backend
  const { data: activityData, isLoading: activityLoading, error: activityError } = useQuery({
    queryKey: ['dashboard-activity'],
    queryFn: async () => {
      const response = await api.get('/api/dashboard/activity');
      return response.data;
    },
    staleTime: 5 * 60 * 1000
  });
  const safeActivity = Array.isArray(activityData?.data) ? activityData.data : [];

  // Calendar: fetch from backend
  const { data: calendarData, isLoading: calendarLoading, error: calendarError } = useQuery({
    queryKey: ['dashboard-calendar'],
    queryFn: async () => {
      const response = await api.get('/api/dashboard/calendar');
      return response.data;
    },
    staleTime: 5 * 60 * 1000
  });
  const safeCalendar = Array.isArray(calendarData?.data) ? calendarData.data : [];

  // Alerts/Signals: fetch from backend
  const { data: signalsData, isLoading: signalsLoading, error: signalsError } = useQuery({
    queryKey: ['dashboard-signals'],
    queryFn: async () => {
      const response = await api.get('/api/dashboard/signals');
      return response.data;
    },
    staleTime: 2 * 60 * 1000
  });
  const safeSignals = Array.isArray(signalsData?.data) ? signalsData.data : [];

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

  // User context
  const { user, isLoading: userLoading, error: userError, isAuthenticated } = useUser();

  // Optionally redirect to login if not authenticated
  // useEffect(() => {
  //   if (!userLoading && !isAuthenticated) {
  //     window.location.href = '/login';
  //   }
  // }, [userLoading, isAuthenticated]);

  return (
    <Box>
      {/* Institutional Header */}
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
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
            <Typography variant="h5" sx={{ fontWeight: 700, letterSpacing: 1 }}>{BRAND_NAME} Client Portal</Typography>
            <Typography variant="caption" color="text.secondary">Professional Investor Dashboard</Typography>
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
            renderInput={(params) => <TextField {...params} label="Symbol" size="small" />} />
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
            <Button size="small" color="secondary" variant="outlined" onClick={() => {
              api.post('/auth/logout')
                .then(() => window.location.href = '/login')
                .catch(error => {
                  console.error('Logout error:', error);
                  window.location.href = '/login';
                });
            }}>Logout</Button>
          )}
        </Box>
      </Box>
      <Divider sx={{ mb: 3 }} />

      {/* Top Row: Portfolio Snapshot, Watchlist, Quick Actions */}
      <Grid container spacing={3} sx={{ mb: 3 }}>
        <Grid item xs={12} md={4}>
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
        <Grid item xs={12} md={5}>
          <Card sx={{ boxShadow: 3, borderLeft: '6px solid #43a047' }}>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                <TrendingFlat sx={{ color: 'info.main', mr: 1 }} />
                <Typography variant="h6" sx={{ fontWeight: 600 }}>Watchlist</Typography>
                <Tooltip title="Your selected stocks for monitoring" arrow><Info sx={{ color: 'grey.500', ml: 1, fontSize: 18 }} /></Tooltip>
              </Box>
              <Box sx={{ maxHeight: 140, overflowY: 'auto' }}>
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
        <Grid item xs={12} md={3}>
          <Card sx={{ boxShadow: 3, bgcolor: 'grey.50', borderLeft: '6px solid #ffb300' }}>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                <Download sx={{ color: 'primary.main', mr: 1 }} />
                <Typography variant="h6" sx={{ fontWeight: 600 }}>Quick Actions</Typography>
                <Tooltip title="Access common actions quickly" arrow><Info sx={{ color: 'grey.500', ml: 1, fontSize: 18 }} /></Tooltip>
              </Box>
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                <Button variant="contained" color="primary" fullWidth startIcon={<TrendingUp />} aria-label="Trade">Trade</Button>
                <Button variant="outlined" color="primary" fullWidth startIcon={<AccountBalance />} aria-label="Transfer Funds">Transfer Funds</Button>
                <Button variant="outlined" color="secondary" fullWidth startIcon={<Download />} aria-label="Download Report">Download Report</Button>
                <Button variant="outlined" color="info" fullWidth startIcon={<ContactSupport />} aria-label="Contact Support">Contact Support</Button>
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

      {/* Summary/Insight Widgets */}
      <MarketOverviewWidget />
      <Grid container spacing={3}>
        <Grid item xs={12} md={4}>
          <EarningsCalendarWidget symbol={selectedSymbol} />
        </Grid>
        <Grid item xs={12} md={4}>
          <AnalystInsightsWidget symbol={selectedSymbol} />
        </Grid>
        <Grid item xs={12} md={4}>
          <FinancialHighlightsWidget symbol={selectedSymbol} />
        </Grid>
        <Grid item xs={12} md={12}>
          <UserSettingsWidget user={user} />
        </Grid>
      </Grid>

      {/* TODO: Add new summary/insight widgets here (Market Overview, Earnings, Analyst, Financial Highlights, Data Health, etc.) */}
      {/* TODO: Replace mock data with real API calls for watchlist, portfolio, news, etc. */}
      {/* ...existing code... */}

      {/* Compliance Disclaimer */}
      <Box sx={{ mt: 4, mb: 2, textAlign: 'center' }}>
        <Typography variant="caption" color="text.secondary">
          For institutional use only. Not investment advice. Data may be delayed or incomplete. &copy; {new Date().getFullYear()} Hedge Fund Name. All rights reserved.
        </Typography>
      </Box>
    </Box>
  );
};

export default Dashboard;
