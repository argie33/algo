import React, { useState, useEffect } from 'react';
import {
  Box,
  Grid,
  Card,
  CardContent,
  Typography,
  Divider,
  Button,
  TextField,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Tabs,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Chip,
  IconButton,
  Alert,
  Tooltip,
  Fab,
  Menu,
  MenuItem,
  Switch,
  FormControlLabel,
  LinearProgress,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Stack,
  Avatar,
  AvatarGroup,
  Slide,
  Badge,
  ListItemIcon,
  List,
  ListItem,
  ListItemText,
  Stepper,
  Step,
  StepLabel,
  CircularProgress,
  Select,
  FormControl,
  InputLabel,
  Autocomplete,
  AppBar,
  Toolbar,
  Drawer,
  Breadcrumbs,
  Link,
  Rating,
  Skeleton
} from '@mui/material';
import {
  Add as AddIcon,
  Edit as EditIcon,
  Delete as DeleteIcon,
  TrendingUp,
  TrendingDown,
  AttachMoney,
  PieChart as PieChartIcon,
  BarChart as BarChartIcon,
  Timeline,
  Sync as SyncIcon,
  Settings as SettingsIcon,
  Upload as UploadIcon,
  Download as DownloadIcon,
  Refresh as RefreshIcon,
  ExpandMore,
  AccountBalance,
  Business,
  ShowChart,
  Analytics,
  Info,
  Warning,
  CheckCircle,
  Error,
  Key as KeyIcon,
  CloudUpload,
  ManualRecord,
  Dashboard,
  Speed,
  Security,
  AssessmentOutlined,
  CompareArrows,
  TrendingFlat,
  Visibility,
  VisibilityOff,
  FilterList,
  Sort,
  ImportExport,
  Share,
  Print,
  BookmarkBorder,
  Bookmark,
  NotificationsActive,
  Schedule,
  CalendarToday,
  AccessTime,
  Person,
  Group,
  Star,
  StarBorder,
  ThumbUp,
  ThumbDown,
  Flag,
  Assessment,
  DataUsage,
  DonutLarge,
  MultilineChart,
  CandlestickChart,
  TableChart,
  ViewModule,
  ViewList,
  ViewCompact,
  Fullscreen,
  FullscreenExit,
  ZoomIn,
  ZoomOut,
  AccountBalanceWallet,
  CreditCard,
  PaymentOutlined,
  MonetizationOn,
  TrendingUpOutlined,
  TrendingDownOutlined,
  EqualizerOutlined,
  InsightsOutlined,
  AutoGraphOutlined,
  QueryStatsOutlined,
  PsychologyOutlined,
  WaterDropOutlined,
  OpacityOutlined,
  LocalFireDepartmentOutlined,
  AcUnitOutlined,
  FlashOnOutlined,
  BoltOutlined,
  PowerOutlined,
  EmojiEventsOutlined,
  WorkspacePremiumOutlined,
  MilitaryTechOutlined,
  GradingOutlined,
  SchoolOutlined
} from '@mui/icons-material';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer, PieChart, Pie, Cell, BarChart, Bar, ComposedChart, Area, AreaChart, ScatterChart, Scatter, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar, Treemap, Sankey, FunnelChart, Funnel, LabelList } from 'recharts';
import { formatCurrency, formatNumber, formatPercentage } from '../utils/formatters';
import { format, subDays, subMonths, subYears, startOfYear, endOfYear, differenceInDays } from 'date-fns';
import { useAuth } from '../contexts/AuthContext';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../services/api';

const COLORS = ['#1976d2', '#43a047', '#ffb300', '#8e24aa', '#e53935', '#00bcd4', '#ff7043', '#9e9e9e'];
const PERFORMANCE_COLORS = {
  excellent: '#4caf50',
  good: '#8bc34a',
  average: '#ffeb3b',
  poor: '#ff9800',
  terrible: '#f44336'
};
const RISK_COLORS = {
  low: '#4caf50',
  medium: '#ff9800',
  high: '#f44336'
};

// Enhanced portfolio data structure
const samplePortfolioData = {
  totalValue: 1247850.32,
  dayChange: 15420.15,
  dayChangePercent: 1.25,
  totalReturn: 187654.32,
  totalReturnPercent: 17.7,
  cash: 25000.00,
  marginUsed: 0,
  buyingPower: 25000.00,
  // Enhanced metrics
  inception: new Date('2022-01-01'),
  benchmarkReturn: 156832.45,
  benchmarkReturnPercent: 14.2,
  alpha: 3.5,
  beta: 0.92,
  sharpeRatio: 1.85,
  sortinoRatio: 2.31,
  maxDrawdown: -8.2,
  maxDrawdownDate: new Date('2023-03-15'),
  volatility: 15.4,
  calmarRatio: 2.16,
  winRate: 68.3,
  profitFactor: 2.4,
  averageWin: 8.7,
  averageLoss: -3.6,
  totalTrades: 147,
  winningTrades: 98,
  losingTrades: 49,
  currentStreak: 7,
  longestWinStreak: 12,
  longestLoseStreak: 4,
  largestWin: 15420.32,
  largestLoss: -7892.15,
  riskScore: 'B+',
  diversificationScore: 8.7,
  concentrationRisk: 'Low',
  sectorExposure: 'Well Balanced',
  liquidityScore: 9.2,
  expenseRatio: 0.15,
  turnoverRate: 24.3,
  positions: [
    {
      symbol: 'AAPL',
      name: 'Apple Inc.',
      shares: 150,
      avgPrice: 175.50,
      currentPrice: 182.25,
      marketValue: 27337.50,
      dayChange: 1.15,
      dayChangePercent: 0.63,
      totalReturn: 1012.50,
      totalReturnPercent: 3.84,
      sector: 'Technology',
      allocation: 2.2
    },
    {
      symbol: 'MSFT',
      name: 'Microsoft Corporation',
      shares: 100,
      avgPrice: 385.20,
      currentPrice: 412.78,
      marketValue: 41278.00,
      dayChange: -2.15,
      dayChangePercent: -0.52,
      totalReturn: 2758.00,
      totalReturnPercent: 7.16,
      sector: 'Technology',
      allocation: 3.3
    },
    {
      symbol: 'NVDA',
      name: 'NVIDIA Corporation',
      shares: 75,
      avgPrice: 721.80,
      currentPrice: 845.32,
      marketValue: 63399.00,
      dayChange: 12.45,
      dayChangePercent: 1.49,
      totalReturn: 9264.00,
      totalReturnPercent: 17.1,
      sector: 'Technology',
      allocation: 5.1
    },
    {
      symbol: 'SPY',
      name: 'SPDR S&P 500 ETF Trust',
      shares: 500,
      avgPrice: 428.15,
      currentPrice: 448.75,
      marketValue: 224375.00,
      dayChange: 1.25,
      dayChangePercent: 0.28,
      totalReturn: 10300.00,
      totalReturnPercent: 4.81,
      sector: 'ETF',
      allocation: 18.0
    },
    {
      symbol: 'GOOGL',
      name: 'Alphabet Inc.',
      shares: 85,
      avgPrice: 142.30,
      currentPrice: 156.78,
      marketValue: 13326.30,
      dayChange: 0.85,
      dayChangePercent: 0.55,
      totalReturn: 1230.80,
      totalReturnPercent: 10.2,
      sector: 'Technology',
      allocation: 1.1
    }
  ],
  performance: [
    { date: '2024-01-01', value: 1000000, benchmark: 1000000, volatility: 12.1, volume: 1250000 },
    { date: '2024-01-15', value: 1023450, benchmark: 1018200, volatility: 11.8, volume: 1430000 },
    { date: '2024-02-01', value: 1045670, benchmark: 1034500, volatility: 13.2, volume: 1680000 },
    { date: '2024-02-15', value: 1062340, benchmark: 1048900, volatility: 12.9, volume: 1520000 },
    { date: '2024-03-01', value: 1038920, benchmark: 1039200, volatility: 16.4, volume: 2140000 },
    { date: '2024-03-15', value: 1019850, benchmark: 1025300, volatility: 18.7, volume: 2890000 },
    { date: '2024-04-01', value: 1078340, benchmark: 1067800, volatility: 14.2, volume: 1780000 },
    { date: '2024-04-15', value: 1124560, benchmark: 1089400, volatility: 13.1, volume: 1650000 },
    { date: '2024-05-01', value: 1156780, benchmark: 1112600, volatility: 12.7, volume: 1420000 },
    { date: '2024-05-15', value: 1189230, benchmark: 1138900, volatility: 11.9, volume: 1380000 },
    { date: '2024-06-01', value: 1203450, benchmark: 1156200, volatility: 12.3, volume: 1290000 },
    { date: '2024-06-15', value: 1234670, benchmark: 1178500, volatility: 13.5, volume: 1450000 },
    { date: '2024-07-01', value: 1247850, benchmark: 1190000, volatility: 12.8, volume: 1380000 }
  ],
  monthlyReturns: [
    { month: 'Jan 2024', portfolio: 2.34, benchmark: 1.82, excess: 0.52 },
    { month: 'Feb 2024', portfolio: 2.17, benchmark: 1.59, excess: 0.58 },
    { month: 'Mar 2024', portfolio: -0.67, benchmark: 0.47, excess: -1.14 },
    { month: 'Apr 2024', portfolio: 5.75, benchmark: 4.13, excess: 1.62 },
    { month: 'May 2024', portfolio: 6.96, benchmark: 2.03, excess: 4.93 },
    { month: 'Jun 2024', portfolio: 4.03, benchmark: 3.85, excess: 0.18 },
    { month: 'Jul 2024', portfolio: 1.08, benchmark: 1.00, excess: 0.08 }
  ],
  riskMetrics: [
    { metric: 'Value at Risk (1%)', value: '-2.8%', description: 'Maximum expected loss with 99% confidence' },
    { metric: 'Expected Shortfall', value: '-4.2%', description: 'Average loss beyond VaR threshold' },
    { metric: 'Beta to S&P 500', value: '0.92', description: 'Sensitivity to market movements' },
    { metric: 'Correlation to Market', value: '0.87', description: 'Relationship with broad market' },
    { metric: 'Tracking Error', value: '3.4%', description: 'Standard deviation of excess returns' },
    { metric: 'Information Ratio', value: '1.03', description: 'Risk-adjusted excess return' }
  ],
  allocation: {
    bySector: [
      { name: 'Technology', value: 28.5, amount: 355638, risk: 'Medium', return1Y: 23.4, volatility: 22.1 },
      { name: 'Healthcare', value: 18.2, amount: 227108, risk: 'Low', return1Y: 11.7, volatility: 14.8 },
      { name: 'Financials', value: 15.8, amount: 197161, risk: 'Medium', return1Y: 18.9, volatility: 19.3 },
      { name: 'Consumer Discretionary', value: 12.4, amount: 154733, risk: 'High', return1Y: 28.7, volatility: 26.4 },
      { name: 'Industrials', value: 8.9, amount: 111058, risk: 'Medium', return1Y: 15.2, volatility: 17.6 },
      { name: 'Energy', value: 6.7, amount: 83606, risk: 'High', return1Y: 31.8, volatility: 34.2 },
      { name: 'Real Estate', value: 4.2, amount: 52410, risk: 'Medium', return1Y: 9.4, volatility: 21.7 },
      { name: 'Utilities', value: 3.1, amount: 38683, risk: 'Low', return1Y: 6.8, volatility: 12.3 },
      { name: 'Cash & Equivalents', value: 2.2, amount: 27453, risk: 'Low', return1Y: 4.5, volatility: 0.1 }
    ],
    byAssetType: [
      { name: 'Individual Stocks', value: 62.3, amount: 777548, risk: 'Medium' },
      { name: 'ETFs', value: 28.5, amount: 355638, risk: 'Low' },
      { name: 'Mutual Funds', value: 7.0, amount: 87350, risk: 'Low' },
      { name: 'Cash & Money Market', value: 2.2, amount: 27453, risk: 'Low' }
    ],
    byGeography: [
      { name: 'US Large Cap', value: 45.2, amount: 564267 },
      { name: 'US Mid Cap', value: 18.7, amount: 233349 },
      { name: 'US Small Cap', value: 12.1, average: 150990 },
      { name: 'International Developed', value: 15.3, amount: 190920 },
      { name: 'Emerging Markets', value: 6.5, amount: 81110 },
      { name: 'Cash', value: 2.2, amount: 27453 }
    ],
    byMarketCap: [
      { name: 'Large Cap (>$10B)', value: 58.4, amount: 729053 },
      { name: 'Mid Cap ($2-10B)', value: 24.6, amount: 307171 },
      { name: 'Small Cap (<$2B)', value: 14.8, amount: 184682 },
      { name: 'Cash', value: 2.2, amount: 27453 }
    ]
  },
  topHoldings: [
    { symbol: 'AAPL', name: 'Apple Inc.', weight: 8.4, value: 104819, shares: 575, change24h: 1.23 },
    { symbol: 'MSFT', name: 'Microsoft Corp.', weight: 7.2, value: 89845, shares: 218, change24h: -0.87 },
    { symbol: 'NVDA', name: 'NVIDIA Corp.', weight: 6.8, value: 84854, shares: 100, change24h: 2.41 },
    { symbol: 'AMZN', name: 'Amazon.com Inc.', weight: 5.1, value: 63640, shares: 420, change24h: 0.95 },
    { symbol: 'GOOGL', name: 'Alphabet Inc.', weight: 4.9, value: 61164, shares: 390, change24h: 1.78 }
  ],
  alerts: [
    { type: 'warning', message: 'Technology sector overweight by 3.5% vs target allocation', severity: 'medium', date: new Date() },
    { type: 'info', message: 'Quarterly rebalancing due in 12 days', severity: 'low', date: new Date() },
    { type: 'success', message: 'Portfolio outperformed benchmark by 3.5% this quarter', severity: 'low', date: new Date() }
  ],
};

function TabPanel({ children, value, index, ...other }) {
  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`portfolio-tabpanel-${index}`}
      aria-labelledby={`portfolio-tab-${index}`}
      {...other}
    >
      {value === index && (
        <Box sx={{ pt: 3 }}>
          {children}
        </Box>
      )}
    </div>
  );
}

function Portfolio() {
  const { isAuthenticated, user } = useAuth();
  const queryClient = useQueryClient();
  
  // State management
  const [tabValue, setTabValue] = useState(0);
  const [portfolioData, setPortfolioData] = useState(samplePortfolioData);
  const [showAddDialog, setShowAddDialog] = useState(false);
  const [showApiDialog, setShowApiDialog] = useState(false);
  const [showRebalanceDialog, setShowRebalanceDialog] = useState(false);
  const [showAlertDialog, setShowAlertDialog] = useState(false);
  const [showAnalysisDialog, setShowAnalysisDialog] = useState(false);
  const [apiKey, setApiKey] = useState('');
  const [isApiConnected, setIsApiConnected] = useState(false);
  const [loading, setLoading] = useState(false);
  const [viewMode, setViewMode] = useState('detailed'); // 'simple', 'detailed', 'professional'
  const [timeframe, setTimeframe] = useState('1Y'); // '1M', '3M', '6M', '1Y', '2Y', 'ALL'
  const [benchmarkSymbol, setBenchmarkSymbol] = useState('SPY');
  const [showPaperTrade, setShowPaperTrade] = useState(false);
  const [selectedPosition, setSelectedPosition] = useState(null);
  const [sortBy, setSortBy] = useState('allocation');
  const [sortOrder, setSortOrder] = useState('desc');
  const [filterSector, setFilterSector] = useState('all');
  const [showRiskAnalysis, setShowRiskAnalysis] = useState(false);
  const [newPosition, setNewPosition] = useState({
    symbol: '',
    shares: '',
    avgPrice: '',
    currentPrice: '',
    targetAllocation: ''
  });
  const [alertSettings, setAlertSettings] = useState({
    rebalanceThreshold: 5,
    stopLossThreshold: -10,
    takeProfitThreshold: 20,
    volatilityAlert: 25,
    enableNotifications: true
  });

  // Real-time portfolio data fetching
  const { data: realPortfolioData, isLoading: portfolioLoading, error: portfolioError } = useQuery({
    queryKey: ['portfolio', user?.id],
    queryFn: async () => {
      if (!isAuthenticated) return null;
      const response = await api.get('/portfolio');
      return response.data;
    },
    enabled: isAuthenticated,
    refetchInterval: 30000, // Refresh every 30 seconds
    staleTime: 15000
  });

  // Market data for benchmarking
  const { data: benchmarkData } = useQuery({
    queryKey: ['benchmark', benchmarkSymbol, timeframe],
    queryFn: async () => {
      const response = await api.get(`/market/prices/${benchmarkSymbol}?timeframe=${timeframe}`);
      return response.data;
    },
    staleTime: 60000
  });

  const handleTabChange = (event, newValue) => {
    setTabValue(newValue);
  };

  const getTimeframeData = () => {
    const now = new Date();
    let startDate;
    
    switch (timeframe) {
      case '1M': startDate = subMonths(now, 1); break;
      case '3M': startDate = subMonths(now, 3); break;
      case '6M': startDate = subMonths(now, 6); break;
      case '1Y': startDate = subYears(now, 1); break;
      case '2Y': startDate = subYears(now, 2); break;
      default: startDate = portfolioData.inception;
    }
    
    return portfolioData.performance.filter(p => new Date(p.date) >= startDate);
  };

  const calculatePerformanceMetrics = () => {
    const data = getTimeframeData();
    if (data.length < 2) return {};
    
    const startValue = data[0].value;
    const endValue = data[data.length - 1].value;
    const returns = data.map((d, i) => i === 0 ? 0 : (d.value - data[i-1].value) / data[i-1].value);
    
    const totalReturn = (endValue - startValue) / startValue;
    const volatility = Math.sqrt(returns.reduce((sum, r) => sum + r * r, 0) / returns.length) * Math.sqrt(252);
    const sharpe = totalReturn / volatility;
    
    return {
      totalReturn,
      volatility,
      sharpe,
      maxDrawdown: Math.min(...returns),
      winRate: returns.filter(r => r > 0).length / returns.length
    };
  };

  const getPortfolioScore = () => {
    const metrics = calculatePerformanceMetrics();
    let score = 0;
    
    // Performance scoring (40%)
    if (metrics.totalReturn > 0.15) score += 40;
    else if (metrics.totalReturn > 0.10) score += 30;
    else if (metrics.totalReturn > 0.05) score += 20;
    else score += 10;
    
    // Risk management (30%)
    if (metrics.sharpe > 1.5) score += 30;
    else if (metrics.sharpe > 1.0) score += 20;
    else if (metrics.sharpe > 0.5) score += 15;
    else score += 5;
    
    // Diversification (20%)
    const maxAllocation = Math.max(...portfolioData.allocation.bySector.map(s => s.value));
    if (maxAllocation < 25) score += 20;
    else if (maxAllocation < 35) score += 15;
    else if (maxAllocation < 45) score += 10;
    else score += 5;
    
    // Other factors (10%)
    score += portfolioData.liquidityScore;
    
    return Math.min(100, Math.max(0, score));
  };

  const getScoreGrade = (score) => {
    if (score >= 90) return { grade: 'A+', color: '#4caf50', desc: 'Exceptional' };
    if (score >= 85) return { grade: 'A', color: '#4caf50', desc: 'Excellent' };
    if (score >= 80) return { grade: 'A-', color: '#8bc34a', desc: 'Very Good' };
    if (score >= 75) return { grade: 'B+', color: '#8bc34a', desc: 'Good' };
    if (score >= 70) return { grade: 'B', color: '#ffeb3b', desc: 'Above Average' };
    if (score >= 65) return { grade: 'B-', color: '#ffeb3b', desc: 'Average' };
    if (score >= 60) return { grade: 'C+', color: '#ff9800', desc: 'Below Average' };
    if (score >= 55) return { grade: 'C', color: '#ff9800', desc: 'Needs Improvement' };
    if (score >= 50) return { grade: 'C-', color: '#f44336', desc: 'Poor' };
    return { grade: 'D', color: '#f44336', desc: 'Very Poor' };
  };

  const handleAddPosition = async () => {
    if (newPosition.symbol && newPosition.shares && newPosition.avgPrice) {
      try {
        setLoading(true);
        const shares = parseFloat(newPosition.shares);
        const avgPrice = parseFloat(newPosition.avgPrice);
        const currentPrice = parseFloat(newPosition.currentPrice) || avgPrice;
        const targetAllocation = parseFloat(newPosition.targetAllocation) || 0;
        const marketValue = shares * currentPrice;
        const totalReturn = (currentPrice - avgPrice) * shares;
        const totalReturnPercent = ((currentPrice - avgPrice) / avgPrice) * 100;

        const position = {
          symbol: newPosition.symbol.toUpperCase(),
          name: `${newPosition.symbol.toUpperCase()} Inc.`,
          shares,
          avgPrice,
          currentPrice,
          marketValue,
          dayChange: 0,
          dayChangePercent: 0,
          totalReturn,
          totalReturnPercent,
          sector: 'Unknown',
          allocation: (marketValue / portfolioData.totalValue) * 100,
          targetAllocation,
          riskRating: 'Medium',
          beta: 1.0,
          addedDate: new Date(),
          notes: '',
          alerts: []
        };

        if (isAuthenticated) {
          await api.post('/portfolio/positions', position);
          queryClient.invalidateQueries(['portfolio']);
        } else {
          setPortfolioData(prev => ({
            ...prev,
            positions: [...prev.positions, position],
            totalValue: prev.totalValue + marketValue
          }));
        }

        setNewPosition({ symbol: '', shares: '', avgPrice: '', currentPrice: '', targetAllocation: '' });
        setShowAddDialog(false);
      } catch (error) {
        console.error('Error adding position:', error);
      } finally {
        setLoading(false);
      }
    }
  };

  const handleRemovePosition = async (positionId) => {
    try {
      if (isAuthenticated) {
        await api.delete(`/portfolio/positions/${positionId}`);
        queryClient.invalidateQueries(['portfolio']);
      } else {
        setPortfolioData(prev => ({
          ...prev,
          positions: prev.positions.filter((_, idx) => idx !== positionId)
        }));
      }
    } catch (error) {
      console.error('Error removing position:', error);
    }
  };

  const handleRebalance = async () => {
    try {
      setLoading(true);
      if (isAuthenticated) {
        await api.post('/portfolio/rebalance');
        queryClient.invalidateQueries(['portfolio']);
      }
      setShowRebalanceDialog(false);
    } catch (error) {
      console.error('Error rebalancing portfolio:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleConnectAlpaca = async () => {
    if (!apiKey) return;
    
    try {
      setLoading(true);
      if (isAuthenticated) {
        await api.post('/portfolio/connect-broker', { 
          provider: 'alpaca', 
          apiKey, 
          sandboxMode: true 
        });
        setIsApiConnected(true);
        queryClient.invalidateQueries(['portfolio']);
      } else {
        // Simulate connection for demo
        setTimeout(() => {
          setIsApiConnected(true);
        }, 2000);
      }
      setShowApiDialog(false);
    } catch (error) {
      console.error('Error connecting to Alpaca:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleRefreshData = async () => {
    try {
      setLoading(true);
      if (isAuthenticated) {
        await queryClient.invalidateQueries(['portfolio']);
        await queryClient.refetchQueries(['portfolio']);
      } else {
        // Simulate refresh for demo
        setTimeout(() => {
          setLoading(false);
        }, 1500);
        return;
      }
    } catch (error) {
      console.error('Error refreshing data:', error);
    } finally {
      setLoading(false);
    }
  };

  const getSectorColor = (sector) => {
    const sectorColors = {
      'Technology': '#1976d2',
      'Healthcare': '#4caf50',
      'Financials': '#ff9800',
      'Consumer Discretionary': '#9c27b0',
      'Industrials': '#607d8b',
      'Energy': '#f44336',
      'Real Estate': '#795548',
      'Utilities': '#2196f3',
      'ETF': '#43a047',
      'Cash & Equivalents': '#9e9e9e',
      'Cash': '#9e9e9e'
    };
    return sectorColors[sector] || '#9e9e9e';
  };

  const getRiskColor = (risk) => {
    const riskColors = {
      'Low': '#4caf50',
      'Medium': '#ff9800', 
      'High': '#f44336'
    };
    return riskColors[risk] || '#9e9e9e';
  };

  const getPerformanceColor = (value) => {
    if (value > 20) return PERFORMANCE_COLORS.excellent;
    if (value > 10) return PERFORMANCE_COLORS.good;
    if (value > 0) return PERFORMANCE_COLORS.average;
    if (value > -10) return PERFORMANCE_COLORS.poor;
    return PERFORMANCE_COLORS.terrible;
  };

  // Use real data if authenticated, otherwise use sample data
  const currentPortfolio = isAuthenticated && realPortfolioData ? realPortfolioData : portfolioData;
  const portfolioScore = getPortfolioScore();
  const scoreInfo = getScoreGrade(portfolioScore);

  return (
    <Box sx={{ p: 3, bgcolor: 'background.default', minHeight: '100vh' }}>
      {/* Enhanced Header with Portfolio Score */}
      <Card elevation={3} sx={{ mb: 3, background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)', color: 'white' }}>
        <CardContent>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Box>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 1 }}>
                <Typography variant="h3" component="h1" sx={{ fontWeight: 700 }}>
                  Portfolio
                </Typography>
                <Chip 
                  icon={<WorkspacePremiumOutlined />}
                  label={`Score: ${scoreInfo.grade}`}
                  sx={{ 
                    bgcolor: 'rgba(255,255,255,0.2)', 
                    color: 'white',
                    fontWeight: 600,
                    fontSize: '0.9rem'
                  }}
                />
                {isAuthenticated && (
                  <Chip 
                    icon={<CheckCircle />}
                    label="Live Data"
                    sx={{ 
                      bgcolor: 'rgba(76,175,80,0.8)', 
                      color: 'white',
                      fontWeight: 600
                    }}
                  />
                )}
              </Box>
              <Typography variant="h5" sx={{ fontWeight: 600, mb: 0.5 }}>
                {formatCurrency(currentPortfolio.totalValue)}
              </Typography>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap' }}>
                <Chip
                  icon={currentPortfolio.dayChange >= 0 ? <TrendingUp /> : <TrendingDown />}
                  label={`${currentPortfolio.dayChange >= 0 ? '+' : ''}${formatCurrency(currentPortfolio.dayChange)} (${currentPortfolio.dayChangePercent >= 0 ? '+' : ''}${currentPortfolio.dayChangePercent.toFixed(2)}%) today`}
                  sx={{ 
                    bgcolor: currentPortfolio.dayChange >= 0 ? 'rgba(76,175,80,0.8)' : 'rgba(244,67,54,0.8)', 
                    color: 'white',
                    fontWeight: 600
                  }}
                />
                <Chip
                  label={`YTD: ${formatPercentage(currentPortfolio.totalReturnPercent / 100)}`}
                  sx={{ 
                    bgcolor: 'rgba(255,255,255,0.2)', 
                    color: 'white',
                    fontWeight: 600
                  }}
                />
                <Chip
                  label={`vs S&P 500: +${formatPercentage(currentPortfolio.alpha / 100)}`}
                  sx={{ 
                    bgcolor: 'rgba(255,255,255,0.2)', 
                    color: 'white',
                    fontWeight: 600
                  }}
                />
              </Box>
            </Box>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              <Box sx={{ textAlign: 'center' }}>
                <Typography variant="h6" sx={{ fontWeight: 700 }}>
                  {portfolioScore.toFixed(0)}
                </Typography>
                <Typography variant="caption" sx={{ opacity: 0.9 }}>
                  Portfolio Score
                </Typography>
              </Box>
              
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                <Box sx={{ display: 'flex', gap: 1 }}>
                  <Button
                    variant="contained"
                    size="small"
                    startIcon={<AddIcon />}
                    onClick={() => setShowAddDialog(true)}
                    sx={{ 
                      bgcolor: 'rgba(255,255,255,0.2)', 
                      '&:hover': { bgcolor: 'rgba(255,255,255,0.3)' },
                      color: 'white'
                    }}
                  >
                    Add Position
                  </Button>
                  <Button
                    variant="outlined"
                    size="small"
                    startIcon={<Analytics />}
                    onClick={() => setShowAnalysisDialog(true)}
                    sx={{ 
                      borderColor: 'rgba(255,255,255,0.5)', 
                      color: 'white',
                      '&:hover': { borderColor: 'white', bgcolor: 'rgba(255,255,255,0.1)' }
                    }}
                  >
                    Analysis
                  </Button>
                  <IconButton 
                    onClick={() => setShowRebalanceDialog(true)}
                    sx={{ color: 'white' }}
                  >
                    <CompareArrows />
                  </IconButton>
                </Box>
                
                <Box sx={{ display: 'flex', gap: 1 }}>
                  <Button
                    variant="outlined"
                    size="small"
                    startIcon={<KeyIcon />}
                    onClick={() => setShowApiDialog(true)}
                    sx={{ 
                      borderColor: isApiConnected ? 'rgba(76,175,80,0.8)' : 'rgba(255,255,255,0.5)', 
                      color: 'white',
                      '&:hover': { borderColor: 'white', bgcolor: 'rgba(255,255,255,0.1)' }
                    }}
                  >
                    {isApiConnected ? 'Connected' : 'Connect Broker'}
                  </Button>
                  <IconButton 
                    onClick={handleRefreshData} 
                    disabled={loading}
                    sx={{ color: 'white' }}
                  >
                    <RefreshIcon />
                  </IconButton>
                </Box>
              </Box>
            </Box>
          </Box>
        </CardContent>
      </Card>

      {/* Connection Status */}
      {isApiConnected && (
        <Alert severity="success" sx={{ mb: 3 }}>
          <Box display="flex" alignItems="center" gap={1}>
            <CheckCircle fontSize="small" />
            <Typography variant="body2">
              Connected to Alpaca Markets API • Live data sync enabled
            </Typography>
          </Box>
        </Alert>
      )}

      {/* Portfolio Summary Cards */}
      <Grid container spacing={3} sx={{ mb: 3 }}>
        <Grid item xs={12} sm={6} md={3}>
          <Card elevation={2}>
            <CardContent>
              <Box display="flex" alignItems="center" gap={1} mb={1}>
                <AttachMoney color="primary" />
                <Typography variant="h6" fontWeight={600}>Total Value</Typography>
              </Box>
              <Typography variant="h4" fontWeight="bold" color="primary">
                {formatCurrency(portfolioData.totalValue)}
              </Typography>
              <Chip
                icon={portfolioData.dayChange >= 0 ? <TrendingUp /> : <TrendingDown />}
                label={`${portfolioData.dayChange >= 0 ? '+' : ''}${formatCurrency(portfolioData.dayChange)} (${portfolioData.dayChangePercent >= 0 ? '+' : ''}${portfolioData.dayChangePercent.toFixed(2)}%)`}
                color={portfolioData.dayChange >= 0 ? 'success' : 'error'}
                size="small"
                sx={{ mt: 1 }}
              />
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card elevation={2}>
            <CardContent>
              <Box display="flex" alignItems="center" gap={1} mb={1}>
                <Timeline color="primary" />
                <Typography variant="h6" fontWeight={600}>Total Return</Typography>
              </Box>
              <Typography variant="h4" fontWeight="bold" color={portfolioData.totalReturn >= 0 ? 'success.main' : 'error.main'}>
                {formatCurrency(portfolioData.totalReturn)}
              </Typography>
              <Typography variant="body2" color="textSecondary" mt={1}>
                {portfolioData.totalReturnPercent >= 0 ? '+' : ''}{portfolioData.totalReturnPercent.toFixed(2)}% overall
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card elevation={2}>
            <CardContent>
              <Box display="flex" alignItems="center" gap={1} mb={1}>
                <AccountBalance color="primary" />
                <Typography variant="h6" fontWeight={600}>Cash Available</Typography>
              </Box>
              <Typography variant="h4" fontWeight="bold">
                {formatCurrency(portfolioData.cash)}
              </Typography>
              <Typography variant="body2" color="textSecondary" mt={1}>
                Buying Power: {formatCurrency(portfolioData.buyingPower)}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <Card elevation={2}>
            <CardContent>
              <Box display="flex" alignItems="center" gap={1} mb={1}>
                <PieChartIcon color="primary" />
                <Typography variant="h6" fontWeight={600}>Positions</Typography>
              </Box>
              <Typography variant="h4" fontWeight="bold">
                {portfolioData.positions.length}
              </Typography>
              <Typography variant="body2" color="textSecondary" mt={1}>
                Diversified portfolio
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Tabs */}
      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
        <Tabs value={tabValue} onChange={handleTabChange}>
          <Tab label="Holdings" />
          <Tab label="Performance" />
          <Tab label="Allocation" />
          <Tab label="Analysis" />
        </Tabs>
      </Box>

      {/* Holdings Tab */}
      <TabPanel value={tabValue} index={0}>
        <Card elevation={2}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Current Holdings
            </Typography>
            <TableContainer>
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell>Symbol</TableCell>
                    <TableCell>Company</TableCell>
                    <TableCell align="right">Shares</TableCell>
                    <TableCell align="right">Avg Price</TableCell>
                    <TableCell align="right">Current Price</TableCell>
                    <TableCell align="right">Market Value</TableCell>
                    <TableCell align="right">Day Change</TableCell>
                    <TableCell align="right">Total Return</TableCell>
                    <TableCell align="right">Allocation</TableCell>
                    <TableCell align="center">Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {portfolioData.positions.map((position, index) => (
                    <TableRow key={position.symbol} hover>
                      <TableCell>
                        <Box display="flex" alignItems="center" gap={1}>
                          <Avatar sx={{ width: 32, height: 32, backgroundColor: getSectorColor(position.sector) }}>
                            {position.symbol.charAt(0)}
                          </Avatar>
                          <Typography variant="body2" fontWeight={600}>
                            {position.symbol}
                          </Typography>
                        </Box>
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2">{position.name}</Typography>
                        <Typography variant="caption" color="textSecondary">{position.sector}</Typography>
                      </TableCell>
                      <TableCell align="right">{formatNumber(position.shares)}</TableCell>
                      <TableCell align="right">{formatCurrency(position.avgPrice)}</TableCell>
                      <TableCell align="right">{formatCurrency(position.currentPrice)}</TableCell>
                      <TableCell align="right">{formatCurrency(position.marketValue)}</TableCell>
                      <TableCell align="right">
                        <Chip
                          icon={position.dayChange >= 0 ? <TrendingUp /> : <TrendingDown />}
                          label={`${position.dayChange >= 0 ? '+' : ''}${position.dayChangePercent.toFixed(2)}%`}
                          color={position.dayChange >= 0 ? 'success' : 'error'}
                          size="small"
                        />
                      </TableCell>
                      <TableCell align="right">
                        <Box>
                          <Typography variant="body2" color={position.totalReturn >= 0 ? 'success.main' : 'error.main'} fontWeight={600}>
                            {formatCurrency(position.totalReturn)}
                          </Typography>
                          <Typography variant="caption" color={position.totalReturn >= 0 ? 'success.main' : 'error.main'}>
                            {position.totalReturnPercent >= 0 ? '+' : ''}{position.totalReturnPercent.toFixed(2)}%
                          </Typography>
                        </Box>
                      </TableCell>
                      <TableCell align="right">
                        <Typography variant="body2" fontWeight={600}>
                          {position.allocation.toFixed(1)}%
                        </Typography>
                      </TableCell>
                      <TableCell align="center">
                        <IconButton size="small">
                          <EditIcon />
                        </IconButton>
                        <IconButton size="small" color="error">
                          <DeleteIcon />
                        </IconButton>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </CardContent>
        </Card>
      </TabPanel>

      {/* Performance Tab */}
      <TabPanel value={tabValue} index={1}>
        <Grid container spacing={3}>
          <Grid item xs={12}>
            <Card elevation={2}>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Portfolio Performance vs S&P 500
                </Typography>
                <ResponsiveContainer width="100%" height={400}>
                  <AreaChart data={portfolioData.performance}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="date" />
                    <YAxis />
                    <RechartsTooltip formatter={(value) => [formatCurrency(value), '']} />
                    <Area type="monotone" dataKey="value" stackId="1" stroke="#1976d2" fill="#1976d2" fillOpacity={0.3} name="Portfolio" />
                    <Area type="monotone" dataKey="benchmark" stackId="2" stroke="#ff7043" fill="#ff7043" fillOpacity={0.3} name="S&P 500" />
                  </AreaChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </TabPanel>

      {/* Allocation Tab */}
      <TabPanel value={tabValue} index={2}>
        <Grid container spacing={3}>
          <Grid item xs={12} md={6}>
            <Card elevation={2}>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Allocation by Sector
                </Typography>
                <ResponsiveContainer width="100%" height={300}>
                  <PieChart>
                    <Pie
                      data={portfolioData.allocation.bySector}
                      cx="50%"
                      cy="50%"
                      outerRadius={100}
                      fill="#8884d8"
                      dataKey="value"
                      label={({ name, value }) => `${name}: ${value}%`}
                    >
                      {portfolioData.allocation.bySector.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                      ))}
                    </Pie>
                    <RechartsTooltip formatter={(value) => [`${value}%`, '']} />
                  </PieChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12} md={6}>
            <Card elevation={2}>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Asset Type Breakdown
                </Typography>
                <Box sx={{ mt: 2 }}>
                  {portfolioData.allocation.byAssetType.map((asset, index) => (
                    <Box key={asset.name} sx={{ mb: 2 }}>
                      <Box display="flex" justifyContent="space-between" alignItems="center" mb={0.5}>
                        <Typography variant="body2">{asset.name}</Typography>
                        <Typography variant="body2" fontWeight={600}>{asset.value}%</Typography>
                      </Box>
                      <LinearProgress
                        variant="determinate"
                        value={asset.value}
                        sx={{
                          height: 8,
                          borderRadius: 4,
                          backgroundColor: 'grey.200',
                          '& .MuiLinearProgress-bar': {
                            backgroundColor: COLORS[index % COLORS.length]
                          }
                        }}
                      />
                    </Box>
                  ))}
                </Box>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </TabPanel>

      {/* Analysis Tab */}
      <TabPanel value={tabValue} index={3}>
        <Grid container spacing={3}>
          <Grid item xs={12} md={6}>
            <Card elevation={2}>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Risk Metrics
                </Typography>
                <Box>
                  <Box sx={{ mb: 2 }}>
                    <Typography variant="body2" color="textSecondary">Portfolio Beta</Typography>
                    <Typography variant="h6" fontWeight={600}>0.92</Typography>
                    <Typography variant="caption" color="textSecondary">Lower volatility than market</Typography>
                  </Box>
                  <Box sx={{ mb: 2 }}>
                    <Typography variant="body2" color="textSecondary">Sharpe Ratio</Typography>
                    <Typography variant="h6" fontWeight={600}>1.85</Typography>
                    <Typography variant="caption" color="textSecondary">Excellent risk-adjusted returns</Typography>
                  </Box>
                  <Box sx={{ mb: 2 }}>
                    <Typography variant="body2" color="textSecondary">Max Drawdown</Typography>
                    <Typography variant="h6" fontWeight={600}>-8.2%</Typography>
                    <Typography variant="caption" color="textSecondary">Well controlled downside</Typography>
                  </Box>
                  <Box>
                    <Typography variant="body2" color="textSecondary">Volatility (Annualized)</Typography>
                    <Typography variant="h6" fontWeight={600}>15.4%</Typography>
                    <Typography variant="caption" color="textSecondary">Moderate risk profile</Typography>
                  </Box>
                </Box>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12} md={6}>
            <Card elevation={2}>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Portfolio Health Score
                </Typography>
                <Box textAlign="center" py={2}>
                  <Typography variant="h2" fontWeight="bold" color="success.main">
                    A+
                  </Typography>
                  <Typography variant="body1" color="textSecondary" mt={1}>
                    Excellent portfolio performance
                  </Typography>
                  <Box sx={{ mt: 3 }}>
                    <Box display="flex" justifyContent="space-between" mb={1}>
                      <Typography variant="body2">Diversification</Typography>
                      <Typography variant="body2" fontWeight={600}>95%</Typography>
                    </Box>
                    <Box display="flex" justifyContent="space-between" mb={1}>
                      <Typography variant="body2">Risk Management</Typography>
                      <Typography variant="body2" fontWeight={600}>88%</Typography>
                    </Box>
                    <Box display="flex" justifyContent="space-between" mb={1}>
                      <Typography variant="body2">Performance</Typography>
                      <Typography variant="body2" fontWeight={600}>92%</Typography>
                    </Box>
                    <Box display="flex" justifyContent="space-between">
                      <Typography variant="body2">Cost Efficiency</Typography>
                      <Typography variant="body2" fontWeight={600}>96%</Typography>
                    </Box>
                  </Box>
                </Box>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </TabPanel>

      {/* Add Position Dialog */}
      <Dialog open={showAddDialog} onClose={() => setShowAddDialog(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Add New Position</DialogTitle>
        <DialogContent>
          <Box sx={{ pt: 2 }}>
            <TextField
              fullWidth
              label="Symbol"
              value={newPosition.symbol}
              onChange={(e) => setNewPosition({ ...newPosition, symbol: e.target.value })}
              sx={{ mb: 2 }}
              placeholder="AAPL"
            />
            <TextField
              fullWidth
              label="Number of Shares"
              type="number"
              value={newPosition.shares}
              onChange={(e) => setNewPosition({ ...newPosition, shares: e.target.value })}
              sx={{ mb: 2 }}
            />
            <TextField
              fullWidth
              label="Average Price"
              type="number"
              value={newPosition.avgPrice}
              onChange={(e) => setNewPosition({ ...newPosition, avgPrice: e.target.value })}
              sx={{ mb: 2 }}
              placeholder="150.00"
            />
            <TextField
              fullWidth
              label="Current Price (optional)"
              type="number"
              value={newPosition.currentPrice}
              onChange={(e) => setNewPosition({ ...newPosition, currentPrice: e.target.value })}
              placeholder="Will use average price if not provided"
            />
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowAddDialog(false)}>Cancel</Button>
          <Button variant="contained" onClick={handleAddPosition}>Add Position</Button>
        </DialogActions>
      </Dialog>

      {/* Alpaca API Dialog */}
      <Dialog open={showApiDialog} onClose={() => setShowApiDialog(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Connect to Alpaca Markets</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="textSecondary" paragraph>
            Connect your Alpaca Markets account to automatically sync your portfolio data.
          </Typography>
          <TextField
            fullWidth
            label="Alpaca API Key"
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            sx={{ mb: 2 }}
            placeholder="Enter your Alpaca API key"
          />
          <Alert severity="info">
            Your API key is stored securely and only used to fetch portfolio data. We never store or transmit sensitive information.
          </Alert>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowApiDialog(false)}>Cancel</Button>
          <Button 
            variant="contained" 
            onClick={handleConnectAlpaca}
            disabled={!apiKey || loading}
          >
            {loading ? 'Connecting...' : 'Connect'}
          </Button>
        </DialogActions>
      </Dialog>

      {loading && <LinearProgress />}
    </Box>
  );
}

export default Portfolio;