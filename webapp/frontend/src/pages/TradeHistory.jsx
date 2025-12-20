import React, { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Paper,
  Card,
  CardContent,
  Grid,
  TextField,
  MenuItem,
  Button,
  Pagination,
  CircularProgress,
  Box,
  Typography,
  Chip
} from '@mui/material';
import './TradeHistory.css';

const API_BASE_URL = (import.meta.env && import.meta.env.VITE_API_URL) || (window.__CONFIG__ && window.__CONFIG__.API_URL) || "http://localhost:3001";

const TradeHistory = () => {
  const [page, setPage] = useState(1);
  const [limit, setLimit] = useState(25);
  const [filters, setFilters] = useState({
    source: 'alpaca,manual,optimization,user',
    symbol: '',
    type: '',
    sort: 'date_desc'
  });

  // Fetch trades
  const {
    data: tradesData,
    isLoading: tradesLoading,
    error: tradesError,
    refetch: refetchTrades
  } = useQuery({
    queryKey: ['trades', page, limit, filters],
    queryFn: async () => {
      const params = new URLSearchParams({
        page,
        limit,
        source: filters.source || 'alpaca,manual,optimization,user',
        symbol: filters.symbol || '',
        type: filters.type || '',
        sort: filters.sort || 'date_desc'
      });

      const response = await fetch(`${API_BASE_URL}/api/trades?${params}`);
      if (!response.ok) throw new Error('Failed to fetch trades');
      return response.json();
    },
    staleTime: 0
  });

  // Fetch summary
  const {
    data: summaryData,
    isLoading: summaryLoading,
    error: summaryError
  } = useQuery({
    queryKey: ['tradeSummary'],
    queryFn: async () => {
      const response = await fetch(`${API_BASE_URL}/api/trades/summary`);
      if (!response.ok) throw new Error('Failed to fetch summary');
      return response.json();
    },
    staleTime: 0
  });

  const summary = summaryData?.data || {};
  const trades = tradesData?.data?.trades || [];
  const pagination = tradesData?.data?.pagination || {};

  const handleFilterChange = (field, value) => {
    setFilters(prev => ({
      ...prev,
      [field]: value
    }));
    setPage(1);
  };

  const handleReset = () => {
    setFilters({
      source: 'alpaca,manual,optimization,user',
      symbol: '',
      type: '',
      sort: 'date_desc'
    });
    setPage(1);
  };

  const formatDate = (dateString) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  const formatCurrency = (value) => {
    if (value === null || value === undefined) return '-';
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2
    }).format(value);
  };

  const formatPercent = (value) => {
    if (value === null || value === undefined) return '-';
    return `${parseFloat(value).toFixed(2)}%`;
  };

  const getSourceColor = (source) => {
    const colors = {
      alpaca: 'primary',
      manual: 'secondary',
      optimization: 'info',
      user: 'warning'
    };
    return colors[source] || 'default';
  };

  const getPnLColor = (value) => {
    if (value === null || value === undefined) return 'inherit';
    return value > 0 ? 'success' : 'error';
  };

  return (
    <div className="trade-history-container">
      <Typography variant="h4" gutterBottom>
        Trade History
      </Typography>

      {/* Summary Cards */}
      {!summaryLoading && !summaryError && (
        <Grid container spacing={2} sx={{ marginBottom: 3 }}>
          <Grid item xs={6} sm={4} md={2}>
            <Card>
              <CardContent>
                <Typography color="textSecondary" gutterBottom>
                  Total Trades
                </Typography>
                <Typography variant="h6">
                  {summary.totalTrades || 0}
                </Typography>
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={6} sm={4} md={2}>
            <Card>
              <CardContent>
                <Typography color="textSecondary" gutterBottom>
                  Win Rate
                </Typography>
                <Typography variant="h6" sx={{ color: '#4caf50' }}>
                  {formatPercent(summary.winRate)}
                </Typography>
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={6} sm={4} md={2}>
            <Card>
              <CardContent>
                <Typography color="textSecondary" gutterBottom>
                  Total P&L
                </Typography>
                <Typography
                  variant="h6"
                  sx={{ color: summary.totalPnL >= 0 ? '#4caf50' : '#f44336' }}
                >
                  {formatCurrency(summary.totalPnL)}
                </Typography>
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={6} sm={4} md={2}>
            <Card>
              <CardContent>
                <Typography color="textSecondary" gutterBottom>
                  Winning Trades
                </Typography>
                <Typography variant="h6" sx={{ color: '#4caf50' }}>
                  {summary.winningTrades || 0}
                </Typography>
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={6} sm={4} md={2}>
            <Card>
              <CardContent>
                <Typography color="textSecondary" gutterBottom>
                  Losing Trades
                </Typography>
                <Typography variant="h6" sx={{ color: '#f44336' }}>
                  {summary.losingTrades || 0}
                </Typography>
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={6} sm={4} md={2}>
            <Card>
              <CardContent>
                <Typography color="textSecondary" gutterBottom>
                  Unique Symbols
                </Typography>
                <Typography variant="h6">
                  {summary.uniqueSymbols || 0}
                </Typography>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      )}

      {/* Filters */}
      <Paper sx={{ padding: 2, marginBottom: 3 }}>
        <Grid container spacing={2} alignItems="flex-end">
          <Grid item xs={12} sm={6} md={2}>
            <TextField
              select
              fullWidth
              label="Sort"
              value={filters.sort}
              onChange={(e) => handleFilterChange('sort', e.target.value)}
              size="small"
            >
              <MenuItem value="date_desc">Newest First</MenuItem>
              <MenuItem value="date_asc">Oldest First</MenuItem>
              <MenuItem value="pnl_desc">Best P&L First</MenuItem>
              <MenuItem value="pnl_asc">Worst P&L First</MenuItem>
            </TextField>
          </Grid>

          <Grid item xs={12} sm={6} md={2}>
            <TextField
              fullWidth
              label="Symbol"
              placeholder="AAPL,MSFT"
              value={filters.symbol}
              onChange={(e) => handleFilterChange('symbol', e.target.value)}
              size="small"
            />
          </Grid>

          <Grid item xs={12} sm={6} md={2}>
            <TextField
              select
              fullWidth
              label="Type"
              value={filters.type}
              onChange={(e) => handleFilterChange('type', e.target.value)}
              size="small"
            >
              <MenuItem value="">All Types</MenuItem>
              <MenuItem value="buy">Buy</MenuItem>
              <MenuItem value="sell">Sell</MenuItem>
            </TextField>
          </Grid>

          <Grid item xs={12} sm={6} md={2}>
            <TextField
              select
              fullWidth
              label="Limit"
              value={limit && [10, 25, 50, 100].includes(limit) ? limit : 25}
              onChange={(e) => setLimit(parseInt(e.target.value))}
              size="small"
            >
              <MenuItem value={10}>10</MenuItem>
              <MenuItem value={25}>25</MenuItem>
              <MenuItem value={50}>50</MenuItem>
              <MenuItem value={100}>100</MenuItem>
            </TextField>
          </Grid>

          <Grid item xs={12} sm={6} md={2}>
            <Button
              variant="outlined"
              fullWidth
              onClick={handleReset}
              size="small"
            >
              Reset
            </Button>
          </Grid>

          <Grid item xs={12} sm={6} md={2}>
            <Button
              variant="contained"
              fullWidth
              onClick={() => refetchTrades()}
              size="small"
            >
              Refresh
            </Button>
          </Grid>
        </Grid>
      </Paper>

      {/* Trades Table */}
      {tradesLoading && <CircularProgress />}

      {tradesError && (
        <Typography color="error">
          Error loading trades: {tradesError.message}
        </Typography>
      )}

      {!tradesLoading && !tradesError && trades.length === 0 && (
        <Typography>No trades found</Typography>
      )}

      {!tradesLoading && !tradesError && trades.length > 0 && (
        <>
          <Paper sx={{ overflowX: 'auto' }}>
            <Table>
              <TableHead>
                <TableRow sx={{ backgroundColor: '#f5f5f5' }}>
                  <TableCell>Symbol</TableCell>
                  <TableCell align="center">Type</TableCell>
                  <TableCell align="right">Quantity</TableCell>
                  <TableCell align="right">Price</TableCell>
                  <TableCell align="right">Value</TableCell>
                  <TableCell align="right">Commission</TableCell>
                  <TableCell>Date</TableCell>
                  <TableCell align="right">P&L $</TableCell>
                  <TableCell align="right">P&L %</TableCell>
                  <TableCell>Source</TableCell>
                  <TableCell>Status</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {trades.map((trade) => (
                  <TableRow key={trade.id}>
                    <TableCell sx={{ fontWeight: 'bold' }}>
                      {trade.symbol}
                    </TableCell>
                    <TableCell align="center">
                      <Chip
                        label={trade.type.toUpperCase()}
                        color={trade.type === 'buy' ? 'success' : 'error'}
                        size="small"
                        variant="outlined"
                      />
                    </TableCell>
                    <TableCell align="right">
                      {parseFloat(trade.quantity).toFixed(2)}
                    </TableCell>
                    <TableCell align="right">
                      {formatCurrency(trade.price)}
                    </TableCell>
                    <TableCell align="right">
                      {formatCurrency(trade.orderValue)}
                    </TableCell>
                    <TableCell align="right">
                      {formatCurrency(trade.commission)}
                    </TableCell>
                    <TableCell sx={{ fontSize: '0.85rem' }}>
                      {formatDate(trade.executionDate)}
                    </TableCell>
                    <TableCell
                      align="right"
                      sx={{
                        color: getPnLColor(trade.pnlAmount),
                        fontWeight: 'bold'
                      }}
                    >
                      {formatCurrency(trade.pnlAmount)}
                    </TableCell>
                    <TableCell
                      align="right"
                      sx={{
                        color: getPnLColor(trade.pnlPercentage),
                        fontWeight: 'bold'
                      }}
                    >
                      {formatPercent(trade.pnlPercentage)}
                    </TableCell>
                    <TableCell>
                      <Chip
                        label={trade.source}
                        size="small"
                        color={getSourceColor(trade.source)}
                        variant="outlined"
                      />
                    </TableCell>
                    <TableCell>
                      {trade.status ? (
                        <Chip
                          label={trade.status}
                          size="small"
                          variant="outlined"
                        />
                      ) : (
                        '-'
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Paper>

          {/* Pagination */}
          <Box sx={{ display: 'flex', justifyContent: 'center', marginTop: 3 }}>
            <Pagination
              count={pagination.totalPages || 1}
              page={page}
              onChange={(e, value) => setPage(value)}
              color="primary"
            />
          </Box>

          <Typography variant="caption" sx={{ marginTop: 2, display: 'block' }}>
            Showing {trades.length} of {pagination.total} trades (Page {page} of {pagination.totalPages})
          </Typography>
        </>
      )}
    </div>
  );
};

export default TradeHistory;
