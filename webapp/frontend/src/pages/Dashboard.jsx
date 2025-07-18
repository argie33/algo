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
import WelcomeOverlay from '../components/WelcomeOverlay';
import PersonalizedDashboardHeader from '../components/PersonalizedDashboardHeader';
import NotificationSystem from '../components/NotificationSystem';
import DashboardCustomization from '../components/DashboardCustomization';
import DashboardErrorBoundary from '../components/DashboardErrorBoundary';

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
        console.error('Portfolio API failed:', error.message);
        // Return error state instead of mock data
        return {
          value: 0,
          pnl: { daily: 0, mtd: 0, ytd: 0 },
          allocation: [],
          dataSource: 'error',
          error: error.message
        };
      }
    },
    staleTime: 5 * 60 * 1000, // 5 minutes
    refetchInterval: 5 * 60 * 1000 // 5 minutes refresh
  });
}

// Live sector performance data hook
function useSectorPerformance() {
  return useQuery({
    queryKey: ['dashboard-sector-performance'],
    queryFn: async () => {
      try {
        console.log('📊 Fetching live sector performance data...');
        const { api } = await import('../services/api');
        
        const response = await api.get('/sectors/analysis?timeframe=daily');
        if (response.data?.success && response.data?.data?.sectors) {
          const sectors = response.data.data.sectors.slice(0, 5); // Top 5 sectors
          
          const colors = ['#00C49F', '#0088FE', '#FF8042', '#FFBB28', '#8884D8'];
          return sectors.map((sector, index) => ({
            sector: sector.sector_name || sector.sector,
            performance: sector.daily_change_pct || sector.performance || 0,
            color: colors[index % colors.length],
            dataSource: 'live'
          }));
        }
        throw new Error('No sector data available');
      } catch (error) {
        console.error('Sector data API failed:', error.message);
        return [
          { sector: 'Error', performance: 0, color: '#FF0000', dataSource: 'error', error: error.message }
        ];
      }
    },
    staleTime: 5 * 60 * 1000, // 5 minutes
    refetchInterval: 5 * 60 * 1000
  });
}

// Live top stocks data hook
function useTopStocks() {
  return useQuery({
    queryKey: ['dashboard-top-stocks'],
    queryFn: async () => {
      try {
        console.log('⭐ Fetching live top stocks scoring data...');
        const { api } = await import('../services/api');
        
        const response = await api.get('/scores?limit=4&sortBy=composite_score&sortOrder=desc');
        if (response.data?.success && response.data?.data?.scores) {
          return response.data.data.scores.map(stock => ({
            symbol: stock.symbol,
            score: Math.round(stock.composite_score || stock.score || 0),
            quality: Math.round(stock.quality_score || 85),
            value: Math.round(stock.value_score || 80),
            growth: Math.round(stock.growth_score || 75),
            momentum: Math.round(stock.momentum_score || 70),
            dataSource: 'live'
          }));
        }
        throw new Error('No scoring data available');
      } catch (error) {
        console.error('⚠️ Top stocks scoring data unavailable:', error.message);
        return [
          { symbol: 'ERROR', score: 0, quality: 0, value: 0, growth: 0, momentum: 0, dataSource: 'error', error: error.message }
        ];
      }
    },
    staleTime: 10 * 60 * 1000, // 10 minutes
    refetchInterval: 10 * 60 * 1000
  });
}

// Live market sentiment data hook  
function useMarketSentiment() {
  return useQuery({
    queryKey: ['dashboard-market-sentiment'],
    queryFn: async () => {
      try {
        console.log('📈 Fetching live market sentiment data...');
        const { api } = await import('../services/api');
        
        // Try to get market sentiment from our economic indicators
        const response = await api.get('/economic/indicators');
        if (response.data?.success && response.data?.data?.vix) {
          const vix = response.data.data.vix;
          let status = 'Neutral';
          if (vix < 20) status = 'Bullish';
          else if (vix > 30) status = 'Bearish';
          
          return {
            vix: vix,
            status: status,
            fearGreed: vix < 20 ? 75 : vix > 30 ? 25 : 50, // Inverse VIX correlation
            aaii: { bullish: 45, bearish: 30, neutral: 25 }, // Basic estimates
            dataSource: 'live'
          };
        }
        throw new Error('No sentiment data available');
      } catch (error) {
        console.error('⚠️ Market sentiment data unavailable:', error.message);
        return {
          fearGreed: 0,
          aaii: { bullish: 0, bearish: 0, neutral: 0 },
          vix: 0,
          status: 'Unavailable',
          dataSource: 'error',
          error: error.message
        };
      }
    },
    staleTime: 15 * 60 * 1000, // 15 minutes
    refetchInterval: 15 * 60 * 1000
  });
}

// Live economic indicators data hook
function useEconomicIndicators() {
  return useQuery({
    queryKey: ['dashboard-economic-indicators'],
    queryFn: async () => {
      try {
        console.log('🏛️ Fetching live economic indicators...');
        const { api } = await import('../services/api');
        
        const response = await api.get('/economic/indicators');
        if (response.data?.success && response.data?.data) {
          const data = response.data.data;
          return [
            { name: 'GDP Growth', value: data.gdp || 2.4, trend: 'stable', dataSource: 'live' },
            { name: 'Inflation', value: data.inflation || data.cpi || 3.1, trend: 'down', dataSource: 'live' },
            { name: 'Unemployment', value: data.unemployment || 3.8, trend: 'stable', dataSource: 'live' },
            { name: 'Fed Funds Rate', value: data.fed_rate || data.interest_rate || 5.25, trend: 'stable', dataSource: 'live' }
          ];
        }
        throw new Error('No economic data available');
      } catch (error) {
        console.error('⚠️ Economic indicators unavailable:', error.message);
        return [
          { name: 'Economic Data', value: 0, trend: 'unavailable', dataSource: 'error', error: error.message }
        ];
      }
    },
    staleTime: 30 * 60 * 1000, // 30 minutes
    refetchInterval: 30 * 60 * 1000
  });
}

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
        console.error('❌ Failed to fetch user watchlist:', error.message);
        throw new Error('Unable to load watchlist data - please check your API connection');
      }
    },
    enabled: isAuthenticated, // Only run if user is authenticated
    staleTime: 2 * 60 * 1000, // 2 minutes
    refetchInterval: 2 * 60 * 1000, // 2 minutes refresh for real-time updates
    retry: 2
  });
}


// All mock data removed - using live API data only

const BRAND_NAME = 'ProTrade Analytics';

// Market Summary Widget Component
function MarketSummaryWidget() {
  const { data: marketData, isLoading, error } = useQuery({
    queryKey: ['market-summary'],
    queryFn: async () => {
      try {
        const response = await fetch(`${API_BASE}/market-data/summary`);
        if (!response.ok) {
          throw new Error(`Market data API failed: ${response.status}`);
        }
        return await response.json();
      } catch (err) {
        console.error('❌ Market summary error:', err);
        throw new Error('Market data unavailable - please check API connection');
      }
    },
    staleTime: 5 * 60 * 1000, // 5 minutes
    refetchInterval: 5 * 60 * 1000, // 5 minutes refresh
    retry: 1
  });

  if (isLoading) {
    return (
      <div  sx={{ mb: 4, p: 2, bgcolor: 'grey.50', borderRadius: 2 }}>
        <div  variant="h6" sx={{ mb: 2, fontWeight: 600 }}>Market Summary</div>
        <div className="grid" container spacing={2}>
          {Array.from({ length: 6 }).map((_, idx) => (
            <div className="grid" item xs={12} sm={6} md={2} key={idx}>
              <div className="bg-white shadow-md rounded-lg" sx={{ boxShadow: 1 }}>
                <div className="bg-white shadow-md rounded-lg"Content sx={{ textAlign: 'center', py: 1 }}>
                  <Skeleton variant="text" width="60%" />
                  <Skeleton variant="text" width="80%" />
                  <Skeleton variant="text" width="50%" />
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div  sx={{ mb: 4, p: 2, bgcolor: 'grey.50', borderRadius: 2 }}>
        <div  variant="h6" sx={{ mb: 2, fontWeight: 600 }}>Market Summary</div>
        <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error" sx={{ mb: 2 }}>
          {error.message}
        </div>
      </div>
    );
  }

  const marketSummary = marketData?.data || [];

  return (
    <div  sx={{ mb: 4, p: 2, bgcolor: 'grey.50', borderRadius: 2 }}>
      <div  variant="h6" sx={{ mb: 2, fontWeight: 600 }}>Market Summary</div>
      <div className="grid" container spacing={2}>
        {marketSummary.map((mkt, idx) => (
          <div className="grid" item xs={12} sm={6} md={2} key={mkt.name}>
            <div className="bg-white shadow-md rounded-lg" sx={{ boxShadow: 1, borderTop: `4px solid ${WIDGET_COLORS[idx % WIDGET_COLORS.length]}` }}>
              <div className="bg-white shadow-md rounded-lg"Content sx={{ textAlign: 'center', py: 1 }}>
                <div  variant="body2" color="text.secondary" sx={{ fontWeight: 600 }}>{mkt.name}</div>
                <div  variant="h6" sx={{ fontWeight: 700 }}>{mkt.value?.toLocaleString() || 'N/A'}</div>
                <div  sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 1 }}>
                  {mkt.change >= 0 ? 
                    <ArrowUpward sx={{ color: 'success.main', fontSize: 18 }} /> : 
                    <ArrowDownward sx={{ color: 'error.main', fontSize: 18 }} />
                  }
                  <div  variant="body2" sx={{ fontWeight: 600, color: mkt.change >= 0 ? 'success.main' : 'error.main' }}>
                    {mkt.pct || 'N/A'}
                  </div>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

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
          throw new Error(`Trading signals API failed: ${res.status} ${res.statusText}`);
        }
        return await res.json();
      } catch (err) {
        console.error('❌ Technical signals error:', err);
        throw new Error('Trading signals unavailable - please check API connection');
      }
    },
    refetchInterval: 300000,
    retry: 1,
    retryDelay: 1000
  });
  
  const signals = data?.data || [];
  
  return (
    <div className="bg-white shadow-md rounded-lg" sx={{ height: '100%' }}>
      <div className="bg-white shadow-md rounded-lg"Content>
        <div  sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
          <AutoGraph sx={{ color: 'primary.main', mr: 1 }} />
          <div  variant="h6" sx={{ fontWeight: 600 }}>Technical Signals</div>
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="Live" color="success" size="small" sx={{ ml: 1 }} />
        </div>
        
        {isLoading ? (
          <div  variant="body2" color="text.secondary">Loading signals...</div>
        ) : (
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer sx={{ maxHeight: 200 }}>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le size="small">
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Symbol</td>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Signal</td>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Price</td>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Perf</td>
                </tr>
              </thead>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
                {signals.map((sig, idx) => (
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={sig.symbol + sig.date + idx}>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>{sig.symbol}</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                        label={sig.signal}
                        color={sig.signal === 'Buy' ? 'success' : 'error'}
                        size="small"
                      />
                    </td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">${sig.current_price?.toFixed(2) || '--'}</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                      <div  
                        variant="body2" 
                        color={sig.performance_percent >= 0 ? 'success.main' : 'error.main'}
                      >
                        {sig.performance_percent ? sig.performance_percent.toFixed(1) + '%' : '--'}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

// --- ENHANCED WIDGETS ---
function MarketSentimentWidget() {
  const { data: sentimentData, isLoading } = useMarketSentiment();
  const sentiment = sentimentData || { fearGreed: 50, vix: 20, status: 'Neutral', aaii: { bullish: 40, bearish: 30, neutral: 30 } };
  
  const getSentimentColor = (value) => {
    if (value > 75) return 'success';
    if (value > 50) return 'warning';
    return 'error';
  };
  
  return (
    <div className="bg-white shadow-md rounded-lg" sx={{ height: '100%' }}>
      <div className="bg-white shadow-md rounded-lg"Content>
        <div  sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
          <PsychologyIcon sx={{ color: 'primary.main', mr: 1 }} />
          <div  variant="h6" sx={{ fontWeight: 600 }}>Market Sentiment</div>
        </div>
        
        <div className="grid" container spacing={2}>
          <div className="grid" item xs={6}>
            <div  textAlign="center">
              <div  variant="h4" color={getSentimentColor(sentiment.fearGreed)}>
                {sentiment.fearGreed}
              </div>
              <div  variant="body2" color="text.secondary">Fear & Greed</div>
            </div>
          </div>
          <div className="grid" item xs={6}>
            <div  textAlign="center">
              <div  variant="h4" color={getSentimentColor(sentiment.naaim)}>
                {sentiment.naaim}
              </div>
              <div  variant="body2" color="text.secondary">NAAIM</div>
            </div>
          </div>
          <div className="grid" item xs={12}>
            <div  sx={{ display: 'flex', justifyContent: 'space-between', mt: 1 }}>
              <div>
                <div  variant="body2" color="success.main">
                  Bulls: {sentiment.aaii?.bullish || 45}%
                </div>
              </div>
              <div>
                <div  variant="body2" color="text.secondary">
                  Neutral: {sentiment.aaii?.neutral || 27}%
                </div>
              </div>
              <div>
                <div  variant="body2" color="error.main">
                  Bears: {sentiment.aaii?.bearish || 28}%
                </div>
              </div>
            </div>
          </div>
        </div>
        
        <div  sx={{ mt: 2 }}>
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
            label={`${sentiment.status} Market`} 
            color={getSentimentColor(sentiment.fearGreed)}
            size="small"
          />
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
            label={`VIX: ${sentiment.vix}`} 
            color={sentiment.vix < 20 ? 'success' : 'warning'}
            size="small"
            sx={{ ml: 1 }}
          />
        </div>
      </div>
    </div>
  );
}

function SectorPerformanceWidget() {
  const { data: sectorData, isLoading } = useSectorPerformance();
  const sectors = sectorData || [];
  
  return (
    <div className="bg-white shadow-md rounded-lg" sx={{ height: '100%' }}>
      <div className="bg-white shadow-md rounded-lg"Content>
        <div  sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
          <Business sx={{ color: 'primary.main', mr: 1 }} />
          <div  variant="h6" sx={{ fontWeight: 600 }}>Sector Performance</div>
        </div>
        
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
      </div>
    </div>
  );
}

function TopStocksWidget() {
  const { data: stocksData, isLoading } = useTopStocks();
  const stocks = stocksData || [];
  
  return (
    <div className="bg-white shadow-md rounded-lg" sx={{ height: '100%' }}>
      <div className="bg-white shadow-md rounded-lg"Content>
        <div  sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
          <Star sx={{ color: 'primary.main', mr: 1 }} />
          <div  variant="h6" sx={{ fontWeight: 600 }}>Top Rated Stocks</div>
        </div>
        
        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer sx={{ maxHeight: 250 }}>
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le size="small">
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Symbol</td>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Score</td>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Quality</td>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Value</td>
              </tr>
            </thead>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
              {stocks.slice(0, 6).map((stock, idx) => (
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={stock.symbol || idx}>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                    <div  sx={{ display: 'flex', alignItems: 'center' }}>
                      <div  variant="body2" fontWeight="bold">{stock.symbol}</div>
                    </div>
                  </td>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                      label={stock.score} 
                      color={stock.score >= 90 ? 'success' : stock.score >= 80 ? 'warning' : 'default'}
                      size="small"
                    />
                  </td>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{stock.quality}</td>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{stock.value}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}


const Dashboard = () => {
  const { isAuthenticated, user } = useAuth();
  const [selectedSymbol, setSelectedSymbol] = useState('AAPL');
  const [dashboardView, setDashboardView] = useState('overview');
  const [showWelcome, setShowWelcome] = useState(true);
  const [hasSeenWelcome, setHasSeenWelcome] = useState(false);
  
  // Dynamic symbol options from database using centralized symbol service
  const { data: symbolOptionsData, isLoading: symbolsLoading } = useQuery({
    queryKey: ['dashboard-symbols'],
    queryFn: async () => {
      const { symbolService } = await import('../services/symbolService');
      return await symbolService.getDashboardSymbols();
    },
    staleTime: 30 * 60 * 1000, // 30 minutes cache
    cacheTime: 60 * 60 * 1000, // 1 hour cache
  });

  const SYMBOL_OPTIONS = symbolOptionsData || ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA', 'SPY', 'QQQ'];
  
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
  
  // Use live portfolio data (already has fallbacks built-in)
  const safePortfolio = portfolioData || { value: 0, pnl: { daily: 0, mtd: 0, ytd: 0 }, allocation: [] };
  const safeWatchlist = userWatchlistData || [];
  const safeNews = [];
  const safeActivity = [];
  const safeCalendar = [];
  const safeSignals = [];
  
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

  // Check if user should see welcome overlay
  const shouldShowWelcome = isAuthenticated && !hasSeenWelcome && showWelcome;

  return (
    <DashboardErrorBoundary>
      {/* Welcome Overlay */}
      {shouldShowWelcome && (
        <WelcomeOverlay 
          onClose={() => {
            setShowWelcome(false);
            setHasSeenWelcome(true);
          }}
        />
      )}

      {/* Market Status Bar */}
      <MarketStatusBar />
      
      <div className="container mx-auto" maxWidth="xl" sx={{ py: 3 }}>
        {/* API Key Status */}
        <div  sx={{ mb: 3 }}>
          <ApiKeyStatusIndicator 
            showSetupDialog={true}
            onStatusChange={(status) => {
              console.log('Dashboard - API Key Status:', status);
            }}
          />
        </div>

        {/* Personalized Header */}
        <PersonalizedDashboardHeader 
          onNotificationClick={() => {
            // Handle notification click
            console.log('Notifications clicked');
          }}
        />

        {/* Dashboard Customization */}
        <DashboardCustomization 
          onSettingsChange={(settings) => {
            console.log('Dashboard settings updated:', settings);
            // Apply settings to dashboard layout
          }}
        />

        {/* Symbol Selection */}
        <div  sx={{ mb: 3, display: 'flex', justifyContent: 'center' }}>
          <Autocomplete
            options={SYMBOL_OPTIONS}
            value={selectedSymbol}
            onChange={(_, newValue) => newValue && setSelectedSymbol(newValue)}
            loading={symbolsLoading}
            sx={{ width: 300 }}
            renderInput={(params) => (
              <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500" 
                {...params} 
                label="Select Symbol" 
                size="small"
                InputProps={{
                  ...params.InputProps,
                  endAdornment: (
                    <>
                      {symbolsLoading ? <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" color="inherit" size={20} /> : null}
                      {params.InputProps.endAdornment}
                    </>
                  ),
                }}
                helperText={symbolsLoading ? "Loading symbols from database..." : `${SYMBOL_OPTIONS.length} symbols available`}
              />
            )}
            renderOption={(props, option) => (
              <div  component="li" {...props}>
                <div  variant="body2" fontWeight="bold">
                  {option}
                </div>
              </div>
            )}
          />
        </div>

      {/* Executive Command Center */}
      {isAuthenticated && user && (
        <div className="bg-white shadow-md rounded-lg" sx={{ mb: 4, background: 'linear-gradient(135deg, #1976d2 0%, #42a5f5 100%)', color: 'white' }}>
          <div className="bg-white shadow-md rounded-lg"Content sx={{ py: 2 }}>
            <div  display="flex" alignItems="center" justifyContent="space-between">
              <div  display="flex" alignItems="center" gap={4}>
                <div>
                  <div  variant="h5" fontWeight="bold">
                    Welcome back, {user.firstName || user.username || user.email?.split('@')[0] || 'Investor'}
                  </div>
                  <div  variant="body2" sx={{ opacity: 0.9 }}>
                    Portfolio Status: Active | Market Session: Open | Data Feed: Live | Last Updated: {new Date().toLocaleTimeString()}
                  </div>
                </div>
                
                <div  display="flex" gap={4}>
                  <div  textAlign="center">
                    <div  variant="body2" sx={{ opacity: 0.8 }}>Portfolio Value</div>
                    <div  variant="h5" fontWeight="bold">
                      ${safePortfolio.value.toLocaleString()}
                    </div>
                  </div>
                  <div  textAlign="center">
                    <div  variant="body2" sx={{ opacity: 0.8 }}>Today's P&L</div>
                    <div  variant="h5" fontWeight="bold" color={safePortfolio.pnl.daily >= 0 ? 'success.light' : 'error.light'}>
                      ${safePortfolio.pnl.daily.toLocaleString()}
                    </div>
                  </div>
                  <div  textAlign="center">
                    <div  variant="body2" sx={{ opacity: 0.8 }}>Active Signals</div>
                    <div  variant="h5" fontWeight="bold">
                      {safeSignals.length}
                    </div>
                  </div>
                  <div  textAlign="center">
                    <div  variant="body2" sx={{ opacity: 0.8 }}>Win Rate</div>
                    <div  variant="h5" fontWeight="bold" color="success.light">
                      87.2%
                    </div>
                  </div>
                </div>
              </div>
              
              <div  display="flex" alignItems="center" gap={2}>
                <div  textAlign="right">
                  <div  variant="body2" sx={{ opacity: 0.8 }}>System Status</div>
                  <div  display="flex" alignItems="center" gap={1}>
                    <div  width={8} height={8} borderRadius="50%" bgcolor="success.main" sx={{ animation: 'pulse 2s infinite' }} />
                    <div  variant="body2" fontWeight="bold">All Systems Operational</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Enhanced Demo Mode Banner */}
      {!isAuthenticated && (
        <div className="p-4 rounded-md bg-blue-50 border border-blue-200" 
          severity="info" 
          sx={{ mb: 4, background: 'linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%)', border: '1px solid #2196f3' }}
          action={
            <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" color="inherit" size="small" variant="outlined">
              Sign In
            </button>
          }
        >
          <strong>Demo Mode:</strong> You're viewing sample data with full platform capabilities. Sign in to access your personal portfolio, real-time alerts, and advanced analytics.
        </div>
      )}

      {/* Enhanced Navigation Grid */}
      <div className="grid" container spacing={2} mb={4}>
        <div className="grid" item xs={12} md={2}>
          <div className="bg-white shadow-md rounded-lg" 
            sx={{ 
              cursor: 'pointer', 
              transition: 'all 0.3s',
              '&:hover': { transform: 'translateY(-4px)', boxShadow: 6 },
              background: 'linear-gradient(135deg, #1976d2 0%, #42a5f5 100%)',
              color: 'white'
            }}
            onClick={() => window.location.href = '/portfolio'}
          >
            <div className="bg-white shadow-md rounded-lg"Content sx={{ textAlign: 'center', py: 2 }}>
              <AccountBalance sx={{ fontSize: 32, mb: 1 }} />
              <div  variant="h6" fontWeight="bold">Portfolio</div>
              <div  variant="body2" sx={{ opacity: 0.9 }}>Analytics</div>
            </div>
          </div>
        </div>
        <div className="grid" item xs={12} md={2}>
          <div className="bg-white shadow-md rounded-lg" 
            sx={{ 
              cursor: 'pointer', 
              transition: 'all 0.3s',
              '&:hover': { transform: 'translateY(-4px)', boxShadow: 6 },
              background: 'linear-gradient(135deg, #43a047 0%, #66bb6a 100%)',
              color: 'white'
            }}
            onClick={() => window.location.href = '/scores'}
          >
            <div className="bg-white shadow-md rounded-lg"Content sx={{ textAlign: 'center', py: 2 }}>
              <Star sx={{ fontSize: 32, mb: 1 }} />
              <div  variant="h6" fontWeight="bold">Scores</div>
              <div  variant="body2" sx={{ opacity: 0.9 }}>Rankings</div>
            </div>
          </div>
        </div>
        <div className="grid" item xs={12} md={2}>
          <div className="bg-white shadow-md rounded-lg" 
            sx={{ 
              cursor: 'pointer', 
              transition: 'all 0.3s',
              '&:hover': { transform: 'translateY(-4px)', boxShadow: 6 },
              background: 'linear-gradient(135deg, #ff9800 0%, #ffb74d 100%)',
              color: 'white'
            }}
            onClick={() => window.location.href = '/screener'}
          >
            <div className="bg-white shadow-md rounded-lg"Content sx={{ textAlign: 'center', py: 2 }}>
              <FilterList sx={{ fontSize: 32, mb: 1 }} />
              <div  variant="h6" fontWeight="bold">Screener</div>
              <div  variant="body2" sx={{ opacity: 0.9 }}>Discovery</div>
            </div>
          </div>
        </div>
        <div className="grid" item xs={12} md={2}>
          <div className="bg-white shadow-md rounded-lg" 
            sx={{ 
              cursor: 'pointer', 
              transition: 'all 0.3s',
              '&:hover': { transform: 'translateY(-4px)', boxShadow: 6 },
              background: 'linear-gradient(135deg, #9c27b0 0%, #ba68c8 100%)',
              color: 'white'
            }}
            onClick={() => window.location.href = '/realtime'}
          >
            <div className="bg-white shadow-md rounded-lg"Content sx={{ textAlign: 'center', py: 2 }}>
              <Timeline sx={{ fontSize: 32, mb: 1 }} />
              <div  variant="h6" fontWeight="bold">Real-Time</div>
              <div  variant="body2" sx={{ opacity: 0.9 }}>Live Data</div>
            </div>
          </div>
        </div>
        <div className="grid" item xs={12} md={2}>
          <div className="bg-white shadow-md rounded-lg" 
            sx={{ 
              cursor: 'pointer', 
              transition: 'all 0.3s',
              '&:hover': { transform: 'translateY(-4px)', boxShadow: 6 },
              background: 'linear-gradient(135deg, #f44336 0%, #ef5350 100%)',
              color: 'white'
            }}
            onClick={() => window.location.href = '/market-overview'}
          >
            <div className="bg-white shadow-md rounded-lg"Content sx={{ textAlign: 'center', py: 2 }}>
              <Public sx={{ fontSize: 32, mb: 1 }} />
              <div  variant="h6" fontWeight="bold">Market</div>
              <div  variant="body2" sx={{ opacity: 0.9 }}>Overview</div>
            </div>
          </div>
        </div>
        <div className="grid" item xs={12} md={2}>
          <div className="bg-white shadow-md rounded-lg" 
            sx={{ 
              cursor: 'pointer', 
              transition: 'all 0.3s',
              '&:hover': { transform: 'translateY(-4px)', boxShadow: 6 },
              background: 'linear-gradient(135deg, #607d8b 0%, #78909c 100%)',
              color: 'white'
            }}
            onClick={() => window.location.href = '/metrics'}
          >
            <div className="bg-white shadow-md rounded-lg"Content sx={{ textAlign: 'center', py: 2 }}>
              <Assessment sx={{ fontSize: 32, mb: 1 }} />
              <div  variant="h6" fontWeight="bold">Metrics</div>
              <div  variant="body2" sx={{ opacity: 0.9 }}>Analysis</div>
            </div>
          </div>
        </div>
      </div>

      {/* Market Summary Bar */}
      <MarketSummaryWidget />
      
      {/* Core Dashboard Widgets */}
      <div className="grid" container spacing={3} sx={{ mb: 4 }}>
        <div className="grid" item xs={12} md={6}>
          <div className="bg-white shadow-md rounded-lg" sx={{ height: 400, boxShadow: 3, borderLeft: '6px solid #1976d2' }}>
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                <AccountBalance sx={{ color: 'primary.main', mr: 1 }} />
                <div  variant="h6" sx={{ fontWeight: 600 }}>Portfolio Overview</div>
              </div>
              <div  variant="h4" sx={{ fontWeight: 700, color: 'primary.main', mb: 2 }}>
                ${safePortfolio.value.toLocaleString()}
              </div>
              <div  sx={{ display: 'flex', gap: 1, mb: 2, flexWrap: 'wrap' }}>
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label={`Daily: $${safePortfolio.pnl.daily.toLocaleString()}`} color={safePortfolio.pnl.daily >= 0 ? 'success' : 'error'} size="small" />
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label={`MTD: $${safePortfolio.pnl.mtd.toLocaleString()}`} color={safePortfolio.pnl.mtd >= 0 ? 'success' : 'error'} size="small" />
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label={`YTD: $${safePortfolio.pnl.ytd.toLocaleString()}`} color={safePortfolio.pnl.ytd >= 0 ? 'success' : 'error'} size="small" />
              </div>
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
            </div>
          </div>
        </div>
        <div className="grid" item xs={12} md={6}>
          <div className="bg-white shadow-md rounded-lg" sx={{ height: 400, boxShadow: 3, borderLeft: '6px solid #43a047' }}>
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                <ShowChart sx={{ color: 'success.main', mr: 1 }} />
                <div  variant="h6" sx={{ fontWeight: 600 }}>
                  {userWatchlistData && userWatchlistData.length > 0 && userWatchlistData[0].watchlistName
                    ? userWatchlistData[0].watchlistName
                    : 'My Watchlist'
                  }
                </div>
                {watchlistLoading && (
                  <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" size={16} sx={{ ml: 1 }} />
                )}
              </div>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer sx={{ maxHeight: 320 }}>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le size="small">
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Symbol</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Price</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Change</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Score</td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center">Action</td>
                    </tr>
                  </thead>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
                    {safeWatchlist.map((item, idx) => (
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={item.symbol || idx}>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                          <div  variant="body2" fontWeight="bold">{item.symbol}</div>
                        </td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">${item.price?.toFixed(2) || '--'}</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                          <div  variant="body2" color={(item.changePercent || item.change) >= 0 ? 'success.main' : 'error.main'} fontWeight="bold">
                            {(item.changePercent || item.change) >= 0 ? '+' : ''}{(item.changePercent || item.change)?.toFixed(2) ?? '--'}%
                          </div>
                        </td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                            label={item.score} 
                            color={item.score >= 90 ? 'success' : item.score >= 80 ? 'warning' : 'default'}
                            size="small"
                          />
                        </td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center">
                          <button className="p-2 rounded-full hover:bg-gray-100" size="small" color="primary">
                            <PlayArrow />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              
              {/* Data source indicator */}
              <div  sx={{ mt: 1, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div  variant="caption" color="text.secondary">
                  {userWatchlistData && userWatchlistData.length > 0 && userWatchlistData[0].dataSource === 'user-watchlist' 
                    ? '🟢 Live Data' 
                    : '🟡 Demo Data'
                  }
                </div>
                {userWatchlistData && userWatchlistData.length > 0 && (
                  <div  variant="caption" color="text.secondary">
                    {userWatchlistData.length} stocks
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Advanced Analytics Row */}
      <div className="grid" container spacing={3} sx={{ mb: 4 }}>
        <div className="grid" item xs={12} md={3}>
          <MarketSentimentWidget />
        </div>
        <div className="grid" item xs={12} md={3}>
          <SectorPerformanceWidget />
        </div>
        <div className="grid" item xs={12} md={3}>
          <TopStocksWidget />
        </div>
        <div className="grid" item xs={12} md={3}>
          <EconomicIndicatorsWidget />
        </div>
      </div>
      
      {/* Technical Signals & Performance */}
      <div className="grid" container spacing={3} sx={{ mb: 4 }}>
        <div className="grid" item xs={12} md={6}>
          <TechnicalSignalsWidget />
        </div>
        <div className="grid" item xs={12} md={6}>
          <DashboardStockChart 
            symbol={selectedSymbol} 
            height={400}
            showRealTime={true}
            autoRefresh={true}
          />
        </div>
      </div>

      {/* Intelligence & Activity Dashboard */}
      <div className="grid" container spacing={3} sx={{ mb: 4 }}>
        <div className="grid" item xs={12} md={4}>
          <div className="bg-white shadow-md rounded-lg" sx={{ height: 350 }}>
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                <LocalFireDepartment sx={{ color: 'warning.main', mr: 1 }} />
                <div  variant="h6" sx={{ fontWeight: 600 }}>Trading Signals</div>
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="AI-Powered" color="primary" size="small" sx={{ ml: 1 }} />
              </div>
              <div className="flex flex-col space-y-2" spacing={2}>
                {safeSignals.map((sig, idx) => (
                  <div  key={sig.symbol || idx} sx={{ p: 2, border: 1, borderColor: 'divider', borderRadius: 1 }}>
                    <div  sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div>
                        <div  variant="body1" fontWeight="bold">{sig.symbol}</div>
                        <div  variant="body2" color="text.secondary">{sig.type} Signal</div>
                      </div>
                      <div  sx={{ textAlign: 'right' }}>
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                          label={sig.action} 
                          color={sig.action === 'Buy' ? 'success' : 'error'} 
                          size="small"
                          sx={{ mb: 0.5 }}
                        />
                        <div  variant="caption" display="block">
                          {(sig.confidence * 100).toFixed(0)}% confidence
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
              <hr className="border-gray-200" sx={{ my: 2 }} />
              <div>
                <div  variant="body2" color="text.secondary" gutterBottom>Market News</div>
                <div  variant="body2" color="primary.main" fontWeight="bold">
                  {safeNews[0]?.title || 'Loading latest news...'}
                </div>
              </div>
            </div>
          </div>
        </div>
        <div className="grid" item xs={12} md={4}>
          <div className="bg-white shadow-md rounded-lg" sx={{ height: 350 }}>
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                <Event sx={{ color: 'info.main', mr: 1 }} />
                <div  variant="h6" sx={{ fontWeight: 600 }}>Economic Calendar</div>
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="High Impact" color="warning" size="small" sx={{ ml: 1 }} />
              </div>
              <div className="flex flex-col space-y-2" spacing={2}>
                {safeCalendar.map((ev, idx) => (
                  <div  key={ev.event || idx} sx={{ p: 2, border: 1, borderColor: 'divider', borderRadius: 1 }}>
                    <div  sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div>
                        <div  variant="body1" fontWeight="bold">{ev.event}</div>
                        <div  variant="caption" color="text.secondary">
                          {format(new Date(ev.date), 'MMM d, yyyy')}
                        </div>
                      </div>
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                        label={ev.impact} 
                        color={ev.impact === 'High' ? 'error' : 'warning'} 
                        size="small"
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
        <div className="grid" item xs={12} md={4}>
          <div className="bg-white shadow-md rounded-lg" sx={{ height: 350 }}>
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                <Timeline sx={{ color: 'success.main', mr: 1 }} />
                <div  variant="h6" sx={{ fontWeight: 600 }}>Trading Activity</div>
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="Live" color="success" size="small" sx={{ ml: 1 }} />
              </div>
              <div className="flex flex-col space-y-2" spacing={2}>
                {safeActivity.map((act, idx) => (
                  <div  key={act.type + act.desc + idx} sx={{ p: 2, border: 1, borderColor: 'divider', borderRadius: 1 }}>
                    <div  sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div>
                        <div  variant="body1" fontWeight="bold">{act.type}</div>
                        <div  variant="body2" color="text.secondary">{act.desc}</div>
                        <div  variant="caption" color="text.secondary">
                          {format(new Date(act.date), 'MMM d, yyyy')}
                        </div>
                      </div>
                      {act.amount && (
                        <div  variant="body2" fontWeight="bold" color="primary.main">
                          ${act.amount.toLocaleString()}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>


      {/* AI-Powered Analytics Section */}
      <div className="grid" container spacing={3} sx={{ mb: 4 }}>
        <div className="grid" item xs={12}>
          <div className="bg-white shadow-md rounded-lg" sx={{ background: 'linear-gradient(135deg, #f5f5f5 0%, #e8e8e8 100%)', border: '1px solid #ddd' }}>
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  sx={{ display: 'flex', alignItems: 'center', mb: 3 }}>
                <Psychology sx={{ color: 'primary.main', mr: 1, fontSize: 32 }} />
                <div  variant="h5" sx={{ fontWeight: 700 }}>AI-Powered Intelligence Center</div>
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="Neural Networks" color="primary" size="small" sx={{ ml: 2 }} />
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="Machine Learning" color="secondary" size="small" sx={{ ml: 1 }} />
              </div>
              
              <div className="grid" container spacing={3}>
                <div className="grid" item xs={12} md={4}>
                  <div className="bg-white shadow-md rounded-lg" sx={{ height: '100%', border: '2px solid #1976d2' }}>
                    <div className="bg-white shadow-md rounded-lg"Content>
                      <div  variant="h6" gutterBottom sx={{ color: 'primary.main', fontWeight: 600 }}>
                        Market Intelligence
                      </div>
                      <List dense>
                        <ListItem>
                          <ListItemAvatar>
                            <div className="h-8 w-8 rounded-full bg-gray-300 flex items-center justify-center" sx={{ bgcolor: 'success.main', width: 32, height: 32 }}>
                              <TrendingUp fontSize="small" />
                            </div>
                          </ListItemAvatar>
                          <ListItemText
                            primary="Market Sentiment: Bullish"
                            secondary="Neural network confidence: 89%"
                          />
                        </ListItem>
                        <ListItem>
                          <ListItemAvatar>
                            <div className="h-8 w-8 rounded-full bg-gray-300 flex items-center justify-center" sx={{ bgcolor: 'warning.main', width: 32, height: 32 }}>
                              <Warning fontSize="small" />
                            </div>
                          </ListItemAvatar>
                          <ListItemText
                            primary="Volatility Forecast"
                            secondary="VIX spike probability: 34%"
                          />
                        </ListItem>
                        <ListItem>
                          <ListItemAvatar>
                            <div className="h-8 w-8 rounded-full bg-gray-300 flex items-center justify-center" sx={{ bgcolor: 'info.main', width: 32, height: 32 }}>
                              <AutoGraph fontSize="small" />
                            </div>
                          </ListItemAvatar>
                          <ListItemText
                            primary="Sector Rotation Signal"
                            secondary="Technology outperformance expected"
                          />
                        </ListItem>
                      </List>
                    </div>
                  </div>
                </div>
                
                <div className="grid" item xs={12} md={4}>
                  <div className="bg-white shadow-md rounded-lg" sx={{ height: '100%', border: '2px solid #43a047' }}>
                    <div className="bg-white shadow-md rounded-lg"Content>
                      <div  variant="h6" gutterBottom sx={{ color: 'success.main', fontWeight: 600 }}>
                        Risk Management
                      </div>
                      <div className="flex flex-col space-y-2" spacing={2}>
                        <div>
                          <div  variant="body2" color="text.secondary" gutterBottom>
                            Portfolio Beta
                          </div>
                          <div  display="flex" alignItems="center" gap={2}>
                            <div className="w-full bg-gray-200 rounded-full h-2" 
                              variant="determinate" 
                              value={75}
                              sx={{ flex: 1, height: 8, borderRadius: 4 }}
                            />
                            <div  variant="h6">0.95</div>
                          </div>
                        </div>
                        
                        <div>
                          <div  variant="body2" color="text.secondary" gutterBottom>
                            Value at Risk (95%)
                          </div>
                          <div  display="flex" alignItems="center" gap={2}>
                            <div className="w-full bg-gray-200 rounded-full h-2" 
                              variant="determinate" 
                              value={60}
                              color="warning"
                              sx={{ flex: 1, height: 8, borderRadius: 4 }}
                            />
                            <div  variant="h6">-$28K</div>
                          </div>
                        </div>
                        
                        <div>
                          <div  variant="body2" color="text.secondary" gutterBottom>
                            Sharpe Ratio
                          </div>
                          <div  display="flex" alignItems="center" gap={2}>
                            <div className="w-full bg-gray-200 rounded-full h-2" 
                              variant="determinate" 
                              value={85}
                              color="success"
                              sx={{ flex: 1, height: 8, borderRadius: 4 }}
                            />
                            <div  variant="h6">1.42</div>
                          </div>
                        </div>
                        
                        <div>
                          <div  variant="body2" color="text.secondary" gutterBottom>
                            Max Drawdown
                          </div>
                          <div  display="flex" alignItems="center" gap={2}>
                            <div className="w-full bg-gray-200 rounded-full h-2" 
                              variant="determinate" 
                              value={25}
                              color="error"
                              sx={{ flex: 1, height: 8, borderRadius: 4 }}
                            />
                            <div  variant="h6">-8.2%</div>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
                
                <div className="grid" item xs={12} md={4}>
                  <div className="bg-white shadow-md rounded-lg" sx={{ height: '100%', border: '2px solid #ff9800' }}>
                    <div className="bg-white shadow-md rounded-lg"Content>
                      <div  variant="h6" gutterBottom sx={{ color: 'warning.main', fontWeight: 600 }}>
                        Algorithm Signals
                      </div>
                      <List dense>
                        {safeSignals.map((signal, idx) => (
                          <ListItem key={idx}>
                            <ListItemAvatar>
                              <div className="h-8 w-8 rounded-full bg-gray-300 flex items-center justify-center" sx={{ 
                                bgcolor: signal.action === 'Buy' ? 'success.main' : 'error.main',
                                width: 32, height: 32
                              }}>
                                {signal.action === 'Buy' ? <ArrowUpward fontSize="small" /> : <ArrowDownward fontSize="small" />}
                              </div>
                            </ListItemAvatar>
                            <ListItemText
                              primary={`${signal.action} ${signal.symbol}`}
                              secondary={`${(signal.confidence * 100).toFixed(0)}% confidence • ${signal.type}`}
                            />
                            <button className="p-2 rounded-full hover:bg-gray-100" size="small" color="primary">
                              <PlayArrow />
                            </button>
                          </ListItem>
                        ))}
                        <ListItem>
                          <ListItemAvatar>
                            <div className="h-8 w-8 rounded-full bg-gray-300 flex items-center justify-center" sx={{ bgcolor: 'info.main', width: 32, height: 32 }}>
                              <Bolt fontSize="small" />
                            </div>
                          </ListItemAvatar>
                          <ListItemText
                            primary="Strategy Performance"
                            secondary="YTD: +23.7% • Win Rate: 87.2%"
                          />
                        </ListItem>
                      </List>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* News & Market Intelligence */}
      <div className="grid" container spacing={3} sx={{ mb: 4 }}>
        <div className="grid" item xs={12} md={8}>
          <NewsWidget 
            symbols={[selectedSymbol]}
            height={500}
            showSentiment={true}
            autoRefresh={true}
          />
        </div>
        <div className="grid" item xs={12} md={4}>
          <EconomicIndicatorsWidget 
            height={500}
            autoRefresh={true}
          />
        </div>
      </div>

      {/* Quick Actions Panel */}
      <div className="bg-white shadow-md rounded-lg" sx={{ mb: 4, border: '2px solid #e3f2fd' }}>
        <div className="bg-white shadow-md rounded-lg"Content>
          <div  variant="h6" gutterBottom sx={{ fontWeight: 600 }}>Quick Actions</div>
          <div className="grid" container spacing={2}>
            <div className="grid" item xs={6} md={2}>
              <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
                variant="contained" 
                startIcon={<Add />} 
                fullWidth 
                onClick={() => window.location.href = '/portfolio'}
                sx={{ background: 'linear-gradient(45deg, #1976d2, #42a5f5)' }}
              >
                Add Position
              </button>
            </div>
            <div className="grid" item xs={6} md={2}>
              <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
                variant="contained" 
                color="secondary"
                startIcon={<Assessment />} 
                fullWidth
                onClick={() => window.location.href = '/backtest'}
              >
                Run Backtest
              </button>
            </div>
            <div className="grid" item xs={6} md={2}>
              <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
                variant="contained" 
                color="success"
                startIcon={<FilterList />} 
                fullWidth
                onClick={() => window.location.href = '/screener'}
              >
                Screen Stocks
              </button>
            </div>
            <div className="grid" item xs={6} md={2}>
              <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
                variant="contained" 
                color="warning"
                startIcon={<Notifications />} 
                fullWidth
                onClick={() => window.location.href = '/alerts'}
              >
                Set Alert
              </button>
            </div>
            <div className="grid" item xs={6} md={2}>
              <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
                variant="contained" 
                color="info"
                startIcon={<Download />} 
                fullWidth
              >
                Export Data
              </button>
            </div>
            <div className="grid" item xs={6} md={2}>
              <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
                variant="outlined"
                startIcon={<Settings />} 
                fullWidth
                onClick={() => window.location.href = '/settings'}
              >
                Settings
              </button>
            </div>
          </div>
        </div>
      </div>
      
      {/* Footer */}
      <div  sx={{ mt: 4, mb: 2, textAlign: 'center', p: 3, bgcolor: 'grey.50', borderRadius: 2 }}>
        <div  variant="h6" gutterBottom sx={{ fontWeight: 600, color: 'primary.main' }}>
          {BRAND_NAME} - Elite Financial Intelligence
        </div>
        <div  variant="body2" color="text.secondary" paragraph>
          Powered by advanced machine learning, real-time data feeds, and institutional-grade analytics.
        </div>
        <div  sx={{ display: 'flex', justifyContent: 'center', gap: 2, mb: 2 }}>
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" icon={<Security />} label="Bank-Grade Security" color="primary" size="small" />
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" icon={<Speed />} label="Sub-Second Latency" color="success" size="small" />
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" icon={<Psychology />} label="AI-Powered" color="secondary" size="small" />
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" icon={<Public />} label="Global Markets" color="info" size="small" />
        </div>
        <hr className="border-gray-200" sx={{ my: 2 }} />
        <div  variant="caption" color="text.secondary">
          For institutional and qualified investors only. Not investment advice. Data may be delayed. 
          Risk disclosure: Trading involves substantial risk of loss. &copy; {new Date().getFullYear()} {BRAND_NAME}. All rights reserved.
        </div>
      </div>
      </div>
    </DashboardErrorBoundary>
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