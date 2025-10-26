import React, { useState, useMemo, useEffect } from "react";
import {
  Container,
  Typography,
  Box,
  Card,
  CardContent,
  Grid,
  TextField,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TablePagination,
  Paper,
  Alert,
  CircularProgress,
  Divider,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  InputAdornment,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  alpha,
  Chip,
  useTheme,
} from "@mui/material";
import {
  TrendingUp,
  TrendingDown,
  TrendingFlat,
  SentimentSatisfiedAlt,
  Search,
  Reddit,
  Newspaper,
  TrendingUpRounded,
  ExpandMore,
  Info as InfoIcon,
  Timeline as TimelineIcon,
  ShowChart as ShowChartIcon,
} from "@mui/icons-material";
import { useQuery } from "@tanstack/react-query";
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip as RechartsTooltip } from "recharts";

const API_BASE = (import.meta.env && import.meta.env.VITE_API_URL) || "http://localhost:3001";

// Composite sentiment scoring algorithm
const calculateCompositeSentiment = (newsScore, analystScore, socialScore) => {
  // Weights: News 40%, Analyst 35%, Social 25%
  const weights = { news: 0.4, analyst: 0.35, social: 0.25 };

  let totalWeight = 0;
  let weightedSum = 0;

  if (newsScore !== null && newsScore !== undefined) {
    weightedSum += newsScore * weights.news;
    totalWeight += weights.news;
  }
  if (analystScore !== null && analystScore !== undefined) {
    weightedSum += analystScore * weights.analyst;
    totalWeight += weights.analyst;
  }
  if (socialScore !== null && socialScore !== undefined) {
    weightedSum += socialScore * weights.social;
    totalWeight += weights.social;
  }

  // Return normalized score or null if no data
  if (totalWeight === 0) return null;
  return weightedSum / totalWeight;
};

// Convert composite score to sentiment label
const getSentimentLabel = (score) => {
  if (score === null || score === undefined) return { label: "Unknown", color: "default", icon: <TrendingFlat /> };
  if (score > 0.3) return { label: "Bullish", color: "success", icon: <TrendingUp /> };
  if (score < -0.3) return { label: "Bearish", color: "error", icon: <TrendingDown /> };
  return { label: "Neutral", color: "warning", icon: <TrendingFlat /> };
};

// Detect sentiment divergence (when sources disagree significantly)
const detectSentimentDivergence = (newsScore, analystScore, socialScore) => {
  const scores = [newsScore, analystScore, socialScore].filter(s => s !== null && s !== undefined);
  if (scores.length < 2) return null;

  const maxScore = Math.max(...scores);
  const minScore = Math.min(...scores);
  const divergence = maxScore - minScore;

  // Significant divergence threshold
  if (divergence > 0.6) {
    return {
      isDiverged: true,
      severity: divergence > 1 ? "critical" : "moderate",
      message: `Sources disagree significantly (${(divergence * 100).toFixed(0)}% spread)`
    };
  }

  return { isDiverged: false };
};

// Comprehensive Analyst Metrics Component - Detailed analyst data
const ComprehensiveAnalystMetrics = ({ symbol }) => {
  const theme = useTheme();
  const [sentimentTrend, setSentimentTrend] = React.useState(null);
  const [momentum, setMomentum] = React.useState(null);
  const [epsRevisions, setEpsRevisions] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState(null);

  React.useEffect(() => {
    const fetchAnalystData = async () => {
      try {
        setLoading(true);
        setError(null);

        // Fetch from multiple analyst endpoints
        const [trendRes, momentumRes, epsRes] = await Promise.all([
          fetch(`${API_BASE}/api/analysts/${symbol}/sentiment-trend`).catch(() => null),
          fetch(`${API_BASE}/api/analysts/${symbol}/analyst-momentum`).catch(() => null),
          fetch(`${API_BASE}/api/analysts/${symbol}/eps-revisions`).catch(() => null),
        ]);

        if (trendRes?.ok) {
          const trendData = await trendRes.json();
          setSentimentTrend(trendData?.data || trendData);
        }
        if (momentumRes?.ok) {
          const momentumData = await momentumRes.json();
          setMomentum(momentumData?.data || momentumData);
        }
        if (epsRes?.ok) {
          const epsData = await epsRes.json();
          setEpsRevisions(epsData?.data || epsData);
        }
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    if (symbol) {
      fetchAnalystData();
    }
  }, [symbol]);

  if (loading) {
    return (
      <Card variant="outlined">
        <CardContent>
          <CircularProgress size={24} sx={{ mr: 1 }} />
          <Typography variant="body2" color="textSecondary">Loading comprehensive analyst data...</Typography>
        </CardContent>
      </Card>
    );
  }

  return (
    <Box>
      {/* Sentiment Trend */}
      {sentimentTrend && (
        <Card variant="outlined" sx={{ mb: 2 }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>Analyst Sentiment Trend</Typography>
            {Array.isArray(sentimentTrend) ? (
              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Date</TableCell>
                      <TableCell align="center">Bullish %</TableCell>
                      <TableCell align="center">Neutral %</TableCell>
                      <TableCell align="center">Bearish %</TableCell>
                      <TableCell align="center">Total</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {sentimentTrend.slice(0, 10).map((item, idx) => (
                      <TableRow key={idx}>
                        <TableCell>{new Date(item.date || item.timestamp).toLocaleDateString()}</TableCell>
                        <TableCell align="center">
                          <Chip label={`${item.bullish_pct || 0}%`} size="small" color="success" />
                        </TableCell>
                        <TableCell align="center">
                          <Chip label={`${item.neutral_pct || 0}%`} size="small" />
                        </TableCell>
                        <TableCell align="center">
                          <Chip label={`${item.bearish_pct || 0}%`} size="small" color="error" />
                        </TableCell>
                        <TableCell align="center">{item.total_analysts || 0}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            ) : (
              <Typography variant="body2" color="textSecondary">No trend data available</Typography>
            )}
          </CardContent>
        </Card>
      )}

      {/* Momentum Data */}
      {momentum && (
        <Card variant="outlined" sx={{ mb: 2 }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>Analyst Actions & Momentum</Typography>
            <Grid container spacing={2}>
              <Grid item xs={12} sm={6} md={3}>
                <Box sx={{ p: 1.5, bgcolor: alpha(theme.palette.success.main, 0.1), borderRadius: 1 }}>
                  <Typography variant="caption" color="textSecondary">Upgrades (30d)</Typography>
                  <Typography variant="h5" sx={{ fontWeight: 'bold', color: theme.palette.success.main }}>
                    {momentum.upgrades_30d || momentum.upgrades || 0}
                  </Typography>
                </Box>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <Box sx={{ p: 1.5, bgcolor: alpha(theme.palette.error.main, 0.1), borderRadius: 1 }}>
                  <Typography variant="caption" color="textSecondary">Downgrades (30d)</Typography>
                  <Typography variant="h5" sx={{ fontWeight: 'bold', color: theme.palette.error.main }}>
                    {momentum.downgrades_30d || momentum.downgrades || 0}
                  </Typography>
                </Box>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <Box sx={{ p: 1.5, bgcolor: alpha(theme.palette.info.main, 0.1), borderRadius: 1 }}>
                  <Typography variant="caption" color="textSecondary">Initiations</Typography>
                  <Typography variant="h5" sx={{ fontWeight: 'bold', color: theme.palette.info.main }}>
                    {momentum.initiations || 0}
                  </Typography>
                </Box>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <Box sx={{ p: 1.5, bgcolor: alpha(theme.palette.warning.main, 0.1), borderRadius: 1 }}>
                  <Typography variant="caption" color="textSecondary">Maintained</Typography>
                  <Typography variant="h5" sx={{ fontWeight: 'bold', color: theme.palette.warning.main }}>
                    {momentum.maintained || 0}
                  </Typography>
                </Box>
              </Grid>
            </Grid>
          </CardContent>
        </Card>
      )}

      {/* EPS Revisions */}
      {epsRevisions && (
        <Card variant="outlined">
          <CardContent>
            <Typography variant="h6" gutterBottom>EPS Revisions & Estimates</Typography>
            {Array.isArray(epsRevisions) ? (
              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Period</TableCell>
                      <TableCell align="center">Current Estimate</TableCell>
                      <TableCell align="center">7-Day Change</TableCell>
                      <TableCell align="center">30-Day Change</TableCell>
                      <TableCell align="center">Count</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {epsRevisions.slice(0, 5).map((item, idx) => (
                      <TableRow key={idx}>
                        <TableCell>{item.period || item.fiscal_period || 'N/A'}</TableCell>
                        <TableCell align="center">${item.current_estimate || item.estimate || 0}</TableCell>
                        <TableCell align="center">
                          <Chip
                            label={`${item.seven_day_change || 0 > 0 ? '+' : ''}${item.seven_day_change || 0}%`}
                            size="small"
                            color={item.seven_day_change > 0 ? 'success' : 'error'}
                            variant={item.seven_day_change ? 'filled' : 'outlined'}
                          />
                        </TableCell>
                        <TableCell align="center">
                          <Chip
                            label={`${item.thirty_day_change || 0 > 0 ? '+' : ''}${item.thirty_day_change || 0}%`}
                            size="small"
                            color={item.thirty_day_change > 0 ? 'success' : 'error'}
                            variant={item.thirty_day_change ? 'filled' : 'outlined'}
                          />
                        </TableCell>
                        <TableCell align="center">{item.estimate_count || 0}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            ) : (
              <Typography variant="body2" color="textSecondary">No EPS revision data available</Typography>
            )}
          </CardContent>
        </Card>
      )}

      {!sentimentTrend && !momentum && !epsRevisions && !loading && (
        <Alert severity="info">No comprehensive analyst metrics available for {symbol}</Alert>
      )}
    </Box>
  );
};

// Comprehensive Social Sentiment Component
const ComprehensiveSocialSentiment = ({ symbol }) => {
  const [socialData, setSocialData] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState(null);

  React.useEffect(() => {
    const fetchSocialData = async () => {
      try {
        setLoading(true);
        setError(null);

        // Fetch sentiment analysis data which includes social metrics
        const response = await fetch(`${API_BASE}/api/sentiment/analysis?symbol=${symbol}`);
        if (response.ok) {
          const data = await response.json();
          setSocialData(data?.data || data);
        }
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    if (symbol) {
      fetchSocialData();
    }
  }, [symbol]);

  if (loading) {
    return (
      <Card variant="outlined">
        <CardContent>
          <CircularProgress size={24} sx={{ mr: 1 }} />
          <Typography variant="body2" color="textSecondary">Loading social sentiment data...</Typography>
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card variant="outlined">
        <CardContent>
          <Typography variant="body2" color="error">Error loading social data: {error}</Typography>
        </CardContent>
      </Card>
    );
  }

  return (
    <Box>
      {socialData && Array.isArray(socialData) ? (
        <Card variant="outlined">
          <CardContent>
            <Typography variant="h6" gutterBottom>Social Media & Alternative Data Sentiment</Typography>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Date</TableCell>
                    <TableCell>Source</TableCell>
                    <TableCell align="center">Sentiment Score</TableCell>
                    <TableCell align="center">Positive</TableCell>
                    <TableCell align="center">Neutral</TableCell>
                    <TableCell align="center">Negative</TableCell>
                    <TableCell align="center">Total Volume</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {socialData.slice(0, 15).map((item, idx) => (
                    <TableRow key={idx}>
                      <TableCell>{new Date(item.date || item.timestamp).toLocaleDateString()}</TableCell>
                      <TableCell>
                        <Chip
                          label={item.source || 'Social'}
                          size="small"
                          variant="outlined"
                        />
                      </TableCell>
                      <TableCell align="center">
                        <Chip
                          label={item.sentiment_score?.toFixed(2) || 'N/A'}
                          size="small"
                          color={item.sentiment_score > 0.2 ? 'success' : item.sentiment_score < -0.2 ? 'error' : 'warning'}
                        />
                      </TableCell>
                      <TableCell align="center">
                        <Chip label={item.positive_mentions || 0} size="small" color="success" variant="outlined" />
                      </TableCell>
                      <TableCell align="center">
                        <Chip label={item.neutral_mentions || 0} size="small" variant="outlined" />
                      </TableCell>
                      <TableCell align="center">
                        <Chip label={item.negative_mentions || 0} size="small" color="error" variant="outlined" />
                      </TableCell>
                      <TableCell align="center">{item.total_mentions || 0}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </CardContent>
        </Card>
      ) : (
        <Alert severity="info">No social sentiment data available for {symbol}</Alert>
      )}
    </Box>
  );
};

// Analyst Trend Card Component - Metrics-focused display
const AnalystTrendCard = ({ symbol }) => {
  const theme = useTheme();
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState(null);
  const [insightsData, setInsightsData] = React.useState(null);
  const [epsRevisions, setEpsRevisions] = React.useState(null);
  const [sentimentTrend, setSentimentTrend] = React.useState(null);
  const [analystMomentum, setAnalystMomentum] = React.useState(null);

  // Fetch comprehensive analyst data from all endpoints
  React.useEffect(() => {
    const fetchAllAnalystData = async () => {
      try {
        setLoading(true);
        setError(null);

        // Fetch from all endpoints in parallel
        const [insightsRes, epsRes, trendRes, momentumRes] = await Promise.all([
          fetch(`${API_BASE}/api/sentiment/analyst/insights/${symbol}`).catch(() => null),
          fetch(`${API_BASE}/api/analysts/${symbol}/eps-revisions`).catch(() => null),
          fetch(`${API_BASE}/api/analysts/${symbol}/sentiment-trend`).catch(() => null),
          fetch(`${API_BASE}/api/analysts/${symbol}/analyst-momentum`).catch(() => null),
        ]);

        // Process insights data
        if (insightsRes?.ok) {
          const insights = await insightsRes.json();
          setInsightsData(insights);
        }

        // Process EPS revisions
        if (epsRes?.ok) {
          const eps = await epsRes.json();
          setEpsRevisions(eps);
        }

        // Process sentiment trend
        if (trendRes?.ok) {
          const trend = await trendRes.json();
          setSentimentTrend(trend);
        }

        // Process analyst momentum
        if (momentumRes?.ok) {
          const momentum = await momentumRes.json();
          setAnalystMomentum(momentum);
        }
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    if (symbol) {
      fetchAllAnalystData();
    }
  }, [symbol]);

  // Use metrics directly from the endpoint response
  const data = insightsData;
  const metrics = data?.metrics || null;
  const momentum = data?.momentum || null;
  const priceTargets = data?.priceTargets || [];
  const coverage = data?.coverage || null;
  const recentUpgrades = data?.recentUpgrades || [];

  if (loading) {
    return (
      <Card variant="outlined">
        <CardContent>
          <Box display="flex" alignItems="center" gap={1} mb={2}>
            <TrendingUpRounded />
            <Typography variant="h6">Analyst Sentiment & Price Targets</Typography>
          </Box>
          <CircularProgress size={24} sx={{ mr: 1 }} />
          <Typography variant="body2" color="textSecondary">Loading comprehensive analyst data...</Typography>
        </CardContent>
      </Card>
    );
  }

  if (error || !data) {
    return (
      <Card variant="outlined">
        <CardContent>
          <Box display="flex" alignItems="center" gap={1} mb={2}>
            <TrendingUpRounded />
            <Typography variant="h6">Analyst Sentiment & Price Targets</Typography>
          </Box>
          <Typography variant="body2" color="textSecondary">
            {error ? `Error: ${error}` : `No analyst data available for ${symbol}`}
          </Typography>
        </CardContent>
      </Card>
    );
  }

  // Clean metrics-focused display for hedge fund quality analysis
  return (
    <Card variant="outlined">
      <CardContent>
        {/* Header */}
        <Box display="flex" alignItems="center" gap={1} mb={3}>
          <TrendingUpRounded />
          <Typography variant="h6">Analyst Sentiment & Metrics</Typography>
        </Box>

        {/* Metrics Grid - Professional Hedge Fund Display */}
        {metrics && (
          <Grid container spacing={2} sx={{ mb: 3 }}>
            {/* Bullish Distribution */}
            <Grid item xs={12} sm={6} md={2}>
              <Box sx={{
                p: 2,
                bgcolor: alpha(theme.palette.success.main, 0.08),
                borderRadius: 1,
                border: `1px solid ${alpha(theme.palette.success.main, 0.2)}`
              }}>
                <Typography variant="overline" color="textSecondary" display="block" sx={{ mb: 0.5 }}>
                  Bullish
                </Typography>
                <Typography variant="h5" sx={{ fontWeight: "bold", color: theme.palette.success.main, mb: 0.5 }}>
                  {metrics.bullishPercent}%
                </Typography>
                <Typography variant="caption" color="textSecondary">
                  {metrics.bullish} analysts
                </Typography>
              </Box>
            </Grid>

            {/* Neutral Distribution */}
            <Grid item xs={12} sm={6} md={2}>
              <Box sx={{
                p: 2,
                bgcolor: alpha(theme.palette.info.main, 0.08),
                borderRadius: 1,
                border: `1px solid ${alpha(theme.palette.info.main, 0.2)}`
              }}>
                <Typography variant="overline" color="textSecondary" display="block" sx={{ mb: 0.5 }}>
                  Neutral
                </Typography>
                <Typography variant="h5" sx={{ fontWeight: "bold", color: theme.palette.info.main, mb: 0.5 }}>
                  {metrics.neutralPercent}%
                </Typography>
                <Typography variant="caption" color="textSecondary">
                  {metrics.neutral} analysts
                </Typography>
              </Box>
            </Grid>

            {/* Bearish Distribution */}
            <Grid item xs={12} sm={6} md={2}>
              <Box sx={{
                p: 2,
                bgcolor: alpha(theme.palette.error.main, 0.08),
                borderRadius: 1,
                border: `1px solid ${alpha(theme.palette.error.main, 0.2)}`
              }}>
                <Typography variant="overline" color="textSecondary" display="block" sx={{ mb: 0.5 }}>
                  Bearish
                </Typography>
                <Typography variant="h5" sx={{ fontWeight: "bold", color: theme.palette.error.main, mb: 0.5 }}>
                  {metrics.bearishPercent}%
                </Typography>
                <Typography variant="caption" color="textSecondary">
                  {metrics.bearish} analysts
                </Typography>
              </Box>
            </Grid>

            {/* Total Analysts */}
            <Grid item xs={12} sm={6} md={2}>
              <Box sx={{
                p: 2,
                bgcolor: alpha(theme.palette.primary.main, 0.08),
                borderRadius: 1,
                border: `1px solid ${alpha(theme.palette.primary.main, 0.2)}`
              }}>
                <Typography variant="overline" color="textSecondary" display="block" sx={{ mb: 0.5 }}>
                  Coverage
                </Typography>
                <Typography variant="h5" sx={{ fontWeight: "bold", mb: 0.5 }}>
                  {metrics.totalAnalysts}
                </Typography>
                <Typography variant="caption" color="textSecondary">
                  analysts covering
                </Typography>
              </Box>
            </Grid>

            {/* Price Target Metrics */}
            {metrics.avgPriceTarget && (
              <>
                <Grid item xs={12} sm={6} md={2}>
                  <Box sx={{
                    p: 2,
                    bgcolor: alpha(theme.palette.warning.main, 0.08),
                    borderRadius: 1,
                    border: `1px solid ${alpha(theme.palette.warning.main, 0.2)}`
                  }}>
                    <Typography variant="overline" color="textSecondary" display="block" sx={{ mb: 0.5 }}>
                      Avg Price Target
                    </Typography>
                    <Typography variant="h5" sx={{ fontWeight: "bold", mb: 0.5 }}>
                      ${typeof metrics.avgPriceTarget === 'number' ? metrics.avgPriceTarget.toFixed(2) : parseFloat(metrics.avgPriceTarget || 0).toFixed(2)}
                    </Typography>
                    <Typography variant="caption" color="textSecondary">
                      consensus target
                    </Typography>
                  </Box>
                </Grid>

                {/* Upside/Downside Potential */}
                {metrics.priceTargetVsCurrent !== null && (
                  <Grid item xs={12} sm={6} md={2}>
                    <Box sx={{
                      p: 2,
                      bgcolor: alpha(
                        metrics.priceTargetVsCurrent > 0 ? theme.palette.success.main : theme.palette.error.main,
                        0.08
                      ),
                      borderRadius: 1,
                      border: `1px solid ${alpha(
                        metrics.priceTargetVsCurrent > 0 ? theme.palette.success.main : theme.palette.error.main,
                        0.2
                      )}`
                    }}>
                      <Typography variant="overline" color="textSecondary" display="block" sx={{ mb: 0.5 }}>
                        Upside/Downside
                      </Typography>
                      <Typography variant="h5" sx={{
                        fontWeight: "bold",
                        color: metrics.priceTargetVsCurrent > 0 ? theme.palette.success.main : theme.palette.error.main,
                        mb: 0.5
                      }}>
                        {metrics.priceTargetVsCurrent > 0 ? "+" : ""}{typeof metrics.priceTargetVsCurrent === 'number' ? metrics.priceTargetVsCurrent.toFixed(1) : parseFloat(metrics.priceTargetVsCurrent || 0).toFixed(1)}%
                      </Typography>
                      <Typography variant="caption" color="textSecondary">
                        vs current price
                      </Typography>
                    </Box>
                  </Grid>
                )}

                {/* Coverage Firms Count */}
                {insightsData && insightsData.coverage && (
                  <Grid item xs={12} sm={6} md={2}>
                    <Box sx={{
                      p: 2,
                      bgcolor: alpha(theme.palette.secondary.main, 0.08),
                      borderRadius: 1,
                      border: `1px solid ${alpha(theme.palette.secondary.main, 0.2)}`
                    }}>
                      <Typography variant="overline" color="textSecondary" display="block" sx={{ mb: 0.5 }}>
                        Analyst Firms
                      </Typography>
                      <Typography variant="h5" sx={{ fontWeight: "bold", color: theme.palette.secondary.main, mb: 0.5 }}>
                        {insightsData.coverage.totalFirms || 0}
                      </Typography>
                      <Typography variant="caption" color="textSecondary">
                        firms covering
                      </Typography>
                    </Box>
                  </Grid>
                )}

                {/* Recommendation Distribution Summary */}
                {metrics && (
                  <Grid item xs={12} sm={6} md={2}>
                    <Box sx={{
                      p: 2,
                      bgcolor: alpha(theme.palette.primary.main, 0.04),
                      borderRadius: 1,
                      border: `1px solid ${alpha(theme.palette.primary.main, 0.15)}`
                    }}>
                      <Typography variant="overline" color="textSecondary" display="block" sx={{ mb: 1 }}>
                        Distribution
                      </Typography>
                      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <Typography variant="caption">Bull</Typography>
                          <Typography variant="caption" sx={{ fontWeight: 'bold', color: theme.palette.success.main }}>
                            {metrics.bullish}/{metrics.totalAnalysts}
                          </Typography>
                        </Box>
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <Typography variant="caption">Neutral</Typography>
                          <Typography variant="caption" sx={{ fontWeight: 'bold', color: theme.palette.info.main }}>
                            {metrics.neutral}/{metrics.totalAnalysts}
                          </Typography>
                        </Box>
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <Typography variant="caption">Bear</Typography>
                          <Typography variant="caption" sx={{ fontWeight: 'bold', color: theme.palette.error.main }}>
                            {metrics.bearish}/{metrics.totalAnalysts}
                          </Typography>
                        </Box>
                      </Box>
                    </Box>
                  </Grid>
                )}
              </>
            )}
          </Grid>
        )}

        {/* 30-Day Momentum */}
        {momentum && (
          <Box sx={{
            p: 2,
            bgcolor: alpha(theme.palette.grey[500], 0.05),
            borderRadius: 1,
            border: `1px solid ${theme.palette.divider}`,
            mb: 2
          }}>
            <Typography variant="overline" color="textSecondary" display="block" sx={{ mb: 1 }}>
              30-Day Analyst Actions
            </Typography>
            <Box display="flex" gap={3}>
              <Box>
                <Typography variant="body2" color="textSecondary" sx={{ mb: 0.5 }}>
                  Upgrades
                </Typography>
                <Typography variant="h6" sx={{ fontWeight: "bold", color: theme.palette.success.main }}>
                  {momentum.upgrades30d}
                </Typography>
              </Box>
              <Box>
                <Typography variant="body2" color="textSecondary" sx={{ mb: 0.5 }}>
                  Downgrades
                </Typography>
                <Typography variant="h6" sx={{ fontWeight: "bold", color: theme.palette.error.main }}>
                  {momentum.downgrades30d}
                </Typography>
              </Box>
              <Box ml="auto">
                <Typography variant="body2" color="textSecondary" sx={{ mb: 0.5 }}>
                  Net Momentum
                </Typography>
                <Chip
                  label={`${momentum.upgrades30d - momentum.downgrades30d > 0 ? "+" : ""}${momentum.upgrades30d - momentum.downgrades30d}`}
                  color={momentum.upgrades30d > momentum.downgrades30d ? "success" : momentum.upgrades30d < momentum.downgrades30d ? "error" : "default"}
                  variant="outlined"
                  sx={{ fontWeight: "bold" }}
                />
              </Box>
            </Box>
          </Box>
        )}

        {/* Price Targets */}
        {priceTargets && priceTargets.length > 0 && (
          <>
            <Divider sx={{ my: 2 }} />
            <Typography variant="h6" gutterBottom sx={{ mt: 3 }}>
              Price Targets by Firm
            </Typography>
            <TableContainer component={Paper} variant="outlined">
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Firm</TableCell>
                    <TableCell align="center">Target Price</TableCell>
                    <TableCell align="center">Previous</TableCell>
                    <TableCell align="center">Change</TableCell>
                    <TableCell>Date</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {priceTargets.slice(0, 10).map((target, idx) => (
                    <TableRow key={idx}>
                      <TableCell>{target.analyst_firm}</TableCell>
                      <TableCell align="center">
                        <Chip label={`$${parseFloat(target.target_price).toFixed(2)}`} size="small" />
                      </TableCell>
                      <TableCell align="center">
                        <Typography variant="body2" color="textSecondary">
                          ${parseFloat(target.previous_target_price || 0).toFixed(2)}
                        </Typography>
                      </TableCell>
                      <TableCell align="center">
                        <Chip
                          label={`${(parseFloat(target.target_price) - parseFloat(target.previous_target_price || 0)).toFixed(2)}`}
                          size="small"
                          color={parseFloat(target.target_price) > parseFloat(target.previous_target_price || 0) ? 'success' : 'error'}
                          variant="outlined"
                        />
                      </TableCell>
                      <TableCell>
                        {new Date(target.target_date).toLocaleDateString()}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </>
        )}

        {/* Recent Analyst Actions */}
        {recentUpgrades && recentUpgrades.length > 0 && (
          <>
            <Divider sx={{ my: 2 }} />
            <Typography variant="h6" gutterBottom sx={{ mt: 3 }}>
              Recent Analyst Actions
            </Typography>
            <TableContainer component={Paper} variant="outlined">
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Firm</TableCell>
                    <TableCell align="center">Action</TableCell>
                    <TableCell>From Grade</TableCell>
                    <TableCell>To Grade</TableCell>
                    <TableCell>Details</TableCell>
                    <TableCell>Date</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {recentUpgrades.slice(0, 8).map((upgrade, idx) => (
                    <TableRow key={idx}>
                      <TableCell>{upgrade.firm}</TableCell>
                      <TableCell align="center">
                        <Chip
                          label={upgrade.action === 'up' ? '↑' : upgrade.action === 'down' ? '↓' : '→'}
                          size="small"
                          color={upgrade.action === 'up' ? 'success' : upgrade.action === 'down' ? 'error' : 'default'}
                          variant="outlined"
                        />
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2">{upgrade.from_grade || '-'}</Typography>
                      </TableCell>
                      <TableCell>
                        <Chip label={upgrade.to_grade} size="small" />
                      </TableCell>
                      <TableCell>
                        <Typography variant="caption">{upgrade.details}</Typography>
                      </TableCell>
                      <TableCell>
                        {new Date(upgrade.date).toLocaleDateString()}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </>
        )}

        {/* Analyst Coverage */}
        {coverage && coverage.firms && coverage.firms.length > 0 && (
          <>
            <Divider sx={{ my: 2 }} />
            <Typography variant="h6" gutterBottom sx={{ mt: 3 }}>
              Analyst Coverage ({coverage.totalFirms} firms)
            </Typography>
            <Grid container spacing={2}>
              {coverage.firms.slice(0, 6).map((firm, idx) => (
                <Grid item xs={12} sm={6} md={4} key={idx}>
                  <Box sx={{ p: 2, bgcolor: alpha(theme.palette.primary.main, 0.05), borderRadius: 1 }}>
                    <Typography variant="subtitle2" fontWeight="bold">{firm.analyst_firm}</Typography>
                    <Typography variant="caption" color="textSecondary">
                      Analyst: {firm.analyst_name}
                    </Typography>
                    <Typography variant="caption" display="block" sx={{ mt: 0.5 }}>
                      <Chip label={firm.coverage_status} size="small" variant="outlined" />
                    </Typography>
                    <Typography variant="caption" color="textSecondary" sx={{ mt: 1, display: 'block' }}>
                      Since: {new Date(firm.coverage_started).toLocaleDateString()}
                    </Typography>
                  </Box>
                </Grid>
              ))}
            </Grid>
          </>
        )}

        {/* EPS Revisions */}
        {epsRevisions && (
          <>
            <Divider sx={{ my: 2 }} />
            <Typography variant="h6" gutterBottom sx={{ mt: 3 }}>
              EPS Revisions & Estimates
            </Typography>
            {epsRevisions.data ? (
              <TableContainer component={Paper} variant="outlined">
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Period</TableCell>
                      <TableCell align="center">Current Estimate</TableCell>
                      <TableCell align="center">7-Day Change</TableCell>
                      <TableCell align="center">30-Day Change</TableCell>
                      <TableCell align="center">Analyst Count</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {(epsRevisions.data || []).slice(0, 8).map((item, idx) => (
                      <TableRow key={idx}>
                        <TableCell>{item.period || item.fiscal_period || 'N/A'}</TableCell>
                        <TableCell align="center">
                          ${parseFloat(item.current_estimate || item.estimate || 0).toFixed(2)}
                        </TableCell>
                        <TableCell align="center">
                          <Chip
                            label={`${item.seven_day_change > 0 ? '+' : ''}${(item.seven_day_change || 0).toFixed(1)}%`}
                            size="small"
                            color={item.seven_day_change > 0 ? 'success' : item.seven_day_change < 0 ? 'error' : 'default'}
                            variant="outlined"
                          />
                        </TableCell>
                        <TableCell align="center">
                          <Chip
                            label={`${item.thirty_day_change > 0 ? '+' : ''}${(item.thirty_day_change || 0).toFixed(1)}%`}
                            size="small"
                            color={item.thirty_day_change > 0 ? 'success' : item.thirty_day_change < 0 ? 'error' : 'default'}
                            variant="outlined"
                          />
                        </TableCell>
                        <TableCell align="center">{item.estimate_count || item.analyst_count || 0}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            ) : (
              <Typography variant="body2" color="textSecondary">No EPS revision data available</Typography>
            )}
          </>
        )}

        {/* Sentiment Trend */}
        {sentimentTrend && sentimentTrend.chartData && (
          <>
            <Divider sx={{ my: 2 }} />
            <Typography variant="h6" gutterBottom sx={{ mt: 3 }}>
              Analyst Sentiment Trend (90 Days)
            </Typography>
            <TableContainer component={Paper} variant="outlined">
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Date</TableCell>
                    <TableCell align="center">Avg Rating</TableCell>
                    <TableCell align="center">Strong Buy</TableCell>
                    <TableCell align="center">Buy</TableCell>
                    <TableCell align="center">Hold</TableCell>
                    <TableCell align="center">Sell</TableCell>
                    <TableCell align="center">Strong Sell</TableCell>
                    <TableCell align="center">Analysts</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {sentimentTrend.chartData.slice(0, 20).map((item, idx) => (
                    <TableRow key={idx}>
                      <TableCell>{new Date(item.date).toLocaleDateString()}</TableCell>
                      <TableCell align="center">{item.ratingMean != null ? item.ratingMean.toFixed(2) : 'N/A'}</TableCell>
                      <TableCell align="center">{item.strongBuy}</TableCell>
                      <TableCell align="center">{item.buy}</TableCell>
                      <TableCell align="center">{item.hold}</TableCell>
                      <TableCell align="center">{item.sell}</TableCell>
                      <TableCell align="center">{item.strongSell}</TableCell>
                      <TableCell align="center">{item.totalAnalysts}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>

            {/* Trend Summary */}
            {sentimentTrend.trends && (
              <Box sx={{ mt: 3, p: 2, bgcolor: alpha(theme.palette.info.main, 0.05), borderRadius: 1 }}>
                <Grid container spacing={2}>
                  <Grid item xs={12} sm={6} md={3}>
                    <Typography variant="caption" color="textSecondary">Sentiment Trend</Typography>
                    <Typography variant="subtitle2">{sentimentTrend.trends.sentimentTrend?.interpretation || 'N/A'}</Typography>
                  </Grid>
                  <Grid item xs={12} sm={6} md={3}>
                    <Typography variant="caption" color="textSecondary">Rating Momentum</Typography>
                    <Typography variant="subtitle2">{sentimentTrend.trends.ratingMomentum?.velocity || 'N/A'}</Typography>
                  </Grid>
                  <Grid item xs={12} sm={6} md={3}>
                    <Typography variant="caption" color="textSecondary">Coverage Trend</Typography>
                    <Typography variant="subtitle2">{sentimentTrend.trends.analystCoverageTrend?.interpretation || 'N/A'}</Typography>
                  </Grid>
                  <Grid item xs={12} sm={6} md={3}>
                    <Typography variant="caption" color="textSecondary">Current Momentum</Typography>
                    <Chip
                      label={sentimentTrend.trends.ratingMomentum?.momentum || 'N/A'}
                      size="small"
                      color={sentimentTrend.trends.ratingMomentum?.momentum === 'Strong' ? 'success' : 'default'}
                    />
                  </Grid>
                </Grid>
              </Box>
            )}
          </>
        )}

        {/* Analyst Momentum */}
        {analystMomentum && analystMomentum.summary && (
          <>
            <Divider sx={{ my: 2 }} />
            <Typography variant="h6" gutterBottom sx={{ mt: 3 }}>
              Analyst Momentum & Activity
            </Typography>
            <Grid container spacing={2}>
              <Grid item xs={12} sm={6} md={3}>
                <Box sx={{ p: 2, bgcolor: alpha(theme.palette.success.main, 0.1), borderRadius: 1, textAlign: 'center' }}>
                  <Typography variant="caption" color="textSecondary">Recent Upgrades</Typography>
                  <Typography variant="h5" sx={{ color: theme.palette.success.main, fontWeight: 'bold' }}>
                    {analystMomentum.summary.recentUpgrades || 0}
                  </Typography>
                </Box>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <Box sx={{ p: 2, bgcolor: alpha(theme.palette.error.main, 0.1), borderRadius: 1, textAlign: 'center' }}>
                  <Typography variant="caption" color="textSecondary">Recent Downgrades</Typography>
                  <Typography variant="h5" sx={{ color: theme.palette.error.main, fontWeight: 'bold' }}>
                    {analystMomentum.summary.recentDowngrades || 0}
                  </Typography>
                </Box>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <Box sx={{ p: 2, bgcolor: alpha(theme.palette.warning.main, 0.1), borderRadius: 1, textAlign: 'center' }}>
                  <Typography variant="caption" color="textSecondary">Net Momentum</Typography>
                  <Typography variant="h5" sx={{ color: theme.palette.warning.main, fontWeight: 'bold' }}>
                    {((analystMomentum.summary.recentUpgrades || 0) - (analystMomentum.summary.recentDowngrades || 0)) > 0 ? '+' : ''}{(analystMomentum.summary.recentUpgrades || 0) - (analystMomentum.summary.recentDowngrades || 0)}
                  </Typography>
                </Box>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <Box sx={{ p: 2, bgcolor: alpha(theme.palette.info.main, 0.1), borderRadius: 1, textAlign: 'center' }}>
                  <Typography variant="caption" color="textSecondary">Momentum Status</Typography>
                  <Typography variant="subtitle2">{analystMomentum.summary.momentumStatus || 'N/A'}</Typography>
                </Box>
              </Grid>
            </Grid>
          </>
        )}

        {/* No data message */}
        {!metrics && !momentum && !priceTargets && !recentUpgrades && !epsRevisions && !sentimentTrend && (
          <Typography variant="body2" color="textSecondary">
            No comprehensive analyst sentiment data available for this stock
          </Typography>
        )}
      </CardContent>
    </Card>
  );
};

function Sentiment() {
  const [expandedSymbol, setExpandedSymbol] = useState(null);
  const [searchFilter, setSearchFilter] = useState("");
  const [sortBy, setSortBy] = useState("composite");
  const [filterSentiment, setFilterSentiment] = useState("all");

  // Analyst upgrades/downgrades state
  const [upgrades, setUpgrades] = useState([]);
  const [upgradesLoading, setUpgradesLoading] = useState(false);
  const [upgradesError, setUpgradesError] = useState(null);
  const [searchSymbol, setSearchSymbol] = useState("");
  const [tablePage, setTablePage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);

  // Fetch all sentiment data
  const { data: sentimentData, isLoading, error } = useQuery({
    queryKey: ["sentimentStocks"],
    queryFn: async () => {
      const response = await fetch(`${API_BASE}/api/sentiment/stocks`);
      if (!response.ok) throw new Error("Failed to fetch sentiment");
      return response.json();
    },
    staleTime: 300000, // 5 minutes
    refetchInterval: 300000,
  });

  // Parse sentiment data
  const rawData = sentimentData?.data || [];

  // Fetch analyst upgrades/downgrades
  useEffect(() => {
    const fetchAnalystUpgrades = async () => {
      try {
        setUpgradesLoading(true);
        const response = await fetch(`${API_BASE}/api/analysts/upgrades?limit=100`);
        if (!response.ok) throw new Error("Failed to fetch analyst upgrades");
        const data = await response.json();
        if (data?.data) {
          setUpgrades(data.data);
        }
      } catch (err) {
        console.error("Error fetching analyst upgrades:", err);
        setUpgradesError("Failed to load analyst upgrades");
      } finally {
        setUpgradesLoading(false);
      }
    };

    fetchAnalystUpgrades();
  }, []);

  // Helper functions for analyst upgrades
  const getActionIcon = (action, fromGrade, toGrade) => {
    if (!action) return <ShowChartIcon />;

    const actionLower = action.toLowerCase();

    // Check action field first
    if (actionLower === "up" || actionLower.includes("upgrade")) {
      return <TrendingUp sx={{ color: "success.main" }} />;
    } else if (actionLower === "down" || actionLower.includes("downgrade")) {
      return <TrendingDown sx={{ color: "error.main" }} />;
    }

    // Check grade changes if action is maintain/reit/init
    if (fromGrade && toGrade) {
      const bullishGrades = ["Buy", "Outperform", "Overweight", "Strong Buy"];
      const bearishGrades = ["Sell", "Underperform", "Underweight"];
      const gradeOrder = [
        "Strong Sell",
        "Sell",
        "Underweight",
        "Underperform",
        "Hold",
        "Neutral",
        "Equal-Weight",
        "Market Perform",
        "Sector Perform",
        "Peer Perform",
        "Perform",
        "Buy",
        "Outperform",
        "Overweight",
        "Strong Buy",
      ];
      const fromIndex = gradeOrder.findIndex((g) => fromGrade?.includes(g));
      const toIndex = gradeOrder.findIndex((g) => toGrade?.includes(g));

      // If grade changed, show upgrade/downgrade
      if (toIndex > fromIndex && fromIndex !== -1) {
        return <TrendingUp sx={{ color: "success.main" }} />;
      } else if (toIndex < fromIndex && toIndex !== -1) {
        return <TrendingDown sx={{ color: "error.main" }} />;
      }

      // If maintained/reiterated/initiated, check if grade is bullish or bearish
      const isBullish = bullishGrades.some((g) => toGrade?.includes(g));
      const isBearish = bearishGrades.some((g) => toGrade?.includes(g));

      if (isBullish) {
        return <TrendingUp sx={{ color: "success.main" }} />;
      } else if (isBearish) {
        return <TrendingDown sx={{ color: "error.main" }} />;
      }
    }

    return <ShowChartIcon sx={{ color: "info.main" }} />;
  };

  const getActionColor = (action, fromGrade, toGrade) => {
    if (!action) return "default";

    const actionLower = action.toLowerCase();

    // Check action field first
    if (actionLower === "up" || actionLower.includes("upgrade")) {
      return "success";
    } else if (actionLower === "down" || actionLower.includes("downgrade")) {
      return "error";
    }

    // Check grade changes if action is maintain/reit/init
    if (fromGrade && toGrade) {
      const bullishGrades = ["Buy", "Outperform", "Overweight", "Strong Buy"];
      const bearishGrades = ["Sell", "Underperform", "Underweight"];
      const gradeOrder = [
        "Strong Sell",
        "Sell",
        "Underweight",
        "Underperform",
        "Hold",
        "Neutral",
        "Equal-Weight",
        "Market Perform",
        "Sector Perform",
        "Peer Perform",
        "Perform",
        "Buy",
        "Outperform",
        "Overweight",
        "Strong Buy",
      ];
      const fromIndex = gradeOrder.findIndex((g) => fromGrade?.includes(g));
      const toIndex = gradeOrder.findIndex((g) => toGrade?.includes(g));

      // If grade changed, show upgrade/downgrade
      if (toIndex > fromIndex && fromIndex !== -1) {
        return "success";
      } else if (toIndex < fromIndex && toIndex !== -1) {
        return "error";
      }

      // If maintained/reiterated/initiated, check if grade is bullish or bearish
      const isBullish = bullishGrades.some((g) => toGrade?.includes(g));
      const isBearish = bearishGrades.some((g) => toGrade?.includes(g));

      if (isBullish) {
        return "success";
      } else if (isBearish) {
        return "error";
      }
    }

    return "info";
  };

  const formatDate = (dateString) => {
    if (!dateString) return "N/A";
    try {
      return new Date(dateString).toLocaleDateString();
    } catch {
      return dateString;
    }
  };

  const filteredUpgrades = upgrades.filter((upgrade) =>
    !searchSymbol || upgrade.symbol?.toLowerCase().includes(searchSymbol.toLowerCase())
  );

  // Group by symbol and calculate composite scores
  const groupedBySymbol = rawData.reduce((acc, item) => {
    const symbol = item.symbol;
    if (!acc[symbol]) {
      acc[symbol] = {
        symbol,
        news: [],
        social: [],
        analyst: [],
      };
    }

    // Group by source type - handle all source types
    const source = (item.source || "").toLowerCase();
    if (source === "analyst" || source.includes("analyst") || source.includes("rating")) {
      acc[symbol].analyst.push(item);
    } else if (source === "social" || source.includes("reddit") || source.includes("social") || source.includes("twitter")) {
      acc[symbol].social.push(item);
    } else if (source === "news" || source.includes("news") || source.includes("article") || source === "technical" || source.includes("technical")) {
      // Treat technical and news as the same (news category)
      acc[symbol].news.push(item);
    } else {
      // Default to social if source is unclear
      acc[symbol].social.push(item);
    }

    return acc;
  }, {});

  // Convert to array and calculate composite scores
  const stocksList = Object.values(groupedBySymbol).map(stock => {
    const latestNews = stock.news[0];
    const latestSocial = stock.social[0];
    const latestAnalyst = stock.analyst[0];

    const compositeScore = calculateCompositeSentiment(
      latestNews?.sentiment_score,
      latestAnalyst?.sentiment_score,
      latestSocial?.sentiment_score
    );

    return {
      symbol: stock.symbol,
      compositeScore,
      compositeSentiment: getSentimentLabel(compositeScore),
      news: stock.news,
      social: stock.social,
      analyst: stock.analyst,
      latestNews,
      latestSocial,
      latestAnalyst,
      allData: [...stock.news, ...stock.social, ...stock.analyst].sort((a, b) =>
        new Date(b.date) - new Date(a.date)
      ),
    };
  });

  // Enhanced filtering and sorting with divergence detection
  const filteredAndSortedStocks = useMemo(() => {
    let stocks = stocksList
      .map(stock => ({
        ...stock,
        divergence: detectSentimentDivergence(
          stock.latestNews?.sentiment_score,
          stock.latestAnalyst?.sentiment_score,
          stock.latestSocial?.sentiment_score
        ),
      }))
      .filter(stock => {
        const matchesSearch = stock.symbol.toLowerCase().includes(searchFilter.toLowerCase());

        if (filterSentiment === "all") return matchesSearch;
        if (filterSentiment === "bullish") return matchesSearch && stock.compositeScore > 0.3;
        if (filterSentiment === "bearish") return matchesSearch && stock.compositeScore < -0.3;
        if (filterSentiment === "neutral") return matchesSearch && stock.compositeScore >= -0.3 && stock.compositeScore <= 0.3;

        return matchesSearch;
      });

    // Sort based on selected criteria
    stocks.sort((a, b) => {
      switch (sortBy) {
        case "composite":
          return (b.compositeScore || -999) - (a.compositeScore || -999);
        case "news":
          return (b.latestNews?.sentiment_score || -999) - (a.latestNews?.sentiment_score || -999);
        case "analyst":
          return (b.latestAnalyst?.sentiment_score || -999) - (a.latestAnalyst?.sentiment_score || -999);
        case "social":
          return (b.latestSocial?.sentiment_score || -999) - (a.latestSocial?.sentiment_score || -999);
        case "symbol":
          return a.symbol.localeCompare(b.symbol);
        default:
          return 0;
      }
    });

    return stocks;
  }, [stocksList, searchFilter, sortBy, filterSentiment]);

  const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042'];

  // Handle accordion toggle
  const handleAccordionToggle = (symbol) => {
    setExpandedSymbol(expandedSymbol === symbol ? null : symbol);
  };

  return (
    <Container maxWidth="xl" sx={{ py: 3 }}>
      {/* Header */}
      <Box sx={{ mb: 3 }}>
        <Box display="flex" alignItems="center" gap={2}>
          <SentimentSatisfiedAlt sx={{ fontSize: 40, color: "primary.main" }} />
          <Typography variant="h4" component="h1">
            Sentiment Analysis
          </Typography>
        </Box>
        <Typography variant="subtitle1" color="textSecondary" sx={{ mt: 1 }}>
          Individual stock analyst sentiment analysis and ratings trends
        </Typography>
      </Box>

      {/* Section 1: Stock Details - Middle Section */}
      <Box sx={{ mb: 4 }}>
        {/* Search and Filter Bar */}
        <Card sx={{ mb: 3 }}>
          <CardContent>
            <Grid container spacing={2} alignItems="flex-end">
              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  label="Search Symbols"
                  placeholder="Filter by symbol (e.g., AAPL, GOOGL)"
                  value={searchFilter}
                  onChange={(e) => setSearchFilter(e.target.value)}
                  InputProps={{
                    startAdornment: (
                      <InputAdornment position="start">
                        <Search />
                      </InputAdornment>
                    ),
                  }}
                />
              </Grid>
              <Grid item xs={12} sm={3}>
                <FormControl fullWidth size="small">
                  <InputLabel>Sentiment</InputLabel>
                  <Select
                    value={filterSentiment}
                    onChange={(e) => setFilterSentiment(e.target.value)}
                    label="Sentiment"
                  >
                    <MenuItem value="all">All</MenuItem>
                    <MenuItem value="bullish">Bullish</MenuItem>
                    <MenuItem value="neutral">Neutral</MenuItem>
                    <MenuItem value="bearish">Bearish</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
              <Grid item xs={12} sm={3}>
                <FormControl fullWidth size="small">
                  <InputLabel>Sort By</InputLabel>
                  <Select
                    value={sortBy}
                    onChange={(e) => setSortBy(e.target.value)}
                    label="Sort By"
                  >
                    <MenuItem value="composite">Composite Score</MenuItem>
                    <MenuItem value="news">News Sentiment</MenuItem>
                    <MenuItem value="analyst">Analyst Rating</MenuItem>
                    <MenuItem value="social">Social Media</MenuItem>
                    <MenuItem value="symbol">Symbol A-Z</MenuItem>
                  </Select>
                </FormControl>
              </Grid>
            </Grid>
            {filteredAndSortedStocks.length > 0 && (
              <Typography variant="caption" color="textSecondary" sx={{ mt: 2, display: "block" }}>
                Showing {filteredAndSortedStocks.length} symbol{filteredAndSortedStocks.length !== 1 ? "s" : ""} with sentiment data
              </Typography>
            )}
          </CardContent>
        </Card>

        {/* Loading State */}
        {isLoading && (
          <Box display="flex" justifyContent="center" py={4}>
            <CircularProgress />
          </Box>
        )}

        {/* Error State */}
        {error && (
          <Alert severity="error" sx={{ mb: 3 }}>
            Failed to load sentiment data: {error.message}
          </Alert>
        )}

        {/* Accordion List - Stock Details */}
        {!isLoading && !error && (
          <>
            {filteredAndSortedStocks.length === 0 ? (
              <Alert severity="info">
                {searchFilter ? `No symbols match "${searchFilter}"` : "No sentiment data available"}
              </Alert>
            ) : (
              <Box>
                {filteredAndSortedStocks.map((stock) => {
                const componentData = [
                  { name: "News", value: stock.latestNews?.sentiment_score || 0, weight: 40 },
                  { name: "Analyst", value: stock.latestAnalyst?.sentiment_score || 0, weight: 35 },
                  { name: "Social", value: stock.latestSocial?.sentiment_score || 0, weight: 25 },
                ].filter(d => d.value !== 0);

                return (
                  <Accordion
                    key={stock.symbol}
                    expanded={expandedSymbol === stock.symbol}
                    onChange={() => handleAccordionToggle(stock.symbol)}
                    sx={{ mb: 1 }}
                  >
                    <AccordionSummary
                      expandIcon={<ExpandMore />}
                      sx={{
                        backgroundColor: "grey.50",
                        "&:hover": { backgroundColor: "grey.100" },
                        borderLeft: "none",
                      }}
                    >
                      <Grid container alignItems="center" spacing={2} sx={{ width: "100%" }}>
                        <Grid item xs={2}>
                          <Typography variant="h6" fontWeight="bold">
                            {stock.symbol}
                            {stock.divergence?.isDiverged && (
                              <InfoIcon
                                sx={{
                                  fontSize: 16,
                                  ml: 0.5,
                                  color: "warning.main",
                                  verticalAlign: "middle"
                                }}
                              />
                            )}
                          </Typography>
                        </Grid>
                        <Grid item xs={3}>
                          <Box display="flex" alignItems="center" gap={1}>
                            {stock.compositeSentiment.icon}
                            <Chip
                              label={stock.compositeSentiment.label}
                              color={stock.compositeSentiment.color}
                              size="small"
                            />
                          </Box>
                        </Grid>
                        <Grid item xs={2}>
                          <Typography variant="h6" fontWeight="bold">
                            {stock.compositeScore !== null ? stock.compositeScore.toFixed(2) : "N/A"}
                          </Typography>
                          <Typography variant="caption" color="textSecondary">
                            Composite Score
                          </Typography>
                        </Grid>
                        <Grid item xs={5}>
                          <Grid container spacing={1}>
                            <Grid item xs={4}>
                              <Box display="flex" alignItems="center" gap={0.5}>
                                <Newspaper fontSize="small" />
                                <Chip
                                  label={stock.latestNews?.sentiment_score?.toFixed(2) || "N/A"}
                                  size="small"
                                  color={stock.latestNews?.sentiment_score > 0.2 ? "success" : stock.latestNews?.sentiment_score < -0.2 ? "error" : "warning"}
                                />
                              </Box>
                            </Grid>
                            <Grid item xs={4}>
                              <Box display="flex" alignItems="center" gap={0.5}>
                                <TrendingUpRounded fontSize="small" />
                                <Chip
                                  label={stock.latestAnalyst?.sentiment_score?.toFixed(2) || "N/A"}
                                  size="small"
                                  color={stock.latestAnalyst?.sentiment_score > 0.2 ? "success" : stock.latestAnalyst?.sentiment_score < -0.2 ? "error" : "warning"}
                                />
                              </Box>
                            </Grid>
                            <Grid item xs={4}>
                              <Box display="flex" alignItems="center" gap={0.5}>
                                <Reddit fontSize="small" />
                                <Chip
                                  label={stock.latestSocial?.sentiment_score?.toFixed(2) || "N/A"}
                                  size="small"
                                  color={stock.latestSocial?.sentiment_score > 0.2 ? "success" : stock.latestSocial?.sentiment_score < -0.2 ? "error" : "warning"}
                                />
                              </Box>
                            </Grid>
                          </Grid>
                        </Grid>
                      </Grid>
                    </AccordionSummary>

                    <AccordionDetails>
                      <Grid container spacing={3}>
                        {/* Composite Score Card */}
                        <Grid item xs={12} md={4}>
                          <Card variant="outlined">
                            <CardContent>
                              <Typography variant="h6" gutterBottom>Composite Sentiment</Typography>
                              <Box display="flex" alignItems="center" justifyContent="space-between" mb={2}>
                                <Typography variant="h3" fontWeight="bold">
                                  {stock.compositeScore !== null ? stock.compositeScore.toFixed(2) : "N/A"}
                                </Typography>
                                <Chip
                                  label={stock.compositeSentiment.label}
                                  color={stock.compositeSentiment.color}
                                  icon={stock.compositeSentiment.icon}
                                  size="large"
                                />
                              </Box>
                              <Divider sx={{ my: 2 }} />
                              <Typography variant="caption" color="textSecondary">
                                Weighted average of news (40%), analyst ratings (35%), and social sentiment (25%)
                              </Typography>
                            </CardContent>
                          </Card>
                        </Grid>

                        {/* Component Breakdown */}
                        <Grid item xs={12} md={8}>
                          <Card variant="outlined">
                            <CardContent>
                              <Typography variant="h6" gutterBottom>Sentiment Component Breakdown</Typography>
                              <Grid container spacing={2}>
                                <Grid item xs={12} md={6}>
                                  {componentData.length > 0 ? (
                                    <ResponsiveContainer width="100%" height={200}>
                                      <PieChart>
                                        <Pie
                                          data={componentData}
                                          dataKey="weight"
                                          nameKey="name"
                                          cx="50%"
                                          cy="50%"
                                          outerRadius={70}
                                          label={({ name, weight }) => `${name} (${weight}%)`}
                                        >
                                          {componentData.map((entry, index) => (
                                            <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                                          ))}
                                        </Pie>
                                        <RechartsTooltip />
                                      </PieChart>
                                    </ResponsiveContainer>
                                  ) : (
                                    <Typography variant="body2" color="textSecondary">No component data available</Typography>
                                  )}
                                </Grid>
                                <Grid item xs={12} md={6}>
                                  <Box>
                                    <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
                                      <Box display="flex" alignItems="center" gap={1}>
                                        <Newspaper fontSize="small" />
                                        <Typography variant="body2">News Sentiment</Typography>
                                      </Box>
                                      <Chip
                                        label={stock.latestNews?.sentiment_score?.toFixed(2) || "N/A"}
                                        size="small"
                                        color={stock.latestNews?.sentiment_score > 0.2 ? "success" : stock.latestNews?.sentiment_score < -0.2 ? "error" : "warning"}
                                      />
                                    </Box>
                                    <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
                                      <Box display="flex" alignItems="center" gap={1}>
                                        <TrendingUpRounded fontSize="small" />
                                        <Typography variant="body2">Analyst Ratings</Typography>
                                      </Box>
                                      <Chip
                                        label={stock.latestAnalyst?.sentiment_score?.toFixed(2) || "N/A"}
                                        size="small"
                                        color={stock.latestAnalyst?.sentiment_score > 0.2 ? "success" : stock.latestAnalyst?.sentiment_score < -0.2 ? "error" : "warning"}
                                      />
                                    </Box>
                                    <Box display="flex" justifyContent="space-between" alignItems="center">
                                      <Box display="flex" alignItems="center" gap={1}>
                                        <Reddit fontSize="small" />
                                        <Typography variant="body2">Social Media</Typography>
                                      </Box>
                                      <Chip
                                        label={stock.latestSocial?.sentiment_score?.toFixed(2) || "N/A"}
                                        size="small"
                                        color={stock.latestSocial?.sentiment_score > 0.2 ? "success" : stock.latestSocial?.sentiment_score < -0.2 ? "error" : "warning"}
                                      />
                                    </Box>
                                  </Box>
                                </Grid>
                              </Grid>
                            </CardContent>
                          </Card>
                        </Grid>

                        {/* News Sentiment Details */}
                        {stock.news.length > 0 && (
                          <Grid item xs={12} md={4}>
                            <Card variant="outlined">
                              <CardContent>
                                <Box display="flex" alignItems="center" gap={1} mb={2}>
                                  <Newspaper />
                                  <Typography variant="h6">News Sentiment</Typography>
                                </Box>
                                <Box display="flex" justifyContent="space-between" mb={1}>
                                  <Typography variant="body2">Score:</Typography>
                                  <Typography variant="body2" fontWeight="600">
                                    {stock.latestNews?.sentiment_score?.toFixed(2) || "N/A"}
                                  </Typography>
                                </Box>
                                <Box display="flex" justifyContent="space-between" mb={1}>
                                  <Typography variant="body2">Positive:</Typography>
                                  <Chip label={stock.latestNews?.positive_mentions || 0} size="small" color="success" variant="outlined" />
                                </Box>
                                <Box display="flex" justifyContent="space-between" mb={1}>
                                  <Typography variant="body2">Neutral:</Typography>
                                  <Chip label={stock.latestNews?.neutral_mentions || 0} size="small" color="default" variant="outlined" />
                                </Box>
                                <Box display="flex" justifyContent="space-between" mb={1}>
                                  <Typography variant="body2">Negative:</Typography>
                                  <Chip label={stock.latestNews?.negative_mentions || 0} size="small" color="error" variant="outlined" />
                                </Box>
                                <Box display="flex" justifyContent="space-between">
                                  <Typography variant="body2">Total Articles:</Typography>
                                  <Typography variant="body2" fontWeight="600">{stock.latestNews?.total_mentions || 0}</Typography>
                                </Box>
                              </CardContent>
                            </Card>
                          </Grid>
                        )}

                        {/* Social Sentiment Details */}
                        {stock.social.length > 0 && (
                          <Grid item xs={12} md={4}>
                            <Card variant="outlined">
                              <CardContent>
                                <Box display="flex" alignItems="center" gap={1} mb={2}>
                                  <Reddit />
                                  <Typography variant="h6">Social Media</Typography>
                                </Box>
                                <Box display="flex" justifyContent="space-between" mb={1}>
                                  <Typography variant="body2">Score:</Typography>
                                  <Typography variant="body2" fontWeight="600">
                                    {stock.latestSocial?.sentiment_score?.toFixed(2) || "N/A"}
                                  </Typography>
                                </Box>
                                <Box display="flex" justifyContent="space-between" mb={1}>
                                  <Typography variant="body2">Positive:</Typography>
                                  <Chip label={stock.latestSocial?.positive_mentions || 0} size="small" color="success" variant="outlined" />
                                </Box>
                                <Box display="flex" justifyContent="space-between" mb={1}>
                                  <Typography variant="body2">Neutral:</Typography>
                                  <Chip label={stock.latestSocial?.neutral_mentions || 0} size="small" color="default" variant="outlined" />
                                </Box>
                                <Box display="flex" justifyContent="space-between" mb={1}>
                                  <Typography variant="body2">Negative:</Typography>
                                  <Chip label={stock.latestSocial?.negative_mentions || 0} size="small" color="error" variant="outlined" />
                                </Box>
                                <Box display="flex" justifyContent="space-between">
                                  <Typography variant="body2">Total Mentions:</Typography>
                                  <Typography variant="body2" fontWeight="600">{stock.latestSocial?.total_mentions || 0}</Typography>
                                </Box>
                              </CardContent>
                            </Card>
                          </Grid>
                        )}

                        {/* Analyst Sentiment Details with Trend */}
                        <Grid item xs={12} md={6}>
                          <AnalystTrendCard symbol={stock.symbol} />
                        </Grid>

                        {/* Historical Sentiment Table */}
                        <Grid item xs={12}>
                          <Card variant="outlined">
                            <CardContent>
                              <Typography variant="h6" mb={2}>Recent Sentiment Data</Typography>
                              <TableContainer component={Paper} variant="outlined">
                                <Table size="small">
                                  <TableHead>
                                    <TableRow>
                                      <TableCell>Date</TableCell>
                                      <TableCell>Source</TableCell>
                                      <TableCell align="center">Score</TableCell>
                                      <TableCell align="center">Positive</TableCell>
                                      <TableCell align="center">Neutral</TableCell>
                                      <TableCell align="center">Negative</TableCell>
                                      <TableCell align="center">Total</TableCell>
                                    </TableRow>
                                  </TableHead>
                                  <TableBody>
                                    {stock.allData.slice(0, 10).map((row, index) => (
                                      <TableRow key={`${stock.symbol}-${index}`}>
                                        <TableCell>{new Date(row.date).toLocaleDateString()}</TableCell>
                                        <TableCell>
                                          <Chip label={row.source || "Unknown"} size="small" variant="outlined" />
                                        </TableCell>
                                        <TableCell align="center">
                                          <Chip
                                            label={row.sentiment_score?.toFixed(2) || "N/A"}
                                            size="small"
                                            color={row.sentiment_score > 0.2 ? "success" : row.sentiment_score < -0.2 ? "error" : "warning"}
                                          />
                                        </TableCell>
                                        <TableCell align="center">{row.positive_mentions || 0}</TableCell>
                                        <TableCell align="center">{row.neutral_mentions || 0}</TableCell>
                                        <TableCell align="center">{row.negative_mentions || 0}</TableCell>
                                        <TableCell align="center">{row.total_mentions || 0}</TableCell>
                                      </TableRow>
                                    ))}
                                  </TableBody>
                                </Table>
                              </TableContainer>
                            </CardContent>
                          </Card>
                        </Grid>
                      </Grid>
                    </AccordionDetails>
                  </Accordion>
                );
              })}
            </Box>
          )}
        </>
      )}
      </Box>

      {/* Section 3: Analyst Insights & Actions - AT THE BOTTOM */}
      <Box sx={{ mb: 4 }}>
        {upgradesLoading ? (
          <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: 400 }}>
            <CircularProgress />
          </Box>
        ) : upgradesError ? (
          <Alert severity="error">{upgradesError}</Alert>
        ) : (
          <>
            {/* Filters */}
            <Box sx={{ mb: 3, display: "flex", gap: 2, flexWrap: "wrap" }}>
              <TextField
                placeholder="Search by symbol..."
                variant="outlined"
                size="small"
                value={searchSymbol}
                onChange={(e) => setSearchSymbol(e.target.value)}
                InputProps={{
                  startAdornment: (
                    <InputAdornment position="start">
                      <Search />
                    </InputAdornment>
                  ),
                }}
                sx={{ minWidth: 200 }}
              />
            </Box>

            {/* Analyst Upgrades/Downgrades Table */}
            {filteredUpgrades.length > 0 ? (
              <Card sx={{ mb: 4 }}>
                <CardContent>
                  <Typography variant="h6" gutterBottom sx={{ display: "flex", alignItems: "center", gap: 1, mb: 3 }}>
                    <TimelineIcon />
                    Recent Analyst Actions (Upgrades/Downgrades)
                  </Typography>

                  <TableContainer>
                    <Table>
                      <TableHead>
                        <TableRow>
                          <TableCell>Symbol</TableCell>
                          <TableCell>Company Name</TableCell>
                          <TableCell>Firm</TableCell>
                          <TableCell>Action</TableCell>
                          <TableCell>From Grade</TableCell>
                          <TableCell>To Grade</TableCell>
                          <TableCell>Date</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {(rowsPerPage > 0
                          ? filteredUpgrades.slice(tablePage * rowsPerPage, tablePage * rowsPerPage + rowsPerPage)
                          : filteredUpgrades
                        ).map((upgrade, index) => (
                          <TableRow key={upgrade.id || index} hover>
                            <TableCell>
                              <Typography variant="body2" fontWeight="bold" sx={{ color: "primary.main" }}>
                                {upgrade.symbol}
                              </Typography>
                            </TableCell>
                            <TableCell>
                              <Typography variant="body2">{upgrade.company_name || "N/A"}</Typography>
                            </TableCell>
                            <TableCell>
                              <Typography variant="body2">{upgrade.firm || "N/A"}</Typography>
                            </TableCell>
                            <TableCell>
                              <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                                {getActionIcon(upgrade.action, upgrade.from_grade, upgrade.to_grade)}
                                <Chip
                                  label={upgrade.action === "main" ? "maint" : (upgrade.action || "N/A")}
                                  color={getActionColor(upgrade.action, upgrade.from_grade, upgrade.to_grade)}
                                  size="small"
                                />
                              </Box>
                            </TableCell>
                            <TableCell>
                              <Typography variant="body2">{upgrade.from_grade || "N/A"}</Typography>
                            </TableCell>
                            <TableCell>
                              <Typography variant="body2">{upgrade.to_grade || "N/A"}</Typography>
                            </TableCell>
                            <TableCell>
                              <Typography variant="body2">{formatDate(upgrade.date)}</Typography>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </TableContainer>
                  <TablePagination
                    component="div"
                    count={filteredUpgrades.length}
                    page={tablePage}
                    onPageChange={(e, newPage) => setTablePage(newPage)}
                    rowsPerPage={rowsPerPage}
                    onRowsPerPageChange={(e) => {
                      setRowsPerPage(parseInt(e.target.value, 10));
                      setTablePage(0);
                    }}
                    rowsPerPageOptions={[10, 25, 50, 100, { label: "All", value: -1 }]}
                  />
                </CardContent>
              </Card>
            ) : (
              <Alert severity="info">No analyst upgrades/downgrades found</Alert>
            )}

            {/* Section: Comprehensive Analyst Metrics - Detailed Data */}
            <Divider sx={{ my: 4 }} />
            <Box sx={{ mb: 3 }}>
              <Typography variant="h6" sx={{ display: "flex", alignItems: "center", gap: 1, mb: 2 }}>
                <TrendingUpRounded />
                Comprehensive Analyst Metrics by Stock
              </Typography>
              <Typography variant="body2" color="textSecondary" sx={{ mb: 3 }}>
                Detailed analyst sentiment trends, momentum, EPS revisions, and all available analyst metrics
              </Typography>
            </Box>

            {isLoading ? (
              <Box display="flex" justifyContent="center" py={4}>
                <CircularProgress />
              </Box>
            ) : error ? (
              <Alert severity="error" sx={{ mb: 3 }}>
                Failed to load sentiment data: {error.message}
              </Alert>
            ) : filteredAndSortedStocks.length === 0 ? (
              <Alert severity="info">No sentiment data available</Alert>
            ) : (
              <Box>
                {filteredAndSortedStocks.map((stock) => (
                  <Accordion key={`analyst-${stock.symbol}`} sx={{ mb: 2 }}>
                    <AccordionSummary expandIcon={<ExpandMore />}>
                      <Box sx={{ width: "100%", display: "flex", alignItems: "center", gap: 2 }}>
                        <Typography variant="h6" fontWeight="bold" sx={{ minWidth: 80 }}>
                          {stock.symbol}
                        </Typography>
                        <Box display="flex" alignItems="center" gap={1}>
                          {stock.compositeSentiment.icon}
                          <Chip
                            label={stock.compositeSentiment.label}
                            color={stock.compositeSentiment.color}
                            size="small"
                          />
                        </Box>
                      </Box>
                    </AccordionSummary>
                    <AccordionDetails>
                      <ComprehensiveAnalystMetrics symbol={stock.symbol} />
                    </AccordionDetails>
                  </Accordion>
                ))}
              </Box>
            )}

            {/* Section: Comprehensive Social Sentiment Metrics */}
            <Divider sx={{ my: 4 }} />
            <Box sx={{ mb: 3 }}>
              <Typography variant="h6" sx={{ display: "flex", alignItems: "center", gap: 1, mb: 2 }}>
                <Reddit />
                Comprehensive Social Sentiment Metrics by Stock
              </Typography>
              <Typography variant="body2" color="textSecondary" sx={{ mb: 3 }}>
                Detailed social media, alternative data, and sentiment volume trends for each stock
              </Typography>
            </Box>

            {isLoading ? (
              <Box display="flex" justifyContent="center" py={4}>
                <CircularProgress />
              </Box>
            ) : error ? (
              <Alert severity="error" sx={{ mb: 3 }}>
                Failed to load sentiment data: {error.message}
              </Alert>
            ) : filteredAndSortedStocks.length === 0 ? (
              <Alert severity="info">No sentiment data available</Alert>
            ) : (
              <Box>
                {filteredAndSortedStocks.map((stock) => (
                  <Accordion key={`social-${stock.symbol}`} sx={{ mb: 2 }}>
                    <AccordionSummary expandIcon={<ExpandMore />}>
                      <Box sx={{ width: "100%", display: "flex", alignItems: "center", gap: 2 }}>
                        <Typography variant="h6" fontWeight="bold" sx={{ minWidth: 80 }}>
                          {stock.symbol}
                        </Typography>
                        <Box display="flex" alignItems="center" gap={1}>
                          {stock.compositeSentiment.icon}
                          <Chip
                            label={stock.compositeSentiment.label}
                            color={stock.compositeSentiment.color}
                            size="small"
                          />
                        </Box>
                      </Box>
                    </AccordionSummary>
                    <AccordionDetails>
                      <ComprehensiveSocialSentiment symbol={stock.symbol} />
                    </AccordionDetails>
                  </Accordion>
                ))}
              </Box>
            )}
          </>
        )}
      </Box>

    </Container>
  );
}

export default Sentiment;
