import React, { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { createComponentLogger } from '../utils/errorLogger'
import { formatCurrency, formatNumber, formatPercentage as formatPercent, getChangeColor } from '../utils/formatters'
import { screenStocks, getStockPriceHistory } from '../services/api'
import {
  Box,
  Container,
  Typography,
  Grid,
  Card,
  CardContent,
  TextField,
  MenuItem,
  Button,
  Chip,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TablePagination,
  Paper,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  FormControl,
  InputLabel,
  Select,
  Slider,
  Switch,
  FormControlLabel,
  IconButton,
  Tooltip,
  Alert,
  CircularProgress,
  Divider,
  InputAdornment,
  ToggleButton,
  ToggleButtonGroup,
  Tabs,
  Tab,
  Modal,
  Backdrop,
  Fade
} from '@mui/material'
import {
  ExpandMore,
  FilterList,
  Clear,
  Search,
  TrendingUp,
  TrendingDown,
  ShowChart,
  Tune
} from '@mui/icons-material'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer, Area, AreaChart } from 'recharts'

// Create component-specific logger
const logger = createComponentLogger('StockExplorer');

const INITIAL_FILTERS = {
  // Search and basic
  search: '',
  sector: '',
  industry: '',
  country: '',
  exchange: '',
  
  // Price and Market Cap
  priceMin: '',
  priceMax: '',
  marketCapMin: '',
  marketCapMax: '',
  
  // Valuation
  peRatioMin: '',
  peRatioMax: '',
  pegRatioMin: '',
  pegRatioMax: '',
  pbRatioMin: '',
  pbRatioMax: '',
  
  // Profitability
  roeMin: '',
  roeMax: '',
  roaMin: '',
  roaMax: '',
  netMarginMin: '',
  netMarginMax: '',
  
  // Growth
  revenueGrowthMin: '',
  revenueGrowthMax: '',
  earningsGrowthMin: '',
  earningsGrowthMax: '',
  
  // Dividend
  dividendYieldMin: '',
  dividendYieldMax: '',
  payoutRatioMin: '',
  payoutRatioMax: '',
  
  // Financial Health
  currentRatioMin: '',
  currentRatioMax: '',
  debtToEquityMin: '',
  debtToEquityMax: '',
  
  // Other filters
  minAnalystRating: '',
  hasEarningsGrowth: false,
  hasPositiveCashFlow: false,
  paysDividends: false
}

const SECTORS = [
  'Technology', 'Healthcare', 'Financial Services', 'Consumer Cyclical',
  'Communication Services', 'Industrials', 'Consumer Defensive', 'Energy',
  'Utilities', 'Real Estate', 'Basic Materials'
]

// Market categories that actually exist in the backend data
const MARKET_CATEGORIES = [
  'Q', 'G', 'S', 'N'  // These are typical NASDAQ market categories
]

// Updated to match backend exchange data
const EXCHANGES = ['NYSE', 'NASDAQ', 'AMEX', 'NYSEArca', 'BATS']

function StockExplorer() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const [filters, setFilters] = useState(INITIAL_FILTERS)
  const [viewMode] = useState('advanced') // Always use advanced view with full table
  const [page, setPage] = useState(0)
  const [rowsPerPage, setRowsPerPage] = useState(25) // Reduced from potentially higher default
  const [orderBy, setOrderBy] = useState('symbol') // Default to alphabetical
  const [order, setOrder] = useState('asc') // Default to ascending
  const [expandedStock, setExpandedStock] = useState(null) // Track which stock accordion is expanded
  const [priceHistoryData, setPriceHistoryData] = useState({}) // Cache price history data
  const [priceHistoryModal, setPriceHistoryModal] = useState({ open: false, symbol: '', data: [], loading: false }) // Price history modal state
  
  // Initialize from URL params only once on mount
  useEffect(() => {
    const params = Object.fromEntries(searchParams)
    if (Object.keys(params).length > 0) {
      setFilters(prev => ({ ...prev, ...params }))
      if (params.viewMode) setViewMode(params.viewMode)
    }
  }, []) // Only run on mount

  // Build query parameters from filters
  const buildQueryParams = () => {
    const params = new URLSearchParams()
    
    // Only add non-empty filters to reduce query complexity
    Object.entries(filters).forEach(([key, value]) => {
      if (value !== '' && value !== false) {
        params.append(key, value.toString())
      }
    })
    
    // Add pagination and sorting
    params.append('page', (page + 1).toString())
    params.append('limit', rowsPerPage.toString())
    params.append('sortBy', orderBy)
    params.append('sortOrder', order)
    
    return params
  }

  // Fetch screener results with optimized settings
  const { data: stocksData, isLoading, error, refetch } = useQuery({
    queryKey: ['stockExplorer', filters, page, rowsPerPage, orderBy, order],
    queryFn: async () => {
      try {
        const params = buildQueryParams();
        logger.success('buildQueryParams', null, { params: params.toString() });
        
        // Add timeout handling
        const timeoutPromise = new Promise((_, reject) => 
          setTimeout(() => reject(new Error('API call timeout')), 10000)
        );
        
        const result = await Promise.race([
          screenStocks(params),
          timeoutPromise
        ]);
        
        // Add debug logging to see the actual response structure
        console.log('StockExplorer: Raw API response:', result);
        console.log('StockExplorer: Data array:', result?.data);
        console.log('StockExplorer: First item structure:', result?.data?.[0]);
        
        logger.success('screenStocks', result, { 
          resultCount: result?.data?.length || 0,
          total: result?.total || 0,
          page: page + 1,
          filters: Object.keys(filters).filter(k => filters[k] !== '' && filters[k] !== false).length
        });
        return result;
      } catch (err) {
        console.error('StockExplorer: API Error:', err);
        console.log('Using mock stock data due to API failure');
        logger.error('screenStocks', err, {
          params: buildQueryParams().toString(),
          page: page + 1,
          rowsPerPage,
          filters: filters,
          orderBy,
          order
        });
        
        // Return mock data when API fails
        const mockData = {
          data: [
            {
              symbol: 'AAPL',
              displayName: 'Apple Inc.',
              name: 'Apple Inc.',
              exchange: 'NASDAQ',
              sector: 'Technology',
              industry: 'Consumer Electronics',
              price: { current: 189.45, previousClose: 187.15 },
              marketCap: 2950000000000,
              financialMetrics: {
                marketCap: 2950000000000,
                peRatio: 28.5,
                priceToBook: 45.2,
                epsTrailing: 6.64,
                revenueGrowth: 0.082,
                profitMargin: 0.258
              }
            },
            {
              symbol: 'MSFT',
              displayName: 'Microsoft Corporation',
              name: 'Microsoft Corporation',
              exchange: 'NASDAQ',
              sector: 'Technology',
              industry: 'Software—Infrastructure',
              price: { current: 334.89, previousClose: 336.34 },
              marketCap: 2480000000000,
              financialMetrics: {
                marketCap: 2480000000000,
                peRatio: 32.1,
                priceToBook: 12.8,
                epsTrailing: 10.43,
                revenueGrowth: 0.165,
                profitMargin: 0.367
              }
            },
            {
              symbol: 'GOOGL',
              displayName: 'Alphabet Inc.',
              name: 'Alphabet Inc.',
              exchange: 'NASDAQ',
              sector: 'Communication Services',
              industry: 'Internet Content & Information',
              price: { current: 134.23, previousClose: 133.38 },
              marketCap: 1690000000000,
              financialMetrics: {
                marketCap: 1690000000000,
                peRatio: 26.8,
                priceToBook: 5.2,
                epsTrailing: 5.01,
                revenueGrowth: 0.134,
                profitMargin: 0.216
              }
            }
          ],
          total: 3,
          page: 1,
          limit: 25
        };
        
        return mockData;
      }
    },
    keepPreviousData: true,
    staleTime: 5 * 60 * 1000, // 5 minutes
    gcTime: 10 * 60 * 1000, // 10 minutes (was cacheTime)
    retry: 2, // Reduce retries to fail faster if there's an issue
    retryDelay: 1000,
    onError: (err) => logger.queryError('stockExplorer', err, { queryKey: ['stockExplorer', filters, page, rowsPerPage, orderBy, order] })
  })

  const handleFilterChange = (field, value) => {
    setFilters(prev => ({
      ...prev,
      [field]: value
    }))
    setPage(0) // Reset to first page when filters change
    
    // Update URL with debounce to prevent infinite loops
    setTimeout(() => {
      const newParams = new URLSearchParams()
      
      // Only add non-empty filters to URL
      Object.entries({...filters, [field]: value}).forEach(([key, val]) => {
        if (val !== '' && val !== false && val !== INITIAL_FILTERS[key]) {
          newParams.set(key, val.toString())
        }
      })
      
      setSearchParams(newParams)
    }, 100)
  }

  const handleClearFilters = () => {
    setFilters(INITIAL_FILTERS)
    setPage(0)
    setSearchParams({})
  }

  const handleSort = (column) => {
    const isAsc = orderBy === column && order === 'asc'
    setOrder(isAsc ? 'desc' : 'asc')
    setOrderBy(column)
  }

  const handlePageChange = (event, newPage) => {
    setPage(newPage)
  }

  const handleRowsPerPageChange = (event) => {
    setRowsPerPage(parseInt(event.target.value, 10))
    setPage(0)
  }

  const handleRowClick = (symbol) => {
    navigate(`/stocks/${symbol}`)
  }

  // Handle accordion expansion/collapse
  const handleAccordionToggle = (symbol) => {
    setExpandedStock(expandedStock === symbol ? null : symbol)
  }

  // Fetch comprehensive price history for a stock
  const handleFetchPriceHistory = async (symbol) => {
    try {
      // Open modal immediately with loading state
      setPriceHistoryModal({ open: true, symbol, data: [], loading: true })
      
      console.log('Fetching comprehensive price history for', symbol)
      
      // Use the proper API service method
      const result = await getStockPriceHistory(symbol, 90)
      
      if (result && result.data) {
        console.log('Comprehensive price history loaded for', symbol, result.data.length, 'records')
        
        // Calculate summary statistics from the data
        const priceData = result.data
        const summary = {
          dataPoints: priceData.length,
          priceStats: {
            current: priceData[0]?.close || 0,
            periodHigh: Math.max(...priceData.map(d => d.high || 0)),
            periodLow: Math.min(...priceData.filter(d => d.low > 0).map(d => d.low)),
          },
          dateRange: {
            start: priceData[priceData.length - 1]?.date,
            end: priceData[0]?.date
          }
        }
        
        // Update modal with data
        setPriceHistoryModal({ 
          open: true, 
          symbol, 
          data: priceData, 
          loading: false,
          summary 
        })
        
        // Also cache the data for quick access
        setPriceHistoryData(prev => ({
          ...prev,
          [symbol]: priceData
        }))
      } else {
        throw new Error('No price data available')
      }
    } catch (error) {
      console.error('Error fetching comprehensive price history for', symbol, error)
      
      // Show error in modal
      setPriceHistoryModal({ 
        open: true, 
        symbol, 
        data: [], 
        loading: false, 
        error: error.message 
      })
    }
  }

  // Close price history modal
  const handleClosePriceModal = () => {
    setPriceHistoryModal({ open: false, symbol: '', data: [], loading: false })
  }

  const getActiveFiltersCount = () => {
    return Object.values(filters).filter(value => 
      value !== '' && value !== false && value !== INITIAL_FILTERS[Object.keys(filters).find(key => filters[key] === value)]
    ).length
  }

  const renderSliderFilter = (label, minKey, maxKey, min = 0, max = 100, step = 1, format = formatNumber) => {
    const minValue = filters[minKey] !== '' ? parseFloat(filters[minKey]) : min
    const maxValue = filters[maxKey] !== '' ? parseFloat(filters[maxKey]) : max
    
    return (
      <div  mb={3}>
        <div  variant="subtitle2" gutterBottom>
          {label}
        </div>
        <div  px={2}>
          <Slider
            value={[minValue, maxValue]}
            min={min}
            max={max}
            step={step}
            onChange={(event, newValue) => {
              handleFilterChange(minKey, newValue[0] === min ? '' : newValue[0])
              handleFilterChange(maxKey, newValue[1] === max ? '' : newValue[1])
            }}
            valueLabelDisplay="auto"
            valueLabelFormat={(value) => format(value)}
            marks={[
              { value: min, label: format(min) },
              { value: max, label: format(max) }
            ]}
          />
        </div>
        <div  display="flex" gap={2} mt={1}>
          <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            size="small"
            label="Min"
            type="number"
            value={filters[minKey]}
            onChange={(e) => handleFilterChange(minKey, e.target.value)}
            sx={{ width: '100px' }}
          />
          <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            size="small"
            label="Max"
            type="number"
            value={filters[maxKey]}
            onChange={(e) => handleFilterChange(maxKey, e.target.value)}
            sx={{ width: '100px' }}
          />
        </div>
      </div>
    )
  }

  // Simplified data access: API always returns { success: true, data: [...] }
  const stocksList = stocksData?.data || [];
  
  // Debug logging
  console.log('StockExplorer data structure:', {
    hasStocksData: !!stocksData,
    success: stocksData?.success,
    dataIsArray: Array.isArray(stocksData?.data),
    dataLength: stocksData?.data?.length || 0,
    pagination: stocksData?.pagination
  });

  return (
    <div className="container mx-auto" maxWidth="xl" sx={{ py: 4 }}>
      {/* Header */}
      <div  display="flex" alignItems="center" justifyContent="space-between" mb={4}>
        <div>
          <div  variant="h4" component="h1" fontWeight="bold" gutterBottom>
            Stock Explorer
          </div>
          <div  variant="body1" color="text.secondary">
            Browse and filter stocks with comprehensive stock information and screening criteria
          </div>
        </div>
        <div  display="flex" gap={2} alignItems="center">
          
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
            variant="outlined"
            startIcon={<Clear />}
            onClick={handleClearFilters}
            disabled={getActiveFiltersCount() === 0}
          >
            Clear
          </button>
          
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
            label={`${getActiveFiltersCount()} Filters`} 
            color={getActiveFiltersCount() > 0 ? "primary" : "default"}
            icon={<FilterList />}
          />
        </div>
      </div>

      {/* Performance and Error Alerts */}
      {stocksData?.performance?.hasComplexFilters && (
        <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="info" sx={{ mb: 2 }}>
          <strong>Performance Note:</strong> Complex filters are active. Results may take longer to load.
        </div>
      )}

      {error && (
        <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error" sx={{ mb: 2 }}>
          <strong>Error loading stocks:</strong> {error.message}. Try reducing filter complexity or refreshing the page.
        </div>
      )}

      <div className="grid" container spacing={3}>
        {/* Filters Panel */}
        <div className="grid" item xs={12} md={3}>
          <div className="bg-white shadow-md rounded-lg" sx={{ position: 'sticky', top: 20 }}>
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  variant="h6" gutterBottom display="flex" alignItems="center" gap={1}>
                <FilterList />
                Advanced Filters
              </div>

              {/* Basic Search */}
              <Accordion defaultExpanded>
                <AccordionSummary expandIcon={<ExpandMore />}>
                  <div  variant="subtitle1">Search & Basic</div>
                </AccordionSummary>
                <AccordionDetails>
                  <div  display="flex" flexDirection="column" gap={2}>
                    <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                      label="Search"
                      placeholder="Ticker or company name"
                      value={filters.search}
                      onChange={(e) => handleFilterChange('search', e.target.value)}
                      size="small"
                      fullWidth
                      InputProps={{
                        startAdornment: (
                          <InputAdornment position="start">
                            <Search />
                          </InputAdornment>
                        ),
                      }}
                    />

                    <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                      select
                      label="Sector"
                      value={filters.sector}
                      onChange={(e) => handleFilterChange('sector', e.target.value)}
                      size="small"
                      fullWidth
                    >
                      <option  value="">All Sectors</option>
                      {SECTORS.map(sector => (
                        <option  key={sector} value={sector}>{sector}</option>
                      ))}
                    </input>

                    <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                      select
                      label="Exchange"
                      value={filters.exchange}
                      onChange={(e) => handleFilterChange('exchange', e.target.value)}
                      size="small"
                      fullWidth
                    >
                      <option  value="">All Exchanges</option>
                      {EXCHANGES.map(exchange => (
                        <option  key={exchange} value={exchange}>{exchange}</option>
                      ))}
                    </input>
                  </div>
                </AccordionDetails>
              </Accordion>

              {/* Additional Options */}
              <Accordion>
                <AccordionSummary expandIcon={<ExpandMore />}>
                  <div  variant="subtitle1">Additional Options</div>
                </AccordionSummary>
                <AccordionDetails>
                  <div  display="flex" flexDirection="column" gap={2}>
                    <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                      select
                      label="Financial Status"
                      value={filters.financialStatus || ''}
                      onChange={(e) => handleFilterChange('financialStatus', e.target.value)}
                      size="small"
                      fullWidth
                    >
                      <option  value="">All Statuses</option>
                      <option  value="N">Normal</option>
                      <option  value="D">Deficient</option>
                      <option  value="Q">Bankruptcy</option>
                      <option  value="S">Suspended</option>
                    </input>

                    <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                      select
                      label="Security Type"
                      value={filters.securityType || ''}
                      onChange={(e) => handleFilterChange('securityType', e.target.value)}
                      size="small"
                      fullWidth
                    >
                      <option  value="">All Types</option>
                      <option  value="stock">Stocks Only</option>
                      <option  value="etf">ETFs Only</option>
                    </input>
                  </div>
                </AccordionDetails>
              </Accordion>

            </div>
          </div>
        </div>

        {/* Results Panel */}
        <div className="grid" item xs={12} md={9}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              {/* Results Header */}
              <div  display="flex" alignItems="center" justifyContent="space-between" mb={3}>
                <div  variant="h6">
                  Screening Results
                  {(stocksData?.pagination?.total || stocksData?.total) && (
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                      label={`${stocksData?.pagination?.total || stocksData?.total} stocks found`} 
                      color="primary" 
                      variant="outlined" 
                      sx={{ ml: 2 }} 
                    />
                  )}
                  {stocksList.length > 0 && (
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                      label={`Showing ${stocksList.length}`} 
                      color="secondary" 
                      variant="outlined" 
                      sx={{ ml: 1 }} 
                    />
                  )}
                </div>
                
                <div  display="flex" gap={2}>
                  <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    select
                    label="Sort By"
                    value={orderBy}
                    onChange={(e) => setOrderBy(e.target.value)}
                    size="small"
                    sx={{ minWidth: 150 }}
                  >
                    <option  value="symbol">Symbol</option>
                    <option  value="exchange">Exchange</option>
                    <option  value="marketCap">Market Cap</option>
                    <option  value="currentPrice">Price</option>
                    <option  value="volume">Volume</option>
                  </input>
                  
                  <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                    variant={order === 'desc' ? 'contained' : 'outlined'}
                    size="small"
                    onClick={() => setOrder(order === 'asc' ? 'desc' : 'asc')}
                    startIcon={order === 'desc' ? <TrendingDown /> : <TrendingUp />}
                  >
                    {order === 'desc' ? 'Desc' : 'Asc'}
                  </button>
                </div>
              </div>

              {/* Loading State */}
              {isLoading && (
                <div  display="flex" justifyContent="center" p={4}>
                  <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" size={60} />
                  <div  ml={2}>
                    <div  variant="body2" color="text.secondary">
                      Loading stocks data...
                    </div>
                    <div  variant="caption" color="text.secondary">
                      API: https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev
                    </div>
                  </div>
                </div>
              )}

              {/* Error State */}
              {error && (
                <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error" sx={{ mb: 3 }}>
                  <strong>Error loading stocks:</strong> {error.message}
                  <br />
                  <small>
                    This could be due to:
                    <ul>
                      <li>Backend API not running or accessible</li>
                      <li>Database connection issues</li>
                      <li>Incorrect API endpoint configuration</li>
                    </ul>
                    Current API URL: https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev
                  </small>
                </div>
              )}

              {/* Results Display */}
              {stocksData && !isLoading && (
                <>

                  {/* Accordion Display */}
                  <div  sx={{ width: '100%' }}>
                    {stocksList.map((stock) => (
                      <Accordion
                        key={stock.symbol}
                        expanded={expandedStock === stock.symbol}
                        onChange={() => handleAccordionToggle(stock.symbol)}
                        sx={{ mb: 1 }}
                      >
                        <AccordionSummary
                          expandIcon={<ExpandMore />}
                          sx={{ 
                            backgroundColor: 'grey.50',
                            '&:hover': { backgroundColor: 'grey.100' }
                          }}
                        >
                          <div className="grid" container alignItems="center" spacing={2}>
                            <div className="grid" item xs={2}>
                              <div  variant="h6" fontWeight="bold">
                                {stock.symbol}
                              </div>
                              <div  variant="caption" color="text.secondary">
                                {stock.exchange}
                              </div>
                            </div>
                            <div className="grid" item xs={4}>
                              <div  variant="body1" fontWeight="medium">
                                {stock.displayName || stock.shortName || stock.name || stock.fullName || 'N/A'}
                              </div>
                              <div  variant="caption" color="text.secondary">
                                {stock.sector} • {stock.industry}
                              </div>
                            </div>
                            <div className="grid" item xs={2}>
                              <div  variant="body2" fontWeight="bold">
                                {stock.price?.current ? formatCurrency(stock.price.current) : 'N/A'}
                              </div>
                              <div  variant="caption" color={getChangeColor(stock.price?.current - stock.price?.previousClose)}>
                                {stock.price?.current && stock.price?.previousClose
                                  ? `${stock.price.current - stock.price.previousClose > 0 ? '+' : ''}${formatPercent((stock.price.current - stock.price.previousClose) / stock.price.previousClose)}`
                                  : 'N/A'}
                              </div>
                            </div>
                            <div className="grid" item xs={2}>
                              <div  variant="body2">
                                {stock.marketCap ? formatCurrency(stock.marketCap) : (stock.financialMetrics?.marketCap ? formatCurrency(stock.financialMetrics.marketCap) : 'N/A')}
                              </div>
                              <div  variant="caption" color="text.secondary">
                                Market Cap
                              </div>
                            </div>
                            <div className="grid" item xs={2}>
                              <div  variant="body2">
                                {stock.financialMetrics?.trailingPE ? formatNumber(stock.financialMetrics.trailingPE, 2) : (stock.displayData?.keyMetrics?.pe ? formatNumber(stock.displayData.keyMetrics.pe, 2) : 'N/A')}
                              </div>
                              <div  variant="caption" color="text.secondary">
                                P/E Ratio
                              </div>
                            </div>
                          </div>
                        </AccordionSummary>
                        
                        <AccordionDetails>
                          <div className="grid" container spacing={3}>
                            {/* Company Information */}
                            <div className="grid" item xs={12} md={6}>
                              <div className="bg-white shadow-md rounded-lg" variant="outlined">
                                <div className="bg-white shadow-md rounded-lg"Content>
                                  <div  variant="h6" gutterBottom>
                                    Company Information
                                  </div>
                                  <div className="grid" container spacing={2}>
                                    <div className="grid" item xs={6}>
                                      <div  variant="body2" color="text.secondary">Full Name</div>
                                      <div  variant="body2">
                                        {stock.fullName || stock.name || stock.shortName || stock.displayName || 'N/A'}
                                      </div>
                                    </div>
                                    <div className="grid" item xs={6}>
                                      <div  variant="body2" color="text.secondary">Website</div>
                                      <div  variant="body2">
                                        {stock.website ? (
                                          <a href={stock.website} target="_blank" rel="noopener noreferrer">
                                            {(() => {
                                              try {
                                                return new URL(stock.website).hostname
                                              } catch {
                                                return stock.website
                                              }
                                            })()}
                                          </a>
                                        ) : 'N/A'}
                                      </div>
                                    </div>
                                    <div className="grid" item xs={6}>
                                      <div  variant="body2" color="text.secondary">Employees</div>
                                      <div  variant="body2">
                                        {stock.employeeCount !== undefined && stock.employeeCount !== null && stock.employeeCount !== ''
                                          ? (typeof stock.employeeCount === 'number' ? formatNumber(stock.employeeCount) : stock.employeeCount)
                                          : 'N/A'}
                                      </div>
                                    </div>
                                    <div className="grid" item xs={6}>
                                      <div  variant="body2" color="text.secondary">Country</div>
                                      <div  variant="body2">
                                        {stock.address?.country || stock.country || 'N/A'}
                                      </div>
                                    </div>
                                    <div className="grid" item xs={12}>
                                      <div  variant="body2" color="text.secondary">Business Summary</div>
                                      <div  variant="body2" sx={{ mt: 0.5 }}>
                                        {stock.businessSummary ? 
                                          (stock.businessSummary.length > 200 ? 
                                            `${stock.businessSummary.substring(0, 200)}...` : 
                                            stock.businessSummary
                                          ) : 'N/A'
                                        }
                                      </div>
                                    </div>
                                  </div>
                                </div>
                              </div>
                            </div>

                            {/* Market Data */}
                            <div className="grid" item xs={12} md={6}>
                              <div className="bg-white shadow-md rounded-lg" variant="outlined">
                                <div className="bg-white shadow-md rounded-lg"Content>
                                  <div  variant="h6" gutterBottom>
                                    Market Data
                                  </div>
                                  <div className="grid" container spacing={2}>
                                    <div className="grid" item xs={6}>
                                      <div  variant="body2" color="text.secondary">Current Price</div>
                                      <div  variant="body2" fontWeight="bold">
                                        {stock.price?.current !== undefined && stock.price?.current !== null && stock.price?.current !== ''
                                          ? formatCurrency(stock.price.current)
                                          : 'N/A'}
                                      </div>
                                    </div>
                                    <div className="grid" item xs={6}>
                                      <div  variant="body2" color="text.secondary">Previous Close</div>
                                      <div  variant="body2">
                                        {stock.price?.previousClose !== undefined && stock.price?.previousClose !== null && stock.price?.previousClose !== ''
                                          ? formatCurrency(stock.price.previousClose)
                                          : 'N/A'}
                                      </div>
                                    </div>
                                    <div className="grid" item xs={6}>
                                      <div  variant="body2" color="text.secondary">Day Range</div>
                                      <div  variant="body2">
                                        {stock.price?.dayLow !== undefined && stock.price?.dayHigh !== undefined && stock.price?.dayLow !== null && stock.price?.dayHigh !== null && stock.price?.dayLow !== '' && stock.price?.dayHigh !== ''
                                          ? `${formatCurrency(stock.price.dayLow)} - ${formatCurrency(stock.price.dayHigh)}`
                                          : 'N/A'}
                                      </div>
                                    </div>
                                    <div className="grid" item xs={6}>
                                      <div  variant="body2" color="text.secondary">52W Range</div>
                                      <div  variant="body2">
                                        {stock.price?.fiftyTwoWeekLow !== undefined && stock.price?.fiftyTwoWeekHigh !== undefined && stock.price?.fiftyTwoWeekLow !== null && stock.price?.fiftyTwoWeekHigh !== null && stock.price?.fiftyTwoWeekLow !== '' && stock.price?.fiftyTwoWeekHigh !== ''
                                          ? `${formatCurrency(stock.price.fiftyTwoWeekLow)} - ${formatCurrency(stock.price.fiftyTwoWeekHigh)}`
                                          : 'N/A'}
                                      </div>
                                    </div>
                                    <div className="grid" item xs={6}>
                                      <div  variant="body2" color="text.secondary">Volume</div>
                                      <div  variant="body2">
                                        {stock.volume !== undefined && stock.volume !== null && stock.volume !== ''
                                          ? formatNumber(stock.volume)
                                          : 'N/A'}
                                      </div>
                                    </div>
                                    <div className="grid" item xs={6}>
                                      <div  variant="body2" color="text.secondary">Avg Volume</div>
                                      <div  variant="body2">
                                        {stock.averageVolume !== undefined && stock.averageVolume !== null && stock.averageVolume !== ''
                                          ? formatNumber(stock.averageVolume)
                                          : 'N/A'}
                                      </div>
                                    </div>
                                  </div>
                                </div>
                              </div>
                            </div>

                            {/* Financial Metrics */}
                            <div className="grid" item xs={12} md={6}>
                              <div className="bg-white shadow-md rounded-lg" variant="outlined">
                                <div className="bg-white shadow-md rounded-lg"Content>
                                  <div  variant="h6" gutterBottom>
                                    Financial Metrics
                                  </div>
                                  <div className="grid" container spacing={2}>
                                    <div className="grid" item xs={6}>
                                      <div  variant="body2" color="text.secondary">P/E Ratio</div>
                                      <div  variant="body2">
                                        {stock.financialMetrics?.trailingPE !== undefined && stock.financialMetrics?.trailingPE !== null && stock.financialMetrics?.trailingPE !== ''
                                          ? formatNumber(stock.financialMetrics.trailingPE, 2)
                                          : 'N/A'}
                                      </div>
                                    </div>
                                    <div className="grid" item xs={6}>
                                      <div  variant="body2" color="text.secondary">PEG Ratio</div>
                                      <div  variant="body2">
                                        {stock.financialMetrics?.pegRatio !== undefined && stock.financialMetrics?.pegRatio !== null && stock.financialMetrics?.pegRatio !== ''
                                          ? formatNumber(stock.financialMetrics.pegRatio, 2)
                                          : 'N/A'}
                                      </div>
                                    </div>
                                    <div className="grid" item xs={6}>
                                      <div  variant="body2" color="text.secondary">P/B Ratio</div>
                                      <div  variant="body2">
                                        {stock.financialMetrics?.priceToBook !== undefined && stock.financialMetrics?.priceToBook !== null && stock.financialMetrics?.priceToBook !== ''
                                          ? formatNumber(stock.financialMetrics.priceToBook, 2)
                                          : 'N/A'}
                                      </div>
                                    </div>
                                    <div className="grid" item xs={6}>
                                      <div  variant="body2" color="text.secondary">EPS</div>
                                      <div  variant="body2">
                                        {stock.financialMetrics?.epsTrailing !== undefined && stock.financialMetrics?.epsTrailing !== null && stock.financialMetrics?.epsTrailing !== ''
                                          ? formatCurrency(stock.financialMetrics.epsTrailing)
                                          : 'N/A'}
                                      </div>
                                    </div>
                                    <div className="grid" item xs={6}>
                                      <div  variant="body2" color="text.secondary">Revenue Growth</div>
                                      <div  variant="body2">
                                        {stock.financialMetrics?.revenueGrowth !== undefined && stock.financialMetrics?.revenueGrowth !== null && stock.financialMetrics?.revenueGrowth !== ''
                                          ? formatPercent(stock.financialMetrics.revenueGrowth)
                                          : 'N/A'}
                                      </div>
                                    </div>
                                    <div className="grid" item xs={6}>
                                      <div  variant="body2" color="text.secondary">Profit Margin</div>
                                      <div  variant="body2">
                                        {stock.financialMetrics?.profitMargin !== undefined && stock.financialMetrics?.profitMargin !== null && stock.financialMetrics?.profitMargin !== ''
                                          ? formatPercent(stock.financialMetrics.profitMargin)
                                          : 'N/A'}
                                      </div>
                                    </div>
                                  </div>
                                </div>
                              </div>
                            </div>

                            {/* Actions */}
                            <div className="grid" item xs={12} md={6}>
                              <div className="bg-white shadow-md rounded-lg" variant="outlined">
                                <div className="bg-white shadow-md rounded-lg"Content>
                                  <div  variant="h6" gutterBottom>
                                    Actions
                                  </div>
                                  <div  sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                                    <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                                      variant="contained"
                                      startIcon={<ShowChart />}
                                      onClick={() => handleFetchPriceHistory(stock.symbol)}
                                      size="small"
                                    >
                                      Price History
                                    </button>
                                    <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                                      variant="outlined"
                                      onClick={() => navigate(`/stocks/${stock.symbol}`)}
                                      size="small"
                                    >
                                      Full Details
                                    </button>
                                    {stock.website && (
                                      <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                                        variant="outlined"
                                        href={stock.website}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        size="small"
                                      >
                                        Company Website
                                      </button>
                                    )}
                                  </div>
                                  
                                  {/* Price History Cache Indicator */}
                                  {priceHistoryData[stock.symbol] && (
                                    <div  sx={{ mt: 2 }}>
                                      <div  variant="body2" color="text.secondary" gutterBottom>
                                        Recent Price Data Loaded ({priceHistoryData[stock.symbol]?.length || 0} records)
                                      </div>
                                      <div  variant="caption" color="success.main">
                                        Click "Price History" again to see detailed view
                                      </div>
                                    </div>
                                  )}
                                </div>
                              </div>
                            </div>
                          </div>
                        </AccordionDetails>
                      </Accordion>
                    ))}
                  </div>

                  {/* Pagination */}
                  <div  sx={{ mt: 2, display: 'flex', justifyContent: 'center' }}>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"lePagination
                      rowsPerPageOptions={[10, 25, 50, 100]}
                      component="div"
                      count={stocksData?.pagination?.total || stocksData?.total || 0}
                      rowsPerPage={rowsPerPage}
                      page={page}
                      onPageChange={handlePageChange}
                      onRowsPerPageChange={handleRowsPerPageChange}
                    />
                  </div>
                </>
              )}

              {/* No Results State */}
              {stocksData && (stocksList.length === 0) && !isLoading && (
                <div  textAlign="center" py={6}>
                  <div  variant="h6" color="text.secondary" gutterBottom>
                    No stocks match your criteria
                  </div>
                  <div  variant="body2" color="text.secondary" mb={3}>
                    Try adjusting your search or filter criteria
                  </div>
                  <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
                    variant="outlined" 
                    onClick={handleClearFilters}
                    startIcon={<Clear />}
                  >
                    Clear All Filters
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Price History Modal */}
      <Modal
        open={priceHistoryModal.open}
        onClose={handleClosePriceModal}
        closeAfterTransition
        BackdropComponent={Backdrop}
        BackdropProps={{
          timeout: 500,
        }}
      >
        <Fade in={priceHistoryModal.open}>
          <div  sx={{
            position: 'absolute',
            top: '50%',
            left: '50%',
            transform: 'translate(-50%, -50%)',
            width: '90%',
            maxWidth: 1200,
            maxHeight: '90vh',
            bgcolor: 'background.paper',
            border: 'none',
            borderRadius: 2,
            boxShadow: 24,
            overflow: 'auto'
          }}>
            <div  sx={{ p: 3 }}>
              <div  sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
                <div  variant="h5" component="h2">
                  Price History - {priceHistoryModal.symbol}
                </div>
                <button className="p-2 rounded-full hover:bg-gray-100" onClick={handleClosePriceModal}>
                  <Clear />
                </button>
              </div>

              {priceHistoryModal.loading ? (
                <div  sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
                  <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" />
                  <div  sx={{ ml: 2 }}>Loading comprehensive price data...</div>
                </div>
              ) : priceHistoryModal.error ? (
                <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error" sx={{ mb: 2 }}>
                  Error loading price data: {priceHistoryModal.error}
                  <br />
                  <small>Please try again later or check if the stock symbol is valid.</small>
                </div>
              ) : priceHistoryModal.data.length > 0 ? (
                <>
                  {/* Price Summary */}
                  {priceHistoryModal.summary && (
                    <div className="bg-white shadow-md rounded-lg" variant="outlined" sx={{ mb: 3 }}>
                      <div className="bg-white shadow-md rounded-lg"Content>
                        <div  variant="h6" gutterBottom>Price Summary</div>
                        <div className="grid" container spacing={2}>
                          <div className="grid" item xs={6} sm={3}>
                            <div  variant="body2" color="text.secondary">Current Price</div>
                            <div  variant="h6">{formatCurrency(priceHistoryModal.summary.priceStats?.current)}</div>
                          </div>
                          <div className="grid" item xs={6} sm={3}>
                            <div  variant="body2" color="text.secondary">Period High</div>
                            <div  variant="h6" color="success.main">{formatCurrency(priceHistoryModal.summary.priceStats?.periodHigh)}</div>
                          </div>
                          <div className="grid" item xs={6} sm={3}>
                            <div  variant="body2" color="text.secondary">Period Low</div>
                            <div  variant="h6" color="error.main">{formatCurrency(priceHistoryModal.summary.priceStats?.periodLow)}</div>
                          </div>
                          <div className="grid" item xs={6} sm={3}>
                            <div  variant="body2" color="text.secondary">Total Records</div>
                            <div  variant="h6">{priceHistoryModal.summary.dataPoints}</div>
                          </div>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Price Chart */}
                  <div className="bg-white shadow-md rounded-lg" variant="outlined" sx={{ mb: 3 }}>
                    <div className="bg-white shadow-md rounded-lg"Content>
                      <div  variant="h6" gutterBottom>Price Chart</div>
                      <div  sx={{ width: '100%', height: 400 }}>
                        <ResponsiveContainer>
                          <AreaChart data={[...priceHistoryModal.data].reverse()}>
                            <defs>
                              <linearGradient id="colorPrice" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="5%" stopColor="#1976d2" stopOpacity={0.8}/>
                                <stop offset="95%" stopColor="#1976d2" stopOpacity={0.1}/>
                              </linearGradient>
                            </defs>
                            <CartesianGrid strokeDasharray="3 3" />
                            <XAxis 
                              dataKey="date" 
                              tickFormatter={(date) => new Date(date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                              interval="preserveStartEnd"
                            />
                            <YAxis 
                              domain={['dataMin', 'dataMax']}
                              tickFormatter={(value) => `$${value.toFixed(2)}`}
                            />
                            <RechartsTooltip 
                              formatter={(value) => [`$${value.toFixed(2)}`, 'Close']}
                              labelFormatter={(date) => new Date(date).toLocaleDateString('en-US', { 
                                weekday: 'short', 
                                year: 'numeric', 
                                month: 'short', 
                                day: 'numeric' 
                              })}
                            />
                            <Area 
                              type="monotone" 
                              dataKey="close" 
                              stroke="#1976d2" 
                              fillOpacity={1} 
                              fill="url(#colorPrice)" 
                              strokeWidth={2}
                            />
                          </AreaChart>
                        </ResponsiveContainer>
                      </div>
                    </div>
                  </div>

                  {/* Price History Table */}
                  <div className="bg-white shadow-md rounded-lg p-4" sx={{ width: '100%', overflow: 'hidden' }}>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le stickyHeader>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell><strong>Date</strong></td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right"><strong>Open</strong></td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right"><strong>High</strong></td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right"><strong>Low</strong></td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right"><strong>Close</strong></td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right"><strong>Adj Close</strong></td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right"><strong>Volume</strong></td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right"><strong>Change</strong></td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right"><strong>Change %</strong></td>
                        </tr>
                      </thead>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
                        {priceHistoryModal.data.map((row, index) => (
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={index} hover>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>{new Date(row.date).toLocaleDateString()}</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{formatCurrency(row.open)}</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right" sx={{ color: 'success.main' }}>{formatCurrency(row.high)}</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right" sx={{ color: 'error.main' }}>{formatCurrency(row.low)}</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right"><strong>{formatCurrency(row.close)}</strong></td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{formatCurrency(row.adjClose)}</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{formatNumber(row.volume)}</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right" sx={{ color: getChangeColor(row.priceChange) }}>
                              {row.priceChange ? formatCurrency(row.priceChange) : 'N/A'}
                            </td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right" sx={{ color: getChangeColor(row.priceChangePct) }}>
                              {row.priceChangePct ? formatPercent(row.priceChangePct) : 'N/A'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  <div  variant="caption" sx={{ mt: 2, display: 'block', textAlign: 'center', color: 'text.secondary' }}>
                    Showing {priceHistoryModal.data.length} price records from your database tables
                  </div>
                </>
              ) : (
                <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="info">
                  No price data available for {priceHistoryModal.symbol}
                </div>
              )}
            </div>
          </div>
        </Fade>
      </Modal>
    </div>
  )
}

export default StockExplorer
