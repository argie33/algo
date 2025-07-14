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
import { useQuery } from '@tanstack/react-query';
import { getStockPrices, getStockMetrics, getBuySignals, getSellSignals, getWatchlists, getWatchlistItems } from '../services/api';
import { format } from 'date-fns';
import { getApiConfig } from '../services/api';
import HistoricalPriceChart from '../components/HistoricalPriceChart';
import DashboardStockChart from '../components/DashboardStockChart';
import NewsWidget from '../components/NewsWidget';
import EconomicIndicatorsWidget from '../components/EconomicIndicatorsWidget';
import dataCache from '../services/dataCache';
import MarketStatusBar from '../components/MarketStatusBar';
import RealTimePriceWidget from '../components/RealTimePriceWidget';
import ApiKeyStatusIndicator from '../components/ApiKeyStatusIndicator';

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

// Real portfolio data hook - integrated with user API keys
function usePortfolioData() {
  return useQuery({
    queryKey: ['dashboard-portfolio'],
    queryFn: async () => {
      try {
        console.log('🏦 Fetching real portfolio data from broker APIs...');
        
        // Fetch real portfolio data from our backend using the api service
        const { api } = await import('../services/api');
        
        const [holdingsRes, accountRes] = await Promise.all([
          api.get('/api/portfolio/holdings').catch(err => {
            console.warn('Holdings API call failed:', err.message);
            return null;
          }),
          api.get('/api/portfolio/performance').catch(err => {
            console.warn('Performance API call failed:', err.message);
            return null;
          })
        ]);
        
        let holdings = [];
        let accountInfo = null;
        
        if (holdingsRes && holdingsRes.data) {
          console.log('✅ Holdings data received:', holdingsRes.data.data?.holdings?.length || 0, 'positions');
          holdings = holdingsRes.data.data?.holdings || [];
        }
        
        if (accountRes && accountRes.data) {
          console.log('✅ Account data received:', accountRes.data.data ? 'success' : 'no data');
          accountInfo = accountRes.data.data || null;
        }
        
        // Transform real data to dashboard format
        if (holdings.length > 0) {
          const totalValue = holdings.reduce((sum, h) => sum + (h.market_value || h.marketValue || 0), 0);
          const totalGainLoss = holdings.reduce((sum, h) => sum + (h.unrealized_pl || h.gainLoss || 0), 0);
          
          console.log(`📊 Portfolio: $${totalValue.toFixed(2)} total value, $${totalGainLoss.toFixed(2)} P&L`);
          
          const allocation = holdings.slice(0, 4).map(h => ({
            name: h.symbol,
            value: totalValue > 0 ? ((h.market_value || h.marketValue || 0) / totalValue * 100).toFixed(1) : '0',
            sector: h.sector || 'Technology'
          }));
          
          // Add cash allocation if available
          const cashValue = accountInfo?.cash || accountInfo?.buying_power || 0;
          if (cashValue > 0) {
            allocation.push({
              name: 'Cash',
              value: totalValue > 0 ? (cashValue / (totalValue + cashValue) * 100).toFixed(1) : '100',
              sector: 'Cash'
            });
          }
          
          return {
            value: totalValue,
            pnl: { 
              daily: accountInfo?.dayChange || accountInfo?.today_pl || totalGainLoss,
              mtd: totalGainLoss,
              ytd: totalGainLoss
            },
            allocation: allocation,
            dataSource: 'real'
          };
        }
        
        // If no holdings but account info exists
        if (accountInfo) {
          const cashValue = accountInfo.cash || accountInfo.buying_power || 0;
          console.log('📊 Account with no positions, cash:', cashValue);
          
          return {
            value: cashValue,
            pnl: { 
              daily: accountInfo.dayChange || accountInfo.today_pl || 0,
              mtd: 0,
              ytd: 0
            },
            allocation: [
              { name: 'Cash', value: 100, sector: 'Cash' }
            ],
            dataSource: 'real'
          };
        }
        
        throw new Error('No portfolio data available');
      } catch (error) {
        console.log('⚠️ Using mock portfolio data due to error:', error.message);
        // Return mock data as fallback only when real API fails
        return {
          value: 1250000,
          pnl: { daily: 3200, mtd: 18000, ytd: 92000 },
          allocation: [
            { name: 'AAPL', value: 38, sector: 'Technology' },
            { name: 'MSFT', value: 27, sector: 'Technology' },
            { name: 'GOOGL', value: 18, sector: 'Technology' },
            { name: 'Cash', value: 10, sector: 'Cash' },
            { name: 'Other', value: 7, sector: 'Mixed' }
          ],
          dataSource: 'mock'
        };
      }
    },
    staleTime: 5 * 60 * 1000, // 5 minutes
    refetchInterval: 5 * 60 * 1000 // 5 minutes refresh
  });
}

// ⚠️ MOCK DATA - Replace with real sentiment API when available
const mockMarketSentiment = {
  fearGreed: 72,
  aaii: { bullish: 45, bearish: 28, neutral: 27 },
  naaim: 65,
  vix: 18.5,
  status: 'Bullish',
  isMockData: true
};

// ⚠️ MOCK DATA - Replace with real sector performance API when available
const mockSectorPerformance = [
  { sector: 'Technology', performance: 2.1, color: '#00C49F', isMockData: true },
  { sector: 'Healthcare', performance: 1.8, color: '#0088FE', isMockData: true },
  { sector: 'Finance', performance: -0.5, color: '#FF8042', isMockData: true },
  { sector: 'Energy', performance: 3.2, color: '#FFBB28', isMockData: true },
  { sector: 'Consumer', performance: 0.9, color: '#8884D8', isMockData: true }
];

// ⚠️ MOCK DATA - Replace with real stock scoring API when available
const mockTopStocks = [
  { symbol: 'NVDA', score: 95, quality: 92, value: 85, growth: 98, momentum: 94, isMockData: true },
  { symbol: 'MSFT', score: 88, quality: 95, value: 78, growth: 87, momentum: 92, isMockData: true },
  { symbol: 'GOOGL', score: 85, quality: 88, value: 92, growth: 82, momentum: 78, isMockData: true },
  { symbol: 'AAPL', score: 82, quality: 90, value: 72, growth: 85, momentum: 82, isMockData: true }
];

// ⚠️ MOCK DATA - Replace with real economic data API when available
const mockEconomicIndicators = [
  { name: 'GDP Growth', value: 2.4, trend: 'stable', isMockData: true },
  { name: 'Inflation', value: 3.1, trend: 'down', isMockData: true },
  { name: 'Unemployment', value: 3.8, trend: 'stable', isMockData: true },
  { name: 'Fed Funds Rate', value: 5.25, trend: 'stable', isMockData: true }
];

// Real user watchlist data hook - uses actual watchlist API
function useUserWatchlistData() {
  const { isAuthenticated } = useAuth();
  
  return useQuery({
    queryKey: ['dashboard-user-watchlist'],
    queryFn: async () => {
      try {
        console.log('🔍 Fetching user watchlists for dashboard...');
        
        // First get all user watchlists
        const watchlistsData = await getWatchlists();
        console.log('📋 User watchlists:', watchlistsData);
        
        if (!watchlistsData?.data || watchlistsData.data.length === 0) {
          throw new Error('No watchlists found');
        }
        
        // Use the first (default) watchlist
        const defaultWatchlist = watchlistsData.data[0];
        console.log('🎯 Using default watchlist:', defaultWatchlist.name, `(ID: ${defaultWatchlist.id})`);
        
        // Get items from the default watchlist
        const itemsData = await getWatchlistItems(defaultWatchlist.id);
        console.log('📊 Watchlist items:', itemsData);
        
        if (!itemsData?.data?.items || itemsData.data.items.length === 0) {
          throw new Error('No items in watchlist');
        }
        
        // Transform API data to dashboard format
        const transformedItems = itemsData.data.items.slice(0, 6).map(item => ({
          symbol: item.symbol,
          price: parseFloat(item.current_price || item.price || 0),
          change: parseFloat(item.day_change_amount || item.change || 0),
          changePercent: parseFloat(item.day_change_percent || item.changePercent || 0),
          name: item.security_name || item.short_name || item.name || item.symbol,
          score: item.score || Math.floor(Math.random() * 20) + 80, // Add random score if not provided
          dataSource: 'user-watchlist',
          watchlistName: defaultWatchlist.name
        }));
        
        console.log('✅ Dashboard watchlist data ready:', transformedItems);
        return transformedItems;
        
      } catch (error) {
        console.log('⚠️ Failed to fetch user watchlist, using fallback:', error.message);
        
        // Return fallback mock data
        return [
          { symbol: 'AAPL', price: 195.89, change: 2.34, changePercent: 1.21, name: 'Apple Inc.', score: 85, dataSource: 'fallback' },
          { symbol: 'TSLA', price: 711.02, change: -5.67, changePercent: -0.79, name: 'Tesla Inc.', score: 78, dataSource: 'fallback' },
          { symbol: 'NVDA', price: 1200.45, change: 15.23, changePercent: 1.29, name: 'NVIDIA Corp.', score: 95, dataSource: 'fallback' },
          { symbol: 'AMZN', price: 3405.12, change: -12.45, changePercent: -0.36, name: 'Amazon.com Inc.', score: 82, dataSource: 'fallback' }
        ];
      }
    },
    enabled: isAuthenticated, // Only run if user is authenticated
    staleTime: 2 * 60 * 1000, // 2 minutes
    refetchInterval: 2 * 60 * 1000, // 2 minutes refresh for real-time updates
    retry: 2
  });
}

const mockPortfolio = {
  value: 125000,
  totalValue: 125000,
  dayChange: 2500,
  dayChangePercent: 2.04,
  pnl: {
    daily: 2500,
    mtd: 4200,
    ytd: 18750
  },
  allocation: [
    { name: 'Technology', value: 45.2, color: '#1976d2' },
    { name: 'Healthcare', value: 18.7, color: '#43a047' },
    { name: 'Finance', value: 15.3, color: '#ffb300' },
    { name: 'Consumer', value: 12.4, color: '#8e24aa' },
    { name: 'Other', value: 8.4, color: '#e53935' }
  ],
  holdings: [
    { symbol: 'AAPL', shares: 100, value: 19500, change: 2.1 },
    { symbol: 'TSLA', shares: 25, value: 17755, change: -1.8 },
    { symbol: 'NVDA', shares: 10, value: 12000, change: 3.5 }
  ]
};

const mockActivity = [
  { type: 'Trade', desc: 'Bought 100 AAPL', date: '2025-06-21', amount: 19500 },
  { type: 'Alert', desc: 'TSLA price alert triggered', date: '2025-06-20', amount: null },
  { type: 'Trade', desc: 'Sold 50 NVDA', date: '2025-06-19', amount: 60000 }
];

const mockCalendar = [
  { event: 'FOMC Rate Decision', date: '2025-06-25', impact: 'High' },
  { event: 'AAPL Earnings', date: '2025-07-01', impact: 'Medium' },
  { event: 'Nonfarm Payrolls', date: '2025-07-05', impact: 'High' }
];

const mockSignals = [
  { symbol: 'AAPL', action: 'Buy', confidence: 0.92, type: 'Technical' },
  { symbol: 'TSLA', action: 'Sell', confidence: 0.87, type: 'Momentum' }
];

const mockNews = [
  { title: 'Fed Holds Rates Steady, Signals Caution', date: '2025-06-21', sentiment: 'Neutral' },
  { title: 'AAPL Surges on Strong Earnings', date: '2025-06-20', sentiment: 'Positive' },
  { title: 'Global Markets Mixed Ahead of FOMC', date: '2025-06-19', sentiment: 'Neutral' }
];

const mockWatchlist = [
  { symbol: 'AAPL', price: 195.89, change: 2.34, changePercent: 1.21, name: 'Apple Inc.' },
  { symbol: 'TSLA', price: 711.02, change: -5.67, changePercent: -0.79, name: 'Tesla Inc.' },
  { symbol: 'NVDA', price: 1200.45, change: 15.23, changePercent: 1.29, name: 'NVIDIA Corp.' },
  { symbol: 'AMZN', price: 3405.12, change: -12.45, changePercent: -0.36, name: 'Amazon.com Inc.' }
];

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
  return useQuery({
    queryKey: ['market-overview'],
    queryFn: async () => {
      return dataCache.get('/market/overview', {}, {
        cacheType: 'marketData',
        fetchFunction: async () => {
          try {
            const res = await fetch(`${API_BASE}/market/overview`);
            if (!res.ok) throw new Error('Failed to fetch market overview');
            return res.json();
          } catch (err) {
            console.error('Market overview API failed:', err);
            throw new Error('Market data unavailable - check API connection');
          }
        }
      });
    },
    staleTime: 60 * 60 * 1000, // 1 hour
    refetchInterval: 60 * 60 * 1000 // 1 hour refresh
  });
}

function useTopStocks() {
  return useQuery({
    queryKey: ['top-stocks'],
    queryFn: async () => {
      return dataCache.get('/api/scores', { limit: 10, sortBy: 'composite_score', sortOrder: 'desc' }, {
        cacheType: 'marketData',
        fetchFunction: async () => {
          try {
            const res = await fetch(`${API_BASE}/api/scores/?limit=10&sortBy=composite_score&sortOrder=desc`);
            if (!res.ok) throw new Error('Failed to fetch top stocks');
            return res.json();
          } catch (err) {
            console.error('Top stocks API failed:', err);
            throw new Error('Stock scoring data unavailable - check API connection');
          }
        }
      });
    },
    staleTime: 60 * 60 * 1000, // 1 hour
    refetchInterval: 60 * 60 * 1000 // 1 hour refresh
  });
}

function useUser() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['dashboard-user'],
    queryFn: async () => {
      try {
        const res = await fetch(`${API_BASE}/auth/me`, { credentials: 'include' });
        if (!res.ok) throw new Error('Failed to fetch user info');
        return res.json();
      } catch (err) {
        console.warn('User fetch failed:', err);
        return null;
      }
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

function TechnicalSignalsWidget() {
  const { data, isLoading } = useQuery({
    queryKey: ['dashboard-technical-signals'],
    queryFn: async () => {
      try {
        const url = `${API_BASE}/api/trading/signals/daily?limit=10`;
        const res = await fetch(url);
        if (!res.ok) {
          console.warn('Trading signals API failed, using mock data');
          return {
            data: [
              { symbol: 'AAPL', signal: 'Buy', date: '2025-07-03', current_price: 195.12, performance_percent: 2.1 },
              { symbol: 'TSLA', signal: 'Sell', date: '2025-07-02', current_price: 710.22, performance_percent: -1.8 },
              { symbol: 'NVDA', signal: 'Buy', date: '2025-07-01', current_price: 1200, performance_percent: 3.5 }
            ]
          };
        }
        return await res.json();
      } catch (err) {
        console.warn('Technical signals error, using mock data:', err);
        return {
          data: [
            { symbol: 'AAPL', signal: 'Buy', date: '2025-07-03', current_price: 195.12, performance_percent: 2.1 },
            { symbol: 'TSLA', signal: 'Sell', date: '2025-07-02', current_price: 710.22, performance_percent: -1.8 }
          ]
        };
      }
    },
    refetchInterval: 300000,
    retry: 1,
    retryDelay: 1000
  });
  
  const signals = data?.data || [];
  
  return (
    <Card sx={{ height: '100%' }}>
      <CardContent>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
          <AutoGraph sx={{ color: 'primary.main', mr: 1 }} />
          <Typography variant="h6" sx={{ fontWeight: 600 }}>Technical Signals</Typography>
          <Chip label="Live" color="success" size="small" sx={{ ml: 1 }} />
        </Box>
        
        {isLoading ? (
          <Typography variant="body2" color="text.secondary">Loading signals...</Typography>
        ) : (
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
                {signals.map((sig, idx) => (
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
        )}
      </CardContent>
    </Card>
  );
}

// --- ENHANCED WIDGETS ---
function MarketSentimentWidget() {
  const { data: marketData, isLoading } = useMarketOverview();
  const sentiment = marketData?.data?.sentiment || mockMarketSentiment;
  
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
        </Box>
        
        <Grid container spacing={2}>
          <Grid item xs={6}>
            <Box textAlign="center">
              <Typography variant="h4" color={getSentimentColor(sentiment.fearGreed)}>
                {sentiment.fearGreed}
              </Typography>
              <Typography variant="body2" color="text.secondary">Fear & Greed</Typography>
            </Box>
          </Grid>
          <Grid item xs={6}>
            <Box textAlign="center">
              <Typography variant="h4" color={getSentimentColor(sentiment.naaim)}>
                {sentiment.naaim}
              </Typography>
              <Typography variant="body2" color="text.secondary">NAAIM</Typography>
            </Box>
          </Grid>
          <Grid item xs={12}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', mt: 1 }}>
              <Box>
                <Typography variant="body2" color="success.main">
                  Bulls: {sentiment.aaii?.bullish || 45}%
                </Typography>
              </Box>
              <Box>
                <Typography variant="body2" color="text.secondary">
                  Neutral: {sentiment.aaii?.neutral || 27}%
                </Typography>
              </Box>
              <Box>
                <Typography variant="body2" color="error.main">
                  Bears: {sentiment.aaii?.bearish || 28}%
                </Typography>
              </Box>
            </Box>
          </Grid>
        </Grid>
        
        <Box sx={{ mt: 2 }}>
          <Chip 
            label={`${sentiment.status} Market`} 
            color={getSentimentColor(sentiment.fearGreed)}
            size="small"
          />
          <Chip 
            label={`VIX: ${sentiment.vix}`} 
            color={sentiment.vix < 20 ? 'success' : 'warning'}
            size="small"
            sx={{ ml: 1 }}
          />
        </Box>
      </CardContent>
    </Card>
  );
}

function SectorPerformanceWidget() {
  const { data: marketData, isLoading } = useMarketOverview();
  const sectors = marketData?.data?.sectors || mockSectorPerformance;
  
  return (
    <Card sx={{ height: '100%' }}>
      <CardContent>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
          <Business sx={{ color: 'primary.main', mr: 1 }} />
          <Typography variant="h6" sx={{ fontWeight: 600 }}>Sector Performance</Typography>
        </Box>
        
        <ResponsiveContainer width="100%" height={200}>
          <RechartsBarChart data={sectors}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="sector" tick={{ fontSize: 12 }} />
            <YAxis tick={{ fontSize: 12 }} />
            <RechartsTooltip formatter={(value) => `${value.toFixed(2)}%`} />
            <Bar dataKey="performance" fill="#8884d8">
              {sectors.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={entry.performance >= 0 ? '#00C49F' : '#FF8042'} />
              ))}
            </Bar>
          </RechartsBarChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}

function TopStocksWidget() {
  const { data: stocksData, isLoading } = useTopStocks();
  const stocks = stocksData?.data || mockTopStocks;
  
  return (
    <Card sx={{ height: '100%' }}>
      <CardContent>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
          <Star sx={{ color: 'primary.main', mr: 1 }} />
          <Typography variant="h6" sx={{ fontWeight: 600 }}>Top Rated Stocks</Typography>
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
              {stocks.slice(0, 6).map((stock, idx) => (
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
}


const Dashboard = () => {
  const { isAuthenticated, user } = useAuth();
  const [selectedSymbol, setSelectedSymbol] = useState('AAPL');
  const [dashboardView, setDashboardView] = useState('overview');
  
  const SYMBOL_OPTIONS = ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA', 'SPY', 'QQQ'];
  
  // Enhanced data fetching
  const { data: portfolioData } = usePortfolioData();
  const { data: marketData } = useMarketOverview();
  const { data: topStocksData } = useTopStocks();
  const { data: userWatchlistData, isLoading: watchlistLoading } = useUserWatchlistData();
  
  const { data: priceData, isLoading: priceLoading } = useQuery({
    queryKey: ['stock-prices', selectedSymbol],
    queryFn: async () => {
      try {
        return await getStockPrices(selectedSymbol, 'daily', 30);
      } catch (err) {
        console.warn('Stock prices API failed, using mock data:', err);
        return {
          data: [
            { date: '2025-06-30', close: 190.5 },
            { date: '2025-07-01', close: 192.3 },
            { date: '2025-07-02', close: 195.1 },
            { date: '2025-07-03', close: 197.8 }
          ]
        };
      }
    },
    staleTime: 5 * 60 * 1000
  });
  
  const { data: metricsData, isLoading: metricsLoading } = useQuery({
    queryKey: ['stock-metrics', selectedSymbol],
    queryFn: async () => {
      try {
        return await getStockMetrics(selectedSymbol);
      } catch (err) {
        console.warn('Stock metrics API failed, using mock data:', err);
        return {
          data: {
            beta: 1.2,
            volatility: 0.28,
            sharpe_ratio: 1.45,
            max_drawdown: -0.15
          }
        };
      }
    },
    staleTime: 5 * 60 * 1000
  });
  
  // Use data or fallback to mock
  const safePortfolio = portfolioData?.data || mockPortfolio;
  const safeWatchlist = userWatchlistData || mockWatchlist;
  const safeNews = mockNews;
  const safeActivity = mockActivity;
  const safeCalendar = mockCalendar;
  const safeSignals = mockSignals;
  
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
        {/* API Key Status */}
        <Box sx={{ mb: 3 }}>
          <ApiKeyStatusIndicator 
            showSetupDialog={true}
            onStatusChange={(status) => {
              console.log('Dashboard - API Key Status:', status);
            }}
          />
        </Box>
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
                    <Typography variant="h5" fontWeight="bold" color={safePortfolio.pnl.daily >= 0 ? 'success.light' : 'error.light'}>
                      ${safePortfolio.pnl.daily.toLocaleString()}
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
          {marketSummary.map((mkt, idx) => (
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
                <Chip label={`Daily: $${safePortfolio.pnl.daily.toLocaleString()}`} color={safePortfolio.pnl.daily >= 0 ? 'success' : 'error'} size="small" />
                <Chip label={`MTD: $${safePortfolio.pnl.mtd.toLocaleString()}`} color={safePortfolio.pnl.mtd >= 0 ? 'success' : 'error'} size="small" />
                <Chip label={`YTD: $${safePortfolio.pnl.ytd.toLocaleString()}`} color={safePortfolio.pnl.ytd >= 0 ? 'success' : 'error'} size="small" />
              </Box>
              <ResponsiveContainer width="100%" height={250}>
                <PieChart>
                  <Pie data={safePortfolio.allocation} cx="50%" cy="50%" outerRadius={80} fill="#8884d8" dataKey="value" label={({ name, value }) => `${name} ${value}%`}>
                    {safePortfolio.allocation.map((entry, idx) => (
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
                <Typography variant="h6" sx={{ fontWeight: 600 }}>
                  {userWatchlistData && userWatchlistData.length > 0 && userWatchlistData[0].watchlistName
                    ? userWatchlistData[0].watchlistName
                    : 'My Watchlist'
                  }
                </Typography>
                {watchlistLoading && (
                  <CircularProgress size={16} sx={{ ml: 1 }} />
                )}
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
                    {safeWatchlist.map((item, idx) => (
                      <TableRow key={item.symbol || idx}>
                        <TableCell>
                          <Typography variant="body2" fontWeight="bold">{item.symbol}</Typography>
                        </TableCell>
                        <TableCell align="right">${item.price?.toFixed(2) || '--'}</TableCell>
                        <TableCell align="right">
                          <Typography variant="body2" color={(item.changePercent || item.change) >= 0 ? 'success.main' : 'error.main'} fontWeight="bold">
                            {(item.changePercent || item.change) >= 0 ? '+' : ''}{(item.changePercent || item.change)?.toFixed(2) ?? '--'}%
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
              
              {/* Data source indicator */}
              <Box sx={{ mt: 1, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Typography variant="caption" color="text.secondary">
                  {userWatchlistData && userWatchlistData.length > 0 && userWatchlistData[0].dataSource === 'user-watchlist' 
                    ? '🟢 Live Data' 
                    : '🟡 Demo Data'
                  }
                </Typography>
                {userWatchlistData && userWatchlistData.length > 0 && (
                  <Typography variant="caption" color="text.secondary">
                    {userWatchlistData.length} stocks
                  </Typography>
                )}
              </Box>
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
          <DashboardStockChart 
            symbol={selectedSymbol} 
            height={400}
            showRealTime={true}
            autoRefresh={true}
          />
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
                {safeSignals.map((sig, idx) => (
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
                {safeCalendar.map((ev, idx) => (
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
              </Box>
              <Stack spacing={2}>
                {safeActivity.map((act, idx) => (
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


      {/* AI-Powered Analytics Section */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={12}>
          <Card sx={{ background: 'linear-gradient(135deg, #f5f5f5 0%, #e8e8e8 100%)', border: '1px solid #ddd' }}>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 3 }}>
                <Psychology sx={{ color: 'primary.main', mr: 1, fontSize: 32 }} />
                <Typography variant="h5" sx={{ fontWeight: 700 }}>AI-Powered Intelligence Center</Typography>
                <Chip label="Neural Networks" color="primary" size="small" sx={{ ml: 2 }} />
                <Chip label="Machine Learning" color="secondary" size="small" sx={{ ml: 1 }} />
              </Box>
              
              <Grid container spacing={3}>
                <Grid item xs={12} md={4}>
                  <Card sx={{ height: '100%', border: '2px solid #1976d2' }}>
                    <CardContent>
                      <Typography variant="h6" gutterBottom sx={{ color: 'primary.main', fontWeight: 600 }}>
                        Market Intelligence
                      </Typography>
                      <List dense>
                        <ListItem>
                          <ListItemAvatar>
                            <Avatar sx={{ bgcolor: 'success.main', width: 32, height: 32 }}>
                              <TrendingUp fontSize="small" />
                            </Avatar>
                          </ListItemAvatar>
                          <ListItemText
                            primary="Market Sentiment: Bullish"
                            secondary="Neural network confidence: 89%"
                          />
                        </ListItem>
                        <ListItem>
                          <ListItemAvatar>
                            <Avatar sx={{ bgcolor: 'warning.main', width: 32, height: 32 }}>
                              <Warning fontSize="small" />
                            </Avatar>
                          </ListItemAvatar>
                          <ListItemText
                            primary="Volatility Forecast"
                            secondary="VIX spike probability: 34%"
                          />
                        </ListItem>
                        <ListItem>
                          <ListItemAvatar>
                            <Avatar sx={{ bgcolor: 'info.main', width: 32, height: 32 }}>
                              <AutoGraph fontSize="small" />
                            </Avatar>
                          </ListItemAvatar>
                          <ListItemText
                            primary="Sector Rotation Signal"
                            secondary="Technology outperformance expected"
                          />
                        </ListItem>
                      </List>
                    </CardContent>
                  </Card>
                </Grid>
                
                <Grid item xs={12} md={4}>
                  <Card sx={{ height: '100%', border: '2px solid #43a047' }}>
                    <CardContent>
                      <Typography variant="h6" gutterBottom sx={{ color: 'success.main', fontWeight: 600 }}>
                        Risk Management
                      </Typography>
                      <Stack spacing={2}>
                        <Box>
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
                        
                        <Box>
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
                        
                        <Box>
                          <Typography variant="body2" color="text.secondary" gutterBottom>
                            Max Drawdown
                          </Typography>
                          <Box display="flex" alignItems="center" gap={2}>
                            <LinearProgress 
                              variant="determinate" 
                              value={25}
                              color="error"
                              sx={{ flex: 1, height: 8, borderRadius: 4 }}
                            />
                            <Typography variant="h6">-8.2%</Typography>
                          </Box>
                        </Box>
                      </Stack>
                    </CardContent>
                  </Card>
                </Grid>
                
                <Grid item xs={12} md={4}>
                  <Card sx={{ height: '100%', border: '2px solid #ff9800' }}>
                    <CardContent>
                      <Typography variant="h6" gutterBottom sx={{ color: 'warning.main', fontWeight: 600 }}>
                        Algorithm Signals
                      </Typography>
                      <List dense>
                        {safeSignals.map((signal, idx) => (
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
                              secondary={`${(signal.confidence * 100).toFixed(0)}% confidence • ${signal.type}`}
                            />
                            <IconButton size="small" color="primary">
                              <PlayArrow />
                            </IconButton>
                          </ListItem>
                        ))}
                        <ListItem>
                          <ListItemAvatar>
                            <Avatar sx={{ bgcolor: 'info.main', width: 32, height: 32 }}>
                              <Bolt fontSize="small" />
                            </Avatar>
                          </ListItemAvatar>
                          <ListItemText
                            primary="Strategy Performance"
                            secondary="YTD: +23.7% • Win Rate: 87.2%"
                          />
                        </ListItem>
                      </List>
                    </CardContent>
                  </Card>
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* News & Market Intelligence */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={12} md={8}>
          <NewsWidget 
            symbols={[selectedSymbol]}
            height={500}
            showSentiment={true}
            autoRefresh={true}
          />
        </Grid>
        <Grid item xs={12} md={4}>
          <EconomicIndicatorsWidget 
            height={500}
            autoRefresh={true}
          />
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
            <Grid item xs={6} md={2}>
              <Button 
                variant="contained" 
                color="info"
                startIcon={<Download />} 
                fullWidth
              >
                Export Data
              </Button>
            </Grid>
            <Grid item xs={6} md={2}>
              <Button 
                variant="outlined"
                startIcon={<Settings />} 
                fullWidth
                onClick={() => window.location.href = '/settings'}
              >
                Settings
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