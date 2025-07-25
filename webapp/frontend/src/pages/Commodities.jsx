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
    retry: 3,
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
    retry: 3,
    staleTime: 30000, // 30 seconds for prices
    refreshInterval: 5000, // Real-time updates every 5 seconds
    fallback: [],
    errorMessage: 'Failed to load commodity prices'
  });
}

function useCommodityMarketSummary() {
  return useSimpleFetch(`${API_BASE}/api/commodities/market-summary`, {
    enabled: true,
    retry: 3,
    staleTime: 60000, // 1 minute
    fallback: null,
    errorMessage: 'Failed to load market summary'
  });
}

function useCommodityCorrelations() {
  return useSimpleFetch(`${API_BASE}/api/commodities/correlations`, {
    enabled: true,
    retry: 3,
    staleTime: 300000, // 5 minutes
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
  if (!price) return '--';
  return `$${price.toFixed(2)} ${unit || ''}`;
};

const getChangeColor = (change) => {
  if (change > 0) return 'success.main';
  if (change < 0) return 'error.main';
  return 'text.secondary';
};

const getChangeIcon = (change) => {
  if (change > 0) return <TrendingUp sx={{ fontSize: 16 }} />;
  if (change < 0) return <TrendingDown sx={{ fontSize: 16 }} />;
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
  const PriceCard = ({ commodity }) => (
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
              {commodity.change > 0 ? '+' : ''}{commodity.change?.toFixed(2)}
            </Typography>
            <Typography 
              variant="body2" 
              color={getChangeColor(commodity.changePercent)}
              fontWeight="bold"
            >
              ({commodity.changePercent > 0 ? '+' : ''}{commodity.changePercent?.toFixed(2)}%)
            </Typography>
          </Box>
          <IconButton size="small">
            <StarBorder />
          </IconButton>
        </Box>
        
        <Box sx={{ mt: 2, pt: 2, borderTop: '1px solid', borderColor: 'divider' }}>
          <Typography variant="caption" color="text.secondary">
            Volume: {commodity.volume?.toLocaleString()}
          </Typography>
        </Box>
      </CardContent>
    </Card>
  );

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
                    {commodity.symbol.slice(0, 2)}
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
                      {commodity.change > 0 ? '+' : ''}{commodity.change?.toFixed(2)}
                    </Typography>
                    <Typography 
                      variant="caption" 
                      color={getChangeColor(commodity.changePercent)}
                    >
                      ({commodity.changePercent > 0 ? '+' : ''}{commodity.changePercent?.toFixed(2)}%)
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

const Commodities = () => {
  const [selectedCategory, setSelectedCategory] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [view, setView] = useState('grid');
  const [sortConfig, setSortConfig] = useState({ field: 'symbol', direction: 'asc' });
  const [timeframe, setTimeframe] = useState('1d');

  // Data fetching
  const { data: categoriesData, loading: categoriesLoading, error: categoriesError, refetch: refetchCategories } = useCommodityCategories();
  const { data: pricesData, loading: pricesLoading, error: pricesError, refetch: refetchPrices } = useCommodityPrices(selectedCategory);
  const { data: summaryData, loading: summaryLoading, error: summaryError, refetch: refetchSummary } = useCommodityMarketSummary();
  const { data: correlationsData, loading: correlationsLoading } = useCommodityCorrelations();

  // Data processing
  const categories = categoriesData?.data || [];
  const prices = pricesData?.data || [];
  const summary = summaryData?.data || null;
  const correlations = correlationsData?.data || null;

  // Filter and sort prices
  const filteredPrices = useMemo(() => {
    let filtered = prices;

    // Filter by search term
    if (searchTerm) {
      filtered = filtered.filter(commodity =>
        commodity.symbol.toLowerCase().includes(searchTerm.toLowerCase()) ||
        commodity.name.toLowerCase().includes(searchTerm.toLowerCase())
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
          categories={categories}
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
            label={`${filteredPrices.length} commodities`} 
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
    </Container>
  );
};

export default Commodities;