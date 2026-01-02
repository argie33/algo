/**
 * Portfolio Optimizer Dashboard
 * Real-time analysis, recommendations, and trade execution
 */

import React, { useState, useEffect } from 'react';
import {
  Box, Container, Paper, Grid, Card, CardContent, Button, Table,
  TableBody, TableCell, TableContainer, TableHead, TableRow, CircularProgress,
  Alert, Dialog, DialogTitle, DialogContent, DialogActions, Chip, Typography,
  LinearProgress, Divider
} from '@mui/material';
import {
  TrendingUp, TrendingDown, Warning, CheckCircle
} from '@mui/icons-material';
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';
import { api as axios } from '../services/api';

export default function PortfolioOptimizerNew() {
  const [loading, setLoading] = useState(false);
  const [analysis, setAnalysis] = useState(null);
  const [error, setError] = useState(null);

  // Color palette for pie chart
  const COLORS = ['#8884d8', '#82ca9d', '#ffc658', '#ff7c7c', '#8dd1e1', '#d084d0', '#a4de6c', '#ffb347'];

  // Fetch optimization analysis
  const fetchAnalysis = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await axios.get('/api/optimization/analysis');
      console.log('[PortfolioOptimizerNew] API Response:', response.data);
      // Extract analysis data from unified response format {success: true, data: {analysis: {...}}}
      // Handle both response.data.analysis and response.data.data.analysis formats
      const analysisData = response.data?.data?.analysis || response.data?.analysis || response.data;
      console.log('[PortfolioOptimizerNew] Analysis Data:', analysisData);
      if (!analysisData) {
        setError('No analysis data returned from server');
        setAnalysis(null);
      } else {
        setAnalysis(analysisData);
      }
    } catch (err) {
      console.error('[PortfolioOptimizerNew] Fetch Error:', err);
      setError(err.response?.data?.error || err.message);
    } finally {
      setLoading(false);
    }
  };


  useEffect(() => {
    fetchAnalysis();
  }, []);

  if (loading && !analysis) {
    return (
      <Container maxWidth="lg" sx={{ py: 4, textAlign: 'center' }}>
        <CircularProgress />
      </Container>
    );
  }

  if (!analysis) {
    return (
      <Container maxWidth="lg" sx={{ py: 4 }}>
        {error ? (
          <Alert severity="error">
            <Typography variant="h6" sx={{ mb: 1 }}>Unable to load optimization data</Typography>
            <Typography variant="body2">{error}</Typography>
            <Button
              variant="outlined"
              onClick={fetchAnalysis}
              sx={{ mt: 2 }}
            >
              Try Again
            </Button>
          </Alert>
        ) : (
          <Alert severity="info">No portfolio data available - please add holdings to get optimization recommendations</Alert>
        )}
      </Container>
    );
  }

  // Extract metrics from the correct structure in the backend response
  const currentMetrics = analysis.portfolioMetrics?.current || {};
  const optimizedMetrics = analysis.portfolioMetrics?.optimized || {};

  // Current portfolio metrics
  const metrics = {
    beta: currentMetrics.beta,
    sharpeRatio: currentMetrics.sharpeRatio,
    volatility: currentMetrics.volatility,
    concentration: analysis.concentration || '—',
    avgQuality: analysis.avgQuality !== null && analysis.avgQuality !== undefined ? analysis.avgQuality : null,
  };

  // Expected improvements comparing current to optimized
  const improvements = {
    beta: {
      expected: optimizedMetrics.beta,
      improved: optimizedMetrics.beta !== undefined && currentMetrics.beta !== undefined && optimizedMetrics.beta < currentMetrics.beta,
    },
    sharpeRatio: {
      expected: optimizedMetrics.sharpeRatio,
      improved: optimizedMetrics.sharpeRatio !== undefined && currentMetrics.sharpeRatio !== undefined && optimizedMetrics.sharpeRatio > currentMetrics.sharpeRatio,
    },
    volatility: {
      expected: optimizedMetrics.volatility,
      improved: optimizedMetrics.volatility !== undefined && currentMetrics.volatility !== undefined && optimizedMetrics.volatility < currentMetrics.volatility,
    },
    concentration: {
      expected: analysis.targetConcentration || '—',
      improved: false,
    },
    quality: {
      expected: analysis.expectedQuality !== null && analysis.expectedQuality !== undefined ? analysis.expectedQuality : null,
      improved: false,
    },
  };

  const issues = analysis.issues || [];
  const recommendations = analysis.recommendations || [];

  // Map recommendations to portfolio stocks for display (single source of truth) - NO fake defaults
  const portfolio = {
    stocks: recommendations.map((rec, idx) => {
      return {
        symbol: rec.symbol,
        weight: rec.targetWeight ? parseFloat(rec.targetWeight.replace('%', '')) : null,
        action: rec.action,
        priority: rec.priority,
        reason: rec.reason,
      };
    }),
    total_value: analysis.portfolioValue !== null && analysis.portfolioValue !== undefined ? analysis.portfolioValue :
                 analysis.totalValue !== null && analysis.totalValue !== undefined ? analysis.totalValue : null,
  };

  // Handle null improvements (when optimized metrics unavailable due to data integrity)
  const metricsData = improvements ? [
    { name: 'Beta', current: metrics?.beta, expected: improvements.beta?.expected },
    { name: 'Sharpe', current: metrics?.sharpeRatio, expected: improvements.sharpeRatio?.expected },
    { name: 'Concentration %', current: metrics?.concentration ? parseFloat(metrics.concentration.replace('%', '')) : 0, expected: improvements.concentration?.expected ? parseFloat(improvements.concentration.expected.replace('%', '')) : 0 },
  ] : [];

  const issueColors = { high: '#d32f2f', medium: '#f57c00', low: '#388e3c' };

  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      <Box sx={{ mb: 3, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Typography variant="h4">Portfolio Optimizer</Typography>
        <Box sx={{ display: 'flex', gap: 1 }}>
          <Button variant="contained" onClick={fetchAnalysis} disabled={loading}>
            {loading ? <CircularProgress size={24} /> : 'Refresh Analysis'}
          </Button>
        </Box>
      </Box>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {/* ANALYSIS SECTION */}
      {(
        <>
          {/* Key Metrics */}
          <Grid container spacing={2} sx={{ mb: 3 }}>
            <Grid item xs={12} sm={6} md={3}>
              <Card>
                <CardContent>
                  <Typography color="textSecondary" gutterBottom>Beta</Typography>
                  <Typography variant="h5">{metrics?.beta || "—"}</Typography>
                  <Typography variant="body2" color={improvements?.beta?.improved ? 'success.main' : 'error.main'}>
                    {improvements?.beta?.improved ? '📉' : '📈'} {(typeof improvements?.beta?.expected === 'number' && !isNaN(improvements.beta.expected)) ? improvements.beta.expected.toFixed(2) : "—"}
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Card>
                <CardContent>
                  <Typography color="textSecondary" gutterBottom>Sharpe Ratio</Typography>
                  <Typography variant="h5">{(typeof metrics?.sharpeRatio === 'number' && !isNaN(metrics.sharpeRatio)) ? metrics.sharpeRatio.toFixed(2) : "—"}</Typography>
                  <Typography variant="body2" color={improvements?.sharpeRatio?.improved ? 'success.main' : 'error.main'}>
                    {improvements?.sharpeRatio?.improved ? '✓' : '✗'} {(typeof improvements?.sharpeRatio?.expected === 'number' && !isNaN(improvements?.sharpeRatio?.expected)) ? improvements.sharpeRatio.expected.toFixed(2) : "—"}
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Card>
                <CardContent>
                  <Typography color="textSecondary" gutterBottom>Concentration</Typography>
                  <Typography variant="h5">{metrics?.concentration || "—"}</Typography>
                  <Typography variant="body2" color={improvements?.concentration?.improved ? 'success.main' : 'error.main'}>
                    {improvements?.concentration?.improved ? '✓' : '✗'} {improvements?.concentration?.expected || "—"}
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Card>
                <CardContent>
                  <Typography color="textSecondary" gutterBottom>Quality</Typography>
                  <Typography variant="h5">{(typeof metrics.avgQuality === 'number' && !isNaN(metrics.avgQuality)) ? metrics.avgQuality.toFixed(1) : "—"}</Typography>
                  <Typography variant="body2" color={improvements?.quality?.improved ? 'success.main' : 'error.main'}>
                    {improvements?.quality?.improved ? '✓' : '✗'} {(typeof improvements?.quality?.expected === 'number' && !isNaN(improvements?.quality?.expected)) ? improvements.quality.expected.toFixed(1) : "—"}
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
          </Grid>

          {/* Recommendations */}
          <Paper sx={{ mb: 3, p: 2 }}>
            <Typography variant="h6" sx={{ mb: 2 }}>Recommendations ({recommendations.length})</Typography>
            <TableContainer>
              <Table>
                <TableHead>
                  <TableRow sx={{ bgcolor: '#f5f5f5' }}>
                    <TableCell><strong>#</strong></TableCell>
                    <TableCell><strong>Action</strong></TableCell>
                    <TableCell><strong>Symbol</strong></TableCell>
                    <TableCell><strong>Reason</strong></TableCell>
                    <TableCell><strong>Target Weight</strong></TableCell>
                    <TableCell><strong>Priority</strong></TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {recommendations.map((rec) => (
                    <TableRow key={rec.id}>
                      <TableCell>{rec.id}</TableCell>
                      <TableCell>
                        <Chip
                          label={rec.action}
                          color={rec.action === 'BUY' ? 'success' : 'error'}
                          size="small"
                          variant="outlined"
                        />
                      </TableCell>
                      <TableCell><strong>{rec.symbol}</strong></TableCell>
                      <TableCell>{rec.reason}</TableCell>
                      <TableCell>{rec.targetWeight || '-'}</TableCell>
                      <TableCell>
                        <Chip
                          label={rec.priority}
                          size="small"
                          sx={{ bgcolor: issueColors[rec.priority], color: 'white' }}
                        />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </Paper>

          {/* Metrics Comparison Chart & Improvements */}
          <Paper sx={{ p: 3, mb: 3 }}>
            <Typography variant="h6" sx={{ mb: 2, fontWeight: 'bold' }}>📈 Expected Improvements</Typography>
            <Typography variant="caption" sx={{ color: '#888', mb: 2, display: 'block' }}>Quantified improvements from current to optimized portfolio</Typography>

            {metricsData.length === 0 || (metricsData.every(d => d.current === null && d.expected === null)) ? (
              <Alert severity="info" sx={{ mb: 2 }}>
                Portfolio metrics unavailable - requires at least 2 days of historical performance data. Once you have sufficient portfolio history, metrics like Beta, Sharpe Ratio, and Volatility will be calculated and displayed here.
              </Alert>
            ) : null}

            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={metricsData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" />
                <YAxis />
                <Tooltip formatter={(value) => value?.toFixed ? value.toFixed(2) : value} />
                <Legend />
                <Bar dataKey="current" fill="#8884d8" name="Current Portfolio" />
                <Bar dataKey="expected" fill="#82ca9d" name="Optimized Portfolio" />
              </BarChart>
            </ResponsiveContainer>

            {/* Improvement Details */}
            <Box sx={{ mt: 3, p: 2, bgcolor: '#f5f5f5', borderRadius: 1 }}>
              <Grid container spacing={2}>
                {/* Beta Improvement */}
                <Grid item xs={12} sm={6} md={3}>
                  <Card sx={{ bgcolor: 'white', boxShadow: 'none', border: '1px solid #eee', height: '100%' }}>
                    <CardContent sx={{ p: 2 }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
                        <Typography variant="caption" sx={{ color: '#666', fontWeight: 'bold', textTransform: 'uppercase' }}>Beta</Typography>
                        {improvements?.beta?.improved ? (
                          <Box sx={{ color: '#4caf50', fontWeight: 'bold' }}>📉</Box>
                        ) : (
                          <Box sx={{ color: '#999' }}>—</Box>
                        )}
                      </Box>
                      <Typography sx={{ color: '#333', fontWeight: 'bold', mb: 0.5 }}>
                        {metrics?.beta || '—'} → {improvements?.beta?.expected ? (typeof improvements.beta.expected === 'number' ? improvements.beta.expected.toFixed(2) : improvements.beta.expected) : '—'}
                      </Typography>
                      <Typography variant="caption" sx={{ color: improvements?.beta?.improved ? '#4caf50' : '#999' }}>
                        {improvements?.beta?.improved ? `✓ Lower is better` : '—'}
                      </Typography>
                    </CardContent>
                  </Card>
                </Grid>

                {/* Sharpe Ratio Improvement */}
                <Grid item xs={12} sm={6} md={3}>
                  <Card sx={{ bgcolor: 'white', boxShadow: 'none', border: '1px solid #eee', height: '100%' }}>
                    <CardContent sx={{ p: 2 }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
                        <Typography variant="caption" sx={{ color: '#666', fontWeight: 'bold', textTransform: 'uppercase' }}>Sharpe Ratio</Typography>
                        {improvements?.sharpeRatio?.improved ? (
                          <Box sx={{ color: '#4caf50', fontWeight: 'bold' }}>📈</Box>
                        ) : (
                          <Box sx={{ color: '#999' }}>—</Box>
                        )}
                      </Box>
                      <Typography sx={{ color: '#333', fontWeight: 'bold', mb: 0.5 }}>
                        {(typeof metrics?.sharpeRatio === 'number' ? metrics.sharpeRatio.toFixed(2) : '—')} → {improvements?.sharpeRatio?.expected ? (typeof improvements.sharpeRatio.expected === 'number' ? improvements.sharpeRatio.expected.toFixed(2) : improvements.sharpeRatio.expected) : '—'}
                      </Typography>
                      <Typography variant="caption" sx={{ color: improvements?.sharpeRatio?.improved ? '#4caf50' : '#999' }}>
                        {improvements?.sharpeRatio?.improved ? `✓ Higher is better` : '—'}
                      </Typography>
                    </CardContent>
                  </Card>
                </Grid>

                {/* Volatility Improvement */}
                <Grid item xs={12} sm={6} md={3}>
                  <Card sx={{ bgcolor: 'white', boxShadow: 'none', border: '1px solid #eee', height: '100%' }}>
                    <CardContent sx={{ p: 2 }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
                        <Typography variant="caption" sx={{ color: '#666', fontWeight: 'bold', textTransform: 'uppercase' }}>Volatility</Typography>
                        {improvements?.volatility?.improved ? (
                          <Box sx={{ color: '#4caf50', fontWeight: 'bold' }}>📉</Box>
                        ) : (
                          <Box sx={{ color: '#999' }}>—</Box>
                        )}
                      </Box>
                      <Typography sx={{ color: '#333', fontWeight: 'bold', mb: 0.5 }}>
                        {metrics?.volatility ? `${metrics.volatility}%` : '—'} → {improvements?.volatility?.expected ? (typeof improvements.volatility.expected === 'number' ? `${improvements.volatility.expected.toFixed(2)}%` : improvements.volatility.expected) : '—'}
                      </Typography>
                      <Typography variant="caption" sx={{ color: improvements?.volatility?.improved ? '#4caf50' : '#999' }}>
                        {improvements?.volatility?.improved ? `✓ Lower is better` : '—'}
                      </Typography>
                    </CardContent>
                  </Card>
                </Grid>

                {/* Concentration Improvement */}
                <Grid item xs={12} sm={6} md={3}>
                  <Card sx={{ bgcolor: 'white', boxShadow: 'none', border: '1px solid #eee', height: '100%' }}>
                    <CardContent sx={{ p: 2 }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
                        <Typography variant="caption" sx={{ color: '#666', fontWeight: 'bold', textTransform: 'uppercase' }}>Concentration</Typography>
                        {improvements?.concentration?.improved ? (
                          <Box sx={{ color: '#4caf50', fontWeight: 'bold' }}>✓</Box>
                        ) : (
                          <Box sx={{ color: '#999' }}>—</Box>
                        )}
                      </Box>
                      <Typography sx={{ color: '#333', fontWeight: 'bold', mb: 0.5 }}>
                        {metrics?.concentration || '—'} → {improvements?.concentration?.expected || '—'}
                      </Typography>
                      <Typography variant="caption" sx={{ color: improvements?.concentration?.improved ? '#4caf50' : '#999' }}>
                        {improvements?.concentration?.improved ? `✓ Better diversified` : '—'}
                      </Typography>
                    </CardContent>
                  </Card>
                </Grid>
              </Grid>
            </Box>
          </Paper>
        </>
      )}

      <Divider sx={{ my: 4 }} />

      {/* PORTFOLIO CORRELATION ANALYSIS - BEFORE & AFTER */}
      {analysis?.portfolioMetrics && (analysis.portfolioMetrics.current || analysis.portfolioMetrics.optimized) && (
        <Paper sx={{ p: 3, mb: 3, bgcolor: '#fafafa' }}>
          <Typography variant="h5" sx={{ mb: 1, fontWeight: 'bold', color: '#1a1a1a' }}>🔗 Correlation Analysis</Typography>
          <Typography variant="caption" sx={{ color: '#888', mb: 3, display: 'block' }}>Risk metrics comparison | Better = Lower correlation risk</Typography>

          <Grid container spacing={2} sx={{ mb: 3 }}>
            {/* CURRENT PORTFOLIO METRICS */}
            <Grid item xs={12} sm={6}>
              <Card sx={{ height: '100%', bgcolor: 'white', border: '2px solid #fff3e0', boxShadow: '0 2px 8px rgba(0,0,0,0.05)' }}>
                <CardContent sx={{ p: 2.5 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', mb: 2.5 }}>
                    <Box sx={{ width: 10, height: 10, borderRadius: '50%', bgcolor: '#ff9800', mr: 1 }}></Box>
                    <Typography variant="subtitle1" sx={{ fontWeight: '600', color: '#333' }}>Current Portfolio</Typography>
                  </Box>
                  {analysis.portfolioMetrics.current && (
                    <Grid container spacing={1.5}>
                      <Grid item xs={6}>
                        <Box sx={{ bgcolor: '#fff9f0', p: 1.5, borderRadius: 1 }}>
                          <Typography variant="caption" sx={{ color: '#888', fontSize: '0.7rem', fontWeight: '600', textTransform: 'uppercase' }}>Beta</Typography>
                          <Typography variant="h6" sx={{ fontWeight: '700', color: '#ff6f00', mt: 0.5 }}>{(typeof analysis.portfolioMetrics.current.beta === 'number' && !isNaN(analysis.portfolioMetrics.current.beta)) ? analysis.portfolioMetrics.current.beta.toFixed(2) : '—'}</Typography>
                        </Box>
                      </Grid>
                      <Grid item xs={6}>
                        <Box sx={{ bgcolor: '#fff9f0', p: 1.5, borderRadius: 1 }}>
                          <Typography variant="caption" sx={{ color: '#888', fontSize: '0.7rem', fontWeight: '600', textTransform: 'uppercase' }}>Volatility</Typography>
                          <Typography variant="h6" sx={{ fontWeight: '700', color: '#ff6f00', mt: 0.5 }}>{(typeof analysis.portfolioMetrics.current.volatility === 'number' && !isNaN(analysis.portfolioMetrics.current.volatility)) ? analysis.portfolioMetrics.current.volatility.toFixed(1) + '%' : '—'}</Typography>
                        </Box>
                      </Grid>
                      <Grid item xs={6}>
                        <Box sx={{ bgcolor: '#fff9f0', p: 1.5, borderRadius: 1 }}>
                          <Typography variant="caption" sx={{ color: '#888', fontSize: '0.7rem', fontWeight: '600', textTransform: 'uppercase' }}>Sharpe</Typography>
                          <Typography variant="h6" sx={{ fontWeight: '700', color: '#ff6f00', mt: 0.5 }}>{(typeof analysis.portfolioMetrics.current.sharpeRatio === 'number' && !isNaN(analysis.portfolioMetrics.current.sharpeRatio)) ? analysis.portfolioMetrics.current.sharpeRatio.toFixed(2) : '—'}</Typography>
                        </Box>
                      </Grid>
                      <Grid item xs={6}>
                        <Box sx={{ bgcolor: '#fff9f0', p: 1.5, borderRadius: 1 }}>
                          <Typography variant="caption" sx={{ color: '#888', fontSize: '0.7rem', fontWeight: '600', textTransform: 'uppercase' }}>Diversif.</Typography>
                          <Typography variant="h6" sx={{ fontWeight: '700', color: '#ff6f00', mt: 0.5 }}>{(typeof analysis.portfolioMetrics.current.diversificationScore === 'number' && !isNaN(analysis.portfolioMetrics.current.diversificationScore)) ? (analysis.portfolioMetrics.current.diversificationScore * 100).toFixed(0) + '%' : '—'}</Typography>
                        </Box>
                      </Grid>
                      <Grid item xs={12}>
                        <Box sx={{ bgcolor: '#fff9f0', p: 1.5, borderRadius: 1 }}>
                          <Typography variant="caption" sx={{ color: '#888', fontSize: '0.7rem', fontWeight: '600', textTransform: 'uppercase' }}>Concentration Risk</Typography>
                          <Typography variant="h6" sx={{ fontWeight: '700', color: '#ff6f00', mt: 0.5 }}>{(typeof analysis.portfolioMetrics.current.concentrationRatio === 'number' && !isNaN(analysis.portfolioMetrics.current.concentrationRatio)) ? analysis.portfolioMetrics.current.concentrationRatio.toFixed(1) + '%' : '—'}</Typography>
                        </Box>
                      </Grid>
                    </Grid>
                  )}
                </CardContent>
              </Card>
            </Grid>

            {/* OPTIMIZED PORTFOLIO METRICS */}
            <Grid item xs={12} sm={6}>
              <Card sx={{ height: '100%', bgcolor: 'white', border: '2px solid #e8f5e9', boxShadow: '0 2px 8px rgba(0,0,0,0.05)' }}>
                <CardContent sx={{ p: 2.5 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', mb: 2.5 }}>
                    <Box sx={{ width: 10, height: 10, borderRadius: '50%', bgcolor: '#4caf50', mr: 1 }}></Box>
                    <Typography variant="subtitle1" sx={{ fontWeight: '600', color: '#333' }}>Optimized</Typography>
                  </Box>
                  {analysis.portfolioMetrics.optimized && (
                    <Grid container spacing={1.5}>
                      <Grid item xs={6}>
                        <Box sx={{ bgcolor: '#f1f8f5', p: 1.5, borderRadius: 1 }}>
                          <Typography variant="caption" sx={{ color: '#888', fontSize: '0.7rem', fontWeight: '600', textTransform: 'uppercase' }}>Beta</Typography>
                          <Typography variant="h6" sx={{ fontWeight: '700', color: '#2e7d32', mt: 0.5 }}>{(typeof analysis.portfolioMetrics.optimized.beta === 'number' && !isNaN(analysis.portfolioMetrics.optimized.beta)) ? analysis.portfolioMetrics.optimized.beta.toFixed(2) : '—'}</Typography>
                        </Box>
                      </Grid>
                      <Grid item xs={6}>
                        <Box sx={{ bgcolor: '#f1f8f5', p: 1.5, borderRadius: 1 }}>
                          <Typography variant="caption" sx={{ color: '#888', fontSize: '0.7rem', fontWeight: '600', textTransform: 'uppercase' }}>Volatility</Typography>
                          <Typography variant="h6" sx={{ fontWeight: '700', color: '#2e7d32', mt: 0.5 }}>{(typeof analysis.portfolioMetrics.optimized.volatility === 'number' && !isNaN(analysis.portfolioMetrics.optimized.volatility)) ? analysis.portfolioMetrics.optimized.volatility.toFixed(1) + '%' : '—'}</Typography>
                        </Box>
                      </Grid>
                      <Grid item xs={6}>
                        <Box sx={{ bgcolor: '#f1f8f5', p: 1.5, borderRadius: 1 }}>
                          <Typography variant="caption" sx={{ color: '#888', fontSize: '0.7rem', fontWeight: '600', textTransform: 'uppercase' }}>Sharpe</Typography>
                          <Typography variant="h6" sx={{ fontWeight: '700', color: '#2e7d32', mt: 0.5 }}>{(typeof analysis.portfolioMetrics.optimized.sharpeRatio === 'number' && !isNaN(analysis.portfolioMetrics.optimized.sharpeRatio)) ? analysis.portfolioMetrics.optimized.sharpeRatio.toFixed(2) : '—'}</Typography>
                        </Box>
                      </Grid>
                      <Grid item xs={6}>
                        <Box sx={{ bgcolor: '#f1f8f5', p: 1.5, borderRadius: 1 }}>
                          <Typography variant="caption" sx={{ color: '#888', fontSize: '0.7rem', fontWeight: '600', textTransform: 'uppercase' }}>Diversif.</Typography>
                          <Typography variant="h6" sx={{ fontWeight: '700', color: '#2e7d32', mt: 0.5 }}>{(typeof analysis.portfolioMetrics.optimized.diversificationScore === 'number' && !isNaN(analysis.portfolioMetrics.optimized.diversificationScore)) ? (analysis.portfolioMetrics.optimized.diversificationScore * 100).toFixed(0) + '%' : '—'}</Typography>
                        </Box>
                      </Grid>
                      <Grid item xs={12}>
                        <Box sx={{ bgcolor: '#f1f8f5', p: 1.5, borderRadius: 1 }}>
                          <Typography variant="caption" sx={{ color: '#888', fontSize: '0.7rem', fontWeight: '600', textTransform: 'uppercase' }}>Concentration Risk</Typography>
                          <Typography variant="h6" sx={{ fontWeight: '700', color: '#2e7d32', mt: 0.5 }}>{(typeof analysis.portfolioMetrics.optimized.concentrationRatio === 'number' && !isNaN(analysis.portfolioMetrics.optimized.concentrationRatio)) ? analysis.portfolioMetrics.optimized.concentrationRatio.toFixed(1) + '%' : '—'}</Typography>
                        </Box>
                      </Grid>
                    </Grid>
                  )}
                </CardContent>
              </Card>
            </Grid>
          </Grid>

          {/* IMPROVEMENTS SUMMARY */}
          {analysis.portfolioMetrics.improvements && (
            <Grid container spacing={1.5}>
              <Grid item xs={6} sm={3}>
                <Card sx={{ bgcolor: 'white', boxShadow: 'none', border: '1px solid #eee' }}>
                  <CardContent sx={{ p: 1.5, textAlign: 'center' }}>
                    <Typography variant="caption" sx={{ color: '#999', fontSize: '0.65rem', fontWeight: '600', textTransform: 'uppercase' }}>Beta Δ</Typography>
                    <Typography variant="body2" sx={{ fontWeight: '700', color: analysis.portfolioMetrics.improvements.betaReduction?.includes('-') ? '#f44336' : '#4caf50', mt: 0.5 }}>
                      {analysis.portfolioMetrics.improvements.betaReduction}
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={6} sm={3}>
                <Card sx={{ bgcolor: 'white', boxShadow: 'none', border: '1px solid #eee' }}>
                  <CardContent sx={{ p: 1.5, textAlign: 'center' }}>
                    <Typography variant="caption" sx={{ color: '#999', fontSize: '0.65rem', fontWeight: '600', textTransform: 'uppercase' }}>Risk Δ</Typography>
                    <Typography variant="body2" sx={{ fontWeight: '700', color: '#4caf50', mt: 0.5 }}>
                      {analysis.portfolioMetrics.improvements.riskReduction}
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={6} sm={3}>
                <Card sx={{ bgcolor: 'white', boxShadow: 'none', border: '1px solid #eee' }}>
                  <CardContent sx={{ p: 1.5, textAlign: 'center' }}>
                    <Typography variant="caption" sx={{ color: '#999', fontSize: '0.65rem', fontWeight: '600', textTransform: 'uppercase' }}>Sharpe Δ</Typography>
                    <Typography variant="body2" sx={{ fontWeight: '700', color: analysis.portfolioMetrics.improvements.sharpeImprovement?.includes('-') ? '#f44336' : '#4caf50', mt: 0.5 }}>
                      {analysis.portfolioMetrics.improvements.sharpeImprovement}
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={6} sm={3}>
                <Card sx={{ bgcolor: 'white', boxShadow: 'none', border: '1px solid #eee' }}>
                  <CardContent sx={{ p: 1.5, textAlign: 'center' }}>
                    <Typography variant="caption" sx={{ color: '#999', fontSize: '0.65rem', fontWeight: '600', textTransform: 'uppercase' }}>Diversif. Δ</Typography>
                    <Typography variant="body2" sx={{ fontWeight: '700', color: analysis.portfolioMetrics.improvements.diversificationGain?.includes('-') ? '#f44336' : '#4caf50', mt: 0.5 }}>
                      {analysis.portfolioMetrics.improvements.diversificationGain}
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          )}

        </Paper>
      )}



      {/* SECTOR ALLOCATION - BEFORE & AFTER REBALANCE */}
      {analysis?.sectorRebalance && (analysis.sectorRebalance.before?.length > 0 || analysis.sectorRebalance.after?.length > 0) && (
        <Paper sx={{ p: 3, mb: 3, bgcolor: '#fafafa' }}>
          <Typography variant="h5" sx={{ mb: 1, fontWeight: 'bold', color: '#1a1a1a' }}>🎯 Sector Allocation</Typography>
          <Typography variant="caption" sx={{ color: '#888', mb: 3, display: 'block' }}>Diversification impact | More sectors = Lower correlation risk</Typography>

          <Grid container spacing={2}>
            {/* BEFORE */}
            <Grid item xs={12} sm={6}>
              <Card sx={{ height: '100%', bgcolor: 'white', border: '2px solid #fff3e0', boxShadow: '0 2px 8px rgba(0,0,0,0.05)' }}>
                <CardContent sx={{ p: 2.5 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', mb: 2.5 }}>
                    <Box sx={{ width: 10, height: 10, borderRadius: '50%', bgcolor: '#ff9800', mr: 1 }}></Box>
                    <Typography variant="subtitle1" sx={{ fontWeight: '600', color: '#333' }}>Current Sectors</Typography>
                  </Box>
                  <Box>
                    {analysis.sectorRebalance.before.map((sector, idx) => (
                      <Box key={idx} sx={{ mb: 1.5 }}>
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 0.5 }}>
                          <Typography variant="body2" sx={{ fontWeight: '600', color: '#333', flex: 1 }}>{sector.sector}</Typography>
                          <Typography variant="body2" sx={{ fontWeight: '700', color: '#ff6f00', minWidth: '50px', textAlign: 'right' }}>{sector.weight}</Typography>
                          <Typography variant="caption" sx={{ color: '#999', ml: 1 }}>{sector.count}p</Typography>
                        </Box>
                        <Box sx={{ height: 6, bgcolor: '#ffe0b2', borderRadius: '3px', overflow: 'hidden' }}>
                          <Box sx={{ height: '100%', bgcolor: '#ff9800', width: sector.weight, transition: 'width 0.3s' }} />
                        </Box>
                      </Box>
                    ))}
                  </Box>
                  <Box sx={{ mt: 2, pt: 1.5, borderTop: '1px solid #f0f0f0', textAlign: 'center' }}>
                    <Typography variant="caption" sx={{ color: '#ff6f00', fontWeight: '700', fontSize: '0.75rem', textTransform: 'uppercase' }}>
                      {analysis.sectorRebalance.before.length} Sectors
                    </Typography>
                  </Box>
                </CardContent>
              </Card>
            </Grid>

            {/* AFTER */}
            <Grid item xs={12} sm={6}>
              <Card sx={{ height: '100%', bgcolor: 'white', border: '2px solid #e8f5e9', boxShadow: '0 2px 8px rgba(0,0,0,0.05)' }}>
                <CardContent sx={{ p: 2.5 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', mb: 2.5 }}>
                    <Box sx={{ width: 10, height: 10, borderRadius: '50%', bgcolor: '#4caf50', mr: 1 }}></Box>
                    <Typography variant="subtitle1" sx={{ fontWeight: '600', color: '#333' }}>Target Sectors</Typography>
                    {analysis.sectorRebalance.after.length > analysis.sectorRebalance.before.length && (
                      <Chip label={`+${analysis.sectorRebalance.after.length - analysis.sectorRebalance.before.length}`} size="small" sx={{ ml: 'auto', bgcolor: '#c8e6c9', color: '#2e7d32', fontWeight: '600', height: '22px' }} />
                    )}
                  </Box>
                  <Box>
                    {analysis.sectorRebalance.after.map((sector, idx) => (
                      <Box key={idx} sx={{ mb: 1.5 }}>
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 0.5 }}>
                          <Typography variant="body2" sx={{ fontWeight: '600', color: '#333', flex: 1 }}>{sector.sector}</Typography>
                          <Typography variant="body2" sx={{ fontWeight: '700', color: '#2e7d32', minWidth: '50px', textAlign: 'right' }}>{sector.weight}</Typography>
                          <Typography variant="caption" sx={{ color: '#999', ml: 1 }}>{sector.count}p</Typography>
                        </Box>
                        <Box sx={{ height: 6, bgcolor: '#c8e6c9', borderRadius: '3px', overflow: 'hidden' }}>
                          <Box sx={{ height: '100%', bgcolor: '#4caf50', width: sector.weight, transition: 'width 0.3s' }} />
                        </Box>
                      </Box>
                    ))}
                  </Box>
                  <Box sx={{ mt: 2, pt: 1.5, borderTop: '1px solid #f0f0f0', textAlign: 'center' }}>
                    <Typography variant="caption" sx={{ color: '#2e7d32', fontWeight: '700', fontSize: '0.75rem', textTransform: 'uppercase' }}>
                      {analysis.sectorRebalance.after.length} Sectors
                    </Typography>
                  </Box>
                </CardContent>
              </Card>
            </Grid>
          </Grid>

        </Paper>
      )}

      {/* EFFICIENT FRONTIER ANALYSIS */}
      {analysis?.efficientFrontier && analysis.efficientFrontier.length > 0 && (
        <Paper sx={{ p: 3, mb: 3, bgcolor: '#fafafa' }}>
          <Typography variant="h5" sx={{ mb: 1, fontWeight: 'bold', color: '#1a1a1a' }}>📊 Efficient Frontier</Typography>
          <Typography variant="caption" sx={{ color: '#888', mb: 3, display: 'block' }}>Risk vs Return trade-offs | Current portfolio vs optimized strategies</Typography>

          <ResponsiveContainer width="100%" height={350}>
            <LineChart data={analysis.efficientFrontier}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis
                dataKey="riskProfile"
                label={{ value: 'Risk Profile', position: 'insideBottomRight', offset: -5 }}
              />
              <YAxis
                yAxisId="left"
                label={{ value: 'Return %', angle: -90, position: 'insideLeft' }}
              />
              <YAxis
                yAxisId="right"
                orientation="right"
                label={{ value: 'Sharpe Ratio', angle: 90, position: 'insideRight' }}
              />
              <Tooltip
                formatter={(value) => typeof value === 'number' ? value.toFixed(2) : value}
                labelFormatter={(label) => `Risk Profile: ${label}`}
              />
              <Legend />
              <Line
                yAxisId="left"
                type="monotone"
                dataKey="return"
                stroke="#82ca9d"
                name="Expected Return"
                dot={{ r: 5 }}
              />
              <Line
                yAxisId="right"
                type="monotone"
                dataKey="sharpeRatio"
                stroke="#8884d8"
                name="Sharpe Ratio"
                dot={{ r: 5 }}
              />
            </LineChart>
          </ResponsiveContainer>

          <Box sx={{ mt: 3, p: 2, bgcolor: '#f5f5f5', borderRadius: 1 }}>
            <Grid container spacing={2}>
              <Grid item xs={12} sm={6} md={3}>
                <Typography variant="caption" color="textSecondary">Frontier Points</Typography>
                <Typography variant="body2" sx={{ fontWeight: 'bold', color: '#1976d2' }}>
                  {analysis.efficientFrontier.length}
                </Typography>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <Typography variant="caption" color="textSecondary">Risk Range</Typography>
                <Typography variant="body2" sx={{ fontWeight: 'bold', color: '#f57c00' }}>
                  {Math.min(...analysis.efficientFrontier.map(e => e.risk || 0)).toFixed(1)}% - {Math.max(...analysis.efficientFrontier.map(e => e.risk || 0)).toFixed(1)}%
                </Typography>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <Typography variant="caption" color="textSecondary">Return Range</Typography>
                <Typography variant="body2" sx={{ fontWeight: 'bold', color: '#4caf50' }}>
                  {Math.min(...analysis.efficientFrontier.map(e => e.return || 0)).toFixed(1)}% - {Math.max(...analysis.efficientFrontier.map(e => e.return || 0)).toFixed(1)}%
                </Typography>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <Typography variant="caption" color="textSecondary">Max Sharpe Ratio</Typography>
                <Typography variant="body2" sx={{ fontWeight: 'bold', color: '#2196f3' }}>
                  {Math.max(...analysis.efficientFrontier.map(e => e.sharpeRatio || 0)).toFixed(2)}
                </Typography>
              </Grid>
            </Grid>
          </Box>
        </Paper>
      )}

      {/* TARGET ALLOCATION DETAILS */}
      {analysis?.targetAllocation && analysis.targetAllocation.length > 0 && (
        <Paper sx={{ p: 3, mb: 3, bgcolor: '#fafafa' }}>
          <Typography variant="h5" sx={{ mb: 1, fontWeight: 'bold', color: '#1a1a1a' }}>🎯 Target Allocation Breakdown</Typography>
          <Typography variant="caption" sx={{ color: '#888', mb: 3, display: 'block' }}>Recommended portfolio weights for optimal risk-adjusted returns</Typography>

          <Grid container spacing={2}>
            {/* Pie Chart */}
            <Grid item xs={12} md={6}>
              <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 350 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={analysis.targetAllocation
                        .filter(a => a.weight !== null && a.weight !== undefined)
                        .map(a => ({
                          name: a.symbol,
                          value: parseFloat(a.weight.replace('%', ''))
                        }))}
                      cx="50%"
                      cy="50%"
                      labelLine={false}
                      label={({ name, value }) => `${name}: ${value.toFixed(1)}%`}
                      outerRadius={100}
                      fill="#8884d8"
                      dataKey="value"
                    >
                      {analysis.targetAllocation.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip formatter={(value) => `${value.toFixed(2)}%`} />
                  </PieChart>
                </ResponsiveContainer>
              </Box>
            </Grid>

            {/* Table */}
            <Grid item xs={12} md={6}>
              <TableContainer sx={{ maxHeight: 350, overflow: 'auto' }}>
                <Table size="small">
                  <TableHead>
                    <TableRow sx={{ bgcolor: '#e8f5e9', position: 'sticky', top: 0 }}>
                      <TableCell sx={{ fontWeight: 'bold', width: '30%' }}>Symbol</TableCell>
                      <TableCell align="right" sx={{ fontWeight: 'bold', width: '35%' }}>Target Weight</TableCell>
                      <TableCell align="right" sx={{ fontWeight: 'bold', width: '35%' }}>Expected Impact</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {analysis.targetAllocation
                      .filter(a => a.weight !== null && a.weight !== undefined)
                      .map((allocation, idx) => {
                      const weight = parseFloat(allocation.weight.replace('%', ''));
                      const impact = weight > 15 ? 'High' : weight > 5 ? 'Medium' : 'Low';
                      const impactColor = impact === 'High' ? '#2e7d32' : impact === 'Medium' ? '#f57c00' : '#666';
                      return (
                        <TableRow key={idx} sx={{ '&:hover': { bgcolor: '#f1f8f5' } }}>
                          <TableCell sx={{ fontWeight: 'bold', color: '#333' }}>{allocation.symbol}</TableCell>
                          <TableCell align="right" sx={{ fontWeight: '700', color: '#2e7d32', fontSize: '1rem' }}>
                            {weight.toFixed(2)}%
                          </TableCell>
                          <TableCell align="right" sx={{ color: impactColor, fontWeight: 'bold' }}>
                            {impact}
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </TableContainer>

              <Box sx={{ mt: 2, p: 2, bgcolor: '#f1f8f5', borderRadius: 1, borderLeft: '3px solid #4caf50' }}>
                <Typography variant="caption" sx={{ color: '#2e7d32', fontWeight: 'bold' }}>
                  Total Portfolio: {analysis.targetAllocation
                    .filter(a => a.weight !== null && a.weight !== undefined)
                    .reduce((sum, a) => sum + parseFloat(a.weight.replace('%', '')), 0).toFixed(2)}% | {analysis.targetAllocation.filter(a => a.weight !== null && a.weight !== undefined).length} positions
                </Typography>
              </Box>
            </Grid>
          </Grid>
        </Paper>
      )}

      {/* PORTFOLIO HOLDINGS - BEFORE & AFTER REBALANCE */}
      {analysis?.allocationComparison && analysis.allocationComparison.before && analysis.allocationComparison.after && (
        <Paper sx={{ p: 2, mb: 3 }}>
          <Typography variant="h6" sx={{ mb: 3, fontWeight: 'bold' }}>📈 Portfolio Holdings: Before & After Rebalance</Typography>
          <Typography variant="body2" color="textSecondary" sx={{ mb: 2 }}>
            Individual position changes | Compare current weights vs target weights | Green = Improvement expected
          </Typography>

          <Box sx={{ display: 'flex', gap: 3, flexWrap: 'wrap' }}>
            {/* BEFORE HOLDINGS */}
            <Box sx={{ flex: '1 1 400px', minWidth: 400 }}>
              <Typography variant="subtitle2" sx={{ mb: 2, fontWeight: 'bold', color: '#ff6f00', display: 'flex', alignItems: 'center', gap: 1 }}>
                📍 Current Holdings
              </Typography>

              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow sx={{ bgcolor: '#fff3e0' }}>
                      <TableCell sx={{ fontWeight: 'bold', width: '40%' }}>Symbol</TableCell>
                      <TableCell align="right" sx={{ fontWeight: 'bold', width: '30%' }}>Weight</TableCell>
                      <TableCell align="right" sx={{ fontWeight: 'bold', width: '30%' }}>Sector</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {analysis.allocationComparison.before && analysis.allocationComparison.before.length > 0 ? (
                      analysis.allocationComparison.before.map((holding, idx) => (
                        <TableRow key={idx} sx={{ '&:hover': { bgcolor: '#fff8f0' } }}>
                          <TableCell sx={{ fontWeight: 'bold', color: '#333' }}>{holding.symbol}</TableCell>
                          <TableCell align="right" sx={{ color: '#ff9800', fontWeight: 'bold' }}>{holding.weight}</TableCell>
                          <TableCell align="right" sx={{ fontSize: '0.875rem', color: '#666' }}>{holding.sector || 'N/A'}</TableCell>
                        </TableRow>
                      ))
                    ) : (
                      <TableRow>
                        <TableCell colSpan={3} align="center" sx={{ color: '#999', py: 2 }}>No current holdings</TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </TableContainer>

              <Box sx={{ mt: 2, p: 1.5, bgcolor: '#fff9e6', borderRadius: 1, borderLeft: '3px solid #ff9800' }}>
                <Typography variant="caption" sx={{ color: '#ff6f00', fontWeight: 'bold' }}>
                  {analysis.allocationComparison.before ? analysis.allocationComparison.before.length : 0} positions | Total: 100%
                </Typography>
              </Box>
            </Box>

            {/* AFTER HOLDINGS */}
            <Box sx={{ flex: '1 1 400px', minWidth: 400 }}>
              <Typography variant="subtitle2" sx={{ mb: 2, fontWeight: 'bold', color: '#2e7d32', display: 'flex', alignItems: 'center', gap: 1 }}>
                ✅ Target Holdings
              </Typography>

              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow sx={{ bgcolor: '#e8f5e9' }}>
                      <TableCell sx={{ fontWeight: 'bold', width: '40%' }}>Symbol</TableCell>
                      <TableCell align="right" sx={{ fontWeight: 'bold', width: '30%' }}>Weight</TableCell>
                      <TableCell align="right" sx={{ fontWeight: 'bold', width: '30%' }}>Sector</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {analysis.allocationComparison.after && analysis.allocationComparison.after.length > 0 ? (
                      analysis.allocationComparison.after.map((holding, idx) => {
                        try {
                          const beforeHolding = analysis.allocationComparison.before?.find(h => h.symbol === holding.symbol);
                          const beforeWeightStr = beforeHolding?.weight?.toString() || '0%';
                          const afterWeightStr = holding.weight?.toString() || '0%';
                          const beforeWeightNum = parseFloat(beforeWeightStr.replace('%', ''));
                          const afterWeightNum = parseFloat(afterWeightStr.replace('%', ''));
                          const weightChanged = beforeHolding && beforeWeightNum !== afterWeightNum;
                          const isNewPosition = !beforeHolding;

                          return (
                            <TableRow key={idx} sx={{
                              bgcolor: isNewPosition ? '#c8e6c9' : weightChanged ? '#fff8e1' : 'transparent',
                              '&:hover': { bgcolor: isNewPosition ? '#b5ddb5' : '#f5f5f5' }
                            }}>
                              <TableCell sx={{ fontWeight: 'bold', color: '#333' }}>
                                {holding.symbol}
                                {isNewPosition && <Chip label="NEW" size="small" sx={{ ml: 1, bgcolor: '#4caf50', color: 'white', height: '20px' }} />}
                              </TableCell>
                              <TableCell align="right">
                                <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 0.5 }}>
                                  <Typography sx={{ color: '#4caf50', fontWeight: 'bold' }}>
                                    {holding.weight}
                                  </Typography>
                                  {weightChanged && !isNaN(beforeWeightNum) && !isNaN(afterWeightNum) && (
                                    <Typography variant="caption" sx={{
                                      color: afterWeightNum > beforeWeightNum ? '#4caf50' : '#f44336',
                                      fontWeight: 'bold'
                                    }}>
                                      {afterWeightNum > beforeWeightNum ? '↑' : '↓'} {Math.abs((afterWeightNum - beforeWeightNum).toFixed(2))}%
                                    </Typography>
                                  )}
                                </Box>
                              </TableCell>
                              <TableCell align="right" sx={{ fontSize: '0.875rem', color: '#666' }}>
                                {holding.sector || 'N/A'}
                              </TableCell>
                            </TableRow>
                          );
                        } catch (e) {
                          console.error('Error rendering holding:', e, holding);
                          return null;
                        }
                      })
                    ) : (
                      <TableRow>
                        <TableCell colSpan={3} align="center" sx={{ color: '#999', py: 2 }}>No target holdings</TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </TableContainer>

              <Box sx={{ mt: 2, p: 1.5, bgcolor: '#f1f8e9', borderRadius: 1, borderLeft: '3px solid #4caf50' }}>
                <Typography variant="caption" sx={{ color: '#2e7d32', fontWeight: 'bold' }}>
                  {analysis.allocationComparison.after ? analysis.allocationComparison.after.length : 0} positions | +{((analysis.allocationComparison.after?.length || 0) - (analysis.allocationComparison.before?.length || 0))} new
                </Typography>
              </Box>
            </Box>
          </Box>

          {/* Change Summary */}
          <Box sx={{ mt: 3, p: 2, bgcolor: '#f5f5f5', borderRadius: 1, borderLeft: '4px solid #1976d2' }}>
            <Grid container spacing={2}>
              <Grid item xs={12} sm={6} md={3}>
                <Typography variant="caption" color="textSecondary">Current Holdings</Typography>
                <Typography variant="body2" sx={{ fontWeight: 'bold', color: '#ff9800' }}>
                  {analysis.allocationComparison.before?.length || 0}
                </Typography>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <Typography variant="caption" color="textSecondary">Target Holdings</Typography>
                <Typography variant="body2" sx={{ fontWeight: 'bold', color: '#4caf50' }}>
                  {analysis.allocationComparison.after?.length || 0}
                </Typography>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <Typography variant="caption" color="textSecondary">New Positions</Typography>
                <Typography variant="body2" sx={{ fontWeight: 'bold', color: '#2196f3' }}>
                  +{((analysis.allocationComparison.after?.length || 0) - (analysis.allocationComparison.before?.length || 0))}
                </Typography>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <Typography variant="caption" color="textSecondary">Positions Exited</Typography>
                <Typography variant="body2" sx={{ fontWeight: 'bold', color: '#f44336' }}>
                  {analysis.allocationComparison.before ? analysis.allocationComparison.before.filter(b => !analysis.allocationComparison.after?.find(a => a.symbol === b.symbol)).length : 0}
                </Typography>
              </Grid>
            </Grid>
          </Box>
        </Paper>
      )}

    </Container>
  );
}
