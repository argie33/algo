import React, { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { createComponentLogger } from '../utils/errorLogger'
import { screenStocks } from '../services/api'
import { formatCurrency, formatPercentage as formatPercent, formatNumber } from '../utils/formatters'
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
  Divider
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
  Bookmark
} from '@mui/icons-material'

// Create component-specific logger
const logger = createComponentLogger('StockScreener');

const INITIAL_FILTERS = {
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
  sector: '',
  industry: '',
  country: '',
  exchange: '',
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

function StockScreener() {
  const navigate = useNavigate()
  const [filters, setFilters] = useState(INITIAL_FILTERS)
  const [savedScreens, setSavedScreens] = useState([])
  const [page, setPage] = useState(0)
  const [rowsPerPage, setRowsPerPage] = useState(25)
  const [orderBy, setOrderBy] = useState('symbol') // Default to alphabetical
  const [order, setOrder] = useState('asc') // Default to ascending for alphabetical

  // Build query parameters from filters
  const buildQueryParams = () => {
    const params = new URLSearchParams()
    
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

  // Fetch screener results
  const { data: screenResults, isLoading, error, refetch } = useQuery({
    queryKey: ['stockScreener', filters, page, rowsPerPage, orderBy, order],
    queryFn: async () => {
      try {
        const params = buildQueryParams();
        const result = await screenStocks(params);
        logger.success('screenStocks', result, { 
          resultCount: result?.data?.length || 0,
          total: result?.total || 0,
          page: page + 1,
          filters: Object.keys(filters).filter(k => filters[k] !== '' && filters[k] !== false).length
        });
        return result;
      } catch (err) {
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
    retry: 2,
    retryDelay: 1000,
    onError: (err) => logger.queryError('stockScreener', err, { queryKey: ['stockScreener', filters, page, rowsPerPage, orderBy, order] })
  })

  const handleFilterChange = (field, value) => {
    setFilters(prev => ({
      ...prev,
      [field]: value
    }))
    setPage(0) // Reset to first page when filters change
  }

  const handleClearFilters = () => {
    setFilters(INITIAL_FILTERS)
    setPage(0)
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
    { id: 'market_capitalization', label: 'Market Cap', sortable: true, format: (val) => val ? formatCurrency(val) : 'N/A' },
    { id: 'pe_ratio', label: 'P/E', sortable: true, format: (val) => val ? formatNumber(val, 2) : 'N/A' },
    { id: 'dividend_yield', label: 'Div Yield', sortable: true, format: (val) => val ? formatPercent(val * 100) : 'N/A' },
    { id: 'return_on_equity', label: 'ROE', sortable: true, format: (val) => val ? formatPercent(val * 100) : 'N/A' },
    { id: 'revenue_growth', label: 'Rev Growth', sortable: true, format: (val) => val ? formatPercent(val * 100) : 'N/A' },
    { id: 'sector', label: 'Sector', sortable: true }
  ]

  // Normalize stocks list to handle both { data: [...] } and { data: { data: [...] } } API responses
  let stocksList = [];
  let totalCount = 0;
  
  if (screenResults) {
    // Handle the backend response structure: { data: [...], total: number }
    if (Array.isArray(screenResults.data)) {
      stocksList = screenResults.data;
      totalCount = screenResults.total || screenResults.data.length;
    } else if (screenResults.data && Array.isArray(screenResults.data.data)) {
      stocksList = screenResults.data.data;
      totalCount = screenResults.data.total || screenResults.data.data.length;
    }
  }

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      {/* Header */}
      <Box display="flex" alignItems="center" justifyContent="between" mb={4}>
        <Box>
          <Typography variant="h4" component="h1" fontWeight="bold" gutterBottom>
            Stock Screener
          </Typography>
          <Typography variant="body1" color="text.secondary">
            Filter and analyze stocks based on fundamental criteria
          </Typography>
        </Box>
        <Box display="flex" gap={2}>
          <Button
            variant="outlined"
            startIcon={<Clear />}
            onClick={handleClearFilters}
            disabled={getActiveFiltersCount() === 0}
          >
            Clear Filters
          </Button>
          <Chip 
            label={`${getActiveFiltersCount()} Filters Active`} 
            color={getActiveFiltersCount() > 0 ? "primary" : "default"}
            icon={<FilterList />}
          />
        </Box>
      </Box>

      <Grid container spacing={3}>
        {/* Filters Panel */}
        <Grid item xs={12} md={3}>
          <Card sx={{ position: 'sticky', top: 20 }}>
            <CardContent>
              <Typography variant="h6" gutterBottom display="flex" alignItems="center" gap={1}>
                <FilterList />
                Screening Filters
              </Typography>

              {/* Basic Filters */}
              <Accordion defaultExpanded>
                <AccordionSummary expandIcon={<ExpandMore />}>
                  <Typography variant="subtitle1">Basic Criteria</Typography>
                </AccordionSummary>
                <AccordionDetails>
                  <Box display="flex" flexDirection="column" gap={2}>
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

                    <TextField
                      label="Country"
                      value={filters.country}
                      onChange={(e) => handleFilterChange('country', e.target.value)}
                      size="small"
                      fullWidth
                      placeholder="e.g., US, CA, GB"
                    />
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

              {/* Profitability */}
              <Accordion>
                <AccordionSummary expandIcon={<ExpandMore />}>
                  <Typography variant="subtitle1">Profitability</Typography>
                </AccordionSummary>
                <AccordionDetails>
                  {renderSliderFilter('ROE (%)', 'roeMin', 'roeMax', -50, 100, 1, (val) => `${val}%`)}
                  {renderSliderFilter('ROA (%)', 'roaMin', 'roaMax', -20, 50, 1, (val) => `${val}%`)}
                  {renderSliderFilter('Net Margin (%)', 'netMarginMin', 'netMarginMax', -50, 50, 1, (val) => `${val}%`)}
                </AccordionDetails>
              </Accordion>

              {/* Growth */}
              <Accordion>
                <AccordionSummary expandIcon={<ExpandMore />}>
                  <Typography variant="subtitle1">Growth</Typography>
                </AccordionSummary>
                <AccordionDetails>
                  {renderSliderFilter('Revenue Growth (%)', 'revenueGrowthMin', 'revenueGrowthMax', -50, 100, 1, (val) => `${val}%`)}
                  {renderSliderFilter('Earnings Growth (%)', 'earningsGrowthMin', 'earningsGrowthMax', -100, 200, 1, (val) => `${val}%`)}
                  
                  <FormControlLabel
                    control={
                      <Switch
                        checked={filters.hasEarningsGrowth}
                        onChange={(e) => handleFilterChange('hasEarningsGrowth', e.target.checked)}
                      />
                    }
                    label="Positive Earnings Growth"
                  />
                </AccordionDetails>
              </Accordion>

              {/* Dividend */}
              <Accordion>
                <AccordionSummary expandIcon={<ExpandMore />}>
                  <Typography variant="subtitle1">Dividend</Typography>
                </AccordionSummary>
                <AccordionDetails>
                  {renderSliderFilter('Dividend Yield (%)', 'dividendYieldMin', 'dividendYieldMax', 0, 15, 0.1, (val) => `${val}%`)}
                  {renderSliderFilter('Payout Ratio (%)', 'payoutRatioMin', 'payoutRatioMax', 0, 200, 1, (val) => `${val}%`)}
                  
                  <FormControlLabel
                    control={
                      <Switch
                        checked={filters.paysDividends}
                        onChange={(e) => handleFilterChange('paysDividends', e.target.checked)}
                      />
                    }
                    label="Pays Dividends"
                  />
                </AccordionDetails>
              </Accordion>

              {/* Financial Health */}
              <Accordion>
                <AccordionSummary expandIcon={<ExpandMore />}>
                  <Typography variant="subtitle1">Financial Health</Typography>
                </AccordionSummary>
                <AccordionDetails>
                  {renderSliderFilter('Current Ratio', 'currentRatioMin', 'currentRatioMax', 0, 10, 0.1)}
                  {renderSliderFilter('Debt to Equity', 'debtToEquityMin', 'debtToEquityMax', 0, 5, 0.1)}
                  
                  <FormControlLabel
                    control={
                      <Switch
                        checked={filters.hasPositiveCashFlow}
                        onChange={(e) => handleFilterChange('hasPositiveCashFlow', e.target.checked)}
                      />
                    }
                    label="Positive Free Cash Flow"
                  />
                </AccordionDetails>
              </Accordion>
            </CardContent>
          </Card>
        </Grid>

        {/* Results Panel */}
        <Grid item xs={12} md={9}>
          <Card>
            <CardContent>
              {/* Results Header */}
              <Box display="flex" alignItems="center" justifyContent="between" mb={3}>
                <Typography variant="h6">
                  Screening Results
                  {totalCount > 0 && (
                    <Chip 
                      label={`${totalCount} stocks found`} 
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
                  Error loading screening results: {error.message}
                </Alert>
              )}

              {/* Results Table */}
              {screenResults && !isLoading && (
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
                        {stocksList.map((stock) => (
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
                    count={totalCount}
                    rowsPerPage={rowsPerPage}
                    page={page}
                    onPageChange={handlePageChange}
                    onRowsPerPageChange={handleRowsPerPageChange}
                  />
                </>
              )}

              {/* No Results */}
              {screenResults && stocksList.length === 0 && !isLoading && (
                <Box textAlign="center" py={6}>
                  <Typography variant="h6" color="text.secondary" gutterBottom>
                    No stocks match your criteria
                  </Typography>
                  <Typography variant="body2" color="text.secondary" mb={3}>
                    Try adjusting your filters to see more results
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

export default StockScreener
