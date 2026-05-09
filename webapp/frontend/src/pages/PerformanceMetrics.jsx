/**
 * Daily Performance Metrics Dashboard
 *
 * Shows:
 * - Sharpe Ratio, Max Drawdown, Calmar Ratio
 * - Win Rate, Profit Factor, Expectancy
 * - Trade statistics (count, duration, R-multiples)
 * - Recent closed trades
 *
 * Updates daily after algo runs at 5:30pm ET
 */

import React, { useState, useEffect } from 'react';
import {
  Box, Container, Grid, Paper, Typography, Card, CardContent,
  CircularProgress, Button, ToggleButton, ToggleButtonGroup,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
} from '@mui/material';
import { styled } from '@mui/system';
import TrendingUpIcon from '@mui/icons-material/TrendingUp';
import TrendingDownIcon from '@mui/icons-material/TrendingDown';
import EqualizerIcon from '@mui/icons-material/Equalizer';

const MetricCard = styled(Paper)(({ theme }) => ({
  padding: theme.spacing(2),
  display: 'flex',
  flexDirection: 'column',
  borderRadius: 12,
  boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
  border: '1px solid rgba(0,0,0,0.05)',
}));

const MetricValue = styled(Typography)(({ theme }) => ({
  fontSize: '1.75rem',
  fontWeight: 700,
  marginTop: theme.spacing(1),
  fontFamily: 'monospace',
}));

const MetricLabel = styled(Typography)(({ theme }) => ({
  fontSize: '0.85rem',
  color: theme.palette.text.secondary,
  textTransform: 'uppercase',
  letterSpacing: 0.5,
}));

const StatusBadge = styled(Box)(({ theme, status }) => ({
  display: 'inline-block',
  padding: '4px 12px',
  borderRadius: 20,
  fontSize: '0.75rem',
  fontWeight: 600,
  backgroundColor: status === 'good' ? '#e8f5e9' : status === 'warning' ? '#fff3e0' : '#ffebee',
  color: status === 'good' ? '#2e7d32' : status === 'warning' ? '#e65100' : '#c62828',
}));

export default function PerformanceMetrics() {
  const [metrics, setMetrics] = useState(null);
  const [recentTrades, setRecentTrades] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [period, setPeriod] = useState('week');
  const [lastUpdate, setLastUpdate] = useState(null);

  useEffect(() => {
    fetchMetrics();
  }, [period]);

  const fetchMetrics = async () => {
    try {
      setLoading(true);
      setError(null);

      const response = await fetch(`/api/performance/metrics?period=${period}`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const data = await response.json();
      setMetrics(data);
      setLastUpdate(new Date());

      // Fetch recent trades
      const tradesResponse = await fetch('/api/performance/trades?limit=10');
      if (tradesResponse.ok) {
        const tradesData = await tradesResponse.json();
        setRecentTrades(tradesData.trades || []);
      }
    } catch (err) {
      console.error('Error fetching metrics:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const getMetricStatus = (value, metric) => {
    if (metric === 'sharpe_ratio') return value > 1.0 ? 'good' : value > 0.5 ? 'warning' : 'bad';
    if (metric === 'max_drawdown') return value < 0.20 ? 'good' : value < 0.30 ? 'warning' : 'bad';
    if (metric === 'win_rate_pct') return value >= 50 ? 'good' : value >= 40 ? 'warning' : 'bad';
    if (metric === 'profit_factor') return value > 1.5 ? 'good' : value > 1.2 ? 'warning' : 'bad';
    if (metric === 'calmar_ratio') return value > 1.0 ? 'good' : value > 0.5 ? 'warning' : 'bad';
    return 'neutral';
  };

  if (loading) {
    return (
      <Container maxWidth="lg" sx={{ py: 4 }}>
        <Box display="flex" justifyContent="center" alignItems="center" minHeight="400px">
          <CircularProgress />
        </Box>
      </Container>
    );
  }

  if (error) {
    return (
      <Container maxWidth="lg" sx={{ py: 4 }}>
        <Paper sx={{ p: 3, bgcolor: '#ffebee' }}>
          <Typography color="error">Error loading metrics: {error}</Typography>
          <Button onClick={fetchMetrics} variant="outlined" sx={{ mt: 2 }}>
            Retry
          </Button>
        </Paper>
      </Container>
    );
  }

  if (!metrics) {
    return (
      <Container maxWidth="lg" sx={{ py: 4 }}>
        <Paper sx={{ p: 3 }}>
          <Typography>No trades yet. Check back after the algo runs.</Typography>
        </Paper>
      </Container>
    );
  }

  const m = metrics; // shorthand

  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      {/* Header */}
      <Box sx={{ mb: 4 }}>
        <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
          <Box display="flex" alignItems="center" gap={2}>
            <EqualizerIcon sx={{ fontSize: 32, color: 'primary.main' }} />
            <Typography variant="h4" fontWeight={700}>
              Performance Metrics
            </Typography>
          </Box>
          <ToggleButtonGroup
            value={period}
            exclusive
            onChange={(e, newPeriod) => setPeriod(newPeriod)}
            size="small"
          >
            <ToggleButton value="day">1D</ToggleButton>
            <ToggleButton value="week">1W</ToggleButton>
            <ToggleButton value="month">1M</ToggleButton>
            <ToggleButton value="all">All</ToggleButton>
          </ToggleButtonGroup>
        </Box>
        {lastUpdate && (
          <Typography variant="caption" color="textSecondary">
            Updated: {lastUpdate.toLocaleTimeString()} on {lastUpdate.toLocaleDateString()}
          </Typography>
        )}
      </Box>

      {/* Key Risk Metrics */}
      <Grid container spacing={2} sx={{ mb: 4 }}>
        <Grid item xs={12} sm={6} md={3}>
          <MetricCard>
            <MetricLabel>Sharpe Ratio</MetricLabel>
            <MetricValue sx={{ color: 'primary.main' }}>
              {m.risk_metrics.sharpe_ratio.toFixed(2)}
            </MetricValue>
            <StatusBadge status={getMetricStatus(m.risk_metrics.sharpe_ratio, 'sharpe_ratio')}>
              {m.risk_metrics.sharpe_ratio > 1.0 ? 'Good' : m.risk_metrics.sharpe_ratio > 0.5 ? 'Fair' : 'Weak'}
            </StatusBadge>
            <Typography variant="caption" sx={{ mt: 1, color: 'textSecondary' }}>
              Risk-adjusted return. Target: &gt;1.0
            </Typography>
          </MetricCard>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <MetricCard>
            <MetricLabel>Max Drawdown</MetricLabel>
            <MetricValue sx={{ color: 'error.main' }}>
              {(parseFloat(m.risk_metrics.max_drawdown) * 100).toFixed(1)}%
            </MetricValue>
            <StatusBadge status={getMetricStatus(parseFloat(m.risk_metrics.max_drawdown), 'max_drawdown')}>
              {parseFloat(m.risk_metrics.max_drawdown) < 0.20 ? 'Good' : 'Watch'}
            </StatusBadge>
            <Typography variant="caption" sx={{ mt: 1, color: 'textSecondary' }}>
              Peak-to-trough loss. Target: &lt;20%
            </Typography>
          </MetricCard>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <MetricCard>
            <MetricLabel>Calmar Ratio</MetricLabel>
            <MetricValue sx={{ color: 'success.main' }}>
              {m.risk_metrics.calmar_ratio.toFixed(2)}
            </MetricValue>
            <StatusBadge status={getMetricStatus(m.risk_metrics.calmar_ratio, 'calmar_ratio')}>
              {m.risk_metrics.calmar_ratio > 1.0 ? 'Good' : 'Improve'}
            </StatusBadge>
            <Typography variant="caption" sx={{ mt: 1, color: 'textSecondary' }}>
              Return per unit of drawdown. Target: &gt;1.0
            </Typography>
          </MetricCard>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <MetricCard>
            <MetricLabel>Total P&L</MetricLabel>
            <MetricValue sx={{ color: m.profitability.total_pnl >= 0 ? 'success.main' : 'error.main' }}>
              ${m.profitability.total_pnl.toLocaleString('en-US', { maximumFractionDigits: 0 })}
            </MetricValue>
            <Typography variant="caption" sx={{ mt: 1, color: 'textSecondary' }}>
              Cumulative profit/loss
            </Typography>
          </MetricCard>
        </Grid>
      </Grid>

      {/* Trade Statistics */}
      <Grid container spacing={2} sx={{ mb: 4 }}>
        <Grid item xs={12} sm={6} md={3}>
          <MetricCard>
            <MetricLabel>Total Trades</MetricLabel>
            <MetricValue>{m.summary.total_trades}</MetricValue>
            <Typography variant="caption" sx={{ mt: 1, color: 'textSecondary' }}>
              W: {m.summary.win_count} | L: {m.summary.loss_count} | T: {m.summary.breakeven_count}
            </Typography>
          </MetricCard>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <MetricCard>
            <MetricLabel>Win Rate</MetricLabel>
            <MetricValue sx={{ color: m.summary.win_rate_pct >= 50 ? 'success.main' : 'warning.main' }}>
              {m.summary.win_rate_pct.toFixed(1)}%
            </MetricValue>
            <StatusBadge status={getMetricStatus(m.summary.win_rate_pct, 'win_rate_pct')}>
              {m.summary.win_rate_pct >= 50 ? 'Good' : 'Fair'}
            </StatusBadge>
          </MetricCard>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <MetricCard>
            <MetricLabel>Profit Factor</MetricLabel>
            <MetricValue sx={{ color: m.profitability.profit_factor > 1.5 ? 'success.main' : 'warning.main' }}>
              {m.profitability.profit_factor.toFixed(2)}x
            </MetricValue>
            <StatusBadge status={getMetricStatus(m.profitability.profit_factor, 'profit_factor')}>
              {m.profitability.profit_factor > 1.5 ? 'Good' : 'Fair'}
            </StatusBadge>
          </MetricCard>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <MetricCard>
            <MetricLabel>Avg Expectancy</MetricLabel>
            <MetricValue sx={{ color: m.trade_quality.avg_r_multiple >= 1.0 ? 'success.main' : 'warning.main' }}>
              {m.trade_quality.avg_r_multiple.toFixed(2)}R
            </MetricValue>
            <Typography variant="caption" sx={{ mt: 1, color: 'textSecondary' }}>
              Average risk/reward ratio
            </Typography>
          </MetricCard>
        </Grid>
      </Grid>

      {/* Win/Loss Analysis */}
      <Grid container spacing={2} sx={{ mb: 4 }}>
        <Grid item xs={12} sm={6}>
          <MetricCard>
            <MetricLabel>Winners</MetricLabel>
            <Box sx={{ mt: 2 }}>
              <Typography variant="body2">
                <strong>Gross Profit:</strong> ${m.profitability.gross_profit.toLocaleString('en-US', { maximumFractionDigits: 0 })}
              </Typography>
              <Typography variant="body2" sx={{ mt: 1 }}>
                <strong>Avg Win:</strong> ${m.trade_quality.avg_win.toFixed(0)} ({m.trade_quality.avg_win_pct.toFixed(2)}%)
              </Typography>
              <Typography variant="body2" sx={{ mt: 1 }}>
                <strong>Best Trade:</strong> {m.trade_quality.best_trade_r.toFixed(2)}R
              </Typography>
            </Box>
          </MetricCard>
        </Grid>

        <Grid item xs={12} sm={6}>
          <MetricCard>
            <MetricLabel>Losers</MetricLabel>
            <Box sx={{ mt: 2 }}>
              <Typography variant="body2">
                <strong>Gross Loss:</strong> ${m.profitability.gross_loss.toLocaleString('en-US', { maximumFractionDigits: 0 })}
              </Typography>
              <Typography variant="body2" sx={{ mt: 1 }}>
                <strong>Avg Loss:</strong> ${m.trade_quality.avg_loss.toFixed(0)} ({m.trade_quality.avg_loss_pct.toFixed(2)}%)
              </Typography>
              <Typography variant="body2" sx={{ mt: 1 }}>
                <strong>Worst Trade:</strong> {m.trade_quality.worst_trade_r.toFixed(2)}R
              </Typography>
            </Box>
          </MetricCard>
        </Grid>
      </Grid>

      {/* Recent Trades Table */}
      {recentTrades.length > 0 && (
        <Paper sx={{ borderRadius: 2, overflow: 'hidden' }}>
          <Box sx={{ p: 2, bgcolor: 'grey.50', borderBottom: '1px solid rgba(0,0,0,0.05)' }}>
            <Typography variant="h6">Recent Closed Trades</Typography>
          </Box>
          <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow sx={{ bgcolor: 'grey.100' }}>
                  <TableCell><strong>Date</strong></TableCell>
                  <TableCell align="center"><strong>Symbol</strong></TableCell>
                  <TableCell align="right"><strong>Entry</strong></TableCell>
                  <TableCell align="right"><strong>Exit</strong></TableCell>
                  <TableCell align="right"><strong>P&L</strong></TableCell>
                  <TableCell align="center"><strong>%</strong></TableCell>
                  <TableCell align="center"><strong>Days</strong></TableCell>
                  <TableCell align="right"><strong>R-Mult</strong></TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {recentTrades.map((trade) => (
                  <TableRow key={trade.trade_id} sx={{ '&:hover': { bgcolor: 'grey.50' } }}>
                    <TableCell fontSize="0.9rem">{trade.exit_date}</TableCell>
                    <TableCell align="center" sx={{ fontWeight: 600 }}>{trade.symbol}</TableCell>
                    <TableCell align="right">${trade.entry_price.toFixed(2)}</TableCell>
                    <TableCell align="right">${trade.exit_price.toFixed(2)}</TableCell>
                    <TableCell
                      align="right"
                      sx={{
                        color: trade.pnl_dollars >= 0 ? 'success.main' : 'error.main',
                        fontWeight: 600,
                      }}
                    >
                      ${trade.pnl_dollars.toFixed(0)}
                    </TableCell>
                    <TableCell align="center" sx={{ color: trade.pnl_pct >= 0 ? 'success.main' : 'error.main' }}>
                      {trade.pnl_pct.toFixed(2)}%
                    </TableCell>
                    <TableCell align="center">{trade.duration_days}</TableCell>
                    <TableCell align="right">{trade.r_multiple.toFixed(2)}R</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </Paper>
      )}

      {/* Refresh Button */}
      <Box sx={{ mt: 4, display: 'flex', justifyContent: 'center' }}>
        <Button variant="outlined" onClick={fetchMetrics}>
          Refresh Metrics
        </Button>
      </Box>
    </Container>
  );
}
