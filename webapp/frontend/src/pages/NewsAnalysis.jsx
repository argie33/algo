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
        <Box sx={{ p: 3 }}>
          {children}
        </Box>
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
    <Container maxWidth="xl" sx={{ py: 4 }}>
      {/* Header */}
      <Box display="flex" alignItems="center" justifyContent="between" mb={4}>
        <Box>
          <Typography variant="h3" component="h1" gutterBottom>
            News & Events Analysis
          </Typography>
          <Typography variant="body1" color="text.secondary">
            AI-powered market news analysis and event tracking
          </Typography>
        </Box>
        
        <Box display="flex" alignItems="center" gap={2}>
          <Badge badgeContent={newsData.alerts.length} color="error">
            <IconButton>
              <NotificationsActive />
            </IconButton>
          </Badge>
          <Button variant="outlined" startIcon={<Refresh />}>
            Refresh
          </Button>
        </Box>
      </Box>

      {/* Alert Summary */}
      {newsData.alerts.length > 0 && (
        <Alert 
          severity="warning" 
          sx={{ mb: 3 }}
          action={
            <Button color="inherit" size="small">
              View All
            </Button>
          }
        >
          <strong>{newsData.alerts.length} active alerts:</strong> {newsData.alerts[0].message}
          {newsData.alerts.length > 1 && ` and ${newsData.alerts.length - 1} more`}
        </Alert>
      )}

      {/* Market Sentiment Overview */}
      <Grid container spacing={3} mb={4}>
        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" justifyContent="between">
                <Box>
                  <Typography variant="h6" color="text.secondary">
                    News Sentiment
                  </Typography>
                  <Typography variant="h4" color="primary">
                    {newsData.sentiment.overall}
                  </Typography>
                  <Typography variant="body2">
                    {newsData.sentiment.distribution.bullish}% Bullish
                  </Typography>
                </Box>
                <TrendingUp color="primary" fontSize="large" />
              </Box>
              <LinearProgress 
                variant="determinate" 
                value={newsData.sentiment.distribution.bullish} 
                color="success"
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
                    Articles Today
                  </Typography>
                  <Typography variant="h4" color="secondary">
                    {newsData.stats.articlesToday}
                  </Typography>
                  <Typography variant="body2">
                    +{newsData.stats.articlesChange}% vs yesterday
                  </Typography>
                </Box>
                <Newspaper color="secondary" fontSize="large" />
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
                    Events This Week
                  </Typography>
                  <Typography variant="h4" color="info.main">
                    {newsData.stats.eventsThisWeek}
                  </Typography>
                  <Typography variant="body2">
                    {newsData.stats.highImpactEvents} high impact
                  </Typography>
                </Box>
                <Event color="info" fontSize="large" />
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
                  <Typography variant="h4" color="warning.main">
                    {newsData.sentiment.aiConfidence}%
                  </Typography>
                  <Typography variant="body2">
                    Analysis accuracy
                  </Typography>
                </Box>
                <Assessment color="warning" fontSize="large" />
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Filters */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Grid container spacing={2} alignItems="center">
            <Grid item xs={12} md={4}>
              <TextField
                fullWidth
                size="small"
                label="Search news..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                InputProps={{
                  startAdornment: <Search sx={{ mr: 1, color: 'text.secondary' }} />
                }}
              />
            </Grid>
            <Grid item xs={12} md={3}>
              <TextField
                select
                fullWidth
                size="small"
                label="Category"
                value={selectedCategory}
                onChange={(e) => setSelectedCategory(e.target.value)}
              >
                <MenuItem value="all">All Categories</MenuItem>
                <MenuItem value="earnings">Earnings</MenuItem>
                <MenuItem value="market">Market News</MenuItem>
                <MenuItem value="economic">Economic Data</MenuItem>
                <MenuItem value="corporate">Corporate News</MenuItem>
                <MenuItem value="analyst">Analyst Reports</MenuItem>
              </TextField>
            </Grid>
            <Grid item xs={12} md={3}>
              <TextField
                select
                fullWidth
                size="small"
                label="Timeframe"
                value={selectedTimeframe}
                onChange={(e) => setSelectedTimeframe(e.target.value)}
              >
                <MenuItem value="today">Today</MenuItem>
                <MenuItem value="week">This Week</MenuItem>
                <MenuItem value="month">This Month</MenuItem>
                <MenuItem value="all">All Time</MenuItem>
              </TextField>
            </Grid>
            <Grid item xs={12} md={2}>
              <Button
                fullWidth
                variant="outlined"
                startIcon={<FilterList />}
                size="small"
              >
                More Filters
              </Button>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      {/* Main Content Tabs */}
      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
        <Tabs value={tabValue} onChange={handleTabChange} aria-label="news analysis tabs">
          <Tab label="Breaking News" icon={<Newspaper />} />
          <Tab label="Market Events" icon={<Event />} />
          <Tab label="Earnings Calendar" icon={<Assessment />} />
          <Tab label="Economic Data" icon={<Business />} />
          <Tab label="AI Insights" icon={<Assessment />} />
        </Tabs>
      </Box>

      <TabPanel value={tabValue} index={0}>
        {/* Breaking News */}
        <Grid container spacing={3}>
          <Grid item xs={12} md={8}>
            <Card>
              <CardHeader 
                title="Latest Market News" 
                action={
                  <Chip 
                    label={`${filteredNews.length} articles`} 
                    color="primary" 
                    variant="outlined" 
                  />
                }
              />
              <CardContent>
                {loading ? (
                  <Box display="flex" justifyContent="center" p={4}>
                    <CircularProgress />
                  </Box>
                ) : (
                  <List>
                    {filteredNews.map((article, index) => (
                      <React.Fragment key={article.id}>
                        <ListItem alignItems="flex-start">
                          <ListItemAvatar>
                            <Avatar sx={{ bgcolor: getSentimentColor(article.sentiment) + '.main' }}>
                              {getSentimentIcon(article.sentiment)}
                            </Avatar>
                          </ListItemAvatar>
                          <ListItemText
                            primary={
                              <Box display="flex" alignItems="center" gap={1} mb={1}>
                                <Typography variant="h6" component="span">
                                  {article.title}
                                </Typography>
                                <Chip 
                                  label={article.impact} 
                                  color={getImpactColor(article.impact)}
                                  size="small"
                                />
                              </Box>
                            }
                            secondary={
                              <Box>
                                <Typography variant="body2" color="text.primary" paragraph>
                                  {article.summary}
                                </Typography>
                                <Box display="flex" alignItems="center" justifyContent="between">
                                  <Box display="flex" alignItems="center" gap={2}>
                                    <Typography variant="caption" color="text.secondary">
                                      {article.source} • {formatDistanceToNow(new Date(article.timestamp))} ago
                                    </Typography>
                                    <Chip 
                                      label={article.sentiment} 
                                      color={getSentimentColor(article.sentiment)}
                                      size="small"
                                      variant="outlined"
                                    />
                                    {article.tickers.map(ticker => (
                                      <Chip key={ticker} label={ticker} size="small" variant="outlined" />
                                    ))}
                                  </Box>
                                  <Box>
                                    <IconButton 
                                      size="small" 
                                      onClick={() => toggleBookmark(article.id)}
                                      color={bookmarkedNews.has(article.id) ? 'primary' : 'default'}
                                    >
                                      {bookmarkedNews.has(article.id) ? <Bookmark /> : <BookmarkBorder />}
                                    </IconButton>
                                    <IconButton size="small">
                                      <Share />
                                    </IconButton>
                                    <IconButton size="small">
                                      <OpenInNew />
                                    </IconButton>
                                  </Box>
                                </Box>
                              </Box>
                            }
                          />
                        </ListItem>
                        {index < filteredNews.length - 1 && <Divider variant="inset" component="li" />}
                      </React.Fragment>
                    ))}
                  </List>
                )}
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} md={4}>
            <Grid container spacing={3}>
              {/* Trending Topics */}
              <Grid item xs={12}>
                <Card>
                  <CardHeader title="Trending Topics" />
                  <CardContent>
                    <Box display="flex" flexWrap="wrap" gap={1}>
                      {newsData.trendingTopics.map((topic, index) => (
                        <Chip
                          key={topic.topic}
                          label={`${topic.topic} (${topic.mentions})`}
                          color={index < 3 ? 'primary' : 'default'}
                          variant={index < 3 ? 'filled' : 'outlined'}
                          size="small"
                        />
                      ))}
                    </Box>
                  </CardContent>
                </Card>
              </Grid>

              {/* Market Movers */}
              <Grid item xs={12}>
                <Card>
                  <CardHeader title="News-Driven Movers" />
                  <CardContent>
                    <List dense>
                      {newsData.newsMovers.map((mover) => (
                        <ListItem key={mover.symbol} disablePadding>
                          <ListItemText
                            primary={
                              <Box display="flex" alignItems="center" justifyContent="between">
                                <Typography variant="body2" fontWeight="bold">
                                  {mover.symbol}
                                </Typography>
                                <Chip
                                  label={`${mover.change >= 0 ? '+' : ''}${formatPercentage(mover.change)}`}
                                  color={mover.change >= 0 ? 'success' : 'error'}
                                  size="small"
                                />
                              </Box>
                            }
                            secondary={mover.reason}
                          />
                        </ListItem>
                      ))}
                    </List>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          </Grid>
        </Grid>
      </TabPanel>

      <TabPanel value={tabValue} index={1}>
        {/* Market Events */}
        <Grid container spacing={3}>
          <Grid item xs={12} md={8}>
            <Card>
              <CardHeader title="Upcoming Market Events" />
              <CardContent>
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
                        <Typography variant="h6" component="span">
                          {event.title}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          {event.description}
                        </Typography>
                        <Box display="flex" gap={1} mt={1}>
                          <Chip label={event.type} size="small" variant="outlined" />
                          <Chip 
                            label={`${event.impact} Impact`} 
                            color={getImpactColor(event.impact)}
                            size="small"
                          />
                          {event.tickers.map(ticker => (
                            <Chip key={ticker} label={ticker} size="small" variant="outlined" />
                          ))}
                        </Box>
                      </TimelineContent>
                    </TimelineItem>
                  ))}
                </Timeline>
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} md={4}>
            <Card>
              <CardHeader title="Event Impact Analysis" />
              <CardContent>
                <Typography variant="body2" color="text.secondary" paragraph>
                  AI-powered analysis of upcoming events and their potential market impact.
                </Typography>
                <Alert severity="info" sx={{ mb: 2 }}>
                  This week: 3 high-impact events expected to drive volatility
                </Alert>
                {/* Add more event analysis content here */}
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </TabPanel>

      <TabPanel value={tabValue} index={2}>
        {/* Earnings Calendar */}
        <Grid container spacing={3}>
          <Grid item xs={12}>
            <Card>
              <CardHeader title="Earnings Calendar" />
              <CardContent>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                  Comprehensive earnings calendar with AI-powered estimates and analysis
                </Typography>
                <Alert severity="info">
                  This feature will show detailed earnings calendar, analyst estimates, and historical performance.
                </Alert>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </TabPanel>

      <TabPanel value={tabValue} index={3}>
        {/* Economic Data */}
        <Grid container spacing={3}>
          <Grid item xs={12}>
            <Card>
              <CardHeader title="Economic Data Releases" />
              <CardContent>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                  Real-time economic data releases and their market impact analysis
                </Typography>
                <Alert severity="info">
                  This feature will show economic data releases, forecasts vs actual, and market reactions.
                </Alert>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </TabPanel>

      <TabPanel value={tabValue} index={4}>
        {/* AI Insights */}
        <Grid container spacing={3}>
          <Grid item xs={12} md={8}>
            <Card>
              <CardHeader 
                title="AI-Powered Market Insights" 
                subheader="Advanced sentiment analysis and predictive modeling"
                action={
                  <Box display="flex" alignItems="center" gap={1}>
                    <Chip label="Live Analysis" color="success" size="small" />
                    <Chip label={`${newsData.sentiment.aiConfidence}% Confidence`} color="info" size="small" />
                  </Box>
                }
              />
              <CardContent>
                {/* AI Sentiment Timeline */}
                <Box mb={4}>
                  <Typography variant="h6" gutterBottom>
                    Sentiment Evolution (24h)
                  </Typography>
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
                </Box>

                {/* Market Regime Detection */}
                <Box mb={4}>
                  <Typography variant="h6" gutterBottom>
                    Market Regime Analysis
                  </Typography>
                  <Grid container spacing={2}>
                    <Grid item xs={12} md={4}>
                      <Card variant="outlined">
                        <CardContent>
                          <Box display="flex" alignItems="center" gap={2}>
                            <Avatar sx={{ bgcolor: 'success.main' }}>
                              <TrendingUp />
                            </Avatar>
                            <Box>
                              <Typography variant="h6">
                                {newsData.aiInsights.marketRegime.current}
                              </Typography>
                              <Typography variant="body2" color="text.secondary">
                                Current Regime
                              </Typography>
                            </Box>
                          </Box>
                          <LinearProgress 
                            variant="determinate" 
                            value={newsData.aiInsights.marketRegime.confidence}
                            sx={{ mt: 2 }}
                          />
                          <Typography variant="caption" color="text.secondary">
                            {newsData.aiInsights.marketRegime.confidence}% Confidence
                          </Typography>
                        </CardContent>
                      </Card>
                    </Grid>
                    <Grid item xs={12} md={8}>
                      <Card variant="outlined">
                        <CardContent>
                          <Typography variant="subtitle1" gutterBottom>
                            Key Regime Indicators
                          </Typography>
                          <List dense>
                            {newsData.aiInsights.marketRegime.indicators.map((indicator, index) => (
                              <ListItem key={index}>
                                <ListItemText
                                  primary={indicator.name}
                                  secondary={
                                    <Box display="flex" alignItems="center" gap={1}>
                                      <LinearProgress 
                                        variant="determinate" 
                                        value={Math.abs(indicator.value)}
                                        sx={{ flexGrow: 1, height: 6, borderRadius: 3 }}
                                        color={indicator.value >= 0 ? 'success' : 'error'}
                                      />
                                      <Typography variant="caption">
                                        {indicator.value >= 0 ? '+' : ''}{indicator.value}%
                                      </Typography>
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
                </Box>

                {/* AI Predictions */}
                <Box mb={4}>
                  <Typography variant="h6" gutterBottom>
                    AI Market Predictions
                  </Typography>
                  <Grid container spacing={2}>
                    {newsData.aiInsights.predictions.map((prediction, index) => (
                      <Grid item xs={12} md={6} key={index}>
                        <Card variant="outlined">
                          <CardContent>
                            <Box display="flex" alignItems="center" justifyContent="between" mb={2}>
                              <Typography variant="subtitle1">
                                {prediction.target}
                              </Typography>
                              <Chip 
                                label={prediction.timeframe}
                                color="primary"
                                size="small"
                                variant="outlined"
                              />
                            </Box>
                            <Box display="flex" alignItems="center" gap={2} mb={2}>
                              <Box flex={1}>
                                <Typography variant="h5" color={prediction.direction === 'up' ? 'success.main' : 'error.main'}>
                                  {prediction.direction === 'up' ? '↗' : '↘'} {prediction.magnitude}%
                                </Typography>
                                <Typography variant="body2" color="text.secondary">
                                  Predicted Move
                                </Typography>
                              </Box>
                              <Box textAlign="right">
                                <Typography variant="h6">
                                  {prediction.confidence}%
                                </Typography>
                                <Typography variant="body2" color="text.secondary">
                                  Confidence
                                </Typography>
                              </Box>
                            </Box>
                            <Typography variant="body2" color="text.secondary">
                              {prediction.reasoning}
                            </Typography>
                          </CardContent>
                        </Card>
                      </Grid>
                    ))}
                  </Grid>
                </Box>

                {/* Anomaly Detection */}
                <Box>
                  <Typography variant="h6" gutterBottom>
                    Market Anomalies Detected
                  </Typography>
                  <List>
                    {newsData.aiInsights.anomalies.map((anomaly, index) => (
                      <ListItem key={index}>
                        <ListItemAvatar>
                          <Avatar sx={{ bgcolor: anomaly.severity === 'high' ? 'error.main' : 'warning.main' }}>
                            <Warning />
                          </Avatar>
                        </ListItemAvatar>
                        <ListItemText
                          primary={anomaly.title}
                          secondary={
                            <Box>
                              <Typography variant="body2" color="text.primary">
                                {anomaly.description}
                              </Typography>
                              <Box display="flex" alignItems="center" gap={1} mt={1}>
                                <Chip 
                                  label={anomaly.severity}
                                  color={anomaly.severity === 'high' ? 'error' : 'warning'}
                                  size="small"
                                />
                                <Typography variant="caption" color="text.secondary">
                                  Detected {formatDistanceToNow(new Date(anomaly.timestamp))} ago
                                </Typography>
                              </Box>
                            </Box>
                          }
                        />
                      </ListItem>
                    ))}
                  </List>
                </Box>
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} md={4}>
            <Grid container spacing={3}>
              {/* AI Model Performance */}
              <Grid item xs={12}>
                <Card>
                  <CardHeader title="AI Model Performance" />
                  <CardContent>
                    <Box mb={3}>
                      <Typography variant="body2" color="text.secondary" gutterBottom>
                        Sentiment Accuracy (7-day)
                      </Typography>
                      <Box display="flex" alignItems="center" gap={2}>
                        <Box flex={1}>
                          <LinearProgress 
                            variant="determinate" 
                            value={newsData.aiInsights.modelPerformance.sentimentAccuracy}
                            color="success"
                            sx={{ height: 8, borderRadius: 4 }}
                          />
                        </Box>
                        <Typography variant="h6" color="success.main">
                          {newsData.aiInsights.modelPerformance.sentimentAccuracy}%
                        </Typography>
                      </Box>
                    </Box>
                    
                    <Box mb={3}>
                      <Typography variant="body2" color="text.secondary" gutterBottom>
                        Prediction Accuracy (30-day)
                      </Typography>
                      <Box display="flex" alignItems="center" gap={2}>
                        <Box flex={1}>
                          <LinearProgress 
                            variant="determinate" 
                            value={newsData.aiInsights.modelPerformance.predictionAccuracy}
                            color="primary"
                            sx={{ height: 8, borderRadius: 4 }}
                          />
                        </Box>
                        <Typography variant="h6" color="primary.main">
                          {newsData.aiInsights.modelPerformance.predictionAccuracy}%
                        </Typography>
                      </Box>
                    </Box>
                    
                    <Box>
                      <Typography variant="body2" color="text.secondary" gutterBottom>
                        Model Confidence
                      </Typography>
                      <Box display="flex" alignItems="center" gap={2}>
                        <Box flex={1}>
                          <LinearProgress 
                            variant="determinate" 
                            value={newsData.aiInsights.modelPerformance.confidence}
                            color="info"
                            sx={{ height: 8, borderRadius: 4 }}
                          />
                        </Box>
                        <Typography variant="h6" color="info.main">
                          {newsData.aiInsights.modelPerformance.confidence}%
                        </Typography>
                      </Box>
                    </Box>
                  </CardContent>
                </Card>
              </Grid>

              {/* News Impact Score */}
              <Grid item xs={12}>
                <Card>
                  <CardHeader title="News Impact Scoring" />
                  <CardContent>
                    <Typography variant="body2" color="text.secondary" paragraph>
                      AI-calculated impact scores for recent news events
                    </Typography>
                    <List dense>
                      {newsData.aiInsights.impactScores.map((score, index) => (
                        <ListItem key={index} disablePadding>
                          <ListItemText
                            primary={
                              <Box display="flex" alignItems="center" justifyContent="between">
                                <Typography variant="body2">
                                  {score.event}
                                </Typography>
                                <Chip
                                  label={score.score}
                                  color={score.score >= 80 ? 'error' : score.score >= 60 ? 'warning' : 'success'}
                                  size="small"
                                />
                              </Box>
                            }
                            secondary={
                              <LinearProgress 
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