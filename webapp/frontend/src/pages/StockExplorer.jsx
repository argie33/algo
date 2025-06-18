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
import api, { screenStocks } from '../services/api'
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
          />
        </Box>      </Box>
    )
  }
  const columns = [
    { id: 'symbol', label: 'Symbol', sortable: true },
    { id: 'security_name', label: 'Security Name', sortable: true },
    { id: 'exchange', label: 'Exchange', sortable: true },
    { id: 'market_category', label: 'Market Category', sortable: true },
    { id: 'cqs_symbol', label: 'CQS Symbol', sortable: false },
    { id: 'financial_status', label: 'Financial Status', sortable: true },
    { id: 'round_lot_size', label: 'Round Lot Size', sortable: true, format: formatNumber },
    { id: 'etf', label: 'ETF', sortable: true },
    { id: 'secondary_symbol', label: 'Secondary Symbol', sortable: false },
    { id: 'test_issue', label: 'Test Issue', sortable: true }
  ]
  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      {/* Header */}
      <Box display="flex" alignItems="center" justifyContent="space-between" mb={4}>
        <Box>
          <Typography variant="h4" component="h1" fontWeight="bold" gutterBottom>
            Stock Explorer
          </Typography>          <Typography variant="body1" color="text.secondary">
            Browse and filter stocks with simple search or advanced screening criteria
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
            <strong>Note:</strong> Currently showing basic stock information. Financial metrics (price, P/E, etc.) require additional data integration.
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
                    </Alert>
                  )}
                  
                  <TableContainer component={Paper} variant="outlined">
                    <Table size="small" stickyHeader>
                      <TableHead>
                        <TableRow>
                          {columns.map((column) => (
                            <TableCell
                              key={column.id}
                              sortDirection={orderBy === column.id ? order : false}
                              sx={{ 
                                fontWeight: 'bold',
                                cursor: column.sortable ? 'pointer' : 'default',
                                '&:hover': column.sortable ? { backgroundColor: 'action.hover' } : {}
                              }}
                              onClick={() => column.sortable && handleSort(column.id)}
                            >
                              {column.label}
                              {orderBy === column.id && (
                                <Box component="span" ml={1}>
                                  {order === 'desc' ? '↓' : '↑'}
                                </Box>
                              )}
                            </TableCell>
                          ))}
                          <TableCell>Actions</TableCell>
                        </TableRow>
                      </TableHead><TableBody>
                        {stocksData.data?.map((stock) => (
                          <TableRow
                            key={stock.ticker || stock.symbol}
                            hover
                            sx={{ 
                              cursor: 'pointer',
                              '&:hover': { backgroundColor: 'action.hover' }
                            }}
                            onClick={() => handleRowClick(stock.ticker || stock.symbol)}
                          >                            {columns.map((column) => {
                              // Map backend field names to frontend column IDs
                              let value = stock[column.id];
                              
                              // Handle field name mapping from backend API response
                              if (column.id === 'symbol' && !value) {
                                value = stock.ticker || stock.symbol;
                              } else if (column.id === 'name' && !value) {
                                value = stock.short_name || stock.security_name || stock.name || stock.fullName;
                              } else if (column.id === 'exchange' && !value) {
                                value = stock.exchange || stock.primaryExchange;
                              } else if (column.id === 'market_category' && !value) {
                                value = stock.market_category || stock.marketCategory || stock.category;
                              } else if (column.id === 'financial_status' && !value) {
                                value = stock.financial_status || stock.financialStatus;
                              } else if (column.id === 'type' && !value) {
                                value = stock.isEtf ? 'ETF' : 'Stock';
                                if (!value && stock.displayData?.type) {
                                  value = stock.displayData.type;
                                }
                              } else if (column.id === 'cqs_symbol' && !value) {
                                value = stock.cqs_symbol || stock.cqsSymbol;
                              } else if (column.id === 'round_lot_size' && !value) {
                                value = stock.round_lot_size || stock.roundLotSize;
                              }
                              
                              return (
                                <TableCell key={column.id}>
                                  {column.format 
                                    ? column.format(value)
                                    : value || 'N/A'
                                  }
                                </TableCell>
                              );
                            })}
                            <TableCell onClick={(e) => e.stopPropagation()}>
                              <Tooltip title="View Details">
                                <IconButton 
                                  size="small"
                                  onClick={() => handleRowClick(stock.ticker || stock.symbol)}
                                >
                                  <ShowChart />
                                </IconButton>
                              </Tooltip>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </TableContainer>
                  {/* Pagination */}
                  <TablePagination
                    rowsPerPageOptions={[10, 25, 50, 100]}
                    component="div"
                    count={stocksData?.pagination?.total || stocksData?.total || 0}
                    rowsPerPage={rowsPerPage}
                    page={page}
                    onPageChange={handlePageChange}
                    onRowsPerPageChange={handleRowsPerPageChange}
                  />
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
