/**
 * Swing Trading Algo Dashboard
 *
 * Real-time monitoring of:
 * - Algorithm status and configuration
 * - Live signal evaluation
 * - Active positions and P&L
 * - Trade history and statistics
 * - Market health and risk metrics
 */

import React, { useState, useEffect } from 'react';
import {
  Box,
  Card,
  CardContent,
  CardHeader,
  Grid,
  Typography,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Chip,
  LinearProgress,
  Alert,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  Tabs,
  Tab,
  Paper,
} from '@mui/material';
import {
  TrendingUp,
  TrendingDown,
  Warning,
  CheckCircle,
  Error as ErrorIcon,
} from '@mui/icons-material';
import { api } from '../services/api';

function AlgoTradingDashboard() {
  const [algoStatus, setAlgoStatus] = useState(null);
  const [evaluatedSignals, setEvaluatedSignals] = useState(null);
  const [positions, setPositions] = useState([]);
  const [trades, setTrades] = useState([]);
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedTab, setSelectedTab] = useState(0);
  const [autoRefresh, setAutoRefresh] = useState(true);

  // Fetch all algo data
  const fetchAlgoData = async () => {
    try {
      setLoading(true);
      setError(null);

      const [statusRes, signalsRes, positionsRes, tradesRes, configRes] = await Promise.all([
        api.get('/algo/status'),
        api.get('/algo/evaluate'),
        api.get('/algo/positions'),
        api.get('/algo/trades?limit=50'),
        api.get('/algo/config'),
      ]);

      if (statusRes.data?.success) setAlgoStatus(statusRes.data.data);
      if (signalsRes.data?.success) setEvaluatedSignals(signalsRes.data.data);
      if (positionsRes.data?.success) setPositions(positionsRes.data.items || []);
      if (tradesRes.data?.success) setTrades(tradesRes.data.items || []);
      if (configRes.data?.success) setConfig(configRes.data.data);

      setLoading(false);
    } catch (err) {
      setError(err.message || 'Failed to fetch algo data');
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAlgoData();

    if (autoRefresh) {
      const interval = setInterval(fetchAlgoData, 30000); // Refresh every 30 seconds
      return () => clearInterval(interval);
    }
  }, [autoRefresh]);

  if (loading) {
    return (
      <Box sx={{ p: 2 }}>
        <LinearProgress />
      </Box>
    );
  }

  const portfolio = algoStatus?.portfolio || {};
  const market = algoStatus?.market || {};

  return (
    <Box sx={{ p: 2 }}>
      <Box sx={{ mb: 3, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Typography variant="h4">Swing Trading Algo Dashboard</Typography>
        <Box sx={{ display: 'flex', gap: 1 }}>
          <Button
            variant="contained"
            size="small"
            onClick={fetchAlgoData}
          >
            Refresh
          </Button>
          <Button
            variant={autoRefresh ? 'contained' : 'outlined'}
            size="small"
            onClick={() => setAutoRefresh(!autoRefresh)}
          >
            {autoRefresh ? 'Auto' : 'Manual'}
          </Button>
        </Box>
      </Box>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {/* Status Overview */}
      <Grid container spacing={2} sx={{ mb: 3 }}>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <Box>
                  <Typography color="textSecondary" gutterBottom>
                    Status
                  </Typography>
                  <Typography variant="h6">
                    {algoStatus?.status || 'Unknown'}
                  </Typography>
                </Box>
                <CheckCircle sx={{ fontSize: 40, color: 'green' }} />
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <Box>
                  <Typography color="textSecondary" gutterBottom>
                    Portfolio Value
                  </Typography>
                  <Typography variant="h6">
                    ${portfolio.total_value?.toLocaleString() || '0'}
                  </Typography>
                </Box>
                <TrendingUp sx={{ fontSize: 40, color: 'blue' }} />
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <Box>
                  <Typography color="textSecondary" gutterBottom>
                    Active Positions
                  </Typography>
                  <Typography variant="h6">
                    {portfolio.position_count || 0}
                  </Typography>
                </Box>
                <Typography variant="h5" sx={{ color: 'purple' }}>
                  {positions.length}
                </Typography>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <Box>
                  <Typography color="textSecondary" gutterBottom>
                    Unrealized P&L
                  </Typography>
                  <Typography
                    variant="h6"
                    sx={{ color: portfolio.unrealized_pnl_pct >= 0 ? 'green' : 'red' }}
                  >
                    {portfolio.unrealized_pnl_pct?.toFixed(2)}%
                  </Typography>
                </Box>
                {portfolio.unrealized_pnl_pct >= 0 ? (
                  <TrendingUp sx={{ fontSize: 40, color: 'green' }} />
                ) : (
                  <TrendingDown sx={{ fontSize: 40, color: 'red' }} />
                )}
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Market Health */}
      <Grid container spacing={2} sx={{ mb: 3 }}>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="textSecondary" gutterBottom>
                Market Trend
              </Typography>
              <Chip
                label={market.trend || 'Unknown'}
                color={market.trend === 'uptrend' ? 'success' : 'warning'}
              />
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="textSecondary" gutterBottom>
                Market Stage
              </Typography>
              <Chip label={`Stage ${market.stage || 1}`} variant="outlined" />
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="textSecondary" gutterBottom>
                Distribution Days
              </Typography>
              <Typography variant="h6">{market.distribution_days || 0}</Typography>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="textSecondary" gutterBottom>
                VIX Level
              </Typography>
              <Typography variant="h6">{market.vix || '0.00'}</Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Tabbed Content */}
      <Paper>
        <Tabs value={selectedTab} onChange={(e, newTab) => setSelectedTab(newTab)}>
          <Tab label="Evaluated Signals" />
          <Tab label="Active Positions" />
          <Tab label="Trade History" />
          <Tab label="Configuration" />
        </Tabs>

        {/* Tab 1: Signals */}
        {selectedTab === 0 && (
          <Box sx={{ p: 2 }}>
            <Typography variant="subtitle1" gutterBottom>
              {evaluatedSignals?.total_buy_signals || 0} signals evaluated,{' '}
              {evaluatedSignals?.qualified_for_trading || 0} qualified for trading
            </Typography>

            {evaluatedSignals?.top_qualified?.length > 0 ? (
              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow sx={{ backgroundColor: '#f5f5f5' }}>
                      <TableCell>Symbol</TableCell>
                      <TableCell align="right">Entry Price</TableCell>
                      <TableCell align="center">Trend Score</TableCell>
                      <TableCell align="center">SQS</TableCell>
                      <TableCell align="center">Completeness</TableCell>
                      <TableCell align="center">Status</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {evaluatedSignals.top_qualified.map((signal) => (
                      <TableRow key={signal.symbol}>
                        <TableCell sx={{ fontWeight: 'bold' }}>{signal.symbol}</TableCell>
                        <TableCell align="right">${signal.entry_price?.toFixed(2)}</TableCell>
                        <TableCell align="center">{signal.trend_score}/10</TableCell>
                        <TableCell align="center">{signal.sqs}</TableCell>
                        <TableCell align="center">{signal.completeness_pct?.toFixed(0)}%</TableCell>
                        <TableCell align="center">
                          <Chip
                            label="Ready"
                            size="small"
                            color={signal.all_tiers_pass ? 'success' : 'warning'}
                          />
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            ) : (
              <Alert severity="info">No qualified signals at this time</Alert>
            )}
          </Box>
        )}

        {/* Tab 2: Positions */}
        {selectedTab === 1 && (
          <Box sx={{ p: 2 }}>
            {positions.length > 0 ? (
              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow sx={{ backgroundColor: '#f5f5f5' }}>
                      <TableCell>Symbol</TableCell>
                      <TableCell align="right">Qty</TableCell>
                      <TableCell align="right">Entry</TableCell>
                      <TableCell align="right">Current</TableCell>
                      <TableCell align="right">Position Value</TableCell>
                      <TableCell align="right">Unrealized P&L</TableCell>
                      <TableCell align="center">%</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {positions.map((pos) => (
                      <TableRow key={pos.position_id}>
                        <TableCell sx={{ fontWeight: 'bold' }}>{pos.symbol}</TableCell>
                        <TableCell align="right">{pos.quantity}</TableCell>
                        <TableCell align="right">${pos.avg_entry_price?.toFixed(2)}</TableCell>
                        <TableCell align="right">${pos.current_price?.toFixed(2)}</TableCell>
                        <TableCell align="right">${pos.position_value?.toLocaleString()}</TableCell>
                        <TableCell
                          align="right"
                          sx={{
                            color: pos.unrealized_pnl >= 0 ? 'green' : 'red',
                            fontWeight: 'bold',
                          }}
                        >
                          ${pos.unrealized_pnl?.toFixed(2)}
                        </TableCell>
                        <TableCell
                          align="center"
                          sx={{
                            color: pos.unrealized_pnl_pct >= 0 ? 'green' : 'red',
                          }}
                        >
                          {pos.unrealized_pnl_pct?.toFixed(2)}%
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            ) : (
              <Alert severity="info">No active positions</Alert>
            )}
          </Box>
        )}

        {/* Tab 3: Trade History */}
        {selectedTab === 2 && (
          <Box sx={{ p: 2 }}>
            {trades.length > 0 ? (
              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow sx={{ backgroundColor: '#f5f5f5' }}>
                      <TableCell>Symbol</TableCell>
                      <TableCell>Entry Date</TableCell>
                      <TableCell align="right">Entry Price</TableCell>
                      <TableCell align="right">Exit Price</TableCell>
                      <TableCell align="right">P&L %</TableCell>
                      <TableCell align="center">Days</TableCell>
                      <TableCell>Status</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {trades.map((trade) => (
                      <TableRow key={trade.trade_id}>
                        <TableCell sx={{ fontWeight: 'bold' }}>{trade.symbol}</TableCell>
                        <TableCell>{trade.trade_date}</TableCell>
                        <TableCell align="right">${trade.entry_price?.toFixed(2)}</TableCell>
                        <TableCell align="right">
                          {trade.exit_price ? `$${trade.exit_price.toFixed(2)}` : '—'}
                        </TableCell>
                        <TableCell
                          align="right"
                          sx={{
                            color: trade.profit_loss_pct >= 0 ? 'green' : 'red',
                            fontWeight: 'bold',
                          }}
                        >
                          {trade.profit_loss_pct?.toFixed(2)}%
                        </TableCell>
                        <TableCell align="center">{trade.trade_duration_days || 0}</TableCell>
                        <TableCell>
                          <Chip
                            label={trade.status}
                            size="small"
                            color={trade.status === 'closed' ? 'default' : 'primary'}
                          />
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            ) : (
              <Alert severity="info">No trade history</Alert>
            )}
          </Box>
        )}

        {/* Tab 4: Configuration */}
        {selectedTab === 3 && (
          <Box sx={{ p: 2 }}>
            {config ? (
              <Grid container spacing={2}>
                {Object.entries(config).slice(0, 12).map(([key, val]) => (
                  <Grid item xs={12} sm={6} md={4} key={key}>
                    <Card variant="outlined">
                      <CardContent>
                        <Typography color="textSecondary" gutterBottom>
                          {key}
                        </Typography>
                        <Typography variant="body2">
                          {String(val.value)}
                        </Typography>
                        <Typography variant="caption" color="textSecondary">
                          {val.description}
                        </Typography>
                      </CardContent>
                    </Card>
                  </Grid>
                ))}
              </Grid>
            ) : (
              <Alert severity="info">Configuration not available</Alert>
            )}
          </Box>
        )}
      </Paper>
    </Box>
  );
}

export default AlgoTradingDashboard;
