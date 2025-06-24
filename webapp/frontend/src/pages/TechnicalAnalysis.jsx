import React, { useState, useEffect } from 'react';
import { getTechnicalData } from '../services/api';
import {
  Container, Typography, Box, Card, CardContent, Grid, Button, Paper, Table, TableHead, TableRow, TableCell, TableBody, TablePagination, TextField, CircularProgress, Alert, Chip, Autocomplete
} from '@mui/material';
import { TrendingUp, TrendingDown, ShowChart, Refresh } from '@mui/icons-material';
import { formatNumber, formatDate } from '../utils/formatters';

// TEST COMMENT: Fresh branch workflow trigger test - webapp-workflow-fix
export default function TechnicalAnalysis() {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);
  const [symbol, setSymbol] = useState('');
  const [timeframe, setTimeframe] = useState('daily');
  const [total, setTotal] = useState(0);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const params = {
        limit: rowsPerPage,
        page: page + 1
      };
      if (symbol) {
        params.symbol = symbol;
      }
      
      console.log('Fetching technical data with params:', params);
      const result = await getTechnicalData(timeframe, params);
      console.log('Technical data result:', result);
      
      if (result.error) {
        setError(result.error);
        setData([]);
        setTotal(0);
      } else {
        setData(result.data || []);
        setTotal(result.pagination?.total || (result.data ? result.data.length : 0));
      }
    } catch (e) {
      console.error('Error fetching technical data:', e);
      setError(e.message || 'Failed to load technical data');
      setData([]);
      setTotal(0);
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchData();
  }, [page, rowsPerPage, timeframe]);

  const handleSearch = () => {
    setPage(0);
    fetchData();
  };

  const handlePageChange = (event, newPage) => setPage(newPage);
  const handleRowsPerPageChange = (event) => {
    setRowsPerPage(parseInt(event.target.value, 10));
    setPage(0);
  };

  const columns = [
    { id: 'symbol', label: 'Symbol' },
    { id: 'date', label: 'Date', format: formatDate },
    { id: 'rsi', label: 'RSI' },
    { id: 'macd', label: 'MACD' },
    { id: 'macd_signal', label: 'MACD Signal' },
    { id: 'adx', label: 'ADX' },
    { id: 'atr', label: 'ATR' },
    { id: 'mfi', label: 'MFI' },
    { id: 'sma_20', label: 'SMA 20' },
    { id: 'sma_50', label: 'SMA 50' },
    { id: 'ema_9', label: 'EMA 9' },
    { id: 'ema_21', label: 'EMA 21' }
  ];

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      <Box display="flex" alignItems="center" gap={2} mb={3}>
        <ShowChart color="primary" fontSize="large" />
        <Typography variant="h4" fontWeight="bold">Technical Analysis</Typography>
      </Box>

      {/* Search Controls */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Grid container spacing={2} alignItems="center">
            <Grid item xs={12} sm={4}>
              <TextField
                label="Symbol (optional)"
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
                fullWidth
                size="small"
                placeholder="e.g. AAPL"
              />
            </Grid>
            <Grid item xs={12} sm={3}>
              <TextField
                select
                label="Timeframe"
                value={timeframe}
                onChange={(e) => setTimeframe(e.target.value)}
                fullWidth
                size="small"
                SelectProps={{ native: true }}
              >
                <option value="daily">Daily</option>
                <option value="weekly">Weekly</option>
                <option value="monthly">Monthly</option>
              </TextField>
            </Grid>
            <Grid item xs={12} sm={2}>
              <Button
                variant="contained"
                startIcon={<ShowChart />}
                onClick={handleSearch}
                disabled={loading}
                fullWidth
              >
                Search
              </Button>
            </Grid>
            <Grid item xs={12} sm={2}>
              <Button
                variant="outlined"
                startIcon={<Refresh />}
                onClick={() => {
                  setSymbol('');
                  setPage(0);
                  fetchData();
                }}
                disabled={loading}
                fullWidth
              >
                Reset
              </Button>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      {/* Error Display */}
      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {error}
        </Alert>
      )}

      {/* Data Summary */}
      {!loading && data.length > 0 && (
        <Card sx={{ mb: 3 }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Summary
            </Typography>
            <Grid container spacing={2}>
              <Grid item xs={6} sm={3}>
                <Chip 
                  label={`Total Records: ${total}`} 
                  color="primary" 
                  variant="outlined" 
                />
              </Grid>
              <Grid item xs={6} sm={3}>
                <Chip 
                  label={`Timeframe: ${timeframe}`} 
                  color="secondary" 
                  variant="outlined" 
                />
              </Grid>
              {symbol && (
                <Grid item xs={6} sm={3}>
                  <Chip 
                    label={`Symbol: ${symbol}`} 
                    color="info" 
                    variant="outlined" 
                  />
                </Grid>
              )}
            </Grid>
          </CardContent>
        </Card>
      )}

      {/* Loading State */}
      {loading && (
        <Box display="flex" justifyContent="center" py={4}>
          <CircularProgress />
        </Box>
      )}

      {/* No Data Message */}
      {!loading && data.length === 0 && !error && (
        <Alert severity="info">
          No technical data found. Try adjusting your search criteria or check if data has been loaded into the database.
        </Alert>
      )}

      {/* Data Table */}
      {!loading && data.length > 0 && (
        <Paper>
          <Table stickyHeader>
            <TableHead>
              <TableRow>
                {columns.map((column) => (
                  <TableCell key={column.id} align="center">
                    {column.label}
                  </TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {data.map((row, index) => (
                <TableRow key={`${row.symbol}-${row.date}-${index}`} hover>
                  {columns.map((column) => {
                    const value = row[column.id];
                    return (
                      <TableCell key={column.id} align="center">
                        {column.format && value !== null && value !== undefined
                          ? column.format(value)
                          : value !== null && value !== undefined
                          ? formatNumber(value)
                          : '-'}
                      </TableCell>
                    );
                  })}
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <TablePagination
            rowsPerPageOptions={[5, 10, 25, 50, 100]}
            component="div"
            count={total}
            rowsPerPage={rowsPerPage}
            page={page}
            onPageChange={handlePageChange}
            onRowsPerPageChange={handleRowsPerPageChange}
          />
        </Paper>
      )}
    </Container>
  );
}
