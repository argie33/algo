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
const AnalystTrendCard = ({ symbol, allData }) => {
  const theme = useTheme();

  // Filter analyst data from the provided data
  const analystData = React.useMemo(() => {
    if (!allData || !Array.isArray(allData)) return [];
    return allData.filter(item => item.source === "analyst");
  }, [allData]);

  // Calculate comprehensive analyst metrics
  const analystMetrics = React.useMemo(() => {
    if (analystData.length === 0) return null;

    const currentData = analystData[0];
    const metadata = currentData?.metadata || {};
    const recentData = analystData.slice(0, 30);

    // Calculate average sentiment score
    const avgScore = recentData.reduce((sum, d) => sum + (d.sentiment_score || 0), 0) / recentData.length;
    const sentimentScore = Math.max(0, Math.min(100, (avgScore + 1) * 50));

    // Determine trend direction
    const oldestData = recentData[recentData.length - 1];
    const ratingChange = (currentData?.sentiment_score || 0) - (oldestData?.sentiment_score || 0);
    const trendDirection = ratingChange > 0.1 ? "↗️ Improving" : ratingChange < -0.1 ? "↘️ Declining" : "→ Stable";

    // Rating distribution from metadata
    const strongBuy = metadata.strong_buy_count || 0;
    const buy = metadata.buy_count || 0;
    const hold = metadata.hold_count || 0;
    const sell = metadata.sell_count || 0;
    const strongSell = metadata.strong_sell_count || 0;
    const totalRatings = strongBuy + buy + hold + sell + strongSell;

    const bullishCount = strongBuy + buy;
    const bearishCount = sell + strongSell;
    const bullishPercentage = totalRatings > 0 ? (bullishCount / totalRatings) * 100 : 0;
    const neutralPercentage = totalRatings > 0 ? (hold / totalRatings) * 100 : 0;
    const bearishPercentage = totalRatings > 0 ? (bearishCount / totalRatings) * 100 : 0;

    // Price target analysis
    const avgPriceTarget = metadata.avg_price_target || null;
    const priceTargetVsCurrent = metadata.price_target_vs_current || 0; // Percentage deviation

    // Recent analyst activity
    const upgradesLast30d = metadata.upgrades_last_30d || 0;
    const downgradesLast30d = metadata.downgrades_last_30d || 0;
    const activityNet = upgradesLast30d - downgradesLast30d;

    // EPS revision momentum
    const epsRevisionsUp = metadata.eps_revisions_up_last_30d || 0;
    const epsRevisionsDown = metadata.eps_revisions_down_last_30d || 0;
    const epsNetMomentum = epsRevisionsUp - epsRevisionsDown;

    return {
      sentimentScore,
      trendDirection,
      analystCount: metadata.analyst_count || 0,
      totalAnalysts: metadata.total_analysts || 0,
      // Rating distribution
      strongBuy, buy, hold, sell, strongSell,
      bullishPercentage,
      neutralPercentage,
      bearishPercentage,
      totalRatings,
      // Price target
      avgPriceTarget,
      priceTargetVsCurrent,
      // Activity
      upgradesLast30d,
      downgradesLast30d,
      activityNet,
      // EPS momentum
      epsRevisionsUp,
      epsRevisionsDown,
      epsNetMomentum,
    };
  }, [analystData]);

  // Format chart data for trend visualization
  const chartData = React.useMemo(() => {
    if (analystData.length === 0) return [];

    return analystData
      .slice(0, 90)
      .reverse()
      .map((item) => ({
        date: new Date(item.date).toLocaleDateString("en-US", { month: "short", day: "numeric" }),
        recommendationMean: item.sentiment_score ? (item.sentiment_score + 1) * 2.5 : 3,
      }));
  }, [analystData]);

  // Rating distribution pie chart data
  const ratingDistributionData = React.useMemo(() => {
    if (!analystMetrics) return [];
    return [
      { name: "Strong Buy", value: analystMetrics.strongBuy, color: theme.palette.success.main },
      { name: "Buy", value: analystMetrics.buy, color: theme.palette.success.light },
      { name: "Hold", value: analystMetrics.hold, color: theme.palette.warning.main },
      { name: "Sell", value: analystMetrics.sell, color: theme.palette.error.light },
      { name: "Strong Sell", value: analystMetrics.strongSell, color: theme.palette.error.main },
    ].filter(item => item.value > 0);
  }, [analystMetrics, theme]);

  if (analystData.length === 0) {
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
    return theme.palette.grey[600];
  };

  const getActivityColor = (net) => {
    if (net > 0) return theme.palette.success.main;
    if (net < 0) return theme.palette.error.main;
    return theme.palette.grey[600];
  };

  return (
    <>
      {/* Analyst Momentum Summary Card */}
      <Card variant="outlined">
        <CardContent>
          <Box display="flex" alignItems="center" gap={1} mb={3}>
            <TrendingUpRounded />
            <Typography variant="h6">Analyst Sentiment & Trends</Typography>
          </Box>

          <Grid container spacing={2}>
            {/* Sentiment Score */}
            <Grid item xs={12} sm={6} md={3}>
              <Box textAlign="center">
                <Typography variant="caption" color="textSecondary" display="block" mb={1}>
                  Sentiment Score
                </Typography>
                <Chip
                  label={`${analystMetrics?.sentimentScore?.toFixed(1) || 0}%`}
                  color={analystMetrics?.sentimentScore > 60 ? "success" : analystMetrics?.sentimentScore > 40 ? "warning" : "error"}
                  size="small"
                />
              </Box>
            </Grid>

            {/* Trend Direction */}
            <Grid item xs={12} sm={6} md={3}>
              <Box textAlign="center">
                <Typography variant="caption" color="textSecondary" display="block" mb={1}>
                  Trend
                </Typography>
                <Chip
                  label={analystMetrics?.trendDirection || "Stable"}
                  sx={{
                    bgcolor: alpha(getMomentumColor(analystMetrics?.trendDirection), 0.2),
                    color: getMomentumColor(analystMetrics?.trendDirection)
                  }}
                  size="small"
                />
              </Box>
            </Grid>

            {/* Analyst Coverage */}
            <Grid item xs={12} sm={6} md={3}>
              <Box textAlign="center">
                <Typography variant="caption" color="textSecondary" display="block" mb={1}>
                  Analyst Count
                </Typography>
                <Typography variant="body2" sx={{ fontWeight: "bold" }}>
                  {analystMetrics?.analystCount || 0}
                </Typography>
              </Box>
            </Grid>

            {/* Price Target Upside/Downside */}
            <Grid item xs={12} sm={6} md={3}>
              <Box textAlign="center">
                <Typography variant="caption" color="textSecondary" display="block" mb={1}>
                  Price Target
                </Typography>
                {analystMetrics?.priceTargetVsCurrent !== null ? (
                  <Chip
                    label={`${analystMetrics?.priceTargetVsCurrent > 0 ? "+" : ""}${analystMetrics?.priceTargetVsCurrent?.toFixed(1)}%`}
                    color={analystMetrics?.priceTargetVsCurrent > 0 ? "success" : analystMetrics?.priceTargetVsCurrent < 0 ? "error" : "default"}
                    size="small"
                  />
                ) : (
                  <Typography variant="body2" color="textSecondary">N/A</Typography>
                )}
              </Box>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      {/* Rating Distribution Card */}
      <Card variant="outlined" sx={{ mt: 2 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Rating Distribution
          </Typography>
          <Grid container spacing={2} alignItems="center">
            {/* Pie Chart */}
            <Grid item xs={12} sm={6}>
              {ratingDistributionData.length > 0 ? (
                <ResponsiveContainer width="100%" height={250}>
                  <PieChart>
                    <Pie
                      data={ratingDistributionData}
                      cx="50%"
                      cy="50%"
                      labelLine={false}
                      label={({ name, value, percent }) => `${name}: ${value} (${(percent * 100).toFixed(0)}%)`}
                      outerRadius={80}
                      fill="#8884d8"
                      dataKey="value"
                    >
                      {ratingDistributionData.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={entry.color} />
                      ))}
                    </Pie>
                    <RechartsTooltip
                      formatter={(value) => [`${value} analysts`, "Count"]}
                    />
                  </PieChart>
                </ResponsiveContainer>
              ) : (
                <Box display="flex" alignItems="center" justifyContent="center" height={250}>
                  <Typography color="textSecondary">No rating data available</Typography>
                </Box>
              )}
            </Grid>

            {/* Rating Details */}
            <Grid item xs={12} sm={6}>
              <Box display="flex" flexDirection="column" gap={1.5}>
                {analystMetrics?.strongBuy > 0 && (
                  <Box display="flex" justifyContent="space-between" alignItems="center">
                    <Typography variant="body2">Strong Buy:</Typography>
                    <Chip label={`${analystMetrics?.strongBuy}`} color="success" size="small" />
                  </Box>
                )}
                {analystMetrics?.buy > 0 && (
                  <Box display="flex" justifyContent="space-between" alignItems="center">
                    <Typography variant="body2">Buy:</Typography>
                    <Chip label={`${analystMetrics?.buy}`} color="success" size="small" variant="outlined" />
                  </Box>
                )}
                {analystMetrics?.hold > 0 && (
                  <Box display="flex" justifyContent="space-between" alignItems="center">
                    <Typography variant="body2">Hold:</Typography>
                    <Chip label={`${analystMetrics?.hold}`} size="small" variant="outlined" />
                  </Box>
                )}
                {analystMetrics?.sell > 0 && (
                  <Box display="flex" justifyContent="space-between" alignItems="center">
                    <Typography variant="body2">Sell:</Typography>
                    <Chip label={`${analystMetrics?.sell}`} color="error" size="small" variant="outlined" />
                  </Box>
                )}
                {analystMetrics?.strongSell > 0 && (
                  <Box display="flex" justifyContent="space-between" alignItems="center">
                    <Typography variant="body2">Strong Sell:</Typography>
                    <Chip label={`${analystMetrics?.strongSell}`} color="error" size="small" />
                  </Box>
                )}
                <Divider sx={{ my: 1 }} />
                <Box display="flex" justifyContent="space-between" alignItems="center">
                  <Typography variant="body2" sx={{ fontWeight: "bold" }}>Bullish:</Typography>
                  <Typography variant="body2" sx={{ fontWeight: "bold", color: theme.palette.success.main }}>
                    {analystMetrics?.bullishPercentage?.toFixed(0)}%
                  </Typography>
                </Box>
              </Box>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      {/* Analyst Activity Card */}
      <Card variant="outlined" sx={{ mt: 2 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Recent Analyst Activity (Last 30 Days)
          </Typography>
          <Grid container spacing={2}>
            {/* Upgrades vs Downgrades */}
            <Grid item xs={12} sm={6}>
              <Box>
                <Typography variant="subtitle2" color="textSecondary" mb={2}>
                  Rating Changes
                </Typography>
                <Box display="flex" gap={2} alignItems="center">
                  <Box flex={1}>
                    <Box display="flex" justifyContent="space-between" mb={0.5}>
                      <Typography variant="body2">Upgrades:</Typography>
                      <Chip
                        label={`${analystMetrics?.upgradesLast30d || 0}`}
                        color="success"
                        size="small"
                      />
                    </Box>
                    <Box display="flex" justifyContent="space-between">
                      <Typography variant="body2">Downgrades:</Typography>
                      <Chip
                        label={`${analystMetrics?.downgradesLast30d || 0}`}
                        color="error"
                        size="small"
                      />
                    </Box>
                  </Box>
                  <Box textAlign="center">
                    <Chip
                      label={`Net: ${analystMetrics?.activityNet > 0 ? "+" : ""}${analystMetrics?.activityNet || 0}`}
                      sx={{
                        bgcolor: alpha(getActivityColor(analystMetrics?.activityNet), 0.2),
                        color: getActivityColor(analystMetrics?.activityNet),
                        fontWeight: "bold"
                      }}
                    />
                  </Box>
                </Box>
              </Box>
            </Grid>

            {/* EPS Revisions */}
            <Grid item xs={12} sm={6}>
              <Box>
                <Typography variant="subtitle2" color="textSecondary" mb={2}>
                  EPS Revisions
                </Typography>
                <Box display="flex" gap={2} alignItems="center">
                  <Box flex={1}>
                    <Box display="flex" justifyContent="space-between" mb={0.5}>
                      <Typography variant="body2">Revisions Up:</Typography>
                      <Chip
                        label={`${analystMetrics?.epsRevisionsUp || 0}`}
                        color="success"
                        size="small"
                      />
                    </Box>
                    <Box display="flex" justifyContent="space-between">
                      <Typography variant="body2">Revisions Down:</Typography>
                      <Chip
                        label={`${analystMetrics?.epsRevisionsDown || 0}`}
                        color="error"
                        size="small"
                      />
                    </Box>
                  </Box>
                  <Box textAlign="center">
                    <Chip
                      label={`Net: ${analystMetrics?.epsNetMomentum > 0 ? "+" : ""}${analystMetrics?.epsNetMomentum || 0}`}
                      sx={{
                        bgcolor: alpha(getActivityColor(analystMetrics?.epsNetMomentum), 0.2),
                        color: getActivityColor(analystMetrics?.epsNetMomentum),
                        fontWeight: "bold"
                      }}
                    />
                  </Box>
                </Box>
              </Box>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      {/* 90-Day Trend Chart */}
      {chartData && chartData.length > 0 && (
        <Card variant="outlined" sx={{ mt: 2 }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              90-Day Rating Trend
            </Typography>
            <ResponsiveContainer width="100%" height={280}>
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke={theme.palette.divider} />
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 12 }}
                  stroke={theme.palette.text.secondary}
                />
                <YAxis
                  domain={[1, 5]}
                  label={{
                    value: "Average Rating",
                    angle: -90,
                    position: "insideLeft",
                    style: { fontSize: 12 }
                  }}
                  stroke={theme.palette.text.secondary}
                />
                <RechartsTooltip
                  contentStyle={{
                    backgroundColor: theme.palette.background.paper,
                    border: `1px solid ${theme.palette.divider}`,
                    borderRadius: 4
                  }}
                  formatter={(value) => {
                    const ratingLabels = {
                      1: "Strong Buy",
                      2: "Buy",
                      3: "Hold",
                      4: "Sell",
                      5: "Strong Sell"
                    };
                    return [ratingLabels[Math.round(value)] || value.toFixed(2), "Average Rating"];
                  }}
                />
                <Legend wrapperStyle={{ paddingTop: 20 }} />
                <Line
                  type="monotone"
                  dataKey="recommendationMean"
                  stroke={theme.palette.primary.main}
                  strokeWidth={2}
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
          Individual stock analyst sentiment analysis and ratings trends
        </Typography>
      </Box>

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
                          <AnalystTrendCard symbol={stock.symbol} allData={stock.analyst} />
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

    </Container>
  );
}

export default Sentiment;
