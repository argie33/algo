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
  ToggleButton,
  ToggleButtonGroup,
  Tabs,
  Tab
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
import api, { screenStocks, getStockPrices, getStockPricesRecent } from '../services/api'
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
  const [viewMode, setViewMode] = useState('simple') // 'simple' or 'advanced'
  const [page, setPage] = useState(0)
  const [rowsPerPage, setRowsPerPage] = useState(25) // Reduced from potentially higher default
  const [orderBy, setOrderBy] = useState('symbol') // Default to alphabetical
  const [order, setOrder] = useState('asc') // Default to ascending
  const [expandedStock, setExpandedStock] = useState(null) // Track which stock accordion is expanded
  const [priceHistoryData, setPriceHistoryData] = useState({}) // Cache price history data
  
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

  // Fetch price history for a stock
  const handleFetchPriceHistory = async (symbol) => {
    if (priceHistoryData[symbol]) {
      // Data already loaded, navigate to a price history view or show in modal
      console.log('Price history for', symbol, priceHistoryData[symbol])
      // For now, let's navigate to the detailed stock page
      navigate(`/stocks/${symbol}`)
      return
    }

    try {
      console.log('Fetching price history for', symbol)
      const response = await getStockPricesRecent(symbol, 100) // Get last 100 days
      setPriceHistoryData(prev => ({
        ...prev,
        [symbol]: response.data
      }))
      console.log('Price history loaded for', symbol, response.data)
      // Navigate to detailed view with price data
      navigate(`/stocks/${symbol}`)
    } catch (error) {
      console.error('Error fetching price history for', symbol, error)
      // Still navigate to stock detail page even if price history fails
      navigate(`/stocks/${symbol}`)
    }
  }

  const handleViewModeChange = (event, newMode) => {
    if (newMode !== null) {
      setViewMode(newMode)
      const newParams = new URLSearchParams(searchParams)
      newParams.set('viewMode', newMode)
      setSearchParams(newParams)
    }
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
    { id: 'marketCap', label: 'Market Cap', sortable: true, format: formatCurrency, align: 'right', minWidth: 120 },
    
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
            </Button>
          )}
          
          <ToggleButtonGroup
            value={viewMode}
            exclusive
            onChange={handleViewModeChange}
            size="small"
          >
            <ToggleButton value="simple">
              <ViewList sx={{ mr: 1 }} />
              Simple
            </ToggleButton>
            <ToggleButton value="advanced">
              <Tune sx={{ mr: 1 }} />
              Advanced
            </ToggleButton>
          </ToggleButtonGroup>
          
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

                {/* Note about future features */}
                <Alert severity="info" sx={{ mt: 2 }}>
                  <Typography variant="body2">
                    <strong>Coming Soon:</strong> Price, valuation, and financial metric filters will be available once market data integration is complete.
                  </Typography>
                </Alert>

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
                  {stocksData?.data?.length && (
                    <Chip 
                      label={`Showing ${stocksData.data.length}`} 
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
                    <MenuItem value="security_name">Company Name</MenuItem>
                    <MenuItem value="exchange">Exchange</MenuItem>
                    <MenuItem value="market_category">Category</MenuItem>
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
                    {stocksData.data?.map((stock) => (
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
                                {stock.companyName || stock.security_name || 'N/A'}
                              </Typography>
                              <Typography variant="caption" color="text.secondary">
                                {stock.sector} • {stock.industry}
                              </Typography>
                            </Grid>
                            <Grid item xs={2}>
                              <Typography variant="body2" fontWeight="bold">
                                {stock.currentPrice ? formatCurrency(stock.currentPrice) : 'N/A'}
                              </Typography>
                              <Typography variant="caption" color={getChangeColor(stock.priceChange)}>
                                {stock.priceChange ? `${stock.priceChange > 0 ? '+' : ''}${formatPercent(stock.priceChange)}` : 'N/A'}
                              </Typography>
                            </Grid>
                            <Grid item xs={2}>
                              <Typography variant="body2">
                                {stock.marketCap ? formatCurrency(stock.marketCap) : 'N/A'}
                              </Typography>
                              <Typography variant="caption" color="text.secondary">
                                Market Cap
                              </Typography>
                            </Grid>
                            <Grid item xs={2}>
                              <Typography variant="body2">
                                {stock.peRatio ? formatNumber(stock.peRatio, 2) : 'N/A'}
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
                                  <Grid container spacing={2}>
                                    <Grid item xs={6}>
                                      <Typography variant="body2" color="text.secondary">Full Name</Typography>
                                      <Typography variant="body2">{stock.longName || stock.companyName || 'N/A'}</Typography>
                                    </Grid>
                                    <Grid item xs={6}>
                                      <Typography variant="body2" color="text.secondary">Website</Typography>
                                      <Typography variant="body2">
                                        {stock.website ? (
                                          <a href={stock.website} target="_blank" rel="noopener noreferrer">
                                            {new URL(stock.website).hostname}
                                          </a>
                                        ) : 'N/A'}
                                      </Typography>
                                    </Grid>
                                    <Grid item xs={6}>
                                      <Typography variant="body2" color="text.secondary">Employees</Typography>
                                      <Typography variant="body2">{stock.employeeCount ? formatNumber(stock.employeeCount) : 'N/A'}</Typography>
                                    </Grid>
                                    <Grid item xs={6}>
                                      <Typography variant="body2" color="text.secondary">Country</Typography>
                                      <Typography variant="body2">{stock.country || 'N/A'}</Typography>
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
                                  <Grid container spacing={2}>
                                    <Grid item xs={6}>
                                      <Typography variant="body2" color="text.secondary">Current Price</Typography>
                                      <Typography variant="body2" fontWeight="bold">
                                        {stock.currentPrice ? formatCurrency(stock.currentPrice) : 'N/A'}
                                      </Typography>
                                    </Grid>
                                    <Grid item xs={6}>
                                      <Typography variant="body2" color="text.secondary">Previous Close</Typography>
                                      <Typography variant="body2">{stock.previousClose ? formatCurrency(stock.previousClose) : 'N/A'}</Typography>
                                    </Grid>
                                    <Grid item xs={6}>
                                      <Typography variant="body2" color="text.secondary">Day Range</Typography>
                                      <Typography variant="body2">
                                        {stock.dayLow && stock.dayHigh ? 
                                          `${formatCurrency(stock.dayLow)} - ${formatCurrency(stock.dayHigh)}` : 'N/A'
                                        }
                                      </Typography>
                                    </Grid>
                                    <Grid item xs={6}>
                                      <Typography variant="body2" color="text.secondary">52W Range</Typography>
                                      <Typography variant="body2">
                                        {stock.fiftyTwoWeekLow && stock.fiftyTwoWeekHigh ? 
                                          `${formatCurrency(stock.fiftyTwoWeekLow)} - ${formatCurrency(stock.fiftyTwoWeekHigh)}` : 'N/A'
                                        }
                                      </Typography>
                                    </Grid>
                                    <Grid item xs={6}>
                                      <Typography variant="body2" color="text.secondary">Volume</Typography>
                                      <Typography variant="body2">{stock.volume ? formatNumber(stock.volume) : 'N/A'}</Typography>
                                    </Grid>
                                    <Grid item xs={6}>
                                      <Typography variant="body2" color="text.secondary">Avg Volume</Typography>
                                      <Typography variant="body2">{stock.averageVolume ? formatNumber(stock.averageVolume) : 'N/A'}</Typography>
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
                                  <Grid container spacing={2}>
                                    <Grid item xs={6}>
                                      <Typography variant="body2" color="text.secondary">P/E Ratio</Typography>
                                      <Typography variant="body2">{stock.peRatio ? formatNumber(stock.peRatio, 2) : 'N/A'}</Typography>
                                    </Grid>
                                    <Grid item xs={6}>
                                      <Typography variant="body2" color="text.secondary">PEG Ratio</Typography>
                                      <Typography variant="body2">{stock.pegRatio ? formatNumber(stock.pegRatio, 2) : 'N/A'}</Typography>
                                    </Grid>
                                    <Grid item xs={6}>
                                      <Typography variant="body2" color="text.secondary">P/B Ratio</Typography>
                                      <Typography variant="body2">{stock.pbRatio ? formatNumber(stock.pbRatio, 2) : 'N/A'}</Typography>
                                    </Grid>
                                    <Grid item xs={6}>
                                      <Typography variant="body2" color="text.secondary">EPS</Typography>
                                      <Typography variant="body2">{stock.eps ? formatCurrency(stock.eps) : 'N/A'}</Typography>
                                    </Grid>
                                    <Grid item xs={6}>
                                      <Typography variant="body2" color="text.secondary">Revenue Growth</Typography>
                                      <Typography variant="body2">{stock.revenueGrowth ? formatPercent(stock.revenueGrowth) : 'N/A'}</Typography>
                                    </Grid>
                                    <Grid item xs={6}>
                                      <Typography variant="body2" color="text.secondary">Profit Margin</Typography>
                                      <Typography variant="body2">{stock.profitMargin ? formatPercent(stock.profitMargin) : 'N/A'}</Typography>
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
                                      View Price History
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
              {stocksData && (!stocksData.data || stocksData.data?.length === 0) && !isLoading && (
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
          </Card>
        </Grid>
      </Grid>
    </Container>
  )
}

export default StockExplorer
