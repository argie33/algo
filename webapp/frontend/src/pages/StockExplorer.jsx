import React, { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { createComponentLogger } from '../utils/errorLogger'
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
  ToggleButton,  ToggleButtonGroup,
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
  BookmarkBorder,
  Bookmark,
  ViewList,
  Tune,
  InfoOutlined
} from '@mui/icons-material'
import api, { screenStocks, getStockPrices, getStockPricesRecent, getEarningsMetrics } from '../services/api'
import { formatCurrency, formatPercentage as formatPercent, formatNumber, getChangeColor, getChangeIcon, getMarketCapCategory } from '../utils/formatters'

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
  }  // Fetch screener results with optimized settings
  const { data: stocksData, isLoading, error, refetch } = useQuery({
    queryKey: ['stockExplorer', filters, page, rowsPerPage, orderBy, order],
    queryFn: async () => {
      try {
        const params = buildQueryParams();
        logger.success('buildQueryParams', null, { params: params.toString() });
        const result = await screenStocks(params);
        
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
        logger.error('screenStocks', err, {
          params: buildQueryParams().toString(),
          page: page + 1,
          rowsPerPage,
          filters: filters,
          orderBy,
          order
        });
        throw err;
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
      
      // Call the correct price API endpoint for historical data
      const response = await fetch(`/api/stocks/${symbol}/prices?limit=90`)
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }
      
      const result = await response.json()
      
      if (result.success && result.data) {
        console.log('Comprehensive price history loaded for', symbol, result.data.length, 'records')
        
        // Update modal with data
        setPriceHistoryModal({ 
          open: true, 
          symbol, 
          data: result.data, 
          loading: false,
          summary: result.summary 
        })
        
        // Also cache the data for quick access
        setPriceHistoryData(prev => ({
          ...prev,
          [symbol]: result.data
        }))
      } else {
        throw new Error(result.error || 'Failed to fetch price data')
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

  // Removed viewMode handler - always use advanced view

  const getActiveFiltersCount = () => {
    return Object.values(filters).filter(value => 
      value !== '' && value !== false && value !== INITIAL_FILTERS[Object.keys(filters).find(key => filters[key] === value)]
    ).length
  }

  const renderSliderFilter = (label, minKey, maxKey, min = 0, max = 100, step = 1, format = formatNumber) => {
    const minValue = filters[minKey] !== '' ? parseFloat(filters[minKey]) : min
    const maxValue = filters[maxKey] !== '' ? parseFloat(filters[maxKey]) : max
    
    return (
      <Box mb={3}>
        <Typography variant="subtitle2" gutterBottom>
          {label}
        </Typography>
        <Box px={2}>
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
        </Box>
        <Box display="flex" gap={2} mt={1}>
          <TextField
            size="small"
            label="Min"
            type="number"
            value={filters[minKey]}
            onChange={(e) => handleFilterChange(minKey, e.target.value)}
            sx={{ width: '100px' }}
          />
          <TextField
            size="small"
            label="Max"
            type="number"
            value={filters[maxKey]}
            onChange={(e) => handleFilterChange(maxKey, e.target.value)}
            sx={{ width: '100px' }}
          />        </Box>
      </Box>
    )
  }
  const columns = [
    // Core identification
    { id: 'symbol', label: 'Symbol', sortable: true, minWidth: 80 },
    { id: 'shortName', label: 'Short Name', sortable: true, minWidth: 150, accessor: (row) => row.shortName || row.name },
    { id: 'fullName', label: 'Full Name', sortable: true, minWidth: 250 },
    
    // Current market data
    { id: 'currentPrice', label: 'Current Price', sortable: true, format: formatCurrency, align: 'right', minWidth: 100, accessor: (row) => row.price?.current },
    { id: 'previousClose', label: 'Prev Close', sortable: true, format: formatCurrency, align: 'right', minWidth: 100, accessor: (row) => row.price?.previousClose },
    { id: 'volume', label: 'Volume', sortable: true, format: formatNumber, align: 'right', minWidth: 100 },
    { id: 'marketCap', label: 'Market Cap', sortable: true, format: formatCurrency, align: 'right', minWidth: 120, accessor: (row) => row.marketCap || row.financialMetrics?.marketCap || row.displayData?.keyMetrics?.marketCap },
    
    // Exchange & categorization 
    { id: 'exchange', label: 'Exchange', sortable: true, minWidth: 100 },
    { id: 'fullExchangeName', label: 'Full Exchange', sortable: true, minWidth: 150 },
    { id: 'marketCategory', label: 'Market Category', sortable: true, minWidth: 120 },
    
    // Business information
    { id: 'sector', label: 'Sector', sortable: true, minWidth: 120 },
    { id: 'industry', label: 'Industry', sortable: true, minWidth: 150 },
    { id: 'employeeCount', label: 'Employees', sortable: true, format: formatNumber, align: 'right', minWidth: 100 },
    
    // Price ranges
    { id: 'dayLow', label: 'Day Low', sortable: true, format: formatCurrency, align: 'right', minWidth: 90, accessor: (row) => row.price?.dayLow },
    { id: 'dayHigh', label: 'Day High', sortable: true, format: formatCurrency, align: 'right', minWidth: 90, accessor: (row) => row.price?.dayHigh },
    { id: 'fiftyTwoWeekLow', label: '52W Low', sortable: true, format: formatCurrency, align: 'right', minWidth: 90, accessor: (row) => row.price?.fiftyTwoWeekLow },
    { id: 'fiftyTwoWeekHigh', label: '52W High', sortable: true, format: formatCurrency, align: 'right', minWidth: 90, accessor: (row) => row.price?.fiftyTwoWeekHigh },
    
    // Moving averages
    { id: 'fiftyDayAverage', label: '50D Avg', sortable: true, format: formatCurrency, align: 'right', minWidth: 90, accessor: (row) => row.price?.fiftyDayAverage },
    { id: 'twoHundredDayAverage', label: '200D Avg', sortable: true, format: formatCurrency, align: 'right', minWidth: 90, accessor: (row) => row.price?.twoHundredDayAverage },
    
    // Contact and corporate info
    { id: 'website', label: 'Website', sortable: false, minWidth: 120, format: (value) => value ? <a href={value} target="_blank" rel="noopener noreferrer">{new URL(value).hostname}</a> : 'N/A' },
    { id: 'country', label: 'Country', sortable: true, minWidth: 100, accessor: (row) => row.address?.country },
    { id: 'city', label: 'City', sortable: true, minWidth: 100, accessor: (row) => row.address?.city },
    { id: 'state', label: 'State', sortable: true, minWidth: 80, accessor: (row) => row.address?.state },
    
    // Financial details
    { id: 'currency', label: 'Currency', sortable: true, minWidth: 80 },
    { id: 'quoteType', label: 'Quote Type', sortable: true, minWidth: 100 },
    
    // Governance scores
    { id: 'auditRisk', label: 'Audit Risk', sortable: true, align: 'right', minWidth: 90, accessor: (row) => row.governance?.auditRisk },
    { id: 'boardRisk', label: 'Board Risk', sortable: true, align: 'right', minWidth: 90, accessor: (row) => row.governance?.boardRisk },
    { id: 'compensationRisk', label: 'Comp Risk', sortable: true, align: 'right', minWidth: 90, accessor: (row) => row.governance?.compensationRisk },
    { id: 'overallRisk', label: 'Overall Risk', sortable: true, align: 'right', minWidth: 100, accessor: (row) => row.governance?.overallRisk },
    
    // Additional identifiers and status
    { id: 'cqsSymbol', label: 'CQS Symbol', sortable: false, minWidth: 100 },
    { id: 'financialStatus', label: 'Financial Status', sortable: true, minWidth: 120 },
    { id: 'roundLotSize', label: 'Round Lot Size', sortable: true, format: formatNumber, align: 'right', minWidth: 120 },
    { id: 'isEtf', label: 'ETF', sortable: true, minWidth: 80, format: (value) => value ? 'Yes' : 'No' },
    { id: 'testIssue', label: 'Test Issue', sortable: true, minWidth: 100, format: (value) => value ? 'Yes' : 'No' }
  ]
  // Normalize stocks list to handle both { data: [...] } and { data: { data: [...] } } API responses
  let stocksList = [];
  if (stocksData) {
    if (Array.isArray(stocksData.data)) {
      stocksList = stocksData.data;
    } else if (stocksData.data && Array.isArray(stocksData.data.data)) {
      stocksList = stocksData.data.data;
    }
  }
  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      {/* Header */}
      <Box display="flex" alignItems="center" justifyContent="space-between" mb={4}>
        <Box>
          <Typography variant="h4" component="h1" fontWeight="bold" gutterBottom>
            Stock Explorer
          </Typography>          <Typography variant="body1" color="text.secondary">
            Browse and filter stocks with comprehensive stock information and screening criteria
          </Typography>
        </Box>        <Box display="flex" gap={2} alignItems="center">
          {/* Debug button in development */}
          {import.meta.env.DEV && (
            <Button
              variant="outlined"
              size="small"
              onClick={async () => {
                try {
                  const response = await screenStocks(new URLSearchParams());
                  console.log('Test API response:', response);
                  alert('API test successful! Check console for details.');
                } catch (err) {
                  console.error('API test failed:', err);
                  alert('API test failed! Check console for details.');
                }
              }}
            >
              Test API
            </Button>          )}
          
          {/* Removed view mode toggle - always use advanced table view */}
          
          <Button
            variant="outlined"
            startIcon={<Clear />}
            onClick={handleClearFilters}
            disabled={getActiveFiltersCount() === 0}
          >
            Clear
          </Button>
          
          <Chip 
            label={`${getActiveFiltersCount()} Filters`} 
            color={getActiveFiltersCount() > 0 ? "primary" : "default"}
            icon={<FilterList />}
          />
        </Box>
      </Box>

      {/* Performance and Error Alerts */}
      {stocksData?.performance?.hasComplexFilters && (
        <Alert severity="info" sx={{ mb: 2 }}>
          <strong>Performance Note:</strong> Complex filters are active. Results may take longer to load.
        </Alert>
      )}

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          <strong>Error loading stocks:</strong> {error.message}. Try reducing filter complexity or refreshing the page.
        </Alert>
      )}

      <Grid container spacing={3}>
        {/* Filters Panel */}
        <Grid item xs={12} md={viewMode === 'simple' ? 12 : 3}>
          {viewMode === 'simple' ? (
            // Simple search bar
            <Card sx={{ mb: 3 }}>
              <CardContent>
                <Grid container spacing={2} alignItems="center">
                  <Grid item xs={12} md={4}>
                    <TextField
                      fullWidth
                      label="Search stocks"
                      placeholder="Enter ticker or company name"
                      value={filters.search}
                      onChange={(e) => handleFilterChange('search', e.target.value)}
                      InputProps={{
                        startAdornment: (
                          <InputAdornment position="start">
                            <Search />
                          </InputAdornment>
                        ),
                      }}
                    />
                  </Grid>
                  <Grid item xs={12} md={3}>
                    <FormControl fullWidth>
                      <InputLabel>Sector</InputLabel>
                      <Select
                        value={filters.sector}
                        label="Sector"
                        onChange={(e) => handleFilterChange('sector', e.target.value)}
                      >
                        <MenuItem value="">All Sectors</MenuItem>
                        {SECTORS.map((sector) => (
                          <MenuItem key={sector} value={sector}>
                            {sector}
                          </MenuItem>
                        ))}
                      </Select>
                    </FormControl>
                  </Grid>
                  <Grid item xs={12} md={3}>
                    <FormControl fullWidth>
                      <InputLabel>Exchange</InputLabel>
                      <Select
                        value={filters.exchange}
                        label="Exchange"
                        onChange={(e) => handleFilterChange('exchange', e.target.value)}
                      >
                        <MenuItem value="">All Exchanges</MenuItem>
                        {EXCHANGES.map((exchange) => (
                          <MenuItem key={exchange} value={exchange}>
                            {exchange}
                          </MenuItem>
                        ))}
                      </Select>
                    </FormControl>
                  </Grid>
                  <Grid item xs={12} md={2}>
                    <Button
                      variant="outlined"
                      onClick={() => setViewMode('advanced')}
                      startIcon={<Tune />}
                      fullWidth
                    >
                      Advanced
                    </Button>
                  </Grid>
                </Grid>
              </CardContent>
            </Card>
          ) : (
            // Advanced filters panel
            <Card sx={{ position: 'sticky', top: 20 }}>
              <CardContent>
                <Typography variant="h6" gutterBottom display="flex" alignItems="center" gap={1}>
                  <FilterList />
                  Advanced Filters
                </Typography>

                {/* Basic Search */}
                <Accordion defaultExpanded>
                  <AccordionSummary expandIcon={<ExpandMore />}>
                    <Typography variant="subtitle1">Search & Basic</Typography>
                  </AccordionSummary>
                  <AccordionDetails>
                    <Box display="flex" flexDirection="column" gap={2}>
                      <TextField
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

                      <TextField
                        select
                        label="Sector"
                        value={filters.sector}
                        onChange={(e) => handleFilterChange('sector', e.target.value)}
                        size="small"
                        fullWidth
                      >
                        <MenuItem value="">All Sectors</MenuItem>
                        {SECTORS.map(sector => (
                          <MenuItem key={sector} value={sector}>{sector}</MenuItem>
                        ))}
                      </TextField>

                      <TextField
                        select
                        label="Exchange"
                        value={filters.exchange}
                        onChange={(e) => handleFilterChange('exchange', e.target.value)}
                        size="small"
                        fullWidth
                      >
                        <MenuItem value="">All Exchanges</MenuItem>
                        {EXCHANGES.map(exchange => (
                          <MenuItem key={exchange} value={exchange}>{exchange}</MenuItem>
                        ))}
                      </TextField>
                    </Box>
                  </AccordionDetails>
                </Accordion>                {/* Price & Market Cap - Hidden until financial data is available */}
                {false && (
                <Accordion>
                  <AccordionSummary expandIcon={<ExpandMore />}>
                    <Typography variant="subtitle1">Price & Market Cap</Typography>
                  </AccordionSummary>
                  <AccordionDetails>
                    {renderSliderFilter('Stock Price ($)', 'priceMin', 'priceMax', 0, 1000, 1, formatCurrency)}
                    {renderSliderFilter('Market Cap ($B)', 'marketCapMin', 'marketCapMax', 0, 1000, 1, (val) => `$${val}B`)}
                  </AccordionDetails>
                </Accordion>
                )}

                {/* Valuation - Hidden until financial data is available */}
                {false && (
                <Accordion>
                  <AccordionSummary expandIcon={<ExpandMore />}>
                    <Typography variant="subtitle1">Valuation</Typography>
                  </AccordionSummary>
                  <AccordionDetails>
                    {renderSliderFilter('P/E Ratio', 'peRatioMin', 'peRatioMax', 0, 50, 0.1)}
                    {renderSliderFilter('PEG Ratio', 'pegRatioMin', 'pegRatioMax', 0, 5, 0.1)}
                    {renderSliderFilter('P/B Ratio', 'pbRatioMin', 'pbRatioMax', 0, 10, 0.1)}
                  </AccordionDetails>
                </Accordion>
                )}

                {/* Additional Filters */}
                <Accordion>
                  <AccordionSummary expandIcon={<ExpandMore />}>
                    <Typography variant="subtitle1">Additional Options</Typography>
                  </AccordionSummary>
                  <AccordionDetails>
                    <Box display="flex" flexDirection="column" gap={2}>
                      <TextField
                        select
                        label="Financial Status"
                        value={filters.financialStatus || ''}
                        onChange={(e) => handleFilterChange('financialStatus', e.target.value)}
                        size="small"
                        fullWidth
                      >
                        <MenuItem value="">All Statuses</MenuItem>
                        <MenuItem value="N">Normal</MenuItem>
                        <MenuItem value="D">Deficient</MenuItem>
                        <MenuItem value="Q">Bankruptcy</MenuItem>
                        <MenuItem value="S">Suspended</MenuItem>
                      </TextField>

                      <TextField
                        select
                        label="Security Type"
                        value={filters.securityType || ''}
                        onChange={(e) => handleFilterChange('securityType', e.target.value)}
                        size="small"
                        fullWidth
                      >
                        <MenuItem value="">All Types</MenuItem>
                        <MenuItem value="stock">Stocks Only</MenuItem>
                        <MenuItem value="etf">ETFs Only</MenuItem>
                      </TextField>
                    </Box>
                  </AccordionDetails>
                </Accordion>

              </CardContent>
            </Card>
          )}
        </Grid>

        {/* Results Panel */}
        <Grid item xs={12} md={viewMode === 'simple' ? 12 : 9}>
          <Card>
            <CardContent>
              {/* Results Header */}
              <Box display="flex" alignItems="center" justifyContent="space-between" mb={3}>                <Typography variant="h6">
                  {viewMode === 'simple' ? 'Stock List' : 'Screening Results'}
                  {(stocksData?.pagination?.total || stocksData?.total) && (
                    <Chip 
                      label={`${stocksData?.pagination?.total || stocksData?.total} stocks found`} 
                      color="primary" 
                      variant="outlined" 
                      sx={{ ml: 2 }} 
                    />
                  )}
                  {stocksList.length > 0 && (
                    <Chip 
                      label={`Showing ${stocksList.length}`} 
                      color="secondary" 
                      variant="outlined" 
                      sx={{ ml: 1 }} 
                    />
                  )}
                </Typography>
                
                <Box display="flex" gap={2}>
                  <TextField
                    select
                    label="Sort By"
                    value={orderBy}
                    onChange={(e) => setOrderBy(e.target.value)}
                    size="small"
                    sx={{ minWidth: 150 }}
                  >
                    <MenuItem value="symbol">Symbol</MenuItem>
                    <MenuItem value="exchange">Exchange</MenuItem>
                    {/* Remove unsupported sort options to match backend allowedSorts */}
                    {/* <MenuItem value="security_name">Company Name</MenuItem> */}
                    {/* <MenuItem value="market_category">Category</MenuItem> */}
                  </TextField>
                  
                  <Button
                    variant={order === 'desc' ? 'contained' : 'outlined'}
                    size="small"
                    onClick={() => setOrder(order === 'asc' ? 'desc' : 'asc')}
                    startIcon={order === 'desc' ? <TrendingDown /> : <TrendingUp />}
                  >
                    {order === 'desc' ? 'Desc' : 'Asc'}
                  </Button>
                </Box>
              </Box>
              {/* Loading State */}
              {isLoading && (
                <Box display="flex" justifyContent="center" p={4}>
                  <CircularProgress size={60} />
                  <Box ml={2}>
                    <Typography variant="body2" color="text.secondary">
                      Loading stocks data...
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      API: {import.meta.env.VITE_API_URL || 'http://localhost:3001'}
                    </Typography>
                  </Box>
                </Box>
              )}{/* Error State */}
              {error && (
                <Alert severity="error" sx={{ mb: 3 }}>
                  <strong>Error loading stocks:</strong> {error.message}
                  <br />
                  <small>
                    This could be due to:
                    <ul>
                      <li>Backend API not running or accessible</li>
                      <li>Database connection issues</li>
                      <li>Incorrect API endpoint configuration</li>
                    </ul>
                    Current API URL: {import.meta.env.VITE_API_URL || 'http://localhost:3001'}
                  </small>
                </Alert>
              )}{/* Results Table */}
              {stocksData && !isLoading && (
                <>
                  {/* Debug Info in Development */}
                  {import.meta.env.DEV && (
                    <Alert severity="info" sx={{ mb: 2 }}>
                      <strong>Debug Info:</strong> Found {stocksData.data?.length || 0} items. 
                      Response structure: {JSON.stringify(Object.keys(stocksData || {}), null, 2)}
                      {stocksData.data?.[0] && (
                        <><br/>First item keys: {JSON.stringify(Object.keys(stocksData.data[0]), null, 2)}</>
                      )}
                    </Alert>                  )}

                  {/* Stock Accordions */}
                  <Box sx={{ width: '100%' }}>
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
                          <Grid container alignItems="center" spacing={2}>
                            <Grid item xs={2}>
                              <Typography variant="h6" fontWeight="bold">
                                {stock.symbol}
                              </Typography>
                              <Typography variant="caption" color="text.secondary">
                                {stock.exchange}
                              </Typography>
                            </Grid>
                            <Grid item xs={4}>
                              <Typography variant="body1" fontWeight="medium">
                                {stock.displayName || stock.shortName || stock.name || stock.fullName || 'N/A'}
                              </Typography>
                              <Typography variant="caption" color="text.secondary">
                                {stock.sector} • {stock.industry}
                              </Typography>
                            </Grid>
                            <Grid item xs={2}>
                              <Typography variant="body2" fontWeight="bold">
                                {stock.price?.current ? formatCurrency(stock.price.current) : 'N/A'}
                              </Typography>
                              <Typography variant="caption" color={getChangeColor(stock.price?.current - stock.price?.previousClose)}>
                                {stock.price?.current && stock.price?.previousClose
                                  ? `${stock.price.current - stock.price.previousClose > 0 ? '+' : ''}${formatPercent((stock.price.current - stock.price.previousClose) / stock.price.previousClose)}`
                                  : 'N/A'}
                              </Typography>
                            </Grid>
                            <Grid item xs={2}>
                              <Typography variant="body2">
                                {stock.marketCap ? formatCurrency(stock.marketCap) : (stock.financialMetrics?.marketCap ? formatCurrency(stock.financialMetrics.marketCap) : 'N/A')}
                              </Typography>
                              <Typography variant="caption" color="text.secondary">
                                Market Cap
                              </Typography>
                            </Grid>
                            <Grid item xs={2}>
                              <Typography variant="body2">
                                {stock.financialMetrics?.trailingPE ? formatNumber(stock.financialMetrics.trailingPE, 2) : (stock.displayData?.keyMetrics?.pe ? formatNumber(stock.displayData.keyMetrics.pe, 2) : 'N/A')}
                              </Typography>
                              <Typography variant="caption" color="text.secondary">
                                P/E Ratio
                              </Typography>
                            </Grid>
                          </Grid>
                        </AccordionSummary>
                        
                        <AccordionDetails>
                          <Grid container spacing={3}>
                            {/* Company Information */}
                            <Grid item xs={12} md={6}>
                              <Card variant="outlined">
                                <CardContent>
                                  <Typography variant="h6" gutterBottom>
                                    Company Information
                                  </Typography>
                                  <Grid container spacing={2}>                                    <Grid item xs={6}>
                                      <Typography variant="body2" color="text.secondary">Full Name</Typography>
                                      <Typography variant="body2">
                                        {stock.fullName || stock.name || stock.shortName || stock.displayName || 'N/A'}
                                      </Typography>
                                    </Grid>
                                    <Grid item xs={6}>
                                      <Typography variant="body2" color="text.secondary">Website</Typography>
                                      <Typography variant="body2">
                                        {stock.website ? (
                                          <a href={stock.website} target="_blank" rel="noopener noreferrer">
                                            {(() => { try { return new URL(stock.website).hostname; } catch { return stock.website; } })()}
                                          </a>
                                        ) : 'N/A'}
                                      </Typography>
                                    </Grid>
                                    <Grid item xs={6}>
                                      <Typography variant="body2" color="text.secondary">Employees</Typography>
                                      <Typography variant="body2">
                                        {stock.employeeCount !== undefined && stock.employeeCount !== null && stock.employeeCount !== ''
                                          ? (typeof stock.employeeCount === 'number' ? formatNumber(stock.employeeCount) : stock.employeeCount)
                                          : 'N/A'}
                                      </Typography>
                                    </Grid>
                                    <Grid item xs={6}>
                                      <Typography variant="body2" color="text.secondary">Country</Typography>
                                      <Typography variant="body2">
                                        {stock.address?.country || stock.country || 'N/A'}
                                      </Typography>
                                    </Grid>
                                    <Grid item xs={12}>
                                      <Typography variant="body2" color="text.secondary">Business Summary</Typography>
                                      <Typography variant="body2" sx={{ mt: 0.5 }}>
                                        {stock.businessSummary ? 
                                          (stock.businessSummary.length > 200 ? 
                                            `${stock.businessSummary.substring(0, 200)}...` : 
                                            stock.businessSummary
                                          ) : 'N/A'
                                        }
                                      </Typography>
                                    </Grid>
                                  </Grid>
                                </CardContent>
                              </Card>
                            </Grid>

                            {/* Market Data */}
                            <Grid item xs={12} md={6}>
                              <Card variant="outlined">
                                <CardContent>
                                  <Typography variant="h6" gutterBottom>
                                    Market Data
                                  </Typography>
                                  <Grid container spacing={2}>                                    <Grid item xs={6}>
                                      <Typography variant="body2" color="text.secondary">Current Price</Typography>
                                      <Typography variant="body2" fontWeight="bold">
                                        {stock.price?.current !== undefined && stock.price?.current !== null && stock.price?.current !== ''
                                          ? formatCurrency(stock.price.current)
                                          : 'N/A'}
                                      </Typography>
                                    </Grid>
                                    <Grid item xs={6}>
                                      <Typography variant="body2" color="text.secondary">Previous Close</Typography>
                                      <Typography variant="body2">
                                        {stock.price?.previousClose !== undefined && stock.price?.previousClose !== null && stock.price?.previousClose !== ''
                                          ? formatCurrency(stock.price.previousClose)
                                          : 'N/A'}
                                      </Typography>
                                    </Grid>
                                    <Grid item xs={6}>
                                      <Typography variant="body2" color="text.secondary">Day Range</Typography>
                                      <Typography variant="body2">
                                        {stock.price?.dayLow !== undefined && stock.price?.dayHigh !== undefined && stock.price?.dayLow !== null && stock.price?.dayHigh !== null && stock.price?.dayLow !== '' && stock.price?.dayHigh !== ''
                                          ? `${formatCurrency(stock.price.dayLow)} - ${formatCurrency(stock.price.dayHigh)}`
                                          : 'N/A'}
                                      </Typography>
                                    </Grid>
                                    <Grid item xs={6}>
                                      <Typography variant="body2" color="text.secondary">52W Range</Typography>
                                      <Typography variant="body2">
                                        {stock.price?.fiftyTwoWeekLow !== undefined && stock.price?.fiftyTwoWeekHigh !== undefined && stock.price?.fiftyTwoWeekLow !== null && stock.price?.fiftyTwoWeekHigh !== null && stock.price?.fiftyTwoWeekLow !== '' && stock.price?.fiftyTwoWeekHigh !== ''
                                          ? `${formatCurrency(stock.price.fiftyTwoWeekLow)} - ${formatCurrency(stock.price.fiftyTwoWeekHigh)}`
                                          : 'N/A'}
                                      </Typography>
                                    </Grid>
                                    <Grid item xs={6}>
                                      <Typography variant="body2" color="text.secondary">Volume</Typography>
                                      <Typography variant="body2">
                                        {stock.volume !== undefined && stock.volume !== null && stock.volume !== ''
                                          ? formatNumber(stock.volume)
                                          : 'N/A'}
                                      </Typography>
                                    </Grid>
                                    <Grid item xs={6}>
                                      <Typography variant="body2" color="text.secondary">Avg Volume</Typography>
                                      <Typography variant="body2">
                                        {stock.averageVolume !== undefined && stock.averageVolume !== null && stock.averageVolume !== ''
                                          ? formatNumber(stock.averageVolume)
                                          : 'N/A'}
                                      </Typography>
                                    </Grid>
                                  </Grid>
                                </CardContent>
                              </Card>
                            </Grid>

                            {/* Financial Metrics */}
                            <Grid item xs={12} md={6}>
                              <Card variant="outlined">
                                <CardContent>
                                  <Typography variant="h6" gutterBottom>
                                    Financial Metrics
                                  </Typography>
                                  <Grid container spacing={2}>                                    <Grid item xs={6}>
                                      <Typography variant="body2" color="text.secondary">P/E Ratio</Typography>
                                      <Typography variant="body2">
                                        {stock.financialMetrics?.trailingPE !== undefined && stock.financialMetrics?.trailingPE !== null && stock.financialMetrics?.trailingPE !== ''
                                          ? formatNumber(stock.financialMetrics.trailingPE, 2)
                                          : 'N/A'}
                                      </Typography>
                                    </Grid>
                                    <Grid item xs={6}>
                                      <Typography variant="body2" color="text.secondary">PEG Ratio</Typography>
                                      <Typography variant="body2">
                                        {stock.financialMetrics?.pegRatio !== undefined && stock.financialMetrics?.pegRatio !== null && stock.financialMetrics?.pegRatio !== ''
                                          ? formatNumber(stock.financialMetrics.pegRatio, 2)
                                          : 'N/A'}
                                      </Typography>
                                    </Grid>
                                    <Grid item xs={6}>
                                      <Typography variant="body2" color="text.secondary">P/B Ratio</Typography>
                                      <Typography variant="body2">
                                        {stock.financialMetrics?.priceToBook !== undefined && stock.financialMetrics?.priceToBook !== null && stock.financialMetrics?.priceToBook !== ''
                                          ? formatNumber(stock.financialMetrics.priceToBook, 2)
                                          : 'N/A'}
                                      </Typography>
                                    </Grid>
                                    <Grid item xs={6}>
                                      <Typography variant="body2" color="text.secondary">EPS</Typography>
                                      <Typography variant="body2">
                                        {stock.financialMetrics?.epsTrailing !== undefined && stock.financialMetrics?.epsTrailing !== null && stock.financialMetrics?.epsTrailing !== ''
                                          ? formatCurrency(stock.financialMetrics.epsTrailing)
                                          : 'N/A'}
                                      </Typography>
                                    </Grid>
                                    <Grid item xs={6}>
                                      <Typography variant="body2" color="text.secondary">Revenue Growth</Typography>
                                      <Typography variant="body2">
                                        {stock.financialMetrics?.revenueGrowth !== undefined && stock.financialMetrics?.revenueGrowth !== null && stock.financialMetrics?.revenueGrowth !== ''
                                          ? formatPercent(stock.financialMetrics.revenueGrowth)
                                          : 'N/A'}
                                      </Typography>
                                    </Grid>
                                    <Grid item xs={6}>
                                      <Typography variant="body2" color="text.secondary">Profit Margin</Typography>
                                      <Typography variant="body2">
                                        {stock.financialMetrics?.profitMargin !== undefined && stock.financialMetrics?.profitMargin !== null && stock.financialMetrics?.profitMargin !== ''
                                          ? formatPercent(stock.financialMetrics.profitMargin)
                                          : 'N/A'}
                                      </Typography>
                                    </Grid>
                                  </Grid>
                                </CardContent>
                              </Card>
                            </Grid>

                            {/* Actions */}
                            <Grid item xs={12} md={6}>
                              <Card variant="outlined">
                                <CardContent>
                                  <Typography variant="h6" gutterBottom>
                                    Actions
                                  </Typography>
                                  <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                                    <Button
                                      variant="contained"
                                      startIcon={<ShowChart />}
                                      onClick={() => handleFetchPriceHistory(stock.symbol)}
                                      size="small"
                                    >
                                      Price History
                                    </Button>
                                    <Button
                                      variant="outlined"
                                      onClick={() => navigate(`/stocks/${stock.symbol}`)}
                                      size="small"
                                    >
                                      Full Details
                                    </Button>
                                    {stock.website && (
                                      <Button
                                        variant="outlined"
                                        href={stock.website}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        size="small"
                                      >
                                        Company Website
                                      </Button>
                                    )}
                                  </Box>
                                  
                                  {/* Show price history data if loaded */}
                                  {priceHistoryData[stock.symbol] && (
                                    <Box sx={{ mt: 2 }}>
                                      <Typography variant="body2" color="text.secondary" gutterBottom>
                                        Recent Price Data Loaded ({priceHistoryData[stock.symbol]?.length || 0} records)
                                      </Typography>
                                      <Typography variant="caption" color="success.main">
                                        Click "View Price History" again to see detailed view
                                      </Typography>
                                    </Box>
                                  )}
                                </CardContent>
                              </Card>
                            </Grid>
                          </Grid>
                        </AccordionDetails>
                      </Accordion>
                    ))}
                  </Box>

                  {/* Pagination */}
                  <Box sx={{ mt: 2, display: 'flex', justifyContent: 'center' }}>
                    <TablePagination
                      rowsPerPageOptions={[10, 25, 50, 100]}
                      component="div"
                      count={stocksData?.pagination?.total || stocksData?.total || 0}
                      rowsPerPage={rowsPerPage}
                      page={page}
                      onPageChange={handlePageChange}
                      onRowsPerPageChange={handleRowsPerPageChange}
                    />
                  </Box>
                </>
              )}              {/* No Results */}
              {stocksData && (stocksList.length === 0) && !isLoading && (
                <Box textAlign="center" py={6}>
                  <Typography variant="h6" color="text.secondary" gutterBottom>
                    No stocks match your criteria
                  </Typography>
                  <Typography variant="body2" color="text.secondary" mb={3}>
                    Try adjusting your search or filter criteria
                  </Typography>
                  {import.meta.env.DEV && (
                    <Typography variant="caption" display="block" color="text.secondary" mb={2}>
                      Debug: Response structure = {JSON.stringify(stocksData, null, 2)}
                    </Typography>
                  )}
                  <Button 
                    variant="outlined" 
                    onClick={handleClearFilters}
                    startIcon={<Clear />}
                  >
                    Clear All Filters
                  </Button>
                </Box>
              )}
            </CardContent>
          </Card>        </Grid>
      </Grid>

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
          <Box sx={{
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
            <Box sx={{ p: 3 }}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
                <Typography variant="h5" component="h2">
                  Price History - {priceHistoryModal.symbol}
                </Typography>
                <IconButton onClick={handleClosePriceModal}>
                  <Clear />
                </IconButton>
              </Box>

              {priceHistoryModal.loading ? (
                <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
                  <CircularProgress />
                  <Typography sx={{ ml: 2 }}>Loading comprehensive price data...</Typography>
                </Box>
              ) : priceHistoryModal.error ? (
                <Alert severity="error" sx={{ mb: 2 }}>
                  {priceHistoryModal.error.includes('Unexpected token') || priceHistoryModal.error.includes('DOCTYPE')
                    ? (
                      <>
                        Error loading price data: The server returned an invalid response (likely HTML instead of JSON).<br />
                        This usually means the backend route is missing, misconfigured, or the API server is down.<br />
                        Please check your backend logs and ensure the /api/stocks/[symbol]/prices endpoint is available and returns JSON.
                      </>
                    )
                    : `Error loading price data: ${priceHistoryModal.error}`}
                </Alert>
              ) : priceHistoryModal.data.length > 0 ? (
                <>
                  {/* Summary Statistics */}
                  {priceHistoryModal.summary && (
                    <Card variant="outlined" sx={{ mb: 3 }}>
                      <CardContent>
                        <Typography variant="h6" gutterBottom>Price Summary</Typography>
                        <Grid container spacing={2}>
                          <Grid item xs={6} sm={3}>
                            <Typography variant="body2" color="text.secondary">Current Price</Typography>
                            <Typography variant="h6">{formatCurrency(priceHistoryModal.summary.priceStats?.current)}</Typography>
                          </Grid>
                          <Grid item xs={6} sm={3}>
                            <Typography variant="body2" color="text.secondary">Period High</Typography>
                            <Typography variant="h6" color="success.main">{formatCurrency(priceHistoryModal.summary.priceStats?.periodHigh)}</Typography>
                          </Grid>
                          <Grid item xs={6} sm={3}>
                            <Typography variant="body2" color="text.secondary">Period Low</Typography>
                            <Typography variant="h6" color="error.main">{formatCurrency(priceHistoryModal.summary.priceStats?.periodLow)}</Typography>
                          </Grid>
                          <Grid item xs={6} sm={3}>
                            <Typography variant="body2" color="text.secondary">Total Records</Typography>
                            <Typography variant="h6">{priceHistoryModal.summary.dataPoints}</Typography>
                          </Grid>
                        </Grid>
                      </CardContent>
                    </Card>
                  )}

                  {/* Price Data Table */}
                  <Paper sx={{ width: '100%', overflow: 'hidden' }}>
                    <Table stickyHeader>
                      <TableHead>
                        <TableRow>
                          <TableCell><strong>Date</strong></TableCell>
                          <TableCell align="right"><strong>Open</strong></TableCell>
                          <TableCell align="right"><strong>High</strong></TableCell>
                          <TableCell align="right"><strong>Low</strong></TableCell>
                          <TableCell align="right"><strong>Close</strong></TableCell>
                          <TableCell align="right"><strong>Adj Close</strong></TableCell>
                          <TableCell align="right"><strong>Volume</strong></TableCell>
                          <TableCell align="right"><strong>Change</strong></TableCell>
                          <TableCell align="right"><strong>Change %</strong></TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {priceHistoryModal.data.map((row, index) => (
                          <TableRow key={index} hover>
                            <TableCell>{new Date(row.date).toLocaleDateString()}</TableCell>
                            <TableCell align="right">{formatCurrency(row.open)}</TableCell>
                            <TableCell align="right" sx={{ color: 'success.main' }}>{formatCurrency(row.high)}</TableCell>
                            <TableCell align="right" sx={{ color: 'error.main' }}>{formatCurrency(row.low)}</TableCell>
                            <TableCell align="right"><strong>{formatCurrency(row.close)}</strong></TableCell>
                            <TableCell align="right">{formatCurrency(row.adjClose)}</TableCell>
                            <TableCell align="right">{formatNumber(row.volume)}</TableCell>
                            <TableCell align="right" sx={{ color: getChangeColor(row.priceChange) }}>
                              {row.priceChange ? formatCurrency(row.priceChange) : 'N/A'}
                            </TableCell>
                            <TableCell align="right" sx={{ color: getChangeColor(row.priceChangePct) }}>
                              {row.priceChangePct ? formatPercent(row.priceChangePct) : 'N/A'}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </Paper>

                  <Typography variant="caption" sx={{ mt: 2, display: 'block', textAlign: 'center', color: 'text.secondary' }}>
                    Showing {priceHistoryModal.data.length} price records from your database tables
                  </Typography>
                </>
              ) : (
                <Alert severity="info">
                  No price data available for {priceHistoryModal.symbol}
                </Alert>
              )}
            </Box>
          </Box>
        </Fade>
      </Modal>
    </Container>
  )
}

export default StockExplorer
