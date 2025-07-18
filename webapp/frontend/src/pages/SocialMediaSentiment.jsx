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

  // Empty data structures for proper error states
  const emptyRedditData = {
    mentions: [],
    sentiment: [],
    topPosts: [],
    subredditBreakdown: []
  };

  const emptyTrendsData = {
    searchVolume: [],
    relatedQueries: [],
    geographicDistribution: []
  };

  const emptySocialMetrics = {
    overall: {
      totalMentions: 0,
      sentimentScore: 0,
      engagementRate: 0,
      viralityIndex: 0,
      influencerMentions: 0
    },
    platforms: [],
    trendingStocks: []
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
        throw new Error(`API request failed: ${response.status}`);
      }
      
      const result = await response.json();
      
      if (result.data) {
        setRedditData(result.data.reddit || { mentions: [], keywords: [], engagement: {} });
        setTrendsData(result.data.googleTrends || { queries: [], regions: [] });
        setSocialMetrics(result.data.socialMetrics || { overall: { totalMentions: 0, sentimentScore: 0, engagementRate: 0, viralityIndex: 0 } });
        setSentimentHistory(result.data.reddit?.mentions || []);
      } else {
        // API returned success but with unexpected structure - show error
        throw new Error('API returned unexpected data structure');
      }

    } catch (error) {
      console.error('Failed to load social media sentiment data:', error);
      setError(`Failed to load social media sentiment data: ${error.message}`);
      
      // Set empty data structures on error instead of mock data
      setRedditData(emptyRedditData);
      setTrendsData(emptyTrendsData);
      setSocialMetrics(emptySocialMetrics);
      setSentimentHistory([]);
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
      {value === index && <div  sx={{ pt: 3 }}>{children}</div>}
    </div>
  );

  if (loading) {
    return (
      <div className="container mx-auto" maxWidth="xl">
        <div  sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '50vh' }}>
          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" size={60} />
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto" maxWidth="xl">
      <div  sx={{ mb: 4 }}>
        <div  sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
          <div  variant="h4" component="h1" sx={{ fontWeight: 700 }}>
            Social Media Sentiment Analysis
          </div>
          <div  sx={{ display: 'flex', gap: 2, alignItems: 'center' }}>
            <div className="mb-4" size="small" sx={{ minWidth: 120 }}>
              <label className="block text-sm font-medium text-gray-700 mb-1">Symbol</label>
              <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={selectedSymbol}
                label="Symbol"
                onChange={(e) => setSelectedSymbol(e.target.value)}
              >
                <option  value="AAPL">AAPL</option>
                <option  value="TSLA">TSLA</option>
                <option  value="NVDA">NVDA</option>
                <option  value="MSFT">MSFT</option>
                <option  value="GOOGL">GOOGL</option>
              </select>
            </div>
            <div className="mb-4" size="small" sx={{ minWidth: 120 }}>
              <label className="block text-sm font-medium text-gray-700 mb-1">Timeframe</label>
              <select className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={timeframe}
                label="Timeframe"
                onChange={(e) => setTimeframe(e.target.value)}
              >
                <option  value="1d">1 Day</option>
                <option  value="7d">7 Days</option>
                <option  value="30d">30 Days</option>
                <option  value="90d">90 Days</option>
              </select>
            </div>
            <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
              variant="outlined"
              startIcon={refreshing ? <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" size={16} /> : <Refresh />}
              onClick={handleRefresh}
              disabled={refreshing}
            >
              Refresh
            </button>
          </div>
        </div>

        {error && (
          <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="error" sx={{ mb: 3 }}>
            {error}
          </div>
        )}

        {/* Overview Cards */}
        <div className="grid" container spacing={3} sx={{ mb: 4 }}>
          <div className="grid" item xs={12} sm={6} md={3}>
            <div className="bg-white shadow-md rounded-lg">
              <div className="bg-white shadow-md rounded-lg"Content>
                <div  sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div>
                    <div  color="textSecondary" gutterBottom variant="body2">
                      Total Mentions
                    </div>
                    <div  variant="h4" component="div">
                      {formatNumber(socialMetrics.overall.totalMentions)}
                    </div>
                  </div>
                  <Forum color="primary" sx={{ fontSize: 40 }} />
                </div>
              </div>
            </div>
          </div>
          <div className="grid" item xs={12} sm={6} md={3}>
            <div className="bg-white shadow-md rounded-lg">
              <div className="bg-white shadow-md rounded-lg"Content>
                <div  sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div>
                    <div  color="textSecondary" gutterBottom variant="body2">
                      Sentiment Score
                    </div>
                    <div  sx={{ display: 'flex', alignItems: 'center' }}>
                      <div  variant="h4" component="div" sx={{ mr: 1 }}>
                        {socialMetrics.overall.sentimentScore.toFixed(2)}
                      </div>
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                        label={getSentimentLabel(socialMetrics.overall.sentimentScore)}
                        color={socialMetrics.overall.sentimentScore >= 0.7 ? 'success' : socialMetrics.overall.sentimentScore >= 0.5 ? 'warning' : 'error'}
                        size="small"
                      />
                    </div>
                  </div>
                  <Psychology color="primary" sx={{ fontSize: 40 }} />
                </div>
              </div>
            </div>
          </div>
          <div className="grid" item xs={12} sm={6} md={3}>
            <div className="bg-white shadow-md rounded-lg">
              <div className="bg-white shadow-md rounded-lg"Content>
                <div  sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div>
                    <div  color="textSecondary" gutterBottom variant="body2">
                      Engagement Rate
                    </div>
                    <div  variant="h4" component="div">
                      {(socialMetrics.overall.engagementRate * 100).toFixed(1)}%
                    </div>
                  </div>
                  <Analytics color="primary" sx={{ fontSize: 40 }} />
                </div>
              </div>
            </div>
          </div>
          <div className="grid" item xs={12} sm={6} md={3}>
            <div className="bg-white shadow-md rounded-lg">
              <div className="bg-white shadow-md rounded-lg"Content>
                <div  sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div>
                    <div  color="textSecondary" gutterBottom variant="body2">
                      Virality Index
                    </div>
                    <div  variant="h4" component="div">
                      {(socialMetrics.overall.viralityIndex * 100).toFixed(0)}
                    </div>
                  </div>
                  <Speed color="primary" sx={{ fontSize: 40 }} />
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Main Content Tabs */}
        <div className="bg-white shadow-md rounded-lg p-4" sx={{ width: '100%' }}>
          <div  sx={{ borderBottom: 1, borderColor: 'divider' }}>
            <div className="border-b border-gray-200" value={selectedTab} onChange={(e, newValue) => setSelectedTab(newValue)}>
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Reddit Analysis" icon={<Reddit />} iconPosition="start" />
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Google Trends" icon={<Public />} iconPosition="start" />
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Platform Overview" icon={<Analytics />} iconPosition="start" />
              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Trending Stocks" icon={<TrendingUp />} iconPosition="start" />
            </div>
          </div>

          {/* Reddit Analysis Tab */}
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={selectedTab} index={0}>
            <div className="grid" container spacing={3}>
              {/* Reddit Mentions Timeline */}
              <div className="grid" item xs={12} lg={8}>
                <div className="bg-white shadow-md rounded-lg">
                  <div className="bg-white shadow-md rounded-lg"Header title="Reddit Mentions & Sentiment Over Time" />
                  <div className="bg-white shadow-md rounded-lg"Content>
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
                  </div>
                </div>
              </div>

              {/* Subreddit Breakdown */}
              <div className="grid" item xs={12} lg={4}>
                <div className="bg-white shadow-md rounded-lg">
                  <div className="bg-white shadow-md rounded-lg"Header title="Subreddit Distribution" />
                  <div className="bg-white shadow-md rounded-lg"Content>
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
                  </div>
                </div>
              </div>

              {/* Top Reddit Posts */}
              <div className="grid" item xs={12}>
                <div className="bg-white shadow-md rounded-lg">
                  <div className="bg-white shadow-md rounded-lg"Header title="Top Reddit Posts" />
                  <div className="bg-white shadow-md rounded-lg"Content>
                    <List>
                      {redditData.topPosts.map((post, index) => (
                        <React.Fragment key={post.id}>
                          <ListItem alignItems="flex-start">
                            <ListItemAvatar>
                              <div className="h-8 w-8 rounded-full bg-gray-300 flex items-center justify-center" sx={{ bgcolor: getSentimentColor(post.sentiment) }}>
                                {index + 1}
                              </div>
                            </ListItemAvatar>
                            <ListItemText
                              primary={
                                <div  sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                  <div  variant="h6">{post.title}</div>
                                  <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                                    label={getSentimentLabel(post.sentiment)}
                                    color={post.sentiment >= 0.7 ? 'success' : post.sentiment >= 0.5 ? 'warning' : 'error'}
                                    size="small"
                                  />
                                </div>
                              }
                              secondary={
                                <div  sx={{ mt: 1 }}>
                                  <div  variant="body2" color="text.secondary">
                                    {post.subreddit} • by {post.author} • {post.timestamp}
                                  </div>
                                  <div  sx={{ display: 'flex', gap: 2, mt: 1 }}>
                                    <div  sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                                      <ThumbUp fontSize="small" />
                                      <div  variant="body2">{post.score}</div>
                                    </div>
                                    <div  sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                                      <Comment fontSize="small" />
                                      <div  variant="body2">{post.comments}</div>
                                    </div>
                                  </div>
                                </div>
                              }
                            />
                          </ListItem>
                          {index < redditData.topPosts.length - 1 && <hr className="border-gray-200" />}
                        </React.Fragment>
                      ))}
                    </List>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Google Trends Tab */}
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={selectedTab} index={1}>
            <div className="grid" container spacing={3}>
              {/* Search Volume Timeline */}
              <div className="grid" item xs={12} lg={8}>
                <div className="bg-white shadow-md rounded-lg">
                  <div className="bg-white shadow-md rounded-lg"Header title="Google Search Volume Trends" />
                  <div className="bg-white shadow-md rounded-lg"Content>
                    <ResponsiveContainer width="100%" height={300}>
                      <AreaChart data={trendsData.searchVolume}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="date" />
                        <YAxis />
                        <RechartsTooltip />
                        <Area type="monotone" dataKey="volume" stroke="#1976d2" fill="#1976d2" fillOpacity={0.3} />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              </div>

              {/* Geographic Distribution */}
              <div className="grid" item xs={12} lg={4}>
                <div className="bg-white shadow-md rounded-lg">
                  <div className="bg-white shadow-md rounded-lg"Header title="Geographic Interest" />
                  <div className="bg-white shadow-md rounded-lg"Content>
                    <List>
                      {trendsData.geographicDistribution.map((region, index) => (
                        <ListItem key={region.region}>
                          <ListItemText
                            primary={region.region}
                            secondary={
                              <div  sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 1 }}>
                                <div className="w-full bg-gray-200 rounded-full h-2"
                                  variant="determinate"
                                  value={region.interest}
                                  sx={{ flexGrow: 1, height: 8, borderRadius: 4 }}
                                />
                                <div  variant="body2">{region.interest}%</div>
                              </div>
                            }
                          />
                        </ListItem>
                      ))}
                    </List>
                  </div>
                </div>
              </div>

              {/* Related Queries */}
              <div className="grid" item xs={12}>
                <div className="bg-white shadow-md rounded-lg">
                  <div className="bg-white shadow-md rounded-lg"Header title="Related Search Queries" />
                  <div className="bg-white shadow-md rounded-lg"Content>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Query</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Search Volume</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center">Trend</td>
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Interest Score</td>
                          </tr>
                        </thead>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
                          {trendsData.relatedQueries.map((query, index) => (
                            <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={index}>
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>{query.query}</td>
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                                <div className="w-full bg-gray-200 rounded-full h-2"
                                  variant="determinate"
                                  value={query.volume}
                                  sx={{ width: 100, height: 8, borderRadius: 4 }}
                                />
                              </td>
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center">
                                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                                  label={query.trend}
                                  color={query.trend === 'rising' ? 'success' : query.trend === 'falling' ? 'error' : 'default'}
                                  size="small"
                                  icon={
                                    query.trend === 'rising' ? <TrendingUp /> :
                                    query.trend === 'falling' ? <TrendingDown /> : <TrendingFlat />
                                  }
                                />
                              </td>
                              <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">{query.volume}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Platform Overview Tab */}
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={selectedTab} index={2}>
            <div className="grid" container spacing={3}>
              {/* Platform Metrics */}
              <div className="grid" item xs={12}>
                <div className="bg-white shadow-md rounded-lg">
                  <div className="bg-white shadow-md rounded-lg"Header title="Social Media Platform Analytics" />
                  <div className="bg-white shadow-md rounded-lg"Content>
                    <div className="grid" container spacing={3}>
                      {socialMetrics.platforms.map((platform, index) => (
                        <div className="grid" item xs={12} sm={6} md={3} key={platform.name}>
                          <div className="bg-white shadow-md rounded-lg" variant="outlined">
                            <div className="bg-white shadow-md rounded-lg"Content>
                              <div  sx={{ textAlign: 'center' }}>
                                <div  variant="h6" gutterBottom>
                                  {platform.name}
                                </div>
                                <div  variant="h4" color="primary" gutterBottom>
                                  {formatNumber(platform.mentions)}
                                </div>
                                <div  variant="body2" color="textSecondary" gutterBottom>
                                  Mentions
                                </div>
                                <div  sx={{ mt: 2 }}>
                                  <div  sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                                    <div  variant="body2">Sentiment</div>
                                    <div  variant="body2">{platform.sentiment.toFixed(2)}</div>
                                  </div>
                                  <div className="w-full bg-gray-200 rounded-full h-2"
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
                                </div>
                                <div  sx={{ mt: 2 }}>
                                  <div  sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                                    <div  variant="body2">Engagement</div>
                                    <div  variant="body2">{(platform.engagement * 100).toFixed(1)}%</div>
                                  </div>
                                  <div className="w-full bg-gray-200 rounded-full h-2"
                                    variant="determinate"
                                    value={platform.engagement * 100}
                                    sx={{ height: 8, borderRadius: 4 }}
                                  />
                                </div>
                              </div>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>

              {/* Platform Comparison Chart */}
              <div className="grid" item xs={12}>
                <div className="bg-white shadow-md rounded-lg">
                  <div className="bg-white shadow-md rounded-lg"Header title="Platform Sentiment Comparison" />
                  <div className="bg-white shadow-md rounded-lg"Content>
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
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Trending Stocks Tab */}
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={selectedTab} index={3}>
            <div className="bg-white shadow-md rounded-lg">
              <div className="bg-white shadow-md rounded-lg"Header title="Most Mentioned Stocks" />
              <div className="bg-white shadow-md rounded-lg"Content>
                <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leContainer>
                  <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"le>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leHead>
                      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Rank</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>Symbol</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">Mentions</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center">Sentiment</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">24h Change</td>
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center">Trend</td>
                      </tr>
                    </thead>
                    <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leBody>
                      {socialMetrics.trendingStocks.map((stock, index) => (
                        <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leRow key={stock.symbol} hover>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                            <div className="h-8 w-8 rounded-full bg-gray-300 flex items-center justify-center" sx={{ bgcolor: index < 3 ? '#ffd700' : 'primary.main', width: 32, height: 32 }}>
                              {index + 1}
                            </div>
                          </td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell>
                            <div  variant="h6">{stock.symbol}</div>
                          </td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                            <div  variant="body1" fontWeight="bold">
                              {formatNumber(stock.mentions)}
                            </div>
                          </td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center">
                            <div  sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 1 }}>
                              <div 
                                sx={{
                                  width: 12,
                                  height: 12,
                                  borderRadius: '50%',
                                  backgroundColor: getSentimentColor(stock.sentiment)
                                }}
                              />
                              <div>{stock.sentiment.toFixed(2)}</div>
                            </div>
                          </td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="right">
                            <div 
                              color={stock.change >= 0 ? 'success.main' : 'error.main'}
                              fontWeight="bold"
                            >
                              {stock.change >= 0 ? '+' : ''}{(stock.change * 100).toFixed(1)}%
                            </div>
                          </td>
                          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"leCell align="center">
                            {stock.change >= 0 ? (
                              <TrendingUp color="success" />
                            ) : (
                              <TrendingDown color="error" />
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default SocialMediaSentiment;