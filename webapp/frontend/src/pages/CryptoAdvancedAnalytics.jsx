/**
 * Crypto Advanced Analytics Dashboard
 * Comprehensive cryptocurrency market analysis and insights
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Card,
  CardContent,
  CardHeader,
  Typography,
  Grid,
  Box,
  Button,
  Tab,
  Tabs,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Chip,
  LinearProgress,
  Alert,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  IconButton,
  Tooltip
} from '@mui/material';
import {
  TrendingUp,
  TrendingDown,
  Refresh,
  Assessment,
  Timeline,
  Security,
  Speed,
  Warning
} from '@mui/icons-material';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  ResponsiveContainer,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  ScatterChart,
  Scatter,
  Legend,
  Tooltip as RechartsTooltip
} from 'recharts';

const CryptoAdvancedAnalytics = () => {
  const [analytics, setAnalytics] = useState(null);
  const [signals, setSignals] = useState([]);
  const [riskData, setRiskData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [tabValue, setTabValue] = useState(0);
  const [selectedTimeframe, setSelectedTimeframe] = useState('7d');
  const [selectedCrypto, setSelectedCrypto] = useState('bitcoin');
  const [refreshing, setRefreshing] = useState(false);

  // Popular cryptocurrencies for analysis
  const cryptoOptions = [
    { id: 'bitcoin', name: 'Bitcoin', symbol: 'BTC' },
    { id: 'ethereum', name: 'Ethereum', symbol: 'ETH' },
    { id: 'cardano', name: 'Cardano', symbol: 'ADA' },
    { id: 'solana', name: 'Solana', symbol: 'SOL' },
    { id: 'chainlink', name: 'Chainlink', symbol: 'LINK' },
    { id: 'polkadot', name: 'Polkadot', symbol: 'DOT' },
    { id: 'avalanche-2', name: 'Avalanche', symbol: 'AVAX' },
    { id: 'polygon', name: 'Polygon', symbol: 'MATIC' }
  ];

  // Fetch analytics data
  const fetchAnalytics = useCallback(async () => {
    try {
      setRefreshing(true);
      const response = await fetch(`/api/crypto-analytics/overview?timeframe=${selectedTimeframe}`);
      const data = await response.json();
      
      if (data.success) {
        setAnalytics(data.data);
      } else {
        setError(data.error || 'Failed to fetch analytics');
      }
    } catch (err) {
      console.error('Analytics fetch error:', err);
      setError('Failed to fetch analytics data');
    } finally {
      setRefreshing(false);
    }
  }, [selectedTimeframe]);

  // Fetch trading signals
  const fetchSignals = useCallback(async () => {
    try {
      const response = await fetch(`/api/crypto-signals/analysis?symbols=${selectedCrypto}&timeframe=${selectedTimeframe}`);
      const data = await response.json();
      
      if (data.success) {
        setSignals(data.data.signals || []);
      }
    } catch (err) {
      console.error('Signals fetch error:', err);
    }
  }, [selectedCrypto, selectedTimeframe]);

  // Fetch risk data
  const fetchRiskData = useCallback(async () => {
    try {
      const response = await fetch(`/api/crypto-risk/analysis?symbols=${selectedCrypto}&timeframe=${selectedTimeframe}`);
      const data = await response.json();
      
      if (data.success) {
        setRiskData(data.data);
      }
    } catch (err) {
      console.error('Risk data fetch error:', err);
    }
  }, [selectedCrypto, selectedTimeframe]);

  // Initial data load
  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      await Promise.all([
        fetchAnalytics(),
        fetchSignals(),
        fetchRiskData()
      ]);
      setLoading(false);
    };
    
    loadData();
  }, [fetchAnalytics, fetchSignals, fetchRiskData]);

  // Auto-refresh every 5 minutes
  useEffect(() => {
    const interval = setInterval(() => {
      fetchAnalytics();
      fetchSignals();
      fetchRiskData();
    }, 300000);
    
    return () => clearInterval(interval);
  }, [fetchAnalytics, fetchSignals, fetchRiskData]);

  // Format currency
  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: amount < 1 ? 6 : 2
    }).format(amount);
  };

  // Get trend color
  const getTrendColor = (value) => {
    if (value > 0) return '#4caf50';
    if (value < 0) return '#f44336';
    return '#666';
  };

  // Get signal strength color
  const getSignalColor = (strength) => {
    if (strength >= 0.7) return '#4caf50';
    if (strength >= 0.4) return '#ff9800';
    return '#f44336';
  };

  // Get risk level color
  const getRiskColor = (level) => {
    switch (level) {
      case 'low': return '#4caf50';
      case 'medium': return '#ff9800';
      case 'high': return '#f44336';
      default: return '#666';
    }
  };

  if (loading) {
    return (
      <Box sx={{ p: 3 }}>
        <Typography variant="h4" gutterBottom>
          Advanced Crypto Analytics
        </Typography>
        <LinearProgress />
        <Typography sx={{ mt: 2 }}>Loading analytics data...</Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ p: 3 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Typography variant="h4" gutterBottom>
          Advanced Crypto Analytics
        </Typography>
        <Box sx={{ display: 'flex', gap: 2, alignItems: 'center' }}>
          <FormControl size="small" sx={{ minWidth: 120 }}>
            <InputLabel>Timeframe</InputLabel>
            <Select
              value={selectedTimeframe}
              onChange={(e) => setSelectedTimeframe(e.target.value)}
              label="Timeframe"
            >
              <MenuItem value="1d">1 Day</MenuItem>
              <MenuItem value="7d">7 Days</MenuItem>
              <MenuItem value="30d">30 Days</MenuItem>
              <MenuItem value="90d">90 Days</MenuItem>
            </Select>
          </FormControl>
          <FormControl size="small" sx={{ minWidth: 120 }}>
            <InputLabel>Crypto</InputLabel>
            <Select
              value={selectedCrypto}
              onChange={(e) => setSelectedCrypto(e.target.value)}
              label="Crypto"
            >
              {cryptoOptions.map((crypto) => (
                <MenuItem key={crypto.id} value={crypto.id}>
                  {crypto.symbol}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <IconButton onClick={() => {
            fetchAnalytics();
            fetchSignals();
            fetchRiskData();
          }} disabled={refreshing}>
            <Refresh />
          </IconButton>
        </Box>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {/* Summary Cards */}
      <Grid container spacing={3} sx={{ mb: 3 }}>
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center' }}>
                <Assessment sx={{ color: '#1976d2', mr: 2 }} />
                <Box>
                  <Typography color="textSecondary" variant="body2">
                    Market Sentiment
                  </Typography>
                  <Typography variant="h6">
                    {analytics?.market_sentiment?.score || 'N/A'}
                  </Typography>
                  <Typography variant="body2" color="textSecondary">
                    {analytics?.market_sentiment?.label || 'Neutral'}
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center' }}>
                <Timeline sx={{ color: '#4caf50', mr: 2 }} />
                <Box>
                  <Typography color="textSecondary" variant="body2">
                    Active Signals
                  </Typography>
                  <Typography variant="h6">
                    {signals.length || 0}
                  </Typography>
                  <Typography variant="body2" color="textSecondary">
                    Strong: {signals.filter(s => s.strength >= 0.7).length}
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center' }}>
                <Security sx={{ color: getRiskColor(riskData?.risk_level), mr: 2 }} />
                <Box>
                  <Typography color="textSecondary" variant="body2">
                    Risk Level
                  </Typography>
                  <Typography variant="h6" sx={{ textTransform: 'capitalize' }}>
                    {riskData?.risk_level || 'Unknown'}
                  </Typography>
                  <Typography variant="body2" color="textSecondary">
                    VaR: {riskData?.value_at_risk ? `${riskData.value_at_risk.toFixed(2)}%` : 'N/A'}
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center' }}>
                <Speed sx={{ color: '#ff9800', mr: 2 }} />
                <Box>
                  <Typography color="textSecondary" variant="body2">
                    Volatility
                  </Typography>
                  <Typography variant="h6">
                    {analytics?.volatility ? `${(analytics.volatility * 100).toFixed(1)}%` : 'N/A'}
                  </Typography>
                  <Typography variant="body2" color="textSecondary">
                    {analytics?.volatility_trend || 'Stable'}
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Tabs */}
      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
        <Tabs value={tabValue} onChange={(e, newValue) => setTabValue(newValue)}>
          <Tab label="Technical Analysis" />
          <Tab label="Risk Metrics" />
          <Tab label="Market Correlation" />
          <Tab label="Performance Analytics" />
        </Tabs>
      </Box>

      {/* Tab Content */}
      {tabValue === 0 && (
        <Grid container spacing={3}>
          {/* Price Chart with Technical Indicators */}
          <Grid item xs={12} lg={8}>
            <Card>
              <CardHeader title={`${cryptoOptions.find(c => c.id === selectedCrypto)?.name || 'Crypto'} Technical Analysis`} />
              <CardContent>
                {analytics?.price_data ? (
                  <ResponsiveContainer width="100%" height={400}>
                    <LineChart data={analytics.price_data}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="date" />
                      <YAxis />
                      <RechartsTooltip />
                      <Legend />
                      <Line type="monotone" dataKey="price" stroke="#8884d8" name="Price" />
                      <Line type="monotone" dataKey="sma_20" stroke="#82ca9d" name="SMA 20" />
                      <Line type="monotone" dataKey="ema_12" stroke="#ffc658" name="EMA 12" />
                    </LineChart>
                  </ResponsiveContainer>
                ) : (
                  <Typography color="textSecondary" sx={{ textAlign: 'center', py: 4 }}>
                    No price data available
                  </Typography>
                )}
              </CardContent>
            </Card>
          </Grid>

          {/* Trading Signals */}
          <Grid item xs={12} lg={4}>
            <Card>
              <CardHeader title="Active Signals" />
              <CardContent>
                {signals.length > 0 ? (
                  <TableContainer>
                    <Table size="small">
                      <TableHead>
                        <TableRow>
                          <TableCell>Signal</TableCell>
                          <TableCell>Strength</TableCell>
                          <TableCell>Action</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {signals.slice(0, 8).map((signal, index) => (
                          <TableRow key={index}>
                            <TableCell>
                              <Typography variant="body2">
                                {signal.indicator}
                              </Typography>
                            </TableCell>
                            <TableCell>
                              <Box sx={{ display: 'flex', alignItems: 'center' }}>
                                <LinearProgress
                                  variant="determinate"
                                  value={signal.strength * 100}
                                  sx={{
                                    width: 40,
                                    mr: 1,
                                    '& .MuiLinearProgress-bar': {
                                      backgroundColor: getSignalColor(signal.strength)
                                    }
                                  }}
                                />
                                <Typography variant="caption">
                                  {(signal.strength * 100).toFixed(0)}%
                                </Typography>
                              </Box>
                            </TableCell>
                            <TableCell>
                              <Chip
                                label={signal.action}
                                size="small"
                                color={signal.action === 'BUY' ? 'success' : signal.action === 'SELL' ? 'error' : 'default'}
                              />
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </TableContainer>
                ) : (
                  <Typography color="textSecondary" sx={{ textAlign: 'center', py: 4 }}>
                    No active signals
                  </Typography>
                )}
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      )}

      {tabValue === 1 && riskData && (
        <Grid container spacing={3}>
          {/* Risk Metrics */}
          <Grid item xs={12} md={6}>
            <Card>
              <CardHeader title="Risk Metrics" />
              <CardContent>
                <Grid container spacing={2}>
                  <Grid item xs={6}>
                    <Typography variant="body2" color="textSecondary">
                      Value at Risk (95%)
                    </Typography>
                    <Typography variant="h6" sx={{ color: getRiskColor('high') }}>
                      {riskData.value_at_risk ? `${riskData.value_at_risk.toFixed(2)}%` : 'N/A'}
                    </Typography>
                  </Grid>
                  <Grid item xs={6}>
                    <Typography variant="body2" color="textSecondary">
                      Expected Shortfall
                    </Typography>
                    <Typography variant="h6" sx={{ color: getRiskColor('high') }}>
                      {riskData.expected_shortfall ? `${riskData.expected_shortfall.toFixed(2)}%` : 'N/A'}
                    </Typography>
                  </Grid>
                  <Grid item xs={6}>
                    <Typography variant="body2" color="textSecondary">
                      Maximum Drawdown
                    </Typography>
                    <Typography variant="h6" sx={{ color: getRiskColor('medium') }}>
                      {riskData.max_drawdown ? `${riskData.max_drawdown.toFixed(2)}%` : 'N/A'}
                    </Typography>
                  </Grid>
                  <Grid item xs={6}>
                    <Typography variant="body2" color="textSecondary">
                      Sharpe Ratio
                    </Typography>
                    <Typography variant="h6" sx={{ color: getTrendColor(riskData.sharpe_ratio || 0) }}>
                      {riskData.sharpe_ratio ? riskData.sharpe_ratio.toFixed(2) : 'N/A'}
                    </Typography>
                  </Grid>
                </Grid>
              </CardContent>
            </Card>
          </Grid>

          {/* Risk Distribution Chart */}
          <Grid item xs={12} md={6}>
            <Card>
              <CardHeader title="Risk Distribution" />
              <CardContent>
                {riskData.risk_distribution ? (
                  <ResponsiveContainer width="100%" height={300}>
                    <BarChart data={riskData.risk_distribution}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="range" />
                      <YAxis />
                      <RechartsTooltip />
                      <Bar dataKey="frequency" fill="#8884d8" />
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <Typography color="textSecondary" sx={{ textAlign: 'center', py: 4 }}>
                    No risk distribution data available
                  </Typography>
                )}
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      )}

      {tabValue === 2 && (
        <Grid container spacing={3}>
          {/* Correlation Matrix */}
          <Grid item xs={12}>
            <Card>
              <CardHeader title="Market Correlation Analysis" />
              <CardContent>
                {analytics?.correlation_data ? (
                  <ResponsiveContainer width="100%" height={400}>
                    <ScatterChart data={analytics.correlation_data}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="crypto1_return" name="Asset 1 Return" />
                      <YAxis dataKey="crypto2_return" name="Asset 2 Return" />
                      <RechartsTooltip cursor={{ strokeDasharray: '3 3' }} />
                      <Scatter name="Correlation" data={analytics.correlation_data} fill="#8884d8" />
                    </ScatterChart>
                  </ResponsiveContainer>
                ) : (
                  <Typography color="textSecondary" sx={{ textAlign: 'center', py: 4 }}>
                    No correlation data available
                  </Typography>
                )}
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      )}

      {tabValue === 3 && (
        <Grid container spacing={3}>
          {/* Performance Metrics */}
          <Grid item xs={12} md={8}>
            <Card>
              <CardHeader title="Performance Analytics" />
              <CardContent>
                {analytics?.performance_data ? (
                  <ResponsiveContainer width="100%" height={400}>
                    <LineChart data={analytics.performance_data}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="date" />
                      <YAxis />
                      <RechartsTooltip />
                      <Legend />
                      <Line type="monotone" dataKey="cumulative_return" stroke="#8884d8" name="Cumulative Return" />
                      <Line type="monotone" dataKey="benchmark" stroke="#82ca9d" name="Benchmark" />
                    </LineChart>
                  </ResponsiveContainer>
                ) : (
                  <Typography color="textSecondary" sx={{ textAlign: 'center', py: 4 }}>
                    No performance data available
                  </Typography>
                )}
              </CardContent>
            </Card>
          </Grid>

          {/* Performance Summary */}
          <Grid item xs={12} md={4}>
            <Card>
              <CardHeader title="Performance Summary" />
              <CardContent>
                <Box sx={{ mb: 2 }}>
                  <Typography variant="body2" color="textSecondary">
                    Total Return
                  </Typography>
                  <Typography variant="h6" sx={{ color: getTrendColor(analytics?.total_return || 0) }}>
                    {analytics?.total_return ? `${(analytics.total_return * 100).toFixed(2)}%` : 'N/A'}
                  </Typography>
                </Box>
                <Box sx={{ mb: 2 }}>
                  <Typography variant="body2" color="textSecondary">
                    Annualized Return
                  </Typography>
                  <Typography variant="h6" sx={{ color: getTrendColor(analytics?.annualized_return || 0) }}>
                    {analytics?.annualized_return ? `${(analytics.annualized_return * 100).toFixed(2)}%` : 'N/A'}
                  </Typography>
                </Box>
                <Box sx={{ mb: 2 }}>
                  <Typography variant="body2" color="textSecondary">
                    Win Rate
                  </Typography>
                  <Typography variant="h6">
                    {analytics?.win_rate ? `${(analytics.win_rate * 100).toFixed(1)}%` : 'N/A'}
                  </Typography>
                </Box>
                <Box>
                  <Typography variant="body2" color="textSecondary">
                    Beta (vs BTC)
                  </Typography>
                  <Typography variant="h6">
                    {analytics?.beta ? analytics.beta.toFixed(2) : 'N/A'}
                  </Typography>
                </Box>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      )}
    </Box>
  );
};

export default CryptoAdvancedAnalytics;