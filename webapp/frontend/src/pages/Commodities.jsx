import React, { useState, useMemo } from 'react';
import {
  Box,
  Typography,
  Container,
  Grid,
  Card,
  CardContent,
  Tabs,
  Tab,
  Chip,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  IconButton,
  TextField,
  InputAdornment,
  Button,
  Stack,
  Avatar,
  Tooltip,
  LinearProgress,
  Alert,
  Switch,
  FormControlLabel,
  MenuItem,
  Select,
  FormControl,
  InputLabel,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  useTheme,
  useMediaQuery
} from '@mui/material';
import {
  TrendingUp,
  TrendingDown,
  Search,
  Refresh,
  FilterList,
  ShowChart,
  Timeline,
  Assessment,
  Business,
  LocalFireDepartment,
  Agriculture,
  Factory,
  AttachMoney,
  ExpandMore,
  ViewList,
  GridView,
  Download,
  Share,
  Notifications,
  Star,
  StarBorder,
  TrendingFlat
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
  BarChart,
  Bar,
  Cell,
  ComposedChart,
  PieChart,
  Pie
} from 'recharts';
import { useSimpleFetch } from '../hooks/useSimpleFetch';
import { getApiConfig } from '../services/api';
import DataContainer from '../components/DataContainer';
import { format } from 'date-fns';

// API Configuration
const { apiUrl: API_BASE } = getApiConfig();

// Constants
const COMMODITY_COLORS = {
  energy: '#ff5722',
  'precious-metals': '#ffb300',
  'base-metals': '#607d8b',
  agriculture: '#43a047',
  livestock: '#795548'
};

const TIMEFRAMES = [
  { label: '1D', value: '1d' },
  { label: '1W', value: '1w' },
  { label: '1M', value: '1m' },
  { label: '3M', value: '3m' },
  { label: '1Y', value: '1y' }
];

// Custom hooks for commodity data
function useCommodityCategories() {
  return useSimpleFetch(`${API_BASE}/api/commodities/categories`, {
    enabled: true,
    retry: 1, // Reduced retries to prevent resource exhaustion
    staleTime: 300000, // 5 minutes
    fallback: [],
    errorMessage: 'Failed to load commodity categories'
  });
}

function useCommodityPrices(category = null, symbol = null) {
  const params = new URLSearchParams();
  if (category) params.append('category', category);
  if (symbol) params.append('symbol', symbol);
  
  return useSimpleFetch(`${API_BASE}/api/commodities/prices?${params.toString()}`, {
    enabled: true,
    retry: 2, // Reduced retries to prevent resource exhaustion
    staleTime: 60000, // Increased to 1 minute to reduce request frequency
    fallback: [],
    errorMessage: 'Failed to load commodity prices'
  });
}

function useCommodityMarketSummary() {
  return useSimpleFetch(`${API_BASE}/api/commodities/market-summary`, {
    enabled: true,
    retry: 1, // Reduced retries to prevent resource exhaustion
    staleTime: 120000, // Increased to 2 minutes
    fallback: null,
    errorMessage: 'Failed to load market summary'
  });
}

function useCommodityCorrelations() {
  return useSimpleFetch(`${API_BASE}/api/commodities/correlations`, {
    enabled: true,
    retry: 1, // Reduced retries to prevent resource exhaustion
    staleTime: 600000, // Increased to 10 minutes - correlations change slowly
    fallback: null,
    errorMessage: 'Failed to load correlations'
  });
}

// Utility functions
const getCommodityIcon = (category) => {
  const iconMap = {
    energy: <LocalFireDepartment />,
    'precious-metals': <AttachMoney />,
    'base-metals': <Factory />,
    agriculture: <Agriculture />,
    livestock: <Business />
  };
  return iconMap[category] || <Assessment />;
};

const formatPrice = (price, unit) => {
  if (!price || isNaN(price)) return '--';
  return `$${Number(price).toFixed(2)} ${unit || ''}`;
};

const getChangeColor = (change) => {
  const numChange = Number(change) || 0;
  if (numChange > 0) return 'success.main';
  if (numChange < 0) return 'error.main';
  return 'text.secondary';
};

const getChangeIcon = (change) => {
  const numChange = Number(change) || 0;
  if (numChange > 0) return <TrendingUp sx={{ fontSize: 16 }} />;
  if (numChange < 0) return <TrendingDown sx={{ fontSize: 16 }} />;
  return <TrendingFlat sx={{ fontSize: 16 }} />;
};

// Main Components
function CommoditiesHeader({ onSearch, onRefresh, searchTerm, isRefreshing }) {
  return (
    <Box sx={{ mb: 4 }}>
      <Box display="flex" alignItems="center" justifyContent="space-between" mb={3}>
        <Box>
          <Typography variant="h3" component="h1" gutterBottom sx={{ 
            fontWeight: 700, 
            background: 'linear-gradient(45deg, #ff5722, #ffb300)', 
            WebkitBackgroundClip: 'text', 
            WebkitTextFillColor: 'transparent' 
          }}>
            Commodities Market
          </Typography>
          <Typography variant="h6" color="text.secondary" sx={{ fontWeight: 500 }}>
            Real-time commodity prices, analysis, and market intelligence
          </Typography>
          <Box display="flex" gap={1} mt={1}>
            <Chip icon={<LocalFireDepartment />} label="Live Prices" color="success" size="small" />
            <Chip icon={<Assessment />} label="Technical Analysis" color="primary" size="small" />
            <Chip icon={<Timeline />} label="Correlations" color="warning" size="small" />
            <Chip icon={<ShowChart />} label="Futures Ready" color="info" size="small" />
          </Box>
        </Box>
        
        <Box display="flex" alignItems="center" gap={2}>
          <TextField
            size="small"
            placeholder="Search commodities..."
            value={searchTerm}
            onChange={(e) => onSearch(e.target.value)}
            InputProps={{
              startAdornment: (
                <InputAdornment position="start">
                  <Search />
                </InputAdornment>
              )
            }}
            sx={{ width: 250 }}
          />
          <Button
            variant="outlined"
            startIcon={<Refresh />}
            onClick={onRefresh}
            disabled={isRefreshing}
          >
            {isRefreshing ? 'Refreshing...' : 'Refresh'}
          </Button>
        </Box>
      </Box>
    </Box>
  );
}

function MarketSummaryBar({ summary }) {
  if (!summary?.overview) return null;
  
  const { overview, performance } = summary;
  
  return (
    <Card sx={{ mb: 3, background: 'linear-gradient(135deg, #1976d2 0%, #42a5f5 100%)', color: 'white' }}>
      <CardContent sx={{ py: 2 }}>
        <Grid container spacing={3} alignItems="center">
          <Grid item xs={12} md={3}>
            <Box>
              <Typography variant="body2" sx={{ opacity: 0.9 }}>Total Market Cap</Typography>
              <Typography variant="h6" fontWeight="bold">
                ${(overview.totalMarketCap / 1e12).toFixed(1)}T
              </Typography>
            </Box>
          </Grid>
          <Grid item xs={12} md={3}>
            <Box>
              <Typography variant="body2" sx={{ opacity: 0.9 }}>Daily Volume</Typography>
              <Typography variant="h6" fontWeight="bold">
                ${(overview.totalVolume / 1e9).toFixed(1)}B
              </Typography>
            </Box>
          </Grid>
          <Grid item xs={12} md={3}>
            <Box>
              <Typography variant="body2" sx={{ opacity: 0.9 }}>Active Contracts</Typography>
              <Typography variant="h6" fontWeight="bold">
                {overview.activeContracts?.toLocaleString()}
              </Typography>
            </Box>
          </Grid>
          <Grid item xs={12} md={3}>
            <Box>
              <Typography variant="body2" sx={{ opacity: 0.9 }}>Session Status</Typography>
              <Box display="flex" alignItems="center" gap={1}>
                <Box 
                  width={8} 
                  height={8} 
                  borderRadius="50%" 
                  bgcolor={overview.tradingSession === 'open' ? 'success.light' : 'warning.light'}
                  sx={{ animation: overview.tradingSession === 'open' ? 'pulse 2s infinite' : 'none' }}
                />
                <Typography variant="h6" fontWeight="bold">
                  {overview.tradingSession === 'open' ? 'Market Open' : 'Market Closed'}
                </Typography>
              </Box>
            </Box>
          </Grid>
        </Grid>
        
        {performance?.['1d'] && (
          <Box sx={{ mt: 2, pt: 2, borderTop: '1px solid rgba(255,255,255,0.2)' }}>
            <Grid container spacing={2}>
              <Grid item xs={4}>
                <Typography variant="body2" sx={{ opacity: 0.9 }}>Today's Gainers</Typography>
                <Typography variant="h6" color="success.light">
                  {performance['1d'].gainers}
                </Typography>
              </Grid>
              <Grid item xs={4}>
                <Typography variant="body2" sx={{ opacity: 0.9 }}>Today's Losers</Typography>
                <Typography variant="h6" color="error.light">
                  {performance['1d'].losers}
                </Typography>
              </Grid>
              <Grid item xs={4}>
                <Typography variant="body2" sx={{ opacity: 0.9 }}>Unchanged</Typography>
                <Typography variant="h6">
                  {performance['1d'].unchanged}
                </Typography>
              </Grid>
            </Grid>
          </Box>
        )}
      </CardContent>
    </Card>
  );
}

function CategoryNavigation({ categories, selectedCategory, onCategoryChange }) {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  
  if (isMobile) {
    return (
      <FormControl fullWidth sx={{ mb: 3 }}>
        <InputLabel>Category</InputLabel>
        <Select
          value={selectedCategory || 'all'}
          onChange={(e) => onCategoryChange(e.target.value === 'all' ? null : e.target.value)}
          label="Category"
        >
          <MenuItem value="all">All Categories</MenuItem>
          {categories.map((category) => (
            <MenuItem key={category.id} value={category.id}>
              <Box display="flex" alignItems="center" gap={1}>
                {getCommodityIcon(category.id)}
                {category.name}
              </Box>
            </MenuItem>
          ))}
        </Select>
      </FormControl>
    );
  }
  
  return (
    <Box sx={{ mb: 3 }}>
      <Tabs
        value={selectedCategory || 'all'}
        onChange={(_, value) => onCategoryChange(value === 'all' ? null : value)}
        variant="scrollable"
        scrollButtons="auto"
        sx={{
          '& .MuiTab-root': {
            minHeight: 64,
            textTransform: 'none',
            fontWeight: 600,
            fontSize: '0.95rem'
          }
        }}
      >
        <Tab
          value="all"
          label={
            <Box display="flex" alignItems="center" gap={1}>
              <GridView />
              All Categories
            </Box>
          }
        />
        {categories.map((category) => (
          <Tab
            key={category.id}
            value={category.id}
            label={
              <Box display="flex" alignItems="center" gap={1} flexDirection="column">
                <Box display="flex" alignItems="center" gap={1}>
                  {getCommodityIcon(category.id)}
                  {category.name}
                </Box>
                {category.performance && (
                  <Chip
                    label={`${category.performance['1d'] > 0 ? '+' : ''}${category.performance['1d']?.toFixed(1)}%`}
                    color={category.performance['1d'] > 0 ? 'success' : 'error'}
                    size="small"
                    sx={{ mt: 0.5, height: 20, fontSize: '0.7rem' }}
                  />
                )}
              </Box>
            }
          />
        ))}
      </Tabs>
    </Box>
  );
}

function CommodityPriceGrid({ prices, onSort, sortConfig, view }) {
  const PriceCard = React.memo(({ commodity }) => (
    <Card 
      sx={{ 
        height: '100%',
        cursor: 'pointer',
        transition: 'all 0.2s',
        '&:hover': { 
          transform: 'translateY(-2px)', 
          boxShadow: 4 
        },
        borderLeft: `4px solid ${COMMODITY_COLORS[commodity.category] || '#1976d2'}`
      }}
    >
      <CardContent>
        <Box display="flex" justifyContent="space-between" alignItems="start" mb={2}>
          <Box>
            <Typography variant="h6" fontWeight="bold">
              {commodity.symbol}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {commodity.name}
            </Typography>
          </Box>
          <Chip
            label={commodity.category?.replace('-', ' ')}
            size="small"
            sx={{ 
              bgcolor: COMMODITY_COLORS[commodity.category] || '#1976d2',
              color: 'white',
              textTransform: 'capitalize'
            }}
          />
        </Box>
        
        <Typography variant="h5" fontWeight="bold" color="primary.main" mb={1}>
          {formatPrice(commodity.price, commodity.unit)}
        </Typography>
        
        <Box display="flex" alignItems="center" justifyContent="space-between">
          <Box display="flex" alignItems="center" gap={1}>
            <Box sx={{ color: getChangeColor(commodity.change) }}>
              {getChangeIcon(commodity.change)}
            </Box>
            <Typography 
              variant="body2" 
              color={getChangeColor(commodity.change)}
              fontWeight="bold"
            >
              {(commodity.change || 0) > 0 ? '+' : ''}{(commodity.change || 0).toFixed(2)}
            </Typography>
            <Typography 
              variant="body2" 
              color={getChangeColor(commodity.changePercent)}
              fontWeight="bold"
            >
              ({(commodity.changePercent || 0) > 0 ? '+' : ''}{(commodity.changePercent || 0).toFixed(2)}%)
            </Typography>
          </Box>
          <IconButton size="small">
            <StarBorder />
          </IconButton>
        </Box>
        
        <Box sx={{ mt: 2, pt: 2, borderTop: '1px solid', borderColor: 'divider' }}>
          <Typography variant="caption" color="text.secondary">
            Volume: {(commodity.volume || 0).toLocaleString()}
          </Typography>
        </Box>
      </CardContent>
    </Card>
  ));

  const PriceTable = () => (
    <TableContainer component={Paper}>
      <Table>
        <TableHead>
          <TableRow>
            <TableCell>
              <Button
                onClick={() => onSort('symbol')}
                sx={{ textTransform: 'none', fontWeight: 'bold' }}
              >
                Symbol {sortConfig?.field === 'symbol' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
              </Button>
            </TableCell>
            <TableCell>Commodity</TableCell>
            <TableCell align="right">
              <Button
                onClick={() => onSort('price')}
                sx={{ textTransform: 'none', fontWeight: 'bold' }}
              >
                Price {sortConfig?.field === 'price' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
              </Button>
            </TableCell>
            <TableCell align="right">
              <Button
                onClick={() => onSort('change')}
                sx={{ textTransform: 'none', fontWeight: 'bold' }}
              >
                Change {sortConfig?.field === 'change' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
              </Button>
            </TableCell>
            <TableCell align="right">
              <Button
                onClick={() => onSort('volume')}
                sx={{ textTransform: 'none', fontWeight: 'bold' }}
              >
                Volume {sortConfig?.field === 'volume' && (sortConfig.direction === 'asc' ? '↑' : '↓')}
              </Button>
            </TableCell>
            <TableCell align="center">Actions</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {prices.map((commodity) => (
            <TableRow 
              key={commodity.symbol}
              sx={{ 
                '&:hover': { bgcolor: 'action.hover' },
                cursor: 'pointer'
              }}
            >
              <TableCell>
                <Box display="flex" alignItems="center" gap={1}>
                  <Avatar
                    sx={{ 
                      width: 32, 
                      height: 32, 
                      bgcolor: COMMODITY_COLORS[commodity.category] || '#1976d2',
                      fontSize: '0.8rem'
                    }}
                  >
                    {(commodity.symbol || '??').slice(0, 2).toUpperCase()}
                  </Avatar>
                  <Typography fontWeight="bold">{commodity.symbol}</Typography>
                </Box>
              </TableCell>
              <TableCell>
                <Box>
                  <Typography variant="body2" fontWeight="medium">
                    {commodity.name}
                  </Typography>
                  <Chip
                    label={commodity.category?.replace('-', ' ')}
                    size="small"
                    sx={{ textTransform: 'capitalize', mt: 0.5 }}
                  />
                </Box>
              </TableCell>
              <TableCell align="right">
                <Typography variant="body1" fontWeight="bold">
                  {formatPrice(commodity.price, commodity.unit)}
                </Typography>
              </TableCell>
              <TableCell align="right">
                <Box display="flex" alignItems="center" justifyContent="flex-end" gap={0.5}>
                  <Box sx={{ color: getChangeColor(commodity.change) }}>
                    {getChangeIcon(commodity.change)}
                  </Box>
                  <Box>
                    <Typography 
                      variant="body2" 
                      color={getChangeColor(commodity.change)}
                      fontWeight="bold"
                    >
                      {(commodity.change || 0) > 0 ? '+' : ''}{(commodity.change || 0).toFixed(2)}
                    </Typography>
                    <Typography 
                      variant="caption" 
                      color={getChangeColor(commodity.changePercent)}
                    >
                      ({(commodity.changePercent || 0) > 0 ? '+' : ''}{(commodity.changePercent || 0).toFixed(2)}%)
                    </Typography>
                  </Box>
                </Box>
              </TableCell>
              <TableCell align="right">
                <Typography variant="body2">
                  {commodity.volume?.toLocaleString()}
                </Typography>
              </TableCell>
              <TableCell align="center">
                <IconButton size="small" color="primary">
                  <Star />
                </IconButton>
                <IconButton size="small" color="secondary">
                  <ShowChart />
                </IconButton>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );

  if (view === 'grid') {
    return (
      <Grid container spacing={3}>
        {prices.map((commodity) => (
          <Grid item xs={12} sm={6} md={4} lg={3} key={commodity.symbol}>
            <PriceCard commodity={commodity} />
          </Grid>
        ))}
      </Grid>
    );
  }

  return <PriceTable />;
}

function CommodityChart({ symbol, timeframe, onTimeframeChange }) {
  const generatePriceHistory = (symbol, days = 30) => {
    const basePrice = {
      'CL': 78.45,
      'GC': 2034.20,
      'SI': 24.67,
      'HG': 3.89,
      'NG': 2.87,
      'ZW': 6.45
    }[symbol] || 100;

    const data = [];
    const now = new Date();
    
    for (let i = days; i >= 0; i--) {
      const date = new Date(now);
      date.setDate(date.getDate() - i);
      
      const volatility = 0.02 + (Math.random() * 0.02); // 2-4% daily volatility
      const change = (Math.random() - 0.5) * 2 * volatility;
      const price = i === days ? basePrice : data[data.length - 1]?.close || basePrice;
      const newPrice = price * (1 + change);
      
      data.push({
        date: date.getTime(),
        timestamp: date.toISOString().split('T')[0],
        open: newPrice * (1 + (Math.random() - 0.5) * 0.01),
        high: newPrice * (1 + Math.random() * 0.02),
        low: newPrice * (1 - Math.random() * 0.02),
        close: newPrice,
        volume: Math.floor(50000 + Math.random() * 100000)
      });
    }
    
    return data;
  };

  const { data: priceHistory, loading: historyLoading } = useSimpleFetch(
    `${API_BASE}/api/commodities/history/${symbol}?period=${timeframe}`,
    {
      enabled: !!symbol,
      retry: 1, // Reduced retries to prevent resource exhaustion
      staleTime: 120000, // Increased to 2 minutes
      fallback: generatePriceHistory(symbol, timeframe === '1d' ? 1 : timeframe === '1w' ? 7 : timeframe === '1m' ? 30 : timeframe === '3m' ? 90 : 365),
      errorMessage: 'Failed to load price history'
    }
  );

  const ChartComponent = ({ data, isFallbackData = false }) => {
    const chartData = Array.isArray(data) ? data : generatePriceHistory(symbol);
    
    return (
      <Card sx={{ height: '100%' }}>
        <CardContent>
          <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
            <Box display="flex" alignItems="center" gap={1}>
              <Timeline sx={{ color: 'primary.main' }} />
              <Typography variant="h6" fontWeight="bold">
                {symbol} Price Chart
              </Typography>
              <Chip 
                label={isFallbackData ? "Demo Data" : "Live"} 
                color={isFallbackData ? "warning" : "success"} 
                size="small" 
              />
            </Box>
            
            <Box display="flex" gap={1}>
              {TIMEFRAMES.map((tf) => (
                <Button
                  key={tf.value}
                  size="small"
                  variant={timeframe === tf.value ? 'contained' : 'outlined'}
                  onClick={() => onTimeframeChange(tf.value)}
                >
                  {tf.label}
                </Button>
              ))}
            </Box>
          </Box>
          
          <Box sx={{ height: 300 }}>
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={chartData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis 
                  dataKey="timestamp" 
                  tick={{ fontSize: 12 }}
                  tickFormatter={(value) => new Date(value).toLocaleDateString()}
                />
                <YAxis 
                  yAxisId="price"
                  orientation="left"
                  tick={{ fontSize: 12 }}
                  tickFormatter={(value) => `$${value.toFixed(2)}`}
                />
                <YAxis 
                  yAxisId="volume"
                  orientation="right"
                  tick={{ fontSize: 12 }}
                  tickFormatter={(value) => `${(value / 1000).toFixed(0)}K`}
                />
                <RechartsTooltip 
                  formatter={(value, name) => {
                    if (name === 'volume') return [`${(value / 1000).toFixed(0)}K`, 'Volume'];
                    return [`$${value.toFixed(2)}`, name];
                  }}
                  labelFormatter={(value) => new Date(value).toLocaleDateString()}
                />
                <Bar 
                  yAxisId="volume" 
                  dataKey="volume" 
                  fill="#8884d8" 
                  opacity={0.3}
                  name="volume"
                />
                <Line 
                  yAxisId="price"
                  type="monotone" 
                  dataKey="close" 
                  stroke="#ff7300" 
                  strokeWidth={2}
                  dot={false}
                  name="Price"
                />
              </ComposedChart>
            </ResponsiveContainer>
          </Box>
        </CardContent>
      </Card>
    );
  };

  return (
    <DataContainer
      loading={historyLoading}
      data={priceHistory}
      fallbackDataType="commodity_prices"
      context="price history"
    >
      <ChartComponent />
    </DataContainer>
  );
}

function CorrelationHeatmap({ correlations }) {
  const HeatmapComponent = ({ data, isFallbackData = false }) => {
    // Generate fallback correlation data if needed
    const fallbackData = {
      matrix: {
        'energy': { 'energy': 1.00, 'precious-metals': -0.23, 'base-metals': 0.47, 'agriculture': 0.12, 'livestock': 0.08 },
        'precious-metals': { 'energy': -0.23, 'precious-metals': 1.00, 'base-metals': 0.18, 'agriculture': -0.05, 'livestock': -0.02 },
        'base-metals': { 'energy': 0.47, 'precious-metals': 0.18, 'base-metals': 1.00, 'agriculture': 0.23, 'livestock': 0.15 },
        'agriculture': { 'energy': 0.12, 'precious-metals': -0.05, 'base-metals': 0.23, 'agriculture': 1.00, 'livestock': 0.34 },
        'livestock': { 'energy': 0.08, 'precious-metals': -0.02, 'base-metals': 0.15, 'agriculture': 0.34, 'livestock': 1.00 }
      }
    };

    const correlationData = data || fallbackData;
    const matrix = correlationData.matrix || {};
    const categories = Object.keys(matrix);

    const getCorrelationColor = (value) => {
      if (value > 0.5) return '#2e7d32'; // Strong positive - dark green
      if (value > 0.2) return '#66bb6a'; // Moderate positive - light green
      if (value > -0.2) return '#bdbdbd'; // Neutral - gray
      if (value > -0.5) return '#ef5350'; // Moderate negative - light red
      return '#c62828'; // Strong negative - dark red
    };

    const getTextColor = (value) => {
      return Math.abs(value) > 0.5 ? 'white' : 'black';
    };

    return (
      <Card sx={{ height: '100%' }}>
        <CardContent>
          <Box display="flex" alignItems="center" mb={2}>
            <Assessment sx={{ color: 'primary.main', mr: 1 }} />
            <Typography variant="h6" fontWeight="bold">
              Sector Correlations
            </Typography>
            <Chip 
              label={isFallbackData ? "Demo Data" : "Live"} 
              color={isFallbackData ? "warning" : "success"} 
              size="small" 
              sx={{ ml: 1 }}
            />
          </Box>
          
          <Typography variant="body2" color="text.secondary" mb={2}>
            90-day correlation matrix between commodity sectors
          </Typography>

          <Box sx={{ 
            display: 'grid', 
            gridTemplateColumns: `120px repeat(${categories.length}, 1fr)`,
            gap: 1,
            fontSize: '0.75rem'
          }}>
            {/* Header row */}
            <Box /> {/* Empty corner */}
            {categories.map((cat) => (
              <Box 
                key={cat} 
                sx={{ 
                  p: 1, 
                  textAlign: 'center', 
                  fontWeight: 'bold',
                  textTransform: 'capitalize',
                  fontSize: '0.7rem'
                }}
              >
                {cat.replace('-', ' ')}
              </Box>
            ))}
            
            {/* Data rows */}
            {categories.map((rowCat) => (
              <React.Fragment key={rowCat}>
                <Box sx={{ 
                  p: 1, 
                  fontWeight: 'bold',
                  textTransform: 'capitalize',
                  fontSize: '0.8rem',
                  display: 'flex',
                  alignItems: 'center'
                }}>
                  {rowCat.replace('-', ' ')}
                </Box>
                {categories.map((colCat) => {
                  const value = matrix[rowCat]?.[colCat] || 0;
                  return (
                    <Paper
                      key={`${rowCat}-${colCat}`}
                      elevation={1}
                      sx={{
                        p: 1,
                        textAlign: 'center',
                        bgcolor: getCorrelationColor(value),
                        color: getTextColor(value),
                        cursor: 'pointer',
                        transition: 'transform 0.2s',
                        '&:hover': {
                          transform: 'scale(1.05)',
                          zIndex: 1
                        }
                      }}
                    >
                      <Typography variant="caption" fontWeight="bold">
                        {value.toFixed(2)}
                      </Typography>
                    </Paper>
                  );
                })}
              </React.Fragment>
            ))}
          </Box>

          <Box sx={{ mt: 2, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Box display="flex" alignItems="center" gap={1}>
              <Box width={12} height={12} bgcolor="#c62828" />
              <Typography variant="caption">Strong Negative</Typography>
            </Box>
            <Box display="flex" alignItems="center" gap={1}>
              <Box width={12} height={12} bgcolor="#bdbdbd" />
              <Typography variant="caption">Neutral</Typography>
            </Box>
            <Box display="flex" alignItems="center" gap={1}>
              <Box width={12} height={12} bgcolor="#2e7d32" />
              <Typography variant="caption">Strong Positive</Typography>
            </Box>
          </Box>
        </CardContent>
      </Card>
    );
  };

  return (
    <DataContainer
      data={correlations}
      fallbackDataType="commodity_correlations"
      context="correlations"
    >
      <HeatmapComponent />
    </DataContainer>
  );
}

function CommodityNewsWidget() {
  const { data: newsData, loading: newsLoading, error: newsError } = useSimpleFetch(
    `${API_BASE}/api/commodities/news?limit=5`,
    {
      enabled: true,
      retry: 1, // Reduced retries to prevent resource exhaustion
      staleTime: 600000, // Increased to 10 minutes - news doesn't change that often
      fallback: [],
      errorMessage: 'Failed to load commodity news'
    }
  );

  const NewsComponent = ({ data, isFallbackData = false }) => {
    const fallbackNews = [
      {
        id: 'news-1',
        title: 'Oil Prices Surge on Supply Chain Concerns',
        summary: 'Crude oil futures climb as geopolitical tensions affect major shipping routes...',
        source: 'Commodity News',
        publishedAt: new Date().toISOString(),
        category: 'energy'
      },
      {
        id: 'news-2',
        title: 'Gold Holds Steady Amid Market Volatility',
        summary: 'Precious metals maintain strength as investors seek safe-haven assets...',
        source: 'Metal Markets',
        publishedAt: new Date(Date.now() - 3600000).toISOString(),
        category: 'precious-metals'
      },
      {
        id: 'news-3',
        title: 'Agricultural Commodities See Mixed Performance',
        summary: 'Weather patterns and seasonal factors drive varied outcomes across grain markets...',
        source: 'Agri Reports',
        publishedAt: new Date(Date.now() - 7200000).toISOString(),
        category: 'agriculture'
      }
    ];

    const news = Array.isArray(data) ? data : fallbackNews;

    return (
      <Card sx={{ height: '100%' }}>
        <CardContent>
          <Box display="flex" alignItems="center" mb={2}>
            <Business sx={{ color: 'primary.main', mr: 1 }} />
            <Typography variant="h6" fontWeight="bold">
              Commodity News
            </Typography>
            <Chip 
              label={isFallbackData ? "Demo Data" : "Live"} 
              color={isFallbackData ? "warning" : "success"} 
              size="small" 
              sx={{ ml: 1 }}
            />
          </Box>

          <Stack spacing={2}>
            {news.slice(0, 5).map((article, idx) => (
              <Paper 
                key={article.id || idx} 
                sx={{ 
                  p: 2, 
                  cursor: 'pointer',
                  transition: 'all 0.2s',
                  '&:hover': { 
                    bgcolor: 'action.hover',
                    transform: 'translateY(-1px)'
                  }
                }}
              >
                <Typography variant="subtitle2" fontWeight="bold" gutterBottom>
                  {article.title}
                </Typography>
                <Typography variant="body2" color="text.secondary" paragraph>
                  {article.summary}
                </Typography>
                <Box display="flex" justifyContent="space-between" alignItems="center">
                  <Typography variant="caption" color="text.secondary">
                    {article.source}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {format(new Date(article.publishedAt), 'MMM d, HH:mm')}
                  </Typography>
                </Box>
              </Paper>
            ))}
          </Stack>

          <Button 
            fullWidth 
            variant="outlined" 
            sx={{ mt: 2 }}
            onClick={() => window.open('/news?category=commodities', '_blank')}
          >
            View All Commodity News
          </Button>
        </CardContent>
      </Card>
    );
  };

  return (
    <DataContainer
      loading={newsLoading}
      error={newsError}
      data={newsData}
      fallbackDataType="news"
      fallbackCount={5}
      context="commodity news"
    >
      <NewsComponent />
    </DataContainer>
  );
}

const Commodities = () => {
  const [selectedCategory, setSelectedCategory] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [view, setView] = useState('grid');
  const [sortConfig, setSortConfig] = useState({ field: 'symbol', direction: 'asc' });
  const [timeframe, setTimeframe] = useState('1d');
  const [selectedSymbol, setSelectedSymbol] = useState('CL'); // Default to Crude Oil

  // Data fetching with controlled loading to prevent resource exhaustion
  const { data: categoriesData, loading: categoriesLoading, error: categoriesError, refetch: refetchCategories } = useCommodityCategories();
  const { data: pricesData, loading: pricesLoading, error: pricesError, refetch: refetchPrices } = useCommodityPrices(selectedCategory);
  
  // Load summary and correlations only after categories are loaded
  const { data: summaryData, loading: summaryLoading, error: summaryError, refetch: refetchSummary } = useCommodityMarketSummary();
  const { data: correlationsData, loading: correlationsLoading } = useCommodityCorrelations();

  // Data processing
  const categories = categoriesData?.data || [];
  const prices = pricesData?.data || [];
  const summary = summaryData?.data || null;
  const correlations = correlationsData?.data || null;

  // Filter and sort prices with defensive programming
  const filteredPrices = useMemo(() => {
    // Ensure prices is an array and filter out invalid entries
    let filtered = (prices || []).filter(commodity => 
      commodity && 
      typeof commodity === 'object' &&
      commodity.symbol &&
      commodity.name
    );

    // Filter by search term
    if (searchTerm) {
      filtered = filtered.filter(commodity =>
        (commodity.symbol || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
        (commodity.name || '').toLowerCase().includes(searchTerm.toLowerCase())
      );
    }

    // Sort
    if (sortConfig.field) {
      filtered.sort((a, b) => {
        const aVal = a[sortConfig.field];
        const bVal = b[sortConfig.field];
        
        if (typeof aVal === 'string') {
          return sortConfig.direction === 'asc' 
            ? aVal.localeCompare(bVal)
            : bVal.localeCompare(aVal);
        }
        
        return sortConfig.direction === 'asc' 
          ? (aVal || 0) - (bVal || 0)
          : (bVal || 0) - (aVal || 0);
      });
    }

    return filtered;
  }, [prices, searchTerm, sortConfig]);

  // Memoized calculations for performance
  const commodityCount = useMemo(() => filteredPrices.length, [filteredPrices]);
  
  const categoryChipsData = useMemo(() => 
    categories.map(category => ({
      ...category,
      performance: category.performance || {}
    })), [categories]
  );

  // Event handlers
  const handleRefreshAll = () => {
    refetchCategories();
    refetchPrices();
    refetchSummary();
  };

  const handleSort = (field) => {
    setSortConfig(prev => ({
      field,
      direction: prev.field === field && prev.direction === 'asc' ? 'desc' : 'asc'
    }));
  };

  const isLoading = categoriesLoading || pricesLoading || summaryLoading;

  return (
    <Container maxWidth="xl" sx={{ py: 3 }}>
      <CommoditiesHeader
        onSearch={setSearchTerm}
        onRefresh={handleRefreshAll}
        searchTerm={searchTerm}
        isRefreshing={isLoading}
      />

      <DataContainer
        loading={summaryLoading}
        error={summaryError}
        data={summaryData}
        fallbackDataType="commodity_summary"
        context="market summary"
      >
        <MarketSummaryBar summary={summary} />
      </DataContainer>

      <DataContainer
        loading={categoriesLoading}
        error={categoriesError}
        data={categoriesData}
        fallbackDataType="commodity_categories"
        context="categories"
      >
        <CategoryNavigation
          categories={categoryChipsData}
          selectedCategory={selectedCategory}
          onCategoryChange={setSelectedCategory}
        />
      </DataContainer>

      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Box display="flex" alignItems="center" gap={2}>
          <Typography variant="h6" fontWeight="bold">
            Market Data
          </Typography>
          <Chip 
            label={`${commodityCount} commodities`} 
            color="primary" 
            size="small" 
          />
        </Box>
        
        <Box display="flex" alignItems="center" gap={2}>
          <FormControl size="small" sx={{ minWidth: 120 }}>
            <InputLabel>Timeframe</InputLabel>
            <Select
              value={timeframe}
              onChange={(e) => setTimeframe(e.target.value)}
              label="Timeframe"
            >
              {TIMEFRAMES.map((tf) => (
                <MenuItem key={tf.value} value={tf.value}>
                  {tf.label}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          
          <Button
            variant={view === 'grid' ? 'contained' : 'outlined'}
            onClick={() => setView('grid')}
            startIcon={<GridView />}
            size="small"
          >
            Grid
          </Button>
          <Button
            variant={view === 'table' ? 'contained' : 'outlined'}
            onClick={() => setView('table')}
            startIcon={<ViewList />}
            size="small"
          >
            Table
          </Button>
        </Box>
      </Box>

      <DataContainer
        loading={pricesLoading}
        error={pricesError}
        data={pricesData}
        fallbackDataType="commodity_prices"
        fallbackCount={12}
        context="commodity prices"
        emptyMessage="No commodities found"
      >
        <CommodityPriceGrid
          prices={filteredPrices}
          onSort={handleSort}
          sortConfig={sortConfig}
          view={view}
        />
      </DataContainer>

      {/* Charts and Analysis Section */}
      <Grid container spacing={3} sx={{ mt: 3 }}>
        <Grid item xs={12} lg={8}>
          <CommodityChart
            symbol={selectedSymbol}
            timeframe={timeframe}
            onTimeframeChange={setTimeframe}
          />
        </Grid>
        <Grid item xs={12} lg={4}>
          <CommodityNewsWidget />
        </Grid>
      </Grid>

      {/* Correlation Analysis */}
      <Grid container spacing={3} sx={{ mt: 3 }}>
        <Grid item xs={12} md={6}>
          <CorrelationHeatmap correlations={correlations} />
        </Grid>
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" mb={2}>
                <ShowChart sx={{ color: 'primary.main', mr: 1 }} />
                <Typography variant="h6" fontWeight="bold">
                  Quick Actions
                </Typography>
              </Box>
              
              <Grid container spacing={2}>
                <Grid item xs={12}>
                  <FormControl fullWidth size="small">
                    <InputLabel>Select Commodity to Chart</InputLabel>
                    <Select
                      value={selectedSymbol}
                      onChange={(e) => setSelectedSymbol(e.target.value)}
                      label="Select Commodity to Chart"
                    >
                      {filteredPrices.map((commodity) => (
                        <MenuItem key={commodity.symbol} value={commodity.symbol}>
                          <Box display="flex" alignItems="center" gap={1}>
                            <Avatar
                              sx={{ 
                                width: 24, 
                                height: 24, 
                                bgcolor: COMMODITY_COLORS[commodity.category] || '#1976d2',
                                fontSize: '0.7rem'
                              }}
                            >
                              {(commodity.symbol || '??').slice(0, 2).toUpperCase()}
                            </Avatar>
                            {commodity.symbol || 'N/A'} - {commodity.name || 'Unknown'}
                          </Box>
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                </Grid>
                
                <Grid item xs={6}>
                  <Button
                    fullWidth
                    variant="contained"
                    startIcon={<Star />}
                    onClick={() => console.log('Add to watchlist:', selectedSymbol)}
                    sx={{ background: 'linear-gradient(45deg, #ff5722, #ffb300)' }}
                  >
                    Add to Watchlist
                  </Button>
                </Grid>
                <Grid item xs={6}>
                  <Button
                    fullWidth
                    variant="contained"
                    color="success"
                    startIcon={<ShowChart />}
                    onClick={() => console.log('Analyze:', selectedSymbol)}
                  >
                    Technical Analysis
                  </Button>
                </Grid>
                
                <Grid item xs={6}>
                  <Button
                    fullWidth
                    variant="outlined"
                    startIcon={<Download />}
                    onClick={() => console.log('Export data')}
                  >
                    Export Data
                  </Button>
                </Grid>
                <Grid item xs={6}>
                  <Button
                    fullWidth
                    variant="outlined"
                    startIcon={<Notifications />}
                    onClick={() => console.log('Set alert')}
                  >
                    Price Alert
                  </Button>
                </Grid>
              </Grid>

              <Box sx={{ mt: 3, p: 2, bgcolor: 'grey.50', borderRadius: 1 }}>
                <Typography variant="body2" color="text.secondary" gutterBottom>
                  Market Insights
                </Typography>
                <Typography variant="body2">
                  • Energy commodities showing mixed performance with supply concerns
                </Typography>
                <Typography variant="body2">
                  • Precious metals maintaining safe-haven demand
                </Typography>
                <Typography variant="body2">
                  • Agricultural markets influenced by weather patterns
                </Typography>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Container>
  );
};

export default Commodities;