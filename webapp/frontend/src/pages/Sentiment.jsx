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

// Analyst Trend Card Component - Metrics-focused display
const AnalystTrendCard = ({ symbol }) => {
  const theme = useTheme();
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState(null);
  const [data, setData] = React.useState(null);

  // Fetch analyst insights from the correct endpoint
  React.useEffect(() => {
    const fetchAnalystInsights = async () => {
      try {
        setLoading(true);
        const response = await fetch(`${API_BASE}/api/sentiment/analyst/insights/${symbol}`);
        if (!response.ok) throw new Error("Failed to fetch analyst insights");
        const result = await response.json();
        setData(result);
      } catch (err) {
        setError(err.message);
        setData(null);
      } finally {
        setLoading(false);
      }
    };

    if (symbol) {
      fetchAnalystInsights();
    }
  }, [symbol]);

  // Use metrics directly from the endpoint response
  const metrics = data?.metrics || null;
  const momentum = data?.momentum || null;

  if (loading) {
    return (
      <Card variant="outlined">
        <CardContent>
          <Box display="flex" alignItems="center" gap={1} mb={2}>
            <TrendingUpRounded />
            <Typography variant="h6">Analyst Sentiment</Typography>
          </Box>
          <Typography variant="body2" color="textSecondary">Loading analyst data...</Typography>
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
            <Typography variant="h6">Analyst Sentiment</Typography>
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
            <Grid item xs={12} sm={6} md={3}>
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
            <Grid item xs={12} sm={6} md={3}>
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
            <Grid item xs={12} sm={6} md={3}>
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
            <Grid item xs={12} sm={6} md={3}>
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
                <Grid item xs={12} sm={6} md={3}>
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
                  <Grid item xs={12} sm={6} md={3}>
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

        {/* No data message */}
        {!metrics && !momentum && (
          <Typography variant="body2" color="textSecondary">
            No analyst sentiment data available
          </Typography>
        )}
      </CardContent>
    </Card>
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

    // Group by source type
    const source = (item.source || "").toLowerCase();
    if (source.includes("news") || source.includes("article")) {
      acc[symbol].news.push(item);
    } else if (source.includes("reddit") || source.includes("social") || source.includes("twitter") || source.includes("technical")) {
      acc[symbol].social.push(item);
    } else if (source.includes("analyst") || source.includes("rating")) {
      acc[symbol].analyst.push(item);
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

      {/* Section 1: Comparative View Charts - AT THE TOP */}
      <Box sx={{ mb: 4 }}>
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Market Sentiment Overview
            </Typography>
            <Grid container spacing={3}>
              {/* Left: Sentiment Statistics Cards */}
              <Grid item xs={12} md={6}>
                <Grid container spacing={2}>
                  {/* Bullish Count */}
                  <Grid item xs={6} sm={6}>
                    <Box sx={{ p: 2, backgroundColor: '#e8f5e9', borderRadius: 1, textAlign: 'center' }}>
                      <Typography variant="h4" sx={{ color: '#2e7d32', fontWeight: 'bold' }}>
                        {stocksList.filter(s => s.compositeSentiment?.sentiment === 'bullish').length}
                      </Typography>
                      <Typography variant="body2" color="textSecondary">
                        Bullish Stocks
                      </Typography>
                    </Box>
                  </Grid>
                  {/* Neutral Count */}
                  <Grid item xs={6} sm={6}>
                    <Box sx={{ p: 2, backgroundColor: '#f5f5f5', borderRadius: 1, textAlign: 'center' }}>
                      <Typography variant="h4" sx={{ color: '#616161', fontWeight: 'bold' }}>
                        {stocksList.filter(s => s.compositeSentiment?.sentiment === 'neutral').length}
                      </Typography>
                      <Typography variant="body2" color="textSecondary">
                        Neutral Stocks
                      </Typography>
                    </Box>
                  </Grid>
                  {/* Bearish Count */}
                  <Grid item xs={6} sm={6}>
                    <Box sx={{ p: 2, backgroundColor: '#ffebee', borderRadius: 1, textAlign: 'center' }}>
                      <Typography variant="h4" sx={{ color: '#c62828', fontWeight: 'bold' }}>
                        {stocksList.filter(s => s.compositeSentiment?.sentiment === 'bearish').length}
                      </Typography>
                      <Typography variant="body2" color="textSecondary">
                        Bearish Stocks
                      </Typography>
                    </Box>
                  </Grid>
                  {/* Market Average */}
                  <Grid item xs={6} sm={6}>
                    <Box sx={{ p: 2, backgroundColor: '#e3f2fd', borderRadius: 1, textAlign: 'center' }}>
                      <Typography variant="h4" sx={{ color: '#1565c0', fontWeight: 'bold' }}>
                        {stocksList.length > 0 ? (stocksList.reduce((sum, s) => sum + (s.compositeScore || 0), 0) / stocksList.length).toFixed(2) : 'N/A'}
                      </Typography>
                      <Typography variant="body2" color="textSecondary">
                        Avg Sentiment
                      </Typography>
                    </Box>
                  </Grid>
                </Grid>
              </Grid>

              {/* Right: Source-based Sentiment Pie Chart */}
              <Grid item xs={12} md={6}>
                <Typography variant="body2" color="textSecondary" paragraph>
                  Sentiment Sources Distribution:
                </Typography>
                {stocksList.length > 0 && (
                  <ResponsiveContainer width="100%" height={250}>
                    <PieChart>
                      <Pie
                        data={[
                          { name: 'News', value: stocksList.filter(s => s.latestNews?.sentiment_score).length },
                          { name: 'Analyst', value: stocksList.filter(s => s.latestAnalyst?.sentiment_score).length },
                          { name: 'Social', value: stocksList.filter(s => s.latestSocial?.sentiment_score).length },
                        ]}
                        cx="50%"
                        cy="50%"
                        labelLine={false}
                        label={({ name, value, percent }) => `${name}: ${value}`}
                        outerRadius={70}
                        fill="#8884d8"
                        dataKey="value"
                      >
                        {['#0088FE', '#00C49F', '#FFBB28'].map((fill, idx) => (
                          <Cell key={`cell-${idx}`} fill={fill} />
                        ))}
                      </Pie>
                      <RechartsTooltip />
                    </PieChart>
                  </ResponsiveContainer>
                )}
              </Grid>
            </Grid>
          </CardContent>
        </Card>
      </Box>

      {/* Section 2: Stock Details - Middle Section */}
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

            {/* Analyst Insights by Symbol - Detailed Metrics */}
            <Divider sx={{ my: 4 }} />
            <Box sx={{ mb: 3 }}>
              <Typography variant="h6" sx={{ display: "flex", alignItems: "center", gap: 1, mb: 2 }}>
                <TrendingUpRounded />
                Detailed Analyst Metrics by Stock
              </Typography>
              <Typography variant="body2" color="textSecondary" sx={{ mb: 3 }}>
                Browse detailed analyst sentiment metrics, price targets, and coverage statistics for each stock
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
                {filteredAndSortedStocks.slice(0, 10).map((stock) => (
                  <Accordion key={stock.symbol} sx={{ mb: 2 }}>
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
                      <AnalystTrendCard symbol={stock.symbol} />
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
