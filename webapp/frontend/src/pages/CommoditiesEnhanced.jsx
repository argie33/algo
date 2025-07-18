import React, { useState, useEffect, useCallback } from 'react';
import {
  Box,
  Container,
  Typography,
  Grid,
  Card,
  CardContent,
  CardHeader,
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
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Alert,
  LinearProgress,
  Tooltip,
  ButtonGroup,
  Button,
  Stack,
  Divider,
  CircularProgress,
  Badge,
  Avatar,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Switch,
  FormControlLabel,
  Skeleton,
  Accordion,
  AccordionSummary,
  AccordionDetails
} from '@mui/material';
import {
  TrendingUp,
  TrendingDown,
  ShowChart,
  Agriculture,
  LocalGasStation,
  Diamond,
  Construction,
  Thermostat,
  Cloud,
  Assessment,
  Timeline,
  BarChart,
  PieChart,
  TableChart,
  Refresh,
  Info,
  Warning,
  CheckCircle,
  Error,
  Speed,
  Analytics,
  Insights,
  CandlestickChart,
  MonetizationOn,
  Schedule,
  Stars,
  Psychology,
  TrendingFlat,
  NotificationsActive,
  FilterList,
  ExpandMore,
  SignalCellular4Bar,
  SignalCellularConnectedNoInternet4Bar,
  Bolt,
  FlashOn,
  EmojiEvents,
  AccountBalance,
  DataUsage,
  MultilineChart,
  DonutSmall,
  Equalizer,
  Functions,
  CalendarMonth,
  Place,
  LocationOn,
  BusinessCenter,
  School,
  HelpOutline,
  BookmarkBorder,
  Bookmark,
  Share,
  Download,
  Print,
  Settings,
  Fullscreen,
  ZoomIn,
  ZoomOut,
  PanTool,
  OpenInNew,
  Launch,
  SmartToy,
  AutoGraph,
  CompareArrows,
  SwapVert,
  SwapHoriz,
  CompareArrowsOutlined,
  TrendingUpOutlined,
  TrendingDownOutlined,
  ShowChartOutlined,
  BarChartOutlined,
  PieChartOutlined,
  MultilineChartOutlined,
  CandlestickChartOutlined,
  TimelineOutlined,
  AnalyticsOutlined,
  InsightsOutlined,
  AssessmentOutlined,
  SpeedOutlined,
  PsychologyOutlined,
  AccountBalanceOutlined,
  BusinessCenterOutlined,
  SchoolOutlined,
  EmojiEventsOutlined,
  StarOutlined,
  BoltOutlined,
  FlashOnOutlined,
  SignalCellular4BarOutlined,
  NotificationsActiveOutlined,
  FilterListOutlined,
  CalendarMonthOutlined,
  PlaceOutlined,
  HelpOutlineOutlined,
  BookmarkBorderOutlined,
  SettingsOutlined,
  FullscreenOutlined,
  LaunchOutlined,
  SmartToyOutlined,
  AutoGraphOutlined
} from '@mui/icons-material';
import { 
  LineChart, 
  Line, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip as RechartsTooltip, 
  ResponsiveContainer, 
  AreaChart, 
  Area, 
  BarChart as RechartsBarChart, 
  Bar, 
  PieChart as RechartsPieChart, 
  Cell,
  ComposedChart,
  Legend,
  Scatter,
  ScatterChart,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  Treemap,
  FunnelChart,
  Funnel,
  LabelList
} from 'recharts';
import { motion, AnimatePresence } from 'framer-motion';
import apiService from '../services/api';

// Color palette for professional commodities trading
const COLORS = {
  primary: '#1976d2',
  secondary: '#dc004e',
  success: '#2e7d32',
  error: '#d32f2f',
  warning: '#ed6c02',
  info: '#0288d1',
  gold: '#FFD700',
  silver: '#C0C0C0',
  copper: '#B87333',
  oil: '#2F4F4F',
  gas: '#FF6347',
  agriculture: '#228B22',
  neutral: '#666666'
};

// Enhanced commodity categories with more detailed information
const COMMODITY_CATEGORIES = {
  energy: {
    name: 'Energy',
    icon: LocalGasStation,
    color: COLORS.oil,
    description: 'Crude oil, natural gas, and refined products',
    commodities: ['CL=F', 'NG=F', 'BZ=F', 'RB=F', 'HO=F'],
    keyFactors: ['Supply disruptions', 'OPEC decisions', 'Weather', 'Economic growth']
  },
  metals: {
    name: 'Precious Metals',
    icon: Diamond,
    color: COLORS.gold,
    description: 'Gold, silver, platinum, and palladium',
    commodities: ['GC=F', 'SI=F', 'PL=F', 'PA=F'],
    keyFactors: ['Dollar strength', 'Inflation', 'Central bank policy', 'Safe haven demand']
  },
  industrial: {
    name: 'Industrial Metals',
    icon: Construction,
    color: COLORS.copper,
    description: 'Copper and base metals',
    commodities: ['HG=F'],
    keyFactors: ['Manufacturing PMI', 'Infrastructure spending', 'China demand', 'Supply strikes']
  },
  agriculture: {
    name: 'Agriculture',
    icon: Agriculture,
    color: COLORS.agriculture,
    description: 'Grains, softs, and agricultural products',
    commodities: ['ZC=F', 'ZS=F', 'ZW=F', 'KC=F', 'SB=F', 'CC=F', 'CT=F'],
    keyFactors: ['Weather patterns', 'Crop yields', 'Trade policies', 'Seasonal demand']
  },
  livestock: {
    name: 'Livestock',
    icon: Agriculture,
    color: '#8B4513',
    description: 'Live cattle, feeder cattle, and lean hogs',
    commodities: ['LE=F', 'GF=F', 'HE=F'],
    keyFactors: ['Feed costs', 'Disease outbreaks', 'Consumer demand', 'Export markets']
  },
  forex: {
    name: 'Currencies',
    icon: AccountBalance,
    color: COLORS.info,
    description: 'Major currency pairs and USD index',
    commodities: ['DX-Y.NYB', 'EURUSD=X', 'GBPUSD=X', 'USDJPY=X', 'USDCAD=X'],
    keyFactors: ['Interest rates', 'Economic data', 'Central bank policy', 'Risk sentiment']
  }
};

// Signal strength indicators
const SIGNAL_STRENGTH = {
  'Strong': { color: COLORS.success, icon: SignalCellular4Bar, score: 85 },
  'Moderate': { color: COLORS.warning, icon: SignalCellular4Bar, score: 65 },
  'Weak': { color: COLORS.error, icon: SignalCellularConnectedNoInternet4Bar, score: 45 },
  'Neutral': { color: COLORS.neutral, icon: TrendingFlat, score: 50 }
};

// Tab panel component
function TabPanel({ children, value, index, ...other }) {
  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`commodities-tabpanel-${index}`}
      aria-labelledby={`commodities-tab-${index}`}
      {...other}
    >
      {value === index && <div  sx={{ py: 3 }}>{children}</div>}
    </div>
  );
}

// Enhanced commodity card component
const CommodityCard = ({ category, data, onClick, isSelected }) => {
  const Icon = category.icon;
  const avgChange = data.reduce((sum, c) => sum + (c.change_percent || 0), 0) / data.length;
  const gainers = data.filter(c => (c.change_percent || 0) > 0).length;
  const losers = data.filter(c => (c.change_percent || 0) < 0).length;
  
  return (
    <motion.div
      whileHover={{ scale: 1.02 }}
      whileTap={{ scale: 0.98 }}
      transition={{ type: "spring", stiffness: 300 }}
    >
      <div className="bg-white shadow-md rounded-lg" 
        sx={{ 
          height: 280,
          cursor: 'pointer',
          background: `linear-gradient(135deg, ${category.color + '1A'} 0%, ${category.color + '0D'} 100%)`,
          border: `2px solid ${isSelected ? category.color : category.color + '33'}`,
          transition: 'all 0.3s ease',
          '&:hover': {
            transform: 'translateY(-4px)',
            boxShadow: `0 12px 24px ${category.color + '33'}`,
            border: `2px solid ${category.color}`
          }
        }}
        onClick={() => onClick(category)}
      >
        <div className="bg-white shadow-md rounded-lg"Header
          avatar={
            <div className="h-8 w-8 rounded-full bg-gray-300 flex items-center justify-center" sx={{ bgcolor: category.color, width: 48, height: 48 }}>
              <Icon sx={{ fontSize: 28 }} />
            </div>
          }
          title={
            <div  display="flex" alignItems="center" gap={1}>
              <div  variant="h6" fontWeight="bold">
                {category.name}
              </div>
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                label={`${avgChange >= 0 ? '+' : ''}${avgChange.toFixed(2)}%`}
                size="small"
                sx={{ 
                  backgroundColor: avgChange >= 0 ? COLORS.success : COLORS.error,
                  color: 'white',
                  fontWeight: 'bold'
                }}
              />
            </div>
          }
          subheader={category.description}
        />
        <div className="bg-white shadow-md rounded-lg"Content>
          <div className="flex flex-col space-y-2" spacing={2}>
            <div  display="flex" justifyContent="space-between" alignItems="center">
              <div  variant="body2" color="textSecondary">
                {data.length} commodities
              </div>
              <div  display="flex" gap={1}>
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                  label={`${gainers} ↑`} 
                  size="small" 
                  color="success" 
                  variant="outlined"
                />
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                  label={`${losers} ↓`} 
                  size="small" 
                  color="error" 
                  variant="outlined"
                />
              </div>
            </div>
            
            <div>
              <div  variant="caption" color="textSecondary">
                Key Factors:
              </div>
              <div  variant="body2" sx={{ mt: 0.5 }}>
                {category.keyFactors.slice(0, 2).join(', ')}
              </div>
            </div>
            
            <div className="w-full bg-gray-200 rounded-full h-2"
              variant="determinate"
              value={Math.abs(avgChange) * 10}
              sx={{
                height: 8,
                borderRadius: 4,
                backgroundColor: category.color + '33',
                '& .MuiLinearProgress-bar': {
                  backgroundColor: category.color,
                  borderRadius: 4
                }
              }}
            />
          </div>
        </div>
      </div>
    </motion.div>
  );
};

// Trading signal component
const TradingSignal = ({ signal }) => {
  const strength = SIGNAL_STRENGTH[signal.strength] || SIGNAL_STRENGTH.Neutral;
  const SignalIcon = strength.icon;
  
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
    >
      <div className="bg-white shadow-md rounded-lg" sx={{ mb: 2, border: `1px solid ${strength.color + '4D'}` }}>
        <div className="bg-white shadow-md rounded-lg"Content>
          <div  display="flex" alignItems="center" gap={2} mb={1}>
            <SignalIcon sx={{ color: strength.color }} />
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
              label={signal.signal}
              size="small"
              sx={{ 
                backgroundColor: signal.signal === 'BUY' ? COLORS.success : COLORS.error,
                color: 'white',
                fontWeight: 'bold'
              }}
            />
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
              label={signal.strength}
              size="small"
              sx={{ 
                backgroundColor: strength.color,
                color: 'white'
              }}
            />
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
              label={signal.timeframe}
              size="small"
              variant="outlined"
            />
            <div  ml="auto">
              <div  variant="caption" color="textSecondary">
                Confidence: {signal.confidence}%
              </div>
            </div>
          </div>
          <div  variant="body2" sx={{ mb: 1 }}>
            {signal.reason}
          </div>
          <div className="w-full bg-gray-200 rounded-full h-2" 
            variant="determinate" 
            value={signal.confidence} 
            sx={{
              height: 4,
              borderRadius: 2,
              backgroundColor: strength.color + '33',
              '& .MuiLinearProgress-bar': {
                backgroundColor: strength.color,
                borderRadius: 2
              }
            }}
          />
        </div>
      </div>
    </motion.div>
  );
};

// Professional price table component
const PriceTable = ({ data, loading, onRowClick }) => {
  
  if (loading) {
    return (
      <div  sx={{ p: 3 }}>
        {[...Array(8)].map((_, i) => (
          <div  key={i} sx={{ mb: 2 }}>
            <Skeleton variant="rectangular" height={60} />
          </div>
        ))}
      </div>
    );
  }
  
  return (
    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer>
      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le>
        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
              <div  variant="subtitle2" fontWeight="bold">
                Commodity
              </div>
            </td>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
              <div  variant="subtitle2" fontWeight="bold">
                Price
              </div>
            </td>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
              <div  variant="subtitle2" fontWeight="bold">
                Change
              </div>
            </td>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
              <div  variant="subtitle2" fontWeight="bold">
                % Change
              </div>
            </td>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center">
              <div  variant="subtitle2" fontWeight="bold">
                Trend
              </div>
            </td>
            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center">
              <div  variant="subtitle2" fontWeight="bold">
                Score
              </div>
            </td>
          </tr>
        </thead>
        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
          {data.map((item, index) => (
            <motion.tr
              key={item.symbol}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: index * 0.1 }}
              style={{ cursor: 'pointer' }}
              onClick={() => onRowClick(item)}
            >
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                <div  display="flex" alignItems="center" gap={2}>
                  <div className="h-8 w-8 rounded-full bg-gray-300 flex items-center justify-center" 
                    sx={{ 
                      width: 32, 
                      height: 32,
                      bgcolor: getCommodityColor(item.symbol),
                      fontSize: 12,
                      fontWeight: 'bold'
                    }}
                  >
                    {item.symbol.slice(0, 2)}
                  </div>
                  <div>
                    <div  variant="body2" fontWeight="medium">
                      {item.name}
                    </div>
                    <div  variant="caption" color="textSecondary">
                      {item.symbol}
                    </div>
                  </div>
                </div>
              </td>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                <div  variant="body2" fontWeight="bold">
                  ${item.price?.toFixed(2)}
                </div>
              </td>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                <div  
                  variant="body2" 
                  sx={{ 
                    color: (item.change_amount || 0) >= 0 ? COLORS.success : COLORS.error,
                    fontWeight: 'medium'
                  }}
                >
                  {(item.change_amount || 0) >= 0 ? '+' : ''}{item.change_amount?.toFixed(3)}
                </div>
              </td>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                  label={`${(item.change_percent || 0) >= 0 ? '+' : ''}${item.change_percent?.toFixed(2)}%`}
                  size="small"
                  sx={{
                    backgroundColor: (item.change_percent || 0) >= 0 ? COLORS.success : COLORS.error,
                    color: 'white',
                    fontWeight: 'bold'
                  }}
                />
              </td>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center">
                {(item.change_percent || 0) > 0 ? (
                  <TrendingUp sx={{ color: COLORS.success }} />
                ) : (
                  <TrendingDown sx={{ color: COLORS.error }} />
                )}
              </td>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center">
                <div  display="flex" alignItems="center" justifyContent="center" gap={1}>
                  <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500"
                    variant="determinate"
                    value={item.overall_score || 50}
                    size={32}
                    thickness={4}
                    sx={{
                      color: getScoreColor(item.overall_score || 50),
                    }}
                  />
                  <div  variant="caption" fontWeight="bold">
                    {item.overall_score || 50}
                  </div>
                </div>
              </td>
            </motion.tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

// Utility functions
const getCommodityColor = (symbol) => {
  if (symbol.includes('GC') || symbol.includes('SI') || symbol.includes('PL') || symbol.includes('PA')) return COLORS.gold;
  if (symbol.includes('CL') || symbol.includes('NG') || symbol.includes('BZ')) return COLORS.oil;
  if (symbol.includes('HG')) return COLORS.copper;
  if (symbol.includes('ZC') || symbol.includes('ZS') || symbol.includes('ZW')) return COLORS.agriculture;
  return COLORS.neutral;
};

const getScoreColor = (score) => {
  if (score >= 70) return COLORS.success;
  if (score >= 50) return COLORS.warning;
  return COLORS.error;
};

const formatCurrency = (value, symbol = '$') => {
  if (value === null || value === undefined) return 'N/A';
  return `${symbol}${value.toFixed(2)}`;
};

const formatPercent = (value) => {
  if (value === null || value === undefined) return 'N/A';
  const sign = value >= 0 ? '+' : '';
  return `${sign}${value.toFixed(2)}%`;
};

const CommoditiesEnhanced = () => {
  const [activeTab, setActiveTab] = useState(0);
  const [selectedCommodity, setSelectedCommodity] = useState('CL=F');
  const [selectedCategory, setSelectedCategory] = useState(null);
  const [selectedTimeframe, setSelectedTimeframe] = useState('1M');
  const [loading, setLoading] = useState(true);
  const [pricesData, setPricesData] = useState([]);
  const [cotData, setCotData] = useState([]);
  const [seasonalityData, setSeasonalityData] = useState([]);
  const [tradingSignals, setTradingSignals] = useState([]);
  const [commodityMetrics, setCommodityMetrics] = useState(null);
  const [marketSummary, setMarketSummary] = useState({});
  const [historyData, setHistoryData] = useState([]);
  const [error, setError] = useState(null);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [refreshInterval, setRefreshInterval] = useState(null);

  // Fetch data functions
  const fetchPricesData = useCallback(async () => {
    try {
      setLoading(true);
      const response = await apiService.get('/commodities/prices');
      if (response.success) {
        setPricesData(response.data);
        setError(null);
      } else {
        setError('Failed to fetch prices data');
      }
    } catch (err) {
      setError('Network error fetching prices');
      console.error('Error fetching prices:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchCOTData = useCallback(async (symbol) => {
    try {
      const response = await apiService.get(`/commodities/cot/${symbol}`);
      if (response.success) {
        setCotData(response.data);
      }
    } catch (err) {
      console.error('Error fetching COT data:', err);
    }
  }, []);

  const fetchSeasonalityData = useCallback(async (symbol) => {
    try {
      const response = await apiService.get(`/commodities/seasonality/${symbol}`);
      if (response.success) {
        setSeasonalityData(response.data);
      }
    } catch (err) {
      console.error('Error fetching seasonality data:', err);
    }
  }, []);

  const fetchTradingSignals = useCallback(async (symbol) => {
    try {
      const response = await apiService.get(`/commodities/signals/${symbol}`);
      if (response.success) {
        setTradingSignals(response.data);
      }
    } catch (err) {
      console.error('Error fetching trading signals:', err);
    }
  }, []);

  const fetchCommodityMetrics = useCallback(async (symbol) => {
    try {
      const response = await apiService.get(`/commodities/metrics/${symbol}`);
      if (response.success) {
        setCommodityMetrics(response.data);
      }
    } catch (err) {
      console.error('Error fetching commodity metrics:', err);
    }
  }, []);

  const fetchMarketSummary = useCallback(async () => {
    try {
      const response = await apiService.get('/commodities/market-summary');
      if (response.success) {
        setMarketSummary(response.data);
      }
    } catch (err) {
      console.error('Error fetching market summary:', err);
    }
  }, []);

  const fetchHistoryData = useCallback(async (symbol, period) => {
    try {
      const response = await apiService.get(`/commodities/history/${symbol}?period=${period}`);
      if (response.success) {
        setHistoryData(response.data);
      }
    } catch (err) {
      console.error('Error fetching history data:', err);
    }
  }, []);

  // Effects
  useEffect(() => {
    fetchPricesData();
    fetchMarketSummary();
  }, [fetchPricesData, fetchMarketSummary]);

  useEffect(() => {
    if (selectedCommodity) {
      fetchCOTData(selectedCommodity);
      fetchSeasonalityData(selectedCommodity);
      fetchTradingSignals(selectedCommodity);
      fetchCommodityMetrics(selectedCommodity);
      fetchHistoryData(selectedCommodity, selectedTimeframe);
    }
  }, [selectedCommodity, selectedTimeframe, fetchCOTData, fetchSeasonalityData, fetchTradingSignals, fetchCommodityMetrics, fetchHistoryData]);

  // Auto refresh setup
  useEffect(() => {
    if (autoRefresh) {
      const interval = setInterval(() => {
        fetchPricesData();
        fetchMarketSummary();
        if (selectedCommodity) {
          fetchCommodityMetrics(selectedCommodity);
        }
      }, 60000); // Refresh every minute
      setRefreshInterval(interval);
      return () => clearInterval(interval);
    } else if (refreshInterval) {
      clearInterval(refreshInterval);
      setRefreshInterval(null);
    }
  }, [autoRefresh, selectedCommodity, fetchPricesData, fetchMarketSummary, fetchCommodityMetrics, refreshInterval]);

  // Event handlers
  const handleCommoditySelect = (commodity) => {
    setSelectedCommodity(commodity.symbol);
    setActiveTab(3); // Switch to detailed analysis tab
  };

  const handleCategorySelect = (category) => {
    setSelectedCategory(category);
    setActiveTab(1); // Switch to category analysis tab
  };

  const handleRefresh = () => {
    fetchPricesData();
    fetchMarketSummary();
    if (selectedCommodity) {
      fetchCOTData(selectedCommodity);
      fetchSeasonalityData(selectedCommodity);
      fetchTradingSignals(selectedCommodity);
      fetchCommodityMetrics(selectedCommodity);
      fetchHistoryData(selectedCommodity, selectedTimeframe);
    }
  };

  // Render functions
  const renderMarketOverview = () => (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
    >
      <div className="grid" container spacing={3}>
        {/* Header */}
        <div className="grid" item xs={12}>
          <div  display="flex" alignItems="center" justifyContent="space-between" mb={2}>
            <div  variant="h4" fontWeight="bold" sx={{ 
              background: `linear-gradient(45deg, ${COLORS.primary}, ${COLORS.secondary})`,
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              display: 'flex',
              alignItems: 'center',
              gap: 1
            }}>
              <Assessment />
              Commodities Trading Dashboard
            </div>
            <div  display="flex" gap={1}>
              <div className="mb-4"Label
                control={<input type="checkbox" className="toggle" checked={autoRefresh} onChange={(e) => setAutoRefresh(e.target.checked)} />}
                label="Auto Refresh"
              />
              <button className="p-2 rounded-full hover:bg-gray-100" onClick={handleRefresh} color="primary">
                <Refresh />
              </button>
            </div>
          </div>
        </div>
        
        {/* Category Cards */}
        {Object.entries(COMMODITY_CATEGORIES).map(([key, category]) => {
          const categoryData = pricesData.filter(item => {
            return category.commodities.includes(item.symbol);
          });
          
          return (
            <div className="grid" item xs={12} sm={6} md={4} lg={2} key={key}>
              <CommodityCard 
                category={category}
                data={categoryData}
                onClick={handleCategorySelect}
                isSelected={selectedCategory?.name === category.name}
              />
            </div>
          );
        })}

        {/* Live Price Table */}
        <div className="grid" item xs={12}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Header 
              title={
                <div  display="flex" alignItems="center" gap={1}>
                  <ShowChart />
                  Live Commodity Prices
                  <span className="inline-flex items-center justify-center px-2 py-1 text-xs font-bold leading-none text-red-100 bg-red-600 rounded-full" 
                    badgeContent={pricesData.length} 
                    color="primary"
                    sx={{ ml: 1 }}
                  />
                </div>
              }
              action={
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                  label="LIVE" 
                  size="small" 
                  sx={{ 
                    backgroundColor: COLORS.success,
                    color: 'white',
                    fontWeight: 'bold',
                    animation: 'pulse 2s infinite'
                  }}
                />
              }
            />
            <div className="bg-white shadow-md rounded-lg"Content sx={{ p: 0 }}>
              <PriceTable 
                data={pricesData} 
                loading={loading} 
                onRowClick={handleCommoditySelect}
              />
            </div>
          </div>
        </div>
      </div>
    </motion.div>
  );

  const renderCOTAnalysis = () => (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
    >
      <div className="grid" container spacing={3}>
        {/* Header */}
        <div className="grid" item xs={12}>
          <div  display="flex" alignItems="center" justifyContent="space-between" mb={2}>
            <div  variant="h5" fontWeight="bold" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <BarChart />
              Commitment of Traders Analysis
            </div>
            <div className="mb-4" sx={{ minWidth: 200 }}>
              <label className="block text-sm font-medium text-gray-700 mb-1">Select Commodity</label>
              <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={selectedCommodity}
                onChange={(e) => setSelectedCommodity(e.target.value)}
                label="Select Commodity"
              >
                {pricesData.map((item) => (
                  <option  key={item.symbol} value={item.symbol}>
                    {item.symbol} - {item.name}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="info" sx={{ mb: 3 }}>
            <div  variant="subtitle2">Understanding COT Data</div>
            <div  variant="body2">
              Commercial traders are typically producers and consumers (smart money). 
              Non-commercial traders are speculators and hedge funds. When commercials are net long, 
              it's generally bullish; when net short, it's bearish.
            </div>
          </div>
        </div>

        {/* COT Charts */}
        <div className="grid" item xs={12} md={8}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Header 
              title="Net Positions Over Time"
              subheader="Commercial vs Non-Commercial Positioning"
            />
            <div className="bg-white shadow-md rounded-lg"Content>
              <ResponsiveContainer width="100%" height={400}>
                <ComposedChart data={cotData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="week" />
                  <YAxis />
                  <RechartsTooltip />
                  <Legend />
                  <Line 
                    type="monotone" 
                    dataKey="commercial_net" 
                    stroke={COLORS.success} 
                    strokeWidth={3}
                    name="Commercial Net"
                  />
                  <Line 
                    type="monotone" 
                    dataKey="non_commercial_net" 
                    stroke={COLORS.error} 
                    strokeWidth={3}
                    name="Non-Commercial Net"
                  />
                  <Bar 
                    dataKey="open_interest" 
                    fill={'#2196f34D'} 
                    name="Open Interest"
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

        {/* COT Summary */}
        <div className="grid" item xs={12} md={4}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Header title="Current COT Analysis" />
            <div className="bg-white shadow-md rounded-lg"Content>
              <div className="flex flex-col space-y-2" spacing={3}>
                {cotData.length > 0 && (
                  <>
                    <div>
                      <div  variant="subtitle2" gutterBottom>
                        Commercial Net Position
                      </div>
                      <div  display="flex" alignItems="center" gap={1}>
                        <div  variant="h6" color={cotData[0].commercial_net > 0 ? "success.main" : "error.main"}>
                          {cotData[0].commercial_net > 0 ? '+' : ''}{cotData[0].commercial_net?.toLocaleString()}
                        </div>
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                          label={cotData[0].commercial_net > 0 ? "Bullish" : "Bearish"} 
                          size="small" 
                          color={cotData[0].commercial_net > 0 ? "success" : "error"}
                        />
                      </div>
                      <div  variant="caption" color="textSecondary">
                        {cotData[0].commercial_net_pct?.toFixed(1)}% of open interest
                      </div>
                    </div>

                    <hr className="border-gray-200" />

                    <div>
                      <div  variant="subtitle2" gutterBottom>
                        Non-Commercial Net Position
                      </div>
                      <div  display="flex" alignItems="center" gap={1}>
                        <div  variant="h6" color={cotData[0].non_commercial_net > 0 ? "success.main" : "error.main"}>
                          {cotData[0].non_commercial_net > 0 ? '+' : ''}{cotData[0].non_commercial_net?.toLocaleString()}
                        </div>
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                          label={cotData[0].non_commercial_net > 0 ? "Long" : "Short"} 
                          size="small" 
                          color={cotData[0].non_commercial_net > 0 ? "success" : "error"}
                        />
                      </div>
                      <div  variant="caption" color="textSecondary">
                        {cotData[0].non_commercial_net_pct?.toFixed(1)}% of open interest
                      </div>
                    </div>

                    <hr className="border-gray-200" />

                    <div>
                      <div  variant="subtitle2" gutterBottom>
                        Smart Money Signal
                      </div>
                      <div  display="flex" alignItems="center" gap={1}>
                        <CheckCircle sx={{ color: 'success.main' }} />
                        <div  variant="body2">
                          {cotData[0].commercial_net > 0 
                            ? "Commercial traders are net long, suggesting bullish outlook"
                            : "Commercial traders are net short, suggesting bearish outlook"
                          }
                        </div>
                      </div>
                    </div>
                  </>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Trading Signals */}
        <div className="grid" item xs={12}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Header 
              title={
                <div  display="flex" alignItems="center" gap={1}>
                  <SignalCellular4Bar />
                  Trading Signals
                  <span className="inline-flex items-center justify-center px-2 py-1 text-xs font-bold leading-none text-red-100 bg-red-600 rounded-full" badgeContent={tradingSignals.length} color="primary" />
                </div>
              }
            />
            <div className="bg-white shadow-md rounded-lg"Content>
              {tradingSignals.length > 0 ? (
                <div className="grid" container spacing={2}>
                  {tradingSignals.map((signal, index) => (
                    <div className="grid" item xs={12} md={6} key={index}>
                      <TradingSignal signal={signal} />
                    </div>
                  ))}
                </div>
              ) : (
                <div  textAlign="center" py={4}>
                  <div  variant="h6" color="textSecondary">
                    No trading signals available
                  </div>
                  <div  variant="body2" color="textSecondary">
                    Select a commodity to view analysis
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </motion.div>
  );

  const renderSeasonalAnalysis = () => (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
    >
      <div className="grid" container spacing={3}>
        {/* Header */}
        <div className="grid" item xs={12}>
          <div  display="flex" alignItems="center" justifyContent="space-between" mb={2}>
            <div  variant="h5" fontWeight="bold" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Timeline />
              Seasonal Analysis & Patterns
            </div>
            <div className="mb-4" sx={{ minWidth: 200 }}>
              <label className="block text-sm font-medium text-gray-700 mb-1">Select Commodity</label>
              <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={selectedCommodity}
                onChange={(e) => setSelectedCommodity(e.target.value)}
                label="Select Commodity"
              >
                {pricesData.map((item) => (
                  <option  key={item.symbol} value={item.symbol}>
                    {item.symbol} - {item.name}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>

        {/* Seasonal Chart */}
        <div className="grid" item xs={12} md={8}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Header 
              title="Seasonal Performance Patterns"
              subheader="Historical win rates and average returns by month"
            />
            <div className="bg-white shadow-md rounded-lg"Content>
              <ResponsiveContainer width="100%" height={400}>
                <ComposedChart data={seasonalityData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="month_name" />
                  <YAxis yAxisId="left" />
                  <YAxis yAxisId="right" orientation="right" />
                  <RechartsTooltip />
                  <Legend />
                  <Bar 
                    yAxisId="left"
                    dataKey="win_rate" 
                    fill={COLORS.success}
                    name="Win Rate (%)"
                  />
                  <Line 
                    yAxisId="right"
                    type="monotone" 
                    dataKey="avg_return_pct" 
                    stroke={COLORS.primary} 
                    strokeWidth={3}
                    name="Avg Return (%)"
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

        {/* Seasonal Insights */}
        <div className="grid" item xs={12} md={4}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Header title="Seasonal Insights" />
            <div className="bg-white shadow-md rounded-lg"Content>
              <div className="flex flex-col space-y-2" spacing={2}>
                {seasonalityData.length > 0 ? (
                  <>
                    {/* Current month highlight */}
                    {(() => {
                      const currentMonth = new Date().getMonth() + 1;
                      const currentSeasonality = seasonalityData.find(s => s.month === currentMonth);
                      return currentSeasonality ? (
                        <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity={currentSeasonality.strength === 'Strong' ? 'success' : 
                                       currentSeasonality.strength === 'Moderate' ? 'info' : 'warning'}>
                          <div  variant="subtitle2">Current Month ({currentSeasonality.month_name})</div>
                          <div  variant="body2">
                            Win Rate: {currentSeasonality.win_rate?.toFixed(1)}% | 
                            Avg Return: {currentSeasonality.avg_return_pct?.toFixed(2)}%
                          </div>
                        </div>
                      ) : null;
                    })()}

                    {/* Best and worst months */}
                    {(() => {
                      const bestMonth = seasonalityData.reduce((best, current) => 
                        current.win_rate > best.win_rate ? current : best
                      );
                      const worstMonth = seasonalityData.reduce((worst, current) => 
                        current.win_rate < worst.win_rate ? current : worst
                      );
                      
                      return (
                        <>
                          <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="success">
                            <div  variant="subtitle2">Best Month: {bestMonth.month_name}</div>
                            <div  variant="body2">
                              Win Rate: {bestMonth.win_rate?.toFixed(1)}% | 
                              Avg Return: {bestMonth.avg_return_pct?.toFixed(2)}%
                            </div>
                          </div>
                          
                          <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error">
                            <div  variant="subtitle2">Worst Month: {worstMonth.month_name}</div>
                            <div  variant="body2">
                              Win Rate: {worstMonth.win_rate?.toFixed(1)}% | 
                              Avg Return: {worstMonth.avg_return_pct?.toFixed(2)}%
                            </div>
                          </div>
                        </>
                      );
                    })()}
                  </>
                ) : (
                  <div  variant="body2" color="textSecondary">
                    No seasonal data available for selected commodity
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </motion.div>
  );

  const renderTechnicalAnalysis = () => (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
    >
      <div className="grid" container spacing={3}>
        {/* Header and Controls */}
        <div className="grid" item xs={12}>
          <div  display="flex" alignItems="center" justifyContent="space-between" mb={2}>
            <div  variant="h5" fontWeight="bold" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <ShowChart />
              Technical Analysis & Metrics
            </div>
            <div  display="flex" gap={2}>
              <div className="mb-4" sx={{ minWidth: 150 }}>
                <label className="block text-sm font-medium text-gray-700 mb-1">Commodity</label>
                <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={selectedCommodity}
                  onChange={(e) => setSelectedCommodity(e.target.value)}
                  label="Commodity"
                >
                  {pricesData.map((item) => (
                    <option  key={item.symbol} value={item.symbol}>
                      {item.symbol} - {item.name}
                    </option>
                  ))}
                </select>
              </div>

              <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"Group variant="outlined">
                {['1D', '1W', '1M', '3M', '6M', '1Y'].map((timeframe) => (
                  <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                    key={timeframe}
                    variant={selectedTimeframe === timeframe ? 'contained' : 'outlined'}
                    onClick={() => setSelectedTimeframe(timeframe)}
                    size="small"
                  >
                    {timeframe}
                  </button>
                ))}
              </ButtonGroup>
            </div>
          </div>
        </div>

        {/* Price Chart */}
        <div className="grid" item xs={12} md={8}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Header title={`${selectedCommodity} Price Chart`} />
            <div className="bg-white shadow-md rounded-lg"Content>
              <ResponsiveContainer width="100%" height={400}>
                <LineChart data={historyData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="date" />
                  <YAxis />
                  <RechartsTooltip />
                  <Line 
                    type="monotone" 
                    dataKey="close" 
                    stroke={COLORS.primary} 
                    strokeWidth={2}
                    name="Close Price"
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

        {/* Technical Indicators */}
        <div className="grid" item xs={12} md={4}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Header title="Technical Indicators" />
            <div className="bg-white shadow-md rounded-lg"Content>
              <div className="flex flex-col space-y-2" spacing={3}>
                {commodityMetrics ? (
                  <>
                    <div>
                      <div  variant="subtitle2">RSI (14)</div>
                      <div  display="flex" alignItems="center" gap={1}>
                        <div  variant="h6">{commodityMetrics.rsi?.toFixed(1)}</div>
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                          label={commodityMetrics.rsi < 30 ? "Oversold" : 
                                 commodityMetrics.rsi > 70 ? "Overbought" : "Neutral"} 
                          size="small" 
                          color={commodityMetrics.rsi < 30 ? "success" : 
                                 commodityMetrics.rsi > 70 ? "error" : "default"}
                        />
                      </div>
                      <div className="w-full bg-gray-200 rounded-full h-2" 
                        variant="determinate" 
                        value={commodityMetrics.rsi} 
                        sx={{ mt: 1 }}
                      />
                    </div>

                    <div>
                      <div  variant="subtitle2">Price Position (52W)</div>
                      <div  display="flex" alignItems="center" gap={1}>
                        <div  variant="h6">{(commodityMetrics.price_position_52w * 100)?.toFixed(1)}%</div>
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                          label={commodityMetrics.price_position_52w < 0.3 ? "Near Lows" : 
                                 commodityMetrics.price_position_52w > 0.7 ? "Near Highs" : "Mid-Range"} 
                          size="small" 
                          color={commodityMetrics.price_position_52w < 0.3 ? "success" : 
                                 commodityMetrics.price_position_52w > 0.7 ? "error" : "default"}
                        />
                      </div>
                      <div className="w-full bg-gray-200 rounded-full h-2" 
                        variant="determinate" 
                        value={commodityMetrics.price_position_52w * 100} 
                        sx={{ mt: 1 }}
                      />
                    </div>

                    <div>
                      <div  variant="subtitle2">Overall Score</div>
                      <div  display="flex" alignItems="center" gap={1}>
                        <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500"
                          variant="determinate"
                          value={commodityMetrics.overall_score}
                          size={40}
                          thickness={4}
                          sx={{ color: getScoreColor(commodityMetrics.overall_score) }}
                        />
                        <div  variant="h6">{commodityMetrics.overall_score}</div>
                      </div>
                    </div>

                    <div>
                      <div  variant="subtitle2">Support/Resistance</div>
                      <div  variant="body2" color="error.main">
                        Support: ${commodityMetrics.support_level?.toFixed(2)}
                      </div>
                      <div  variant="body2" color="success.main">
                        Resistance: ${commodityMetrics.resistance_level?.toFixed(2)}
                      </div>
                    </div>

                    <div>
                      <div  variant="subtitle2">Volatility (Annual)</div>
                      <div  variant="h6">{commodityMetrics.volatility_annual?.toFixed(1)}%</div>
                      <div className="w-full bg-gray-200 rounded-full h-2" 
                        variant="determinate" 
                        value={Math.min(commodityMetrics.volatility_annual, 100)} 
                        sx={{ mt: 1 }}
                      />
                    </div>
                  </>
                ) : (
                  <div  variant="body2" color="textSecondary">
                    Loading technical indicators...
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </motion.div>
  );

  if (error) {
    return (
      <div className="container mx-auto" maxWidth="xl" sx={{ py: 3 }}>
        <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error" sx={{ mb: 3 }}>
          <div  variant="h6">Error Loading Data</div>
          <div  variant="body2">{String(error)}</div>
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto" maxWidth="xl" sx={{ py: 3 }}>
      <div  sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
        <div className="border-b border-gray-200" 
          value={activeTab} 
          onChange={(_, newValue) => setActiveTab(newValue)}
          variant="scrollable"
          scrollButtons="auto"
        >
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Market Overview" icon={<Assessment />} />
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="COT Analysis" icon={<BarChart />} />
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Seasonal Patterns" icon={<Timeline />} />
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Technical Analysis" icon={<ShowChart />} />
        </div>
      </div>

      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={activeTab} index={0}>
        {renderMarketOverview()}
      </div>

      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={activeTab} index={1}>
        {renderCOTAnalysis()}
      </div>

      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={activeTab} index={2}>
        {renderSeasonalAnalysis()}
      </div>

      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={activeTab} index={3}>
        {renderTechnicalAnalysis()}
      </div>
    </div>
  );
};

export default CommoditiesEnhanced;