import React, { useState } from 'react';
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
  Divider
} from '@mui/material';
import {
  ExpandMore,
  Search
} from '@mui/icons-material';
import { formatNumber, formatDate } from '../utils/formatters';
import { getTechnicalData } from '../services/api';

function getSignalColor(value, type) {
  if (value === null || value === undefined) return 'default';
  switch (type) {
    case 'rsi':
      if (value > 70) return 'error';
      if (value < 30) return 'success';
      return 'warning';
    case 'macd':
      return value > 0 ? 'success' : 'error';
    case 'adx':
      if (value > 25) return 'success';
      return 'warning';
    default:
      return 'default';
  }
}

export default function TechnicalAnalysis() {
  const logger = createComponentLogger('TechnicalAnalysis');
  const [timeframe, setTimeframe] = useState('daily');
  const [symbolFilter, setSymbolFilter] = useState('');
  const [page, setPage] = useState(1);
  const [searchInput, setSearchInput] = useState('');
  const { data: technicalData, isLoading, error, refetch } = useQuery({
    queryKey: ['technicalAnalysis', timeframe, symbolFilter, page],
    queryFn: async () => {
      const result = await getTechnicalData(timeframe, {
        symbol: symbolFilter || undefined,
        limit: symbolFilter ? 50 : 25,
        page: page
      });
      if (Array.isArray(result)) return { data: result };
      if (!Array.isArray(result.data)) return { ...result, data: [] };
      return result;
    },
    onError: (error) => logger.queryError('technicalAnalysis', error, { timeframe, symbolFilter, page }),
    refetchInterval: 300000,
    retry: 2,
    staleTime: 60000
  });

  const handleSearch = () => {
    setSymbolFilter(searchInput.trim());
    setPage(1);
  };
  const handleClearSearch = () => {
    setSearchInput('');
    setSymbolFilter('');
    setPage(1);
  };
  const handleTimeframeChange = (e) => {
    setTimeframe(e.target.value);
    setPage(1);
  };

  // --- Summary Chips ---
  const sample = technicalData?.data?.[0] || {};
  const summaryChips = [
    { label: 'RSI', value: sample.rsi, type: 'rsi' },
    { label: 'MACD', value: sample.macd, type: 'macd' },
    { label: 'ADX', value: sample.adx, type: 'adx' },
    { label: 'ATR', value: sample.atr, type: 'default' },
    { label: 'MFI', value: sample.mfi, type: 'rsi' },
    { label: 'SMA 50', value: sample.sma_50, type: 'default' },
    { label: 'EMA 21', value: sample.ema_21, type: 'default' },
    { label: 'Pivot High', value: sample.pivot_high, type: 'default' },
    { label: 'Pivot Low', value: sample.pivot_low, type: 'default' }
  ];

  // --- Table ---
  const columns = [
    { key: 'symbol', label: 'Symbol' },
    { key: 'date', label: 'Date', render: (v) => formatDate(v) },
    { key: 'rsi', label: 'RSI', render: (v) => v != null ? formatNumber(v) : 'N/A' },
    { key: 'macd', label: 'MACD', render: (v) => v != null ? formatNumber(v, 4) : 'N/A' },
    { key: 'macd_signal', label: 'MACD Signal', render: (v) => v != null ? formatNumber(v, 4) : 'N/A' },
    { key: 'macd_hist', label: 'MACD Hist', render: (v) => v != null ? formatNumber(v, 4) : 'N/A' },
    { key: 'adx', label: 'ADX', render: (v) => v != null ? formatNumber(v) : 'N/A' },
    { key: 'atr', label: 'ATR', render: (v) => v != null ? formatNumber(v) : 'N/A' },
    { key: 'mfi', label: 'MFI', render: (v) => v != null ? formatNumber(v) : 'N/A' },
    { key: 'roc', label: 'ROC', render: (v) => v != null ? formatNumber(v) : 'N/A' },
    { key: 'mom', label: 'MOM', render: (v) => v != null ? formatNumber(v) : 'N/A' },
    { key: 'bbands_upper', label: 'BB Upper', render: (v) => v != null ? formatNumber(v) : 'N/A' },
    { key: 'bbands_middle', label: 'BB Middle', render: (v) => v != null ? formatNumber(v) : 'N/A' },
    { key: 'bbands_lower', label: 'BB Lower', render: (v) => v != null ? formatNumber(v) : 'N/A' },
    { key: 'sma_10', label: 'SMA 10', render: (v) => v != null ? formatNumber(v) : 'N/A' },
    { key: 'sma_20', label: 'SMA 20', render: (v) => v != null ? formatNumber(v) : 'N/A' },
    { key: 'sma_50', label: 'SMA 50', render: (v) => v != null ? formatNumber(v) : 'N/A' },
    { key: 'sma_150', label: 'SMA 150', render: (v) => v != null ? formatNumber(v) : 'N/A' },
    { key: 'sma_200', label: 'SMA 200', render: (v) => v != null ? formatNumber(v) : 'N/A' },
    { key: 'ema_4', label: 'EMA 4', render: (v) => v != null ? formatNumber(v) : 'N/A' },
    { key: 'ema_9', label: 'EMA 9', render: (v) => v != null ? formatNumber(v) : 'N/A' },
    { key: 'ema_21', label: 'EMA 21', render: (v) => v != null ? formatNumber(v) : 'N/A' },
    { key: 'ad', label: 'A/D', render: (v) => v != null ? formatNumber(v) : 'N/A' },
    { key: 'cmf', label: 'CMF', render: (v) => v != null ? formatNumber(v, 4) : 'N/A' },
    { key: 'td_sequential', label: 'TD Seq', render: (v) => v != null ? formatNumber(v) : 'N/A' },
    { key: 'td_combo', label: 'TD Combo', render: (v) => v != null ? formatNumber(v) : 'N/A' },
    { key: 'marketwatch', label: 'MW', render: (v) => v != null ? formatNumber(v) : 'N/A' },
    { key: 'dm', label: 'DM', render: (v) => v != null ? formatNumber(v) : 'N/A' },
    { key: 'pivot_high', label: 'Pivot H', render: (v) => v != null ? formatNumber(v) : 'N/A' },
    { key: 'pivot_low', label: 'Pivot L', render: (v) => v != null ? formatNumber(v) : 'N/A' }
  ];

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      <Typography variant="h4" fontWeight="bold" gutterBottom>
        Technical Analysis
      </Typography>
      <Card sx={{ mb: 3, p: 2 }}>
        <Grid container spacing={2} alignItems="center">
          <Grid item xs={12} sm={3} md={2}>
            <FormControl size="small" fullWidth>
              <InputLabel>Timeframe</InputLabel>
              <Select value={timeframe} label="Timeframe" onChange={handleTimeframeChange}>
                <MenuItem value="daily">Daily</MenuItem>
                <MenuItem value="weekly">Weekly</MenuItem>
                <MenuItem value="monthly">Monthly</MenuItem>
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} sm={5} md={3}>
            <TextField
              size="small"
              label="Search Symbol"
              value={searchInput}
              onChange={e => setSearchInput(e.target.value.toUpperCase())}
              onKeyPress={e => e.key === 'Enter' && handleSearch()}
              fullWidth
              placeholder="e.g., AAPL"
            />
          </Grid>
          <Grid item xs={12} sm={2} md={2}>
            <Button
              variant="contained"
              color="primary"
              startIcon={<Search />}
              onClick={handleSearch}
              fullWidth
              disabled={isLoading}
            >
              {symbolFilter ? 'Search' : 'Filter'}
            </Button>
          </Grid>
          {symbolFilter && (
            <Grid item xs={12} sm={2} md={2}>
              <Button variant="text" onClick={handleClearSearch} fullWidth disabled={isLoading}>
                Show All
              </Button>
            </Grid>
          )}
        </Grid>
      </Card>
      {/* Summary Chips */}
      <Box mb={2} display="flex" flexWrap="wrap" gap={1}>
        {summaryChips.map((chip, i) => (
          <Chip
            key={chip.label}
            label={`${chip.label}: ${chip.value != null ? formatNumber(chip.value) : 'N/A'}`}
            color={getSignalColor(chip.value, chip.type)}
            variant="outlined"
            sx={{ fontWeight: 'bold', fontSize: 16, px: 2, py: 1 }}
          />
        ))}
      </Box>
      <Divider sx={{ mb: 2 }} />
      {/* Info Alert about data display */}
      <Alert severity="info" sx={{ mb: 3 }}>
        {symbolFilter ? (
          `Showing historical data for ${symbolFilter.toUpperCase()} (${timeframe})`
        ) : (
          `Showing latest ${timeframe} technical data for all symbols. Search for a specific symbol to view its historical data.`
        )}
      </Alert>
      {/* Error State */}
      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          Error loading technical data: {error.message}
        </Alert>
      )}
      {/* Loading State */}
      {isLoading ? (
        <Box display="flex" flexDirection="column" alignItems="center" p={4}>
          <CircularProgress sx={{ mb: 2 }} />
          <Typography variant="body2" color="text.secondary">
            {symbolFilter ?
              `Loading historical data for ${symbolFilter.toUpperCase()}...` :
              `Loading latest technical data for all symbols...`
            }
          </Typography>
        </Box>
      ) : (
        <Paper elevation={1} sx={{ width: '100%', overflow: 'auto', mb: 3 }}>
          <TableContainer sx={{ maxHeight: 600 }}>
            <Table stickyHeader size="small">
              <TableHead>
                <TableRow>
                  {columns.map(col => (
                    <TableCell key={col.key} sx={{ fontWeight: 'bold', background: '#f5f5f5' }}>{col.label}</TableCell>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {Array.isArray(technicalData?.data) && technicalData.data.length > 0 ? technicalData.data.map((row, idx) => (
                  <TableRow key={row.symbol + '-' + idx} hover>
                    {columns.map(col => (
                      <TableCell key={col.key} align={col.key === 'symbol' ? 'left' : 'right'}>
                        {col.render ? col.render(row[col.key]) : row[col.key]}
                      </TableCell>
                    ))}
                  </TableRow>
                )) : (
                  <TableRow>
                    <TableCell colSpan={columns.length} align="center">
                      <Typography variant="body2" color="text.secondary">
                        No technical data available
                      </Typography>
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>
        </Paper>
      )}
      {/* Pagination for historical data */}
      {symbolFilter && technicalData?.data?.length > 0 && (
        <Box display="flex" justifyContent="center" mt={2}>
          <Button
            onClick={() => setPage(Math.max(1, page - 1))}
            disabled={page === 1 || isLoading}
            sx={{ mr: 2 }}
          >
            Previous
          </Button>
          <Typography variant="body2" sx={{ alignSelf: 'center', mx: 2 }}>
            Page {page}
          </Typography>
          <Button
            onClick={() => setPage(page + 1)}
            disabled={isLoading || (technicalData?.data?.length || 0) < 25}
          >
            Next
          </Button>
        </Box>
      )}
      {/* Overview Accordion for selected symbol */}
      {sample.symbol && (
        <Accordion sx={{ mt: 3 }}>
          <AccordionSummary expandIcon={<ExpandMore />}>
            <Typography variant="h6">
              Technical Overview - {sample.symbol}
            </Typography>
          </AccordionSummary>
          <AccordionDetails>
            <Grid container spacing={2}>
              <Grid item xs={12} sm={6} md={3}>
                <Typography variant="subtitle2">RSI</Typography>
                <Typography variant="body1" fontWeight="bold">{sample.rsi != null ? formatNumber(sample.rsi) : 'N/A'}</Typography>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <Typography variant="subtitle2">MACD</Typography>
                <Typography variant="body1" fontWeight="bold">{sample.macd != null ? formatNumber(sample.macd, 4) : 'N/A'}</Typography>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <Typography variant="subtitle2">ADX</Typography>
                <Typography variant="body1" fontWeight="bold">{sample.adx != null ? formatNumber(sample.adx) : 'N/A'}</Typography>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <Typography variant="subtitle2">ATR</Typography>
                <Typography variant="body1" fontWeight="bold">{sample.atr != null ? formatNumber(sample.atr) : 'N/A'}</Typography>
              </Grid>
              {/* Add more details as needed */}
            </Grid>
          </AccordionDetails>
        </Accordion>
      )}
    </Container>
  );
}
