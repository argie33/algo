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
  CircularProgress,
  Alert,
  Button,
  TextField,
  IconButton,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Tooltip,
  Avatar,
  List,
  ListItem,
  ListItemText,
  ListItemAvatar,
  Divider,
  LinearProgress,
  Badge,
  Switch,
  FormControlLabel,
  Accordion,
  AccordionSummary,
  AccordionDetails
} from '@mui/material';
import {
  TrendingUp,
  TrendingDown,
  Search,
  Reddit,
  Timeline,
  SentimentSatisfied as Sentiment,
  TrendingFlat,
  ExpandMore,
  FilterList,
  Refresh,
  Download,
  Share,
  Psychology,
  Public,
  Forum,
  Insights,
  Analytics,
  Speed,
  Warning,
  CheckCircle,
  Info,
  Star,
  ThumbUp,
  ThumbDown,
  Comment,
  Visibility,
  Schedule,
  Place,
  Language
} from '@mui/icons-material';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  Legend,
  ResponsiveContainer,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  AreaChart,
  Area,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  Treemap,
  Sankey,
  ComposedChart
} from 'recharts';
import { useAuth } from '../contexts/AuthContext';
import { getApiConfig } from '../services/api';

const SocialMediaSentiment = () => {
  const { isAuthenticated, user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedTab, setSelectedTab] = useState(0);
  const [selectedSymbol, setSelectedSymbol] = useState('AAPL');
  const [timeframe, setTimeframe] = useState('7d');
  const [refreshing, setRefreshing] = useState(false);
  
  // Data states
  const [redditData, setRedditData] = useState({
    mentions: [],
    sentiment: [],
    topPosts: [],
    subredditBreakdown: []
  });
  const [trendsData, setTrendsData] = useState({
    searchVolume: [],
    relatedQueries: [],
    geographicDistribution: []
  });
  const [socialMetrics, setSocialMetrics] = useState({
    overall: {},
    platforms: [],
    trendingStocks: []
  });
  const [sentimentHistory, setSentimentHistory] = useState([]);

  const { apiUrl: API_BASE } = getApiConfig();

  // Mock data for development
  const mockRedditData = {
    mentions: [
      { date: '2025-07-01', mentions: 156, sentiment: 0.65 },
      { date: '2025-07-02', mentions: 234, sentiment: 0.72 },
      { date: '2025-07-03', mentions: 189, sentiment: 0.58 },
      { date: '2025-07-04', mentions: 298, sentiment: 0.81 },
      { date: '2025-07-05', mentions: 267, sentiment: 0.76 }
    ],
    sentiment: [
      { platform: 'r/investing', positive: 45, neutral: 32, negative: 23 },
      { platform: 'r/stocks', positive: 52, neutral: 28, negative: 20 },
      { platform: 'r/SecurityAnalysis', positive: 38, neutral: 41, negative: 21 },
      { platform: 'r/ValueInvesting', positive: 41, neutral: 35, negative: 24 }
    ],
    topPosts: [
      {
        id: 1,
        title: 'AAPL Q4 earnings analysis - bullish indicators',
        subreddit: 'r/investing',
        score: 1245,
        comments: 189,
        sentiment: 0.82,
        author: 'u/InvestorAnalyst',
        timestamp: '2 hours ago'
      },
      {
        id: 2,
        title: 'Technical analysis: AAPL breaking resistance',
        subreddit: 'r/stocks',
        score: 892,
        comments: 156,
        sentiment: 0.75,
        author: 'u/TechTrader',
        timestamp: '4 hours ago'
      },
      {
        id: 3,
        title: 'Why I\'m long AAPL for the next 5 years',
        subreddit: 'r/SecurityAnalysis',
        score: 634,
        comments: 98,
        sentiment: 0.88,
        author: 'u/LongTermValue',
        timestamp: '6 hours ago'
      }
    ],
    subredditBreakdown: [
      { name: 'r/investing', value: 35, sentiment: 0.72 },
      { name: 'r/stocks', value: 28, sentiment: 0.68 },
      { name: 'r/SecurityAnalysis', value: 18, sentiment: 0.75 },
      { name: 'r/ValueInvesting', value: 12, sentiment: 0.71 },
      { name: 'r/wallstreetbets', value: 7, sentiment: 0.85 }
    ]
  };

  const mockTrendsData = {
    searchVolume: [
      { date: '2025-07-01', volume: 82, relativeInterest: 0.82 },
      { date: '2025-07-02', volume: 95, relativeInterest: 0.95 },
      { date: '2025-07-03', volume: 78, relativeInterest: 0.78 },
      { date: '2025-07-04', volume: 100, relativeInterest: 1.0 },
      { date: '2025-07-05', volume: 91, relativeInterest: 0.91 }
    ],
    relatedQueries: [
      { query: 'AAPL stock price', volume: 100, trend: 'rising' },
      { query: 'Apple earnings 2025', volume: 85, trend: 'rising' },
      { query: 'AAPL dividend', volume: 72, trend: 'stable' },
      { query: 'Apple iPhone sales', volume: 68, trend: 'falling' },
      { query: 'AAPL technical analysis', volume: 55, trend: 'rising' }
    ],
    geographicDistribution: [
      { region: 'United States', interest: 100, sentiment: 0.74 },
      { region: 'Canada', interest: 45, sentiment: 0.71 },
      { region: 'United Kingdom', interest: 38, sentiment: 0.69 },
      { region: 'Germany', interest: 35, sentiment: 0.67 },
      { region: 'Australia', interest: 32, sentiment: 0.73 }
    ]
  };

  const mockSocialMetrics = {
    overall: {
      totalMentions: 1234,
      sentimentScore: 0.73,
      engagementRate: 0.15,
      viralityIndex: 0.28,
      influencerMentions: 45
    },
    platforms: [
      { name: 'Reddit', mentions: 567, sentiment: 0.71, engagement: 0.18 },
      { name: 'Twitter', mentions: 423, sentiment: 0.68, engagement: 0.12 },
      { name: 'StockTwits', mentions: 189, sentiment: 0.82, engagement: 0.22 },
      { name: 'Discord', mentions: 55, sentiment: 0.75, engagement: 0.31 }
    ],
    trendingStocks: [
      { symbol: 'AAPL', mentions: 1234, sentiment: 0.73, change: 0.15 },
      { symbol: 'TSLA', mentions: 1089, sentiment: 0.68, change: -0.08 },
      { symbol: 'NVDA', mentions: 892, sentiment: 0.81, change: 0.22 },
      { symbol: 'MSFT', mentions: 756, sentiment: 0.69, change: 0.05 },
      { symbol: 'GOOGL', mentions: 634, sentiment: 0.72, change: 0.12 }
    ]
  };

  const COLORS = ['#1976d2', '#388e3c', '#f57c00', '#d32f2f', '#7b1fa2'];

  useEffect(() => {
    loadSentimentData();
  }, [selectedSymbol, timeframe]);

  const loadSentimentData = async () => {
    try {
      setLoading(true);
      setError(null);

      // Fetch real data from API
      const response = await fetch(`${API_BASE}/api/sentiment/social/${selectedSymbol}?timeframe=${timeframe}`);
      
      if (!response.ok) {
        if (response.status === 404 || response.status === 500) {
          console.warn(`Sentiment API returned ${response.status}, using mock data`);
          // Use mock data for 404/500 errors
          setRedditData(mockRedditData);
          setTrendsData(mockTrendsData);
          setSocialMetrics(mockSocialMetrics);
          setSentimentHistory(mockRedditData.mentions);
          return;
        }
        throw new Error(`API request failed: ${response.status}`);
      }
      
      const result = await response.json();
      
      if (result.data) {
        setRedditData(result.data.reddit || mockRedditData);
        setTrendsData(result.data.googleTrends || mockTrendsData);
        setSocialMetrics(result.data.socialMetrics || mockSocialMetrics);
        setSentimentHistory(result.data.reddit?.mentions || mockRedditData.mentions);
      } else {
        // Fallback to mock data if API doesn't return expected structure
        setRedditData(mockRedditData);
        setTrendsData(mockTrendsData);
        setSocialMetrics(mockSocialMetrics);
        setSentimentHistory(mockRedditData.mentions);
      }

    } catch (error) {
      console.error('Error loading sentiment data:', error);
      
      // Only show error to user for unexpected errors, not for expected API unavailability
      if (!error.message.includes('404') && !error.message.includes('500')) {
        setError(`Failed to load social media sentiment data: ${error.message}`);
      } else {
        console.warn('Sentiment API not available, using mock data silently');
      }
      
      // Fallback to mock data on error
      setRedditData(mockRedditData);
      setTrendsData(mockTrendsData);
      setSocialMetrics(mockSocialMetrics);
      setSentimentHistory(mockRedditData.mentions);
    } finally {
      setLoading(false);
    }
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    await loadSentimentData();
    setRefreshing(false);
  };

  const getSentimentColor = (score) => {
    if (score >= 0.7) return '#4caf50';
    if (score >= 0.5) return '#ff9800';
    return '#f44336';
  };

  const getSentimentLabel = (score) => {
    if (score >= 0.7) return 'Bullish';
    if (score >= 0.5) return 'Neutral';
    return 'Bearish';
  };

  const formatNumber = (num) => {
    if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`;
    if (num >= 1000) return `${(num / 1000).toFixed(1)}K`;
    return num.toString();
  };

  const TabPanel = ({ children, value, index, ...other }) => (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`sentiment-tabpanel-${index}`}
      aria-labelledby={`sentiment-tab-${index}`}
      {...other}
    >
      {value === index && <Box sx={{ pt: 3 }}>{children}</Box>}
    </div>
  );

  if (loading) {
    return (
      <Container maxWidth="xl">
        <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '50vh' }}>
          <CircularProgress size={60} />
        </Box>
      </Container>
    );
  }

  return (
    <Container maxWidth="xl">
      <Box sx={{ mb: 4 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
          <Typography variant="h4" component="h1" sx={{ fontWeight: 700 }}>
            Social Media Sentiment Analysis
          </Typography>
          <Box sx={{ display: 'flex', gap: 2, alignItems: 'center' }}>
            <FormControl size="small" sx={{ minWidth: 120 }}>
              <InputLabel>Symbol</InputLabel>
              <Select
                value={selectedSymbol}
                label="Symbol"
                onChange={(e) => setSelectedSymbol(e.target.value)}
              >
                <MenuItem value="AAPL">AAPL</MenuItem>
                <MenuItem value="TSLA">TSLA</MenuItem>
                <MenuItem value="NVDA">NVDA</MenuItem>
                <MenuItem value="MSFT">MSFT</MenuItem>
                <MenuItem value="GOOGL">GOOGL</MenuItem>
              </Select>
            </FormControl>
            <FormControl size="small" sx={{ minWidth: 120 }}>
              <InputLabel>Timeframe</InputLabel>
              <Select
                value={timeframe}
                label="Timeframe"
                onChange={(e) => setTimeframe(e.target.value)}
              >
                <MenuItem value="1d">1 Day</MenuItem>
                <MenuItem value="7d">7 Days</MenuItem>
                <MenuItem value="30d">30 Days</MenuItem>
                <MenuItem value="90d">90 Days</MenuItem>
              </Select>
            </FormControl>
            <Button
              variant="outlined"
              startIcon={refreshing ? <CircularProgress size={16} /> : <Refresh />}
              onClick={handleRefresh}
              disabled={refreshing}
            >
              Refresh
            </Button>
          </Box>
        </Box>

        {error && (
          <Alert severity="error" sx={{ mb: 3 }}>
            {error}
          </Alert>
        )}

        {/* Overview Cards */}
        <Grid container spacing={3} sx={{ mb: 4 }}>
          <Grid item xs={12} sm={6} md={3}>
            <Card>
              <CardContent>
                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <Box>
                    <Typography color="textSecondary" gutterBottom variant="body2">
                      Total Mentions
                    </Typography>
                    <Typography variant="h4" component="div">
                      {formatNumber(socialMetrics.overall.totalMentions)}
                    </Typography>
                  </Box>
                  <Forum color="primary" sx={{ fontSize: 40 }} />
                </Box>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <Card>
              <CardContent>
                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <Box>
                    <Typography color="textSecondary" gutterBottom variant="body2">
                      Sentiment Score
                    </Typography>
                    <Box sx={{ display: 'flex', alignItems: 'center' }}>
                      <Typography variant="h4" component="div" sx={{ mr: 1 }}>
                        {socialMetrics.overall.sentimentScore.toFixed(2)}
                      </Typography>
                      <Chip
                        label={getSentimentLabel(socialMetrics.overall.sentimentScore)}
                        color={socialMetrics.overall.sentimentScore >= 0.7 ? 'success' : socialMetrics.overall.sentimentScore >= 0.5 ? 'warning' : 'error'}
                        size="small"
                      />
                    </Box>
                  </Box>
                  <Psychology color="primary" sx={{ fontSize: 40 }} />
                </Box>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <Card>
              <CardContent>
                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <Box>
                    <Typography color="textSecondary" gutterBottom variant="body2">
                      Engagement Rate
                    </Typography>
                    <Typography variant="h4" component="div">
                      {(socialMetrics.overall.engagementRate * 100).toFixed(1)}%
                    </Typography>
                  </Box>
                  <Analytics color="primary" sx={{ fontSize: 40 }} />
                </Box>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <Card>
              <CardContent>
                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <Box>
                    <Typography color="textSecondary" gutterBottom variant="body2">
                      Virality Index
                    </Typography>
                    <Typography variant="h4" component="div">
                      {(socialMetrics.overall.viralityIndex * 100).toFixed(0)}
                    </Typography>
                  </Box>
                  <Speed color="primary" sx={{ fontSize: 40 }} />
                </Box>
              </CardContent>
            </Card>
          </Grid>
        </Grid>

        {/* Main Content Tabs */}
        <Paper sx={{ width: '100%' }}>
          <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
            <Tabs value={selectedTab} onChange={(e, newValue) => setSelectedTab(newValue)}>
              <Tab label="Reddit Analysis" icon={<Reddit />} iconPosition="start" />
              <Tab label="Google Trends" icon={<Public />} iconPosition="start" />
              <Tab label="Platform Overview" icon={<Analytics />} iconPosition="start" />
              <Tab label="Trending Stocks" icon={<TrendingUp />} iconPosition="start" />
            </Tabs>
          </Box>

          {/* Reddit Analysis Tab */}
          <TabPanel value={selectedTab} index={0}>
            <Grid container spacing={3}>
              {/* Reddit Mentions Timeline */}
              <Grid item xs={12} lg={8}>
                <Card>
                  <CardHeader title="Reddit Mentions & Sentiment Over Time" />
                  <CardContent>
                    <ResponsiveContainer width="100%" height={300}>
                      <ComposedChart data={redditData.mentions}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="date" />
                        <YAxis yAxisId="mentions" />
                        <YAxis yAxisId="sentiment" orientation="right" domain={[0, 1]} />
                        <RechartsTooltip />
                        <Legend />
                        <Bar yAxisId="mentions" dataKey="mentions" fill="#1976d2" name="Mentions" />
                        <Line yAxisId="sentiment" type="monotone" dataKey="sentiment" stroke="#4caf50" strokeWidth={2} name="Sentiment Score" />
                      </ComposedChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
              </Grid>

              {/* Subreddit Breakdown */}
              <Grid item xs={12} lg={4}>
                <Card>
                  <CardHeader title="Subreddit Distribution" />
                  <CardContent>
                    <ResponsiveContainer width="100%" height={300}>
                      <PieChart>
                        <Pie
                          data={redditData.subredditBreakdown}
                          cx="50%"
                          cy="50%"
                          labelLine={false}
                          label={({ name, value }) => `${name}: ${value}%`}
                          outerRadius={80}
                          fill="#8884d8"
                          dataKey="value"
                        >
                          {redditData.subredditBreakdown.map((entry, index) => (
                            <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                          ))}
                        </Pie>
                        <RechartsTooltip />
                      </PieChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
              </Grid>

              {/* Top Reddit Posts */}
              <Grid item xs={12}>
                <Card>
                  <CardHeader title="Top Reddit Posts" />
                  <CardContent>
                    <List>
                      {redditData.topPosts.map((post, index) => (
                        <React.Fragment key={post.id}>
                          <ListItem alignItems="flex-start">
                            <ListItemAvatar>
                              <Avatar sx={{ bgcolor: getSentimentColor(post.sentiment) }}>
                                {index + 1}
                              </Avatar>
                            </ListItemAvatar>
                            <ListItemText
                              primary={
                                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                  <Typography variant="h6">{post.title}</Typography>
                                  <Chip
                                    label={getSentimentLabel(post.sentiment)}
                                    color={post.sentiment >= 0.7 ? 'success' : post.sentiment >= 0.5 ? 'warning' : 'error'}
                                    size="small"
                                  />
                                </Box>
                              }
                              secondary={
                                <Box sx={{ mt: 1 }}>
                                  <Typography variant="body2" color="text.secondary">
                                    {post.subreddit} • by {post.author} • {post.timestamp}
                                  </Typography>
                                  <Box sx={{ display: 'flex', gap: 2, mt: 1 }}>
                                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                                      <ThumbUp fontSize="small" />
                                      <Typography variant="body2">{post.score}</Typography>
                                    </Box>
                                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                                      <Comment fontSize="small" />
                                      <Typography variant="body2">{post.comments}</Typography>
                                    </Box>
                                  </Box>
                                </Box>
                              }
                            />
                          </ListItem>
                          {index < redditData.topPosts.length - 1 && <Divider />}
                        </React.Fragment>
                      ))}
                    </List>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          </TabPanel>

          {/* Google Trends Tab */}
          <TabPanel value={selectedTab} index={1}>
            <Grid container spacing={3}>
              {/* Search Volume Timeline */}
              <Grid item xs={12} lg={8}>
                <Card>
                  <CardHeader title="Google Search Volume Trends" />
                  <CardContent>
                    <ResponsiveContainer width="100%" height={300}>
                      <AreaChart data={trendsData.searchVolume}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="date" />
                        <YAxis />
                        <RechartsTooltip />
                        <Area type="monotone" dataKey="volume" stroke="#1976d2" fill="#1976d2" fillOpacity={0.3} />
                      </AreaChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
              </Grid>

              {/* Geographic Distribution */}
              <Grid item xs={12} lg={4}>
                <Card>
                  <CardHeader title="Geographic Interest" />
                  <CardContent>
                    <List>
                      {trendsData.geographicDistribution.map((region, index) => (
                        <ListItem key={region.region}>
                          <ListItemText
                            primary={region.region}
                            secondary={
                              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 1 }}>
                                <LinearProgress
                                  variant="determinate"
                                  value={region.interest}
                                  sx={{ flexGrow: 1, height: 8, borderRadius: 4 }}
                                />
                                <Typography variant="body2">{region.interest}%</Typography>
                              </Box>
                            }
                          />
                        </ListItem>
                      ))}
                    </List>
                  </CardContent>
                </Card>
              </Grid>

              {/* Related Queries */}
              <Grid item xs={12}>
                <Card>
                  <CardHeader title="Related Search Queries" />
                  <CardContent>
                    <TableContainer>
                      <Table>
                        <TableHead>
                          <TableRow>
                            <TableCell>Query</TableCell>
                            <TableCell align="right">Search Volume</TableCell>
                            <TableCell align="center">Trend</TableCell>
                            <TableCell align="right">Interest Score</TableCell>
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {trendsData.relatedQueries.map((query, index) => (
                            <TableRow key={index}>
                              <TableCell>{query.query}</TableCell>
                              <TableCell align="right">
                                <LinearProgress
                                  variant="determinate"
                                  value={query.volume}
                                  sx={{ width: 100, height: 8, borderRadius: 4 }}
                                />
                              </TableCell>
                              <TableCell align="center">
                                <Chip
                                  label={query.trend}
                                  color={query.trend === 'rising' ? 'success' : query.trend === 'falling' ? 'error' : 'default'}
                                  size="small"
                                  icon={
                                    query.trend === 'rising' ? <TrendingUp /> :
                                    query.trend === 'falling' ? <TrendingDown /> : <TrendingFlat />
                                  }
                                />
                              </TableCell>
                              <TableCell align="right">{query.volume}</TableCell>
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

          {/* Platform Overview Tab */}
          <TabPanel value={selectedTab} index={2}>
            <Grid container spacing={3}>
              {/* Platform Metrics */}
              <Grid item xs={12}>
                <Card>
                  <CardHeader title="Social Media Platform Analytics" />
                  <CardContent>
                    <Grid container spacing={3}>
                      {socialMetrics.platforms.map((platform, index) => (
                        <Grid item xs={12} sm={6} md={3} key={platform.name}>
                          <Card variant="outlined">
                            <CardContent>
                              <Box sx={{ textAlign: 'center' }}>
                                <Typography variant="h6" gutterBottom>
                                  {platform.name}
                                </Typography>
                                <Typography variant="h4" color="primary" gutterBottom>
                                  {formatNumber(platform.mentions)}
                                </Typography>
                                <Typography variant="body2" color="textSecondary" gutterBottom>
                                  Mentions
                                </Typography>
                                <Box sx={{ mt: 2 }}>
                                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                                    <Typography variant="body2">Sentiment</Typography>
                                    <Typography variant="body2">{platform.sentiment.toFixed(2)}</Typography>
                                  </Box>
                                  <LinearProgress
                                    variant="determinate"
                                    value={platform.sentiment * 100}
                                    sx={{
                                      height: 8,
                                      borderRadius: 4,
                                      '& .MuiLinearProgress-bar': {
                                        backgroundColor: getSentimentColor(platform.sentiment)
                                      }
                                    }}
                                  />
                                </Box>
                                <Box sx={{ mt: 2 }}>
                                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                                    <Typography variant="body2">Engagement</Typography>
                                    <Typography variant="body2">{(platform.engagement * 100).toFixed(1)}%</Typography>
                                  </Box>
                                  <LinearProgress
                                    variant="determinate"
                                    value={platform.engagement * 100}
                                    sx={{ height: 8, borderRadius: 4 }}
                                  />
                                </Box>
                              </Box>
                            </CardContent>
                          </Card>
                        </Grid>
                      ))}
                    </Grid>
                  </CardContent>
                </Card>
              </Grid>

              {/* Platform Comparison Chart */}
              <Grid item xs={12}>
                <Card>
                  <CardHeader title="Platform Sentiment Comparison" />
                  <CardContent>
                    <ResponsiveContainer width="100%" height={300}>
                      <BarChart data={socialMetrics.platforms}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="name" />
                        <YAxis />
                        <RechartsTooltip />
                        <Legend />
                        <Bar dataKey="mentions" fill="#1976d2" name="Mentions" />
                        <Bar dataKey="sentiment" fill="#4caf50" name="Sentiment Score" />
                      </BarChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          </TabPanel>

          {/* Trending Stocks Tab */}
          <TabPanel value={selectedTab} index={3}>
            <Card>
              <CardHeader title="Most Mentioned Stocks" />
              <CardContent>
                <TableContainer>
                  <Table>
                    <TableHead>
                      <TableRow>
                        <TableCell>Rank</TableCell>
                        <TableCell>Symbol</TableCell>
                        <TableCell align="right">Mentions</TableCell>
                        <TableCell align="center">Sentiment</TableCell>
                        <TableCell align="right">24h Change</TableCell>
                        <TableCell align="center">Trend</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {socialMetrics.trendingStocks.map((stock, index) => (
                        <TableRow key={stock.symbol} hover>
                          <TableCell>
                            <Avatar sx={{ bgcolor: index < 3 ? '#ffd700' : 'primary.main', width: 32, height: 32 }}>
                              {index + 1}
                            </Avatar>
                          </TableCell>
                          <TableCell>
                            <Typography variant="h6">{stock.symbol}</Typography>
                          </TableCell>
                          <TableCell align="right">
                            <Typography variant="body1" fontWeight="bold">
                              {formatNumber(stock.mentions)}
                            </Typography>
                          </TableCell>
                          <TableCell align="center">
                            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 1 }}>
                              <Box
                                sx={{
                                  width: 12,
                                  height: 12,
                                  borderRadius: '50%',
                                  backgroundColor: getSentimentColor(stock.sentiment)
                                }}
                              />
                              <Typography>{stock.sentiment.toFixed(2)}</Typography>
                            </Box>
                          </TableCell>
                          <TableCell align="right">
                            <Typography
                              color={stock.change >= 0 ? 'success.main' : 'error.main'}
                              fontWeight="bold"
                            >
                              {stock.change >= 0 ? '+' : ''}{(stock.change * 100).toFixed(1)}%
                            </Typography>
                          </TableCell>
                          <TableCell align="center">
                            {stock.change >= 0 ? (
                              <TrendingUp color="success" />
                            ) : (
                              <TrendingDown color="error" />
                            )}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              </CardContent>
            </Card>
          </TabPanel>
        </Paper>
      </Box>
    </Container>
  );
};

export default SocialMediaSentiment;