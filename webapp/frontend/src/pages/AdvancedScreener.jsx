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
        <Box sx={{ py: 3 }}>
          {children}
        </Box>
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
    <Container maxWidth="xl" sx={{ py: 3 }}>
      {/* Enhanced Header */}
      <Box display="flex" alignItems="center" justifyContent="between" mb={3}>
        <Box>
          <Typography variant="h4" gutterBottom sx={{ fontWeight: 700, display: 'flex', alignItems: 'center' }}>
            <Analytics sx={{ mr: 2, color: 'primary.main' }} />
            Advanced Stock Screener
          </Typography>
          <Typography variant="body1" color="text.secondary">
            Professional-grade stock screening with multi-factor analysis and real-time scoring
          </Typography>
          <Box display="flex" gap={1} mt={1}>
            <Chip label="Multi-Factor Analysis" color="primary" size="small" variant="outlined" />
            <Chip label="Real-Time Scoring" color="success" size="small" variant="outlined" />
            <Chip label="Portfolio Integration" color="info" size="small" variant="outlined" />
            {isAuthenticated && <Chip label="Cloud Sync" color="secondary" size="small" variant="outlined" />}
          </Box>
        </Box>

        <Box display="flex" alignItems="center" gap={2}>
          {/* Authentication Status */}
          {authLoading ? (
            <CircularProgress size={24} />
          ) : isAuthenticated ? (
            <Box display="flex" alignItems="center" gap={1}>
              <Person color="primary" />
              <Typography variant="body2" color="primary">
                {user?.username || user?.email || 'User'}
              </Typography>
            </Box>
          ) : (
            <Chip label="Guest Mode" color="warning" size="small" variant="outlined" />
          )}

          {/* Quick Actions */}
          <Badge badgeContent={savedScreens.length} color="primary">
            <Button
              variant="outlined"
              startIcon={<FolderOpen />}
              onClick={() => setActiveTab(2)}
              size="small"
            >
              My Screens
            </Button>
          </Badge>

          <Button
            variant="outlined"
            startIcon={<Save />}
            onClick={() => setSaveDialogOpen(true)}
            size="small"
            disabled={!filteredAndSortedResults.length}
          >
            Save Screen
          </Button>

          <Button
            variant="outlined"
            startIcon={<Download />}
            onClick={exportResults}
            size="small"
            disabled={!filteredAndSortedResults.length}
          >
            Export
          </Button>

          <Button
            variant="outlined"
            startIcon={<Refresh />}
            onClick={runScreen}
            size="small"
            disabled={loading || !results.length}
          >
            Refresh
          </Button>

          <FormControlLabel
            control={
              <Switch
                checked={autoRefresh}
                onChange={(e) => setAutoRefresh(e.target.checked)}
                size="small"
              />
            }
            label="Auto-refresh"
            sx={{ ml: 1 }}
          />

          {autoRefresh && (
            <TextField
              select
              value={refreshInterval}
              onChange={(e) => setRefreshInterval(Number(e.target.value))}
              size="small"
              sx={{ ml: 1, minWidth: 80 }}
            >
              <MenuItem value={10}>10s</MenuItem>
              <MenuItem value={30}>30s</MenuItem>
              <MenuItem value={60}>1m</MenuItem>
              <MenuItem value={300}>5m</MenuItem>
            </TextField>
          )}
        </Box>
      </Box>

      {/* Screen Statistics */}
      {filteredAndSortedResults.length > 0 && (
        <Card sx={{ mb: 3, bgcolor: 'primary.dark', color: 'primary.contrastText' }}>
          <CardContent sx={{ py: 2 }}>
            <Box display="flex" alignItems="center" justifyContent="between">
              <Box display="flex" alignItems="center" gap={4}>
                <Box>
                  <Typography variant="h6" fontWeight="bold">
                    {filteredAndSortedResults.length} Stocks Found
                  </Typography>
                  <Typography variant="body2" sx={{ opacity: 0.8 }}>
                    Average Composite Score: {(filteredAndSortedResults.reduce((sum, stock) => sum + stock.scores.composite, 0) / filteredAndSortedResults.length).toFixed(1)}
                  </Typography>
                </Box>
                
                <Box display="flex" gap={3}>
                  <Box textAlign="center">
                    <Typography variant="body2" sx={{ opacity: 0.8 }}>High Quality (80+)</Typography>
                    <Typography variant="h6" fontWeight="bold">
                      {filteredAndSortedResults.filter(s => s.scores.quality >= 80).length}
                    </Typography>
                  </Box>
                  <Box textAlign="center">
                    <Typography variant="body2" sx={{ opacity: 0.8 }}>Growth Leaders (70+)</Typography>
                    <Typography variant="h6" fontWeight="bold">
                      {filteredAndSortedResults.filter(s => s.scores.growth >= 70).length}
                    </Typography>
                  </Box>
                  <Box textAlign="center">
                    <Typography variant="body2" sx={{ opacity: 0.8 }}>Selected</Typography>
                    <Typography variant="h6" fontWeight="bold">
                      {selectedStocks.length}
                    </Typography>
                  </Box>
                </Box>
              </Box>
              
              <Box display="flex" alignItems="center" gap={2}>
                {selectedStocks.length > 0 && (
                  <Box display="flex" gap={1}>
                    <Button
                      variant="contained"
                      startIcon={<Compare />}
                      onClick={handleCompareStocks}
                      size="small"
                      disabled={selectedStocks.length < 2}
                    >
                      Compare ({selectedStocks.length})
                    </Button>
                    <Button
                      variant="contained"
                      startIcon={<AddShoppingCart />}
                      onClick={() => handleAddToPortfolio(selectedStocks)}
                      size="small"
                    >
                      Add to Portfolio
                    </Button>
                  </Box>
                )}
              </Box>
            </Box>
          </CardContent>
        </Card>
      )}

      {/* Preset Screens */}
      {presetScreens.length > 0 && (
        <Card sx={{ mb: 3 }}>
          <CardHeader
            title="Quick Preset Screens"
            subheader="Get started with professionally designed screening strategies"
          />
          <CardContent>
            <Grid container spacing={2}>
              {presetScreens.map((preset) => (
                <Grid item xs={12} sm={6} md={3} key={preset.id}>
                  <Card 
                    variant="outlined" 
                    sx={{ 
                      cursor: 'pointer', 
                      '&:hover': { boxShadow: 2 },
                      transition: 'all 0.2s'
                    }}
                    onClick={() => loadPresetScreen(preset)}
                  >
                    <CardContent sx={{ textAlign: 'center', p: 2 }}>
                      <Typography variant="h6" sx={{ fontWeight: 600, mb: 1 }}>
                        {preset.name}
                      </Typography>
                      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                        {preset.description}
                      </Typography>
                      <Button 
                        variant="outlined" 
                        size="small" 
                        startIcon={<PlaylistAdd />}
                      >
                        Apply Screen
                      </Button>
                    </CardContent>
                  </Card>
                </Grid>
              ))}
            </Grid>
          </CardContent>
        </Card>
      )}

      <Tabs value={activeTab} onChange={(e, v) => setActiveTab(v)} sx={{ mb: 3 }}>
        <Tab label="Screening Criteria" icon={<FilterList />} />
        <Tab label={`Results (${results.length})`} icon={<Assessment />} />
        <Tab label="Saved Screens" icon={<Save />} />
      </Tabs>

      <TabPanel value={activeTab} index={0}>
        <Grid container spacing={3}>
          <Grid item xs={12} md={8}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Score Criteria
                </Typography>
                
                <Grid container spacing={3}>
                  {Object.entries(screenCriteria).filter(([key]) => 
                    ['quality', 'growth', 'value', 'momentum', 'sentiment', 'positioning'].includes(key)
                  ).map(([key, value]) => (
                    <Grid item xs={12} sm={6} key={key}>
                      <Typography variant="body2" sx={{ mb: 1, textTransform: 'capitalize' }}>
                        {key} Score: {value[0]} - {value[1]}
                      </Typography>
                      <Slider
                        value={value}
                        onChange={(e, newValue) => setScreenCriteria(prev => ({ ...prev, [key]: newValue }))}
                        valueLabelDisplay="auto"
                        min={0}
                        max={100}
                        color="primary"
                        sx={{ mb: 2 }}
                      />
                    </Grid>
                  ))}
                </Grid>
              </CardContent>
            </Card>

            <Card sx={{ mt: 3 }}>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Financial Metrics
                </Typography>
                
                <Grid container spacing={3}>
                  <Grid item xs={12} sm={6}>
                    <Typography variant="body2" sx={{ mb: 1 }}>
                      Dividend Yield: {screenCriteria.dividendYield[0]}% - {screenCriteria.dividendYield[1]}%
                    </Typography>
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
                  </Grid>
                  
                  <Grid item xs={12} sm={6}>
                    <Typography variant="body2" sx={{ mb: 1 }}>
                      P/E Ratio: {screenCriteria.pe[0]} - {screenCriteria.pe[1]}
                    </Typography>
                    <Slider
                      value={screenCriteria.pe}
                      onChange={(e, newValue) => setScreenCriteria(prev => ({ ...prev, pe: newValue }))}
                      valueLabelDisplay="auto"
                      min={0}
                      max={50}
                      color="secondary"
                      sx={{ mb: 2 }}
                    />
                  </Grid>
                  
                  <Grid item xs={12} sm={6}>
                    <Typography variant="body2" sx={{ mb: 1 }}>
                      P/B Ratio: {screenCriteria.pb[0]} - {screenCriteria.pb[1]}
                    </Typography>
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
                  </Grid>
                  
                  <Grid item xs={12} sm={6}>
                    <Typography variant="body2" sx={{ mb: 1 }}>
                      ROE: {screenCriteria.roe[0]}% - {screenCriteria.roe[1]}%
                    </Typography>
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
                  </Grid>
                </Grid>
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} md={4}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Market Filters
                </Typography>
                
                <FormControl fullWidth sx={{ mb: 2 }}>
                  <InputLabel>Market Cap</InputLabel>
                  <Select
                    value={screenCriteria.marketCap}
                    onChange={(e) => setScreenCriteria(prev => ({ ...prev, marketCap: e.target.value }))}
                  >
                    <MenuItem value="any">Any</MenuItem>
                    <MenuItem value="mega_cap">Mega Cap (&gt;$200B)</MenuItem>
                    <MenuItem value="large_cap">Large Cap ($10B-$200B)</MenuItem>
                    <MenuItem value="mid_cap">Mid Cap ($2B-$10B)</MenuItem>
                    <MenuItem value="small_cap">Small Cap ($300M-$2B)</MenuItem>
                    <MenuItem value="micro_cap">Micro Cap (&lt;$300M)</MenuItem>
                  </Select>
                </FormControl>

                <FormControl fullWidth sx={{ mb: 2 }}>
                  <InputLabel>Sector</InputLabel>
                  <Select
                    value={screenCriteria.sector}
                    onChange={(e) => setScreenCriteria(prev => ({ ...prev, sector: e.target.value }))}
                  >
                    <MenuItem value="any">Any Sector</MenuItem>
                    {sectors.map((sector) => (
                      <MenuItem key={sector.sector} value={sector.sector}>
                        {sector.sector} ({sector.count} stocks)
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>

                <FormControl fullWidth sx={{ mb: 3 }}>
                  <InputLabel>Exchange</InputLabel>
                  <Select
                    value={screenCriteria.exchange}
                    onChange={(e) => setScreenCriteria(prev => ({ ...prev, exchange: e.target.value }))}
                  >
                    <MenuItem value="any">Any Exchange</MenuItem>
                    <MenuItem value="NYSE">NYSE</MenuItem>
                    <MenuItem value="NASDAQ">NASDAQ</MenuItem>
                  </Select>
                </FormControl>

                <Button
                  variant="contained"
                  color="primary"
                  fullWidth
                  size="large"
                  onClick={runScreen}
                  disabled={loading}
                  startIcon={loading ? <CircularProgress size={20} /> : <Search />}
                  sx={{ mb: 2 }}
                >
                  {loading ? 'Screening...' : 'Run Screen'}
                </Button>

                <Button
                  variant="outlined"
                  fullWidth
                  onClick={() => setSaveDialogOpen(true)}
                  startIcon={<Save />}
                  sx={{ mb: 1 }}
                >
                  Save Screen
                </Button>

                <Button
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
                </Button>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </TabPanel>

      <TabPanel value={activeTab} index={1}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
          <Typography variant="h6">
            Screening Results ({results.length} stocks found)
          </Typography>
          {results.length > 0 && (
            <Button
              variant="outlined"
              startIcon={<Download />}
              onClick={exportResults}
            >
              Export CSV
            </Button>
          )}
        </Box>

        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}

        {results.length === 0 && !error ? (
          <Alert severity="info">
            No results to display. Run a screen to see matching stocks.
          </Alert>
        ) : !error && (
          <Card>
            <TableContainer>
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell>Symbol</TableCell>
                    <TableCell>Company</TableCell>
                    <TableCell align="center">Quality</TableCell>
                    <TableCell align="center">Growth</TableCell>
                    <TableCell align="center">Value</TableCell>
                    <TableCell align="center">Momentum</TableCell>
                    <TableCell align="center">Sentiment</TableCell>
                    <TableCell align="center">Composite</TableCell>
                    <TableCell align="right">Price</TableCell>
                    <TableCell align="right">P/E</TableCell>
                    <TableCell align="right">P/B</TableCell>
                    <TableCell align="right">Market Cap</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {results
                    .slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage)
                    .map((stock) => (
                    <TableRow key={stock.symbol} hover>
                      <TableCell>
                        <Typography variant="body2" fontWeight="bold">
                          {stock.symbol}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2">
                          {stock.company}
                        </Typography>
                      </TableCell>
                      {['quality', 'growth', 'value', 'momentum', 'sentiment'].map((metric) => (
                        <TableCell key={metric} align="center">
                          <Chip
                            label={stock.scores[metric]}
                            color={getScoreColor(stock.scores[metric])}
                            size="small"
                            icon={getScoreIcon(stock.scores[metric])}
                          />
                        </TableCell>
                      ))}
                      <TableCell align="center">
                        <Chip
                          label={stock.scores.composite}
                          color={getScoreColor(stock.scores.composite)}
                          variant="filled"
                        />
                      </TableCell>
                      <TableCell align="right">
                        {formatCurrency(stock.price)}
                      </TableCell>
                      <TableCell align="right">
                        {stock.pe ? formatNumber(stock.pe) : 'N/A'}
                      </TableCell>
                      <TableCell align="right">
                        {stock.pb ? formatNumber(stock.pb) : 'N/A'}
                      </TableCell>
                      <TableCell align="right">
                        {formatCurrency(stock.marketCap, 0)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
            <TablePagination
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
          </Card>
        )}
      </TabPanel>

      <TabPanel value={activeTab} index={2}>
        <Typography variant="h6" gutterBottom>
          Saved Screening Strategies
        </Typography>
        
        <Grid container spacing={2}>
          {savedScreens.map((screen) => (
            <Grid item xs={12} sm={6} md={4} key={screen.id}>
              <Card>
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    {screen.name}
                  </Typography>
                  <Typography variant="body2" color="text.secondary" gutterBottom>
                    Quality: {screen.criteria.quality[0]}-{screen.criteria.quality[1]}
                  </Typography>
                  <Typography variant="body2" color="text.secondary" gutterBottom>
                    Growth: {screen.criteria.growth[0]}-{screen.criteria.growth[1]}
                  </Typography>
                  <Button
                    variant="outlined"
                    size="small"
                    onClick={() => loadScreen(screen.criteria)}
                    sx={{ mt: 1 }}
                  >
                    Load Screen
                  </Button>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      </TabPanel>

      {/* Save Screen Dialog */}
      <Dialog open={saveDialogOpen} onClose={() => setSaveDialogOpen(false)}>
        <DialogTitle>Save Screening Strategy</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            label="Screen Name"
            fullWidth
            variant="outlined"
            value={screenName}
            onChange={(e) => setScreenName(e.target.value)}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSaveDialogOpen(false)}>Cancel</Button>
          <Button onClick={saveScreen} variant="contained">Save</Button>
        </DialogActions>
      </Dialog>

      {/* Stock Comparison Dialog */}
      <Dialog 
        open={compareDialogOpen} 
        onClose={() => setCompareDialogOpen(false)}
        maxWidth="lg"
        fullWidth
      >
        <DialogTitle>
          <Box display="flex" alignItems="center" gap={1}>
            <Compare />
            Stock Comparison
          </Box>
        </DialogTitle>
        <DialogContent>
          {selectedStocks.length > 0 ? (
            <Box sx={{ mt: 2 }}>
              <Grid container spacing={2}>
                {selectedStocks.map((symbol) => {
                  const stock = mockResults.find(s => s.symbol === symbol);
                  if (!stock) return null;
                  
                  return (
                    <Grid item xs={12} md={6} lg={4} key={symbol}>
                      <Card>
                        <CardHeader 
                          title={stock.symbol}
                          subheader={stock.company}
                          avatar={
                            <Box sx={{ 
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
                            </Box>
                          }
                        />
                        <CardContent>
                          <Box sx={{ mb: 2 }}>
                            <Typography variant="h6" color="primary">
                              {formatCurrency(stock.price)}
                            </Typography>
                            <Typography variant="body2" color="text.secondary">
                              {stock.sector} • {formatCurrency(stock.marketCap, 0)}
                            </Typography>
                          </Box>
                          
                          <Grid container spacing={1} sx={{ mb: 2 }}>
                            <Grid item xs={6}>
                              <Typography variant="body2">P/E Ratio</Typography>
                              <Typography variant="body1" fontWeight="bold">
                                {stock.pe || 'N/A'}
                              </Typography>
                            </Grid>
                            <Grid item xs={6}>
                              <Typography variant="body2">P/B Ratio</Typography>
                              <Typography variant="body1" fontWeight="bold">
                                {stock.pb || 'N/A'}
                              </Typography>
                            </Grid>
                            <Grid item xs={6}>
                              <Typography variant="body2">ROE</Typography>
                              <Typography variant="body1" fontWeight="bold">
                                {stock.roe ? formatPercentage(stock.roe) : 'N/A'}
                              </Typography>
                            </Grid>
                            <Grid item xs={6}>
                              <Typography variant="body2">Dividend</Typography>
                              <Typography variant="body1" fontWeight="bold">
                                {stock.dividendYield ? formatPercentage(stock.dividendYield) : 'N/A'}
                              </Typography>
                            </Grid>
                          </Grid>

                          <Divider sx={{ my: 2 }} />
                          
                          <Typography variant="subtitle2" gutterBottom>
                            Score Breakdown
                          </Typography>
                          <Grid container spacing={1}>
                            {Object.entries(stock.scores).filter(([key]) => key !== 'composite').map(([key, value]) => (
                              <Grid item xs={6} key={key}>
                                <Box display="flex" alignItems="center" gap={1}>
                                  <Typography variant="body2" sx={{ textTransform: 'capitalize' }}>
                                    {key}:
                                  </Typography>
                                  <Chip 
                                    label={value}
                                    size="small"
                                    color={getScoreColor(value)}
                                  />
                                </Box>
                              </Grid>
                            ))}
                          </Grid>
                        </CardContent>
                      </Card>
                    </Grid>
                  );
                })}
              </Grid>
            </Box>
          ) : (
            <Typography>No stocks selected for comparison</Typography>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCompareDialogOpen(false)}>Close</Button>
          <Button 
            variant="contained" 
            onClick={() => handleAddToPortfolio(selectedStocks)}
            disabled={selectedStocks.length === 0}
          >
            Add All to Portfolio
          </Button>
        </DialogActions>
      </Dialog>

      {/* Portfolio Integration Dialog */}
      <Dialog 
        open={portfolioDialogOpen} 
        onClose={() => setPortfolioDialogOpen(false)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>
          <Box display="flex" alignItems="center" gap={1}>
            <AddShoppingCart />
            Add to Portfolio
          </Box>
        </DialogTitle>
        <DialogContent>
          <Box sx={{ mt: 2 }}>
            <Typography variant="body1" gutterBottom>
              You're about to add {selectedStocks.length} stock{selectedStocks.length > 1 ? 's' : ''} to your portfolio:
            </Typography>
            
            <Box sx={{ my: 2 }}>
              {selectedStocks.map((symbol) => {
                const stock = mockResults.find(s => s.symbol === symbol);
                if (!stock) return null;
                
                return (
                  <Box key={symbol} sx={{ 
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
                    <Box sx={{ 
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
                    </Box>
                    <Box sx={{ flex: 1 }}>
                      <Typography variant="subtitle1" fontWeight="bold">
                        {stock.symbol}
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        {stock.company}
                      </Typography>
                    </Box>
                    <Box sx={{ textAlign: 'right' }}>
                      <Typography variant="h6" color="primary">
                        {formatCurrency(stock.price)}
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        {stock.sector}
                      </Typography>
                    </Box>
                  </Box>
                );
              })}
            </Box>

            <Alert severity="info" sx={{ mt: 2 }}>
              {isAuthenticated ? (
                <Box>
                  <Typography variant="body2">
                    These stocks will be added to your portfolio for tracking. You can manage position sizes and set alerts from your Portfolio page.
                  </Typography>
                  <Typography variant="body2" sx={{ mt: 1 }}>
                    <strong>Logged in as:</strong> {user?.email}
                  </Typography>
                </Box>
              ) : (
                <Box>
                  <Typography variant="body2">
                    You're not signed in. These stocks will be saved locally and won't sync across devices.
                  </Typography>
                  <Typography variant="body2" sx={{ mt: 1 }}>
                    <strong>Tip:</strong> Sign in to sync your portfolio across all devices.
                  </Typography>
                </Box>
              )}
            </Alert>

            {isAuthenticated && (
              <Box sx={{ mt: 2 }}>
                <FormControl fullWidth variant="outlined">
                  <InputLabel>Portfolio</InputLabel>
                  <Select
                    value="main"
                    label="Portfolio"
                  >
                    <MenuItem value="main">Main Portfolio</MenuItem>
                    <MenuItem value="watchlist">Watchlist</MenuItem>
                    <MenuItem value="research">Research List</MenuItem>
                  </Select>
                </FormControl>
              </Box>
            )}
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPortfolioDialogOpen(false)}>
            Cancel
          </Button>
          <Button 
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
          </Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
};

export default AdvancedScreener;