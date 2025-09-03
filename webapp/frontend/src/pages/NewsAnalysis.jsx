import React, { useState, useEffect, useCallback } from "react";
import {
  Alert,
  Avatar,
  Box,
  Button,
  Card,
  CardContent,
  CardHeader,
  Chip,
  CircularProgress,
  Container,
  Divider,
  Grid,
  IconButton,
  List,
  ListItem,
  ListItemAvatar,
  ListItemText,
  MenuItem,
  Paper,
  Select,
  Tab,
  Tabs,
  TextField,
  Typography,
} from "@mui/material";
import {
  AccessTime,
  BookmarkBorder,
  Bookmark,
  Search,
  Analytics,
  Article,
  ShowChart,
  Insights,
  Psychology,
  SmartToy,
} from "@mui/icons-material";
import { apiCall, createLogger } from '../utils/apiService';

function TabPanel({ children, value, index, ...other }) {
  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`news-tabpanel-${index}`}
      aria-labelledby={`news-tab-${index}`}
      {...other}
    >
      {value === index && <Box sx={{ p: 3 }}>{children}</Box>}
    </div>
  );
}

const NewsAnalysis = () => {
  const [tabValue, setTabValue] = useState(0);
  const [_newsData, _setNewsData] = useState(null);
  const [articles, setArticles] = useState([]);
  const [marketSentiment, setMarketSentiment] = useState(null);
  const [sentimentDashboard, setSentimentDashboard] = useState(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("all");
  const [selectedTimeframe, setSelectedTimeframe] = useState("24h");
  const [bookmarkedNews, setBookmarkedNews] = useState(new Set());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  
  const logger = createLogger("NewsAnalysis");

  const fetchAllNewsData = useCallback(async () => {
    setLoading(true);
    setError(null);
    
    try {
      // Convert selectedTimeframe to API format
      const timeframeMap = {
        "1h": "1h",
        "4h": "4h", 
        "24h": "1d",
        "7d": "7d",
        "30d": "1m"
      };
      
      const apiTimeframe = timeframeMap[selectedTimeframe] || "1d";
      
      logger.info("Fetching news data", { 
        category: selectedCategory, 
        timeframe: apiTimeframe 
      });
      
      // Fetch articles
      const articlesParams = {
        category: selectedCategory !== "all" ? selectedCategory : undefined,
        timeframe: apiTimeframe,
        limit: 50
      };
      
      const articlesResponse = await apiCall(
        `/api/news/articles?${new URLSearchParams(
          Object.entries(articlesParams).filter(([_k, v]) => v !== undefined)
        ).toString()}`,
        { method: "GET" },
        "NewsAnalysis"
      );
      
      if (articlesResponse?.articles) {
        setArticles(articlesResponse.articles);
        logger.info("Articles loaded successfully", { count: (articlesResponse.articles?.length || 0) });
      }
      
      // Fetch market sentiment  
      const sentimentResponse = await apiCall(
        "/api/news/market-sentiment",
        { method: "GET" },
        "NewsAnalysis"
      );
      
      if (sentimentResponse) {
        setMarketSentiment(sentimentResponse);
        logger.info("Market sentiment loaded successfully");
      }
      
      // Fetch sentiment dashboard
      const dashboardResponse = await apiCall(
        "/api/news/sentiment-dashboard", 
        { method: "GET" },
        "NewsAnalysis"
      );
      
      if (dashboardResponse) {
        setSentimentDashboard(dashboardResponse);
        _setNewsData(dashboardResponse);
        logger.info("Sentiment dashboard loaded successfully");
      }
      
    } catch (err) {
      logger.error("Failed to fetch news data", err);
      setError(err.message || "Failed to load news data");
    } finally {
      setLoading(false);
    }
  }, [selectedCategory, selectedTimeframe, logger]);

  useEffect(() => {
    fetchAllNewsData();
  }, [fetchAllNewsData]);

  const handleTabChange = (event, newValue) => {
    setTabValue(newValue);
  };

  const handleBookmark = (articleId) => {
    setBookmarkedNews(prev => {
      const newSet = new Set(prev);
      if (newSet.has(articleId)) {
        newSet.delete(articleId);
      } else {
        newSet.add(articleId);
      }
      return newSet;
    });
  };

  const getTimeframeOptions = () => [
    { value: "1h", label: "Last Hour" },
    { value: "4h", label: "Last 4 Hours" },
    { value: "24h", label: "Last 24 Hours" },
    { value: "7d", label: "Last 7 Days" },
    { value: "30d", label: "Last 30 Days" }
  ];

  const getCategoryOptions = () => [
    { value: "all", label: "All Categories" },
    { value: "earnings", label: "Earnings" },
    { value: "fed", label: "Federal Reserve" },
    { value: "market", label: "Market News" },
    { value: "tech", label: "Technology" },
    { value: "finance", label: "Finance" }
  ];

  if (loading) {
    return (
      <Container maxWidth="xl" sx={{ mt: 4, mb: 4 }}>
        <Box display="flex" justifyContent="center" alignItems="center" minHeight="60vh">
          <Box textAlign="center">
            <CircularProgress size={60} sx={{ mb: 2 }} />
            <Typography variant="h6" color="text.secondary">
              Loading AI News Analysis...
            </Typography>
          </Box>
        </Box>
      </Container>
    );
  }

  if (error) {
    return (
      <Container maxWidth="xl" sx={{ mt: 4, mb: 4 }}>
        <Alert severity="error" sx={{ mb: 2 }}>
          <Typography variant="h6" gutterBottom>
            Error Loading News Data
          </Typography>
          <Typography variant="body2">
            {error}
          </Typography>
        </Alert>
        <Button 
          variant="contained" 
          onClick={fetchAllNewsData}
          sx={{ mt: 2 }}
        >
          Retry Loading
        </Button>
      </Container>
    );
  }

  return (
    <Container maxWidth="xl" sx={{ mt: 4, mb: 4 }}>
      {/* Header */}
      <Box sx={{ mb: 4 }}>
        <Box display="flex" alignItems="center" gap={2} mb={2}>
          <SmartToy sx={{ fontSize: 40, color: "primary.main" }} />
          <Box>
            <Typography variant="h4" component="h1" fontWeight="bold">
              AI News Analysis
            </Typography>
            <Typography variant="subtitle1" color="text.secondary">
              AI-powered market insights and sentiment analysis
            </Typography>
          </Box>
        </Box>

        {/* Controls */}
        <Paper sx={{ p: 2, mb: 3 }}>
          <Grid container spacing={2} alignItems="center">
            <Grid item xs={12} md={4}>
              <TextField
                fullWidth
                variant="outlined"
                placeholder="Search news..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                InputProps={{
                  startAdornment: <Search sx={{ mr: 1, color: "text.secondary" }} />,
                }}
              />
            </Grid>
            <Grid item xs={12} md={3}>
              <Select
                fullWidth
                value={selectedCategory}
                onChange={(e) => setSelectedCategory(e.target.value)}
                displayEmpty
              >
                {getCategoryOptions().map((option) => (
                  <MenuItem key={option.value} value={option.value}>
                    {option.label}
                  </MenuItem>
                ))}
              </Select>
            </Grid>
            <Grid item xs={12} md={3}>
              <Select
                fullWidth
                value={selectedTimeframe}
                onChange={(e) => setSelectedTimeframe(e.target.value)}
              >
                {getTimeframeOptions().map((option) => (
                  <MenuItem key={option.value} value={option.value}>
                    {option.label}
                  </MenuItem>
                ))}
              </Select>
            </Grid>
            <Grid item xs={12} md={2}>
              <Button
                fullWidth
                variant="outlined"
                onClick={fetchAllNewsData}
                disabled={loading}
                startIcon={loading ? <CircularProgress size={16} /> : <Analytics />}
              >
                {loading ? "Loading..." : "Analyze"}
              </Button>
            </Grid>
          </Grid>
        </Paper>

        {/* Tabs */}
        <Tabs
          value={tabValue}
          onChange={handleTabChange}
          indicatorColor="primary"
          textColor="primary"
          variant="scrollable"
          scrollButtons="auto"
        >
          <Tab
            label="Market Sentiment"
            icon={<Psychology />}
            iconPosition="start"
          />
          <Tab
            label="AI Insights"
            icon={<Insights />}
            iconPosition="start"
          />
          <Tab
            label="News Articles"
            icon={<Article />}
            iconPosition="start"
          />
          <Tab
            label="Market Impact"
            icon={<ShowChart />}
            iconPosition="start"
          />
        </Tabs>
      </Box>

      {/* Tab Panels */}
      <TabPanel value={tabValue} index={0}>
        <Grid container spacing={3}>
          {/* Market Sentiment Overview */}
          <Grid item xs={12} lg={8}>
            <Card>
              <CardHeader 
                title="Market Sentiment Overview"
                subheader="Real-time sentiment analysis from multiple sources"
              />
              <CardContent>
                {marketSentiment ? (
                  <Box>
                    <Typography variant="h6" gutterBottom>
                      Overall Sentiment: {marketSentiment.overall || "Neutral"}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      Last Updated: {new Date().toLocaleString()}
                    </Typography>
                  </Box>
                ) : (
                  <Typography variant="body2" color="text.secondary">
                    No market sentiment data available
                  </Typography>
                )}
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} lg={4}>
            <Card>
              <CardHeader title="Sentiment Distribution" />
              <CardContent>
                <Typography variant="body2" color="text.secondary">
                  Sentiment breakdown will be displayed here when data is available.
                </Typography>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </TabPanel>

      <TabPanel value={tabValue} index={1}>
        <Card>
          <CardHeader 
            title="AI-Powered Insights"
            subheader="Machine learning analysis of market trends and patterns"
          />
          <CardContent>
            {sentimentDashboard ? (
              <Box>
                <Typography variant="h6" gutterBottom>
                  AI Analysis Results
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Dashboard data loaded successfully
                </Typography>
              </Box>
            ) : (
              <Typography variant="body2" color="text.secondary">
                No AI insights available at the moment
              </Typography>
            )}
          </CardContent>
        </Card>
      </TabPanel>

      <TabPanel value={tabValue} index={2}>
        <Card>
          <CardHeader 
            title="Latest News Articles"
            subheader={`Showing ${(articles?.length || 0)} articles`}
          />
          <CardContent>
            {articles.length > 0 ? (
              <List>
                {articles
                  .filter(article => 
                    !searchTerm || 
                    article.headline?.toLowerCase().includes(searchTerm.toLowerCase()) ||
                    article.summary?.toLowerCase().includes(searchTerm.toLowerCase())
                  )
                  .slice(0, 20)
                  .map((article, index) => (
                    <React.Fragment key={article.id || index}>
                      <ListItem alignItems="flex-start">
                        <ListItemAvatar>
                          <Avatar sx={{ bgcolor: "primary.main" }}>
                            <Article />
                          </Avatar>
                        </ListItemAvatar>
                        <ListItemText
                          primary={
                            <Box display="flex" justifyContent="space-between" alignItems="flex-start">
                              <Typography variant="h6" component="div" sx={{ flexGrow: 1, pr: 1 }}>
                                {article.headline || article.title || "Untitled Article"}
                              </Typography>
                              <IconButton
                                size="small"
                                onClick={() => handleBookmark(article.id)}
                                sx={{ ml: 1 }}
                              >
                                {bookmarkedNews.has(article.id) ? 
                                  <Bookmark color="primary" /> : 
                                  <BookmarkBorder />
                                }
                              </IconButton>
                            </Box>
                          }
                          secondary={
                            <Box>
                              <Typography variant="body2" color="text.secondary" paragraph>
                                {article.summary || "No summary available"}
                              </Typography>
                              <Box display="flex" alignItems="center" gap={2} flexWrap="wrap">
                                <Typography variant="caption" color="text.secondary">
                                  {article.source || "Unknown Source"}
                                </Typography>
                                <Typography variant="caption" color="text.secondary">
                                  <AccessTime sx={{ fontSize: 14, mr: 0.5 }} />
                                  {article.timestamp ? new Date(article.timestamp).toLocaleString() : "Unknown Time"}
                                </Typography>
                                {article.sentiment && (
                                  <Chip 
                                    label={article.sentiment} 
                                    size="small" 
                                    color={
                                      article.sentiment === "Positive" || article.sentiment === "Bullish" ? "success" :
                                      article.sentiment === "Negative" || article.sentiment === "Bearish" ? "error" : 
                                      "default"
                                    }
                                  />
                                )}
                                {article.impact && (
                                  <Chip 
                                    label={`${article.impact} Impact`} 
                                    size="small" 
                                    variant="outlined"
                                  />
                                )}
                              </Box>
                            </Box>
                          }
                        />
                      </ListItem>
                      {index < (articles?.length || 0) - 1 && <Divider variant="inset" component="li" />}
                    </React.Fragment>
                  ))}
              </List>
            ) : (
              <Typography variant="body2" color="text.secondary" textAlign="center" py={4}>
                No news articles available for the selected criteria
              </Typography>
            )}
          </CardContent>
        </Card>
      </TabPanel>

      <TabPanel value={tabValue} index={3}>
        <Card>
          <CardHeader 
            title="Market Impact Analysis"
            subheader="How news events are affecting market movements"
          />
          <CardContent>
            <Typography variant="body2" color="text.secondary">
              Market impact analysis will be displayed here when data is available.
            </Typography>
          </CardContent>
        </Card>
      </TabPanel>
    </Container>
  );
};

export default NewsAnalysis;