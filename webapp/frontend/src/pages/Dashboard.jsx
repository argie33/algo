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
  Link
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
  Close
} from '@mui/icons-material';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer } from 'recharts';
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
import { PieChart, Pie, Cell } from 'recharts';
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

  console.log('📊 Dashboard: Data summary:', {
    user: { hasData: !!user, isLoading: userLoading, hasError: !!userError },
    watchlist: { hasData: !!watchlist, isLoading: watchlistLoading, hasError: !!watchlistError },
    portfolio: { hasData: !!portfolio, isLoading: portfolioLoading, hasError: !!portfolioError },
    portfolioMetrics: { hasData: !!portfolioMetrics, isLoading: metricsLoading, hasError: !!metricsError },
    holdings: { hasData: !!holdings, isLoading: holdingsLoading, hasError: !!holdingsError },
    userSettings: { hasData: !!userSettings, isLoading: settingsLoading, hasError: !!settingsError },
    marketSummary: { hasData: !!marketSummary, isLoading: marketLoading, hasError: !!marketError },
    technicalSignals: { hasData: !!technicalSignals, isLoading: signalsLoading, hasError: !!signalsError }
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
    <Box>
      {/* Header */}
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
        <Box sx={{ display: 'flex', alignItems: 'center' }}>
          {logoSrc ? (
            <img src={logoSrc} alt="Logo" style={{ height: 48, width: 48, borderRadius: '50%' }} />
          ) : (
            <Avatar sx={{ bgcolor: 'primary.main', width: 48, height: 48, fontSize: 28 }}>
              FD
            </Avatar>
          )}
          <Box>
            <Typography variant="h5" sx={{ fontWeight: 700, letterSpacing: 1 }}>
              {BRAND_NAME} Client Portal
            </Typography>
            <Typography variant="caption" color="text.secondary">
              Professional Investor Dashboard
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
      <Divider sx={{ mb: 3 }} />

      {/* Debug Results */}
      {debugResults && (
        <Alert severity="info" sx={{ mb: 2 }}>
          <Typography variant="subtitle2" gutterBottom>API Debug Results:</Typography>
          <pre style={{ fontSize: '12px', overflow: 'auto', maxHeight: '200px' }}>
            {JSON.stringify(debugResults, null, 2)}
          </pre>
        </Alert>
      )}

      {/* Top Row: Portfolio, Watchlist */}
      <Grid container spacing={3} sx={{ mb: 3 }}>
        <Grid item xs={12} md={6}>
          <Card sx={{ bgcolor: 'grey.50', boxShadow: 3, borderLeft: '6px solid #1976d2' }}>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                <AccountBalance sx={{ color: 'primary.main', mr: 1 }} />
                <Typography variant="h6" sx={{ fontWeight: 600 }}>Portfolio Value</Typography>
                <Tooltip title="Click to add positions" arrow>
                  <IconButton size="small" onClick={() => setAddPositionOpen(true)}>
                    <Add />
                  </IconButton>
                </Tooltip>
              </Box>
              <Typography variant="h4" sx={{ fontWeight: 700, color: 'primary.main', letterSpacing: 1 }}>
                ${portfolio.value.toLocaleString()}
              </Typography>
              <Box sx={{ display: 'flex', gap: 2, mt: 1 }}>
                <Chip label={`Daily: $${portfolio.pnl.daily.toLocaleString()}`} 
                      color={portfolio.pnl.daily >= 0 ? 'success' : 'error'} size="small" />
                <Chip label={`MTD: $${portfolio.pnl.mtd.toLocaleString()}`} 
                      color={portfolio.pnl.mtd >= 0 ? 'success' : 'error'} size="small" />
                <Chip label={`YTD: $${portfolio.pnl.ytd.toLocaleString()}`} 
                      color={portfolio.pnl.ytd >= 0 ? 'success' : 'error'} size="small" />
              </Box>
              
              {/* Portfolio Metrics */}
              <Box sx={{ mt: 2, p: 2, bgcolor: 'white', borderRadius: 1 }}>
                <Typography variant="body2" sx={{ fontWeight: 600, mb: 1 }}>Portfolio Metrics</Typography>
                <Grid container spacing={1}>
                  <Grid item xs={6}>
                    <Typography variant="caption" color="text.secondary">Sharpe Ratio</Typography>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>{portfolioMetrics.sharpe?.toFixed(2) || 'N/A'}</Typography>
                  </Grid>
                  <Grid item xs={6}>
                    <Typography variant="caption" color="text.secondary">Beta</Typography>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>{portfolioMetrics.beta?.toFixed(2) || 'N/A'}</Typography>
                  </Grid>
                  <Grid item xs={6}>
                    <Typography variant="caption" color="text.secondary">Max Drawdown</Typography>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>{(portfolioMetrics.maxDrawdown * 100)?.toFixed(1) || 'N/A'}%</Typography>
                  </Grid>
                  <Grid item xs={6}>
                    <Typography variant="caption" color="text.secondary">Volatility</Typography>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>{(portfolioMetrics.volatility * 100)?.toFixed(1) || 'N/A'}%</Typography>
                  </Grid>
                </Grid>
              </Box>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={6}>
          <Card sx={{ boxShadow: 3, borderLeft: '6px solid #43a047' }}>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                <Bookmark sx={{ color: 'info.main', mr: 1 }} />
                <Typography variant="h6" sx={{ fontWeight: 600 }}>Watchlist</Typography>
                <Tooltip title="Add symbol to watchlist" arrow>
                  <IconButton size="small" onClick={() => setAddWatchlistOpen(true)}>
                    <Add />
                  </IconButton>
                </Tooltip>
              </Box>
              <Box sx={{ maxHeight: 200, overflowY: 'auto' }}>
                {watchlist.length === 0 ? (
                  <Typography variant="body2" color="text.secondary">
                    No symbols in watchlist. Click + to add.
                  </Typography>
                ) : (
                  <table style={{ width: '100%', fontSize: 14 }}>
                    <thead>
                      <tr>
                        <th align="left">Symbol</th>
                        <th align="right">Price</th>
                        <th align="right">Change</th>
                        <th align="center">Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {watchlist.map((symbol, idx) => (
                        <tr key={symbol} style={{ background: idx % 2 ? '#f9f9f9' : 'white' }}>
                          <td>{symbol}</td>
                          <td align="right">$--</td>
                          <td align="right">--%</td>
                          <td align="center">
                            <IconButton size="small" onClick={() => removeSymbol.mutate(symbol)}>
                              <Remove />
                            </IconButton>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Market Overview */}
      <MarketOverviewWidget />

      {/* Technical Signals */}
      <TechnicalSignalsWidget />

      {/* Performance Analytics */}
      <Grid container spacing={3} sx={{ mb: 3 }}>
        <Grid item xs={12} md={8}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                <ShowChart sx={{ color: 'primary.main', mr: 1 }} />
                <Typography variant="h6" sx={{ fontWeight: 600 }}>Performance Analytics ({selectedSymbol})</Typography>
              </Box>
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={equityCurve} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="date" tick={{ fontSize: 12 }} />
                  <YAxis tick={{ fontSize: 12 }} domain={['auto', 'auto']} />
                  <RechartsTooltip formatter={(v) => `$${v?.toLocaleString?.() ?? v}`}/>
                  <Line type="monotone" dataKey="equity" stroke="#1976d2" strokeWidth={2} dot={false} name="Equity" />
                </LineChart>
              </ResponsiveContainer>
              <Typography variant="caption" color="text.secondary">Equity curve for {selectedSymbol}</Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={4}>
          <HoldingsWidget />
        </Grid>
      </Grid>

      {/* Insights Row */}
      <Grid container spacing={3} sx={{ mb: 3 }}>
        <Grid item xs={12} md={4}>
          <EarningsCalendarWidget symbol={selectedSymbol} />
        </Grid>
        <Grid item xs={12} md={4}>
          <AnalystInsightsWidget symbol={selectedSymbol} />
        </Grid>
        <Grid item xs={12} md={4}>
          <FinancialHighlightsWidget symbol={selectedSymbol} />
        </Grid>
      </Grid>

      {/* User Settings */}
      <UserSettingsWidget user={user} />

      {/* Contact Support - Subtle link */}
      <Box sx={{ mt: 3, textAlign: 'center' }}>
        <Link href="#" color="text.secondary" sx={{ textDecoration: 'none' }}>
          <ContactSupport sx={{ fontSize: 16, mr: 0.5, verticalAlign: 'middle' }} />
          Contact Support
        </Link>
      </Box>

      {/* Dialogs */}
      <AddPositionDialog 
        open={addPositionOpen} 
        onClose={() => setAddPositionOpen(false)} 
        onAdd={handleAddPosition} 
      />
      <AddToWatchlistDialog 
        open={addWatchlistOpen} 
        onClose={() => setAddWatchlistOpen(false)} 
        onAdd={handleAddToWatchlist} 
      />

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

export default Dashboard;
