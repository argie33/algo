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
      {value === index && <Box sx={{ py: 3 }}>{children}</Box>}
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
      <Card 
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
        <CardHeader
          avatar={
            <Avatar sx={{ bgcolor: category.color, width: 48, height: 48 }}>
              <Icon sx={{ fontSize: 28 }} />
            </Avatar>
          }
          title={
            <Box display="flex" alignItems="center" gap={1}>
              <Typography variant="h6" fontWeight="bold">
                {category.name}
              </Typography>
              <Chip 
                label={`${avgChange >= 0 ? '+' : ''}${avgChange.toFixed(2)}%`}
                size="small"
                sx={{ 
                  backgroundColor: avgChange >= 0 ? COLORS.success : COLORS.error,
                  color: 'white',
                  fontWeight: 'bold'
                }}
              />
            </Box>
          }
          subheader={category.description}
        />
        <CardContent>
          <Stack spacing={2}>
            <Box display="flex" justifyContent="space-between" alignItems="center">
              <Typography variant="body2" color="textSecondary">
                {data.length} commodities
              </Typography>
              <Box display="flex" gap={1}>
                <Chip 
                  label={`${gainers} ↑`} 
                  size="small" 
                  color="success" 
                  variant="outlined"
                />
                <Chip 
                  label={`${losers} ↓`} 
                  size="small" 
                  color="error" 
                  variant="outlined"
                />
              </Box>
            </Box>
            
            <Box>
              <Typography variant="caption" color="textSecondary">
                Key Factors:
              </Typography>
              <Typography variant="body2" sx={{ mt: 0.5 }}>
                {category.keyFactors.slice(0, 2).join(', ')}
              </Typography>
            </Box>
            
            <LinearProgress
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
          </Stack>
        </CardContent>
      </Card>
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
      <Card sx={{ mb: 2, border: `1px solid ${strength.color + '4D'}` }}>
        <CardContent>
          <Box display="flex" alignItems="center" gap={2} mb={1}>
            <SignalIcon sx={{ color: strength.color }} />
            <Chip 
              label={signal.signal}
              size="small"
              sx={{ 
                backgroundColor: signal.signal === 'BUY' ? COLORS.success : COLORS.error,
                color: 'white',
                fontWeight: 'bold'
              }}
            />
            <Chip 
              label={signal.strength}
              size="small"
              sx={{ 
                backgroundColor: strength.color,
                color: 'white'
              }}
            />
            <Chip 
              label={signal.timeframe}
              size="small"
              variant="outlined"
            />
            <Box ml="auto">
              <Typography variant="caption" color="textSecondary">
                Confidence: {signal.confidence}%
              </Typography>
            </Box>
          </Box>
          <Typography variant="body2" sx={{ mb: 1 }}>
            {signal.reason}
          </Typography>
          <LinearProgress 
            variant="determinate" 
            value={signal.confidence} 
            sx={{
              height: 4,
              borderRadius: 2,
              backgroundColor: alpha(strength.color, 0.2),
              '& .MuiLinearProgress-bar': {
                backgroundColor: strength.color,
                borderRadius: 2
              }
            }}
          />
        </CardContent>
      </Card>
    </motion.div>
  );
};

// Professional price table component
const PriceTable = ({ data, loading, onRowClick }) => {
  
  if (loading) {
    return (
      <Box sx={{ p: 3 }}>
        {[...Array(8)].map((_, i) => (
          <Box key={i} sx={{ mb: 2 }}>
            <Skeleton variant="rectangular" height={60} />
          </Box>
        ))}
      </Box>
    );
  }
  
  return (
    <TableContainer>
      <Table>
        <TableHead>
          <TableRow>
            <TableCell>
              <Typography variant="subtitle2" fontWeight="bold">
                Commodity
              </Typography>
            </TableCell>
            <TableCell align="right">
              <Typography variant="subtitle2" fontWeight="bold">
                Price
              </Typography>
            </TableCell>
            <TableCell align="right">
              <Typography variant="subtitle2" fontWeight="bold">
                Change
              </Typography>
            </TableCell>
            <TableCell align="right">
              <Typography variant="subtitle2" fontWeight="bold">
                % Change
              </Typography>
            </TableCell>
            <TableCell align="center">
              <Typography variant="subtitle2" fontWeight="bold">
                Trend
              </Typography>
            </TableCell>
            <TableCell align="center">
              <Typography variant="subtitle2" fontWeight="bold">
                Score
              </Typography>
            </TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {data.map((item, index) => (
            <motion.tr
              key={item.symbol}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: index * 0.1 }}
              style={{ cursor: 'pointer' }}
              onClick={() => onRowClick(item)}
            >
              <TableCell>
                <Box display="flex" alignItems="center" gap={2}>
                  <Avatar 
                    sx={{ 
                      width: 32, 
                      height: 32,
                      bgcolor: getCommodityColor(item.symbol),
                      fontSize: 12,
                      fontWeight: 'bold'
                    }}
                  >
                    {item.symbol.slice(0, 2)}
                  </Avatar>
                  <Box>
                    <Typography variant="body2" fontWeight="medium">
                      {item.name}
                    </Typography>
                    <Typography variant="caption" color="textSecondary">
                      {item.symbol}
                    </Typography>
                  </Box>
                </Box>
              </TableCell>
              <TableCell align="right">
                <Typography variant="body2" fontWeight="bold">
                  ${item.price?.toFixed(2)}
                </Typography>
              </TableCell>
              <TableCell align="right">
                <Typography 
                  variant="body2" 
                  sx={{ 
                    color: (item.change_amount || 0) >= 0 ? COLORS.success : COLORS.error,
                    fontWeight: 'medium'
                  }}
                >
                  {(item.change_amount || 0) >= 0 ? '+' : ''}{item.change_amount?.toFixed(3)}
                </Typography>
              </TableCell>
              <TableCell align="right">
                <Chip
                  label={`${(item.change_percent || 0) >= 0 ? '+' : ''}${item.change_percent?.toFixed(2)}%`}
                  size="small"
                  sx={{
                    backgroundColor: (item.change_percent || 0) >= 0 ? COLORS.success : COLORS.error,
                    color: 'white',
                    fontWeight: 'bold'
                  }}
                />
              </TableCell>
              <TableCell align="center">
                {(item.change_percent || 0) > 0 ? (
                  <TrendingUp sx={{ color: COLORS.success }} />
                ) : (
                  <TrendingDown sx={{ color: COLORS.error }} />
                )}
              </TableCell>
              <TableCell align="center">
                <Box display="flex" alignItems="center" justifyContent="center" gap={1}>
                  <CircularProgress
                    variant="determinate"
                    value={item.overall_score || 50}
                    size={32}
                    thickness={4}
                    sx={{
                      color: getScoreColor(item.overall_score || 50),
                    }}
                  />
                  <Typography variant="caption" fontWeight="bold">
                    {item.overall_score || 50}
                  </Typography>
                </Box>
              </TableCell>
            </motion.tr>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
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
      <Grid container spacing={3}>
        {/* Header */}
        <Grid item xs={12}>
          <Box display="flex" alignItems="center" justifyContent="space-between" mb={2}>
            <Typography variant="h4" fontWeight="bold" sx={{ 
              background: `linear-gradient(45deg, ${COLORS.primary}, ${COLORS.secondary})`,
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              display: 'flex',
              alignItems: 'center',
              gap: 1
            }}>
              <Assessment />
              Commodities Trading Dashboard
            </Typography>
            <Box display="flex" gap={1}>
              <FormControlLabel
                control={<Switch checked={autoRefresh} onChange={(e) => setAutoRefresh(e.target.checked)} />}
                label="Auto Refresh"
              />
              <IconButton onClick={handleRefresh} color="primary">
                <Refresh />
              </IconButton>
            </Box>
          </Box>
        </Grid>
        
        {/* Category Cards */}
        {Object.entries(COMMODITY_CATEGORIES).map(([key, category]) => {
          const categoryData = pricesData.filter(item => {
            return category.commodities.includes(item.symbol);
          });
          
          return (
            <Grid item xs={12} sm={6} md={4} lg={2} key={key}>
              <CommodityCard 
                category={category}
                data={categoryData}
                onClick={handleCategorySelect}
                isSelected={selectedCategory?.name === category.name}
              />
            </Grid>
          );
        })}

        {/* Live Price Table */}
        <Grid item xs={12}>
          <Card>
            <CardHeader 
              title={
                <Box display="flex" alignItems="center" gap={1}>
                  <ShowChart />
                  Live Commodity Prices
                  <Badge 
                    badgeContent={pricesData.length} 
                    color="primary"
                    sx={{ ml: 1 }}
                  />
                </Box>
              }
              action={
                <Chip 
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
            <CardContent sx={{ p: 0 }}>
              <PriceTable 
                data={pricesData} 
                loading={loading} 
                onRowClick={handleCommoditySelect}
              />
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </motion.div>
  );

  const renderCOTAnalysis = () => (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
    >
      <Grid container spacing={3}>
        {/* Header */}
        <Grid item xs={12}>
          <Box display="flex" alignItems="center" justifyContent="space-between" mb={2}>
            <Typography variant="h5" fontWeight="bold" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <BarChart />
              Commitment of Traders Analysis
            </Typography>
            <FormControl sx={{ minWidth: 200 }}>
              <InputLabel>Select Commodity</InputLabel>
              <Select
                value={selectedCommodity}
                onChange={(e) => setSelectedCommodity(e.target.value)}
                label="Select Commodity"
              >
                {pricesData.map((item) => (
                  <MenuItem key={item.symbol} value={item.symbol}>
                    {item.symbol} - {item.name}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Box>
          <Alert severity="info" sx={{ mb: 3 }}>
            <Typography variant="subtitle2">Understanding COT Data</Typography>
            <Typography variant="body2">
              Commercial traders are typically producers and consumers (smart money). 
              Non-commercial traders are speculators and hedge funds. When commercials are net long, 
              it's generally bullish; when net short, it's bearish.
            </Typography>
          </Alert>
        </Grid>

        {/* COT Charts */}
        <Grid item xs={12} md={8}>
          <Card>
            <CardHeader 
              title="Net Positions Over Time"
              subheader="Commercial vs Non-Commercial Positioning"
            />
            <CardContent>
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
            </CardContent>
          </Card>
        </Grid>

        {/* COT Summary */}
        <Grid item xs={12} md={4}>
          <Card>
            <CardHeader title="Current COT Analysis" />
            <CardContent>
              <Stack spacing={3}>
                {cotData.length > 0 && (
                  <>
                    <Box>
                      <Typography variant="subtitle2" gutterBottom>
                        Commercial Net Position
                      </Typography>
                      <Box display="flex" alignItems="center" gap={1}>
                        <Typography variant="h6" color={cotData[0].commercial_net > 0 ? "success.main" : "error.main"}>
                          {cotData[0].commercial_net > 0 ? '+' : ''}{cotData[0].commercial_net?.toLocaleString()}
                        </Typography>
                        <Chip 
                          label={cotData[0].commercial_net > 0 ? "Bullish" : "Bearish"} 
                          size="small" 
                          color={cotData[0].commercial_net > 0 ? "success" : "error"}
                        />
                      </Box>
                      <Typography variant="caption" color="textSecondary">
                        {cotData[0].commercial_net_pct?.toFixed(1)}% of open interest
                      </Typography>
                    </Box>

                    <Divider />

                    <Box>
                      <Typography variant="subtitle2" gutterBottom>
                        Non-Commercial Net Position
                      </Typography>
                      <Box display="flex" alignItems="center" gap={1}>
                        <Typography variant="h6" color={cotData[0].non_commercial_net > 0 ? "success.main" : "error.main"}>
                          {cotData[0].non_commercial_net > 0 ? '+' : ''}{cotData[0].non_commercial_net?.toLocaleString()}
                        </Typography>
                        <Chip 
                          label={cotData[0].non_commercial_net > 0 ? "Long" : "Short"} 
                          size="small" 
                          color={cotData[0].non_commercial_net > 0 ? "success" : "error"}
                        />
                      </Box>
                      <Typography variant="caption" color="textSecondary">
                        {cotData[0].non_commercial_net_pct?.toFixed(1)}% of open interest
                      </Typography>
                    </Box>

                    <Divider />

                    <Box>
                      <Typography variant="subtitle2" gutterBottom>
                        Smart Money Signal
                      </Typography>
                      <Box display="flex" alignItems="center" gap={1}>
                        <CheckCircle sx={{ color: 'success.main' }} />
                        <Typography variant="body2">
                          {cotData[0].commercial_net > 0 
                            ? "Commercial traders are net long, suggesting bullish outlook"
                            : "Commercial traders are net short, suggesting bearish outlook"
                          }
                        </Typography>
                      </Box>
                    </Box>
                  </>
                )}
              </Stack>
            </CardContent>
          </Card>
        </Grid>

        {/* Trading Signals */}
        <Grid item xs={12}>
          <Card>
            <CardHeader 
              title={
                <Box display="flex" alignItems="center" gap={1}>
                  <SignalCellular4Bar />
                  Trading Signals
                  <Badge badgeContent={tradingSignals.length} color="primary" />
                </Box>
              }
            />
            <CardContent>
              {tradingSignals.length > 0 ? (
                <Grid container spacing={2}>
                  {tradingSignals.map((signal, index) => (
                    <Grid item xs={12} md={6} key={index}>
                      <TradingSignal signal={signal} />
                    </Grid>
                  ))}
                </Grid>
              ) : (
                <Box textAlign="center" py={4}>
                  <Typography variant="h6" color="textSecondary">
                    No trading signals available
                  </Typography>
                  <Typography variant="body2" color="textSecondary">
                    Select a commodity to view analysis
                  </Typography>
                </Box>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </motion.div>
  );

  const renderSeasonalAnalysis = () => (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
    >
      <Grid container spacing={3}>
        {/* Header */}
        <Grid item xs={12}>
          <Box display="flex" alignItems="center" justifyContent="space-between" mb={2}>
            <Typography variant="h5" fontWeight="bold" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Timeline />
              Seasonal Analysis & Patterns
            </Typography>
            <FormControl sx={{ minWidth: 200 }}>
              <InputLabel>Select Commodity</InputLabel>
              <Select
                value={selectedCommodity}
                onChange={(e) => setSelectedCommodity(e.target.value)}
                label="Select Commodity"
              >
                {pricesData.map((item) => (
                  <MenuItem key={item.symbol} value={item.symbol}>
                    {item.symbol} - {item.name}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Box>
        </Grid>

        {/* Seasonal Chart */}
        <Grid item xs={12} md={8}>
          <Card>
            <CardHeader 
              title="Seasonal Performance Patterns"
              subheader="Historical win rates and average returns by month"
            />
            <CardContent>
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
            </CardContent>
          </Card>
        </Grid>

        {/* Seasonal Insights */}
        <Grid item xs={12} md={4}>
          <Card>
            <CardHeader title="Seasonal Insights" />
            <CardContent>
              <Stack spacing={2}>
                {seasonalityData.length > 0 ? (
                  <>
                    {/* Current month highlight */}
                    {(() => {
                      const currentMonth = new Date().getMonth() + 1;
                      const currentSeasonality = seasonalityData.find(s => s.month === currentMonth);
                      return currentSeasonality ? (
                        <Alert severity={currentSeasonality.strength === 'Strong' ? 'success' : 
                                       currentSeasonality.strength === 'Moderate' ? 'info' : 'warning'}>
                          <Typography variant="subtitle2">Current Month ({currentSeasonality.month_name})</Typography>
                          <Typography variant="body2">
                            Win Rate: {currentSeasonality.win_rate?.toFixed(1)}% | 
                            Avg Return: {currentSeasonality.avg_return_pct?.toFixed(2)}%
                          </Typography>
                        </Alert>
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
                          <Alert severity="success">
                            <Typography variant="subtitle2">Best Month: {bestMonth.month_name}</Typography>
                            <Typography variant="body2">
                              Win Rate: {bestMonth.win_rate?.toFixed(1)}% | 
                              Avg Return: {bestMonth.avg_return_pct?.toFixed(2)}%
                            </Typography>
                          </Alert>
                          
                          <Alert severity="error">
                            <Typography variant="subtitle2">Worst Month: {worstMonth.month_name}</Typography>
                            <Typography variant="body2">
                              Win Rate: {worstMonth.win_rate?.toFixed(1)}% | 
                              Avg Return: {worstMonth.avg_return_pct?.toFixed(2)}%
                            </Typography>
                          </Alert>
                        </>
                      );
                    })()}
                  </>
                ) : (
                  <Typography variant="body2" color="textSecondary">
                    No seasonal data available for selected commodity
                  </Typography>
                )}
              </Stack>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </motion.div>
  );

  const renderTechnicalAnalysis = () => (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
    >
      <Grid container spacing={3}>
        {/* Header and Controls */}
        <Grid item xs={12}>
          <Box display="flex" alignItems="center" justifyContent="space-between" mb={2}>
            <Typography variant="h5" fontWeight="bold" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <ShowChart />
              Technical Analysis & Metrics
            </Typography>
            <Box display="flex" gap={2}>
              <FormControl sx={{ minWidth: 150 }}>
                <InputLabel>Commodity</InputLabel>
                <Select
                  value={selectedCommodity}
                  onChange={(e) => setSelectedCommodity(e.target.value)}
                  label="Commodity"
                >
                  {pricesData.map((item) => (
                    <MenuItem key={item.symbol} value={item.symbol}>
                      {item.symbol} - {item.name}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>

              <ButtonGroup variant="outlined">
                {['1D', '1W', '1M', '3M', '6M', '1Y'].map((timeframe) => (
                  <Button
                    key={timeframe}
                    variant={selectedTimeframe === timeframe ? 'contained' : 'outlined'}
                    onClick={() => setSelectedTimeframe(timeframe)}
                    size="small"
                  >
                    {timeframe}
                  </Button>
                ))}
              </ButtonGroup>
            </Box>
          </Box>
        </Grid>

        {/* Price Chart */}
        <Grid item xs={12} md={8}>
          <Card>
            <CardHeader title={`${selectedCommodity} Price Chart`} />
            <CardContent>
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
            </CardContent>
          </Card>
        </Grid>

        {/* Technical Indicators */}
        <Grid item xs={12} md={4}>
          <Card>
            <CardHeader title="Technical Indicators" />
            <CardContent>
              <Stack spacing={3}>
                {commodityMetrics ? (
                  <>
                    <Box>
                      <Typography variant="subtitle2">RSI (14)</Typography>
                      <Box display="flex" alignItems="center" gap={1}>
                        <Typography variant="h6">{commodityMetrics.rsi?.toFixed(1)}</Typography>
                        <Chip 
                          label={commodityMetrics.rsi < 30 ? "Oversold" : 
                                 commodityMetrics.rsi > 70 ? "Overbought" : "Neutral"} 
                          size="small" 
                          color={commodityMetrics.rsi < 30 ? "success" : 
                                 commodityMetrics.rsi > 70 ? "error" : "default"}
                        />
                      </Box>
                      <LinearProgress 
                        variant="determinate" 
                        value={commodityMetrics.rsi} 
                        sx={{ mt: 1 }}
                      />
                    </Box>

                    <Box>
                      <Typography variant="subtitle2">Price Position (52W)</Typography>
                      <Box display="flex" alignItems="center" gap={1}>
                        <Typography variant="h6">{(commodityMetrics.price_position_52w * 100)?.toFixed(1)}%</Typography>
                        <Chip 
                          label={commodityMetrics.price_position_52w < 0.3 ? "Near Lows" : 
                                 commodityMetrics.price_position_52w > 0.7 ? "Near Highs" : "Mid-Range"} 
                          size="small" 
                          color={commodityMetrics.price_position_52w < 0.3 ? "success" : 
                                 commodityMetrics.price_position_52w > 0.7 ? "error" : "default"}
                        />
                      </Box>
                      <LinearProgress 
                        variant="determinate" 
                        value={commodityMetrics.price_position_52w * 100} 
                        sx={{ mt: 1 }}
                      />
                    </Box>

                    <Box>
                      <Typography variant="subtitle2">Overall Score</Typography>
                      <Box display="flex" alignItems="center" gap={1}>
                        <CircularProgress
                          variant="determinate"
                          value={commodityMetrics.overall_score}
                          size={40}
                          thickness={4}
                          sx={{ color: getScoreColor(commodityMetrics.overall_score) }}
                        />
                        <Typography variant="h6">{commodityMetrics.overall_score}</Typography>
                      </Box>
                    </Box>

                    <Box>
                      <Typography variant="subtitle2">Support/Resistance</Typography>
                      <Typography variant="body2" color="error.main">
                        Support: ${commodityMetrics.support_level?.toFixed(2)}
                      </Typography>
                      <Typography variant="body2" color="success.main">
                        Resistance: ${commodityMetrics.resistance_level?.toFixed(2)}
                      </Typography>
                    </Box>

                    <Box>
                      <Typography variant="subtitle2">Volatility (Annual)</Typography>
                      <Typography variant="h6">{commodityMetrics.volatility_annual?.toFixed(1)}%</Typography>
                      <LinearProgress 
                        variant="determinate" 
                        value={Math.min(commodityMetrics.volatility_annual, 100)} 
                        sx={{ mt: 1 }}
                      />
                    </Box>
                  </>
                ) : (
                  <Typography variant="body2" color="textSecondary">
                    Loading technical indicators...
                  </Typography>
                )}
              </Stack>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </motion.div>
  );

  if (error) {
    return (
      <Container maxWidth="xl" sx={{ py: 3 }}>
        <Alert severity="error" sx={{ mb: 3 }}>
          <Typography variant="h6">Error Loading Data</Typography>
          <Typography variant="body2">{String(error)}</Typography>
        </Alert>
      </Container>
    );
  }

  return (
    <Container maxWidth="xl" sx={{ py: 3 }}>
      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
        <Tabs 
          value={activeTab} 
          onChange={(_, newValue) => setActiveTab(newValue)}
          variant="scrollable"
          scrollButtons="auto"
        >
          <Tab label="Market Overview" icon={<Assessment />} />
          <Tab label="COT Analysis" icon={<BarChart />} />
          <Tab label="Seasonal Patterns" icon={<Timeline />} />
          <Tab label="Technical Analysis" icon={<ShowChart />} />
        </Tabs>
      </Box>

      <TabPanel value={activeTab} index={0}>
        {renderMarketOverview()}
      </TabPanel>

      <TabPanel value={activeTab} index={1}>
        {renderCOTAnalysis()}
      </TabPanel>

      <TabPanel value={activeTab} index={2}>
        {renderSeasonalAnalysis()}
      </TabPanel>

      <TabPanel value={activeTab} index={3}>
        {renderTechnicalAnalysis()}
      </TabPanel>
    </Container>
  );
};

export default CommoditiesEnhanced;