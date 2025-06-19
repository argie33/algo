import React, { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { createComponentLogger } from '../utils/errorLogger';
import {
  Box,
  Container,
  Typography,
  Grid,
  Card,
  CardContent,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  CircularProgress,
  Alert,
  TextField,
  Button,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Chip,
  InputAdornment,
  TablePagination,
  Divider
} from '@mui/material';
import {
  ExpandMore,
  Search,
  FilterList,
  Clear
} from '@mui/icons-material';
import { formatNumber, formatDate } from '../utils/formatters';
import { getTechnicalData } from '../services/api';

function TechnicalAnalysis() {
  const logger = createComponentLogger('TechnicalAnalysis');
  const [timeframe, setTimeframe] = useState('daily');
  const [symbolFilter, setSymbolFilter] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);
  const [orderBy, setOrderBy] = useState('symbol');
  const [order, setOrder] = useState('asc');
  const [activeFilters, setActiveFilters] = useState(0);
  const [expandedRow, setExpandedRow] = useState(null);

  // Fetch technical data
  const { data: technicalData, isLoading, error, refetch } = useQuery({
    queryKey: ['technicalAnalysis', timeframe, symbolFilter, page, rowsPerPage, orderBy, order],
    queryFn: async () => {
      const params = { overview: !symbolFilter, symbol: symbolFilter, limit: rowsPerPage, page: page + 1, sortBy: orderBy, sortOrder: order };
      const result = await getTechnicalData(timeframe, params);
      if (Array.isArray(result)) return { data: result };
      if (!Array.isArray(result.data)) return { ...result, data: [] };
      return result;
    },
    onError: (error) => logger.queryError('technicalAnalysis', error, { timeframe, symbolFilter, page }),
    refetchInterval: 300000,
    retry: 2,
    staleTime: 60000
  });

  useEffect(() => {
    // Count active filters (excluding default timeframe)
    setActiveFilters(symbolFilter ? 1 : 0);
  }, [symbolFilter]);

  const handleSearch = () => {
    setSymbolFilter(searchInput.trim());
    setPage(0);
  };
  const handleClearSearch = () => {
    setSearchInput('');
    setSymbolFilter('');
    setPage(0);
  };
  const handleTimeframeChange = (e) => {
    setTimeframe(e.target.value);
    setPage(0);
  };
  const handleSort = (column) => {
    const isAsc = orderBy === column && order === 'asc';
    setOrder(isAsc ? 'desc' : 'asc');
    setOrderBy(column);
  };
  const handlePageChange = (event, newPage) => {
    setPage(newPage);
  };
  const handleRowsPerPageChange = (event) => {
    setRowsPerPage(parseInt(event.target.value, 10));
    setPage(0);
  };

  // Table columns (can be expanded)
  const columns = [
    { id: 'symbol', label: 'Symbol', sortable: true },
    { id: 'date', label: 'Date', sortable: true, format: formatDate },
    { id: 'rsi', label: 'RSI', sortable: true },
    { id: 'macd', label: 'MACD', sortable: true },
    { id: 'macd_signal', label: 'MACD Signal', sortable: true },
    { id: 'macd_hist', label: 'MACD Hist', sortable: true },
    { id: 'adx', label: 'ADX', sortable: true },
    { id: 'atr', label: 'ATR', sortable: true },
    { id: 'mfi', label: 'MFI', sortable: true },
    { id: 'roc', label: 'ROC', sortable: true },
    { id: 'mom', label: 'MOM', sortable: true },
    { id: 'bbands_upper', label: 'BB Upper', sortable: true },
    { id: 'bbands_middle', label: 'BB Middle', sortable: true },
    { id: 'bbands_lower', label: 'BB Lower', sortable: true },
    { id: 'sma_10', label: 'SMA 10', sortable: true },
    { id: 'sma_20', label: 'SMA 20', sortable: true },
    { id: 'sma_50', label: 'SMA 50', sortable: true },
    { id: 'sma_150', label: 'SMA 150', sortable: true },
    { id: 'sma_200', label: 'SMA 200', sortable: true },
    { id: 'ema_4', label: 'EMA 4', sortable: true },
    { id: 'ema_9', label: 'EMA 9', sortable: true },
    { id: 'ema_21', label: 'EMA 21', sortable: true },
    { id: 'ad', label: 'A/D', sortable: true },
    { id: 'cmf', label: 'CMF', sortable: true },
    { id: 'td_sequential', label: 'TD Seq', sortable: true },
    { id: 'td_combo', label: 'TD Combo', sortable: true },
    { id: 'marketwatch', label: 'MW', sortable: true },
    { id: 'dm', label: 'DM', sortable: true },
    { id: 'pivot_high', label: 'Pivot H', sortable: true },
    { id: 'pivot_low', label: 'Pivot L', sortable: true }
  ];

  // Accordion rendering for each row
  const renderAccordionTable = () => (
    <Box sx={{ width: '100%' }}>
      {technicalData?.data?.map((row, idx) => (
        <Accordion
          key={row.symbol + '-' + row.date + '-' + idx}
          expanded={expandedRow === idx}
          onChange={() => setExpandedRow(expandedRow === idx ? null : idx)}
          sx={{ mb: 1 }}
        >
          <AccordionSummary expandIcon={<ExpandMore />} sx={{ backgroundColor: 'grey.50', '&:hover': { backgroundColor: 'grey.100' } }}>
            <Grid container alignItems="center" spacing={2}>
              <Grid item xs={2}>
                <Typography variant="h6" fontWeight="bold">{row.symbol}</Typography>
                <Typography variant="caption" color="text.secondary">{formatDate(row.date)}</Typography>
              </Grid>
              <Grid item xs={2}><Typography variant="body2">RSI: <b>{formatNumber(row.rsi)}</b></Typography></Grid>
              <Grid item xs={2}><Typography variant="body2">MACD: <b>{formatNumber(row.macd)}</b></Typography></Grid>
              <Grid item xs={2}><Typography variant="body2">ADX: <b>{formatNumber(row.adx)}</b></Typography></Grid>
              <Grid item xs={2}><Typography variant="body2">ATR: <b>{formatNumber(row.atr)}</b></Typography></Grid>
              <Grid item xs={2}><Typography variant="body2">MFI: <b>{formatNumber(row.mfi)}</b></Typography></Grid>
            </Grid>
          </AccordionSummary>
          <AccordionDetails>
            <Grid container spacing={2}>
              {columns.map((col) => (
                <Grid item xs={12} sm={6} md={3} key={col.id}>
                  <Card variant="outlined" sx={{ height: '100%' }}>
                    <CardContent>
                      <Typography variant="subtitle2">{col.label}</Typography>
                      <Typography variant="h6">{col.format ? col.format(row[col.id]) : (row[col.id] !== undefined && row[col.id] !== null ? formatNumber(row[col.id]) : 'N/A')}</Typography>
                    </CardContent>
                  </Card>
                </Grid>
              ))}
            </Grid>
          </AccordionDetails>
        </Accordion>
      ))}
    </Box>
  );

  // Overview card (first row)
  const sampleData = technicalData?.data?.[0] || {};

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      <Box display="flex" alignItems="flex-start" gap={4}>
        {/* Left filter/search panel */}
        <Box minWidth={260} maxWidth={320}>
          <Card sx={{ mb: 3 }}>
            <CardContent>
              <Typography variant="h6" gutterBottom>Filter Technicals</Typography>
              <FormControl fullWidth size="small" sx={{ mb: 2 }}>
                <InputLabel>Timeframe</InputLabel>
                <Select value={timeframe} label="Timeframe" onChange={handleTimeframeChange}>
                  <MenuItem value="daily">Daily</MenuItem>
                  <MenuItem value="weekly">Weekly</MenuItem>
                  <MenuItem value="monthly">Monthly</MenuItem>
                </Select>
              </FormControl>
              <TextField
                label="Search Symbol"
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value.toUpperCase())}
                onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
                size="small"
                fullWidth
                sx={{ mb: 2 }}
                placeholder="e.g., AAPL"
                InputProps={{
                  startAdornment: (
                    <InputAdornment position="start">
                      <Search />
                    </InputAdornment>
                  )
                }}
              />
              <Box display="flex" gap={1} mb={2}>
                <Button variant="outlined" onClick={handleSearch} startIcon={<Search />} disabled={isLoading}>
                  {symbolFilter ? 'Search' : 'Filter'}
                </Button>
                <Button variant="outlined" startIcon={<Clear />} onClick={handleClearSearch} disabled={isLoading || !symbolFilter}>
                  Clear
                </Button>
                <Chip label={`${activeFilters} Filters`} color={activeFilters > 0 ? 'primary' : 'default'} icon={<FilterList />} />
              </Box>
            </CardContent>
          </Card>
        </Box>
        {/* Main content: overview + table */}
        <Box flex={1}>
          <Typography variant="h4" gutterBottom>Technical Analysis</Typography>
          <Divider sx={{ mb: 2 }} />
          {/* Overview summary */}
          {sampleData.symbol && (
            <Accordion sx={{ mb: 3 }}>
              <AccordionSummary expandIcon={<ExpandMore />}>
                <Typography variant="h6">Technical Overview - {sampleData.symbol}</Typography>
              </AccordionSummary>
              <AccordionDetails>
                <Grid container spacing={2}>
                  <Grid item xs={12} sm={6} md={3}>
                    <Card><CardContent><Typography variant="subtitle2">RSI</Typography><Typography variant="h6">{formatNumber(sampleData.rsi)}</Typography></CardContent></Card>
                  </Grid>
                  <Grid item xs={12} sm={6} md={3}>
                    <Card><CardContent><Typography variant="subtitle2">MACD</Typography><Typography variant="h6">{formatNumber(sampleData.macd)}</Typography></CardContent></Card>
                  </Grid>
                  <Grid item xs={12} sm={6} md={3}>
                    <Card><CardContent><Typography variant="subtitle2">ADX</Typography><Typography variant="h6">{formatNumber(sampleData.adx)}</Typography></CardContent></Card>
                  </Grid>
                  <Grid item xs={12} sm={6} md={3}>
                    <Card><CardContent><Typography variant="subtitle2">ATR</Typography><Typography variant="h6">{formatNumber(sampleData.atr)}</Typography></CardContent></Card>
                  </Grid>
                </Grid>
              </AccordionDetails>
            </Accordion>
          )}
          {/* Error/Loading/Empty states */}
          {error && (
            <Alert severity="error" sx={{ mb: 2 }}>Error loading technical data: {error.message}</Alert>
          )}
          {isLoading ? (
            <Box display="flex" flexDirection="column" alignItems="center" p={4}>
              <CircularProgress sx={{ mb: 2 }} />
              <Typography variant="body2" color="text.secondary">Loading technical data...</Typography>
            </Box>
          ) : (
            <>
              {technicalData?.data?.length === 0 ? (
                <Alert severity="warning" sx={{ mb: 2 }}>No technical data found.</Alert>
              ) : (
                renderAccordionTable()
              )}
              {/* Pagination */}
              <TablePagination
                component="div"
                count={technicalData?.pagination?.total || 0}
                page={page}
                onPageChange={handlePageChange}
                rowsPerPage={rowsPerPage}
                onRowsPerPageChange={handleRowsPerPageChange}
                rowsPerPageOptions={[10, 25, 50, 100]}
                sx={{ mt: 2 }}
              />
            </>
          )}
        </Box>
      </Box>
    </Container>
  );
}

export default TechnicalAnalysis;
