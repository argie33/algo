import React, { useState, useEffect } from 'react';
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
  Chip,
  Button,
  TextField,
  MenuItem,
  IconButton,
  Avatar,
  Badge,
  Divider,
  List,
  ListItem,
  ListItemText,
  ListItemAvatar,
  Alert,
  CircularProgress,
  Paper,
  Timeline,
  TimelineItem,
  TimelineSeparator,
  TimelineConnector,
  TimelineContent,
  TimelineDot,
  TimelineOppositeContent,
  LinearProgress
} from '@mui/material';
import {
  TrendingUp,
  TrendingDown,
  Newspaper,
  Event,
  NotificationsActive,
  Search,
  FilterList,
  Refresh,
  BookmarkBorder,
  Bookmark,
  Share,
  OpenInNew,
  Announcement,
  Business,
  Assessment,
  Schedule,
  Notifications,
  Warning,
  Info,
  CheckCircle,
  Error
} from '@mui/icons-material';
import { formatDistanceToNow, format } from 'date-fns';
import { formatPercentage } from '../utils/formatters';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer
} from 'recharts';

function TabPanel({ children, value, index, ...other }) {
  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`news-tabpanel-${index}`}
      aria-labelledby={`news-tab-${index}`}
      {...other}
    >
      {value === index && (
        <div  sx={{ p: 3 }}>
          {children}
        </div>
      )}
    </div>
  );
}

const NewsAnalysis = () => {
  const [tabValue, setTabValue] = useState(0);
  // ⚠️ MOCK DATA - Using mock news data
  const [newsData, setNewsData] = useState(mockNewsData);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('all');
  const [selectedTimeframe, setSelectedTimeframe] = useState('today');
  const [bookmarkedNews, setBookmarkedNews] = useState(new Set());
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    // ⚠️ MOCK DATA - Simulate data fetching with mock data
    setLoading(true);
    setTimeout(() => {
      setLoading(false);
    }, 1000);
  }, [selectedCategory, selectedTimeframe]);

  const handleTabChange = (event, newValue) => {
    setTabValue(newValue);
  };

  const toggleBookmark = (newsId) => {
    const newBookmarks = new Set(bookmarkedNews);
    if (newBookmarks.has(newsId)) {
      newBookmarks.delete(newsId);
    } else {
      newBookmarks.add(newsId);
    }
    setBookmarkedNews(newBookmarks);
  };

  const getSentimentColor = (sentiment) => {
    switch (sentiment.toLowerCase()) {
      case 'bullish':
      case 'positive':
        return 'success';
      case 'bearish':
      case 'negative':
        return 'error';
      case 'neutral':
        return 'default';
      default:
        return 'default';
    }
  };

  const getSentimentIcon = (sentiment) => {
    switch (sentiment.toLowerCase()) {
      case 'bullish':
      case 'positive':
        return <TrendingUp />;
      case 'bearish':
      case 'negative':
        return <TrendingDown />;
      default:
        return <Info />;
    }
  };

  const getEventTypeIcon = (type) => {
    switch (type.toLowerCase()) {
      case 'earnings':
        return <Assessment color="primary" />;
      case 'announcement':
        return <Announcement color="warning" />;
      case 'economic':
        return <Business color="info" />;
      case 'meeting':
        return <Schedule color="secondary" />;
      default:
        return <Event />;
    }
  };

  const getImpactColor = (impact) => {
    switch (impact.toLowerCase()) {
      case 'high':
        return 'error';
      case 'medium':
        return 'warning';
      case 'low':
        return 'success';
      default:
        return 'default';
    }
  };

  const filteredNews = newsData.news.filter(article => {
    const matchesSearch = article.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         article.summary.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesCategory = selectedCategory === 'all' || article.category === selectedCategory;
    return matchesSearch && matchesCategory;
  });

  return (
    <div className="container mx-auto" maxWidth="xl" sx={{ py: 4 }}>
      {/* Header */}
      <div  display="flex" alignItems="center" justifyContent="between" mb={4}>
        <div>
          <div  variant="h3" component="h1" gutterBottom>
            News & Events Analysis
          </div>
          <div  variant="body1" color="text.secondary">
            AI-powered market news analysis and event tracking
          </div>
        </div>
        
        <div  display="flex" alignItems="center" gap={2}>
          <span className="inline-flex items-center justify-center px-2 py-1 text-xs font-bold leading-none text-red-100 bg-red-600 rounded-full" badgeContent={newsData.alerts.length} color="error">
            <button className="p-2 rounded-full hover:bg-gray-100">
              <NotificationsActive />
            </button>
          </span>
          <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" variant="outlined" startIcon={<Refresh />}>
            Refresh
          </button>
        </div>
      </div>

      {/* Alert Summary */}
      {newsData.alerts.length > 0 && (
        <div className="p-4 rounded-md bg-blue-50 border border-blue-200" 
          severity="warning" 
          sx={{ mb: 3 }}
          action={
            <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500" color="inherit" size="small">
              View All
            </button>
          }
        >
          <strong>{newsData.alerts.length} active alerts:</strong> {newsData.alerts[0].message}
          {newsData.alerts.length > 1 && ` and ${newsData.alerts.length - 1} more`}
        </div>
      )}

      {/* Market Sentiment Overview */}
      <div className="grid" container spacing={3} mb={4}>
        <div className="grid" item xs={12} md={3}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  display="flex" alignItems="center" justifyContent="between">
                <div>
                  <div  variant="h6" color="text.secondary">
                    News Sentiment
                  </div>
                  <div  variant="h4" color="primary">
                    {newsData.sentiment.overall}
                  </div>
                  <div  variant="body2">
                    {newsData.sentiment.distribution.bullish}% Bullish
                  </div>
                </div>
                <TrendingUp color="primary" fontSize="large" />
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2" 
                variant="determinate" 
                value={newsData.sentiment.distribution.bullish} 
                color="success"
                sx={{ mt: 1 }}
              />
            </div>
          </div>
        </div>

        <div className="grid" item xs={12} md={3}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  display="flex" alignItems="center" justifyContent="between">
                <div>
                  <div  variant="h6" color="text.secondary">
                    Articles Today
                  </div>
                  <div  variant="h4" color="secondary">
                    {newsData.stats.articlesToday}
                  </div>
                  <div  variant="body2">
                    +{newsData.stats.articlesChange}% vs yesterday
                  </div>
                </div>
                <Newspaper color="secondary" fontSize="large" />
              </div>
            </div>
          </div>
        </div>

        <div className="grid" item xs={12} md={3}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  display="flex" alignItems="center" justifyContent="between">
                <div>
                  <div  variant="h6" color="text.secondary">
                    Events This Week
                  </div>
                  <div  variant="h4" color="info.main">
                    {newsData.stats.eventsThisWeek}
                  </div>
                  <div  variant="body2">
                    {newsData.stats.highImpactEvents} high impact
                  </div>
                </div>
                <Event color="info" fontSize="large" />
              </div>
            </div>
          </div>
        </div>

        <div className="grid" item xs={12} md={3}>
          <div className="bg-white shadow-md rounded-lg">
            <div className="bg-white shadow-md rounded-lg"Content>
              <div  display="flex" alignItems="center" justifyContent="between">
                <div>
                  <div  variant="h6" color="text.secondary">
                    AI Confidence
                  </div>
                  <div  variant="h4" color="warning.main">
                    {newsData.sentiment.aiConfidence}%
                  </div>
                  <div  variant="body2">
                    Analysis accuracy
                  </div>
                </div>
                <Assessment color="warning" fontSize="large" />
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="bg-white shadow-md rounded-lg" sx={{ mb: 3 }}>
        <div className="bg-white shadow-md rounded-lg"Content>
          <div className="grid" container spacing={2} alignItems="center">
            <div className="grid" item xs={12} md={4}>
              <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                fullWidth
                size="small"
                label="Search news..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                InputProps={{
                  startAdornment: <Search sx={{ mr: 1, color: 'text.secondary' }} />
                }}
              />
            </div>
            <div className="grid" item xs={12} md={3}>
              <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                select
                fullWidth
                size="small"
                label="Category"
                value={selectedCategory}
                onChange={(e) => setSelectedCategory(e.target.value)}
              >
                <option  value="all">All Categories</option>
                <option  value="earnings">Earnings</option>
                <option  value="market">Market News</option>
                <option  value="economic">Economic Data</option>
                <option  value="corporate">Corporate News</option>
                <option  value="analyst">Analyst Reports</option>
              </input>
            </div>
            <div className="grid" item xs={12} md={3}>
              <input className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                select
                fullWidth
                size="small"
                label="Timeframe"
                value={selectedTimeframe}
                onChange={(e) => setSelectedTimeframe(e.target.value)}
              >
                <option  value="today">Today</option>
                <option  value="week">This Week</option>
                <option  value="month">This Month</option>
                <option  value="all">All Time</option>
              </input>
            </div>
            <div className="grid" item xs={12} md={2}>
              <button className="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
                fullWidth
                variant="outlined"
                startIcon={<FilterList />}
                size="small"
              >
                More Filters
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content Tabs */}
      <div  sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
        <div className="border-b border-gray-200" value={tabValue} onChange={handleTabChange} aria-label="news analysis tabs">
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Breaking News" icon={<Newspaper />} />
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Market Events" icon={<Event />} />
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Earnings Calendar" icon={<Assessment />} />
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="Economic Data" icon={<Business />} />
          <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300" label="AI Insights" icon={<Assessment />} />
        </div>
      </div>

      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={tabValue} index={0}>
        {/* Breaking News */}
        <div className="grid" container spacing={3}>
          <div className="grid" item xs={12} md={8}>
            <div className="bg-white shadow-md rounded-lg">
              <div className="bg-white shadow-md rounded-lg"Header 
                title="Latest Market News" 
                action={
                  <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                    label={`${filteredNews.length} articles`} 
                    color="primary" 
                    variant="outlined" 
                  />
                }
              />
              <div className="bg-white shadow-md rounded-lg"Content>
                {loading ? (
                  <div  display="flex" justifyContent="center" p={4}>
                    <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" />
                  </div>
                ) : (
                  <List>
                    {filteredNews.map((article, index) => (
                      <React.Fragment key={article.id}>
                        <ListItem alignItems="flex-start">
                          <ListItemAvatar>
                            <div className="h-8 w-8 rounded-full bg-gray-300 flex items-center justify-center" sx={{ bgcolor: getSentimentColor(article.sentiment) + '.main' }}>
                              {getSentimentIcon(article.sentiment)}
                            </div>
                          </ListItemAvatar>
                          <ListItemText
                            primary={
                              <div  display="flex" alignItems="center" gap={1} mb={1}>
                                <div  variant="h6" component="span">
                                  {article.title}
                                </div>
                                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                                  label={article.impact} 
                                  color={getImpactColor(article.impact)}
                                  size="small"
                                />
                              </div>
                            }
                            secondary={
                              <div>
                                <div  variant="body2" color="text.primary" paragraph>
                                  {article.summary}
                                </div>
                                <div  display="flex" alignItems="center" justifyContent="between">
                                  <div  display="flex" alignItems="center" gap={2}>
                                    <div  variant="caption" color="text.secondary">
                                      {article.source} • {formatDistanceToNow(new Date(article.timestamp))} ago
                                    </div>
                                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                                      label={article.sentiment} 
                                      color={getSentimentColor(article.sentiment)}
                                      size="small"
                                      variant="outlined"
                                    />
                                    {article.tickers.map(ticker => (
                                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" key={ticker} label={ticker} size="small" variant="outlined" />
                                    ))}
                                  </div>
                                  <div>
                                    <button className="p-2 rounded-full hover:bg-gray-100" 
                                      size="small" 
                                      onClick={() => toggleBookmark(article.id)}
                                      color={bookmarkedNews.has(article.id) ? 'primary' : 'default'}
                                    >
                                      {bookmarkedNews.has(article.id) ? <Bookmark /> : <BookmarkBorder />}
                                    </button>
                                    <button className="p-2 rounded-full hover:bg-gray-100" size="small">
                                      <Share />
                                    </button>
                                    <button className="p-2 rounded-full hover:bg-gray-100" size="small">
                                      <OpenInNew />
                                    </button>
                                  </div>
                                </div>
                              </div>
                            }
                          />
                        </ListItem>
                        {index < filteredNews.length - 1 && <hr className="border-gray-200" variant="inset" component="li" />}
                      </React.Fragment>
                    ))}
                  </List>
                )}
              </div>
            </div>
          </div>

          <div className="grid" item xs={12} md={4}>
            <div className="grid" container spacing={3}>
              {/* Trending Topics */}
              <div className="grid" item xs={12}>
                <div className="bg-white shadow-md rounded-lg">
                  <div className="bg-white shadow-md rounded-lg"Header title="Trending Topics" />
                  <div className="bg-white shadow-md rounded-lg"Content>
                    <div  display="flex" flexWrap="wrap" gap={1}>
                      {newsData.trendingTopics.map((topic, index) => (
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                          key={topic.topic}
                          label={`${topic.topic} (${topic.mentions})`}
                          color={index < 3 ? 'primary' : 'default'}
                          variant={index < 3 ? 'filled' : 'outlined'}
                          size="small"
                        />
                      ))}
                    </div>
                  </div>
                </div>
              </div>

              {/* Market Movers */}
              <div className="grid" item xs={12}>
                <div className="bg-white shadow-md rounded-lg">
                  <div className="bg-white shadow-md rounded-lg"Header title="News-Driven Movers" />
                  <div className="bg-white shadow-md rounded-lg"Content>
                    <List dense>
                      {newsData.newsMovers.map((mover) => (
                        <ListItem key={mover.symbol} disablePadding>
                          <ListItemText
                            primary={
                              <div  display="flex" alignItems="center" justifyContent="between">
                                <div  variant="body2" fontWeight="bold">
                                  {mover.symbol}
                                </div>
                                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                                  label={`${mover.change >= 0 ? '+' : ''}${formatPercentage(mover.change)}`}
                                  color={mover.change >= 0 ? 'success' : 'error'}
                                  size="small"
                                />
                              </div>
                            }
                            secondary={mover.reason}
                          />
                        </ListItem>
                      ))}
                    </List>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={tabValue} index={1}>
        {/* Market Events */}
        <div className="grid" container spacing={3}>
          <div className="grid" item xs={12} md={8}>
            <div className="bg-white shadow-md rounded-lg">
              <div className="bg-white shadow-md rounded-lg"Header title="Upcoming Market Events" />
              <div className="bg-white shadow-md rounded-lg"Content>
                <Timeline>
                  {newsData.upcomingEvents.map((event, index) => (
                    <TimelineItem key={event.id}>
                      <TimelineOppositeContent sx={{ m: 'auto 0' }} variant="body2" color="text.secondary">
                        {format(new Date(event.date), 'MMM dd, HH:mm')}
                      </TimelineOppositeContent>
                      <TimelineSeparator>
                        <TimelineDot color={getImpactColor(event.impact)}>
                          {getEventTypeIcon(event.type)}
                        </TimelineDot>
                        {index < newsData.upcomingEvents.length - 1 && <TimelineConnector />}
                      </TimelineSeparator>
                      <TimelineContent sx={{ py: '12px', px: 2 }}>
                        <div  variant="h6" component="span">
                          {event.title}
                        </div>
                        <div  variant="body2" color="text.secondary">
                          {event.description}
                        </div>
                        <div  display="flex" gap={1} mt={1}>
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label={event.type} size="small" variant="outlined" />
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                            label={`${event.impact} Impact`} 
                            color={getImpactColor(event.impact)}
                            size="small"
                          />
                          {event.tickers.map(ticker => (
                            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" key={ticker} label={ticker} size="small" variant="outlined" />
                          ))}
                        </div>
                      </TimelineContent>
                    </TimelineItem>
                  ))}
                </Timeline>
              </div>
            </div>
          </div>

          <div className="grid" item xs={12} md={4}>
            <div className="bg-white shadow-md rounded-lg">
              <div className="bg-white shadow-md rounded-lg"Header title="Event Impact Analysis" />
              <div className="bg-white shadow-md rounded-lg"Content>
                <div  variant="body2" color="text.secondary" paragraph>
                  AI-powered analysis of upcoming events and their potential market impact.
                </div>
                <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="info" sx={{ mb: 2 }}>
                  This week: 3 high-impact events expected to drive volatility
                </div>
                {/* Add more event analysis content here */}
              </div>
            </div>
          </div>
        </div>
      </div>

      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={tabValue} index={2}>
        {/* Earnings Calendar */}
        <div className="grid" container spacing={3}>
          <div className="grid" item xs={12}>
            <div className="bg-white shadow-md rounded-lg">
              <div className="bg-white shadow-md rounded-lg"Header title="Earnings Calendar" />
              <div className="bg-white shadow-md rounded-lg"Content>
                <div  variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                  Comprehensive earnings calendar with AI-powered estimates and analysis
                </div>
                <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="info">
                  This feature will show detailed earnings calendar, analyst estimates, and historical performance.
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={tabValue} index={3}>
        {/* Economic Data */}
        <div className="grid" container spacing={3}>
          <div className="grid" item xs={12}>
            <div className="bg-white shadow-md rounded-lg">
              <div className="bg-white shadow-md rounded-lg"Header title="Economic Data Releases" />
              <div className="bg-white shadow-md rounded-lg"Content>
                <div  variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                  Real-time economic data releases and their market impact analysis
                </div>
                <div className="p-4 rounded-md bg-blue-50 border border-blue-200" severity="info">
                  This feature will show economic data releases, forecasts vs actual, and market reactions.
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <button className="px-4 py-2 text-sm font-medium text-gray-500 hover:text-gray-700 border-b-2 border-transparent hover:border-gray-300"Panel value={tabValue} index={4}>
        {/* AI Insights */}
        <div className="grid" container spacing={3}>
          <div className="grid" item xs={12} md={8}>
            <div className="bg-white shadow-md rounded-lg">
              <div className="bg-white shadow-md rounded-lg"Header 
                title="AI-Powered Market Insights" 
                subheader="Advanced sentiment analysis and predictive modeling"
                action={
                  <div  display="flex" alignItems="center" gap={1}>
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label="Live Analysis" color="success" size="small" />
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" label={`${newsData.sentiment.aiConfidence}% Confidence`} color="info" size="small" />
                  </div>
                }
              />
              <div className="bg-white shadow-md rounded-lg"Content>
                {/* AI Sentiment Timeline */}
                <div  mb={4}>
                  <div  variant="h6" gutterBottom>
                    Sentiment Evolution (24h)
                  </div>
                  <ResponsiveContainer width="100%" height={200}>
                    <LineChart data={newsData.aiInsights.sentimentTimeline}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="time" />
                      <YAxis domain={[-100, 100]} />
                      <RechartsTooltip />
                      <Line 
                        type="monotone" 
                        dataKey="sentiment" 
                        stroke="#1976d2" 
                        strokeWidth={2}
                        dot={{ fill: '#1976d2', strokeWidth: 2 }}
                      />
                      <Line 
                        type="monotone" 
                        dataKey="volume" 
                        stroke="#f57c00" 
                        strokeWidth={2}
                        dot={{ fill: '#f57c00', strokeWidth: 2 }}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>

                {/* Market Regime Detection */}
                <div  mb={4}>
                  <div  variant="h6" gutterBottom>
                    Market Regime Analysis
                  </div>
                  <div className="grid" container spacing={2}>
                    <div className="grid" item xs={12} md={4}>
                      <div className="bg-white shadow-md rounded-lg" variant="outlined">
                        <div className="bg-white shadow-md rounded-lg"Content>
                          <div  display="flex" alignItems="center" gap={2}>
                            <div className="h-8 w-8 rounded-full bg-gray-300 flex items-center justify-center" sx={{ bgcolor: 'success.main' }}>
                              <TrendingUp />
                            </div>
                            <div>
                              <div  variant="h6">
                                {newsData.aiInsights.marketRegime.current}
                              </div>
                              <div  variant="body2" color="text.secondary">
                                Current Regime
                              </div>
                            </div>
                          </div>
                          <div className="w-full bg-gray-200 rounded-full h-2" 
                            variant="determinate" 
                            value={newsData.aiInsights.marketRegime.confidence}
                            sx={{ mt: 2 }}
                          />
                          <div  variant="caption" color="text.secondary">
                            {newsData.aiInsights.marketRegime.confidence}% Confidence
                          </div>
                        </div>
                      </div>
                    </div>
                    <div className="grid" item xs={12} md={8}>
                      <div className="bg-white shadow-md rounded-lg" variant="outlined">
                        <div className="bg-white shadow-md rounded-lg"Content>
                          <div  variant="subtitle1" gutterBottom>
                            Key Regime Indicators
                          </div>
                          <List dense>
                            {newsData.aiInsights.marketRegime.indicators.map((indicator, index) => (
                              <ListItem key={index}>
                                <ListItemText
                                  primary={indicator.name}
                                  secondary={
                                    <div  display="flex" alignItems="center" gap={1}>
                                      <div className="w-full bg-gray-200 rounded-full h-2" 
                                        variant="determinate" 
                                        value={Math.abs(indicator.value)}
                                        sx={{ flexGrow: 1, height: 6, borderRadius: 3 }}
                                        color={indicator.value >= 0 ? 'success' : 'error'}
                                      />
                                      <div  variant="caption">
                                        {indicator.value >= 0 ? '+' : ''}{indicator.value}%
                                      </div>
                                    </div>
                                  }
                                />
                              </ListItem>
                            ))}
                          </List>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                {/* AI Predictions */}
                <div  mb={4}>
                  <div  variant="h6" gutterBottom>
                    AI Market Predictions
                  </div>
                  <div className="grid" container spacing={2}>
                    {newsData.aiInsights.predictions.map((prediction, index) => (
                      <div className="grid" item xs={12} md={6} key={index}>
                        <div className="bg-white shadow-md rounded-lg" variant="outlined">
                          <div className="bg-white shadow-md rounded-lg"Content>
                            <div  display="flex" alignItems="center" justifyContent="between" mb={2}>
                              <div  variant="subtitle1">
                                {prediction.target}
                              </div>
                              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                                label={prediction.timeframe}
                                color="primary"
                                size="small"
                                variant="outlined"
                              />
                            </div>
                            <div  display="flex" alignItems="center" gap={2} mb={2}>
                              <div  flex={1}>
                                <div  variant="h5" color={prediction.direction === 'up' ? 'success.main' : 'error.main'}>
                                  {prediction.direction === 'up' ? '↗' : '↘'} {prediction.magnitude}%
                                </div>
                                <div  variant="body2" color="text.secondary">
                                  Predicted Move
                                </div>
                              </div>
                              <div  textAlign="right">
                                <div  variant="h6">
                                  {prediction.confidence}%
                                </div>
                                <div  variant="body2" color="text.secondary">
                                  Confidence
                                </div>
                              </div>
                            </div>
                            <div  variant="body2" color="text.secondary">
                              {prediction.reasoning}
                            </div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Anomaly Detection */}
                <div>
                  <div  variant="h6" gutterBottom>
                    Market Anomalies Detected
                  </div>
                  <List>
                    {newsData.aiInsights.anomalies.map((anomaly, index) => (
                      <ListItem key={index}>
                        <ListItemAvatar>
                          <div className="h-8 w-8 rounded-full bg-gray-300 flex items-center justify-center" sx={{ bgcolor: anomaly.severity === 'high' ? 'error.main' : 'warning.main' }}>
                            <Warning />
                          </div>
                        </ListItemAvatar>
                        <ListItemText
                          primary={anomaly.title}
                          secondary={
                            <div>
                              <div  variant="body2" color="text.primary">
                                {anomaly.description}
                              </div>
                              <div  display="flex" alignItems="center" gap={1} mt={1}>
                                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800" 
                                  label={anomaly.severity}
                                  color={anomaly.severity === 'high' ? 'error' : 'warning'}
                                  size="small"
                                />
                                <div  variant="caption" color="text.secondary">
                                  Detected {formatDistanceToNow(new Date(anomaly.timestamp))} ago
                                </div>
                              </div>
                            </div>
                          }
                        />
                      </ListItem>
                    ))}
                  </List>
                </div>
              </div>
            </div>
          </div>

          <div className="grid" item xs={12} md={4}>
            <div className="grid" container spacing={3}>
              {/* AI Model Performance */}
              <div className="grid" item xs={12}>
                <div className="bg-white shadow-md rounded-lg">
                  <div className="bg-white shadow-md rounded-lg"Header title="AI Model Performance" />
                  <div className="bg-white shadow-md rounded-lg"Content>
                    <div  mb={3}>
                      <div  variant="body2" color="text.secondary" gutterBottom>
                        Sentiment Accuracy (7-day)
                      </div>
                      <div  display="flex" alignItems="center" gap={2}>
                        <div  flex={1}>
                          <div className="w-full bg-gray-200 rounded-full h-2" 
                            variant="determinate" 
                            value={newsData.aiInsights.modelPerformance.sentimentAccuracy}
                            color="success"
                            sx={{ height: 8, borderRadius: 4 }}
                          />
                        </div>
                        <div  variant="h6" color="success.main">
                          {newsData.aiInsights.modelPerformance.sentimentAccuracy}%
                        </div>
                      </div>
                    </div>
                    
                    <div  mb={3}>
                      <div  variant="body2" color="text.secondary" gutterBottom>
                        Prediction Accuracy (30-day)
                      </div>
                      <div  display="flex" alignItems="center" gap={2}>
                        <div  flex={1}>
                          <div className="w-full bg-gray-200 rounded-full h-2" 
                            variant="determinate" 
                            value={newsData.aiInsights.modelPerformance.predictionAccuracy}
                            color="primary"
                            sx={{ height: 8, borderRadius: 4 }}
                          />
                        </div>
                        <div  variant="h6" color="primary.main">
                          {newsData.aiInsights.modelPerformance.predictionAccuracy}%
                        </div>
                      </div>
                    </div>
                    
                    <div>
                      <div  variant="body2" color="text.secondary" gutterBottom>
                        Model Confidence
                      </div>
                      <div  display="flex" alignItems="center" gap={2}>
                        <div  flex={1}>
                          <div className="w-full bg-gray-200 rounded-full h-2" 
                            variant="determinate" 
                            value={newsData.aiInsights.modelPerformance.confidence}
                            color="info"
                            sx={{ height: 8, borderRadius: 4 }}
                          />
                        </div>
                        <div  variant="h6" color="info.main">
                          {newsData.aiInsights.modelPerformance.confidence}%
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* News Impact Score */}
              <div className="grid" item xs={12}>
                <div className="bg-white shadow-md rounded-lg">
                  <div className="bg-white shadow-md rounded-lg"Header title="News Impact Scoring" />
                  <div className="bg-white shadow-md rounded-lg"Content>
                    <div  variant="body2" color="text.secondary" paragraph>
                      AI-calculated impact scores for recent news events
                    </div>
                    <List dense>
                      {newsData.aiInsights.impactScores.map((score, index) => (
                        <ListItem key={index} disablePadding>
                          <ListItemText
                            primary={
                              <div  display="flex" alignItems="center" justifyContent="between">
                                <div  variant="body2">
                                  {score.event}
                                </div>
                                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                                  label={score.score}
                                  color={score.score >= 80 ? 'error' : score.score >= 60 ? 'warning' : 'success'}
                                  size="small"
                                />
                              </div>
                            }
                            secondary={
                              <div className="w-full bg-gray-200 rounded-full h-2" 
                                variant="determinate" 
                                value={score.score}
                                color={score.score >= 80 ? 'error' : score.score >= 60 ? 'warning' : 'success'}
                                sx={{ mt: 0.5 }}
                              />
                            }
                          />
                        </ListItem>
                      ))}
                    </List>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

// ⚠️ MOCK DATA - Replace with real API when available
const mockNewsData = {
  isMockData: true,
  sentiment: {
    overall: 'Bullish',
    distribution: {
      bullish: 65,
      neutral: 25,
      bearish: 10
    },
    aiConfidence: 87
  },
  aiInsights: {
    sentimentTimeline: [
      { time: '00:00', sentiment: 15, volume: 45 },
      { time: '04:00', sentiment: 28, volume: 52 },
      { time: '08:00', sentiment: 42, volume: 78 },
      { time: '12:00', sentiment: 38, volume: 95 },
      { time: '16:00', sentiment: 55, volume: 87 },
      { time: '20:00', sentiment: 48, volume: 63 }
    ],
    marketRegime: {
      current: 'Risk-On',
      confidence: 78,
      indicators: [
        { name: 'VIX Level', value: -15 },
        { name: 'Credit Spreads', value: -8 },
        { name: 'Momentum Factor', value: 23 },
        { name: 'News Sentiment', value: 35 }
      ]
    },
    predictions: [
      {
        target: 'S&P 500',
        timeframe: '1 Week',
        direction: 'up',
        magnitude: 2.3,
        confidence: 72,
        reasoning: 'Strong earnings momentum and dovish Fed signals suggest continued upward pressure'
      },
      {
        target: 'Tech Sector',
        timeframe: '2 Weeks',
        direction: 'up',
        magnitude: 4.1,
        confidence: 68,
        reasoning: 'AI revenue growth and multiple expansion driving tech outperformance'
      }
    ],
    anomalies: [
      {
        title: 'Unusual Options Activity in Banking Sector',
        description: 'Significant increase in put options activity suggests institutional hedging ahead of regulatory announcements',
        severity: 'high',
        timestamp: '2024-03-07T13:30:00Z'
      },
      {
        title: 'Dark Pool Activity Spike',
        description: 'Large institutional blocks detected in tech names, suggesting potential repositioning',
        severity: 'medium',
        timestamp: '2024-03-07T11:15:00Z'
      }
    ],
    modelPerformance: {
      sentimentAccuracy: 87,
      predictionAccuracy: 72,
      confidence: 84
    },
    impactScores: [
      { event: 'Fed Rate Decision', score: 95 },
      { event: 'AAPL Earnings', score: 78 },
      { event: 'Oil Supply News', score: 65 },
      { event: 'Tech Layoffs', score: 45 }
    ]
  },
  stats: {
    articlesToday: 234,
    articlesChange: 15,
    eventsThisWeek: 12,
    highImpactEvents: 3
  },
  alerts: [
    {
      id: 1,
      type: 'earnings',
      message: 'AAPL earnings expected after market close',
      severity: 'high'
    }
  ],
  news: [
    {
      isMockData: true,
      id: 1,
      title: 'Federal Reserve Signals Potential Rate Cuts Amid Economic Concerns',
      summary: 'Fed officials hint at possible monetary policy adjustments as economic indicators show mixed signals, with markets responding positively to dovish commentary.',
      source: 'Reuters',
      timestamp: '2024-03-07T14:30:00Z',
      sentiment: 'Bullish',
      impact: 'High',
      category: 'economic',
      tickers: ['SPY', 'QQQ'],
      url: '#'
    },
    {
      isMockData: true,
      id: 2,
      title: 'Tech Stocks Rally on Strong AI Revenue Growth',
      summary: 'Major technology companies report robust AI-driven revenue growth, leading to broad-based rally in tech sector with particular strength in semiconductor stocks.',
      source: 'Bloomberg',
      timestamp: '2024-03-07T13:15:00Z',
      sentiment: 'Bullish',
      impact: 'Medium',
      category: 'market',
      tickers: ['NVDA', 'AMD', 'INTC'],
      url: '#'
    },
    {
      isMockData: true,
      id: 3,
      title: 'Oil Prices Surge on Geopolitical Tensions',
      summary: 'Crude oil futures jump 3% as geopolitical tensions escalate, raising concerns about supply disruptions and boosting energy sector stocks.',
      source: 'CNBC',
      timestamp: '2024-03-07T12:45:00Z',
      sentiment: 'Neutral',
      impact: 'Medium',
      category: 'market',
      tickers: ['XOM', 'CVX', 'USO'],
      url: '#'
    },
    {
      isMockData: true,
      id: 4,
      title: 'Apple Announces New Product Launch Event',
      summary: 'Apple schedules special event for March 25th, sparking speculation about new iPad models and AI-enhanced features across product lineup.',
      source: 'TechCrunch',
      timestamp: '2024-03-07T11:20:00Z',
      sentiment: 'Bullish',
      impact: 'Medium',
      category: 'corporate',
      tickers: ['AAPL'],
      url: '#'
    },
    {
      isMockData: true,
      id: 5,
      title: 'Banking Sector Under Pressure from Regulatory Concerns',
      summary: 'Regional banks face headwinds as regulators propose stricter capital requirements, leading to sector-wide selloff in afternoon trading.',
      source: 'Wall Street Journal',
      timestamp: '2024-03-07T10:30:00Z',
      sentiment: 'Bearish',
      impact: 'High',
      category: 'market',
      tickers: ['KRE', 'BAC', 'JPM'],
      url: '#'
    }
  ],
  trendingTopics: [
    { topic: 'Federal Reserve', mentions: 156 },
    { topic: 'AI Technology', mentions: 134 },
    { topic: 'Oil Prices', mentions: 98 },
    { topic: 'Banking Regulation', mentions: 87 },
    { topic: 'Earnings Season', mentions: 76 },
    { topic: 'Geopolitical Risk', mentions: 65 }
  ],
  newsMovers: [
    { symbol: 'NVDA', change: 4.2, reason: 'AI revenue growth reports' },
    { symbol: 'XOM', change: 3.1, reason: 'Oil price surge on tensions' },
    { symbol: 'AAPL', change: 1.8, reason: 'Product launch announcement' },
    { symbol: 'KRE', change: -2.5, reason: 'Banking regulatory concerns' }
  ],
  upcomingEvents: [
    {
      id: 1,
      title: 'FOMC Meeting Minutes Release',
      description: 'Federal Reserve releases minutes from last policy meeting',
      date: '2024-03-08T14:00:00Z',
      type: 'economic',
      impact: 'High',
      tickers: ['SPY', 'TLT']
    },
    {
      id: 2,
      title: 'Apple Product Launch Event',
      description: 'Apple presents new iPad models and AI features',
      date: '2024-03-25T18:00:00Z',
      type: 'announcement',
      impact: 'Medium',
      tickers: ['AAPL']
    },
    {
      id: 3,
      title: 'Monthly Jobs Report',
      description: 'Bureau of Labor Statistics releases employment data',
      date: '2024-03-08T08:30:00Z',
      type: 'economic',
      impact: 'High',
      tickers: ['SPY', 'DXY']
    },
    {
      id: 4,
      title: 'Tesla Earnings Call',
      description: 'Tesla reports Q1 2024 earnings and provides guidance',
      date: '2024-03-20T21:30:00Z',
      type: 'earnings',
      impact: 'Medium',
      tickers: ['TSLA']
    }
  ]
};

export default NewsAnalysis;