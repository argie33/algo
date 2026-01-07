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
import { getApiUrl } from "../utils/apiUrl";

const API_BASE = getApiUrl();

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
  // Need at least 2 sentiment sources to detect divergence
  if (scores.length < 2) return null;

  const maxScore = Math.max(...scores);
  const minScore = Math.min(...scores);
  const divergence = maxScore - minScore;
  const sourcesCount = scores.length; // Track how many sources were included

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
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState(null);

  React.useEffect(() => {
    const fetchAnalystData = async () => {
      try {
        setLoading(true);
        setError(null);

        // Fetch analyst sentiment data and upgrades from working endpoints
        const [sentimentRes, upgradesRes] = await Promise.all([
          fetch(`${API_BASE}/api/sentiment/data?symbol=${symbol}`).catch(() => null),
          fetch(`${API_BASE}/api/analysts/upgrades?limit=50`).catch(() => null),
        ]);

        // Get sentiment data for this symbol
        if (sentimentRes?.ok) {
          const sentimentData = await sentimentRes.json();
          const symbolData = sentimentData.items?.find(item => item.symbol === symbol);
          if (symbolData) {
            setSentimentTrend(symbolData);
          }
        }

        // Filter upgrades for this symbol
        if (upgradesRes?.ok) {
          const upgradesData = await upgradesRes.json();
          const symbolUpgrades = upgradesData.data?.filter(item => item.symbol === symbol) || [];
          if (symbolUpgrades.length > 0) {
            setMomentum(symbolUpgrades.slice(0, 10)); // Show latest 10
          }
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
            <Typography variant="h6" gutterBottom>Analyst Sentiment</Typography>
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
                      <TableRow key={`sent-trend-${item.date}-${idx}`}>
                        <TableCell>{new Date(item.date || item.timestamp).toLocaleDateString()}</TableCell>
                        <TableCell align="center">
                          <Chip label={`${item.bullish_pct ?? 'N/A'}%`} size="small" color="success" />
                        </TableCell>
                        <TableCell align="center">
                          <Chip label={`${item.neutral_pct ?? 'N/A'}%`} size="small" />
                        </TableCell>
                        <TableCell align="center">
                          <Chip label={`${item.bearish_pct ?? 'N/A'}%`} size="small" color="error" />
                        </TableCell>
                        <TableCell align="center">{item.total_analysts ?? 'N/A'}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            ) : (
              <Grid container spacing={2}>
                {(() => {
                  const total = sentimentTrend.analyst_count || 1;
                  const bullish = sentimentTrend.bullish_count || 0;
                  const neutral = sentimentTrend.neutral_count || 0;
                  const bearish = sentimentTrend.bearish_count || 0;
                  const bullishPct = ((bullish / total) * 100).toFixed(1);
                  const neutralPct = ((neutral / total) * 100).toFixed(1);
                  const bearishPct = ((bearish / total) * 100).toFixed(1);
                  return (
                    <>
                      <Grid item xs={12} sm={6} md={4}>
                        <Box sx={{ p: 1.5, bgcolor: alpha(theme.palette.success.main, 0.1), borderRadius: 1 }}>
                          <Typography variant="caption" color="textSecondary">Bullish</Typography>
                          <Typography variant="h5" sx={{ fontWeight: 'bold', color: theme.palette.success.main }}>
                            {bullishPct}%
                          </Typography>
                          <Typography variant="caption" color="textSecondary">({bullish} analysts)</Typography>
                        </Box>
                      </Grid>
                      <Grid item xs={12} sm={6} md={4}>
                        <Box sx={{ p: 1.5, bgcolor: alpha(theme.palette.warning.main, 0.1), borderRadius: 1 }}>
                          <Typography variant="caption" color="textSecondary">Neutral</Typography>
                          <Typography variant="h5" sx={{ fontWeight: 'bold', color: theme.palette.warning.main }}>
                            {neutralPct}%
                          </Typography>
                          <Typography variant="caption" color="textSecondary">({neutral} analysts)</Typography>
                        </Box>
                      </Grid>
                      <Grid item xs={12} sm={6} md={4}>
                        <Box sx={{ p: 1.5, bgcolor: alpha(theme.palette.error.main, 0.1), borderRadius: 1 }}>
                          <Typography variant="caption" color="textSecondary">Bearish</Typography>
                          <Typography variant="h5" sx={{ fontWeight: 'bold', color: theme.palette.error.main }}>
                            {bearishPct}%
                          </Typography>
                          <Typography variant="caption" color="textSecondary">({bearish} analysts)</Typography>
                        </Box>
                      </Grid>
                    </>
                  );
                })()}
              </Grid>
            )}
          </CardContent>
        </Card>
      )}

      {/* Momentum Data - Analyst Upgrades/Downgrades */}
      {momentum && Array.isArray(momentum) && momentum.length > 0 && (
        <Card variant="outlined" sx={{ mb: 2 }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>Recent Analyst Actions</Typography>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Date</TableCell>
                    <TableCell>Firm</TableCell>
                    <TableCell>Action</TableCell>
                    <TableCell align="center">Old Rating</TableCell>
                    <TableCell align="center">New Rating</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {momentum.slice(0, 10).map((item, idx) => (
                    <TableRow key={`upgrade-${item.date}-${idx}`}>
                      <TableCell>{new Date(item.date || item.timestamp).toLocaleDateString()}</TableCell>
                      <TableCell>{item.firm || item.analyst || 'N/A'}</TableCell>
                      <TableCell>
                        <Chip
                          label={item.action || 'N/A'}
                          size="small"
                          color={item.action?.toLowerCase().includes('upgrade') ? 'success' : item.action?.toLowerCase().includes('downgrade') ? 'error' : 'default'}
                        />
                      </TableCell>
                      <TableCell align="center">{item.old_rating || 'N/A'}</TableCell>
                      <TableCell align="center">{item.new_rating || 'N/A'}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </CardContent>
        </Card>
      )}

      {!sentimentTrend && !momentum && !loading && (
        <Alert severity="info">No analyst data available for {symbol}</Alert>
      )}
    </Box>
  );
};

// Comprehensive Social Sentiment Component - Complete display of all social data
const ComprehensiveSocialSentiment = ({ symbol }) => {
  const [insightsData, setInsightsData] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState(null);
  const theme = useTheme();

  React.useEffect(() => {
    const fetchSocialInsights = async () => {
      try {
        setLoading(true);
        setError(null);
        const response = await fetch(`${API_BASE}/api/sentiment/social/insights/${symbol}`);
        if (response.ok) {
          const data = await response.json();
          setInsightsData(data);
        } else {
          setError("No social sentiment data available");
        }
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    if (symbol) {
      fetchSocialInsights();
    }
  }, [symbol]);

  if (loading) {
    return (
      <Card variant="outlined">
        <CardContent>
          <CircularProgress size={20} sx={{ mr: 1 }} />
          <Typography variant="body2" color="textSecondary">Loading social sentiment...</Typography>
        </CardContent>
      </Card>
    );
  }

  if (error || !insightsData?.metrics) {
    return (
      <Card variant="outlined">
        <CardContent>
          <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>Social Sentiment & Market Discussion</Typography>
          <Typography variant="body2" color="textSecondary">
            {error || "No data available"}
          </Typography>
        </CardContent>
      </Card>
    );
  }

  const { metrics, trends, historical } = insightsData;

  return (
    <Card variant="outlined" sx={{ mt: 2 }}>
      <CardContent>
        {/* Clean Header */}
        <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 2.5 }}>
          Social Sentiment & Market Discussion
        </Typography>

        {/* Core Metrics - 2x2 Grid */}
        <Grid container spacing={2} sx={{ mb: 3 }}>
          {/* Reddit Sentiment */}
          <Grid item xs={12} sm={6}>
            <Box sx={{ p: 1.5, bgcolor: alpha(theme.palette.primary.main, 0.05), borderRadius: 1 }}>
              <Typography variant="caption" sx={{ fontWeight: 600, display: 'block', mb: 0.8, color: 'textSecondary' }}>
                Reddit Sentiment
              </Typography>
              <Typography variant="h6" sx={{ fontWeight: 700 }}>
                {metrics.reddit.sentiment_score ? (
                  `${parseFloat(metrics.reddit.sentiment_score) > 0 ? '+' : ''}${parseFloat(metrics.reddit.sentiment_score).toFixed(3)}`
                ) : '—'}
              </Typography>
              <Typography variant="caption" color="textSecondary">
                {metrics.reddit.mention_count || 0} mentions
              </Typography>
            </Box>
          </Grid>

          {/* News Sentiment */}
          <Grid item xs={12} sm={6}>
            <Box sx={{ p: 1.5, bgcolor: alpha(theme.palette.success.main, 0.05), borderRadius: 1 }}>
              <Typography variant="caption" sx={{ fontWeight: 600, display: 'block', mb: 0.8, color: 'textSecondary' }}>
                News Sentiment
              </Typography>
              <Typography variant="h6" sx={{ fontWeight: 700 }}>
                {metrics.news.sentiment_score ? (
                  `${parseFloat(metrics.news.sentiment_score) > 0 ? '+' : ''}${parseFloat(metrics.news.sentiment_score).toFixed(3)}`
                ) : '—'}
              </Typography>
              <Typography variant="caption" color="textSecondary">
                {metrics.news.article_count || 0} articles
              </Typography>
            </Box>
          </Grid>

          {/* Search Volume */}
          <Grid item xs={12} sm={6}>
            <Box sx={{ p: 1.5, bgcolor: alpha(theme.palette.info.main, 0.05), borderRadius: 1 }}>
              <Typography variant="caption" sx={{ fontWeight: 600, display: 'block', mb: 0.8, color: 'textSecondary' }}>
                Search Volume
              </Typography>
              <Typography variant="h6" sx={{ fontWeight: 700 }}>
                {metrics.search.volume_index ?? '—'}
              </Typography>
              <Typography variant="caption" color="textSecondary">
                7d: {metrics.search.trend_7d_direction}{Math.abs(parseFloat(metrics.search.trend_7d_percent || 0)).toFixed(1)}% | 30d: {metrics.search.trend_30d_direction}{Math.abs(parseFloat(metrics.search.trend_30d_percent || 0)).toFixed(1)}%
              </Typography>
            </Box>
          </Grid>

          {/* Social Media Volume */}
          <Grid item xs={12} sm={6}>
            <Box sx={{ p: 1.5, bgcolor: alpha(theme.palette.warning.main, 0.05), borderRadius: 1 }}>
              <Typography variant="caption" sx={{ fontWeight: 600, display: 'block', mb: 0.8, color: 'textSecondary' }}>
                Social Volume & Viral Score
              </Typography>
              <Typography variant="h6" sx={{ fontWeight: 700 }}>
                {metrics.social.volume || 0} posts
              </Typography>
              <Typography variant="caption" color="textSecondary">
                Viral: {metrics.social.viral_score ? parseFloat(metrics.social.viral_score).toFixed(2) : '—'}
              </Typography>
            </Box>
          </Grid>
        </Grid>

        {/* Trend Comparison */}
        {trends && (trends.news_sentiment || trends.reddit_sentiment || trends.search_volume) && (
          <Box sx={{ mb: 3, pt: 2, borderTop: `1px solid ${theme.palette.divider}` }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 2, mt: 1 }}>
              7-Day vs 30-Day Trend Comparison
            </Typography>
            <Grid container spacing={2}>
              {trends.reddit_sentiment && (
                <Grid item xs={12} sm={4}>
                  <Box sx={{ p: 1.5, border: `1px solid ${theme.palette.divider}`, borderRadius: 1 }}>
                    <Typography variant="caption" sx={{ fontWeight: 600, display: 'block', mb: 1 }}>
                      Reddit {trends.reddit_sentiment.direction}
                    </Typography>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                      <span style={{ fontSize: '0.85rem' }}>7-day avg:</span>
                      <span style={{ fontWeight: 600, fontSize: '0.85rem' }}>{parseFloat(trends.reddit_sentiment.current_avg).toFixed(3)}</span>
                    </Box>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span style={{ fontSize: '0.85rem' }}>30-day avg:</span>
                      <span style={{ fontWeight: 600, fontSize: '0.85rem' }}>{parseFloat(trends.reddit_sentiment.period_avg).toFixed(3)}</span>
                    </Box>
                  </Box>
                </Grid>
              )}

              {trends.news_sentiment && (
                <Grid item xs={12} sm={4}>
                  <Box sx={{ p: 1.5, border: `1px solid ${theme.palette.divider}`, borderRadius: 1 }}>
                    <Typography variant="caption" sx={{ fontWeight: 600, display: 'block', mb: 1 }}>
                      News {trends.news_sentiment.direction}
                    </Typography>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                      <span style={{ fontSize: '0.85rem' }}>7-day avg:</span>
                      <span style={{ fontWeight: 600, fontSize: '0.85rem' }}>{parseFloat(trends.news_sentiment.current_avg).toFixed(3)}</span>
                    </Box>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span style={{ fontSize: '0.85rem' }}>30-day avg:</span>
                      <span style={{ fontWeight: 600, fontSize: '0.85rem' }}>{parseFloat(trends.news_sentiment.period_avg).toFixed(3)}</span>
                    </Box>
                  </Box>
                </Grid>
              )}

              {trends.search_volume && (
                <Grid item xs={12} sm={4}>
                  <Box sx={{ p: 1.5, border: `1px solid ${theme.palette.divider}`, borderRadius: 1 }}>
                    <Typography variant="caption" sx={{ fontWeight: 600, display: 'block', mb: 1 }}>
                      Search Volume {trends.search_volume.direction}
                    </Typography>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                      <span style={{ fontSize: '0.85rem' }}>7-day avg:</span>
                      <span style={{ fontWeight: 600, fontSize: '0.85rem' }}>{trends.search_volume.current_avg}</span>
                    </Box>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span style={{ fontSize: '0.85rem' }}>30-day avg:</span>
                      <span style={{ fontWeight: 600, fontSize: '0.85rem' }}>{trends.search_volume.period_avg}</span>
                    </Box>
                  </Box>
                </Grid>
              )}
            </Grid>
          </Box>
        )}

        {/* Historical Data Table */}
        {historical && historical.length > 0 && (
          <Box sx={{ pt: 2, borderTop: `1px solid ${theme.palette.divider}` }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 1.5, mt: 1 }}>
              Historical Data (Last 30 Days)
            </Typography>
            <TableContainer sx={{ maxHeight: 300 }}>
              <Table size="small" stickyHeader>
                <TableHead>
                  <TableRow sx={{ bgcolor: alpha(theme.palette.primary.main, 0.1) }}>
                    <TableCell sx={{ fontWeight: 600, fontSize: '0.8rem' }}>Date</TableCell>
                    <TableCell align="center" sx={{ fontWeight: 600, fontSize: '0.8rem' }}>Reddit</TableCell>
                    <TableCell align="center" sx={{ fontWeight: 600, fontSize: '0.8rem' }}>News</TableCell>
                    <TableCell align="center" sx={{ fontWeight: 600, fontSize: '0.8rem' }}>Search</TableCell>
                    <TableCell align="center" sx={{ fontWeight: 600, fontSize: '0.8rem' }}>Viral</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {historical.slice(0, 30).map((item, idx) => (
                    <TableRow key={`hist-${item.date}-${idx}`} sx={{ '&:nth-of-type(odd)': { bgcolor: alpha(theme.palette.primary.main, 0.02) } }}>
                      <TableCell sx={{ fontSize: '0.8rem' }}>
                        {new Date(item.date).toLocaleDateString()}
                      </TableCell>
                      <TableCell align="center" sx={{ fontSize: '0.8rem' }}>
                        {item.reddit_sentiment ? parseFloat(item.reddit_sentiment).toFixed(2) : '—'}
                      </TableCell>
                      <TableCell align="center" sx={{ fontSize: '0.8rem' }}>
                        {item.news_sentiment ? parseFloat(item.news_sentiment).toFixed(2) : '—'}
                      </TableCell>
                      <TableCell align="center" sx={{ fontSize: '0.8rem' }}>
                        {item.search_volume || '—'}
                      </TableCell>
                      <TableCell align="center" sx={{ fontSize: '0.8rem' }}>
                        {item.viral_score ? parseFloat(item.viral_score).toFixed(2) : '—'}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </Box>
        )}
      </CardContent>
    </Card>
  );
};

// Analyst Trend Card Component - Metrics-focused display
const AnalystTrendCard = ({ symbol }) => {
  const theme = useTheme();
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState(null);
  const [insightsData, setInsightsData] = React.useState(null);
  const [sentimentTrend, setSentimentTrend] = React.useState(null);
  const [analystMomentum, setAnalystMomentum] = React.useState(null);

  // Fetch comprehensive analyst data from all endpoints
  React.useEffect(() => {
    const fetchAllAnalystData = async () => {
      try {
        setLoading(true);
        setError(null);

        // Fetch from available endpoints
        const [insightsRes, sentimentRes, upgradesRes] = await Promise.all([
          fetch(`${API_BASE}/api/sentiment/analyst/insights/${symbol}`).catch(() => null),
          fetch(`${API_BASE}/api/sentiment/data?symbol=${symbol}`).catch(() => null),
          fetch(`${API_BASE}/api/analysts/upgrades?limit=50`).catch(() => null),
        ]);

        // Process insights data (primary source)
        if (insightsRes?.ok) {
          const insights = await insightsRes.json();
          setInsightsData(insights);
        }

        // Get sentiment data for this symbol
        if (sentimentRes?.ok) {
          const sentimentData = await sentimentRes.json();
          const symbolData = sentimentData.items?.find(item => item.symbol === symbol);
          if (symbolData) {
            setSentimentTrend(symbolData);
          }
        }

        // Filter upgrades for this symbol
        if (upgradesRes?.ok) {
          const upgradesData = await upgradesRes.json();
          const symbolUpgrades = upgradesData.data?.filter(item => item.symbol === symbol) || [];
          if (symbolUpgrades.length > 0) {
            setAnalystMomentum(symbolUpgrades.slice(0, 10));
          }
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
                      ${typeof metrics.avgPriceTarget === 'number' ? metrics.avgPriceTarget.toFixed(2) : (metrics.avgPriceTarget ? parseFloat(metrics.avgPriceTarget).toFixed(2) : 'N/A')}
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
                        {metrics.priceTargetVsCurrent > 0 ? "+" : ""}{typeof metrics.priceTargetVsCurrent === 'number' ? metrics.priceTargetVsCurrent.toFixed(1) : (metrics.priceTargetVsCurrent ? parseFloat(metrics.priceTargetVsCurrent).toFixed(1) : 'N/A')}%
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
                    <TableRow key={`price-target-${target.analyst_firm}-${idx}`}>
                      <TableCell>{target.analyst_firm}</TableCell>
                      <TableCell align="center">
                        <Chip label={`$${parseFloat(target.target_price).toFixed(2)}`} size="small" />
                      </TableCell>
                      <TableCell align="center">
                        <Typography variant="body2" color="textSecondary">
                          ${target.previous_target_price ? parseFloat(target.previous_target_price).toFixed(2) : 'N/A'}
                        </Typography>
                      </TableCell>
                      <TableCell align="center">
                        {target.target_price && target.previous_target_price ? (
                          <Chip
                            label={`${(parseFloat(target.target_price) - parseFloat(target.previous_target_price)).toFixed(2)}`}
                            size="small"
                            color={parseFloat(target.target_price) > parseFloat(target.previous_target_price) ? 'success' : 'error'}
                            variant="outlined"
                          />
                        ) : (
                          <Typography variant="body2" color="textSecondary">N/A</Typography>
                        )}
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
                    <TableRow key={`upgrade-${upgrade.firm}-${idx}`}>
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
                <Grid item xs={12} sm={6} md={4} key={`firm-${firm.name || firm}-${idx}`}>
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
                    <TableRow key={`chart-${item.date}-${idx}`}>
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
        {!metrics && !momentum && !priceTargets && !recentUpgrades && !sentimentTrend && (
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

  // Fetch all sentiment data - get all 512 stocks
  const { data: sentimentData, isLoading, error } = useQuery({
    queryKey: ["sentimentStocks"],
    queryFn: async () => {
      const response = await fetch(`${API_BASE}/api/sentiment/data?limit=512&page=1`);
      if (!response.ok) throw new Error("Failed to fetch sentiment");
      return response.json();
    },
    staleTime: 0, // Always fresh // 5 minutes
    refetchInterval: 300000,
  });

  // Parse sentiment data - API returns { items: [...], pagination: {...} }
  const rawData = sentimentData?.items || sentimentData?.data || [];

  // Fetch analyst upgrades/downgrades
  useEffect(() => {
    const fetchAnalystUpgrades = async () => {
      try {
        setUpgradesLoading(true);
        const response = await fetch(`${API_BASE}/api/analysts/upgrades?limit=100`);
        if (!response.ok) throw new Error("Failed to fetch analyst upgrades");
        const data = await response.json();
        // Handle both response structures: { data: [...] } or { data: { upgrades: [...] } }
        const upgradesData = Array.isArray(data?.data) ? data.data : (data?.data?.upgrades || []);
        if (upgradesData && upgradesData.length > 0) {
          setUpgrades(upgradesData);
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

  // Calculate analyst sentiment score from bullish/bearish counts
  const calculateAnalystSentiment = (bullish, bearish, neutral, total) => {
    if (!total || total === 0) return null;
    // Score from -1 (all bearish) to +1 (all bullish)
    const bullishPercent = (bullish / total);
    const bearishPercent = (bearish / total);
    return bullishPercent - bearishPercent;
  };

  // Group by symbol and calculate composite scores
  const groupedBySymbol = rawData.reduce((acc, item) => {
    const symbol = item.symbol;
    if (!acc[symbol]) {
      acc[symbol] = {
        symbol,
        analyst: [],
      };
    }

    // API returns analyst sentiment data (bullish_count, bearish_count, etc.)
    // Calculate sentiment score from these counts
    const analystScore = calculateAnalystSentiment(
      item.bullish_count,
      item.bearish_count,
      item.neutral_count,
      item.analyst_count
    );

    acc[symbol].analyst.push({
      ...item,
      sentiment_score: analystScore,
      source: "analyst"
    });

    return acc;
  }, {});

  // Convert to array and calculate composite scores
  const stocksList = Object.values(groupedBySymbol).map(stock => {
    const latestAnalyst = stock.analyst && stock.analyst.length > 0 ? stock.analyst[0] : null;

    // API returns only analyst sentiment data, so composite = analyst score
    const compositeScore = latestAnalyst?.sentiment_score || null;

    return {
      symbol: stock.symbol,
      compositeScore,
      compositeSentiment: getSentimentLabel(compositeScore),
      analyst: stock.analyst,
      latestAnalyst,
      latestNews: null,
      latestSocial: null,
      allData: [...stock.analyst].sort((a, b) =>
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
        case "composite": {
          const aScore = a.compositeScore;
          const bScore = b.compositeScore;
          // Put nulls at end
          if (aScore === null && bScore === null) return 0;
          if (aScore === null) return 1;
          if (bScore === null) return -1;
          return bScore - aScore;
        }
        case "news": {
          const aScore = a.latestNews?.sentiment_score;
          const bScore = b.latestNews?.sentiment_score;
          // Put nulls at end
          if (aScore === null && bScore === null) return 0;
          if (aScore === null) return 1;
          if (bScore === null) return -1;
          return bScore - aScore;
        }
        case "analyst": {
          const aScore = a.latestAnalyst?.sentiment_score;
          const bScore = b.latestAnalyst?.sentiment_score;
          // Put nulls at end
          if (aScore === null && bScore === null) return 0;
          if (aScore === null) return 1;
          if (bScore === null) return -1;
          return bScore - aScore;
        }
        case "social": {
          const aScore = a.latestSocial?.sentiment_score;
          const bScore = b.latestSocial?.sentiment_score;
          // Put nulls at end
          if (aScore === null && bScore === null) return 0;
          if (aScore === null) return 1;
          if (bScore === null) return -1;
          return bScore - aScore;
        }
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

        {/* Data Table - Stock Details */}
        {!isLoading && !error && (
          <>
            {filteredAndSortedStocks.length === 0 ? (
              <Alert severity="info">
                {searchFilter ? `No symbols match "${searchFilter}"` : "No sentiment data available"}
              </Alert>
            ) : (
              <Box>
                {/* Simple Table View */}
                <Card sx={{ mb: 3 }}>
                  <TableContainer>
                    <Table>
                      <TableHead>
                        <TableRow sx={{ backgroundColor: "grey.100" }}>
                          <TableCell><strong>Symbol</strong></TableCell>
                          <TableCell align="right"><strong>Analysts</strong></TableCell>
                          <TableCell align="right"><strong>Bullish</strong></TableCell>
                          <TableCell align="right"><strong>Neutral</strong></TableCell>
                          <TableCell align="right"><strong>Bearish</strong></TableCell>
                          <TableCell align="right"><strong>Target</strong></TableCell>
                          <TableCell align="right"><strong>Current</strong></TableCell>
                          <TableCell align="right"><strong>Upside %</strong></TableCell>
                          <TableCell align="center"><strong>Sentiment</strong></TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {filteredAndSortedStocks.map((stock) => (
                          <TableRow key={stock.symbol} hover>
                            <TableCell><strong>{stock.symbol}</strong></TableCell>
                            <TableCell align="right">{stock.latestAnalyst?.analyst_count || 0}</TableCell>
                            <TableCell align="right" sx={{ color: "success.main", fontWeight: 600 }}>
                              {stock.latestAnalyst?.bullish_count || 0}
                            </TableCell>
                            <TableCell align="right" sx={{ color: "warning.main", fontWeight: 600 }}>
                              {stock.latestAnalyst?.neutral_count || 0}
                            </TableCell>
                            <TableCell align="right" sx={{ color: "error.main", fontWeight: 600 }}>
                              {stock.latestAnalyst?.bearish_count || 0}
                            </TableCell>
                            <TableCell align="right">${parseFloat(stock.latestAnalyst?.target_price)?.toFixed(2) || "N/A"}</TableCell>
                            <TableCell align="right">${parseFloat(stock.latestAnalyst?.current_price)?.toFixed(2) || "N/A"}</TableCell>
                            <TableCell
                              align="right"
                              sx={{
                                fontWeight: 600,
                                color: parseFloat(stock.latestAnalyst?.upside_downside_percent) > 0 ? "success.main" : "error.main"
                              }}
                            >
                              {parseFloat(stock.latestAnalyst?.upside_downside_percent)?.toFixed(2) || "N/A"}%
                            </TableCell>
                            <TableCell align="center">
                              <Chip
                                label={stock.compositeSentiment.label}
                                color={stock.compositeSentiment.color}
                                size="small"
                              />
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </TableContainer>
                </Card>

                {/* Accordion List - Stock Details */}
                {filteredAndSortedStocks.map((stock) => {
                // CRITICAL: Get sentiment values - return null for missing data, not fake 0
                const analystScore = stock.latestAnalyst?.sentiment_score ?? null;

                // Only include components with real sentiment data (null means unavailable, 0 means real zero)
                const componentData = [
                  ...(analystScore !== null ? [{ name: "Analyst", value: analystScore, weight: 35 }] : [])
                ];

                // Re-normalize weights for components with actual data
                const totalWeight = componentData.reduce((sum, d) => sum + d.weight, 0);
                if (totalWeight > 0) {
                  componentData.forEach(d => d.weight = d.weight / totalWeight * 100);
                }

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
                            {stock.compositeScore !== null ? stock.compositeScore.toFixed(2) : ""}
                          </Typography>
                          <Typography variant="caption" color="textSecondary">
                            Composite Score
                          </Typography>
                        </Grid>
                        <Grid item xs={3}>
                          <Box display="flex" alignItems="center" gap={0.5}>
                            <TrendingUpRounded fontSize="small" />
                            <Chip
                              label={stock.latestAnalyst?.sentiment_score?.toFixed(2) || "N/A"}
                              size="small"
                              color={stock.latestAnalyst?.sentiment_score > 0.2 ? "success" : stock.latestAnalyst?.sentiment_score < -0.2 ? "error" : "warning"}
                            />
                          </Box>
                          <Typography variant="caption" color="textSecondary" sx={{ display: "block", mt: 0.5 }}>
                            Analyst
                          </Typography>
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
                                  {stock.compositeScore !== null ? stock.compositeScore.toFixed(2) : ""}
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


                        {/* Analyst Details Table */}
                        {stock.latestAnalyst && (
                          <Grid item xs={12}>
                            <Card variant="outlined">
                              <CardContent>
                                <Typography variant="h6" mb={2}>Analyst Details</Typography>
                                <Box display="flex" justifyContent="space-between" mb={1}>
                                  <Typography variant="body2">Total Analysts:</Typography>
                                  <Typography variant="body2" fontWeight="600">{stock.latestAnalyst?.analyst_count || 0}</Typography>
                                </Box>
                                <Box display="flex" justifyContent="space-between" mb={1}>
                                  <Typography variant="body2">Bullish:</Typography>
                                  <Chip label={stock.latestAnalyst?.bullish_count || 0} size="small" color="success" />
                                </Box>
                                <Box display="flex" justifyContent="space-between" mb={1}>
                                  <Typography variant="body2">Bearish:</Typography>
                                  <Chip label={stock.latestAnalyst?.bearish_count || 0} size="small" color="error" />
                                </Box>
                                <Box display="flex" justifyContent="space-between" mb={2}>
                                  <Typography variant="body2">Neutral:</Typography>
                                  <Chip label={stock.latestAnalyst?.neutral_count || 0} size="small" color="default" />
                                </Box>
                                <Divider sx={{ my: 2 }} />
                                <Box display="flex" justifyContent="space-between" mb={1}>
                                  <Typography variant="body2">Target Price:</Typography>
                                  <Typography variant="body2" fontWeight="600">${parseFloat(stock.latestAnalyst?.target_price)?.toFixed(2) || "N/A"}</Typography>
                                </Box>
                                <Box display="flex" justifyContent="space-between" mb={1}>
                                  <Typography variant="body2">Current Price:</Typography>
                                  <Typography variant="body2" fontWeight="600">${parseFloat(stock.latestAnalyst?.current_price)?.toFixed(2) || "N/A"}</Typography>
                                </Box>
                                <Box display="flex" justifyContent="space-between">
                                  <Typography variant="body2">Upside/Downside:</Typography>
                                  <Typography
                                    variant="body2"
                                    fontWeight="600"
                                    color={parseFloat(stock.latestAnalyst?.upside_downside_percent) > 0 ? "success.main" : "error.main"}
                                  >
                                    {parseFloat(stock.latestAnalyst?.upside_downside_percent)?.toFixed(2) || "N/A"}%
                                  </Typography>
                                </Box>
                              </CardContent>
                            </Card>
                          </Grid>
                        )}

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
                                        <TableCell align="center">{row.positive_mentions ?? 'N/A'}</TableCell>
                                        <TableCell align="center">{row.neutral_mentions ?? 'N/A'}</TableCell>
                                        <TableCell align="center">{row.negative_mentions ?? 'N/A'}</TableCell>
                                        <TableCell align="center">{row.total_mentions ?? 'N/A'}</TableCell>
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
            ) : null}
          </>
        )}
      </Box>

    </Container>
  );
}

export default Sentiment;
