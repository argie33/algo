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
import { getStockPrices, getStockMetrics, getBuySignals, getSellSignals, getRecentAnalystActions, getKeyMetrics, api } from '../services/api';
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

// User authentication hook
function useUser() {
  return useQuery({
    queryKey: ['dashboard-user'],
    queryFn: async () => {
      const response = await api.get('/dashboard/user');
      return response.data;
    },
    staleTime: 5 * 60 * 1000
  });
}

// Watchlist management hook
function useWatchlist() {
  const queryClient = useQueryClient();
  
  const { data, isLoading, error } = useQuery({
    queryKey: ['dashboard-watchlist'],
    queryFn: async () => {
      const response = await api.get('/dashboard/watchlist');
      return response.data;
    },
    staleTime: 5 * 60 * 1000
  });

  const addSymbol = useMutation({
    mutationFn: async (symbol) => {
      const response = await api.post('/dashboard/watchlist', { symbol });
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries(['dashboard-watchlist']);
    }
  });

  const removeSymbol = useMutation({
    mutationFn: async (symbol) => {
      const response = await api.delete('/dashboard/watchlist', { data: { symbol } });
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries(['dashboard-watchlist']);
    }
  });

  return {
    watchlist: data?.data || [],
    isLoading,
    error,
    addSymbol,
    removeSymbol
  };
}

// Portfolio management hook
function usePortfolio() {
  const queryClient = useQueryClient();
  
  const { data, isLoading, error } = useQuery({
    queryKey: ['dashboard-portfolio'],
    queryFn: async () => {
      const response = await api.get('/dashboard/portfolio');
      return response.data;
    },
    staleTime: 5 * 60 * 1000
  });

  const updatePositions = useMutation({
    mutationFn: async (positions) => {
      const response = await api.post('/dashboard/portfolio', { positions });
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries(['dashboard-portfolio']);
    }
  });

  return {
    portfolio: data?.data || { positions: [], value: 0, pnl: { daily: 0, mtd: 0, ytd: 0 } },
    isLoading,
    error,
    updatePositions
  };
}

// Portfolio metrics hook
function usePortfolioMetrics() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['dashboard-portfolio-metrics'],
    queryFn: async () => {
      const response = await api.get('/dashboard/portfolio/metrics');
      return response.data;
    },
    staleTime: 5 * 60 * 1000
  });

  return {
    metrics: data?.data || {},
    isLoading,
    error
  };
}

// Holdings hook
function useHoldings() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['dashboard-holdings'],
    queryFn: async () => {
      const response = await api.get('/dashboard/holdings');
      return response.data;
    },
    staleTime: 5 * 60 * 1000
  });

  return {
    holdings: data?.data || [],
    isLoading,
    error
  };
}

// User settings hook
function useUserSettings() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['dashboard-user-settings'],
    queryFn: async () => {
      const response = await api.get('/dashboard/user/settings');
      return response.data;
    },
    staleTime: 5 * 60 * 1000
  });

  return {
    settings: data?.data || {},
    isLoading,
    error
  };
}

// Add Position Dialog Component
function AddPositionDialog({ open, onClose, onAdd }) {
  const [symbol, setSymbol] = useState('');
  const [shares, setShares] = useState('');
  const [avgPrice, setAvgPrice] = useState('');

  const handleAdd = () => {
    if (symbol && shares && avgPrice) {
      onAdd({
        symbol: symbol.toUpperCase(),
        shares: parseFloat(shares),
        avgPrice: parseFloat(avgPrice),
        date: new Date().toISOString()
      });
      setSymbol('');
      setShares('');
      setAvgPrice('');
      onClose();
    }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Add Position</DialogTitle>
      <DialogContent>
        <TextField
          fullWidth
          label="Symbol"
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
          margin="normal"
          placeholder="AAPL"
        />
        <TextField
          fullWidth
          label="Number of Shares"
          type="number"
          value={shares}
          onChange={(e) => setShares(e.target.value)}
          margin="normal"
          placeholder="100"
        />
        <TextField
          fullWidth
          label="Average Price"
          type="number"
          value={avgPrice}
          onChange={(e) => setAvgPrice(e.target.value)}
          margin="normal"
          placeholder="150.00"
        />
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button onClick={handleAdd} variant="contained" disabled={!symbol || !shares || !avgPrice}>
          Add Position
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// Add to Watchlist Dialog Component
function AddToWatchlistDialog({ open, onClose, onAdd }) {
  const [symbol, setSymbol] = useState('');

  const handleAdd = () => {
    if (symbol) {
      onAdd(symbol.toUpperCase());
      setSymbol('');
      onClose();
    }
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Add to Watchlist</DialogTitle>
      <DialogContent>
        <TextField
          fullWidth
          label="Symbol"
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
          margin="normal"
          placeholder="AAPL"
        />
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button onClick={handleAdd} variant="contained" disabled={!symbol}>
          Add
        </Button>
      </DialogActions>
    </Dialog>
  );
}

// Technical Signals Widget - Improved
function TechnicalSignalsWidget() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['dashboard-technical-signals'],
    queryFn: async () => {
      const response = await api.get('/technical/daily?limit=10&sortBy=date');
      return response.data;
    },
    refetchInterval: 300000
  });
  
  const signals = data?.data || [];
  
  return (
    <Card sx={{ mb: 3 }}>
      <CardContent>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
          <TrendingUp sx={{ color: 'primary.main', mr: 1 }} />
          <Typography variant="h6" sx={{ fontWeight: 600 }}>Technical Signals</Typography>
          <Tooltip title="Latest technical analysis signals" arrow>
            <Info sx={{ color: 'grey.500', ml: 1, fontSize: 18 }} />
          </Tooltip>
        </Box>
        {isLoading ? (
          <Box display="flex" alignItems="center" gap={2}>
            <CircularProgress size={20} />
            <Typography>Loading technical signals...</Typography>
          </Box>
        ) : error ? (
          <Alert severity="error" sx={{ mb: 2 }}>
            Failed to fetch technical signals: {error.message}
          </Alert>
        ) : signals.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            No technical signals available
          </Typography>
        ) : (
          <Box sx={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', fontSize: 14 }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #e0e0e0' }}>
                  <th align="left" style={{ padding: '8px 0' }}>Symbol</th>
                  <th align="left" style={{ padding: '8px 0' }}>RSI</th>
                  <th align="left" style={{ padding: '8px 0' }}>MACD</th>
                  <th align="left" style={{ padding: '8px 0' }}>Stochastic</th>
                  <th align="left" style={{ padding: '8px 0' }}>ATR</th>
                  <th align="left" style={{ padding: '8px 0' }}>Signal</th>
                  <th align="right" style={{ padding: '8px 0' }}>Date</th>
                </tr>
              </thead>
              <tbody>
                {signals.slice(0, 8).map((sig, idx) => (
                  <tr key={sig.symbol + sig.date + idx} style={{ 
                    background: idx % 2 ? '#f9f9f9' : 'white',
                    borderBottom: '1px solid #f0f0f0'
                  }}>
                    <td style={{ padding: '8px 0', fontWeight: 600 }}>{sig.symbol}</td>
                    <td style={{ padding: '8px 0' }}>
                      {sig.rsi ? (
                        <Chip 
                          label={formatNumber(sig.rsi, 1)} 
                          size="small" 
                          color={sig.rsi > 70 ? 'error' : sig.rsi < 30 ? 'success' : 'default'}
                        />
                      ) : 'N/A'}
                    </td>
                    <td style={{ padding: '8px 0' }}>{sig.macd ? formatNumber(sig.macd, 4) : 'N/A'}</td>
                    <td style={{ padding: '8px 0' }}>{sig.stochastic ? formatNumber(sig.stochastic, 1) : 'N/A'}</td>
                    <td style={{ padding: '8px 0' }}>{sig.atr ? formatNumber(sig.atr, 2) : 'N/A'}</td>
                    <td style={{ padding: '8px 0' }}>
                      {sig.rsi && sig.macd ? (
                        <Chip 
                          label={sig.rsi > 70 || sig.macd < 0 ? 'Sell' : sig.rsi < 30 || sig.macd > 0 ? 'Buy' : 'Hold'} 
                          size="small" 
                          color={sig.rsi > 70 || sig.macd < 0 ? 'error' : sig.rsi < 30 || sig.macd > 0 ? 'success' : 'warning'}
                        />
                      ) : 'N/A'}
                    </td>
                    <td align="right" style={{ padding: '8px 0', fontSize: 12 }}>
                      {sig.date ? format(new Date(sig.date), 'MMM d') : 'N/A'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Box>
        )}
        <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
          Live technical signals from daily analysis. RSI &gt; 70 = Overbought, RSI &lt; 30 = Oversold.
        </Typography>
      </CardContent>
    </Card>
  );
}

// Market Overview Widget
function MarketOverviewWidget() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['dashboard-market-summary'],
    queryFn: async () => {
      const response = await api.get('/dashboard/market-summary');
      return response.data;
    },
    staleTime: 5 * 60 * 1000
  });

  const marketData = data?.data || [];

  return (
    <Card>
      <CardContent>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
          <TrendingUp sx={{ color: 'primary.main', mr: 1 }} />
          <Typography variant="h6" sx={{ fontWeight: 600 }}>Market Overview</Typography>
          <Tooltip title="Real-time market indices" arrow>
            <Info sx={{ color: 'grey.500', ml: 1, fontSize: 18 }} />
          </Tooltip>
        </Box>
        {isLoading ? (
          <Box display="flex" alignItems="center" gap={2}>
            <CircularProgress size={20} />
            <Typography>Loading market data...</Typography>
          </Box>
        ) : error ? (
          <Alert severity="error" sx={{ mb: 2 }}>
            Failed to load market data: {error.message}
          </Alert>
        ) : (
          <Grid container spacing={2}>
            {marketData.map((index, idx) => (
              <Grid item xs={4} key={idx}>
                <Box sx={{ textAlign: 'center', p: 1 }}>
                  <Typography variant="body2" color="text.secondary" gutterBottom>
                    {index.name}
                  </Typography>
                  <Typography variant="h6" sx={{ fontWeight: 600, mb: 0.5 }}>
                    {index.value?.toLocaleString()}
                  </Typography>
                  <Typography 
                    variant="caption" 
                    sx={{ 
                      color: index.change >= 0 ? 'success.main' : 'error.main',
                      fontWeight: 600
                    }}
                  >
                    {index.pct}
                  </Typography>
                </Box>
              </Grid>
            ))}
          </Grid>
        )}
        <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
          Live market indices with real-time updates
        </Typography>
      </CardContent>
    </Card>
  );
}

// Earnings Calendar Widget
function EarningsCalendarWidget({ symbol }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['dashboard-earnings-calendar', symbol],
    queryFn: async () => {
      const response = await api.get(`/dashboard/earnings-calendar?symbol=${symbol}`);
      return response.data;
    },
    staleTime: 5 * 60 * 1000
  });

  const events = data?.data || [];

  return (
    <Card>
      <CardContent>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
          <Event sx={{ color: 'primary.main', mr: 1 }} />
          <Typography variant="h6" sx={{ fontWeight: 600 }}>Earnings & Events</Typography>
          <Tooltip title="Upcoming earnings and economic events" arrow>
            <Info sx={{ color: 'grey.500', ml: 1, fontSize: 18 }} />
          </Tooltip>
        </Box>
        {isLoading ? (
          <Box display="flex" alignItems="center" gap={2}>
            <CircularProgress size={20} />
            <Typography>Loading events...</Typography>
          </Box>
        ) : error ? (
          <Alert severity="error" sx={{ mb: 2 }}>
            Failed to load events: {error.message}
          </Alert>
        ) : events.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            No upcoming events for {symbol}
          </Typography>
        ) : (
          <List dense>
            {events.slice(0, 5).map((event, idx) => (
              <ListItem key={idx} sx={{ px: 0, py: 1 }}>
                <ListItemText
                  primary={event.event}
                  secondary={format(new Date(event.date), 'MMM d, yyyy')}
                  primaryTypographyProps={{ variant: 'body2', fontWeight: 500 }}
                  secondaryTypographyProps={{ variant: 'caption' }}
                />
                <Chip 
                  label={event.event.includes('Earnings') ? 'Earnings' : 'Economic'} 
                  size="small" 
                  color={event.event.includes('Earnings') ? 'primary' : 'secondary'}
                />
              </ListItem>
            ))}
          </List>
        )}
        <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
          Earnings dates and key economic events for {symbol}
        </Typography>
      </CardContent>
    </Card>
  );
}

// Analyst Insights Widget - Keep existing but improve
function AnalystInsightsWidget({ symbol }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['dashboard-analyst-insights', symbol],
    queryFn: async () => {
      const response = await api.get(`/dashboard/analyst-insights?symbol=${symbol}`);
      return response.data;
    },
    staleTime: 5 * 60 * 1000
  });

  const insights = data?.data || { upgrades: [], downgrades: [] };

  return (
    <Card>
      <CardContent>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
          <Analytics sx={{ color: 'primary.main', mr: 1 }} />
          <Typography variant="h6" sx={{ fontWeight: 600 }}>Analyst Insights</Typography>
          <Tooltip title="Recent analyst upgrades and downgrades" arrow>
            <Info sx={{ color: 'grey.500', ml: 1, fontSize: 18 }} />
          </Tooltip>
        </Box>
        {isLoading ? (
          <Box display="flex" alignItems="center" gap={2}>
            <CircularProgress size={20} />
            <Typography>Loading insights...</Typography>
          </Box>
        ) : error ? (
          <Alert severity="error" sx={{ mb: 2 }}>
            Failed to load insights: {error.message}
          </Alert>
        ) : (
          <Box>
            <Box sx={{ mb: 2 }}>
              <Typography variant="body2" sx={{ fontWeight: 600, mb: 1 }}>
                Upgrades ({insights.upgrades.length})
              </Typography>
              {insights.upgrades.length > 0 ? (
                insights.upgrades.slice(0, 3).map((upgrade, idx) => (
                  <Box key={idx} sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                    <Chip label="↑" size="small" color="success" sx={{ mr: 1 }} />
                    <Typography variant="body2">{upgrade.symbol}</Typography>
                  </Box>
                ))
              ) : (
                <Typography variant="body2" color="text.secondary">No recent upgrades</Typography>
              )}
            </Box>
            <Box>
              <Typography variant="body2" sx={{ fontWeight: 600, mb: 1 }}>
                Downgrades ({insights.downgrades.length})
              </Typography>
              {insights.downgrades.length > 0 ? (
                insights.downgrades.slice(0, 3).map((downgrade, idx) => (
                  <Box key={idx} sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                    <Chip label="↓" size="small" color="error" sx={{ mr: 1 }} />
                    <Typography variant="body2">{downgrade.symbol}</Typography>
                  </Box>
                ))
              ) : (
                <Typography variant="body2" color="text.secondary">No recent downgrades</Typography>
              )}
            </Box>
          </Box>
        )}
        <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
          Recent analyst actions for {symbol}
        </Typography>
      </CardContent>
    </Card>
  );
}

// Financial Highlights Widget - Keep existing
function FinancialHighlightsWidget({ symbol }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['dashboard-financial-highlights', symbol],
    queryFn: async () => {
      const response = await api.get(`/dashboard/financial-highlights?symbol=${symbol}`);
      return response.data;
    },
    staleTime: 5 * 60 * 1000
  });

  const highlights = data?.data || [];

  return (
    <Card>
      <CardContent>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
          <AccountBalance sx={{ color: 'primary.main', mr: 1 }} />
          <Typography variant="h6" sx={{ fontWeight: 600 }}>Financial Highlights</Typography>
          <Tooltip title="Key financial metrics and ratios" arrow>
            <Info sx={{ color: 'grey.500', ml: 1, fontSize: 18 }} />
          </Tooltip>
        </Box>
        {isLoading ? (
          <Box display="flex" alignItems="center" gap={2}>
            <CircularProgress size={20} />
            <Typography>Loading highlights...</Typography>
          </Box>
        ) : error ? (
          <Alert severity="error" sx={{ mb: 2 }}>
            Failed to load highlights: {error.message}
          </Alert>
        ) : highlights.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            No financial data available for {symbol}
          </Typography>
        ) : (
          <Grid container spacing={1}>
            {highlights.slice(0, 6).map((highlight, idx) => (
              <Grid item xs={6} key={idx}>
                <Box sx={{ p: 1, bgcolor: 'grey.50', borderRadius: 1 }}>
                  <Typography variant="caption" color="text.secondary" display="block">
                    {highlight.label}
                  </Typography>
                  <Typography variant="body2" sx={{ fontWeight: 600 }}>
                    {highlight.value}
                  </Typography>
                </Box>
              </Grid>
            ))}
          </Grid>
        )}
        <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
          Key financial metrics for {symbol}
        </Typography>
      </CardContent>
    </Card>
  );
}

// Holdings Widget - New
function HoldingsWidget() {
  const { holdings, isLoading, error } = useHoldings();

  return (
    <Card>
      <CardContent>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
          <ViewList sx={{ color: 'primary.main', mr: 1 }} />
          <Typography variant="h6" sx={{ fontWeight: 600 }}>Current Holdings</Typography>
          <Tooltip title="Your current positions" arrow>
            <Info sx={{ color: 'grey.500', ml: 1, fontSize: 18 }} />
          </Tooltip>
        </Box>
        {isLoading ? (
          <Box display="flex" alignItems="center" gap={2}>
            <CircularProgress size={20} />
            <Typography>Loading holdings...</Typography>
          </Box>
        ) : error ? (
          <Alert severity="error" sx={{ mb: 2 }}>
            Failed to load holdings: {error.message}
          </Alert>
        ) : holdings.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            No positions found. Add positions to your portfolio to see them here.
          </Typography>
        ) : (
          <List dense>
            {holdings.slice(0, 5).map((holding, idx) => (
              <ListItem key={idx} sx={{ px: 0, py: 1 }}>
                <ListItemText
                  primary={holding.symbol}
                  secondary={`${holding.shares} shares @ $${holding.avgPrice}`}
                  primaryTypographyProps={{ variant: 'body2', fontWeight: 600 }}
                  secondaryTypographyProps={{ variant: 'caption' }}
                />
                <Typography variant="body2" sx={{ fontWeight: 600 }}>
                  ${(holding.shares * holding.avgPrice).toLocaleString()}
                </Typography>
              </ListItem>
            ))}
          </List>
        )}
        <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
          Your current investment positions
        </Typography>
      </CardContent>
    </Card>
  );
}

// User Settings Widget - Improved
function UserSettingsWidget({ user }) {
  const { settings, isLoading, error } = useUserSettings();

  return (
    <Card>
      <CardContent>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
          <Settings sx={{ color: 'primary.main', mr: 1 }} />
          <Typography variant="h6" sx={{ fontWeight: 600 }}>User Settings</Typography>
          <Tooltip title="Your account settings and preferences" arrow>
            <Info sx={{ color: 'grey.500', ml: 1, fontSize: 18 }} />
          </Tooltip>
        </Box>
        {isLoading ? (
          <Box display="flex" alignItems="center" gap={2}>
            <CircularProgress size={20} />
            <Typography>Loading settings...</Typography>
          </Box>
        ) : error ? (
          <Alert severity="error" sx={{ mb: 2 }}>
            Failed to load settings: {error.message}
          </Alert>
        ) : user ? (
          <Grid container spacing={2}>
            <Grid item xs={12} sm={6}>
              <Box sx={{ p: 2, bgcolor: 'grey.50', borderRadius: 1 }}>
                <Typography variant="body2" color="text.secondary">Email</Typography>
                <Typography variant="body1" sx={{ fontWeight: 600 }}>
                  {user.email}
                </Typography>
              </Box>
            </Grid>
            <Grid item xs={12} sm={6}>
              <Box sx={{ p: 2, bgcolor: 'grey.50', borderRadius: 1 }}>
                <Typography variant="body2" color="text.secondary">Theme</Typography>
                <Typography variant="body1" sx={{ fontWeight: 600 }}>
                  {settings.theme || 'Light'}
                </Typography>
              </Box>
            </Grid>
            <Grid item xs={12}>
              <Box sx={{ display: 'flex', gap: 1, mt: 1 }}>
                <Button size="small" variant="outlined" startIcon={<LinkIcon />}>
                  Connect Broker
                </Button>
                <Button size="small" variant="outlined" startIcon={<ContactSupport />}>
                  Contact Support
                </Button>
              </Box>
            </Grid>
          </Grid>
        ) : (
          <Typography variant="body2" color="text.secondary">
            Please log in to view settings
          </Typography>
        )}
      </CardContent>
    </Card>
  );
}

const Dashboard = () => {
  const [selectedSymbol, setSelectedSymbol] = useState('AAPL');
  const [addPositionOpen, setAddPositionOpen] = useState(false);
  const [addWatchlistOpen, setAddWatchlistOpen] = useState(false);

  // User context
  const { user, isLoading: userLoading, isAuthenticated } = useUser();
  
  // Watchlist management
  const { watchlist, addSymbol, removeSymbol } = useWatchlist();
  
  // Portfolio management
  const { portfolio, updatePositions } = usePortfolio();
  
  // Portfolio metrics
  const { metrics } = usePortfolioMetrics();

  // Symbol options
  const { data: symbolListData } = useQuery({
    queryKey: ['dashboard-symbol-list'],
    queryFn: async () => {
      const response = await api.get('/dashboard/symbols');
      return response.data;
    },
    staleTime: 60 * 60 * 1000
  });
  
  const SYMBOL_OPTIONS = Array.isArray(symbolListData?.data) && symbolListData.data.length > 0
    ? symbolListData.data
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
        </Box>
      </Box>
      <Divider sx={{ mb: 3 }} />

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
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>{metrics.sharpe?.toFixed(2) || 'N/A'}</Typography>
                  </Grid>
                  <Grid item xs={6}>
                    <Typography variant="caption" color="text.secondary">Beta</Typography>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>{metrics.beta?.toFixed(2) || 'N/A'}</Typography>
                  </Grid>
                  <Grid item xs={6}>
                    <Typography variant="caption" color="text.secondary">Max Drawdown</Typography>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>{(metrics.maxDrawdown * 100)?.toFixed(1) || 'N/A'}%</Typography>
                  </Grid>
                  <Grid item xs={6}>
                    <Typography variant="caption" color="text.secondary">Volatility</Typography>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>{(metrics.volatility * 100)?.toFixed(1) || 'N/A'}%</Typography>
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

export default Dashboard;
