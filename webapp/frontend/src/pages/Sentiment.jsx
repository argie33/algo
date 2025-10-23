import React, { useState, useMemo } from "react";
import {
  Container,
  Typography,
  Box,
  Card,
  CardContent,
  Grid,
  TextField,
  Chip,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Alert,
  CircularProgress,
  Divider,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  InputAdornment,
  Tab,
  Tabs,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  useTheme,
  alpha,
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
} from "@mui/icons-material";
import { useQuery } from "@tanstack/react-query";
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip as RechartsTooltip, AreaChart, Area, XAxis, YAxis, CartesianGrid, Legend, LineChart, Line } from "recharts";

const API_BASE = (import.meta.env && import.meta.env.VITE_API_URL) || "http://localhost:3001";

// Market Sentiment Gauge Component
const SentimentGauge = ({ label, value, min = -1, max = 1, format = "decimal" }) => {
  const theme = useTheme();

  // Handle undefined/null values
  const safeValue = value ?? 0;
  const percentage = ((safeValue - min) / (max - min)) * 100;

  let color = theme.palette.warning.main;
  let sentiment = "Neutral";

  if (format === "percentage") {
    if (safeValue > 60) {
      color = theme.palette.success.main;
      sentiment = "Very Bullish";
    } else if (safeValue > 45) {
      color = theme.palette.success.light;
      sentiment = "Bullish";
    } else if (safeValue > 35) {
      color = theme.palette.warning.main;
      sentiment = "Neutral";
    } else if (safeValue > 20) {
      color = theme.palette.warning.light;
      sentiment = "Bearish";
    } else {
      color = theme.palette.error.main;
      sentiment = "Very Bearish";
    }
  } else {
    if (safeValue > 0.5) {
      color = theme.palette.success.main;
      sentiment = "Very Bullish";
    } else if (safeValue > 0.2) {
      color = theme.palette.success.light;
      sentiment = "Bullish";
    } else if (safeValue > -0.2) {
      color = theme.palette.warning.main;
      sentiment = "Neutral";
    } else if (safeValue > -0.5) {
      color = theme.palette.warning.light;
      sentiment = "Bearish";
    } else {
      color = theme.palette.error.main;
      sentiment = "Very Bearish";
    }
  }

  return (
    <Card sx={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <CardContent sx={{ textAlign: "center", flex: 1 }}>
        <Typography variant="subtitle2" sx={{ mb: 2, fontWeight: 600, color: "textSecondary" }}>
          {label}
        </Typography>
        <Typography variant="h4" sx={{ fontWeight: 700, color: color, mb: 1 }}>
          {value === null || value === undefined ? "Loading..." : format === "percentage" ? `${safeValue.toFixed(1)}%` : safeValue.toFixed(2)}
        </Typography>
        <Chip label={sentiment} size="small" sx={{ bgcolor: alpha(color, 0.2), color: color }} />
      </CardContent>
    </Card>
  );
};

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

// Analyst Trend Card Component
const AnalystTrendCard = ({ symbol }) => {
  const theme = useTheme();
  const [trendData, setTrendData] = React.useState(null);
  const [chartData, setChartData] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState(null);

  React.useEffect(() => {
    const fetchTrendData = async () => {
      try {
        setLoading(true);
        const [momentumRes, trendRes] = await Promise.all([
          fetch(`${API_BASE}/api/analysts/${symbol}/analyst-momentum`),
          fetch(`${API_BASE}/api/analysts/${symbol}/sentiment-trend`)
        ]);

        if (!momentumRes.ok || !trendRes.ok) {
          setError("Failed to fetch analyst trend data");
          setTrendData(null);
          setChartData(null);
          return;
        }

        const momentumData = await momentumRes.json();
        const trendDataRaw = await trendRes.json();

        setTrendData(momentumData.data);
        setChartData(trendDataRaw.data?.chartData || []);
        setError(null);
      } catch (err) {
        console.error("Error fetching analyst trends:", err);
        setError("Unable to fetch analyst trends");
        setTrendData(null);
        setChartData(null);
      } finally {
        setLoading(false);
      }
    };

    fetchTrendData();
  }, [symbol]);

  if (loading) {
    return (
      <Card variant="outlined">
        <CardContent sx={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: 200 }}>
          <CircularProgress size={30} />
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card variant="outlined">
        <CardContent>
          <Box display="flex" alignItems="center" gap={1} mb={2}>
            <TrendingUpRounded />
            <Typography variant="h6">Analyst Trends</Typography>
          </Box>
          <Typography variant="body2" color="textSecondary">
            {error}
          </Typography>
        </CardContent>
      </Card>
    );
  }

  if (!trendData) {
    return (
      <Card variant="outlined">
        <CardContent>
          <Box display="flex" alignItems="center" gap={1} mb={2}>
            <TrendingUpRounded />
            <Typography variant="h6">Analyst Trends</Typography>
          </Box>
          <Typography variant="body2" color="textSecondary">
            No analyst trend data available for {symbol}
          </Typography>
        </CardContent>
      </Card>
    );
  }

  const getMomentumColor = (velocity) => {
    if (velocity?.includes("↗️")) return theme.palette.success.main;
    if (velocity?.includes("↘️")) return theme.palette.error.main;
    return theme.palette.warning.main;
  };

  return (
    <>
      {/* Analyst Momentum Card */}
      <Card variant="outlined">
        <CardContent>
          <Box display="flex" alignItems="center" gap={1} mb={2}>
            <TrendingUpRounded />
            <Typography variant="h6">Analyst Momentum</Typography>
          </Box>

          {/* Sentiment Score */}
          <Box display="flex" justifyContent="space-between" mb={2}>
            <Typography variant="body2">Sentiment Score:</Typography>
            <Chip
              label={`${trendData.sentimentScore?.toFixed(1) || 0}%`}
              color={trendData.sentimentScore > 60 ? "success" : trendData.sentimentScore > 40 ? "warning" : "error"}
            />
          </Box>

          {/* Momentum Velocity */}
          <Box display="flex" justifyContent="space-between" mb={2}>
            <Typography variant="body2">Trend Direction:</Typography>
            <Chip
              label={trendData.ratingChangeVelocity || "Stable"}
              sx={{
                bgcolor: alpha(getMomentumColor(trendData.ratingChangeVelocity), 0.2),
                color: getMomentumColor(trendData.ratingChangeVelocity)
              }}
            />
          </Box>

          {/* Analyst Coverage */}
          <Box display="flex" justifyContent="space-between" mb={2}>
            <Typography variant="body2">Analyst Coverage:</Typography>
            <Chip label={`${trendData.analystCount || 0} analysts`} variant="outlined" />
          </Box>

          {/* Rating Distribution */}
          <Divider sx={{ my: 2 }} />
          <Typography variant="caption" color="textSecondary" sx={{ display: "block", mb: 1 }}>
            Current Rating Distribution:
          </Typography>
          <Box display="flex" gap={0.5} flexWrap="wrap">
            <Chip label={`Bullish: ${trendData.bullishPercentage?.toFixed(1) || 0}%`} size="small" color="success" variant="outlined" />
            <Chip label={`Neutral: ${trendData.neutralPercentage?.toFixed(1) || 0}%`} size="small" color="default" variant="outlined" />
            <Chip label={`Bearish: ${trendData.bearishPercentage?.toFixed(1) || 0}%`} size="small" color="error" variant="outlined" />
          </Box>

          {/* EPS Revision Momentum */}
          {trendData.revisionMomentum && (
            <>
              <Divider sx={{ my: 2 }} />
              <Typography variant="caption" color="textSecondary" sx={{ display: "block", mb: 1 }}>
                EPS Revision Momentum (30d):
              </Typography>
              <Box display="flex" gap={1}>
                <Chip label={`↑ ${trendData.revisionMomentum.up || 0}`} size="small" color="success" variant="outlined" />
                <Chip label={`↓ ${trendData.revisionMomentum.down || 0}`} size="small" color="error" variant="outlined" />
              </Box>
            </>
          )}
        </CardContent>
      </Card>

      {/* Sentiment Trend Chart */}
      {chartData && chartData.length > 0 && (
        <Card variant="outlined" sx={{ mt: 2 }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              90-Day Rating Trend
            </Typography>
            <ResponsiveContainer width="100%" height={250}>
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" />
                <YAxis domain={[1, 5]} label={{ value: "Rating (1=Buy, 5=Sell)", angle: -90, position: "insideLeft" }} />
                <RechartsTooltip
                  formatter={(value) => {
                    const ratingLabels = { 1: "Strong Buy", 2: "Buy", 3: "Hold", 4: "Sell", 5: "Strong Sell" };
                    return ratingLabels[Math.round(value)] || value.toFixed(2);
                  }}
                />
                <Legend />
                <Line
                  type="monotone"
                  dataKey="recommendationMean"
                  stroke={theme.palette.primary.main}
                  dot={false}
                  name="Average Rating"
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}
    </>
  );
};

function TabPanel(props) {
  const { children, value, index, ...other } = props;
  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`sentiment-tabpanel-${index}`}
      aria-labelledby={`sentiment-tab-${index}`}
      {...other}
    >
      {value === index && <Box sx={{ py: 3 }}>{children}</Box>}
    </div>
  );
}

function Sentiment() {
  const theme = useTheme();
  const [expandedSymbol, setExpandedSymbol] = useState(null);
  const [searchFilter, setSearchFilter] = useState("");
  const [tabValue, setTabValue] = useState(0);
  const [sortBy, setSortBy] = useState("composite");
  const [filterSentiment, setFilterSentiment] = useState("all");
  const [marketSentiment, setMarketSentiment] = useState({
    fearGreedIndex: null,
    naamExposure: null,
    aaiiSentiment: null
  });

  // Fetch market-level sentiment indicators
  React.useEffect(() => {
    const fetchMarketSentiment = async () => {
      try {
        const responses = await Promise.all([
          fetch(`${API_BASE}/api/market/fear-greed`).catch(() => null),
          fetch(`${API_BASE}/api/market/naaim`).catch(() => null),
          fetch(`${API_BASE}/api/market/aaii`).catch(() => null)
        ]);

        const data = await Promise.all(
          responses.map(r => r?.ok ? r.json().catch(() => null) : null)
        );

        console.log("Market sentiment data:", data); // Debug log

        setMarketSentiment({
          fearGreedIndex: data[0]?.data?.current_value || data[0]?.data?.[0]?.current_value,
          naamExposure: data[1]?.data?.mean_exposure || data[1]?.data?.[0]?.mean_exposure,
          aaiiSentiment: data[2]?.data || data[2]?.data?.[0]
        });
      } catch (error) {
        console.error("Failed to fetch market sentiment:", error);
      }
    };

    // Fetch immediately on load
    fetchMarketSentiment();

    // Set up auto-refresh every 5 minutes (300000ms)
    const interval = setInterval(fetchMarketSentiment, 300000);
    return () => clearInterval(interval);
  }, []);

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

    // Group by source type
    const source = (item.source || "").toLowerCase();
    if (source.includes("news") || source.includes("article")) {
      acc[symbol].news.push(item);
    } else if (source.includes("reddit") || source.includes("social") || source.includes("twitter")) {
      acc[symbol].social.push(item);
    } else if (source.includes("analyst") || source.includes("rating")) {
      acc[symbol].analyst.push(item);
    } else {
      // Default to news if source is unclear
      acc[symbol].news.push(item);
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

  const handleTabChange = (event, newValue) => {
    setTabValue(newValue);
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
          Composite sentiment scores from news, analyst ratings, and social media
        </Typography>
      </Box>

      {/* Market Sentiment Indicators */}
      <Grid container spacing={2} sx={{ mb: 4 }}>
        {/* Fear & Greed Index */}
        <Grid item xs={12} sm={6} md={3}>
          <Card sx={{ height: '100%', bgcolor: marketSentiment.fearGreedIndex < 30 ? 'error.light' : marketSentiment.fearGreedIndex > 70 ? 'success.light' : 'warning.light' }}>
            <CardContent>
              <Typography color="textSecondary" gutterBottom>
                Fear & Greed Index
              </Typography>
              <Typography variant="h5" sx={{ mb: 1 }}>
                {marketSentiment.fearGreedIndex !== null && marketSentiment.fearGreedIndex !== undefined ? marketSentiment.fearGreedIndex.toFixed(2) : 'Loading...'}
              </Typography>
              <Typography variant="body2" color="textSecondary">
                Scale: 0 (Extreme Fear) - 100 (Extreme Greed)
              </Typography>
              {marketSentiment.fearGreedIndex !== null && (
                <Chip
                  label={marketSentiment.fearGreedIndex < 30 ? 'Extreme Fear' : marketSentiment.fearGreedIndex < 50 ? 'Fear' : marketSentiment.fearGreedIndex < 70 ? 'Neutral' : 'Greed'}
                  size="small"
                  sx={{ mt: 1 }}
                  color={marketSentiment.fearGreedIndex < 30 ? 'error' : marketSentiment.fearGreedIndex > 70 ? 'success' : 'warning'}
                />
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* NAAIM Exposure */}
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="textSecondary" gutterBottom>
                NAAIM Exposure
              </Typography>
              <Typography variant="h5" sx={{ mb: 1 }}>
                {marketSentiment.naamExposure !== null && marketSentiment.naamExposure !== undefined ? marketSentiment.naamExposure.toFixed(2) : 'Loading...'}
              </Typography>
              <Typography variant="body2" color="textSecondary">
                Mean Exposure (0=out, 100=in)
              </Typography>
              {marketSentiment.naamExposure !== null && marketSentiment.naamExposure !== undefined && (
                <Chip
                  label={marketSentiment.naamExposure > 60 ? 'Bullish' : marketSentiment.naamExposure < 40 ? 'Bearish' : 'Neutral'}
                  size="small"
                  sx={{ mt: 1 }}
                  color={marketSentiment.naamExposure > 60 ? 'success' : marketSentiment.naamExposure < 40 ? 'error' : 'warning'}
                />
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* AAII Sentiment */}
        <Grid item xs={12} sm={6} md={3}>
          <Card>
            <CardContent>
              <Typography color="textSecondary" gutterBottom>
                AAII Sentiment
              </Typography>
              <Box sx={{ mt: 1 }}>
                <Box display="flex" justifyContent="space-between" mb={1}>
                  <Typography variant="body2">Bullish:</Typography>
                  <Chip label={marketSentiment.aaiiSentiment?.bullish ? `${(parseFloat(marketSentiment.aaiiSentiment.bullish) * 100).toFixed(2)}%` : 'N/A'} size="small" color="success" />
                </Box>
                <Box display="flex" justifyContent="space-between" mb={1}>
                  <Typography variant="body2">Neutral:</Typography>
                  <Chip label={marketSentiment.aaiiSentiment?.neutral ? `${(parseFloat(marketSentiment.aaiiSentiment.neutral) * 100).toFixed(2)}%` : 'N/A'} size="small" color="default" />
                </Box>
                <Box display="flex" justifyContent="space-between">
                  <Typography variant="body2">Bearish:</Typography>
                  <Chip label={marketSentiment.aaiiSentiment?.bearish ? `${(parseFloat(marketSentiment.aaiiSentiment.bearish) * 100).toFixed(2)}%` : 'N/A'} size="small" color="error" />
                </Box>
              </Box>
              <Typography variant="caption" color="textSecondary" sx={{ mt: 1, display: 'block' }}>
                Retail investor sentiment survey
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        {/* Market Classification */}
        <Grid item xs={12} sm={6} md={3}>
          <Card sx={{ display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
            <CardContent>
              <Typography color="textSecondary" gutterBottom>
                Market Classification
              </Typography>
              {marketSentiment.fearGreedIndex !== null && (
                <Typography variant="h6" sx={{ mb: 1 }}>
                  {marketSentiment.fearGreedIndex < 30 ? 'Extreme Fear' : marketSentiment.fearGreedIndex < 50 ? 'Fear' : marketSentiment.fearGreedIndex < 70 ? 'Greed' : 'Extreme Greed'}
                </Typography>
              )}
              <Divider sx={{ my: 1 }} />
              <Typography variant="caption" color="textSecondary">
                Based on Fear & Greed Index
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Tabs */}
      <Box sx={{ borderBottom: 1, borderColor: "divider", mb: 3 }}>
        <Tabs
          value={tabValue}
          onChange={handleTabChange}
          aria-label="sentiment views"
          variant="scrollable"
          scrollButtons="auto"
        >
          <Tab label="Stock Analysis" id="sentiment-tab-0" aria-controls="sentiment-tabpanel-0" />
          <Tab label="Comparative View" id="sentiment-tab-1" aria-controls="sentiment-tabpanel-1" />
          <Tab label="Market Metrics" id="sentiment-tab-2" aria-controls="sentiment-tabpanel-2" />
        </Tabs>
      </Box>

      {/* Controls for Stock Analysis Tab */}
      <TabPanel value={tabValue} index={0}>
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

        {/* Accordion List */}
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
                        backgroundColor: stock.divergence?.isDiverged
                          ? alpha(theme.palette.warning.main, 0.1)
                          : "grey.50",
                        "&:hover": { backgroundColor: "grey.100" },
                        borderLeft: stock.divergence?.isDiverged
                          ? `3px solid ${theme.palette.warning.main}`
                          : "none",
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
                      {stock.divergence?.isDiverged && (
                        <Alert severity={stock.divergence.severity === "critical" ? "error" : "warning"} sx={{ mb: 3, width: "100%" }}>
                          <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                            ⚠️ Source Divergence Detected
                          </Typography>
                          <Typography variant="body2" sx={{ mt: 1 }}>
                            {stock.divergence.message}. News, analyst, and social media sources show significantly different sentiment. Consider reviewing the individual source scores below.
                          </Typography>
                        </Alert>
                      )}
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
      </TabPanel>

      {/* Tab 2: Comparative View */}
      <TabPanel value={tabValue} index={1}>
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Sentiment Distribution by Source
            </Typography>
            <Grid container spacing={3}>
              <Grid item xs={12} md={6}>
                <ResponsiveContainer width="100%" height={300}>
                  <LineChart data={stocksList.slice(0, 10).map(s => ({
                    symbol: s.symbol,
                    news: s.latestNews?.sentiment_score || 0,
                    analyst: s.latestAnalyst?.sentiment_score || 0,
                    social: s.latestSocial?.sentiment_score || 0,
                  }))}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="symbol" />
                    <YAxis domain={[-1, 1]} />
                    <Legend />
                    <RechartsTooltip />
                    <Line type="monotone" dataKey="news" stroke="#0088FE" name="News" />
                    <Line type="monotone" dataKey="analyst" stroke="#00C49F" name="Analyst" />
                    <Line type="monotone" dataKey="social" stroke="#FFBB28" name="Social" />
                  </LineChart>
                </ResponsiveContainer>
              </Grid>
              <Grid item xs={12} md={6}>
                <Typography variant="body2" color="textSecondary" paragraph>
                  Composite Sentiment Distribution:
                </Typography>
                <ResponsiveContainer width="100%" height={300}>
                  <AreaChart data={stocksList.map((s, i) => ({
                    index: i,
                    score: s.compositeScore || 0,
                  }))}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="index" />
                    <YAxis domain={[-1, 1]} />
                    <RechartsTooltip />
                    <Area type="monotone" dataKey="score" stroke={theme.palette.primary.main} fill={alpha(theme.palette.primary.main, 0.3)} />
                  </AreaChart>
                </ResponsiveContainer>
              </Grid>
            </Grid>
          </CardContent>
        </Card>
      </TabPanel>

      {/* Tab 3: Market Metrics */}
      <TabPanel value={tabValue} index={2}>
        <Grid container spacing={3}>
          <Grid item xs={12} sm={6} md={3}>
            <SentimentGauge label="Fear & Greed" value={marketSentiment.fearGreedIndex || 0} min={0} max={100} format="percentage" />
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <SentimentGauge label="NAAIM Exposure" value={marketSentiment.naamExposure || 0} min={0} max={100} format="percentage" />
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <SentimentGauge label="AAII Bullish" value={marketSentiment.aaiiSentiment?.bullish ? parseFloat(marketSentiment.aaiiSentiment.bullish) * 100 : 0} min={0} max={100} format="percentage" />
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <Card>
              <CardContent sx={{ textAlign: "center" }}>
                <Typography variant="subtitle2" sx={{ mb: 2, fontWeight: 600, color: "textSecondary" }}>
                  Avg Composite Score
                </Typography>
                <Typography variant="h4" sx={{ fontWeight: 700, color: "primary.main", mb: 1 }}>
                  {stocksList && stocksList.length > 0 ? ((stocksList.reduce((sum, s) => sum + (s.compositeScore || 0), 0) / stocksList.length) || 0).toFixed(2) : "N/A"}
                </Typography>
                <Chip label="Data Summary" size="small" />
              </CardContent>
            </Card>
          </Grid>

          {/* Analyst Sentiment Metrics */}
          <Grid item xs={12} sm={6} md={3}>
            <Card>
              <CardContent sx={{ textAlign: "center" }}>
                <Typography variant="subtitle2" sx={{ mb: 2, fontWeight: 600, color: "textSecondary" }}>
                  Stocks with Better Analyst Sentiment
                </Typography>
                <Typography variant="h4" sx={{ fontWeight: 700, color: "success.main", mb: 1 }}>
                  {stocksList && stocksList.length > 0 ? stocksList.filter(s => s.latestAnalyst?.sentiment_score > 0.2).length : 0}
                </Typography>
                <Typography variant="caption" color="textSecondary">
                  out of {stocksList?.length || 0} stocks
                </Typography>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <Card>
              <CardContent sx={{ textAlign: "center" }}>
                <Typography variant="subtitle2" sx={{ mb: 2, fontWeight: 600, color: "textSecondary" }}>
                  Neutral Analyst Rating
                </Typography>
                <Typography variant="h4" sx={{ fontWeight: 700, color: "warning.main", mb: 1 }}>
                  {stocksList && stocksList.length > 0 ? stocksList.filter(s => (s.latestAnalyst?.sentiment_score || 0) >= -0.2 && (s.latestAnalyst?.sentiment_score || 0) <= 0.2).length : 0}
                </Typography>
                <Typography variant="caption" color="textSecondary">
                  out of {stocksList?.length || 0} stocks
                </Typography>
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <Card>
              <CardContent sx={{ textAlign: "center" }}>
                <Typography variant="subtitle2" sx={{ mb: 2, fontWeight: 600, color: "textSecondary" }}>
                  Stocks with Worse Analyst Sentiment
                </Typography>
                <Typography variant="h4" sx={{ fontWeight: 700, color: "error.main", mb: 1 }}>
                  {stocksList && stocksList.length > 0 ? stocksList.filter(s => s.latestAnalyst?.sentiment_score < -0.2).length : 0}
                </Typography>
                <Typography variant="caption" color="textSecondary">
                  out of {stocksList?.length || 0} stocks
                </Typography>
              </CardContent>
            </Card>
          </Grid>
        </Grid>

        {/* Additional Market Insights */}
        <Card sx={{ mt: 3 }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Market Sentiment Summary
            </Typography>
            <Divider sx={{ my: 2 }} />
            <Grid container spacing={2}>
              <Grid item xs={12} sm={4}>
                <Box>
                  <Typography variant="caption" color="textSecondary">
                    Bullish Stocks
                  </Typography>
                  <Typography variant="h5" sx={{ color: "success.main", fontWeight: "bold" }}>
                    {stocksList.filter(s => s.compositeScore > 0.3).length}
                  </Typography>
                </Box>
              </Grid>
              <Grid item xs={12} sm={4}>
                <Box>
                  <Typography variant="caption" color="textSecondary">
                    Neutral Stocks
                  </Typography>
                  <Typography variant="h5" sx={{ color: "warning.main", fontWeight: "bold" }}>
                    {stocksList.filter(s => s.compositeScore >= -0.3 && s.compositeScore <= 0.3).length}
                  </Typography>
                </Box>
              </Grid>
              <Grid item xs={12} sm={4}>
                <Box>
                  <Typography variant="caption" color="textSecondary">
                    Bearish Stocks
                  </Typography>
                  <Typography variant="h5" sx={{ color: "error.main", fontWeight: "bold" }}>
                    {stocksList.filter(s => s.compositeScore < -0.3).length}
                  </Typography>
                </Box>
              </Grid>
            </Grid>
          </CardContent>
        </Card>
      </TabPanel>
    </Container>
  );
}

export default Sentiment;
