import React, { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  Box,
  Card,
  CardContent,
  Typography,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Chip,
  Grid,
  Pagination,
  LinearProgress,
  Alert,
  InputAdornment,
  Button,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  IconButton,
  Tooltip
} from '@mui/material'
import {
  Search as SearchIcon,
  FilterList as FilterIcon,
  TrendingUp,
  TrendingDown,
  Info as InfoIcon
} from '@mui/icons-material'

import { getStocks, getSectors } from '../services/api'
import { formatCurrency, formatNumber, formatPercentage, getChangeColor, getChangeIcon, getMarketCapCategory, debounce } from '../utils/formatters'

const StockList = () => {
  const navigate = useNavigate()
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [sector, setSector] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')

  // Debounce search input
  useEffect(() => {
    const handler = debounce(() => {
      setDebouncedSearch(search)
      setPage(1) // Reset to first page when searching
    }, 500)
    
    handler()
  }, [search])

  const { data: stocksData, isLoading, error } = useQuery(
    ['stocks', { page, search: debouncedSearch, sector, limit: 20 }],
    () => getStocks({ page, search: debouncedSearch, sector, limit: 20 }),
    {
      keepPreviousData: true,
    }
  )

  const { data: sectorsData } = useQuery('sectors', getSectors)

  const handlePageChange = (event, newPage) => {
    setPage(newPage)
  }

  const handleSectorChange = (event) => {
    setSector(event.target.value)
    setPage(1)
  }

  const clearFilters = () => {
    setSearch('')
    setSector('')
    setPage(1)
  }

  const handleStockClick = (ticker) => {
    navigate(`/stocks/${ticker}`)
  }

  if (error) {
    return (
      <Box>
        <Typography variant="h4" sx={{ mb: 3, fontWeight: 600 }}>
          Stock List
        </Typography>
        <Alert severity="error">
          Failed to load stocks: {error.message}
        </Alert>
      </Box>
    )
  }

  const stocks = stocksData?.data?.data || []
  const pagination = stocksData?.data?.pagination || {}
  const sectors = sectorsData?.data?.sectors || []

  return (
    <Box>
      <Typography variant="h4" sx={{ mb: 3, fontWeight: 600 }}>
        Stock List
      </Typography>

      {/* Filters */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Grid container spacing={3} alignItems="center">
            <Grid item xs={12} md={4}>
              <TextField
                fullWidth
                label="Search stocks"
                placeholder="Enter ticker or company name"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                InputProps={{
                  startAdornment: (
                    <InputAdornment position="start">
                      <SearchIcon />
                    </InputAdornment>
                  ),
                }}
              />
            </Grid>
            <Grid item xs={12} md={3}>
              <FormControl fullWidth>
                <InputLabel>Sector</InputLabel>
                <Select
                  value={sector}
                  label="Sector"
                  onChange={handleSectorChange}
                >
                  <MenuItem value="">All Sectors</MenuItem>
                  {sectors.map((s) => (
                    <MenuItem key={s.sector} value={s.sector}>
                      {s.sector} ({s.count})
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} md={2}>
              <Button
                variant="outlined"
                startIcon={<FilterIcon />}
                onClick={clearFilters}
                fullWidth
              >
                Clear Filters
              </Button>
            </Grid>
            <Grid item xs={12} md={3}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                {(search || sector) && (
                  <>
                    {search && (
                      <Chip
                        label={`Search: ${search}`}
                        onDelete={() => setSearch('')}
                        size="small"
                      />
                    )}
                    {sector && (
                      <Chip
                        label={`Sector: ${sector}`}
                        onDelete={() => setSector('')}
                        size="small"
                      />
                    )}
                  </>
                )}
              </Box>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      {/* Loading */}
      {isLoading && <LinearProgress sx={{ mb: 2 }} />}

      {/* Results */}
      <Card>
        <CardContent sx={{ p: 0 }}>
          <TableContainer component={Paper} elevation={0}>
            <Table>
              <TableHead>
                <TableRow sx={{ backgroundColor: 'grey.50' }}>
                  <TableCell sx={{ fontWeight: 600 }}>Stock</TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>Price</TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>Change</TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>Market Cap</TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>P/E</TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>P/B</TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>Dividend</TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {stocks.map((stock) => (
                  <TableRow 
                    key={stock.ticker}
                    hover
                    sx={{ 
                      cursor: 'pointer',
                      '&:hover': { backgroundColor: 'action.hover' }
                    }}
                    onClick={() => handleStockClick(stock.ticker)}
                  >
                    <TableCell>
                      <Box>
                        <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                          {stock.ticker}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          {stock.short_name}
                        </Typography>
                        <br />
                        <Chip
                          label={stock.sector || 'Other'}
                          size="small"
                          variant="outlined"
                          sx={{ mt: 0.5, fontSize: '0.7rem' }}
                        />
                      </Box>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        {formatCurrency(stock.regular_market_price)}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                        <Typography 
                          variant="body2" 
                          sx={{ 
                            color: getChangeColor(stock.regular_market_change_percent),
                            fontWeight: 600
                          }}
                        >
                          {getChangeIcon(stock.regular_market_change_percent)}
                          {formatPercentage(stock.regular_market_change_percent)}
                        </Typography>
                      </Box>
                      <Typography 
                        variant="caption" 
                        sx={{ 
                          color: getChangeColor(stock.regular_market_change),
                          display: 'block'
                        }}
                      >
                        {formatCurrency(stock.regular_market_change)}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2">
                        {formatCurrency(stock.market_cap, 0)}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {getMarketCapCategory(stock.market_cap)}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2">
                        {formatNumber(stock.trailing_pe)}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2">
                        {formatNumber(stock.price_to_book)}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2">
                        {formatPercentage(stock.dividend_yield) !== 'N/A' 
                          ? formatPercentage(stock.dividend_yield)
                          : '-'
                        }
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Tooltip title="View Details">
                        <IconButton 
                          size="small"
                          onClick={(e) => {
                            e.stopPropagation()
                            handleStockClick(stock.ticker)
                          }}
                        >
                          <InfoIcon />
                        </IconButton>
                      </Tooltip>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>

          {/* Empty State */}
          {stocks.length === 0 && !isLoading && (
            <Box sx={{ p: 4, textAlign: 'center' }}>
              <Typography variant="h6" color="text.secondary">
                No stocks found
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Try adjusting your search or filter criteria
              </Typography>
            </Box>
          )}

          {/* Pagination */}
          {pagination.totalPages > 1 && (
            <Box sx={{ p: 3, display: 'flex', justifyContent: 'center' }}>
              <Pagination
                count={pagination.totalPages}
                page={pagination.page}
                onChange={handlePageChange}
                color="primary"
                showFirstButton
                showLastButton
              />
            </Box>
          )}

          {/* Results Summary */}
          {stocks.length > 0 && (
            <Box sx={{ p: 2, borderTop: 1, borderColor: 'divider', backgroundColor: 'grey.50' }}>
              <Typography variant="caption" color="text.secondary">
                Showing {stocks.length} of {pagination.total} results
                {pagination.page > 1 && ` • Page ${pagination.page} of ${pagination.totalPages}`}
              </Typography>
            </Box>
          )}
        </CardContent>
      </Card>
    </Box>
  )
}

export default StockList
