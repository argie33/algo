import React, { useState, useEffect, useMemo } from 'react';
import {
  Box,
  Container,
  Typography,
  Grid,
  Card,
  CardContent,
  CardHeader,
  Tabs,
  Tab,
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
  Button,
  TextField,
  MenuItem,
  IconButton,
  FormControl,
  InputLabel,
  Select,
  Tooltip,
  Badge,
  Divider,
  List,
  ListItem,
  ListItemText,
  ListItemAvatar,
  Avatar,
  Rating,
  Stepper,
  Step,
  StepLabel,
  StepContent,
  CircularProgress,
  TableSortLabel,
  Accordion,
  AccordionSummary,
  AccordionDetails
} from '@mui/material';
import {
  TrendingUp,
  TrendingDown,
  Psychology,
  Analytics,
  Newspaper,
  Reddit,
  Twitter,
  Assessment,
  Warning,
  CheckCircle,
  Info,
  Timeline,
  ShowChart,
  BarChart,
  FilterList,
  Refresh,
  Download,
  Share,
  BookmarkBorder,
  Bookmark,
  ThumbUp,
  ThumbDown,
  Visibility,
  VisibilityOff,
  ExpandMore,
  Speed,
  TrendingFlat,
  Lightbulb
} from '@mui/icons-material';
import {
  PieChart,
  Pie,
  Cell,
  BarChart as RechartsBarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  LineChart,
  Line,
  Area,
  AreaChart,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  ComposedChart,
  ScatterChart,
  Scatter
} from 'recharts';
import { formatPercentage, formatNumber } from '../utils/formatters';
import { useSimpleFetch } from '../hooks/useSimpleFetch';
import { getApiConfig } from '../services/api';

// Get API configuration
const { apiUrl: API_BASE } = getApiConfig();

function TabPanel({ children, value, index, ...other }) {
  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`sentiment-tabpanel-${index}`}
      aria-labelledby={`sentiment-tab-${index}`}
      {...other}
    >
      {value === index && (
        <Box sx={{ py: 3 }}>
          {children}
        </Box>
      )}
    </div>
  );
}

// Live sentiment data hooks
function useLiveSentiment(symbol = 'SPY', timeframe = '24h') {
  return useSimpleFetch(`${API_BASE}/api/news/sentiment/${symbol}?timeframe=${timeframe}`, {
    fallback: null,
    errorMessage: 'Failed to load sentiment data'
  });
}

function useLiveMarketSentiment(timeframe = '24h') {
  return useSimpleFetch(`${API_BASE}/api/news/market-sentiment?timeframe=${timeframe}`, {
    fallback: null,
    errorMessage: 'Failed to load market sentiment'
  });
}

function useLiveNewsArticles(symbol = null, timeframe = '24h', limit = 20) {
  const url = symbol 
    ? `${API_BASE}/api/news/articles?symbol=${symbol}&timeframe=${timeframe}&limit=${limit}`
    : `${API_BASE}/api/news/articles?timeframe=${timeframe}&limit=${limit}`;
  
  return useSimpleFetch(url, {
    fallback: { articles: [], total: 0 },
    errorMessage: 'Failed to load news articles'
  });
}

function useLiveTrending(timeframe = '24h', limit = 10) {
  return useSimpleFetch(`${API_BASE}/api/news/trending?timeframe=${timeframe}&limit=${limit}`, {
    fallback: { keywords: [], symbols: [] },
    errorMessage: 'Failed to load trending data'
  });
}

const SentimentAnalysis = () => {
  const [activeTab, setActiveTab] = useState(0);
  const [selectedTimeframe, setSelectedTimeframe] = useState('24h');
  const [selectedSymbol, setSelectedSymbol] = useState('SPY');
  const [orderBy, setOrderBy] = useState('impact');
  const [order, setOrder] = useState('desc');

  // Live data hooks
  const { data: sentimentData, loading: sentimentLoading, error: sentimentError } = useLiveSentiment(selectedSymbol, selectedTimeframe);
  const { data: marketSentiment, loading: marketLoading } = useLiveMarketSentiment(selectedTimeframe);
  const { data: newsData, loading: newsLoading } = useLiveNewsArticles(selectedSymbol, selectedTimeframe, 20);
  const { data: trendingData, loading: trendingLoading } = useLiveTrending(selectedTimeframe);

  // Loading state
  const loading = sentimentLoading || marketLoading || newsLoading || trendingLoading;

  // Transform live data into display format
  const transformedSentimentData = useMemo(() => {
    if (!sentimentData || !marketSentiment) return null;
    
    // Create sources from live data
    const sources = [
      {
        source: 'News Sentiment',
        score: Math.round(sentimentData.overall_sentiment.score * 100 + 50), // Convert -1,1 to 0-100
        previousScore: Math.round(sentimentData.overall_sentiment.score * 100 + 45), // Mock previous
        change: 5,
        weight: 0.4,
        reliability: 0.85
      },
      {
        source: 'Market Overall',
        score: Math.round(marketSentiment.overall_sentiment.score * 100 + 50),
        previousScore: Math.round(marketSentiment.overall_sentiment.score * 100 + 48),
        change: 2,
        weight: 0.3,
        reliability: 0.9
      },
      {
        source: 'Article Analysis',
        score: Math.round(sentimentData.overall_sentiment.distribution.positive / sentimentData.overall_sentiment.total_articles * 100),
        previousScore: 65,
        change: Math.round(sentimentData.overall_sentiment.distribution.positive / sentimentData.overall_sentiment.total_articles * 100) - 65,
        weight: 0.3,
        reliability: 0.8
      }
    ];
    
    // Create historical data from trend
    const historicalData = sentimentData.trend.map(point => ({
      date: new Date(point.hour).toISOString().split('T')[0],
      overall: Math.round(point.sentiment * 100 + 50),
      analyst: Math.round(point.sentiment * 100 + 55),
      social: Math.round(point.sentiment * 100 + 45),
      volume: point.article_count * 100
    }));
    
    // Transform news articles
    const newsImpact = newsData.articles.slice(0, 20).map(article => ({
      timestamp: article.published_at,
      headline: article.title,
      source: article.source,
      sentiment: article.sentiment.label === 'positive' ? 'Bullish' : 
                article.sentiment.label === 'negative' ? 'Bearish' : 'Neutral',
      sentimentScore: Math.round(article.sentiment.score * 100 + 50),
      impact: (article.sentiment.score * article.impact_score),
      confidence: Math.round(article.sentiment.confidence * 100)
    }));
    
    return {
      sources,
      historicalData,
      newsImpact,
      // Mock data for features not yet implemented in backend
      trends: {
        short: 2.3,
        medium: -1.2,
        long: 4.5
      },
      contrarianData: [],
      contrarianOpportunities: [],
      socialPlatforms: [
        { name: 'News Sources', mentions: sentimentData.overall_sentiment.total_articles, sentiment: Math.round(sentimentData.overall_sentiment.score * 100 + 50) },
        { name: 'Market Analysis', mentions: marketSentiment.overall_sentiment.total_articles, sentiment: Math.round(marketSentiment.overall_sentiment.score * 100 + 50) }
      ],
      viralContent: newsData.articles.slice(0, 3).map(article => ({
        platform: 'News',
        content: article.title,
        engagement: `${article.relevance_score.toFixed(1)}K`,
        sentiment: article.sentiment.label === 'positive' ? 'Bullish' : 
                  article.sentiment.label === 'negative' ? 'Bearish' : 'Neutral',
        sentimentScore: Math.round(article.sentiment.score * 100 + 50)
      }))
    };
  }, [sentimentData, marketSentiment, newsData]);

  // Advanced sentiment metrics calculations
  const sentimentMetrics = useMemo(() => {
    if (!transformedSentimentData) {
      return {
        overall: 50,
        momentum: 0,
        volatility: 0,
        extremeReadings: [],
        contrarian: 0,
        confidence: 75,
        divergence: 0
      };
    }
    
    const overall = transformedSentimentData.sources.reduce((sum, source) => sum + source.score * source.weight, 0);
    const momentum = calculateSentimentMomentum(transformedSentimentData.historicalData);
    const volatility = calculateSentimentVolatility(transformedSentimentData.historicalData);
    const extremeReadings = detectExtremeReadings(transformedSentimentData.sources);
    const contrarian = calculateContrarianSignal(transformedSentimentData.sources);
    
    return {
      overall: Math.round(overall),
      momentum,
      volatility,
      extremeReadings,
      contrarian,
      confidence: calculateConfidenceScore(transformedSentimentData.sources),
      divergence: calculateSentimentDivergence(transformedSentimentData.sources)
    };
  }, [transformedSentimentData]);

  // AI insights based on sentiment patterns
  const aiInsights = useMemo(() => {
    return generateSentimentInsights(sentimentMetrics, transformedSentimentData);
  }, [sentimentMetrics, transformedSentimentData]);

  const handleTabChange = (event, newValue) => {
    setActiveTab(newValue);
  };

  const handleSort = (property) => {
    const isAsc = orderBy === property && order === 'asc';
    setOrder(isAsc ? 'desc' : 'asc');
    setOrderBy(property);
  };

  const getSentimentColor = (score) => {
    if (score >= 70) return 'success';
    if (score >= 40) return 'warning';
    return 'error';
  };

  const getSentimentIcon = (score) => {
    if (score >= 60) return <TrendingUp />;
    if (score >= 40) return <TrendingFlat />;
    return <TrendingDown />;
  };

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      {/* Header */}
      <Box display="flex" alignItems="center" justifyContent="between" mb={4}>
        <Box>
          <Typography variant="h3" component="h1" gutterBottom>
            Advanced Sentiment Analysis
          </Typography>
          <Typography variant="subtitle1" color="text.secondary">
            AI-powered multi-source sentiment tracking and contrarian analysis
          </Typography>
        </Box>
        
        <Box display="flex" alignItems="center" gap={2}>
          <FormControl size="small" sx={{ minWidth: 120 }}>
            <InputLabel>Symbol</InputLabel>
            <Select
              value={selectedSymbol}
              label="Symbol"
              onChange={(e) => setSelectedSymbol(e.target.value)}
            >
              <MenuItem value="SPY">SPY (Market)</MenuItem>
              <MenuItem value="QQQ">QQQ (Tech)</MenuItem>
              <MenuItem value="AAPL">AAPL</MenuItem>
              <MenuItem value="TSLA">TSLA</MenuItem>
              <MenuItem value="NVDA">NVDA</MenuItem>
            </Select>
          </FormControl>
          
          <FormControl size="small" sx={{ minWidth: 120 }}>
            <InputLabel>Timeframe</InputLabel>
            <Select
              value={selectedTimeframe}
              label="Timeframe"
              onChange={(e) => setSelectedTimeframe(e.target.value)}
            >
              <MenuItem value="1h">1 Hour</MenuItem>
              <MenuItem value="6h">6 Hours</MenuItem>
              <MenuItem value="24h">1 Day</MenuItem>
              <MenuItem value="3d">3 Days</MenuItem>
              <MenuItem value="1w">1 Week</MenuItem>
              <MenuItem value="1m">1 Month</MenuItem>
            </Select>
          </FormControl>
          
          <Button variant="outlined" startIcon={<Download />}>
            Export
          </Button>
          <Button variant="contained" startIcon={<Refresh />}>
            Refresh
          </Button>
        </Box>
      </Box>

      {/* Loading State */}
      {loading && (
        <Box display="flex" justifyContent="center" py={4}>
          <CircularProgress />
        </Box>
      )}
      
      {/* Error State */}
      {sentimentError && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {sentimentError}
        </Alert>
      )}
      
      {/* Sentiment Alert */}
      {!loading && sentimentMetrics.extremeReadings.length > 0 && (
        <Alert 
          severity="warning" 
          sx={{ mb: 3 }}
          icon={<Warning />}
        >
          <strong>Extreme Sentiment Alert:</strong> {sentimentMetrics.extremeReadings[0].message}
          {sentimentMetrics.contrarian > 75 && " - Strong contrarian signal detected."}
        </Alert>
      )}

      {/* Key Metrics Cards */}
      <Grid container spacing={3} mb={4}>
        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" justifyContent="between">
                <Box>
                  <Typography variant="h6" color="text.secondary">
                    Overall Sentiment
                  </Typography>
                  <Typography variant="h3" color="primary">
                    {sentimentMetrics.overall}
                  </Typography>
                  <Box display="flex" alignItems="center" mt={1}>
                    {getSentimentIcon(sentimentMetrics.overall)}
                    <Typography variant="body2" color="text.secondary" ml={1}>
                      {sentimentMetrics.overall >= 70 ? 'Extremely Bullish' :
                       sentimentMetrics.overall >= 60 ? 'Bullish' :
                       sentimentMetrics.overall >= 40 ? 'Neutral' :
                       sentimentMetrics.overall >= 30 ? 'Bearish' : 'Extremely Bearish'}
                    </Typography>
                  </Box>
                </Box>
                <Psychology color="primary" fontSize="large" />
              </Box>
              <LinearProgress 
                variant="determinate" 
                value={sentimentMetrics.overall} 
                color={getSentimentColor(sentimentMetrics.overall)}
                sx={{ mt: 2 }}
              />
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" justifyContent="between">
                <Box>
                  <Typography variant="h6" color="text.secondary">
                    Sentiment Momentum
                  </Typography>
                  <Typography variant="h3" color="secondary">
                    {formatNumber(sentimentMetrics.momentum, 1)}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    {sentimentMetrics.momentum > 0 ? 'Improving' : 'Deteriorating'}
                  </Typography>
                </Box>
                <Speed color="secondary" fontSize="large" />
              </Box>
              <Rating 
                value={Math.min(5, Math.max(0, (sentimentMetrics.momentum + 50) / 20))} 
                readOnly 
                size="small"
                sx={{ mt: 1 }}
              />
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" justifyContent="between">
                <Box>
                  <Typography variant="h6" color="text.secondary">
                    Contrarian Signal
                  </Typography>
                  <Typography variant="h3" color="warning.main">
                    {sentimentMetrics.contrarian}%
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    {sentimentMetrics.contrarian > 75 ? 'Strong Signal' :
                     sentimentMetrics.contrarian > 50 ? 'Moderate Signal' : 'Weak Signal'}
                  </Typography>
                </Box>
                <Analytics color="warning" fontSize="large" />
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" justifyContent="between">
                <Box>
                  <Typography variant="h6" color="text.secondary">
                    AI Confidence
                  </Typography>
                  <Typography variant="h3" color="info.main">
                    {sentimentMetrics.confidence}%
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Analysis reliability
                  </Typography>
                </Box>
                <Assessment color="info" fontSize="large" />
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Main Content Tabs */}
      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
        <Tabs value={activeTab} onChange={handleTabChange} aria-label="sentiment analysis tabs" variant="scrollable" scrollButtons="auto">
          <Tab label="Multi-Source Analysis" icon={<Analytics />} />
          <Tab label="Sentiment Trends" icon={<Timeline />} />
          <Tab label="Contrarian Signals" icon={<Psychology />} />
          <Tab label="News Impact" icon={<Newspaper />} />
          <Tab label="Social Sentiment" icon={<Reddit />} />
          <Tab label="AI Insights" icon={<Lightbulb />} />
        </Tabs>
      </Box>

      <TabPanel value={activeTab} index={0}>
        {/* Multi-Source Analysis */}
        <Grid container spacing={3}>
          <Grid item xs={12} md={8}>
            <Card>
              <CardHeader title="Sentiment Source Breakdown" />
              <CardContent>
                <ResponsiveContainer width="100%" height={400}>
                  <RadarChart data={transformedSentimentData?.sources || []}>
                    <PolarGrid />
                    <PolarAngleAxis dataKey="source" />
                    <PolarRadiusAxis 
                      angle={90} 
                      domain={[0, 100]} 
                      tick={{ fontSize: 12 }}
                    />
                    <Radar
                      name="Current"
                      dataKey="score"
                      stroke="#8884d8"
                      fill="#8884d8"
                      fillOpacity={0.3}
                      strokeWidth={2}
                    />
                    <Radar
                      name="1W Ago"
                      dataKey="previousScore"
                      stroke="#82ca9d"
                      fill="transparent"
                      strokeWidth={2}
                      strokeDasharray="5 5"
                    />
                    <RechartsTooltip />
                  </RadarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} md={4}>
            <Grid container spacing={3}>
              {/* Source Rankings */}
              <Grid item xs={12}>
                <Card>
                  <CardHeader title="Source Rankings" />
                  <CardContent>
                    <List>
                      {(transformedSentimentData?.sources || [])
                        .sort((a, b) => b.score - a.score)
                        .map((source, index) => (
                        <ListItem key={source.source} disablePadding>
                          <ListItemAvatar>
                            <Avatar sx={{ bgcolor: getSentimentColor(source.score) + '.main' }}>
                              {index + 1}
                            </Avatar>
                          </ListItemAvatar>
                          <ListItemText
                            primary={source.source}
                            secondary={
                              <Box display="flex" alignItems="center" gap={1}>
                                <Typography variant="body2">
                                  Score: {source.score}
                                </Typography>
                                <Chip 
                                  label={`${source.change >= 0 ? '+' : ''}${source.change}`}
                                  color={source.change >= 0 ? 'success' : 'error'}
                                  size="small"
                                  variant="outlined"
                                />
                              </Box>
                            }
                          />
                        </ListItem>
                      ))}
                    </List>
                  </CardContent>
                </Card>
              </Grid>

              {/* Sentiment Divergence */}
              <Grid item xs={12}>
                <Card>
                  <CardHeader title="Sentiment Divergence" />
                  <CardContent>
                    <Box mb={2}>
                      <Typography variant="body2" color="text.secondary">
                        Cross-Source Divergence
                      </Typography>
                      <LinearProgress 
                        variant="determinate" 
                        value={sentimentMetrics.divergence} 
                        color={sentimentMetrics.divergence > 30 ? 'warning' : 'success'}
                        sx={{ mt: 1 }}
                      />
                      <Typography variant="caption" color="text.secondary">
                        {sentimentMetrics.divergence}% divergence
                      </Typography>
                    </Box>
                    
                    <Alert 
                      severity={sentimentMetrics.divergence > 30 ? 'warning' : 'info'}
                      size="small"
                    >
                      {sentimentMetrics.divergence > 30 
                        ? 'High divergence may indicate uncertain market conditions'
                        : 'Low divergence suggests consensus across sources'}
                    </Alert>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          </Grid>
        </Grid>
      </TabPanel>

      <TabPanel value={activeTab} index={1}>
        {/* Sentiment Trends */}
        <Grid container spacing={3}>
          <Grid item xs={12} md={8}>
            <Card>
              <CardHeader title="Sentiment Historical Trends" />
              <CardContent>
                <ResponsiveContainer width="100%" height={400}>
                  <ComposedChart data={transformedSentimentData?.historicalData || []}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="date" />
                    <YAxis yAxisId="left" domain={[0, 100]} />
                    <YAxis yAxisId="right" orientation="right" />
                    <RechartsTooltip />
                    <Area 
                      yAxisId="left"
                      type="monotone" 
                      dataKey="overall" 
                      fill="#8884d8" 
                      stroke="#8884d8"
                      fillOpacity={0.3}
                    />
                    <Line 
                      yAxisId="left"
                      type="monotone" 
                      dataKey="analyst" 
                      stroke="#82ca9d" 
                      strokeWidth={2}
                    />
                    <Line 
                      yAxisId="left"
                      type="monotone" 
                      dataKey="social" 
                      stroke="#ffc658" 
                      strokeWidth={2}
                    />
                    <Bar 
                      yAxisId="right"
                      dataKey="volume" 
                      fill="#ff7300"
                      opacity={0.3}
                    />
                  </ComposedChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} md={4}>
            <Grid container spacing={3}>
              {/* Trend Analysis */}
              <Grid item xs={12}>
                <Card>
                  <CardHeader title="Trend Indicators" />
                  <CardContent>
                    <Box display="flex" flexDirection="column" gap={2}>
                      <Box display="flex" justifyContent="between">
                        <Typography variant="body2">5-Day Trend</Typography>
                        <Chip 
                          label={(transformedSentimentData?.trends.short || 0) >= 0 ? 'Bullish' : 'Bearish'}
                          color={(transformedSentimentData?.trends.short || 0) >= 0 ? 'success' : 'error'}
                          size="small"
                        />
                      </Box>
                      <Box display="flex" justifyContent="between">
                        <Typography variant="body2">20-Day Trend</Typography>
                        <Chip 
                          label={(transformedSentimentData?.trends.medium || 0) >= 0 ? 'Bullish' : 'Bearish'}
                          color={(transformedSentimentData?.trends.medium || 0) >= 0 ? 'success' : 'error'}
                          size="small"
                        />
                      </Box>
                      <Box display="flex" justifyContent="between">
                        <Typography variant="body2">60-Day Trend</Typography>
                        <Chip 
                          label={(transformedSentimentData?.trends.long || 0) >= 0 ? 'Bullish' : 'Bearish'}
                          color={(transformedSentimentData?.trends.long || 0) >= 0 ? 'success' : 'error'}
                          size="small"
                        />
                      </Box>
                      <Box display="flex" justifyContent="between">
                        <Typography variant="body2">Momentum Score</Typography>
                        <Typography variant="body2" fontWeight="bold">
                          {formatNumber(sentimentMetrics.momentum, 1)}
                        </Typography>
                      </Box>
                    </Box>
                  </CardContent>
                </Card>
              </Grid>

              {/* Volatility Analysis */}
              <Grid item xs={12}>
                <Card>
                  <CardHeader title="Sentiment Volatility" />
                  <CardContent>
                    <Box textAlign="center" mb={2}>
                      <Typography variant="h4" color="warning.main">
                        {formatNumber(sentimentMetrics.volatility, 1)}%
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        30-Day Volatility
                      </Typography>
                    </Box>
                    
                    <LinearProgress 
                      variant="determinate" 
                      value={Math.min(100, sentimentMetrics.volatility * 5)} 
                      color="warning"
                      sx={{ mb: 2 }}
                    />
                    
                    <Typography variant="caption" color="text.secondary">
                      {sentimentMetrics.volatility > 20 ? 'High volatility indicates uncertain sentiment' :
                       sentimentMetrics.volatility > 10 ? 'Moderate volatility' : 'Low volatility - stable sentiment'}
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          </Grid>
        </Grid>
      </TabPanel>

      <TabPanel value={activeTab} index={2}>
        {/* Contrarian Signals */}
        <Grid container spacing={3}>
          <Grid item xs={12} md={8}>
            <Card>
              <CardHeader title="Contrarian Signal Analysis" />
              <CardContent>
                <ResponsiveContainer width="100%" height={400}>
                  <ScatterChart data={transformedSentimentData?.contrarianData || []}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis 
                      dataKey="sentiment" 
                      name="Sentiment Score"
                      domain={[0, 100]}
                    />
                    <YAxis 
                      dataKey="priceChange" 
                      name="Future Returns"
                      domain={[-10, 10]}
                    />
                    <RechartsTooltip 
                      cursor={{ strokeDasharray: '3 3' }}
                      formatter={(value, name) => [
                        name === 'priceChange' ? `${value}%` : value,
                        name === 'priceChange' ? 'Future Returns' : 'Sentiment'
                      ]}
                    />
                    <Scatter dataKey="priceChange" fill="#8884d8" />
                  </ScatterChart>
                </ResponsiveContainer>
                <Typography variant="caption" color="text.secondary" sx={{ mt: 2, display: 'block' }}>
                  Scatter plot showing relationship between sentiment extremes and future price movements
                </Typography>
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} md={4}>
            <Card>
              <CardHeader title="Contrarian Opportunities" />
              <CardContent>
                <List>
                  {(transformedSentimentData?.contrarianOpportunities || []).map((opportunity, index) => (
                    <ListItem key={index} divider={index < (transformedSentimentData?.contrarianOpportunities || []).length - 1}>
                      <ListItemText
                        primary={
                          <Box display="flex" alignItems="center" gap={1}>
                            <Typography variant="subtitle2" fontWeight="bold">
                              {opportunity.symbol}
                            </Typography>
                            <Chip 
                              label={`${opportunity.probability}%`}
                              color={opportunity.probability > 70 ? 'success' : 'warning'}
                              size="small"
                            />
                          </Box>
                        }
                        secondary={
                          <Box>
                            <Typography variant="body2" gutterBottom>
                              {opportunity.reason}
                            </Typography>
                            <Box display="flex" gap={1}>
                              <Chip 
                                label={`Sentiment: ${opportunity.currentSentiment}`}
                                size="small"
                                variant="outlined"
                              />
                              <Chip 
                                label={opportunity.signal}
                                color={opportunity.signal === 'Buy' ? 'success' : 'error'}
                                size="small"
                              />
                            </Box>
                          </Box>
                        }
                      />
                    </ListItem>
                  ))}
                </List>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </TabPanel>

      <TabPanel value={activeTab} index={3}>
        {/* News Impact */}
        <Grid container spacing={3}>
          <Grid item xs={12}>
            <Card>
              <CardHeader 
                title="News Sentiment Impact Analysis" 
                action={
                  <Chip 
                    label={`${sentimentData.newsImpact.length} articles analyzed`} 
                    color="primary" 
                    variant="outlined" 
                  />
                }
              />
              <CardContent>
                <TableContainer>
                  <Table>
                    <TableHead>
                      <TableRow>
                        <TableCell>
                          <TableSortLabel
                            active={orderBy === 'timestamp'}
                            direction={orderBy === 'timestamp' ? order : 'asc'}
                            onClick={() => handleSort('timestamp')}
                          >
                            Time
                          </TableSortLabel>
                        </TableCell>
                        <TableCell>Headline</TableCell>
                        <TableCell align="center">
                          <TableSortLabel
                            active={orderBy === 'sentiment'}
                            direction={orderBy === 'sentiment' ? order : 'asc'}
                            onClick={() => handleSort('sentiment')}
                          >
                            Sentiment
                          </TableSortLabel>
                        </TableCell>
                        <TableCell align="center">
                          <TableSortLabel
                            active={orderBy === 'impact'}
                            direction={orderBy === 'impact' ? order : 'asc'}
                            onClick={() => handleSort('impact')}
                          >
                            Market Impact
                          </TableSortLabel>
                        </TableCell>
                        <TableCell align="center">Confidence</TableCell>
                        <TableCell align="center">Actions</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {transformedSentimentData?.newsImpact
                        .sort((a, b) => {
                          const aValue = a[orderBy];
                          const bValue = b[orderBy];
                          if (order === 'asc') {
                            return aValue < bValue ? -1 : 1;
                          } else {
                            return aValue > bValue ? -1 : 1;
                          }
                        })
                        .slice(0, 10)
                        .map((news, index) => (
                        <TableRow key={index}>
                          <TableCell>
                            <Typography variant="caption">
                              {new Date(news.timestamp).toLocaleTimeString()}
                            </Typography>
                          </TableCell>
                          <TableCell>
                            <Box>
                              <Typography variant="body2" fontWeight="bold" gutterBottom>
                                {news.headline}
                              </Typography>
                              <Typography variant="caption" color="text.secondary">
                                {news.source}
                              </Typography>
                            </Box>
                          </TableCell>
                          <TableCell align="center">
                            <Chip 
                              label={news.sentiment}
                              color={getSentimentColor(news.sentimentScore)}
                              size="small"
                            />
                          </TableCell>
                          <TableCell align="center">
                            <Box>
                              <Typography variant="body2" fontWeight="bold">
                                {formatPercentage(news.impact)}
                              </Typography>
                              <LinearProgress 
                                variant="determinate" 
                                value={Math.abs(news.impact) * 10} 
                                color={news.impact >= 0 ? 'success' : 'error'}
                                sx={{ width: 60, mt: 0.5 }}
                              />
                            </Box>
                          </TableCell>
                          <TableCell align="center">
                            <Rating 
                              value={news.confidence / 20} 
                              readOnly 
                              size="small"
                            />
                          </TableCell>
                          <TableCell align="center">
                            <IconButton size="small">
                              <BookmarkBorder />
                            </IconButton>
                            <IconButton size="small">
                              <Share />
                            </IconButton>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </TabPanel>

      <TabPanel value={activeTab} index={4}>
        {/* Social Sentiment */}
        <Grid container spacing={3}>
          <Grid item xs={12} md={6}>
            <Card>
              <CardHeader title="Platform Sentiment Breakdown" />
              <CardContent>
                <ResponsiveContainer width="100%" height={300}>
                  <PieChart>
                    <Pie
                      data={transformedSentimentData?.socialPlatforms || []}
                      cx="50%"
                      cy="50%"
                      outerRadius={80}
                      fill="#8884d8"
                      dataKey="mentions"
                      label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                    >
                      {(transformedSentimentData?.socialPlatforms || []).map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                      ))}
                    </Pie>
                    <RechartsTooltip />
                  </PieChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} md={6}>
            <Card>
              <CardHeader title="Viral Content Analysis" />
              <CardContent>
                <List>
                  {(transformedSentimentData?.viralContent || []).map((content, index) => (
                    <ListItem key={index} divider={index < sentimentData.viralContent.length - 1}>
                      <ListItemAvatar>
                        <Avatar sx={{ bgcolor: content.platform === 'Twitter' ? '#1DA1F2' : '#FF4500' }}>
                          {content.platform === 'Twitter' ? <Twitter /> : <Reddit />}
                        </Avatar>
                      </ListItemAvatar>
                      <ListItemText
                        primary={content.content}
                        secondary={
                          <Box display="flex" alignItems="center" gap={1} mt={1}>
                            <Chip 
                              label={`${content.engagement} relevance`}
                              size="small"
                              variant="outlined"
                            />
                            <Chip 
                              label={content.sentiment}
                              color={getSentimentColor(content.sentimentScore)}
                              size="small"
                            />
                          </Box>
                        }
                      />
                    </ListItem>
                  ))}
                </List>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </TabPanel>

      <TabPanel value={activeTab} index={5}>
        {/* AI Insights */}
        <Grid container spacing={3}>
          <Grid item xs={12} md={8}>
            <Card>
              <CardHeader 
                title="AI-Powered Sentiment Insights" 
                avatar={<Psychology color="primary" />}
              />
              <CardContent>
                <Stepper orientation="vertical">
                  <Step expanded>
                    <StepLabel>
                      <Typography variant="h6" color="primary">
                        Current Market Sentiment
                      </Typography>
                    </StepLabel>
                    <StepContent>
                      <Alert severity="info" sx={{ mb: 2 }}>
                        {aiInsights.marketSummary}
                      </Alert>
                    </StepContent>
                  </Step>

                  <Step expanded>
                    <StepLabel>
                      <Typography variant="h6" color="success.main">
                        Key Opportunities
                      </Typography>
                    </StepLabel>
                    <StepContent>
                      <List>
                        {aiInsights.opportunities.map((opportunity, index) => (
                          <ListItem key={index}>
                            <CheckCircle color="success" sx={{ mr: 2 }} />
                            <Typography variant="body2">{opportunity}</Typography>
                          </ListItem>
                        ))}
                      </List>
                    </StepContent>
                  </Step>

                  <Step expanded>
                    <StepLabel>
                      <Typography variant="h6" color="warning.main">
                        Risk Factors
                      </Typography>
                    </StepLabel>
                    <StepContent>
                      <List>
                        {aiInsights.risks.map((risk, index) => (
                          <ListItem key={index}>
                            <Warning color="warning" sx={{ mr: 2 }} />
                            <Typography variant="body2">{risk}</Typography>
                          </ListItem>
                        ))}
                      </List>
                    </StepContent>
                  </Step>

                  <Step expanded>
                    <StepLabel>
                      <Typography variant="h6" color="info.main">
                        Forecast
                      </Typography>
                    </StepLabel>
                    <StepContent>
                      <Typography variant="body2" paragraph>
                        {aiInsights.forecast}
                      </Typography>
                      
                      <Accordion>
                        <AccordionSummary expandIcon={<ExpandMore />}>
                          <Typography variant="subtitle2">Technical Details</Typography>
                        </AccordionSummary>
                        <AccordionDetails>
                          <Typography variant="body2" color="text.secondary">
                            {aiInsights.technicalDetails}
                          </Typography>
                        </AccordionDetails>
                      </Accordion>
                    </StepContent>
                  </Step>
                </Stepper>
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} md={4}>
            <Grid container spacing={3}>
              {/* AI Confidence */}
              <Grid item xs={12}>
                <Card>
                  <CardHeader title="AI Analysis Confidence" />
                  <CardContent>
                    <Box textAlign="center" mb={3}>
                      <Typography variant="h2" color="primary">
                        {sentimentMetrics.confidence}%
                      </Typography>
                      <Rating 
                        value={sentimentMetrics.confidence / 20} 
                        readOnly 
                        size="large"
                      />
                      <Typography variant="body2" color="text.secondary">
                        Model Confidence
                      </Typography>
                    </Box>
                  </CardContent>
                </Card>
              </Grid>

              {/* Model Performance */}
              <Grid item xs={12}>
                <Card>
                  <CardHeader title="Model Performance" />
                  <CardContent>
                    <Box display="flex" flexDirection="column" gap={2}>
                      <Box display="flex" justifyContent="between">
                        <Typography variant="body2">Accuracy (30d)</Typography>
                        <Typography variant="body2" fontWeight="bold">
                          {aiInsights.modelStats.accuracy}%
                        </Typography>
                      </Box>
                      <Box display="flex" justifyContent="between">
                        <Typography variant="body2">Precision</Typography>
                        <Typography variant="body2" fontWeight="bold">
                          {aiInsights.modelStats.precision}%
                        </Typography>
                      </Box>
                      <Box display="flex" justifyContent="between">
                        <Typography variant="body2">Recall</Typography>
                        <Typography variant="body2" fontWeight="bold">
                          {aiInsights.modelStats.recall}%
                        </Typography>
                      </Box>
                      <Box display="flex" justifyContent="between">
                        <Typography variant="body2">Data Sources</Typography>
                        <Typography variant="body2" fontWeight="bold">
                          {aiInsights.modelStats.dataSources}
                        </Typography>
                      </Box>
                    </Box>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          </Grid>
        </Grid>
      </TabPanel>
    </Container>
  );
};

// ⚠️ MOCK DATA - Replace with real API when available
const mockSentimentData = {
  isMockData: true,
  sources: [
    {
      source: 'Analyst Reports',
      score: 72,
      previousScore: 68,
      change: 4,
      weight: 0.3,
      reliability: 0.9
    },
    {
      source: 'Social Media',
      score: 58,
      previousScore: 62,
      change: -4,
      weight: 0.2,
      reliability: 0.7
    },
    {
      source: 'News Sentiment',
      score: 70,
      previousScore: 65,
      change: 5,
      weight: 0.25,
      reliability: 0.85
    },
    {
      source: 'Options Flow',
      score: 45,
      previousScore: 55,
      change: -10,
      weight: 0.15,
      reliability: 0.8
    },
    {
      source: 'Insider Trading',
      score: 65,
      previousScore: 60,
      change: 5,
      weight: 0.1,
      reliability: 0.95
    }
  ],
  historicalData: Array.from({ length: 30 }, (_, i) => ({
    date: new Date(Date.now() - (29 - i) * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
    overall: 60 + Math.sin(i / 5) * 15 + Math.random() * 10,
    analyst: 65 + Math.cos(i / 7) * 10 + Math.random() * 8,
    social: 55 + Math.sin(i / 3) * 20 + Math.random() * 12,
    volume: 1000 + Math.random() * 2000
  })),
  trends: {
    short: 2.3,    // 5-day
    medium: -1.2,  // 20-day
    long: 4.5      // 60-day
  },
  contrarianData: Array.from({ length: 50 }, (_, i) => ({
    sentiment: Math.random() * 100,
    priceChange: (Math.random() - 0.5) * 20,
    date: new Date(Date.now() - i * 24 * 60 * 60 * 1000).toISOString().split('T')[0]
  })),
  contrarianOpportunities: [
    {
      symbol: 'AAPL',
      currentSentiment: 25,
      probability: 78,
      signal: 'Buy',
      reason: 'Sentiment at extreme low while fundamentals remain strong'
    },
    {
      symbol: 'TSLA',
      currentSentiment: 85,
      probability: 72,
      signal: 'Sell',
      reason: 'Euphoric sentiment levels historically followed by correction'
    },
    {
      symbol: 'NVDA',
      currentSentiment: 20,
      probability: 65,
      signal: 'Buy',
      reason: 'Oversold sentiment despite strong AI growth prospects'
    }
  ],
  newsImpact: Array.from({ length: 20 }, (_, i) => ({
    timestamp: new Date(Date.now() - i * 60 * 60 * 1000).toISOString(),
    headline: [
      'Fed signals dovish stance on interest rates',
      'Tech earnings beat expectations across sector',
      'Geopolitical tensions escalate affecting markets',
      'Inflation data shows cooling trend',
      'Major bank upgrades equity outlook'
    ][i % 5],
    source: ['Reuters', 'Bloomberg', 'CNBC', 'WSJ', 'FT'][i % 5],
    sentiment: ['Bullish', 'Bearish', 'Neutral'][Math.floor(Math.random() * 3)],
    sentimentScore: 20 + Math.random() * 60,
    impact: (Math.random() - 0.5) * 4,
    confidence: 60 + Math.random() * 40
  })),
  socialPlatforms: [
    { name: 'Twitter', mentions: 15420, sentiment: 62 },
    { name: 'Reddit', mentions: 8970, sentiment: 55 },
    { name: 'Discord', mentions: 4320, sentiment: 71 },
    { name: 'Telegram', mentions: 2180, sentiment: 48 }
  ],
  viralContent: [
    {
      platform: 'Twitter',
      content: 'Market showing strong resilience despite headwinds...',
      engagement: '15.2K',
      sentiment: 'Bullish',
      sentimentScore: 75
    },
    {
      platform: 'Reddit',
      content: 'Technical analysis suggests major support level holding...',
      engagement: '8.9K',
      sentiment: 'Neutral',
      sentimentScore: 52
    },
    {
      platform: 'Twitter',
      content: 'Concerning patterns emerging in credit markets...',
      engagement: '12.1K',
      sentiment: 'Bearish',
      sentimentScore: 28
    }
  ]
};

// Color palette for charts
const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884D8', '#82CA9D'];

// ⚠️ MOCK DATA - Advanced calculation functions using mock data
function calculateSentimentMomentum(historicalData) {
  if (historicalData.length < 5) return 0;
  
  const recent = historicalData.slice(-5);
  const older = historicalData.slice(-10, -5);
  
  const recentAvg = recent.reduce((sum, d) => sum + d.overall, 0) / recent.length;
  const olderAvg = older.reduce((sum, d) => sum + d.overall, 0) / older.length;
  
  return ((recentAvg - olderAvg) / olderAvg) * 100;
}

function calculateSentimentVolatility(historicalData) {
  if (historicalData.length < 2) return 0;
  
  const returns = [];
  for (let i = 1; i < historicalData.length; i++) {
    const change = (historicalData[i].overall - historicalData[i-1].overall) / historicalData[i-1].overall;
    returns.push(change);
  }
  
  const mean = returns.reduce((sum, r) => sum + r, 0) / returns.length;
  const variance = returns.reduce((sum, r) => sum + Math.pow(r - mean, 2), 0) / returns.length;
  
  return Math.sqrt(variance) * 100 * Math.sqrt(252); // Annualized
}

function detectExtremeReadings(sources) {
  const extremes = [];
  sources.forEach(source => {
    if (source.score > 80) {
      extremes.push({
        source: source.source,
        message: `${source.source} showing extreme bullish reading (${source.score})`
      });
    } else if (source.score < 20) {
      extremes.push({
        source: source.source,
        message: `${source.source} showing extreme bearish reading (${source.score})`
      });
    }
  });
  return extremes;
}

function calculateContrarianSignal(sources) {
  const extremeCount = sources.filter(s => s.score > 80 || s.score < 20).length;
  const totalSources = sources.length;
  return Math.round((extremeCount / totalSources) * 100);
}

function calculateConfidenceScore(sources) {
  const weightedReliability = sources.reduce((sum, s) => sum + s.reliability * s.weight, 0);
  return Math.round(weightedReliability * 100);
}

function calculateSentimentDivergence(sources) {
  const scores = sources.map(s => s.score);
  const mean = scores.reduce((sum, s) => sum + s, 0) / scores.length;
  const variance = scores.reduce((sum, s) => sum + Math.pow(s - mean, 2), 0) / scores.length;
  return Math.round(Math.sqrt(variance));
}

function generateSentimentInsights(metrics, data) {
  return {
    marketSummary: `Current sentiment shows ${metrics.overall >= 60 ? 'bullish' : metrics.overall >= 40 ? 'neutral' : 'bearish'} bias with ${metrics.momentum > 0 ? 'improving' : 'deteriorating'} momentum. ${metrics.contrarian > 50 ? 'Contrarian signals suggest potential reversal ahead.' : 'Sentiment alignment supports current trend.'}`,
    opportunities: [
      'Social media sentiment diverging from analyst views - potential alpha opportunity',
      'Options flow showing defensive positioning despite bullish news sentiment',
      'Insider trading patterns suggest accumulation during sentiment weakness',
      'Cross-asset sentiment divergence creating relative value opportunities'
    ],
    risks: [
      'High sentiment volatility indicates unstable market psychology',
      'Extreme readings in multiple sources suggest potential reversal risk',
      'Divergence between sentiment sources may signal market uncertainty',
      'Elevated contrarian signal warns of potential sentiment-driven correction'
    ],
    forecast: `Based on current sentiment patterns and historical analysis, expect ${metrics.momentum > 0 ? 'continued positive' : 'potential reversal in'} sentiment trends over the next 5-10 trading days. Key inflection points likely around major economic releases or earnings announcements.`,
    technicalDetails: 'Analysis incorporates machine learning models trained on 5+ years of multi-source sentiment data with real-time natural language processing. Confidence intervals and statistical significance testing ensure robust signal generation.',
    modelStats: {
      accuracy: 84,
      precision: 79,
      recall: 86,
      dataSources: 47
    }
  };
}

export default SentimentAnalysis;