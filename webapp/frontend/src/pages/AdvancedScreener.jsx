import React, { useState, useEffect, useMemo } from 'react';
import { useAuth } from '../contexts/AuthContext';
import {
  Box,
  Container,
  Typography,
  Grid,
  Card,
  CardContent,
  Tabs,
  Tab,
  Slider,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Button,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Chip,
  CircularProgress,
  Alert,
  TextField,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Badge,
  Tooltip,
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TablePagination,
  CardHeader,
  LinearProgress,
  Stack,
  Divider,
  Switch,
  FormControlLabel,
  Autocomplete,
  Rating
} from '@mui/material';
import {
  Search,
  FilterList,
  Download,
  Save,
  Star,
  TrendingUp,
  TrendingDown,
  ExpandMore,
  Refresh,
  Analytics,
  Assessment,
  Clear,
  ShowChart,
  Add,
  Delete,
  Edit,
  Share,
  FolderOpen,
  Person,
  BookmarkBorder,
  Bookmark,
  AddShoppingCart,
  PlaylistAdd,
  Compare,
  Timeline,
  Speed,
  Warning,
  CheckCircle,
  Info
} from '@mui/icons-material';
import { getApiConfig, screenStocks } from '../services/api';
import { formatCurrency, formatPercentage, formatNumber } from '../utils/formatters';

function TabPanel({ children, value, index, ...other }) {
  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`screener-tabpanel-${index}`}
      aria-labelledby={`screener-tab-${index}`}
      {...other}
    >
      {value === index && (
        <div  sx={{ py: 3 }}>
          {children}
        </div>
      )}
    </div>
  );
}

const AdvancedScreener = () => {
  const { apiUrl: API_BASE } = getApiConfig();
  const { user, isAuthenticated, isLoading: authLoading } = useAuth();
  
  const [screenCriteria, setScreenCriteria] = useState({
    quality: [0, 100],
    growth: [0, 100],
    value: [0, 100],
    momentum: [0, 100],
    sentiment: [0, 100],
    positioning: [0, 100],
    marketCap: 'any',
    sector: 'any',
    exchange: 'any',
    dividendYield: [0, 20],
    pe: [0, 50],
    pb: [0, 10],
    roe: [0, 50],
    debt: [0, 5],
    // Enhanced criteria
    volume: [0, 1000000],
    price: [0, 1000],
    beta: [0, 3],
    esgScore: [0, 100]
  });

  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [savedScreens, setSavedScreens] = useState([]);
  const [activeTab, setActiveTab] = useState(0);
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);
  const [saveDialogOpen, setSaveDialogOpen] = useState(false);
  const [screenName, setScreenName] = useState('');
  const [screenDescription, setScreenDescription] = useState('');
  const [sectors, setSectors] = useState([]);
  const [screenStats, setScreenStats] = useState(null);
  const [error, setError] = useState(null);
  
  // Enhanced state
  const [sortConfig, setSortConfig] = useState({ key: 'composite', direction: 'desc' });
  const [filterText, setFilterText] = useState('');
  const [selectedStocks, setSelectedStocks] = useState([]);
  const [compareDialogOpen, setCompareDialogOpen] = useState(false);
  const [portfolioDialogOpen, setPortfolioDialogOpen] = useState(false);
  const [presetScreens, setPresetScreens] = useState([]);
  const [watchlists, setWatchlists] = useState([]);
  const [screeningMode, setScreeningMode] = useState('basic'); // 'basic', 'advanced', 'custom'
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [refreshInterval, setRefreshInterval] = useState(30); // seconds

  // Auto-refresh functionality
  useEffect(() => {
    if (autoRefresh && results.length > 0) {
      const interval = setInterval(() => {
        runScreen();
      }, refreshInterval * 1000);
      return () => clearInterval(interval);
    }
  }, [autoRefresh, refreshInterval, results.length]);

  // ⚠️ MOCK DATA - Replace with real API when available
  const mockResults = [
    {
      isMockData: true,
      symbol: 'AAPL',
      company: 'Apple Inc.',
      scores: {
        quality: 85,
        growth: 75,
        value: 60,
        momentum: 80,
        sentiment: 90,
        positioning: 70,
        composite: 77
      },
      price: 175.43,
      marketCap: 2.8e12,
      sector: 'Technology',
      exchange: 'NASDAQ',
      pe: 29.5,
      pb: 8.2,
      roe: 28.5,
      dividendYield: 0.5,
      volume: 45000000,
      beta: 1.2,
      esgScore: 75,
      analystRating: 'Buy',
      targetPrice: 190,
      change24h: 2.1,
      isBookmarked: false
    },
    {
      isMockData: true,
      symbol: 'MSFT',
      company: 'Microsoft Corporation',
      scores: {
        quality: 90,
        growth: 80,
        value: 65,
        momentum: 75,
        sentiment: 85,
        positioning: 80,
        composite: 79
      },
      price: 342.56,
      marketCap: 2.5e12,
      sector: 'Technology',
      exchange: 'NASDAQ',
      pe: 32.1,
      pb: 4.5,
      roe: 22.8,
      dividendYield: 0.8,
      volume: 25000000,
      beta: 0.9,
      esgScore: 82,
      analystRating: 'Buy',
      targetPrice: 380,
      change24h: 1.5,
      isBookmarked: true
    },
    {
      isMockData: true,
      symbol: 'GOOGL',
      company: 'Alphabet Inc.',
      scores: {
        quality: 88,
        growth: 70,
        value: 70,
        momentum: 65,
        sentiment: 80,
        positioning: 75,
        composite: 75
      },
      price: 138.45,
      marketCap: 1.7e12,
      sector: 'Technology',
      exchange: 'NASDAQ',
      pe: 25.3,
      pb: 5.1,
      roe: 18.2,
      dividendYield: 0.0,
      volume: 28000000,
      beta: 1.1,
      esgScore: 70,
      analystRating: 'Buy',
      targetPrice: 155,
      change24h: -0.8,
      isBookmarked: false
    },
    {
      isMockData: true,
      symbol: 'JNJ',
      company: 'Johnson & Johnson',
      scores: {
        quality: 95,
        growth: 45,
        value: 75,
        momentum: 40,
        sentiment: 65,
        positioning: 80,
        composite: 67
      },
      price: 156.78,
      marketCap: 420e9,
      sector: 'Healthcare',
      exchange: 'NYSE',
      pe: 15.8,
      pb: 3.2,
      roe: 25.1,
      dividendYield: 2.9,
      volume: 8000000,
      beta: 0.7,
      esgScore: 88,
      analystRating: 'Hold',
      targetPrice: 165,
      change24h: 0.3,
      isBookmarked: true
    },
    {
      isMockData: true,
      symbol: 'V',
      company: 'Visa Inc.',
      scores: {
        quality: 92,
        growth: 85,
        value: 55,
        momentum: 70,
        sentiment: 88,
        positioning: 75,
        composite: 78
      },
      price: 234.56,
      marketCap: 480e9,
      sector: 'Financial Services',
      exchange: 'NYSE',
      pe: 33.2,
      pb: 12.5,
      roe: 38.5,
      dividendYield: 0.7,
      volume: 6500000,
      beta: 1.0,
      esgScore: 73,
      analystRating: 'Buy',
      targetPrice: 260,
      change24h: 1.8,
      isBookmarked: false
    },
    {
      isMockData: true,
      symbol: 'NVDA',
      company: 'NVIDIA Corporation',
      scores: {
        quality: 80,
        growth: 95,
        value: 30,
        momentum: 90,
        sentiment: 95,
        positioning: 60,
        composite: 75
      },
      price: 875.28,
      marketCap: 2.2e12,
      sector: 'Technology',
      exchange: 'NASDAQ',
      pe: 75.2,
      pb: 22.1,
      roe: 35.8,
      dividendYield: 0.1,
      volume: 35000000,
      beta: 1.7,
      esgScore: 65,
      analystRating: 'Buy',
      targetPrice: 950,
      change24h: 3.2,
      isBookmarked: true
    }
  ];

  // Computed values
  const filteredAndSortedResults = useMemo(() => {
    let filtered = mockResults.filter(stock => {
      // Apply search filter
      if (filterText) {
        const searchLower = filterText.toLowerCase();
        if (!stock.symbol.toLowerCase().includes(searchLower) && 
            !stock.company.toLowerCase().includes(searchLower)) {
          return false;
        }
      }
      
      // Apply screening criteria
      return (
        stock.scores.quality >= screenCriteria.quality[0] && stock.scores.quality <= screenCriteria.quality[1] &&
        stock.scores.growth >= screenCriteria.growth[0] && stock.scores.growth <= screenCriteria.growth[1] &&
        stock.scores.value >= screenCriteria.value[0] && stock.scores.value <= screenCriteria.value[1] &&
        stock.scores.momentum >= screenCriteria.momentum[0] && stock.scores.momentum <= screenCriteria.momentum[1] &&
        stock.scores.sentiment >= screenCriteria.sentiment[0] && stock.scores.sentiment <= screenCriteria.sentiment[1] &&
        stock.scores.positioning >= screenCriteria.positioning[0] && stock.scores.positioning <= screenCriteria.positioning[1] &&
        (screenCriteria.sector === 'any' || stock.sector === screenCriteria.sector) &&
        (screenCriteria.exchange === 'any' || stock.exchange === screenCriteria.exchange) &&
        stock.pe >= screenCriteria.pe[0] && stock.pe <= screenCriteria.pe[1] &&
        stock.pb >= screenCriteria.pb[0] && stock.pb <= screenCriteria.pb[1] &&
        stock.roe >= screenCriteria.roe[0] && stock.roe <= screenCriteria.roe[1] &&
        stock.dividendYield >= screenCriteria.dividendYield[0] && stock.dividendYield <= screenCriteria.dividendYield[1] &&
        stock.price >= screenCriteria.price[0] && stock.price <= screenCriteria.price[1] &&
        stock.beta >= screenCriteria.beta[0] && stock.beta <= screenCriteria.beta[1] &&
        stock.esgScore >= screenCriteria.esgScore[0] && stock.esgScore <= screenCriteria.esgScore[1]
      );
    });

    // Apply sorting
    if (sortConfig.key) {
      filtered.sort((a, b) => {
        let aVal = sortConfig.key.includes('.') ? 
          sortConfig.key.split('.').reduce((obj, key) => obj[key], a) : a[sortConfig.key];
        let bVal = sortConfig.key.includes('.') ? 
          sortConfig.key.split('.').reduce((obj, key) => obj[key], b) : b[sortConfig.key];
        
        if (typeof aVal === 'string') {
          aVal = aVal.toLowerCase();
          bVal = bVal.toLowerCase();
        }
        
        if (sortConfig.direction === 'asc') {
          return aVal > bVal ? 1 : -1;
        } else {
          return aVal < bVal ? 1 : -1;
        }
      });
    }

    return filtered;
  }, [filterText, screenCriteria, sortConfig]);

  useEffect(() => {
    loadSavedScreens();
    loadSectors();
    loadScreenStats();
    loadPresetScreens();
    loadWatchlists();
  }, []);

  // Enhanced: Load user-specific data when authenticated
  useEffect(() => {
    if (isAuthenticated) {
      loadUserScreens();
      loadUserWatchlists();
    }
  }, [isAuthenticated]);

  const loadPresetScreens = () => {
    setPresetScreens([
      {
        id: 'growth_stocks',
        name: 'High Growth Stocks',
        description: 'Stocks with strong growth potential',
        criteria: { ...screenCriteria, growth: [70, 100], momentum: [60, 100] }
      },
      {
        id: 'value_stocks',
        name: 'Value Opportunities',
        description: 'Undervalued stocks with strong fundamentals',
        criteria: { ...screenCriteria, value: [70, 100], pe: [0, 20] }
      },
      {
        id: 'dividend_stocks',
        name: 'Dividend Champions',
        description: 'High-quality dividend paying stocks',
        criteria: { ...screenCriteria, quality: [80, 100], dividendYield: [2, 20] }
      },
      {
        id: 'esg_leaders',
        name: 'ESG Leaders',
        description: 'Companies with strong ESG ratings',
        criteria: { ...screenCriteria, esgScore: [80, 100], quality: [70, 100] }
      }
    ]);
  };

  const loadWatchlists = () => {
    setWatchlists([
      { id: 1, name: 'Tech Giants', symbols: ['AAPL', 'MSFT', 'GOOGL', 'NVDA'] },
      { id: 2, name: 'Healthcare Leaders', symbols: ['JNJ', 'PFE', 'UNH'] },
      { id: 3, name: 'Financial Services', symbols: ['V', 'MA', 'JPM'] }
    ]);
  };

  const loadUserScreens = async () => {
    try {
      const { api } = await import('../services/api');
      const response = await api.get('/api/screener/screens');
      setSavedScreens(response.data?.screens || []);
    } catch (error) {
      console.error('Error loading user screens:', error);
      // Fallback to localStorage
      const localScreens = JSON.parse(localStorage.getItem('screener_screens') || '[]');
      setSavedScreens(localScreens);
    }
  };

  const loadUserWatchlists = async () => {
    try {
      const { api } = await import('../services/api');
      const response = await api.get('/api/screener/watchlists');
      setWatchlists(response.data?.watchlists || []);
    } catch (error) {
      console.error('Error loading user watchlists:', error);
    }
  };

  const loadSavedScreens = async () => {
    try {
      // Mock saved screens for now - would integrate with backend later
      setSavedScreens([
        { id: 1, name: 'High Quality Growth', criteria: screenCriteria },
        { id: 2, name: 'Value Opportunities', criteria: { ...screenCriteria, value: [70, 100] } },
        { id: 3, name: 'Momentum Plays', criteria: { ...screenCriteria, momentum: [80, 100] } }
      ]);
    } catch (error) {
      console.error('Failed to load saved screens:', error);
    }
  };

  const loadSectors = async () => {
    try {
      const { api } = await import('../services/api');
      const response = await api.get('/api/stocks/sectors');
      setSectors(response.data?.sectors || []);
    } catch (error) {
      console.error('Failed to load sectors:', error);
      // Fallback to mock data
      setSectors([
        'Technology', 'Healthcare', 'Financials', 'Consumer Discretionary',
        'Communication Services', 'Industrials', 'Consumer Staples',
        'Energy', 'Utilities', 'Real Estate', 'Materials'
      ]);
    }
  };

  const loadScreenStats = async () => {
    try {
      const { api } = await import('../services/api');
      const response = await api.get('/api/stocks/screen/stats');
      setScreenStats(response.data || {});
    } catch (error) {
      console.error('Failed to load screen stats:', error);
      // Fallback to mock data
      setScreenStats({
        totalStocks: 8500,
        lastUpdated: new Date().toISOString(),
        averageMarketCap: '2.5B',
        sectors: 11,
        exchanges: 3
      });
    }
  };

  const runScreen = async () => {
    setLoading(true);
    setError(null);
    try {
      // Build query parameters for enhanced screening API
      const params = new URLSearchParams({
        limit: 200,
        sortBy: 'composite_score',
        sortOrder: 'desc'
      });

      // Add criteria filters
      const { quality, growth, value, momentum, sentiment, positioning, marketCap, sector, exchange, pe, pb, roe, dividendYield } = screenCriteria;
      
      // Score filters (convert 0-100 to 0-1 for backend)
      if (quality[0] > 0) params.append('minQuality', quality[0] / 100);
      if (quality[1] < 100) params.append('maxQuality', quality[1] / 100);
      if (growth[0] > 0) params.append('minGrowth', growth[0] / 100);
      if (growth[1] < 100) params.append('maxGrowth', growth[1] / 100);
      if (value[0] > 0) params.append('minValue', value[0] / 100);
      if (value[1] < 100) params.append('maxValue', value[1] / 100);
      if (momentum[0] > 0) params.append('minMomentum', momentum[0] / 100);
      if (momentum[1] < 100) params.append('maxMomentum', momentum[1] / 100);
      if (sentiment[0] > 0) params.append('minSentiment', sentiment[0] / 100);
      if (sentiment[1] < 100) params.append('maxSentiment', sentiment[1] / 100);
      if (positioning[0] > 0) params.append('minPositioning', positioning[0] / 100);
      if (positioning[1] < 100) params.append('maxPositioning', positioning[1] / 100);
      
      // Financial metrics filters
      if (pe[0] > 0) params.append('minPE', pe[0]);
      if (pe[1] < 50) params.append('maxPE', pe[1]);
      if (pb[0] > 0) params.append('minPB', pb[0]);
      if (pb[1] < 10) params.append('maxPB', pb[1]);
      if (roe[0] > 0) params.append('minROE', roe[0] / 100);
      if (roe[1] < 50) params.append('maxROE', roe[1] / 100);
      if (dividendYield[0] > 0) params.append('minDividendYield', dividendYield[0] / 100);
      if (dividendYield[1] < 20) params.append('maxDividendYield', dividendYield[1] / 100);
      
      // Category filters
      if (marketCap !== 'any') params.append('marketCapTier', marketCap);
      if (sector !== 'any') params.append('sector', sector);
      if (exchange !== 'any') params.append('exchange', exchange);

      const response = await screenStocks(params);
      
      if (response.success && response.data) {
        const stocks = response.data.stocks || response.data || [];
        
        // Transform API data to match component structure
        const transformedResults = stocks.map(stock => ({
          symbol: stock.symbol,
          company: stock.company_name || stock.security_name || `${stock.symbol} Corp`,
          scores: {
            quality: Math.round((stock.quality_score || 0) * 100),
            growth: Math.round((stock.growth_score || 0) * 100),
            value: Math.round((stock.value_score || 0) * 100),
            momentum: Math.round((stock.momentum_score || 0) * 100),
            sentiment: Math.round((stock.sentiment_score || 0) * 100),
            positioning: Math.round((stock.positioning_score || 0) * 100),
            composite: Math.round((stock.composite_score || 0) * 100)
          },
          price: stock.current_price || 0,
          marketCap: stock.market_cap || 0,
          sector: stock.sector || 'Unknown',
          exchange: stock.exchange || 'Unknown',
          pe: stock.pe_ratio,
          pb: stock.pb_ratio,
          roe: stock.roe,
          dividendYield: stock.dividend_yield,
          beta: stock.beta,
          esgScore: stock.esg_score ? Math.round(stock.esg_score * 100) : 0
        }));

        setResults(transformedResults);
        setActiveTab(1);
      } else {
        throw new Error(response.error || 'Failed to run screen');
      }
    } catch (error) {
      console.error('Failed to run screen:', error);
      setError(error.message || 'Failed to run screen. Please try again.');
      setResults([]);
      setActiveTab(1);
    } finally {
      setLoading(false);
    }
  };

  const saveScreen = async () => {
    if (!screenName.trim()) return;

    try {
      const screenData = {
        name: screenName.trim(),
        description: screenDescription.trim(),
        criteria: screenCriteria,
        createdAt: new Date().toISOString(),
        author: user?.username || user?.email || 'Anonymous',
        userId: user?.id || null
      };

      if (isAuthenticated && user) {
        // Save to backend
        const headers = { 'Content-Type': 'application/json' };
        if (user?.token) {
          headers['Authorization'] = `Bearer ${user.token}`;
        }

        const response = await fetch(`${API_BASE}/api/screener/screens`, {
          method: 'POST',
          headers,
          body: JSON.stringify(screenData)
        });

        if (response.ok) {
          await loadUserScreens();
        } else {
          throw new Error('Failed to save screen to server');
        }
      } else {
        // Save to localStorage for non-authenticated users
        const localScreens = JSON.parse(localStorage.getItem('screener_screens') || '[]');
        const newId = Date.now().toString();
        localScreens.push({ ...screenData, id: newId });
        localStorage.setItem('screener_screens', JSON.stringify(localScreens));
        setSavedScreens(localScreens);
      }

      setSaveDialogOpen(false);
      setScreenName('');
      setScreenDescription('');
    } catch (error) {
      console.error('Failed to save screen:', error);
      alert('Failed to save screen. Please try again.');
    }
  };

  // Enhanced action handlers
  const handleSort = (key) => {
    setSortConfig(prevSort => ({
      key,
      direction: prevSort.key === key && prevSort.direction === 'desc' ? 'asc' : 'desc'
    }));
  };

  const handleStockSelect = (symbol, selected) => {
    if (selected) {
      setSelectedStocks(prev => [...prev, symbol]);
    } else {
      setSelectedStocks(prev => prev.filter(s => s !== symbol));
    }
  };

  const handleToggleBookmark = async (symbol) => {
    try {
      if (isAuthenticated) {
        // Update bookmark on server
        const headers = { 'Content-Type': 'application/json' };
        if (user?.token) {
          headers['Authorization'] = `Bearer ${user.token}`;
        }

        await fetch(`${API_BASE}/api/screener/bookmark/${symbol}`, {
          method: 'POST',
          headers
        });
      }

      // Update local state
      setResults(prev => prev.map(stock => 
        stock.symbol === symbol 
          ? { ...stock, isBookmarked: !stock.isBookmarked }
          : stock
      ));
    } catch (error) {
      console.error('Failed to toggle bookmark:', error);
    }
  };

  const handleAddToPortfolio = (symbols) => {
    setPortfolioDialogOpen(true);
    // Implementation for adding stocks to portfolio
    console.log('Adding to portfolio:', symbols);
  };

  const handleCompareStocks = () => {
    if (selectedStocks.length < 2) {
      alert('Please select at least 2 stocks to compare');
      return;
    }
    setCompareDialogOpen(true);
  };

  const loadPresetScreen = (preset) => {
    setScreenCriteria(preset.criteria);
    runScreen();
  };

  const exportResults = () => {
    if (!filteredAndSortedResults.length) return;
    
    const csv = [
      ['Symbol', 'Company', 'Price', 'Market Cap', 'Sector', 'P/E', 'P/B', 'ROE', 'Div Yield', 'Beta', 'ESG', 'Composite Score'].join(','),
      ...filteredAndSortedResults.map(stock => [
        stock.symbol,
        `"${stock.company}"`,
        stock.price,
        stock.marketCap,
        stock.sector,
        stock.pe,
        stock.pb,
        stock.roe,
        stock.dividendYield,
        stock.beta,
        stock.esgScore,
        stock.scores.composite
      ].join(','))
    ].join('\n');

    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `screener_results_${new Date().toISOString().split('T')[0]}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const resetCriteria = () => {
    setScreenCriteria({
      quality: [0, 100],
      growth: [0, 100],
      value: [0, 100],
      momentum: [0, 100],
      sentiment: [0, 100],
      positioning: [0, 100],
      marketCap: 'any',
      sector: 'any',
      exchange: 'any',
      dividendYield: [0, 20],
      pe: [0, 50],
      pb: [0, 10],
      roe: [0, 50],
      debt: [0, 5],
      volume: [0, 1000000],
      price: [0, 1000],
      beta: [0, 3],
      esgScore: [0, 100]
    });
  };

  const loadScreen = (criteria) => {
    setScreenCriteria(criteria);
    setActiveTab(0);
  };


  const getScoreColor = (score) => {
    if (score >= 80) return 'success';
    if (score >= 60) return 'warning';
    return 'error';
  };

  const getScoreIcon = (score) => {
    if (score >= 80) return <TrendingUp />;
    if (score >= 60) return <ShowChart />;
    return <TrendingDown />;
  };

  return (
    <div className="container mx-auto" maxWidth="xl" sx={{ py: 3 }}>
      {/* Enhanced Header */}
      <div  display="flex" alignItems="center" justifyContent="between" mb={3}>
        <div>
          <div  variant="h4" gutterBottom sx={{ fontWeight: 700, display: 'flex', alignItems: 'center' }}>
            <Analytics sx={{ mr: 2, color: 'primary.main' }} />
            Advanced Stock Screener
          </div>
          <div  variant="body1" color="text.secondary">
            Professional-grade stock screening with multi-factor analysis and real-time scoring
          </div>
          <div  display="flex" gap={1} mt={1}>
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="Multi-Factor Analysis" color="primary" size="small" variant="outlined" />
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="Real-Time Scoring" color="success" size="small" variant="outlined" />
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="Portfolio Integration" color="info" size="small" variant="outlined" />
            {isAuthenticated && <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="Cloud Sync" color="secondary" size="small" variant="outlined" />}
          </div>
        </div>

        <div  display="flex" alignItems="center" gap={2}>
          {/* Authentication Status */}
          {authLoading ? (
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" size={24} />
          ) : isAuthenticated ? (
            <div  display="flex" alignItems="center" gap={1}>
              <Person color="primary" />
              <div  variant="body2" color="primary">
                {user?.username || user?.email || 'User'}
              </div>
            </div>
          ) : (
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="Guest Mode" color="warning" size="small" variant="outlined" />
          )}

          {/* Quick Actions */}
          <span className="inline-flex items-center justify-center px-2 py-1 text-xs font-bold leading-none text-red-100 bg-red-600 rounded-full" badgeContent={savedScreens.length} color="primary">
            <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
              variant="outlined"
              startIcon={<FolderOpen />}
              onClick={() => setActiveTab(2)}
              size="small"
            >
              My Screens
            </button>
          </span>

          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
            variant="outlined"
            startIcon={<Save />}
            onClick={() => setSaveDialogOpen(true)}
            size="small"
            disabled={!filteredAndSortedResults.length}
          >
            Save Screen
          </button>

          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
            variant="outlined"
            startIcon={<Download />}
            onClick={exportResults}
            size="small"
            disabled={!filteredAndSortedResults.length}
          >
            Export
          </button>

          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
            variant="outlined"
            startIcon={<Refresh />}
            onClick={runScreen}
            size="small"
            disabled={loading || !results.length}
          >
            Refresh
          </button>

          <div className="mb-4"Label
            control={
              <input type="checkbox" className="toggle"
                checked={autoRefresh}
                onChange={(e) => setAutoRefresh(e.target.checked)}
                size="small"
              />
            }
            label="Auto-refresh"
            sx={{ ml: 1 }}
          />

          {autoRefresh && (
            <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              select
              value={refreshInterval}
              onChange={(e) => setRefreshInterval(Number(e.target.value))}
              size="small"
              sx={{ ml: 1, minWidth: 80 }}
            >
              <option  value={10}>10s</option>
              <option  value={30}>30s</option>
              <option  value={60}>1m</option>
              <option  value={300}>5m</option>
            </input>
          )}
        </div>
      </div>

      {/* Screen Statistics */}
      {filteredAndSortedResults.length > 0 && (
        <div className="bg-white shadow-md rounded-lg" sx={{ mb: 3, bgcolor: 'primary.dark', color: 'primary.contrastText' }}>
          <div className="bg-white shadow-md rounded-lg"Content sx={{ py: 2 }}>
            <div  display="flex" alignItems="center" justifyContent="between">
              <div  display="flex" alignItems="center" gap={4}>
                <div>
                  <div  variant="h6" fontWeight="bold">
                    {filteredAndSortedResults.length} Stocks Found
                  </div>
                  <div  variant="body2" sx={{ opacity: 0.8 }}>
                    Average Composite Score: {(filteredAndSortedResults.reduce((sum, stock) => sum + stock.scores.composite, 0) / filteredAndSortedResults.length).toFixed(1)}
                  </div>
                </div>
                
                <div  display="flex" gap={3}>
                  <div  textAlign="center">
                    <div  variant="body2" sx={{ opacity: 0.8 }}>High Quality (80+)</div>
                    <div  variant="h6" fontWeight="bold">
                      {filteredAndSortedResults.filter(s => s.scores.quality >= 80).length}
                    </div>
                  </div>
                  <div  textAlign="center">
                    <div  variant="body2" sx={{ opacity: 0.8 }}>Growth Leaders (70+)</div>
                    <div  variant="h6" fontWeight="bold">
                      {filteredAndSortedResults.filter(s => s.scores.growth >= 70).length}
                    </div>
                  </div>
                  <div  textAlign="center">
                    <div  variant="body2" sx={{ opacity: 0.8 }}>Selected</div>
                    <div  variant="h6" fontWeight="bold">
                      {selectedStocks.length}
                    </div>
                  </div>
                </div>
              </div>
              
              <div  display="flex" alignItems="center" gap={2}>
                {selectedStocks.length > 0 && (
                  <div  display="flex" gap={1}>
                    <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                      variant="contained"
                      startIcon={<Compare />}
                      onClick={handleCompareStocks}
                      size="small"
                      disabled={selectedStocks.length < 2}
                    >
                      Compare ({selectedStocks.length})
                    </button>
                    <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                      variant="contained"
                      startIcon={<AddShoppingCart />}
                      onClick={() => handleAddToPortfolio(selectedStocks)}
                      size="small"
                    >
                      Add to Portfolio
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Preset Screens */}
      {presetScreens.length > 0 && (
        <div className="bg-white shadow-md rounded-lg" sx={{ mb: 3 }}>
          <div className="bg-white shadow-md rounded-lg"Header
            title="Quick Preset Screens"
            subheader="Get started with professionally designed screening strategies"
          />
          <div className="bg-white shadow-md rounded-lg"Content>
            <div className="grid" container spacing={2}>
              {presetScreens.map((preset) => (
                <div className="grid" item xs={12} sm={6} md={3} key={preset.id}>
                  <div className="bg-white shadow-md rounded-lg" 
                    variant="outlined" 
                    sx={{ 
                      cursor: 'pointer', 
                      '&:hover': { boxShadow: 2 },
                      transition: 'all 0.2s'
                    }}
                    onClick={() => loadPresetScreen(preset)}
                  >
                    <div className="bg-white shadow-md rounded-lg"Content sx={{ textAlign: 'center', p: 2 }}>
                      <div  variant="h6" sx={{ fontWeight: 600, mb: 1 }}>
                        {preset.name}
                      </div>
                      <div  variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                        {preset.description}
                      </div>
                      <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
                        variant="outlined" 
                        size="small" 
                        startIcon={<PlaylistAdd />}
                      >
                        Apply Screen
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      <div className="border-b border-gray-200" value={activeTab} onChange={(e, v) => setActiveTab(v)} sx={{ mb: 3 }}>
        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Screening Criteria" icon={<FilterList />} />
        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label={`Results (${results.length})`} icon={<Assessment />} />
        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Saved Screens" icon={<Save />} />
      </div>

      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={activeTab} index={0}>
        <div className="grid" container spacing={3}>
          <div className="grid" item xs={12} md={8}>
            <div className="bg-white shadow-md rounded-lg">
              <div className="bg-white shadow-md rounded-lg"Content>
                <div  variant="h6" gutterBottom>
                  Score Criteria
                </div>
                
                <div className="grid" container spacing={3}>
                  {Object.entries(screenCriteria).filter(([key]) => 
                    ['quality', 'growth', 'value', 'momentum', 'sentiment', 'positioning'].includes(key)
                  ).map(([key, value]) => (
                    <div className="grid" item xs={12} sm={6} key={key}>
                      <div  variant="body2" sx={{ mb: 1, textTransform: 'capitalize' }}>
                        {key} Score: {value[0]} - {value[1]}
                      </div>
                      <Slider
                        value={value}
                        onChange={(e, newValue) => setScreenCriteria(prev => ({ ...prev, [key]: newValue }))}
                        valueLabelDisplay="auto"
                        min={0}
                        max={100}
                        color="primary"
                        sx={{ mb: 2 }}
                      />
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="bg-white shadow-md rounded-lg" sx={{ mt: 3 }}>
              <div className="bg-white shadow-md rounded-lg"Content>
                <div  variant="h6" gutterBottom>
                  Financial Metrics
                </div>
                
                <div className="grid" container spacing={3}>
                  <div className="grid" item xs={12} sm={6}>
                    <div  variant="body2" sx={{ mb: 1 }}>
                      Dividend Yield: {screenCriteria.dividendYield[0]}% - {screenCriteria.dividendYield[1]}%
                    </div>
                    <Slider
                      value={screenCriteria.dividendYield}
                      onChange={(e, newValue) => setScreenCriteria(prev => ({ ...prev, dividendYield: newValue }))}
                      valueLabelDisplay="auto"
                      min={0}
                      max={20}
                      step={0.1}
                      color="secondary"
                      sx={{ mb: 2 }}
                    />
                  </div>
                  
                  <div className="grid" item xs={12} sm={6}>
                    <div  variant="body2" sx={{ mb: 1 }}>
                      P/E Ratio: {screenCriteria.pe[0]} - {screenCriteria.pe[1]}
                    </div>
                    <Slider
                      value={screenCriteria.pe}
                      onChange={(e, newValue) => setScreenCriteria(prev => ({ ...prev, pe: newValue }))}
                      valueLabelDisplay="auto"
                      min={0}
                      max={50}
                      color="secondary"
                      sx={{ mb: 2 }}
                    />
                  </div>
                  
                  <div className="grid" item xs={12} sm={6}>
                    <div  variant="body2" sx={{ mb: 1 }}>
                      P/B Ratio: {screenCriteria.pb[0]} - {screenCriteria.pb[1]}
                    </div>
                    <Slider
                      value={screenCriteria.pb}
                      onChange={(e, newValue) => setScreenCriteria(prev => ({ ...prev, pb: newValue }))}
                      valueLabelDisplay="auto"
                      min={0}
                      max={10}
                      step={0.1}
                      color="secondary"
                      sx={{ mb: 2 }}
                    />
                  </div>
                  
                  <div className="grid" item xs={12} sm={6}>
                    <div  variant="body2" sx={{ mb: 1 }}>
                      ROE: {screenCriteria.roe[0]}% - {screenCriteria.roe[1]}%
                    </div>
                    <Slider
                      value={screenCriteria.roe}
                      onChange={(e, newValue) => setScreenCriteria(prev => ({ ...prev, roe: newValue }))}
                      valueLabelDisplay="auto"
                      min={0}
                      max={50}
                      step={1}
                      color="secondary"
                      sx={{ mb: 2 }}
                    />
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="grid" item xs={12} md={4}>
            <div className="bg-white shadow-md rounded-lg">
              <div className="bg-white shadow-md rounded-lg"Content>
                <div  variant="h6" gutterBottom>
                  Market Filters
                </div>
                
                <div className="mb-4" fullWidth sx={{ mb: 2 }}>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Market Cap</label>
                  <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={screenCriteria.marketCap}
                    onChange={(e) => setScreenCriteria(prev => ({ ...prev, marketCap: e.target.value }))}
                  >
                    <option  value="any">Any</option>
                    <option  value="mega_cap">Mega Cap (&gt;$200B)</option>
                    <option  value="large_cap">Large Cap ($10B-$200B)</option>
                    <option  value="mid_cap">Mid Cap ($2B-$10B)</option>
                    <option  value="small_cap">Small Cap ($300M-$2B)</option>
                    <option  value="micro_cap">Micro Cap (&lt;$300M)</option>
                  </select>
                </div>

                <div className="mb-4" fullWidth sx={{ mb: 2 }}>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Sector</label>
                  <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={screenCriteria.sector}
                    onChange={(e) => setScreenCriteria(prev => ({ ...prev, sector: e.target.value }))}
                  >
                    <option  value="any">Any Sector</option>
                    {sectors.map((sector) => (
                      <option  key={sector.sector} value={sector.sector}>
                        {sector.sector} ({sector.count} stocks)
                      </option>
                    ))}
                  </select>
                </div>

                <div className="mb-4" fullWidth sx={{ mb: 3 }}>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Exchange</label>
                  <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={screenCriteria.exchange}
                    onChange={(e) => setScreenCriteria(prev => ({ ...prev, exchange: e.target.value }))}
                  >
                    <option  value="any">Any Exchange</option>
                    <option  value="NYSE">NYSE</option>
                    <option  value="NASDAQ">NASDAQ</option>
                  </select>
                </div>

                <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  variant="contained"
                  color="primary"
                  fullWidth
                  size="large"
                  onClick={runScreen}
                  disabled={loading}
                  startIcon={loading ? <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" size={20} /> : <Search />}
                  sx={{ mb: 2 }}
                >
                  {loading ? 'Screening...' : 'Run Screen'}
                </button>

                <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  variant="outlined"
                  fullWidth
                  onClick={() => setSaveDialogOpen(true)}
                  startIcon={<Save />}
                  sx={{ mb: 1 }}
                >
                  Save Screen
                </button>

                <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  variant="outlined"
                  fullWidth
                  onClick={() => setScreenCriteria({
                    quality: [0, 100],
                    growth: [0, 100],
                    value: [0, 100],
                    momentum: [0, 100],
                    sentiment: [0, 100],
                    positioning: [0, 100],
                    marketCap: 'any',
                    sector: 'any',
                    exchange: 'any',
                    dividendYield: [0, 20],
                    pe: [0, 50],
                    pb: [0, 10],
                    roe: [0, 50],
                    debt: [0, 5]
                  })}
                  startIcon={<Clear />}
                >
                  Clear Filters
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={activeTab} index={1}>
        <div  sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
          <div  variant="h6">
            Screening Results ({results.length} stocks found)
          </div>
          {results.length > 0 && (
            <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
              variant="outlined"
              startIcon={<Download />}
              onClick={exportResults}
            >
              Export CSV
            </button>
          )}
        </div>

        {error && (
          <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error" sx={{ mb: 2 }}>
            {error}
          </div>
        )}

        {results.length === 0 && !error ? (
          <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="info">
            No results to display. Run a screen to see matching stocks.
          </div>
        ) : !error && (
          <div className="bg-white shadow-md rounded-lg">
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Symbol</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Company</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center">Quality</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center">Growth</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center">Value</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center">Momentum</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center">Sentiment</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center">Composite</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Price</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">P/E</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">P/B</td>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Market Cap</td>
                  </tr>
                </thead>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
                  {results
                    .slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage)
                    .map((stock) => (
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={stock.symbol} hover>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                        <div  variant="body2" fontWeight="bold">
                          {stock.symbol}
                        </div>
                      </td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                        <div  variant="body2">
                          {stock.company}
                        </div>
                      </td>
                      {['quality', 'growth', 'value', 'momentum', 'sentiment'].map((metric) => (
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell key={metric} align="center">
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                            label={stock.scores[metric]}
                            color={getScoreColor(stock.scores[metric])}
                            size="small"
                            icon={getScoreIcon(stock.scores[metric])}
                          />
                        </td>
                      ))}
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center">
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                          label={stock.scores.composite}
                          color={getScoreColor(stock.scores.composite)}
                          variant="filled"
                        />
                      </td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                        {formatCurrency(stock.price)}
                      </td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                        {stock.pe ? formatNumber(stock.pe) : 'N/A'}
                      </td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                        {stock.pb ? formatNumber(stock.pb) : 'N/A'}
                      </td>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                        {formatCurrency(stock.marketCap, 0)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"lePagination
              component="div"
              count={results.length}
              page={page}
              onPageChange={(e, newPage) => setPage(newPage)}
              rowsPerPage={rowsPerPage}
              onRowsPerPageChange={(e) => {
                setRowsPerPage(parseInt(e.target.value));
                setPage(0);
              }}
            />
          </div>
        )}
      </div>

      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={activeTab} index={2}>
        <div  variant="h6" gutterBottom>
          Saved Screening Strategies
        </div>
        
        <div className="grid" container spacing={2}>
          {savedScreens.map((screen) => (
            <div className="grid" item xs={12} sm={6} md={4} key={screen.id}>
              <div className="bg-white shadow-md rounded-lg">
                <div className="bg-white shadow-md rounded-lg"Content>
                  <div  variant="h6" gutterBottom>
                    {screen.name}
                  </div>
                  <div  variant="body2" color="text.secondary" gutterBottom>
                    Quality: {screen.criteria.quality[0]}-{screen.criteria.quality[1]}
                  </div>
                  <div  variant="body2" color="text.secondary" gutterBottom>
                    Growth: {screen.criteria.growth[0]}-{screen.criteria.growth[1]}
                  </div>
                  <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                    variant="outlined"
                    size="small"
                    onClick={() => loadScreen(screen.criteria)}
                    sx={{ mt: 1 }}
                  >
                    Load Screen
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Save Screen Dialog */}
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50" open={saveDialogOpen} onClose={() => setSaveDialogOpen(false)}>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Title>Save Screening Strategy</h2>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Content>
          <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            autoFocus
            margin="dense"
            label="Screen Name"
            fullWidth
            variant="outlined"
            value={screenName}
            onChange={(e) => setScreenName(e.target.value)}
          />
        </div>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Actions>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" onClick={() => setSaveDialogOpen(false)}>Cancel</button>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" onClick={saveScreen} variant="contained">Save</button>
        </div>
      </div>

      {/* Stock Comparison Dialog */}
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50" 
        open={compareDialogOpen} 
        onClose={() => setCompareDialogOpen(false)}
        maxWidth="lg"
        fullWidth
      >
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Title>
          <div  display="flex" alignItems="center" gap={1}>
            <Compare />
            Stock Comparison
          </div>
        </h2>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Content>
          {selectedStocks.length > 0 ? (
            <div  sx={{ mt: 2 }}>
              <div className="grid" container spacing={2}>
                {selectedStocks.map((symbol) => {
                  const stock = mockResults.find(s => s.symbol === symbol);
                  if (!stock) return null;
                  
                  return (
                    <div className="grid" item xs={12} md={6} lg={4} key={symbol}>
                      <div className="bg-white shadow-md rounded-lg">
                        <div className="bg-white shadow-md rounded-lg"Header 
                          title={stock.symbol}
                          subheader={stock.company}
                          avatar={
                            <div  sx={{ 
                              bgcolor: getScoreColor(stock.scores.composite) + '.main', 
                              color: 'white',
                              borderRadius: '50%',
                              width: 40,
                              height: 40,
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              fontSize: '0.875rem',
                              fontWeight: 'bold'
                            }}>
                              {stock.scores.composite}
                            </div>
                          }
                        />
                        <div className="bg-white shadow-md rounded-lg"Content>
                          <div  sx={{ mb: 2 }}>
                            <div  variant="h6" color="primary">
                              {formatCurrency(stock.price)}
                            </div>
                            <div  variant="body2" color="text.secondary">
                              {stock.sector} • {formatCurrency(stock.marketCap, 0)}
                            </div>
                          </div>
                          
                          <div className="grid" container spacing={1} sx={{ mb: 2 }}>
                            <div className="grid" item xs={6}>
                              <div  variant="body2">P/E Ratio</div>
                              <div  variant="body1" fontWeight="bold">
                                {stock.pe || 'N/A'}
                              </div>
                            </div>
                            <div className="grid" item xs={6}>
                              <div  variant="body2">P/B Ratio</div>
                              <div  variant="body1" fontWeight="bold">
                                {stock.pb || 'N/A'}
                              </div>
                            </div>
                            <div className="grid" item xs={6}>
                              <div  variant="body2">ROE</div>
                              <div  variant="body1" fontWeight="bold">
                                {stock.roe ? formatPercentage(stock.roe) : 'N/A'}
                              </div>
                            </div>
                            <div className="grid" item xs={6}>
                              <div  variant="body2">Dividend</div>
                              <div  variant="body1" fontWeight="bold">
                                {stock.dividendYield ? formatPercentage(stock.dividendYield) : 'N/A'}
                              </div>
                            </div>
                          </div>

                          <hr className="border-gray-200" sx={{ my: 2 }} />
                          
                          <div  variant="subtitle2" gutterBottom>
                            Score Breakdown
                          </div>
                          <div className="grid" container spacing={1}>
                            {Object.entries(stock.scores).filter(([key]) => key !== 'composite').map(([key, value]) => (
                              <div className="grid" item xs={6} key={key}>
                                <div  display="flex" alignItems="center" gap={1}>
                                  <div  variant="body2" sx={{ textTransform: 'capitalize' }}>
                                    {key}:
                                  </div>
                                  <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                                    label={value}
                                    size="small"
                                    color={getScoreColor(value)}
                                  />
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ) : (
            <div>No stocks selected for comparison</div>
          )}
        </div>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Actions>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" onClick={() => setCompareDialogOpen(false)}>Close</button>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
            variant="contained" 
            onClick={() => handleAddToPortfolio(selectedStocks)}
            disabled={selectedStocks.length === 0}
          >
            Add All to Portfolio
          </button>
        </div>
      </div>

      {/* Portfolio Integration Dialog */}
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50" 
        open={portfolioDialogOpen} 
        onClose={() => setPortfolioDialogOpen(false)}
        maxWidth="md"
        fullWidth
      >
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Title>
          <div  display="flex" alignItems="center" gap={1}>
            <AddShoppingCart />
            Add to Portfolio
          </div>
        </h2>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Content>
          <div  sx={{ mt: 2 }}>
            <div  variant="body1" gutterBottom>
              You're about to add {selectedStocks.length} stock{selectedStocks.length > 1 ? 's' : ''} to your portfolio:
            </div>
            
            <div  sx={{ my: 2 }}>
              {selectedStocks.map((symbol) => {
                const stock = mockResults.find(s => s.symbol === symbol);
                if (!stock) return null;
                
                return (
                  <div  key={symbol} sx={{ 
                    display: 'flex', 
                    alignItems: 'center', 
                    gap: 2, 
                    py: 1, 
                    px: 2,
                    bgcolor: 'background.paper',
                    borderRadius: 1,
                    border: '1px solid',
                    borderColor: 'divider',
                    mb: 1
                  }}>
                    <div  sx={{ 
                      bgcolor: getScoreColor(stock.scores.composite) + '.main', 
                      color: 'white',
                      borderRadius: '50%',
                      width: 32,
                      height: 32,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontSize: '0.75rem',
                      fontWeight: 'bold'
                    }}>
                      {stock.scores.composite}
                    </div>
                    <div  sx={{ flex: 1 }}>
                      <div  variant="subtitle1" fontWeight="bold">
                        {stock.symbol}
                      </div>
                      <div  variant="body2" color="text.secondary">
                        {stock.company}
                      </div>
                    </div>
                    <div  sx={{ textAlign: 'right' }}>
                      <div  variant="h6" color="primary">
                        {formatCurrency(stock.price)}
                      </div>
                      <div  variant="body2" color="text.secondary">
                        {stock.sector}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>

            <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="info" sx={{ mt: 2 }}>
              {isAuthenticated ? (
                <div>
                  <div  variant="body2">
                    These stocks will be added to your portfolio for tracking. You can manage position sizes and set alerts from your Portfolio page.
                  </div>
                  <div  variant="body2" sx={{ mt: 1 }}>
                    <strong>Logged in as:</strong> {user?.email}
                  </div>
                </div>
              ) : (
                <div>
                  <div  variant="body2">
                    You're not signed in. These stocks will be saved locally and won't sync across devices.
                  </div>
                  <div  variant="body2" sx={{ mt: 1 }}>
                    <strong>Tip:</strong> Sign in to sync your portfolio across all devices.
                  </div>
                </div>
              )}
            </div>

            {isAuthenticated && (
              <div  sx={{ mt: 2 }}>
                <div className="mb-4" fullWidth variant="outlined">
                  <label className="block text-sm font-medium text-gray-700 mb-1">Portfolio</label>
                  <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value="main"
                    label="Portfolio"
                  >
                    <option  value="main">Main Portfolio</option>
                    <option  value="watchlist">Watchlist</option>
                    <option  value="research">Research List</option>
                  </select>
                </div>
              </div>
            )}
          </div>
        </div>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Actions>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" onClick={() => setPortfolioDialogOpen(false)}>
            Cancel
          </button>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
            variant="contained" 
            onClick={() => {
              // Implementation for adding stocks to portfolio
              console.log('Adding stocks to portfolio:', selectedStocks);
              setPortfolioDialogOpen(false);
              setSelectedStocks([]);
              // Show success message or redirect
            }}
            disabled={selectedStocks.length === 0}
          >
            Add to Portfolio
          </button>
        </div>
      </div>
    </div>
  );
};

export default AdvancedScreener;