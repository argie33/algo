import React, { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate, useSearchParams } from 'react-router-dom'
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
import api from '../services/api'
import { formatCurrency, formatPercentage as formatPercent, formatNumber, getChangeColor, getChangeIcon, getMarketCapCategory } from '../utils/formatters'

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

const EXCHANGES = ['NYSE', 'NASDAQ', 'AMEX']

function StockExplorer() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const [filters, setFilters] = useState(INITIAL_FILTERS)
  const [viewMode, setViewMode] = useState('simple') // 'simple' or 'advanced'
  const [page, setPage] = useState(0)
  const [rowsPerPage, setRowsPerPage] = useState(25) // Reduced from potentially higher default
  const [orderBy, setOrderBy] = useState('market_capitalization')
  const [order, setOrder] = useState('desc')
  
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
    queryFn: () => api.screenStocks(buildQueryParams()),
    keepPreviousData: true,
    staleTime: 5 * 60 * 1000, // 5 minutes
    gcTime: 10 * 60 * 1000, // 10 minutes (was cacheTime)
    retry: 2, // Reduce retries to fail faster if there's an issue
    retryDelay: 1000
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
        </Box>
      </Box>
    )
  }

  const columns = [
    { id: 'symbol', label: 'Symbol', sortable: true },
    { id: 'company_name', label: 'Company', sortable: true },
    { id: 'price', label: 'Price', sortable: true, format: formatCurrency },
    { id: 'market_capitalization', label: 'Market Cap', sortable: true, format: formatCurrency },
    { id: 'pe_ratio', label: 'P/E', sortable: true, format: (val) => val ? formatNumber(val, 2) : 'N/A' },
    { id: 'dividend_yield', label: 'Div Yield', sortable: true, format: (val) => val ? formatPercent(val) : 'N/A' },
    { id: 'return_on_equity', label: 'ROE', sortable: true, format: (val) => val ? formatPercent(val) : 'N/A' },
    { id: 'revenue_growth', label: 'Rev Growth', sortable: true, format: (val) => val ? formatPercent(val) : 'N/A' },
    { id: 'sector', label: 'Sector', sortable: true }
  ]
  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      {/* Header */}
      <Box display="flex" alignItems="center" justifyContent="space-between" mb={4}>
        <Box>
          <Typography variant="h4" component="h1" fontWeight="bold" gutterBottom>
            Stock Explorer
          </Typography>
          <Typography variant="body1" color="text.secondary">
            Browse and filter stocks with simple search or advanced screening criteria
          </Typography>
        </Box>
        <Box display="flex" gap={2} alignItems="center">
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
                </Accordion>

                {/* Price & Market Cap */}
                <Accordion>
                  <AccordionSummary expandIcon={<ExpandMore />}>
                    <Typography variant="subtitle1">Price & Market Cap</Typography>
                  </AccordionSummary>
                  <AccordionDetails>
                    {renderSliderFilter('Stock Price ($)', 'priceMin', 'priceMax', 0, 1000, 1, formatCurrency)}
                    {renderSliderFilter('Market Cap ($B)', 'marketCapMin', 'marketCapMax', 0, 1000, 1, (val) => `$${val}B`)}
                  </AccordionDetails>
                </Accordion>

                {/* Valuation */}
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

                {/* Additional filter accordions can be added here */}

              </CardContent>
            </Card>
          )}
        </Grid>

        {/* Results Panel */}
        <Grid item xs={12} md={viewMode === 'simple' ? 12 : 9}>
          <Card>
            <CardContent>
              {/* Results Header */}
              <Box display="flex" alignItems="center" justifyContent="space-between" mb={3}>
                <Typography variant="h6">
                  {viewMode === 'simple' ? 'Stock List' : 'Screening Results'}
                  {stocksData?.total && (
                    <Chip 
                      label={`${stocksData.total} stocks found`} 
                      color="primary" 
                      variant="outlined" 
                      sx={{ ml: 2 }} 
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
                    <MenuItem value="market_capitalization">Market Cap</MenuItem>
                    <MenuItem value="price">Price</MenuItem>
                    <MenuItem value="pe_ratio">P/E Ratio</MenuItem>
                    <MenuItem value="dividend_yield">Dividend Yield</MenuItem>
                    <MenuItem value="return_on_equity">ROE</MenuItem>
                    <MenuItem value="revenue_growth">Revenue Growth</MenuItem>
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
                </Box>
              )}

              {/* Error State */}
              {error && (
                <Alert severity="error" sx={{ mb: 3 }}>
                  Error loading stocks: {error.message}
                </Alert>
              )}

              {/* Results Table */}
              {stocksData && !isLoading && (
                <>
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
                      </TableHead>
                      <TableBody>
                        {stocksData.data?.map((stock) => (
                          <TableRow
                            key={stock.symbol}
                            hover
                            sx={{ 
                              cursor: 'pointer',
                              '&:hover': { backgroundColor: 'action.hover' }
                            }}
                            onClick={() => handleRowClick(stock.symbol)}
                          >
                            {columns.map((column) => (
                              <TableCell key={column.id}>
                                {column.format 
                                  ? column.format(stock[column.id])
                                  : stock[column.id] || 'N/A'
                                }
                              </TableCell>
                            ))}
                            <TableCell onClick={(e) => e.stopPropagation()}>
                              <Tooltip title="View Details">
                                <IconButton 
                                  size="small"
                                  onClick={() => handleRowClick(stock.symbol)}
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
                    count={stocksData.total || 0}
                    rowsPerPage={rowsPerPage}
                    page={page}
                    onPageChange={handlePageChange}
                    onRowsPerPageChange={handleRowsPerPageChange}
                  />
                </>
              )}

              {/* No Results */}
              {stocksData && stocksData.data?.length === 0 && !isLoading && (
                <Box textAlign="center" py={6}>
                  <Typography variant="h6" color="text.secondary" gutterBottom>
                    No stocks match your criteria
                  </Typography>
                  <Typography variant="body2" color="text.secondary" mb={3}>
                    Try adjusting your search or filter criteria
                  </Typography>
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
