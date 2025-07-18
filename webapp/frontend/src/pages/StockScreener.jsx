import React, { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
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
    <div className="container mx-auto" maxWidth="xl" sx={{ py: 4 }}>
      {/* Header */}
      <div  display="flex" alignItems="center" justifyContent="between" mb={4}>
        <div>
          <div  variant="h4" component="h1" fontWeight="bold" gutterBottom>
            Institutional Stock Screener
          </div>
          <div  variant="body1" color="text.secondary">
            Professional-grade quantitative analysis and advanced factor screening
          </div>
          <div  display="flex" gap={1} mt={1}>
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="6-Factor Model" color="primary" size="small" variant="outlined" />
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="Institutional Grade" color="success" size="small" variant="outlined" />
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="Real-time Data" color="info" size="small" variant="outlined" />
          </div>
        </div>
        <div  display="flex" gap={2}>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
            variant="outlined"
            startIcon={<Clear />}
            onClick={handleClearFilters}
            disabled={getActiveFiltersCount() === 0}
          >
            Clear Filters
          </button>
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
            label={`${getActiveFiltersCount()} Filters Active`} 
            color={getActiveFiltersCount() > 0 ? "primary" : "default"}
            icon={<FilterList />}
          />
        </div>
      </div>

      {/* Quick Strategy Chips */}
      <div  mb={3}>
        <div  variant="subtitle1" fontWeight="bold" mb={2}>
          Quick Strategy Filters
        </div>
        <div  display="flex" flexWrap="wrap" gap={1}>
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
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
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
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
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
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
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
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
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
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
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
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
        </div>
      </div>

      <div className="grid" container spacing={3}>
        {/* Filters Panel */}
        <div className="grid" item xs={12} md={3}>
          <div className="bg-white shadow-md rounded-lg" sx={{ position: 'sticky', top: 20 }}>
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  variant="h6" gutterBottom display="flex" alignItems="center" gap={1}>
                <FilterList />
                Screening Filters
              </div>

              {/* Basic Filters */}
              <Accordion defaultExpanded>
                <AccordionSummary expandIcon={<ExpandMore />}>
                  <div  variant="subtitle1">Basic Criteria</div>
                </AccordionSummary>
                <AccordionDetails>
                  <div  display="flex" flexDirection="column" gap={2}>
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

                    <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                      label="Country"
                      value={filters.country}
                      onChange={(e) => handleFilterChange('country', e.target.value)}
                      size="small"
                      fullWidth
                      placeholder="e.g., US, CA, GB"
                    />
                  </div>
                </AccordionDetails>
              </Accordion>

              {/* Price & Market Cap */}
              <Accordion>
                <AccordionSummary expandIcon={<ExpandMore />}>
                  <div  variant="subtitle1">Price & Market Cap</div>
                </AccordionSummary>
                <AccordionDetails>
                  {renderSliderFilter('Stock Price ($)', 'priceMin', 'priceMax', 0, 1000, 1, formatCurrency)}
                  {renderSliderFilter('Market Cap ($B)', 'marketCapMin', 'marketCapMax', 0, 1000, 1, (val) => `$${val}B`)}
                </AccordionDetails>
              </Accordion>

              {/* Valuation */}
              <Accordion>
                <AccordionSummary expandIcon={<ExpandMore />}>
                  <div  variant="subtitle1">Valuation</div>
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
                  <div  variant="subtitle1">Profitability</div>
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
                  <div  variant="subtitle1">Growth</div>
                </AccordionSummary>
                <AccordionDetails>
                  {renderSliderFilter('Revenue Growth (%)', 'revenueGrowthMin', 'revenueGrowthMax', -50, 100, 1, (val) => `${val}%`)}
                  {renderSliderFilter('Earnings Growth (%)', 'earningsGrowthMin', 'earningsGrowthMax', -100, 200, 1, (val) => `${val}%`)}
                  
                  <div className="mb-4"Label
                    control={
                      <input type="checkbox" className="toggle"
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
                  <div  variant="subtitle1">Dividend</div>
                </AccordionSummary>
                <AccordionDetails>
                  {renderSliderFilter('Dividend Yield (%)', 'dividendYieldMin', 'dividendYieldMax', 0, 15, 0.1, (val) => `${val}%`)}
                  {renderSliderFilter('Payout Ratio (%)', 'payoutRatioMin', 'payoutRatioMax', 0, 200, 1, (val) => `${val}%`)}
                  
                  <div className="mb-4"Label
                    control={
                      <input type="checkbox" className="toggle"
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
                  <div  variant="subtitle1">Financial Health</div>
                </AccordionSummary>
                <AccordionDetails>
                  {renderSliderFilter('Current Ratio', 'currentRatioMin', 'currentRatioMax', 0, 10, 0.1)}
                  {renderSliderFilter('Debt to Equity', 'debtToEquityMin', 'debtToEquityMax', 0, 5, 0.1)}
                  
                  <div className="mb-4"Label
                    control={
                      <input type="checkbox" className="toggle"
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
                  <div  variant="subtitle1">Advanced Factor Analysis</div>
                </AccordionSummary>
                <AccordionDetails>
                  <div  variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                    Screen based on our proprietary 6-factor scoring model
                  </div>
                  
                  {/* Quality Score */}
                  <div  sx={{ mb: 3 }}>
                    <div  variant="body2" sx={{ mb: 1 }}>Quality Score (0-100)</div>
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
                  </div>

                  {/* Growth Score */}
                  <div  sx={{ mb: 3 }}>
                    <div  variant="body2" sx={{ mb: 1 }}>Growth Score (0-100)</div>
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
                  </div>

                  {/* Value Score */}
                  <div  sx={{ mb: 3 }}>
                    <div  variant="body2" sx={{ mb: 1 }}>Value Score (0-100)</div>
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
                  </div>

                  {/* Momentum Score */}
                  <div  sx={{ mb: 3 }}>
                    <div  variant="body2" sx={{ mb: 1 }}>Momentum Score (0-100)</div>
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
                  </div>

                  {/* Sentiment Score */}
                  <div  sx={{ mb: 3 }}>
                    <div  variant="body2" sx={{ mb: 1 }}>Sentiment Score (0-100)</div>
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
                  </div>

                  {/* Positioning Score */}
                  <div  sx={{ mb: 3 }}>
                    <div  variant="body2" sx={{ mb: 1 }}>Positioning Score (0-100)</div>
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
                  </div>

                  {/* Composite Score */}
                  <div  sx={{ mb: 2 }}>
                    <div  variant="body2" sx={{ mb: 1 }}>Composite Score (0-100)</div>
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
                  </div>

                  {/* Preset Factor Strategies */}
                  <hr className="border-gray-200" sx={{ my: 2 }} />
                  <div  variant="body2" sx={{ mb: 2 }}>Preset Strategies:</div>
                  <div  display="flex" flexWrap="wrap" gap={1}>
                    <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
                      variant="outlined" 
                      size="small"
                      onClick={() => {
                        handleFilterChange('qualityScoreMin', 70)
                        handleFilterChange('growthScoreMin', 60)
                        handleFilterChange('valueScoreMin', 40)
                      }}
                    >
                      Quality Growth
                    </button>
                    <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
                      variant="outlined" 
                      size="small"
                      onClick={() => {
                        handleFilterChange('valueScoreMin', 70)
                        handleFilterChange('qualityScoreMin', 50)
                        handleFilterChange('momentumScoreMin', 40)
                      }}
                    >
                      Deep Value
                    </button>
                    <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
                      variant="outlined" 
                      size="small"
                      onClick={() => {
                        handleFilterChange('momentumScoreMin', 70)
                        handleFilterChange('sentimentScoreMin', 60)
                        handleFilterChange('growthScoreMin', 50)
                      }}
                    >
                      Momentum
                    </button>
                    <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
                      variant="outlined" 
                      size="small"
                      onClick={() => {
                        handleFilterChange('compositeScoreMin', 75)
                      }}
                    >
                      Top Tier
                    </button>
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
              <div  display="flex" alignItems="center" justifyContent="between" mb={3}>
                <div  variant="h6">
                  Screening Results
                  {totalCount > 0 && (
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                      label={`${totalCount} stocks found`} 
                      color="primary" 
                      variant="outlined" 
                      sx={{ ml: 2 }} 
                    />
                  )}
                </div>
                
                <div  display="flex" gap={2} alignItems="center">
                  <div className="mb-4" size="small" sx={{ minWidth: 150 }}>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Columns</label>
                    <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                      multiple
                      value={selectedColumns}
                      onChange={(e) => setSelectedColumns(e.target.value)}
                      label="Columns"
                      renderValue={(selected) => `${selected.length} columns`}
                    >
                      <option  value="symbol">Symbol</option>
                      <option  value="company_name">Company</option>
                      <option  value="price">Price</option>
                      <option  value="market_capitalization">Market Cap</option>
                      <option  value="pe_ratio">P/E Ratio</option>
                      <option  value="peg_ratio">PEG Ratio</option>
                      <option  value="pb_ratio">P/B Ratio</option>
                      <option  value="dividend_yield">Dividend Yield</option>
                      <option  value="return_on_equity">ROE</option>
                      <option  value="return_on_assets">ROA</option>
                      <option  value="revenue_growth">Revenue Growth</option>
                      <option  value="earnings_growth">EPS Growth</option>
                      <option  value="current_ratio">Current Ratio</option>
                      <option  value="debt_to_equity">Debt/Equity</option>
                      <option  value="gross_margin">Gross Margin</option>
                      <option  value="operating_margin">Operating Margin</option>
                      <option  value="net_margin">Net Margin</option>
                      <hr className="border-gray-200" />
                      <option  value="qualityScore">Quality Score</option>
                      <option  value="growthScore">Growth Score</option>
                      <option  value="valueScore">Value Score</option>
                      <option  value="momentumScore">Momentum Score</option>
                      <option  value="sentimentScore">Sentiment Score</option>
                      <option  value="positioningScore">Positioning Score</option>
                      <option  value="compositeScore">Composite Score</option>
                      <hr className="border-gray-200" />
                      <option  value="analyst_rating">Analyst Rating</option>
                      <option  value="beta">Beta</option>
                      <option  value="volume">Volume</option>
                      <option  value="sector">Sector</option>
                      <option  value="industry">Industry</option>
                      <option  value="country">Country</option>
                    </select>
                  </div>
                  
                  <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    select
                    label="Sort By"
                    value={orderBy}
                    onChange={(e) => setOrderBy(e.target.value)}
                    size="small"
                    sx={{ minWidth: 150 }}
                  >
                    <option  value="market_capitalization">Market Cap</option>
                    <option  value="price">Price</option>
                    <option  value="pe_ratio">P/E Ratio</option>
                    <option  value="dividend_yield">Dividend Yield</option>
                    <option  value="return_on_equity">ROE</option>
                    <option  value="revenue_growth">Revenue Growth</option>
                    <option  value="qualityScore">Quality Score</option>
                    <option  value="growthScore">Growth Score</option>
                    <option  value="compositeScore">Composite Score</option>
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

              {/* Advanced Controls */}
              <div  display="flex" alignItems="center" justifyContent="between" mb={3} p={2} bgcolor="grey.50" borderRadius={1}>
                <div  display="flex" gap={2} alignItems="center">
                  <div  variant="body2" color="text.secondary">
                    Advanced Controls:
                  </div>
                  <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
                    size="small" 
                    variant="outlined"
                    onClick={() => setSelectedColumns(['symbol', 'company_name', 'qualityScore', 'growthScore', 'valueScore', 'compositeScore'])}
                  >
                    Factor View
                  </button>
                  <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
                    size="small" 
                    variant="outlined"
                    onClick={() => setSelectedColumns(['symbol', 'company_name', 'price', 'market_capitalization', 'pe_ratio', 'dividend_yield', 'return_on_equity', 'sector'])}
                  >
                    Fundamental View
                  </button>
                  <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" 
                    size="small" 
                    variant="outlined"
                    onClick={() => setSelectedColumns(['symbol', 'company_name', 'price', 'revenue_growth', 'earnings_growth', 'gross_margin', 'operating_margin', 'net_margin'])}
                  >
                    Growth View
                  </button>
                </div>
                
                <div  display="flex" gap={1}>
                  <div  title="Export to CSV">
                    <button className="p-2 rounded-full hover:bg-gray-100" size="small" onClick={handleExportCSV}>
                      <FileDownload />
                    </button>
                  </div>
                  <div  title="Save Screen">
                    <button className="p-2 rounded-full hover:bg-gray-100" size="small" onClick={() => setShowSaveDialog(true)}>
                      <Save />
                    </button>
                  </div>
                  <div  title="Share Screen">
                    <button className="p-2 rounded-full hover:bg-gray-100" size="small" onClick={() => {
                      const url = new URL(window.location);
                      url.searchParams.set('filters', JSON.stringify(filters));
                      navigator.clipboard.writeText(url.toString());
                      setSnackbar({ open: true, message: 'Screen URL copied to clipboard', severity: 'success' });
                    }}>
                      <Share />
                    </button>
                  </div>
                </div>
              </div>

              {/* Loading State */}
              {isLoading && (
                <div  display="flex" justifyContent="center" p={4}>
                  <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" size={60} />
                </div>
              )}

              {/* Error State */}
              {error && (
                <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error" sx={{ mb: 3 }}>
                  Error loading screening results: {error.message}
                </div>
              )}

              {/* Results Table */}
              {screenResults && !isLoading && (
                <>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer component={Paper} variant="outlined">
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le size="small" stickyHeader>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                          {visibleColumns.map((column) => (
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell
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
                                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" size="small" label="Factor" sx={{ ml: 1, height: 16, fontSize: '0.6rem' }} />
                              )}
                              {orderBy === column.id && (
                                <div  component="span" ml={1}>
                                  {order === 'desc' ? '↓' : '↑'}
                                </div>
                              )}
                            </td>
                          ))}
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Actions</td>
                        </tr>
                      </thead>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
                        {stocksList.map((stock) => {
                          // Calculate factor scores based on available data
                          const factorScores = calculateFactorScores(stock);
                          
                          return (
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow
                              key={stock.symbol}
                              hover
                              sx={{ 
                                cursor: 'pointer',
                                '&:hover': { backgroundColor: 'action.hover' }
                              }}
                              onClick={() => handleRowClick(stock.symbol)}
                            >
                              {visibleColumns.map((column) => (
                                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell key={column.id} sx={{ width: column.width }}>
                                  {column.isFactorScore ? (
                                    <div  display="flex" alignItems="center" gap={1}>
                                      <div  variant="body2" fontWeight="bold">
                                        {factorScores[column.id]}
                                      </div>
                                      <div  width={40} height={6} bgcolor="grey.200" borderRadius={3}>
                                        <div  
                                          width={`${factorScores[column.id]}%`} 
                                          height="100%" 
                                          bgcolor={
                                            factorScores[column.id] > 70 ? 'success.main' : 
                                            factorScores[column.id] > 50 ? 'warning.main' : 'error.main'
                                          }
                                          borderRadius={3}
                                        />
                                      </div>
                                    </div>
                                  ) : column.format ? (
                                    column.format(stock[column.id])
                                  ) : (
                                    stock[column.id] || 'N/A'
                                  )}
                                </td>
                              ))}
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell onClick={(e) => e.stopPropagation()}>
                                <div  display="flex" gap={1}>
                                  <div  title="View Details">
                                    <button className="p-2 rounded-full hover:bg-gray-100" 
                                      size="small"
                                      onClick={() => handleRowClick(stock.symbol)}
                                    >
                                      <ShowChart />
                                    </button>
                                  </div>
                                  <div  title={favorites.has(stock.symbol) ? "Remove from Favorites" : "Add to Favorites"}>
                                    <button className="p-2 rounded-full hover:bg-gray-100" 
                                      size="small"
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        handleToggleFavorite(stock.symbol);
                                      }}
                                      color={favorites.has(stock.symbol) ? "primary" : "default"}
                                    >
                                      {favorites.has(stock.symbol) ? <Star /> : <StarBorder />}
                                    </button>
                                  </div>
                                  {watchlists.length > 0 && (
                                    <div className="mb-4" size="small" sx={{ minWidth: 120 }}>
                                      <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
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
                                            return <div  sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                                              <BookmarkBorder fontSize="small" />
                                              <div  variant="caption">Add to...</div>
                                            </div>
                                          }
                                          return selected;
                                        }}
                                      >
                                        <option  value="" disabled>
                                          <div  variant="caption" color="text.secondary">Select Watchlist</div>
                                        </option>
                                        {watchlists.map((watchlist) => (
                                          <option  key={watchlist.id} value={watchlist.id}>
                                            {watchlist.name}
                                          </option>
                                        ))}
                                      </select>
                                    </div>
                                  )}
                                </div>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>

                  {/* Pagination */}
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"lePagination
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
                <div  textAlign="center" py={6}>
                  <div  variant="h6" color="text.secondary" gutterBottom>
                    No stocks match your criteria
                  </div>
                  <div  variant="body2" color="text.secondary" mb={3}>
                    Try adjusting your filters to see more results
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

      {/* Saved Screens Panel */}
      {savedScreens.length > 0 && (
        <div  mt={4}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  variant="h6" gutterBottom>
                Saved Screens
              </div>
              <div className="grid" container spacing={2}>
                {savedScreens.map((screen) => (
                  <div className="grid" item xs={12} sm={6} md={4} key={screen.id}>
                    <div className="bg-white shadow-md rounded-lg" variant="outlined">
                      <div className="bg-white shadow-md rounded-lg"Content>
                        <div  variant="subtitle1" gutterBottom>
                          {screen.name}
                        </div>
                        <div  variant="body2" color="text.secondary" gutterBottom>
                          {screen.description || 'No description'}
                        </div>
                        <div  variant="caption" color="text.secondary">
                          Created: {new Date(screen.createdAt).toLocaleDateString()}
                        </div>
                        <div  variant="caption" color="text.secondary" display="block">
                          Results: {screen.resultCount}
                        </div>
                        <div  mt={2} display="flex" gap={1}>
                          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                            size="small"
                            variant="outlined"
                            onClick={() => handleLoadScreen(screen)}
                          >
                            Load
                          </button>
                          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                            size="small"
                            variant="outlined"
                            color="error"
                            onClick={() => handleDeleteScreen(screen.id)}
                          >
                            Delete
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Save Screen Dialog */}
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50" open={showSaveDialog} onClose={() => setShowSaveDialog(false)} maxWidth="sm" fullWidth>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Title>Save Screen</h2>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Content>
          <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            autoFocus
            margin="dense"
            label="Screen Name"
            fullWidth
            variant="outlined"
            value={screenName}
            onChange={(e) => setScreenName(e.target.value)}
          />
          <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            margin="dense"
            label="Description (optional)"
            fullWidth
            variant="outlined"
            multiline
            rows={3}
            value={screenDescription}
            onChange={(e) => setScreenDescription(e.target.value)}
          />
          <div  mt={2}>
            <div  variant="body2" color="text.secondary">
              This screen will save your current filters, column selection, and sorting preferences.
            </div>
          </div>
        </div>
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"Actions>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" onClick={() => setShowSaveDialog(false)}>Cancel</button>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" onClick={handleSaveScreen} variant="contained">
            Save Screen
          </button>
        </div>
      </div>

      {/* Snackbar for notifications */}
      <div className="fixed bottom-4 right-4 bg-gray-800 text-white p-4 rounded-md shadow-lg"
        open={snackbar.open}
        autoHideDuration={6000}
        onClose={() => setSnackbar({ ...snackbar, open: false })}
      >
        <div className="p-4 rounded-md bg-blue-50 border border-blue-200" 
          onClose={() => setSnackbar({ ...snackbar, open: false })} 
          severity={snackbar.severity}
        >
          {snackbar.message}
        </div>
      </div>
    </div>
  )
}

export default StockScreener
