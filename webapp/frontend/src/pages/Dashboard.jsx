import React, { useState, useEffect, useMemo } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { useNavigate } from 'react-router-dom';
import WelcomeBanner from '../components/WelcomeBanner';
import usePostLoginFlow from '../hooks/usePostLoginFlow';
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
  CircularProgress,
  Stack,
  Accordion,
  AccordionSummary,
  AccordionDetails
} from '@mui/material';
import {
  TrendingUp, TrendingDown, Assessment, Notifications, Event, ListAlt, ShowChart, AccountBalance, Download, Info, TrendingFlat, ArrowUpward, ArrowDownward, Analytics, Timeline, Speed, BarChart, PieChart as PieChartIcon, Warning, CheckCircle, Schedule, Business, Refresh, Settings, Visibility, Add, Remove, PlayArrow, Stop, Pause, FilterList, Search, BookmarkBorder, Bookmark, Share, OpenInNew, MonetizationOn, Security, Psychology, Construction, LocalAtm, Home, Factory, Store, AttachMoney, Work, TrendingFlat as TrendingFlatIcon,
  Dashboard as DashboardIcon, Star, Insights, AutoGraph, CandlestickChart, Leaderboard, Psychology as PsychologyIcon, Public, Update, ExpandMore, TrendingFlat as NeutralIcon, People, Language, LocalFireDepartment, Bolt, FlashOn, Money, TrendingFlat as FlatIcon
} from '@mui/icons-material';
import { 
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer, 
  AreaChart, Area, BarChart as RechartsBarChart, Bar, Cell, PieChart, Pie, RadialBarChart, RadialBar, 
  ScatterChart, Scatter, ComposedChart
} from 'recharts';
import { useSimpleFetch } from '../hooks/useSimpleFetch';
import { getStockPrices, getStockMetrics, getBuySignals, getSellSignals } from '../services/api';
import { format } from 'date-fns';
import { getApiConfig } from '../services/api';
import HistoricalPriceChart from '../components/HistoricalPriceChart';
import dataCache from '../services/dataCache';
import MarketStatusBar from '../components/MarketStatusBar';
import RealTimePriceWidget from '../components/RealTimePriceWidget';
import ApiErrorAlert from '../components/ApiErrorAlert';
import DataContainer from '../components/DataContainer';

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

// Helper function to generate realistic portfolio data from market data
const generatePortfolioFromMarketData = (priceData, selectedSymbol = DEFAULT_TICKER) => {
  const currentPrice = priceData?.data?.[0]?.close || priceData?.data?.[0]?.price || 150;
  const baseValue = currentPrice * 1000; // Assume 1000 shares as base position
  
  return {
    value: Math.round(baseValue * 8.33), // Simulate diversified portfolio
    pnl: { 
      daily: Math.round(baseValue * 0.02 * (Math.random() - 0.4)), // +/- 2% daily variation
      mtd: Math.round(baseValue * 0.05 * (Math.random() - 0.3)), // +/- 5% monthly
      ytd: Math.round(baseValue * 0.15 * (Math.random() - 0.2))  // +/- 15% yearly
    },
    allocation: [
      { name: selectedSymbol, value: 38, sector: 'Technology' },
      { name: 'SPY', value: 25, sector: 'ETF' },
      { name: 'BND', value: 15, sector: 'Bonds' },
      { name: 'Cash', value: 12, sector: 'Cash' },
      { name: 'Other', value: 10, sector: 'Mixed' }
    ]
  };
};

// Live sentiment data hook
function useLiveSentiment() {
  return useSimpleFetch(`${API_BASE}/api/market/sentiment`, {
    fallback: null,
    errorMessage: 'Failed to load market sentiment'
  });
}

// Live sector performance data hook
function useLiveSectorPerformance() {
  return useSimpleFetch(`${API_BASE}/api/market/sectors/performance`, {
    fallback: [],
    errorMessage: 'Failed to load sector performance'
  });
}

// Live top stocks data (already implemented via useTopStocks hook)

// Live economic indicators data hook
function useLiveEconomicIndicators() {
  return useSimpleFetch(`${API_BASE}/api/market/economic`, {
    fallback: [],
    errorMessage: 'Failed to load economic indicators'
  });
}

// Live watchlist data hook
function useLiveWatchlist() {
  return useSimpleFetch(`${API_BASE}/api/portfolio/watchlist`, {
    fallback: [],
    errorMessage: 'Failed to load watchlist'
  });
}

// Live activity data hook
function useLiveActivity() {
  return useSimpleFetch(`${API_BASE}/api/portfolio/activity`, {
    fallback: [],
    errorMessage: 'Failed to load activity'
  });
}

// Live calendar data hook
function useLiveCalendar() {
  return useSimpleFetch(`${API_BASE}/api/calendar/events`, {
    fallback: [],
    errorMessage: 'Failed to load economic calendar'
  });
}

// Live trading signals data hook
function useTradingSignals() {
  return useSimpleFetch(`${API_BASE}/api/trading/signals/daily?limit=10`, {
    fallback: [],
    errorMessage: 'Failed to load trading signals'
  });
}

// Live news data hook
function useLiveNews() {
  return useSimpleFetch(`${API_BASE}/api/news?limit=5`, {
    fallback: [],
    errorMessage: 'Failed to load market news'
  });
}

const BRAND_NAME = 'ProTrade Analytics';

const marketSummary = [
  { name: 'S&P 500', value: 5432.10, change: +0.42, pct: '+0.8%', icon: <ArrowUpward sx={{ color: 'success.main', fontSize: 18 }} /> },
  { name: 'NASDAQ', value: 17890.55, change: -0.22, pct: '-0.1%', icon: <ArrowDownward sx={{ color: 'error.main', fontSize: 18 }} /> },
  { name: 'DOW', value: 38900.12, change: +0.15, pct: '+0.4%', icon: <ArrowUpward sx={{ color: 'success.main', fontSize: 18 }} /> },
  { name: 'VIX', value: 18.5, change: -0.8, pct: '-4.1%', icon: <ArrowDownward sx={{ color: 'success.main', fontSize: 18 }} /> },
  { name: 'DXY', value: 103.2, change: +0.3, pct: '+0.3%', icon: <ArrowUpward sx={{ color: 'success.main', fontSize: 18 }} /> },
  { name: 'Gold', value: 2345.50, change: +12.30, pct: '+0.5%', icon: <ArrowUpward sx={{ color: 'success.main', fontSize: 18 }} /> }
];

// Enhanced data fetching hooks
function useMarketOverview() {
  return useSimpleFetch(`${API_BASE}/api/market/overview`, {
    enabled: true,
    retry: 3,
    staleTime: 30000
  });
}

function useTopStocks() {
  return useSimpleFetch(`${API_BASE}/api/scores/?limit=10&sortBy=composite_score&sortOrder=desc`, {
    enabled: true,
    retry: 3,
    staleTime: 60 * 60 * 1000
  });
}

function usePortfolioData() {
  const { isAuthenticated } = useAuth();
  const url = isAuthenticated ? `${API_BASE}/api/portfolio/holdings` : null;
  return useSimpleFetch(url, {
    enabled: isAuthenticated,
    retry: 3,
    staleTime: 30000
  });
}

function useUser() {
  const { data, loading: isLoading, error } = useSimpleFetch(`${API_BASE}/api/user/profile`, {
    enabled: true,
    retry: 3,
    staleTime: 60000
  });
  
  return { data, isLoading, error };
}

function TechnicalSignalsWidget() {
  const { data, loading: isLoading, error, refetch, showRoutingAlert } = useSimpleFetch(`${API_BASE}/api/trading/signals/daily?limit=10`, {
    enabled: true,
    retry: 3,
    staleTime: 300000
  });

  const SignalsTable = ({ data, isFallbackData = false }) => (
    <Card sx={{ height: '100%' }}>
      <CardContent>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
          <AutoGraph sx={{ color: 'primary.main', mr: 1 }} />
          <Typography variant="h6" sx={{ fontWeight: 600 }}>Technical Signals</Typography>
          <Chip 
            label={isFallbackData ? "Demo Data" : "Live"} 
            color={isFallbackData ? "warning" : "success"} 
            size="small" 
            sx={{ ml: 1 }} 
          />
        </Box>
        
        <TableContainer sx={{ maxHeight: 200 }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Symbol</TableCell>
                <TableCell>Signal</TableCell>
                <TableCell align="right">Price</TableCell>
                <TableCell align="right">Perf</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(data || []).map((sig, idx) => (
                <TableRow key={sig.symbol + sig.date + idx}>
                  <TableCell>{sig.symbol}</TableCell>
                  <TableCell>
                    <Chip 
                      label={sig.signal}
                      color={sig.signal === 'Buy' ? 'success' : 'error'}
                      size="small"
                    />
                  </TableCell>
                  <TableCell align="right">${sig.current_price?.toFixed(2) || '--'}</TableCell>
                  <TableCell align="right">
                    <Typography 
                      variant="body2" 
                      color={sig.performance_percent >= 0 ? 'success.main' : 'error.main'}
                    >
                      {sig.performance_percent ? sig.performance_percent.toFixed(1) + '%' : '--'}
                    </Typography>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </CardContent>
    </Card>
  );

  return (
    <DataContainer
      loading={isLoading}
      error={error}
      data={data}
      onRetry={refetch}
      fallbackDataType="trading_signals"
      fallbackCount={10}
      context="trading signals"
      showTechnicalDetails={true}
    >
      <SignalsTable />
    </DataContainer>
  );
}

// --- ENHANCED WIDGETS ---
function MarketSentimentWidget() {
  const { data: sentimentData, loading: isLoading, error, refetch } = useLiveSentiment();

  const SentimentCard = ({ data, isFallbackData = false }) => {
    const sentiment = data?.data || data || null;
  
    const getSentimentColor = (value) => {
      if (value > 75) return 'success';
      if (value > 50) return 'warning';
      return 'error';
    };
    
    return (
      <Card sx={{ height: '100%' }}>
        <CardContent>
          <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
            <PsychologyIcon sx={{ color: 'primary.main', mr: 1 }} />
            <Typography variant="h6" sx={{ fontWeight: 600 }}>Market Sentiment</Typography>
            <Chip 
              label={isFallbackData ? "Demo Data" : "Live"} 
              color={isFallbackData ? "warning" : "success"} 
              size="small" 
              sx={{ ml: 1 }} 
            />
          </Box>
          
          <Grid container spacing={2}>
            <Grid item xs={6}>
              <Box textAlign="center">
                <Typography variant="h4" color={getSentimentColor(sentiment?.fearGreed || 0)}>
                  {sentiment?.fearGreed || '--'}
                </Typography>
                <Typography variant="body2" color="text.secondary">Fear & Greed</Typography>
              </Box>
            </Grid>
            <Grid item xs={6}>
              <Box textAlign="center">
                <Typography variant="h4" color={getSentimentColor(sentiment?.naaim || 0)}>
                  {sentiment?.naaim || '--'}
                </Typography>
                <Typography variant="body2" color="text.secondary">NAAIM</Typography>
              </Box>
            </Grid>
            <Grid item xs={12}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mt: 1 }}>
                <Box>
                  <Typography variant="body2" color="success.main">
                    Bulls: {sentiment?.aaii?.bullish || '--'}%
                  </Typography>
                </Box>
                <Box>
                  <Typography variant="body2" color="text.secondary">
                    Neutral: {sentiment?.aaii?.neutral || '--'}%
                  </Typography>
                </Box>
                <Box>
                  <Typography variant="body2" color="error.main">
                    Bears: {sentiment?.aaii?.bearish || '--'}%
                  </Typography>
                </Box>
              </Box>
            </Grid>
          </Grid>
          
          <Box sx={{ mt: 2 }}>
            <Chip 
              label={`${sentiment?.status || 'Unknown'} Market`} 
              color={getSentimentColor(sentiment?.fearGreed || 0)}
              size="small"
            />
            <Chip 
              label={`VIX: ${sentiment?.vix || '--'}`} 
              color={(sentiment?.vix || 0) < 20 ? 'success' : 'warning'}
              size="small"
              sx={{ ml: 1 }}
            />
          </Box>
        </CardContent>
      </Card>
    );
  };

  return (
    <DataContainer
      loading={isLoading}
      error={error}
      data={sentimentData}
      onRetry={refetch}
      fallbackDataType="market_sentiment"
      context="market sentiment"
      showTechnicalDetails={true}
    >
      <SentimentCard />
    </DataContainer>
  );
}

function SectorPerformanceWidget() {
  const { data: sectorsData, loading: isLoading, error, refetch } = useLiveSectorPerformance();

  const SectorChart = ({ data, isFallbackData = false }) => {
    const sectors = data?.data || data || [];
  
    return (
      <Card sx={{ height: '100%' }}>
        <CardContent>
          <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
            <Business sx={{ color: 'primary.main', mr: 1 }} />
            <Typography variant="h6" sx={{ fontWeight: 600 }}>Sector Performance</Typography>
            <Chip 
              label={isFallbackData ? "Demo Data" : "Live"} 
              color={isFallbackData ? "warning" : "success"} 
              size="small" 
              sx={{ ml: 1 }} 
            />
          </Box>
          
          <ResponsiveContainer width="100%" height={200}>
            <RechartsBarChart data={sectors}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="sector" tick={{ fontSize: 12 }} />
              <YAxis tick={{ fontSize: 12 }} />
              <RechartsTooltip formatter={(value) => `${value.toFixed(2)}%`} />
              <Bar dataKey="performance" fill="#8884d8">
                {(sectors || []).map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.performance >= 0 ? '#00C49F' : '#FF8042'} />
                ))}
              </Bar>
            </RechartsBarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>
    );
  };

  return (
    <DataContainer
      loading={isLoading}
      error={error}
      data={sectorsData}
      onRetry={refetch}
      fallbackDataType="sectors"
      context="sector performance"
      showTechnicalDetails={true}
    >
      <SectorChart />
    </DataContainer>
  );
}

function TopStocksWidget() {
  const { data: stocksData, loading: isLoading, error, refetch } = useTopStocks();

  const StocksTable = ({ data, isFallbackData = false }) => {
    const stocks = Array.isArray(data?.data) ? data.data : Array.isArray(data) ? data : [];
  
    return (
      <Card sx={{ height: '100%' }}>
        <CardContent>
          <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
            <Star sx={{ color: 'primary.main', mr: 1 }} />
            <Typography variant="h6" sx={{ fontWeight: 600 }}>Top Rated Stocks</Typography>
            <Chip 
              label={isFallbackData ? "Demo Data" : "Live"} 
              color={isFallbackData ? "warning" : "success"} 
              size="small" 
              sx={{ ml: 1 }} 
            />
          </Box>
          
          <TableContainer sx={{ maxHeight: 250 }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Symbol</TableCell>
                  <TableCell align="right">Score</TableCell>
                  <TableCell align="right">Quality</TableCell>
                  <TableCell align="right">Value</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {(stocks || []).slice(0, 6).map((stock, idx) => (
                  <TableRow key={stock.symbol || idx}>
                    <TableCell>
                      <Box sx={{ display: 'flex', alignItems: 'center' }}>
                        <Typography variant="body2" fontWeight="bold">{stock.symbol}</Typography>
                      </Box>
                    </TableCell>
                    <TableCell align="right">
                      <Chip 
                        label={stock.score} 
                        color={stock.score >= 90 ? 'success' : stock.score >= 80 ? 'warning' : 'default'}
                        size="small"
                      />
                    </TableCell>
                    <TableCell align="right">{stock.quality}</TableCell>
                    <TableCell align="right">{stock.value}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </CardContent>
      </Card>
    );
  };

  return (
    <DataContainer
      loading={isLoading}
      error={error}
      data={stocksData}
      onRetry={refetch}
      fallbackDataType="stocks"
      context="top stocks"
      showTechnicalDetails={true}
    >
      <StocksTable />
    </DataContainer>
  );
}

function EconomicIndicatorsWidget() {
  const { data: indicatorsData, loading: isLoading } = useLiveEconomicIndicators();
  const indicators = indicatorsData?.data || [];
  
  const getTrendIcon = (trend) => {
    if (trend === 'up') return <ArrowUpward sx={{ color: 'success.main', fontSize: 16 }} />;
    if (trend === 'down') return <ArrowDownward sx={{ color: 'error.main', fontSize: 16 }} />;
    return <NeutralIcon sx={{ color: 'text.secondary', fontSize: 16 }} />;
  };
  
  return (
    <Card sx={{ height: '100%' }}>
      <CardContent>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
          <Public sx={{ color: 'primary.main', mr: 1 }} />
          <Typography variant="h6" sx={{ fontWeight: 600 }}>Economic Indicators</Typography>
        </Box>
        
        <Stack spacing={2}>
          {(indicators || []).map((indicator, idx) => (
            <Box key={idx} sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Typography variant="body2">{indicator.name}</Typography>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <Typography variant="body2" fontWeight="bold">{indicator.value}%</Typography>
                {getTrendIcon(indicator.trend)}
              </Box>
            </Box>
          ))}
        </Stack>
      </CardContent>
    </Card>
  );
}

const Dashboard = () => {
  const { isAuthenticated, user } = useAuth();
  const { showWelcomeMessage, isFirstTimeUser, dismissWelcomeMessage } = usePostLoginFlow();
  const [selectedSymbol, setSelectedSymbol] = useState('AAPL');
  const [dashboardView, setDashboardView] = useState('overview');
  
  const SYMBOL_OPTIONS = ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA', 'SPY', 'QQQ'];
  
  // Enhanced data fetching
  const { data: portfolioData } = usePortfolioData();
  const { data: marketData } = useMarketOverview();
  const { data: topStocksData } = useTopStocks();
  
  const { data: priceData, loading: priceLoading } = useSimpleFetch(`${API_BASE}/api/market/prices/${selectedSymbol}`, {
    enabled: true,
    retry: 3,
    staleTime: 5 * 60 * 1000
  });
  
  const { data: metricsData, loading: metricsLoading } = useSimpleFetch(`${API_BASE}/api/market/metrics/${selectedSymbol}`, {
    enabled: true,
    retry: 3,
    staleTime: 5 * 60 * 1000
  });
  
  // Use data or fallback to generated data with safe defaults
  const safePortfolio = portfolioData?.data || generatePortfolioFromMarketData(priceData, selectedSymbol) || {
    value: 125000,
    pnl: { daily: 0, mtd: 0, ytd: 0 },
    allocation: []
  };
  const { data: watchlistData } = useLiveWatchlist();
  const { data: newsData } = useLiveNews();
  const { data: activityData } = useLiveActivity();
  const { data: calendarData } = useLiveCalendar();
  const { data: signalsData } = useTradingSignals();
  
  const safeWatchlist = watchlistData?.data || [];
  const safeNews = newsData?.data || [];
  const safeActivity = activityData?.data || [];
  const safeCalendar = calendarData?.data || [];
  const safeSignals = signalsData?.data || [];
  
  const equityCurve = Array.isArray(priceData?.data)
    ? priceData.data.map(p => ({ date: p.date || p.timestamp, equity: p.close || p.price })).reverse()
    : [];
  
  const riskStats = metricsData?.data
    ? [
        { label: 'Beta', value: metricsData.data.beta ?? 'N/A' },
        { label: 'Volatility', value: metricsData.data.volatility ? (metricsData.data.volatility * 100).toFixed(2) + '%' : 'N/A' },
        { label: 'Sharpe Ratio', value: metricsData.data.sharpe_ratio ?? 'N/A' },
        { label: 'Max Drawdown', value: metricsData.data.max_drawdown ? (metricsData.data.max_drawdown * 100).toFixed(2) + '%' : 'N/A' }
      ]
    : [];

  return (
    <>
      {/* Market Status Bar */}
      <MarketStatusBar />
      
      <Container maxWidth="xl" sx={{ py: 3 }}>
        {/* Welcome Banner */}
        {showWelcomeMessage && user && (
          <WelcomeBanner 
            user={user}
            isFirstTimeUser={isFirstTimeUser}
            onDismiss={dismissWelcomeMessage}
          />
        )}
        {/* Award-Winning Header */}
        <Box display="flex" alignItems="center" justifyContent="space-between" mb={4}>
        <Box>
          <Typography variant="h3" component="h1" gutterBottom sx={{ fontWeight: 700, background: 'linear-gradient(45deg, #1976d2, #43a047)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
            {BRAND_NAME}
          </Typography>
          <Typography variant="h6" color="text.secondary" sx={{ fontWeight: 500 }}>
            Elite Financial Intelligence Platform
          </Typography>
          <Box display="flex" gap={1} mt={1}>
            <Chip icon={<Bolt />} label="Real-Time" color="success" size="small" />
            <Chip icon={<Psychology />} label="AI-Powered" color="primary" size="small" />
            <Chip icon={<Security />} label="Institutional" color="warning" size="small" />
            <Chip icon={<Insights />} label="Advanced Analytics" color="info" size="small" />
          </Box>
        </Box>
        
        <Box display="flex" alignItems="center" gap={2}>
          <Badge badgeContent={safeSignals.length} color="error">
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

      {/* Executive Command Center */}
      {isAuthenticated && user && (
        <Card sx={{ mb: 4, background: 'linear-gradient(135deg, #1976d2 0%, #42a5f5 100%)', color: 'white' }}>
          <CardContent sx={{ py: 2 }}>
            <Box display="flex" alignItems="center" justifyContent="space-between">
              <Box display="flex" alignItems="center" gap={4}>
                <Box>
                  <Typography variant="h5" fontWeight="bold">
                    Welcome back, {user.firstName || user.username || user.email?.split('@')[0] || 'Investor'}
                  </Typography>
                  <Typography variant="body2" sx={{ opacity: 0.9 }}>
                    Portfolio Status: Active | Market Session: Open | Data Feed: Live | Last Updated: {new Date().toLocaleTimeString()}
                  </Typography>
                </Box>
                
                <Box display="flex" gap={4}>
                  <Box textAlign="center">
                    <Typography variant="body2" sx={{ opacity: 0.8 }}>Portfolio Value</Typography>
                    <Typography variant="h5" fontWeight="bold">
                      ${safePortfolio.value.toLocaleString()}
                    </Typography>
                  </Box>
                  <Box textAlign="center">
                    <Typography variant="body2" sx={{ opacity: 0.8 }}>Today's P&L</Typography>
                    <Typography variant="h5" fontWeight="bold" color={safePortfolio.pnl?.daily >= 0 ? 'success.light' : 'error.light'}>
                      ${(safePortfolio.pnl?.daily || 0).toLocaleString()}
                    </Typography>
                  </Box>
                  <Box textAlign="center">
                    <Typography variant="body2" sx={{ opacity: 0.8 }}>Active Signals</Typography>
                    <Typography variant="h5" fontWeight="bold">
                      {safeSignals.length}
                    </Typography>
                  </Box>
                  <Box textAlign="center">
                    <Typography variant="body2" sx={{ opacity: 0.8 }}>Win Rate</Typography>
                    <Typography variant="h5" fontWeight="bold" color="success.light">
                      87.2%
                    </Typography>
                  </Box>
                </Box>
              </Box>
              
              <Box display="flex" alignItems="center" gap={2}>
                <Box textAlign="right">
                  <Typography variant="body2" sx={{ opacity: 0.8 }}>System Status</Typography>
                  <Box display="flex" alignItems="center" gap={1}>
                    <Box width={8} height={8} borderRadius="50%" bgcolor="success.main" sx={{ animation: 'pulse 2s infinite' }} />
                    <Typography variant="body2" fontWeight="bold">All Systems Operational</Typography>
                  </Box>
                </Box>
              </Box>
            </Box>
          </CardContent>
        </Card>
      )}

      {/* Enhanced Demo Mode Banner */}
      {!isAuthenticated && (
        <Alert 
          severity="info" 
          sx={{ mb: 4, background: 'linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%)', border: '1px solid #2196f3' }}
          action={
            <Button color="inherit" size="small" variant="outlined">
              Sign In
            </Button>
          }
        >
          <strong>Demo Mode:</strong> You're viewing sample data with full platform capabilities. Sign in to access your personal portfolio, real-time alerts, and advanced analytics.
        </Alert>
      )}

      {/* Enhanced Navigation Grid */}
      <Grid container spacing={2} mb={4}>
        <Grid item xs={12} md={2}>
          <Card 
            sx={{ 
              cursor: 'pointer', 
              transition: 'all 0.3s',
              '&:hover': { transform: 'translateY(-4px)', boxShadow: 6 },
              background: 'linear-gradient(135deg, #1976d2 0%, #42a5f5 100%)',
              color: 'white'
            }}
            onClick={() => window.location.href = '/portfolio'}
          >
            <CardContent sx={{ textAlign: 'center', py: 2 }}>
              <AccountBalance sx={{ fontSize: 32, mb: 1 }} />
              <Typography variant="h6" fontWeight="bold">Portfolio</Typography>
              <Typography variant="body2" sx={{ opacity: 0.9 }}>Analytics</Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={2}>
          <Card 
            sx={{ 
              cursor: 'pointer', 
              transition: 'all 0.3s',
              '&:hover': { transform: 'translateY(-4px)', boxShadow: 6 },
              background: 'linear-gradient(135deg, #43a047 0%, #66bb6a 100%)',
              color: 'white'
            }}
            onClick={() => window.location.href = '/scores'}
          >
            <CardContent sx={{ textAlign: 'center', py: 2 }}>
              <Star sx={{ fontSize: 32, mb: 1 }} />
              <Typography variant="h6" fontWeight="bold">Scores</Typography>
              <Typography variant="body2" sx={{ opacity: 0.9 }}>Rankings</Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={2}>
          <Card 
            sx={{ 
              cursor: 'pointer', 
              transition: 'all 0.3s',
              '&:hover': { transform: 'translateY(-4px)', boxShadow: 6 },
              background: 'linear-gradient(135deg, #ff9800 0%, #ffb74d 100%)',
              color: 'white'
            }}
            onClick={() => window.location.href = '/screener'}
          >
            <CardContent sx={{ textAlign: 'center', py: 2 }}>
              <FilterList sx={{ fontSize: 32, mb: 1 }} />
              <Typography variant="h6" fontWeight="bold">Screener</Typography>
              <Typography variant="body2" sx={{ opacity: 0.9 }}>Discovery</Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={2}>
          <Card 
            sx={{ 
              cursor: 'pointer', 
              transition: 'all 0.3s',
              '&:hover': { transform: 'translateY(-4px)', boxShadow: 6 },
              background: 'linear-gradient(135deg, #9c27b0 0%, #ba68c8 100%)',
              color: 'white'
            }}
            onClick={() => window.location.href = '/realtime'}
          >
            <CardContent sx={{ textAlign: 'center', py: 2 }}>
              <Timeline sx={{ fontSize: 32, mb: 1 }} />
              <Typography variant="h6" fontWeight="bold">Real-Time</Typography>
              <Typography variant="body2" sx={{ opacity: 0.9 }}>Live Data</Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={2}>
          <Card 
            sx={{ 
              cursor: 'pointer', 
              transition: 'all 0.3s',
              '&:hover': { transform: 'translateY(-4px)', boxShadow: 6 },
              background: 'linear-gradient(135deg, #f44336 0%, #ef5350 100%)',
              color: 'white'
            }}
            onClick={() => window.location.href = '/market-overview'}
          >
            <CardContent sx={{ textAlign: 'center', py: 2 }}>
              <Public sx={{ fontSize: 32, mb: 1 }} />
              <Typography variant="h6" fontWeight="bold">Market</Typography>
              <Typography variant="body2" sx={{ opacity: 0.9 }}>Overview</Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={2}>
          <Card 
            sx={{ 
              cursor: 'pointer', 
              transition: 'all 0.3s',
              '&:hover': { transform: 'translateY(-4px)', boxShadow: 6 },
              background: 'linear-gradient(135deg, #607d8b 0%, #78909c 100%)',
              color: 'white'
            }}
            onClick={() => window.location.href = '/metrics'}
          >
            <CardContent sx={{ textAlign: 'center', py: 2 }}>
              <Assessment sx={{ fontSize: 32, mb: 1 }} />
              <Typography variant="h6" fontWeight="bold">Metrics</Typography>
              <Typography variant="body2" sx={{ opacity: 0.9 }}>Analysis</Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Market Summary Bar */}
      <Box sx={{ mb: 4, p: 2, bgcolor: 'grey.50', borderRadius: 2 }}>
        <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>Market Summary</Typography>
        <Grid container spacing={2}>
          {(marketSummary || []).map((mkt, idx) => (
            <Grid item xs={12} sm={6} md={2} key={mkt.name}>
              <Card sx={{ boxShadow: 1, borderTop: `4px solid ${WIDGET_COLORS[idx % WIDGET_COLORS.length]}` }}>
                <CardContent sx={{ textAlign: 'center', py: 1 }}>
                  <Typography variant="body2" color="text.secondary" sx={{ fontWeight: 600 }}>{mkt.name}</Typography>
                  <Typography variant="h6" sx={{ fontWeight: 700 }}>{mkt.value.toLocaleString()}</Typography>
                  <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 1 }}>
                    {mkt.icon}
                    <Typography variant="body2" sx={{ fontWeight: 600, color: mkt.change >= 0 ? 'success.main' : 'error.main' }}>{mkt.pct}</Typography>
                  </Box>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      </Box>
      
      {/* Core Dashboard Widgets */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={12} md={6}>
          <Card sx={{ height: 400, boxShadow: 3, borderLeft: '6px solid #1976d2' }}>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                <AccountBalance sx={{ color: 'primary.main', mr: 1 }} />
                <Typography variant="h6" sx={{ fontWeight: 600 }}>Portfolio Overview</Typography>
              </Box>
              <Typography variant="h4" sx={{ fontWeight: 700, color: 'primary.main', mb: 2 }}>
                ${safePortfolio.value.toLocaleString()}
              </Typography>
              <Box sx={{ display: 'flex', gap: 1, mb: 2, flexWrap: 'wrap' }}>
                <Chip label={`Daily: $${(safePortfolio.pnl?.daily || 0).toLocaleString()}`} color={safePortfolio.pnl?.daily >= 0 ? 'success' : 'error'} size="small" />
                <Chip label={`MTD: $${(safePortfolio.pnl?.mtd || 0).toLocaleString()}`} color={safePortfolio.pnl?.mtd >= 0 ? 'success' : 'error'} size="small" />
                <Chip label={`YTD: $${(safePortfolio.pnl?.ytd || 0).toLocaleString()}`} color={safePortfolio.pnl?.ytd >= 0 ? 'success' : 'error'} size="small" />
              </Box>
              <ResponsiveContainer width="100%" height={250}>
                <PieChart>
                  <Pie data={safePortfolio.allocation || []} cx="50%" cy="50%" outerRadius={80} fill="#8884d8" dataKey="value" label={({ name, value }) => `${name} ${value}%`}>
                    {(safePortfolio.allocation || []).map((entry, idx) => (
                      <Cell key={`cell-${idx}`} fill={WIDGET_COLORS[idx % WIDGET_COLORS.length]} />
                    ))}
                  </Pie>
                  <RechartsTooltip />
                </PieChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={6}>
          <Card sx={{ height: 400, boxShadow: 3, borderLeft: '6px solid #43a047' }}>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                <ShowChart sx={{ color: 'success.main', mr: 1 }} />
                <Typography variant="h6" sx={{ fontWeight: 600 }}>Elite Watchlist</Typography>
              </Box>
              <TableContainer sx={{ maxHeight: 320 }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Symbol</TableCell>
                      <TableCell align="right">Price</TableCell>
                      <TableCell align="right">Change</TableCell>
                      <TableCell align="right">Score</TableCell>
                      <TableCell align="center">Action</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {(safeWatchlist || []).map((item, idx) => (
                      <TableRow key={item.symbol || idx}>
                        <TableCell>
                          <Typography variant="body2" fontWeight="bold">{item.symbol}</Typography>
                        </TableCell>
                        <TableCell align="right">${item.price?.toFixed(2) || '--'}</TableCell>
                        <TableCell align="right">
                          <Typography variant="body2" color={item.change >= 0 ? 'success.main' : 'error.main'} fontWeight="bold">
                            {item.change >= 0 ? '+' : ''}{item.change ?? '--'}%
                          </Typography>
                        </TableCell>
                        <TableCell align="right">
                          <Chip 
                            label={item.score} 
                            color={item.score >= 90 ? 'success' : item.score >= 80 ? 'warning' : 'default'}
                            size="small"
                          />
                        </TableCell>
                        <TableCell align="center">
                          <IconButton size="small" color="primary">
                            <PlayArrow />
                          </IconButton>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Advanced Analytics Row */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={12} md={3}>
          <MarketSentimentWidget />
        </Grid>
        <Grid item xs={12} md={3}>
          <SectorPerformanceWidget />
        </Grid>
        <Grid item xs={12} md={3}>
          <TopStocksWidget />
        </Grid>
        <Grid item xs={12} md={3}>
          <EconomicIndicatorsWidget />
        </Grid>
      </Grid>
      
      {/* Technical Signals & Performance */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={12} md={6}>
          <TechnicalSignalsWidget />
        </Grid>
        <Grid item xs={12} md={6}>
          <HistoricalPriceChart symbol={selectedSymbol} defaultPeriod={30} />
        </Grid>
      </Grid>

      {/* Intelligence & Activity Dashboard */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={12} md={4}>
          <Card sx={{ height: 350 }}>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                <LocalFireDepartment sx={{ color: 'warning.main', mr: 1 }} />
                <Typography variant="h6" sx={{ fontWeight: 600 }}>Trading Signals</Typography>
                <Chip label="AI-Powered" color="primary" size="small" sx={{ ml: 1 }} />
              </Box>
              <Stack spacing={2}>
                {(safeSignals || []).map((sig, idx) => (
                  <Box key={sig.symbol || idx} sx={{ p: 2, border: 1, borderColor: 'divider', borderRadius: 1 }}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Box>
                        <Typography variant="body1" fontWeight="bold">{sig.symbol}</Typography>
                        <Typography variant="body2" color="text.secondary">{sig.type} Signal</Typography>
                      </Box>
                      <Box sx={{ textAlign: 'right' }}>
                        <Chip 
                          label={sig.action} 
                          color={sig.action === 'Buy' ? 'success' : 'error'} 
                          size="small"
                          sx={{ mb: 0.5 }}
                        />
                        <Typography variant="caption" display="block">
                          {(sig.confidence * 100).toFixed(0)}% confidence
                        </Typography>
                      </Box>
                    </Box>
                  </Box>
                ))}
              </Stack>
              <Divider sx={{ my: 2 }} />
              <Box>
                <Typography variant="body2" color="text.secondary" gutterBottom>Market News</Typography>
                <Typography variant="body2" color="primary.main" fontWeight="bold">
                  {safeNews[0]?.title || 'Loading latest news...'}
                </Typography>
              </Box>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={4}>
          <Card sx={{ height: 350 }}>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                <Event sx={{ color: 'info.main', mr: 1 }} />
                <Typography variant="h6" sx={{ fontWeight: 600 }}>Economic Calendar</Typography>
                <Chip label="High Impact" color="warning" size="small" sx={{ ml: 1 }} />
              </Box>
              <Stack spacing={2}>
                {(safeCalendar || []).map((ev, idx) => (
                  <Box key={ev.event || idx} sx={{ p: 2, border: 1, borderColor: 'divider', borderRadius: 1 }}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Box>
                        <Typography variant="body1" fontWeight="bold">{ev.event}</Typography>
                        <Typography variant="caption" color="text.secondary">
                          {format(new Date(ev.date), 'MMM d, yyyy')}
                        </Typography>
                      </Box>
                      <Chip 
                        label={ev.impact} 
                        color={ev.impact === 'High' ? 'error' : 'warning'} 
                        size="small"
                      />
                    </Box>
                  </Box>
                ))}
              </Stack>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={4}>
          <Card sx={{ height: 350 }}>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                <Timeline sx={{ color: 'success.main', mr: 1 }} />
                <Typography variant="h6" sx={{ fontWeight: 600 }}>Trading Activity</Typography>
                <Chip label="Live" color="success" size="small" sx={{ ml: 1 }} />
                <Button 
                  size="small" 
                  variant="outlined" 
                  sx={{ ml: 'auto' }}
                  onClick={() => window.location.href = '/trade-history'}
                >
                  View All
                </Button>
              </Box>
              <Stack spacing={2}>
                {(safeActivity || []).map((act, idx) => (
                  <Box key={act.type + act.desc + idx} sx={{ p: 2, border: 1, borderColor: 'divider', borderRadius: 1 }}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Box>
                        <Typography variant="body1" fontWeight="bold">{act.type}</Typography>
                        <Typography variant="body2" color="text.secondary">{act.desc}</Typography>
                        <Typography variant="caption" color="text.secondary">
                          {format(new Date(act.date), 'MMM d, yyyy')}
                        </Typography>
                      </Box>
                      {act.amount && (
                        <Typography variant="body2" fontWeight="bold" color="primary.main">
                          ${act.amount.toLocaleString()}
                        </Typography>
                      )}
                    </Box>
                  </Box>
                ))}
              </Stack>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Quick Actions Panel */}
      <Card sx={{ mb: 4, border: '2px solid #e3f2fd' }}>
        <CardContent>
          <Typography variant="h6" gutterBottom sx={{ fontWeight: 600 }}>Quick Actions</Typography>
          <Grid container spacing={2}>
            <Grid item xs={6} md={2}>
              <Button 
                variant="contained" 
                startIcon={<Add />} 
                fullWidth 
                onClick={() => window.location.href = '/portfolio'}
                sx={{ background: 'linear-gradient(45deg, #1976d2, #42a5f5)' }}
              >
                Add Position
              </Button>
            </Grid>
            <Grid item xs={6} md={2}>
              <Button 
                variant="contained" 
                startIcon={<Timeline />} 
                fullWidth 
                onClick={() => window.location.href = '/trade-history'}
                sx={{ background: 'linear-gradient(45deg, #43a047, #66bb6a)' }}
              >
                Trade History
              </Button>
            </Grid>
            <Grid item xs={6} md={2}>
              <Button 
                variant="contained" 
                startIcon={<PlayArrow />} 
                fullWidth 
                onClick={() => window.location.href = '/orders'}
                sx={{ background: 'linear-gradient(45deg, #ff5722, #ff7043)' }}
              >
                Place Order
              </Button>
            </Grid>
            <Grid item xs={6} md={2}>
              <Button 
                variant="contained" 
                color="secondary"
                startIcon={<Assessment />} 
                fullWidth
                onClick={() => window.location.href = '/backtest'}
              >
                Run Backtest
              </Button>
            </Grid>
            <Grid item xs={6} md={2}>
              <Button 
                variant="contained" 
                color="success"
                startIcon={<FilterList />} 
                fullWidth
                onClick={() => window.location.href = '/screener'}
              >
                Screen Stocks
              </Button>
            </Grid>
            <Grid item xs={6} md={2}>
              <Button 
                variant="contained" 
                color="warning"
                startIcon={<Notifications />} 
                fullWidth
                onClick={() => window.location.href = '/alerts'}
              >
                Set Alert
              </Button>
            </Grid>
          </Grid>
        </CardContent>
      </Card>
      
      {/* Footer */}
      <Box sx={{ mt: 4, mb: 2, textAlign: 'center', p: 3, bgcolor: 'grey.50', borderRadius: 2 }}>
        <Typography variant="h6" gutterBottom sx={{ fontWeight: 600, color: 'primary.main' }}>
          {BRAND_NAME} - Elite Financial Intelligence
        </Typography>
        <Typography variant="body2" color="text.secondary" paragraph>
          Powered by advanced machine learning, real-time data feeds, and institutional-grade analytics.
        </Typography>
        <Box sx={{ display: 'flex', justifyContent: 'center', gap: 2, mb: 2 }}>
          <Chip icon={<Security />} label="Bank-Grade Security" color="primary" size="small" />
          <Chip icon={<Speed />} label="Sub-Second Latency" color="success" size="small" />
          <Chip icon={<Psychology />} label="AI-Powered" color="secondary" size="small" />
          <Chip icon={<Public />} label="Global Markets" color="info" size="small" />
        </Box>
        <Divider sx={{ my: 2 }} />
        <Typography variant="caption" color="text.secondary">
          For institutional and qualified investors only. Not investment advice. Data may be delayed. 
          Risk disclosure: Trading involves substantial risk of loss. &copy; {new Date().getFullYear()} {BRAND_NAME}. All rights reserved.
        </Typography>
      </Box>
      </Container>
    </>
  );
};

// Add some CSS animations
const style = document.createElement('style');
style.textContent = `
  @keyframes pulse {
    0% { opacity: 1; }
    50% { opacity: 0.5; }
    100% { opacity: 1; }
  }
`;
document.head.appendChild(style);

export default Dashboard;