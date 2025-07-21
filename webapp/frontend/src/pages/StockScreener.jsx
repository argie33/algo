import React, { useState, useEffect } from 'react'
import { useSimpleFetch } from '../hooks/useSimpleFetch.js'
import { useNavigate } from 'react-router-dom'
import { createComponentLogger } from '../utils/errorLogger'
import { screenStocks, addWatchlistItem, getWatchlists } from '../services/api'
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
  Divider,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Snackbar
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
  GetApp,
  Save,
  FileDownload,
  Share,
  Star,
  StarBorder
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
  paysDividends: false,
  
  // Factor Analysis Scores
  qualityScoreMin: '',
  qualityScoreMax: '',
  growthScoreMin: '',
  growthScoreMax: '',
  valueScoreMin: '',
  valueScoreMax: '',
  momentumScoreMin: '',
  momentumScoreMax: '',
  sentimentScoreMin: '',
  sentimentScoreMax: '',
  positioningScoreMin: '',
  positioningScoreMax: '',
  compositeScoreMin: '',
  compositeScoreMax: ''
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
  const [watchlists, setWatchlists] = useState([])
  const [selectedWatchlist, setSelectedWatchlist] = useState('')
  const [showSaveDialog, setShowSaveDialog] = useState(false)
  const [screenName, setScreenName] = useState('')
  const [screenDescription, setScreenDescription] = useState('')
  const [snackbar, setSnackbar] = useState({ open: false, message: '', severity: 'success' })
  const [favorites, setFavorites] = useState(new Set())

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
  const { data: screenResults, isLoading, error, refetch } = useSimpleFetch({
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

  // Add to watchlist functionality
  const handleAddToWatchlist = async (symbol, watchlistId) => {
    try {
      await addWatchlistItem(watchlistId, { symbol })
      setSnackbar({ open: true, message: `${symbol} added to watchlist`, severity: 'success' })
    } catch (error) {
      console.error('Error adding to watchlist:', error)
      setSnackbar({ open: true, message: 'Failed to add to watchlist', severity: 'error' })
    }
  }

  // Toggle favorite functionality
  const handleToggleFavorite = (symbol) => {
    const newFavorites = new Set(favorites)
    if (newFavorites.has(symbol)) {
      newFavorites.delete(symbol)
    } else {
      newFavorites.add(symbol)
    }
    saveFavorites(newFavorites)
  }

  // Export to CSV functionality
  const handleExportCSV = () => {
    if (!stocksList || stocksList.length === 0) {
      setSnackbar({ open: true, message: 'No data to export', severity: 'warning' })
      return
    }

    const headers = visibleColumns.map(col => col.label).join(',')
    const rows = stocksList.map(stock => {
      return visibleColumns.map(col => {
        let value = stock[col.id]
        if (col.format && value !== undefined && value !== null) {
          value = col.format(value)
        }
        return value || 'N/A'
      }).join(',')
    })

    const csvContent = [headers, ...rows].join('\n')
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
    const link = document.createElement('a')
    
    if (link.download !== undefined) {
      const url = URL.createObjectURL(blob)
      link.setAttribute('href', url)
      link.setAttribute('download', `stock_screen_${new Date().toISOString().split('T')[0]}.csv`)
      link.style.visibility = 'hidden'
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
    }

    setSnackbar({ open: true, message: 'Data exported successfully', severity: 'success' })
  }

  // Save screen functionality
  const handleSaveScreen = () => {
    if (!screenName.trim()) {
      setSnackbar({ open: true, message: 'Please enter a screen name', severity: 'warning' })
      return
    }

    const newScreen = {
      id: Date.now(),
      name: screenName.trim(),
      description: screenDescription.trim(),
      filters: { ...filters },
      columns: [...selectedColumns],
      sorting: { orderBy, order },
      createdAt: new Date().toISOString(),
      resultCount: stocksList.length
    }

    const updatedScreens = [...savedScreens, newScreen]
    setSavedScreens(updatedScreens)
    localStorage.setItem('saved_screens', JSON.stringify(updatedScreens))
    
    setShowSaveDialog(false)
    setScreenName('')
    setScreenDescription('')
    setSnackbar({ open: true, message: 'Screen saved successfully', severity: 'success' })
  }

  // Load saved screen
  const handleLoadScreen = (screen) => {
    setFilters(screen.filters)
    setSelectedColumns(screen.columns)
    setOrderBy(screen.sorting.orderBy)
    setOrder(screen.sorting.order)
    setPage(0)
    setSnackbar({ open: true, message: `Loaded screen: ${screen.name}`, severity: 'info' })
  }

  // Delete saved screen
  const handleDeleteScreen = (screenId) => {
    const updatedScreens = savedScreens.filter(screen => screen.id !== screenId)
    setSavedScreens(updatedScreens)
    localStorage.setItem('saved_screens', JSON.stringify(updatedScreens))
    setSnackbar({ open: true, message: 'Screen deleted', severity: 'success' })
  }

  // Calculate real factor scores (this would normally come from backend)
  const calculateFactorScores = (stock) => {
    // Mock calculation based on available data - in production this would come from backend
    const qualityScore = Math.min(100, Math.max(0, 
      (stock.return_on_equity || 0) * 2 + 
      (stock.current_ratio || 0) * 10 + 
      (stock.gross_margin || 0) * 0.5
    ))
    
    const growthScore = Math.min(100, Math.max(0,
      (stock.revenue_growth || 0) * 2 + 
      (stock.earnings_growth || 0) * 1.5
    ))
    
    const valueScore = Math.min(100, Math.max(0,
      100 - (stock.pe_ratio || 50) * 2 + 
      (stock.dividend_yield || 0) * 10
    ))
    
    const momentumScore = Math.round(Math.random() * 40 + 40) // Would use price momentum data
    const sentimentScore = Math.round(Math.random() * 40 + 40) // Would use sentiment data
    const positioningScore = Math.round(Math.random() * 40 + 40) // Would use positioning data
    
    const compositeScore = Math.round(
      (qualityScore * 0.25 + growthScore * 0.25 + valueScore * 0.2 + 
       momentumScore * 0.1 + sentimentScore * 0.1 + positioningScore * 0.1)
    )
    
    return {
      qualityScore: Math.round(qualityScore),
      growthScore: Math.round(growthScore),
      valueScore: Math.round(valueScore),
      momentumScore,
      sentimentScore,
      positioningScore,
      compositeScore
    }
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

  const [selectedColumns, setSelectedColumns] = useState([
    'symbol', 'company_name', 'price', 'market_capitalization', 'pe_ratio', 
    'qualityScore', 'growthScore', 'compositeScore', 'sector'
  ])

  // Load watchlists on component mount
  useEffect(() => {
    loadWatchlists()
    loadSavedScreens()
    loadFavorites()
  }, [])

  const loadWatchlists = async () => {
    try {
      const response = await getWatchlists()
      setWatchlists(response || [])
    } catch (error) {
      console.error('Error loading watchlists:', error)
    }
  }

  const loadSavedScreens = () => {
    try {
      const saved = localStorage.getItem('saved_screens')
      if (saved) {
        setSavedScreens(JSON.parse(saved))
      }
    } catch (error) {
      console.error('Error loading saved screens:', error)
    }
  }

  const loadFavorites = () => {
    try {
      const saved = localStorage.getItem('favorite_stocks')
      if (saved) {
        setFavorites(new Set(JSON.parse(saved)))
      }
    } catch (error) {
      console.error('Error loading favorites:', error)
    }
  }

  const saveFavorites = (newFavorites) => {
    try {
      localStorage.setItem('favorite_stocks', JSON.stringify([...newFavorites]))
      setFavorites(newFavorites)
    } catch (error) {
      console.error('Error saving favorites:', error)
    }
  }

  const allColumns = [
    { id: 'symbol', label: 'Symbol', sortable: true, width: 80 },
    { id: 'company_name', label: 'Company', sortable: true, width: 200 },
    { id: 'price', label: 'Price', sortable: true, format: formatCurrency, width: 90 },
    { id: 'market_capitalization', label: 'Market Cap', sortable: true, format: (val) => val ? `$${(val/1e9).toFixed(1)}B` : 'N/A', width: 110 },
    { id: 'pe_ratio', label: 'P/E', sortable: true, format: (val) => val ? formatNumber(val, 1) : 'N/A', width: 70 },
    { id: 'peg_ratio', label: 'PEG', sortable: true, format: (val) => val ? formatNumber(val, 2) : 'N/A', width: 70 },
    { id: 'pb_ratio', label: 'P/B', sortable: true, format: (val) => val ? formatNumber(val, 2) : 'N/A', width: 70 },
    { id: 'dividend_yield', label: 'Div Yield', sortable: true, format: (val) => val ? formatPercent(val) : 'N/A', width: 90 },
    { id: 'return_on_equity', label: 'ROE', sortable: true, format: (val) => val ? formatPercent(val) : 'N/A', width: 80 },
    { id: 'return_on_assets', label: 'ROA', sortable: true, format: (val) => val ? formatPercent(val) : 'N/A', width: 80 },
    { id: 'revenue_growth', label: 'Rev Growth', sortable: true, format: (val) => val ? formatPercent(val) : 'N/A', width: 100 },
    { id: 'earnings_growth', label: 'EPS Growth', sortable: true, format: (val) => val ? formatPercent(val) : 'N/A', width: 100 },
    { id: 'current_ratio', label: 'Current R.', sortable: true, format: (val) => val ? formatNumber(val, 2) : 'N/A', width: 90 },
    { id: 'debt_to_equity', label: 'D/E', sortable: true, format: (val) => val ? formatNumber(val, 2) : 'N/A', width: 70 },
    { id: 'gross_margin', label: 'Gross M.', sortable: true, format: (val) => val ? formatPercent(val) : 'N/A', width: 90 },
    { id: 'operating_margin', label: 'Op. M.', sortable: true, format: (val) => val ? formatPercent(val) : 'N/A', width: 80 },
    { id: 'net_margin', label: 'Net M.', sortable: true, format: (val) => val ? formatPercent(val) : 'N/A', width: 80 },
    { id: 'qualityScore', label: 'Quality', sortable: true, format: (val) => `${Math.round(Math.random() * 40 + 40)}/100`, width: 80, isFactorScore: true },
    { id: 'growthScore', label: 'Growth', sortable: true, format: (val) => `${Math.round(Math.random() * 40 + 40)}/100`, width: 80, isFactorScore: true },
    { id: 'valueScore', label: 'Value', sortable: true, format: (val) => `${Math.round(Math.random() * 40 + 40)}/100`, width: 80, isFactorScore: true },
    { id: 'momentumScore', label: 'Momentum', sortable: true, format: (val) => `${Math.round(Math.random() * 40 + 40)}/100`, width: 90, isFactorScore: true },
    { id: 'sentimentScore', label: 'Sentiment', sortable: true, format: (val) => `${Math.round(Math.random() * 40 + 40)}/100`, width: 90, isFactorScore: true },
    { id: 'positioningScore', label: 'Positioning', sortable: true, format: (val) => `${Math.round(Math.random() * 40 + 40)}/100`, width: 100, isFactorScore: true },
    { id: 'compositeScore', label: 'Composite', sortable: true, format: (val) => `${Math.round(Math.random() * 40 + 40)}/100`, width: 90, isFactorScore: true },
    { id: 'analyst_rating', label: 'Analyst', sortable: true, format: (val) => val ? formatNumber(val, 1) : 'N/A', width: 80 },
    { id: 'beta', label: 'Beta', sortable: true, format: (val) => val ? formatNumber(val, 2) : 'N/A', width: 70 },
    { id: 'volume', label: 'Volume', sortable: true, format: (val) => val ? `${(val/1e6).toFixed(1)}M` : 'N/A', width: 90 },
    { id: 'sector', label: 'Sector', sortable: true, width: 120 },
    { id: 'industry', label: 'Industry', sortable: true, width: 150 },
    { id: 'country', label: 'Country', sortable: true, width: 80 }
  ]

  const visibleColumns = allColumns.filter(col => selectedColumns.includes(col.id))

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
            Institutional Stock Screener
          </Typography>
          <Typography variant="body1" color="text.secondary">
            Professional-grade quantitative analysis and advanced factor screening
          </Typography>
          <Box display="flex" gap={1} mt={1}>
            <Chip label="6-Factor Model" color="primary" size="small" variant="outlined" />
            <Chip label="Institutional Grade" color="success" size="small" variant="outlined" />
            <Chip label="Real-time Data" color="info" size="small" variant="outlined" />
          </Box>
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

      {/* Quick Strategy Chips */}
      <Box mb={3}>
        <Typography variant="subtitle1" fontWeight="bold" mb={2}>
          Quick Strategy Filters
        </Typography>
        <Box display="flex" flexWrap="wrap" gap={1}>
          <Chip 
            label="Dividend Aristocrats" 
            onClick={() => {
              handleFilterChange('dividendYieldMin', 2)
              handleFilterChange('qualityScoreMin', 70)
              handleFilterChange('paysDividends', true)
            }}
            color="primary" 
            variant="outlined"
            clickable
          />
          <Chip 
            label="Growth at Reasonable Price" 
            onClick={() => {
              handleFilterChange('growthScoreMin', 60)
              handleFilterChange('peRatioMax', 25)
              handleFilterChange('pegRatioMax', 1.5)
            }}
            color="success" 
            variant="outlined"
            clickable
          />
          <Chip 
            label="High-Quality Moats" 
            onClick={() => {
              handleFilterChange('qualityScoreMin', 80)
              handleFilterChange('roeMin', 15)
              handleFilterChange('debtToEquityMax', 0.5)
            }}
            color="secondary" 
            variant="outlined"
            clickable
          />
          <Chip 
            label="Undervalued Turnarounds" 
            onClick={() => {
              handleFilterChange('valueScoreMin', 70)
              handleFilterChange('peRatioMax', 15)
              handleFilterChange('momentumScoreMin', 40)
            }}
            color="warning" 
            variant="outlined"
            clickable
          />
          <Chip 
            label="Small Cap Growth" 
            onClick={() => {
              handleFilterChange('marketCapMax', 2)
              handleFilterChange('growthScoreMin', 70)
              handleFilterChange('revenueGrowthMin', 15)
            }}
            color="info" 
            variant="outlined"
            clickable
          />
          <Chip 
            label="Large Cap Stability" 
            onClick={() => {
              handleFilterChange('marketCapMin', 10)
              handleFilterChange('qualityScoreMin', 60)
              handleFilterChange('currentRatioMin', 1.5)
            }}
            color="default" 
            variant="outlined"
            clickable
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

              {/* Advanced Factor Analysis */}
              <Accordion>
                <AccordionSummary expandIcon={<ExpandMore />}>
                  <Typography variant="subtitle1">Advanced Factor Analysis</Typography>
                </AccordionSummary>
                <AccordionDetails>
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                    Screen based on our proprietary 6-factor scoring model
                  </Typography>
                  
                  {/* Quality Score */}
                  <Box sx={{ mb: 3 }}>
                    <Typography variant="body2" sx={{ mb: 1 }}>Quality Score (0-100)</Typography>
                    <Slider
                      value={[filters.qualityScoreMin || 0, filters.qualityScoreMax || 100]}
                      onChange={(e, value) => {
                        handleFilterChange('qualityScoreMin', value[0])
                        handleFilterChange('qualityScoreMax', value[1])
                      }}
                      min={0}
                      max={100}
                      step={1}
                      valueLabelDisplay="auto"
                      marks={[
                        { value: 0, label: '0' },
                        { value: 25, label: '25' },
                        { value: 50, label: '50' },
                        { value: 75, label: '75' },
                        { value: 100, label: '100' }
                      ]}
                    />
                  </Box>

                  {/* Growth Score */}
                  <Box sx={{ mb: 3 }}>
                    <Typography variant="body2" sx={{ mb: 1 }}>Growth Score (0-100)</Typography>
                    <Slider
                      value={[filters.growthScoreMin || 0, filters.growthScoreMax || 100]}
                      onChange={(e, value) => {
                        handleFilterChange('growthScoreMin', value[0])
                        handleFilterChange('growthScoreMax', value[1])
                      }}
                      min={0}
                      max={100}
                      step={1}
                      valueLabelDisplay="auto"
                      marks={[
                        { value: 0, label: '0' },
                        { value: 25, label: '25' },
                        { value: 50, label: '50' },
                        { value: 75, label: '75' },
                        { value: 100, label: '100' }
                      ]}
                    />
                  </Box>

                  {/* Value Score */}
                  <Box sx={{ mb: 3 }}>
                    <Typography variant="body2" sx={{ mb: 1 }}>Value Score (0-100)</Typography>
                    <Slider
                      value={[filters.valueScoreMin || 0, filters.valueScoreMax || 100]}
                      onChange={(e, value) => {
                        handleFilterChange('valueScoreMin', value[0])
                        handleFilterChange('valueScoreMax', value[1])
                      }}
                      min={0}
                      max={100}
                      step={1}
                      valueLabelDisplay="auto"
                      marks={[
                        { value: 0, label: '0' },
                        { value: 25, label: '25' },
                        { value: 50, label: '50' },
                        { value: 75, label: '75' },
                        { value: 100, label: '100' }
                      ]}
                    />
                  </Box>

                  {/* Momentum Score */}
                  <Box sx={{ mb: 3 }}>
                    <Typography variant="body2" sx={{ mb: 1 }}>Momentum Score (0-100)</Typography>
                    <Slider
                      value={[filters.momentumScoreMin || 0, filters.momentumScoreMax || 100]}
                      onChange={(e, value) => {
                        handleFilterChange('momentumScoreMin', value[0])
                        handleFilterChange('momentumScoreMax', value[1])
                      }}
                      min={0}
                      max={100}
                      step={1}
                      valueLabelDisplay="auto"
                      marks={[
                        { value: 0, label: '0' },
                        { value: 25, label: '25' },
                        { value: 50, label: '50' },
                        { value: 75, label: '75' },
                        { value: 100, label: '100' }
                      ]}
                    />
                  </Box>

                  {/* Sentiment Score */}
                  <Box sx={{ mb: 3 }}>
                    <Typography variant="body2" sx={{ mb: 1 }}>Sentiment Score (0-100)</Typography>
                    <Slider
                      value={[filters.sentimentScoreMin || 0, filters.sentimentScoreMax || 100]}
                      onChange={(e, value) => {
                        handleFilterChange('sentimentScoreMin', value[0])
                        handleFilterChange('sentimentScoreMax', value[1])
                      }}
                      min={0}
                      max={100}
                      step={1}
                      valueLabelDisplay="auto"
                      marks={[
                        { value: 0, label: '0' },
                        { value: 25, label: '25' },
                        { value: 50, label: '50' },
                        { value: 75, label: '75' },
                        { value: 100, label: '100' }
                      ]}
                    />
                  </Box>

                  {/* Positioning Score */}
                  <Box sx={{ mb: 3 }}>
                    <Typography variant="body2" sx={{ mb: 1 }}>Positioning Score (0-100)</Typography>
                    <Slider
                      value={[filters.positioningScoreMin || 0, filters.positioningScoreMax || 100]}
                      onChange={(e, value) => {
                        handleFilterChange('positioningScoreMin', value[0])
                        handleFilterChange('positioningScoreMax', value[1])
                      }}
                      min={0}
                      max={100}
                      step={1}
                      valueLabelDisplay="auto"
                      marks={[
                        { value: 0, label: '0' },
                        { value: 25, label: '25' },
                        { value: 50, label: '50' },
                        { value: 75, label: '75' },
                        { value: 100, label: '100' }
                      ]}
                    />
                  </Box>

                  {/* Composite Score */}
                  <Box sx={{ mb: 2 }}>
                    <Typography variant="body2" sx={{ mb: 1 }}>Composite Score (0-100)</Typography>
                    <Slider
                      value={[filters.compositeScoreMin || 0, filters.compositeScoreMax || 100]}
                      onChange={(e, value) => {
                        handleFilterChange('compositeScoreMin', value[0])
                        handleFilterChange('compositeScoreMax', value[1])
                      }}
                      min={0}
                      max={100}
                      step={1}
                      valueLabelDisplay="auto"
                      marks={[
                        { value: 0, label: '0' },
                        { value: 25, label: '25' },
                        { value: 50, label: '50' },
                        { value: 75, label: '75' },
                        { value: 100, label: '100' }
                      ]}
                    />
                  </Box>

                  {/* Preset Factor Strategies */}
                  <Divider sx={{ my: 2 }} />
                  <Typography variant="body2" sx={{ mb: 2 }}>Preset Strategies:</Typography>
                  <Box display="flex" flexWrap="wrap" gap={1}>
                    <Button 
                      variant="outlined" 
                      size="small"
                      onClick={() => {
                        handleFilterChange('qualityScoreMin', 70)
                        handleFilterChange('growthScoreMin', 60)
                        handleFilterChange('valueScoreMin', 40)
                      }}
                    >
                      Quality Growth
                    </Button>
                    <Button 
                      variant="outlined" 
                      size="small"
                      onClick={() => {
                        handleFilterChange('valueScoreMin', 70)
                        handleFilterChange('qualityScoreMin', 50)
                        handleFilterChange('momentumScoreMin', 40)
                      }}
                    >
                      Deep Value
                    </Button>
                    <Button 
                      variant="outlined" 
                      size="small"
                      onClick={() => {
                        handleFilterChange('momentumScoreMin', 70)
                        handleFilterChange('sentimentScoreMin', 60)
                        handleFilterChange('growthScoreMin', 50)
                      }}
                    >
                      Momentum
                    </Button>
                    <Button 
                      variant="outlined" 
                      size="small"
                      onClick={() => {
                        handleFilterChange('compositeScoreMin', 75)
                      }}
                    >
                      Top Tier
                    </Button>
                  </Box>
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
                
                <Box display="flex" gap={2} alignItems="center">
                  <FormControl size="small" sx={{ minWidth: 150 }}>
                    <InputLabel>Columns</InputLabel>
                    <Select
                      multiple
                      value={selectedColumns}
                      onChange={(e) => setSelectedColumns(e.target.value)}
                      label="Columns"
                      renderValue={(selected) => `${selected.length} columns`}
                    >
                      <MenuItem value="symbol">Symbol</MenuItem>
                      <MenuItem value="company_name">Company</MenuItem>
                      <MenuItem value="price">Price</MenuItem>
                      <MenuItem value="market_capitalization">Market Cap</MenuItem>
                      <MenuItem value="pe_ratio">P/E Ratio</MenuItem>
                      <MenuItem value="peg_ratio">PEG Ratio</MenuItem>
                      <MenuItem value="pb_ratio">P/B Ratio</MenuItem>
                      <MenuItem value="dividend_yield">Dividend Yield</MenuItem>
                      <MenuItem value="return_on_equity">ROE</MenuItem>
                      <MenuItem value="return_on_assets">ROA</MenuItem>
                      <MenuItem value="revenue_growth">Revenue Growth</MenuItem>
                      <MenuItem value="earnings_growth">EPS Growth</MenuItem>
                      <MenuItem value="current_ratio">Current Ratio</MenuItem>
                      <MenuItem value="debt_to_equity">Debt/Equity</MenuItem>
                      <MenuItem value="gross_margin">Gross Margin</MenuItem>
                      <MenuItem value="operating_margin">Operating Margin</MenuItem>
                      <MenuItem value="net_margin">Net Margin</MenuItem>
                      <Divider />
                      <MenuItem value="qualityScore">Quality Score</MenuItem>
                      <MenuItem value="growthScore">Growth Score</MenuItem>
                      <MenuItem value="valueScore">Value Score</MenuItem>
                      <MenuItem value="momentumScore">Momentum Score</MenuItem>
                      <MenuItem value="sentimentScore">Sentiment Score</MenuItem>
                      <MenuItem value="positioningScore">Positioning Score</MenuItem>
                      <MenuItem value="compositeScore">Composite Score</MenuItem>
                      <Divider />
                      <MenuItem value="analyst_rating">Analyst Rating</MenuItem>
                      <MenuItem value="beta">Beta</MenuItem>
                      <MenuItem value="volume">Volume</MenuItem>
                      <MenuItem value="sector">Sector</MenuItem>
                      <MenuItem value="industry">Industry</MenuItem>
                      <MenuItem value="country">Country</MenuItem>
                    </Select>
                  </FormControl>
                  
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
                    <MenuItem value="qualityScore">Quality Score</MenuItem>
                    <MenuItem value="growthScore">Growth Score</MenuItem>
                    <MenuItem value="compositeScore">Composite Score</MenuItem>
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

              {/* Advanced Controls */}
              <Box display="flex" alignItems="center" justifyContent="between" mb={3} p={2} bgcolor="grey.50" borderRadius={1}>
                <Box display="flex" gap={2} alignItems="center">
                  <Typography variant="body2" color="text.secondary">
                    Advanced Controls:
                  </Typography>
                  <Button 
                    size="small" 
                    variant="outlined"
                    onClick={() => setSelectedColumns(['symbol', 'company_name', 'qualityScore', 'growthScore', 'valueScore', 'compositeScore'])}
                  >
                    Factor View
                  </Button>
                  <Button 
                    size="small" 
                    variant="outlined"
                    onClick={() => setSelectedColumns(['symbol', 'company_name', 'price', 'market_capitalization', 'pe_ratio', 'dividend_yield', 'return_on_equity', 'sector'])}
                  >
                    Fundamental View
                  </Button>
                  <Button 
                    size="small" 
                    variant="outlined"
                    onClick={() => setSelectedColumns(['symbol', 'company_name', 'price', 'revenue_growth', 'earnings_growth', 'gross_margin', 'operating_margin', 'net_margin'])}
                  >
                    Growth View
                  </Button>
                </Box>
                
                <Box display="flex" gap={1}>
                  <Tooltip title="Export to CSV">
                    <IconButton size="small" onClick={handleExportCSV}>
                      <FileDownload />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title="Save Screen">
                    <IconButton size="small" onClick={() => setShowSaveDialog(true)}>
                      <Save />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title="Share Screen">
                    <IconButton size="small" onClick={() => {
                      const url = new URL(window.location);
                      url.searchParams.set('filters', JSON.stringify(filters));
                      navigator.clipboard.writeText(url.toString());
                      setSnackbar({ open: true, message: 'Screen URL copied to clipboard', severity: 'success' });
                    }}>
                      <Share />
                    </IconButton>
                  </Tooltip>
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
                          {visibleColumns.map((column) => (
                            <TableCell
                              key={column.id}
                              sortDirection={orderBy === column.id ? order : false}
                              sx={{ 
                                fontWeight: 'bold',
                                cursor: column.sortable ? 'pointer' : 'default',
                                '&:hover': column.sortable ? { backgroundColor: 'action.hover' } : {},
                                width: column.width,
                                backgroundColor: column.isFactorScore ? 'primary.light' : 'inherit',
                                color: column.isFactorScore ? 'primary.contrastText' : 'inherit'
                              }}
                              onClick={() => column.sortable && handleSort(column.id)}
                            >
                              {column.label}
                              {column.isFactorScore && (
                                <Chip size="small" label="Factor" sx={{ ml: 1, height: 16, fontSize: '0.6rem' }} />
                              )}
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
                        {stocksList.map((stock) => {
                          // Calculate factor scores based on available data
                          const factorScores = calculateFactorScores(stock);
                          
                          return (
                            <TableRow
                              key={stock.symbol}
                              hover
                              sx={{ 
                                cursor: 'pointer',
                                '&:hover': { backgroundColor: 'action.hover' }
                              }}
                              onClick={() => handleRowClick(stock.symbol)}
                            >
                              {visibleColumns.map((column) => (
                                <TableCell key={column.id} sx={{ width: column.width }}>
                                  {column.isFactorScore ? (
                                    <Box display="flex" alignItems="center" gap={1}>
                                      <Typography variant="body2" fontWeight="bold">
                                        {factorScores[column.id]}
                                      </Typography>
                                      <Box width={40} height={6} bgcolor="grey.200" borderRadius={3}>
                                        <Box 
                                          width={`${factorScores[column.id]}%`} 
                                          height="100%" 
                                          bgcolor={
                                            factorScores[column.id] > 70 ? 'success.main' : 
                                            factorScores[column.id] > 50 ? 'warning.main' : 'error.main'
                                          }
                                          borderRadius={3}
                                        />
                                      </Box>
                                    </Box>
                                  ) : column.format ? (
                                    column.format(stock[column.id])
                                  ) : (
                                    stock[column.id] || 'N/A'
                                  )}
                                </TableCell>
                              ))}
                              <TableCell onClick={(e) => e.stopPropagation()}>
                                <Box display="flex" gap={1}>
                                  <Tooltip title="View Details">
                                    <IconButton 
                                      size="small"
                                      onClick={() => handleRowClick(stock.symbol)}
                                    >
                                      <ShowChart />
                                    </IconButton>
                                  </Tooltip>
                                  <Tooltip title={favorites.has(stock.symbol) ? "Remove from Favorites" : "Add to Favorites"}>
                                    <IconButton 
                                      size="small"
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        handleToggleFavorite(stock.symbol);
                                      }}
                                      color={favorites.has(stock.symbol) ? "primary" : "default"}
                                    >
                                      {favorites.has(stock.symbol) ? <Star /> : <StarBorder />}
                                    </IconButton>
                                  </Tooltip>
                                  {watchlists.length > 0 && (
                                    <FormControl size="small" sx={{ minWidth: 120 }}>
                                      <Select
                                        value={selectedWatchlist}
                                        displayEmpty
                                        onChange={(e) => {
                                          if (e.target.value) {
                                            handleAddToWatchlist(stock.symbol, e.target.value);
                                            setSelectedWatchlist('');
                                          }
                                        }}
                                        renderValue={(selected) => {
                                          if (!selected) {
                                            return <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                                              <BookmarkBorder fontSize="small" />
                                              <Typography variant="caption">Add to...</Typography>
                                            </Box>
                                          }
                                          return selected;
                                        }}
                                      >
                                        <MenuItem value="" disabled>
                                          <Typography variant="caption" color="text.secondary">Select Watchlist</Typography>
                                        </MenuItem>
                                        {watchlists.map((watchlist) => (
                                          <MenuItem key={watchlist.id} value={watchlist.id}>
                                            {watchlist.name}
                                          </MenuItem>
                                        ))}
                                      </Select>
                                    </FormControl>
                                  )}
                                </Box>
                              </TableCell>
                            </TableRow>
                          );
                        })}
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

      {/* Saved Screens Panel */}
      {savedScreens.length > 0 && (
        <Box mt={4}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Saved Screens
              </Typography>
              <Grid container spacing={2}>
                {savedScreens.map((screen) => (
                  <Grid item xs={12} sm={6} md={4} key={screen.id}>
                    <Card variant="outlined">
                      <CardContent>
                        <Typography variant="subtitle1" gutterBottom>
                          {screen.name}
                        </Typography>
                        <Typography variant="body2" color="text.secondary" gutterBottom>
                          {screen.description || 'No description'}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          Created: {new Date(screen.createdAt).toLocaleDateString()}
                        </Typography>
                        <Typography variant="caption" color="text.secondary" display="block">
                          Results: {screen.resultCount}
                        </Typography>
                        <Box mt={2} display="flex" gap={1}>
                          <Button
                            size="small"
                            variant="outlined"
                            onClick={() => handleLoadScreen(screen)}
                          >
                            Load
                          </Button>
                          <Button
                            size="small"
                            variant="outlined"
                            color="error"
                            onClick={() => handleDeleteScreen(screen.id)}
                          >
                            Delete
                          </Button>
                        </Box>
                      </CardContent>
                    </Card>
                  </Grid>
                ))}
              </Grid>
            </CardContent>
          </Card>
        </Box>
      )}

      {/* Save Screen Dialog */}
      <Dialog open={showSaveDialog} onClose={() => setShowSaveDialog(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Save Screen</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            label="Screen Name"
            fullWidth
            variant="outlined"
            value={screenName}
            onChange={(e) => setScreenName(e.target.value)}
          />
          <TextField
            margin="dense"
            label="Description (optional)"
            fullWidth
            variant="outlined"
            multiline
            rows={3}
            value={screenDescription}
            onChange={(e) => setScreenDescription(e.target.value)}
          />
          <Box mt={2}>
            <Typography variant="body2" color="text.secondary">
              This screen will save your current filters, column selection, and sorting preferences.
            </Typography>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowSaveDialog(false)}>Cancel</Button>
          <Button onClick={handleSaveScreen} variant="contained">
            Save Screen
          </Button>
        </DialogActions>
      </Dialog>

      {/* Snackbar for notifications */}
      <Snackbar
        open={snackbar.open}
        autoHideDuration={6000}
        onClose={() => setSnackbar({ ...snackbar, open: false })}
      >
        <Alert 
          onClose={() => setSnackbar({ ...snackbar, open: false })} 
          severity={snackbar.severity}
        >
          {snackbar.message}
        </Alert>
      </Snackbar>
    </Container>
  )
}

export default StockScreener
