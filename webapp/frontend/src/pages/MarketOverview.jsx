import { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Alert,
  Box,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Grid,
  LinearProgress,
  Paper,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tabs,
  Typography,
  Zoom,
  alpha,
  useTheme,
} from "@mui/material";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  ResponsiveContainer,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  Legend,
  Tooltip,
} from "recharts";
import {
  TrendingUp,
  TrendingDown,
  TrendingFlat,
  Timeline,
  CalendarToday,
  Equalizer,
} from "@mui/icons-material";

import {
  getMarketOverview,
  getMarketSentimentHistory,
  getMarketBreadth,
  getSeasonalityData,
  getDistributionDays,
} from "../services/api";
import {
  formatCurrency,
  formatPercentage,
  formatPercentageChange,
  getChangeColor,
} from "../utils/formatters";
import { createComponentLogger } from "../utils/errorLogger";

// Create logger instance for this component
const _logger = createComponentLogger("MarketOverview");

const _CHART_COLORS = [
  "#0088FE",
  "#00C49F",
  "#FFBB28",
  "#FF8042",
  "#8884d8",
  "#82ca9d",
  "#ffc658",
  "#ff7c7c",
];

// Advanced color schemes for different visualizations
const _colorSchemes = {
  primary: [
    "#6366f1",
    "#8b5cf6",
    "#ec4899",
    "#f43f5e",
    "#f59e0b",
    "#10b981",
    "#06b6d4",
    "#3b82f6",
  ],
  gradient: [
    { start: "#667eea", end: "#764ba2" },
    { start: "#f093fb", end: "#f5576c" },
    { start: "#4facfe", end: "#00f2fe" },
    { start: "#fa709a", end: "#fee140" },
    { start: "#30cfd0", end: "#330867" },
    { start: "#a8edea", end: "#fed6e3" },
    { start: "#ff9a9e", end: "#fecfef" },
    { start: "#fbc2eb", end: "#a6c1ee" },
  ],
  sentiment: {
    bullish: "#10b981",
    bearish: "#ef4444",
    neutral: "#6b7280",
    extreme: "#dc2626",
    moderate: "#f59e0b",
  },
  performance: {
    positive: "#10b981",
    negative: "#ef4444",
    neutral: "#6b7280",
    strong: "#059669",
    weak: "#dc2626",
  },
};

// Enhanced custom components
const AnimatedCard = ({ children, delay = 0, ...props }) => {
  const theme = useTheme();
  const zoomTimeout = 300 + delay * 100;
  return (
    <Zoom in={true} timeout={zoomTimeout}>
      <Card
        {...props}
        sx={{
          background: theme.palette.background.paper,
          backdropFilter: "blur(10px)",
          border: `1px solid ${alpha(theme.palette.primary.main, 0.1)}`,
          transition: "all 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
          "&:hover": {
            transform: "translateY(-4px)",
            boxShadow: theme.shadows[8],
            border: `1px solid ${alpha(theme.palette.primary.main, 0.2)}`,
          },
          ...props.sx,
        }}
      >
        {children}
      </Card>
    </Zoom>
  );
};

const GradientCard = ({ children, gradient, ...props }) => {
  const theme = useTheme();
  return (
    <Card
      {...props}
      sx={{
        background:
          gradient ||
          `linear-gradient(135deg, ${theme.palette.primary.main} 0%, ${theme.palette.secondary.main} 100%)`,
        color: "white",
        position: "relative",
        overflow: "hidden",
        "&::before": {
          content: '""',
          position: "absolute",
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: "rgba(255,255,255,0.1)",
          transform: "translateX(-100%)",
          transition: "transform 0.6s ease",
        },
        "&:hover::before": {
          transform: "translateX(0)",
        },
        ...props.sx,
      }}
    >
      {children}
    </Card>
  );
};

const _MetricCard = ({
  title,
  value,
  subtitle,
  icon,
  trend,
  color: _color = "primary",
  gradient,
}) => {
  const _theme = useTheme();
  const isPositive = trend > 0;

  return (
    <GradientCard gradient={gradient}>
      <CardContent>
        <Box
          sx={{
            display: "flex",
            alignItems: "flex-start",
            justifyContent: "space-between",
          }}
        >
          <Box sx={{ flex: 1 }}>
            <Typography
              variant="subtitle2"
              sx={{ opacity: 0.9, fontWeight: 500 }}
            >
              {title}
            </Typography>
            <Typography variant="h3" sx={{ my: 1, fontWeight: 700 }}>
              {value}
            </Typography>
            {subtitle && (
              <Typography variant="body2" sx={{ opacity: 0.8 }}>
                {subtitle}
              </Typography>
            )}
            {trend !== undefined && (
              <Box sx={{ display: "flex", alignItems: "center", mt: 1 }}>
                {isPositive ? (
                  <TrendingUp fontSize="small" />
                ) : (
                  <TrendingDown fontSize="small" />
                )}
                <Typography variant="body2" sx={{ ml: 0.5, fontWeight: 600 }}>
                  {Math.abs(trend)}%
                </Typography>
              </Box>
            )}
          </Box>
          {icon && (
            <Box
              sx={{
                width: 48,
                height: 48,
                borderRadius: "50%",
                bgcolor: "rgba(255,255,255,0.2)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: "1.5rem",
              }}
            >
              {icon}
            </Box>
          )}
        </Box>
      </CardContent>
    </GradientCard>
  );
};

const TabPanel = ({ children, value, index, ...other }) => (
  <div
    role="tabpanel"
    hidden={value !== index}
    id={`market-tabpanel-${index}`}
    aria-labelledby={`market-tab-${index}`}
    {...other}
  >
    {value === index && <Box sx={{ pt: 3 }}>{children}</Box>}
  </div>
);

const _DataTable = ({ title, columns, data }) => (
  <Card>
    <CardContent>
      <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
        {title}
      </Typography>
      <TableContainer component={Paper} elevation={0}>
        <Table size="small">
          <TableHead>
            <TableRow sx={{ backgroundColor: "grey.50" }}>
              {(columns || []).map((col) => (
                <TableCell key={col.key} sx={{ fontWeight: 600 }}>
                  {col.label}
                </TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {data?.slice(0, 10).map((item, index) => (
              <TableRow key={item.ticker || index} hover>
                {(columns || []).map((col) => (
                  <TableCell key={col.key}>
                    {col.render
                      ? col.render(item[col.key], item)
                      : item[col.key] || "N/A"}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </CardContent>
  </Card>
);

// Create component-specific logger

// Simplified API functions that work directly with your data
const fetchMarketOverview = async () => {
  try {
    const response = await getMarketOverview();
    return response;
  } catch (error) {
    _logger.error("Market overview error:", error.message || error.toString());
    throw error;
  }
};

const fetchSentimentHistory = async (days = 30) => {
  try {
    const response = await getMarketSentimentHistory(days);
    return response;
  } catch (error) {
    _logger.error(
      "Sentiment history error:",
      error.message || error.toString()
    );
    throw error;
  }
};

const fetchMarketBreadth = async () => {
  try {
    console.log("📏 Fetching market breadth...");
    const response = await getMarketBreadth();
    console.log("📏 Market breadth response:", response);
    return response;
  } catch (error) {
    _logger.error("Market breadth error:", error.message || error.toString());
    throw error;
  }
};

const fetchDistributionDays = async () => {
  try {
    console.log("📊 Fetching distribution days...");
    const response = await getDistributionDays();
    console.log("📊 Distribution days response:", response);
    return response;
  } catch (error) {
    _logger.error("Distribution days error:", error.message || error.toString());
    throw error;
  }
};

const fetchSeasonalityData = async () => {
  try {
    console.log("📅 Fetching seasonality data...");
    const response = await getSeasonalityData();
    console.log("📅 Seasonality response:", response);
    return response;
  } catch (error) {
    _logger.error("Seasonality error:", error.message || error.toString());
    throw error;
  }
};

function MarketOverview() {
  const [tabValue, setTabValue] = useState(0);
  const [tabsReady, setTabsReady] = useState(false);
  const [_viewMode, _setViewMode] = useState("cards");
  const [_selectedSector, _setSelectedSector] = useState("all");
  const theme = useTheme();

  // Fix MUI Tabs validation error by ensuring tabs are ready before rendering
  useEffect(() => {
    const timer = setTimeout(() => setTabsReady(true), 100);
    return () => clearTimeout(timer);
  }, []);

  const {
    data: marketData,
    isLoading: marketLoading,
    error: marketError,
  } = useQuery({
    queryKey: ["market-overview"],
    queryFn: fetchMarketOverview,
    refetchInterval: 60000,
    retry: 2,
    staleTime: 30000,
  });

  const { data: sentimentData, isLoading: sentimentLoading } = useQuery({
    queryKey: ["market-sentiment-history"],
    queryFn: () => fetchSentimentHistory(30),
    enabled: tabValue === 0,
    staleTime: 30000,
  });

  const { data: breadthData, isLoading: breadthLoading } = useQuery({
    queryKey: ["market-breadth"],
    queryFn: fetchMarketBreadth,
    enabled: tabValue === 1,
    staleTime: 30000,
  });

  const { data: distributionDaysData, isLoading: distributionDaysLoading } = useQuery({
    queryKey: ["distribution-days"],
    queryFn: fetchDistributionDays,
    staleTime: 30000,
  });

  const { data: seasonalityData, isLoading: seasonalityLoading } = useQuery({
    queryKey: ["seasonality-data"],
    queryFn: fetchSeasonalityData,
    enabled: tabValue === 2,
    staleTime: 30000,
  });

  const handleTabChange = (event, newValue) => {
    setTabValue(newValue);
  };
  if (marketError) {
    return (
      <Box>
        <Typography variant="h4" sx={{ mb: 3, fontWeight: 600 }}>
          Market Overview
        </Typography>
        <Alert severity="error" sx={{ mb: 3 }}>
          Failed to load market data. Please check your data sources and try
          again.
          <br />
          <small>
            Technical details: {marketError?.message || "Unknown error"}
          </small>
          <br />
          <small>
            Debug endpoint:{" "}
            <code>{window.__CONFIG__?.API_URL}/market/debug</code>
          </small>
        </Alert>
      </Box>
    );
  }

  if (marketLoading || !marketData) {
    return (
      <Box>
        <Typography variant="h4" sx={{ mb: 3, fontWeight: 600 }}>
          Market Overview
        </Typography>
        <CircularProgress />
      </Box>
    );
  }

  // Extract data from API responses - REAL DATA ONLY, NO FALLBACKS
  const sentimentIndicators = marketData?.data?.sentiment_indicators || {};
  const marketBreadth = marketData?.data?.market_breadth || {};
  const marketCap = marketData?.data?.market_cap || {};
  const indices = marketData?.data?.indices || [];
  const topMovers = marketData?.data?.movers || { gainers: [], losers: [] };

  // Real API response structure from loaders
  const breadthInfo = breadthData?.data || {};
  const distributionDays = distributionDaysData?.data || {};
  const sentimentHistory = sentimentData?.data || {};
  console.log("sentimentHistory", sentimentHistory);


  // Prepare sentiment chart data for all indicators
  const fearGreedHistory = sentimentHistory.fear_greed_history || [];
  const naaimHistory = sentimentHistory.naaim_history || [];
  const aaiiHistory = sentimentHistory.aaii_history || [];
  console.log("aaiiHistory", aaiiHistory);

  // Merge by date for multi-line chart (assume all have 'date' or 'timestamp')
  const dateMap = {};
  fearGreedHistory.forEach((item) => {
    const date = item.date || item.timestamp;
    if (!dateMap[date]) dateMap[date] = { date };
    dateMap[date].fear_greed = item.value;
    dateMap[date].fear_greed_text = item.value_text;
  });
  naaimHistory.forEach((item) => {
    const date = item.date || item.timestamp;
    if (!dateMap[date]) dateMap[date] = { date };
    dateMap[date].naaim = item.mean_exposure || item.average;
  });
  aaiiHistory.forEach((item) => {
    const date = item.date || item.timestamp;
    if (!dateMap[date]) dateMap[date] = { date };
    dateMap[date].aaii_bullish = item.bullish;
    dateMap[date].aaii_bearish = item.bearish;
    dateMap[date].aaii_neutral = item.neutral;
  });
  const sentimentChartData = Object.values(dateMap)
    .sort((a, b) => new Date(a.date) - new Date(b.date))
    .slice(-30);
  console.log("sentimentChartData", sentimentChartData);

  // Latest stats for summary cards
  const latestFG = fearGreedHistory[0] || {};
  const latestNAAIM = naaimHistory[0] || {};
  // Get current AAII from sentiment indicators instead of history
  const latestAAII = sentimentIndicators?.aaii || {};

  // Helper to calculate sentiment signal from AAII data
  const getSentimentSignal = (bullish, bearish) => {
    const diff = bullish - bearish;
    if (diff > 10) return { label: "Bullish", color: "success", icon: <TrendingUp /> };
    if (diff < -10) return { label: "Bearish", color: "error", icon: <TrendingDown /> };
    return { label: "Neutral", color: "warning", icon: <TrendingFlat /> };
  };

  const aaiiSignal = getSentimentSignal(latestAAII.bullish || 0, latestAAII.bearish || 0);

  // --- Sentiment History Tab ---
  const SentimentHistoryPanel = () => (
    <Box>
      <Grid container spacing={3}>
        {/* AAII Market Sentiment Summary Card */}
        <Grid item xs={12} md={4}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" justifyContent="space-between" mb={2}>
                <Typography variant="h6">AAII Market Sentiment</Typography>
                <Chip label={aaiiSignal.label} color={aaiiSignal.color} icon={aaiiSignal.icon} />
              </Box>
              <Box>
                <Box mb={2}>
                  <Box display="flex" justifyContent="space-between" mb={1}>
                    <Typography variant="body2" color="textSecondary">Bullish</Typography>
                    <Typography variant="body2" fontWeight="bold" color="success.main">
                      {latestAAII.bullish ?? "N/A"}%
                    </Typography>
                  </Box>
                  <LinearProgress
                    variant="determinate"
                    value={latestAAII.bullish || 0}
                    color="success"
                    sx={{ height: 8, borderRadius: 1 }}
                  />
                </Box>
                <Box mb={2}>
                  <Box display="flex" justifyContent="space-between" mb={1}>
                    <Typography variant="body2" color="textSecondary">Neutral</Typography>
                    <Typography variant="body2" fontWeight="bold" color="warning.main">
                      {latestAAII.neutral ?? "N/A"}%
                    </Typography>
                  </Box>
                  <LinearProgress
                    variant="determinate"
                    value={latestAAII.neutral || 0}
                    color="warning"
                    sx={{ height: 8, borderRadius: 1 }}
                  />
                </Box>
                <Box>
                  <Box display="flex" justifyContent="space-between" mb={1}>
                    <Typography variant="body2" color="textSecondary">Bearish</Typography>
                    <Typography variant="body2" fontWeight="bold" color="error.main">
                      {latestAAII.bearish ?? "N/A"}%
                    </Typography>
                  </Box>
                  <LinearProgress
                    variant="determinate"
                    value={latestAAII.bearish || 0}
                    color="error"
                    sx={{ height: 8, borderRadius: 1 }}
                  />
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* AAII Sentiment Trend Chart */}
        <Grid item xs={12} md={8}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                AAII Market Sentiment Trend
              </Typography>
              <ResponsiveContainer width="100%" height={250}>
                <LineChart data={sentimentChartData.slice(0, 30).reverse()}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="date" tick={{ fontSize: 12 }} />
                  <YAxis domain={[0, 100]} />
                  <Tooltip formatter={(value, name) => [`${value}%`, name]} />
                  <Legend />
                  <Line type="monotone" dataKey="aaii_bullish" name="Bullish %" stroke="#4caf50" strokeWidth={2} />
                  <Line type="monotone" dataKey="aaii_neutral" name="Neutral %" stroke="#ff9800" strokeWidth={2} />
                  <Line type="monotone" dataKey="aaii_bearish" name="Bearish %" stroke="#f44336" strokeWidth={2} />
                </LineChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </Grid>

        {/* Fear & Greed Chart */}
        <Grid item xs={12}>
          <Card>
            <CardContent>
              <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                Fear & Greed Index History
              </Typography>
              <Box sx={{ mb: 2 }}>
                <Typography variant="body2" color="text.secondary">
                  Current: <strong>{latestFG.value ?? "N/A"}</strong> - {latestFG.value_text || ""}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  Measures market sentiment (0=Extreme Fear, 100=Extreme Greed)
                </Typography>
              </Box>
              <ResponsiveContainer width="100%" height={250}>
                <LineChart
                  data={sentimentChartData}
                  margin={{ top: 10, right: 30, left: 0, bottom: 0 }}
                >
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="date" tick={{ fontSize: 12 }} />
                  <YAxis
                    domain={[0, 100]}
                    label={{
                      value: "Fear & Greed Index",
                      angle: -90,
                      position: "insideLeft",
                      fontSize: 12,
                    }}
                  />
                  <Tooltip formatter={(value) => [`${value}`, "Fear & Greed"]} />
                  <Line
                    type="monotone"
                    dataKey="fear_greed"
                    name="Fear & Greed"
                    stroke="#FF8042"
                    strokeWidth={2}
                    dot={{ r: 3 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </Grid>

        {/* NAAIM Chart */}
        <Grid item xs={12}>
          <Card>
            <CardContent>
              <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                NAAIM Exposure History
              </Typography>
              <Box sx={{ mb: 2 }}>
                <Typography variant="body2" color="text.secondary">
                  Current: <strong>{latestNAAIM.mean_exposure ?? latestNAAIM.average ?? "N/A"}%</strong>
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  Active manager equity exposure (0=fully out, 100=fully in)
                </Typography>
              </Box>
              <ResponsiveContainer width="100%" height={250}>
                <LineChart
                  data={sentimentChartData}
                  margin={{ top: 10, right: 30, left: 0, bottom: 0 }}
                >
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="date" tick={{ fontSize: 12 }} />
                  <YAxis
                    domain={[-100, 100]}
                    label={{
                      value: "NAAIM Exposure %",
                      angle: -90,
                      position: "insideLeft",
                      fontSize: 12,
                    }}
                  />
                  <Tooltip formatter={(value) => [`${value}%`, "NAAIM Exposure"]} />
                  <Line
                    type="monotone"
                    dataKey="naaim"
                    name="NAAIM Exposure"
                    stroke="#0088FE"
                    strokeWidth={2}
                    dot={{ r: 3 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );

  return (
    <Box sx={{ minHeight: "100vh", bgcolor: "background.default" }} data-testid="market-overview-page">
      {/* Sentiment Indicators - Above Header */}
      <Grid container spacing={3} sx={{ mb: 3 }}>
        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                Fear & Greed Index
              </Typography>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                <Typography variant="body2">Current Value:</Typography>
                <Typography variant="body2" fontWeight="600">
                  {latestFG.value ?? "N/A"}
                </Typography>
              </Box>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                <Typography variant="body2">Classification:</Typography>
                <Typography variant="body2" fontWeight="600">
                  {latestFG.value_text || latestFG.classification || "N/A"}
                </Typography>
              </Box>
              <Typography variant="caption" color="text.secondary">
                Scale: 0 (Extreme Fear) - 100 (Extreme Greed)
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                NAAIM Exposure
              </Typography>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                <Typography variant="body2">Mean Exposure:</Typography>
                <Typography variant="body2" fontWeight="600">
                  {latestNAAIM.mean_exposure ?? latestNAAIM.average ?? "N/A"}
                </Typography>
              </Box>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                <Typography variant="body2">Bearish Exposure:</Typography>
                <Typography variant="body2" fontWeight="600">
                  {latestNAAIM.bearish_exposure ?? "N/A"}
                </Typography>
              </Box>
              <Typography variant="caption" color="text.secondary">
                Active manager equity exposure (0=out, 100=in)
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                AAII Sentiment
              </Typography>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                <Typography variant="body2">Bullish:</Typography>
                <Typography variant="body2" fontWeight="600">
                  {latestAAII.bullish ?? "N/A"}%
                </Typography>
              </Box>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                <Typography variant="body2">Neutral:</Typography>
                <Typography variant="body2" fontWeight="600">
                  {latestAAII.neutral ?? "N/A"}%
                </Typography>
              </Box>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                <Typography variant="body2">Bearish:</Typography>
                <Typography variant="body2" fontWeight="600">
                  {latestAAII.bearish ?? "N/A"}%
                </Typography>
              </Box>
              <Typography variant="caption" color="text.secondary">
                Retail investor sentiment survey
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Enhanced Header Section */}
      <Box sx={{ mb: 4 }}>
        <Grid container spacing={2} alignItems="center">
          <Grid item xs={12} md={6}>
            <Typography
              variant="h3"
              component="h1"
              gutterBottom
              sx={{
                fontWeight: 800,
                background: `linear-gradient(135deg, ${theme.palette.primary.main} 0%, ${theme.palette.secondary.main} 100%)`,
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
                mb: 1,
              }}
            >
              Market Overview
            </Typography>
            <Typography variant="subtitle1" color="text.secondary">
              Real-time market analysis, sentiment indicators, and
              institutional-grade research insights
            </Typography>
          </Grid>
        </Grid>
        {marketLoading && (
          <Box sx={{ mt: 2 }}>
            <LinearProgress
              sx={{
                borderRadius: 1,
                height: 6,
                bgcolor: alpha(theme.palette.primary.main, 0.1),
                "& .MuiLinearProgress-bar": {
                  borderRadius: 1,
                  background: `linear-gradient(90deg, ${theme.palette.primary.main} 0%, ${theme.palette.secondary.main} 100%)`,
                },
              }}
            />
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ mt: 1, display: "block" }}
            >
              Fetching real-time market data...
            </Typography>
          </Box>
        )}
      </Box>

      {/* Major Indices Display */}
      {indices && indices.length > 0 && (
        <Grid container spacing={3} sx={{ mb: 4 }}>
          {indices.map((index, idx) => (
            <Grid item xs={12} md={4} key={index.symbol}>
              <AnimatedCard delay={idx}>
                <Card>
                  <CardContent>
                    <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <Box>
                        <Typography variant="h6" sx={{ fontWeight: 600 }}>
                          {index.name}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          {index.symbol}
                        </Typography>
                      </Box>
                      <Box sx={{ textAlign: "right" }}>
                        <Typography variant="h5" sx={{ fontWeight: 600 }}>
                          {formatCurrency(index.price, 2)}
                        </Typography>
                        <Typography
                          variant="body1"
                          sx={{
                            color: getChangeColor(index.changePercent),
                            fontWeight: 600,
                          }}
                          className={index.changePercent > 0 ? "text-green-600" : "text-red-600"}
                        >
                          {formatPercentageChange(index.changePercent)}
                        </Typography>
                      </Box>
                    </Box>
                  </CardContent>
                </Card>
              </AnimatedCard>
            </Grid>
          ))}
        </Grid>
      )}


      {/* Top Movers Section */}
      {(topMovers.gainers?.length > 0 || topMovers.losers?.length > 0) && (
        <Grid container spacing={3} sx={{ mb: 4 }}>
          <Grid item xs={12}>
            <Typography variant="h5" sx={{ mb: 2, fontWeight: 600 }}>
              Top Movers
            </Typography>
          </Grid>
          <Grid item xs={12} md={6}>
            <Card>
              <CardContent>
                <Typography variant="h6" sx={{ mb: 2, color: "success.main", fontWeight: 600 }}>
                  Top Gainers
                </Typography>
                {topMovers.gainers?.slice(0, 5).map((mover, idx) => (
                  <Box 
                    key={mover.symbol} 
                    data-testid="mover-item"
                    sx={{ 
                      display: "flex", 
                      justifyContent: "space-between", 
                      alignItems: "center",
                      py: 1,
                      borderBottom: idx < topMovers.gainers.slice(0, 5).length - 1 ? '1px solid' : 'none',
                      borderColor: 'divider'
                    }}
                  >
                    <Box>
                      <Typography variant="body1" sx={{ fontWeight: 600 }}>
                        {mover.symbol}
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        {formatCurrency(mover.price)}
                      </Typography>
                    </Box>
                    <Box sx={{ textAlign: "right" }}>
                      <Typography variant="body1" sx={{ color: "success.main", fontWeight: 600 }}>
                        +{Math.abs(mover.change).toFixed(1)}
                      </Typography>
                      <Typography variant="body2" sx={{ color: "success.main" }}>
                        +{mover.changePercent.toFixed(1)}%
                      </Typography>
                    </Box>
                  </Box>
                ))}
              </CardContent>
            </Card>
          </Grid>
          <Grid item xs={12} md={6}>
            <Card>
              <CardContent>
                <Typography variant="h6" sx={{ mb: 2, color: "error.main", fontWeight: 600 }}>
                  Top Losers
                </Typography>
                {topMovers.losers?.slice(0, 5).map((mover, idx) => (
                  <Box 
                    key={mover.symbol} 
                    data-testid="mover-item"
                    sx={{ 
                      display: "flex", 
                      justifyContent: "space-between", 
                      alignItems: "center",
                      py: 1,
                      borderBottom: idx < topMovers.losers.slice(0, 5).length - 1 ? '1px solid' : 'none',
                      borderColor: 'divider'
                    }}
                  >
                    <Box>
                      <Typography variant="body1" sx={{ fontWeight: 600 }}>
                        {mover.symbol}
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        {formatCurrency(mover.price)}
                      </Typography>
                    </Box>
                    <Box sx={{ textAlign: "right" }}>
                      <Typography variant="body1" sx={{ color: "error.main", fontWeight: 600 }}>
                        {mover.change.toFixed(1)}
                      </Typography>
                      <Typography variant="body2" sx={{ color: "error.main" }}>
                        {mover.changePercent.toFixed(1)}%
                      </Typography>
                    </Box>
                  </Box>
                ))}
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      )}

      {/* Enhanced Market Breadth Section */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={12} md={6}>
          <AnimatedCard delay={3}>
            <CardContent>
              <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                Market Breadth
              </Typography>
              <Grid container spacing={2}>
                <Grid item xs={6}>
                  <Box
                    sx={{
                      textAlign: "center",
                      p: 2,
                      backgroundColor: "success.light",
                      borderRadius: 1,
                    }}
                  >
                    <Typography variant="h4" color="success.contrastText">
                      {marketBreadth.advancing !== undefined &&
                      marketBreadth.advancing !== null
                        ? parseInt(marketBreadth.advancing).toLocaleString()
                        : "N/A"}
                    </Typography>
                    <Typography variant="body2" color="success.contrastText">
                      Advancing
                    </Typography>
                  </Box>
                </Grid>
                <Grid item xs={6}>
                  <Box
                    sx={{
                      textAlign: "center",
                      p: 2,
                      backgroundColor: "error.light",
                      borderRadius: 1,
                    }}
                  >
                    <Typography variant="h4" color="error.contrastText">
                      {marketBreadth.declining !== undefined &&
                      marketBreadth.declining !== null
                        ? parseInt(marketBreadth.declining).toLocaleString()
                        : "N/A"}
                    </Typography>
                    <Typography variant="body2" color="error.contrastText">
                      Declining
                    </Typography>
                  </Box>
                </Grid>
                <Grid item xs={12}>
                  <Box sx={{ textAlign: "center", mt: 2 }}>
                    <Typography variant="body2" color="text.secondary">
                      Advance/Decline Ratio:{" "}
                      {marketBreadth.advance_decline_ratio !== undefined
                        ? marketBreadth.advance_decline_ratio
                        : "N/A"}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      Average Change:{" "}
                      {marketBreadth.average_change_percent !== undefined
                        ? parseFloat(
                            marketBreadth.average_change_percent
                          ).toFixed(2) + "%"
                        : "N/A"}
                    </Typography>
                  </Box>
                </Grid>
              </Grid>
            </CardContent>
          </AnimatedCard>
        </Grid>
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                Market Statistics
              </Typography>
              <Box
                sx={{ display: "flex", justifyContent: "space-between", mb: 2 }}
              >
                <Typography variant="body2">Total Stocks:</Typography>
                <Typography variant="body2" fontWeight="600">
                  {marketBreadth.total_stocks !== undefined
                    ? parseInt(marketBreadth.total_stocks).toLocaleString()
                    : "N/A"}
                </Typography>
              </Box>
              <Box
                sx={{ display: "flex", justifyContent: "space-between", mb: 2 }}
              >
                <Typography variant="body2">Total Market Cap:</Typography>
                <Typography variant="body2" fontWeight="600">
                  {marketCap.total !== undefined
                    ? formatCurrency(marketCap.total)
                    : "N/A"}
                </Typography>
              </Box>
              <Box
                sx={{ display: "flex", justifyContent: "space-between", mb: 2 }}
              >
                <Typography variant="body2">Unchanged:</Typography>
                <Typography variant="body2" fontWeight="600">
                  {marketBreadth.unchanged !== undefined
                    ? parseInt(marketBreadth.unchanged).toLocaleString()
                    : "N/A"}
                </Typography>
              </Box>{" "}
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                Market Cap Distribution
              </Typography>
              <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
                <Typography variant="body2">Large Cap:</Typography>
                <Typography variant="body2" fontWeight="600">
                  {formatCurrency(marketCap.large_cap)}
                </Typography>
              </Box>
              <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
                <Typography variant="body2">Mid Cap:</Typography>
                <Typography variant="body2" fontWeight="600">
                  {formatCurrency(marketCap.mid_cap)}
                </Typography>
              </Box>
              <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
                <Typography variant="body2">Small Cap:</Typography>
                <Typography variant="body2" fontWeight="600">
                  {formatCurrency(marketCap.small_cap)}
                </Typography>
              </Box>
              <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
                <Typography variant="body2">Total:</Typography>
                <Typography variant="body2" fontWeight="600">
                  {formatCurrency(marketCap.total)}
                </Typography>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Distribution Days Card - IBD Methodology */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                Distribution Days
              </Typography>
              {distributionDaysLoading ? (
                <CircularProgress size={24} />
              ) : (
                <>
                  {Object.entries(distributionDays).length > 0 ? (
                    <>
                      {Object.entries(distributionDays).map(([symbol, data]) => {
                        // Determine color based on signal
                        const getSignalColor = (signal) => {
                          switch (signal) {
                            case "NORMAL":
                              return "success.main";
                            case "ELEVATED":
                              return "warning.main";
                            case "CAUTION":
                              return "warning.dark";
                            case "UNDER_PRESSURE":
                              return "error.main";
                            default:
                              return "text.secondary";
                          }
                        };

                        const getSignalChipColor = (signal) => {
                          switch (signal) {
                            case "NORMAL":
                              return "success";
                            case "ELEVATED":
                              return "warning";
                            case "CAUTION":
                              return "warning";
                            case "UNDER_PRESSURE":
                              return "error";
                            default:
                              return "default";
                          }
                        };

                        return (
                          <Box
                            key={symbol}
                            sx={{
                              display: "flex",
                              justifyContent: "space-between",
                              alignItems: "center",
                              mb: 1.5,
                              p: 1,
                              borderRadius: 1,
                              backgroundColor: "grey.50",
                            }}
                          >
                            <Box>
                              <Typography variant="body2" fontWeight={600}>
                                {data.name}
                              </Typography>
                              <Typography variant="caption" color="text.secondary">
                                {symbol}
                              </Typography>
                            </Box>
                            <Box sx={{ textAlign: "right" }}>
                              <Typography
                                variant="h6"
                                sx={{
                                  color: getSignalColor(data.signal),
                                  fontWeight: 600,
                                }}
                              >
                                {data.count}
                              </Typography>
                              <Chip
                                label={data.signal}
                                color={getSignalChipColor(data.signal)}
                                size="small"
                              />
                            </Box>
                          </Box>
                        );
                      })}
                      <Box sx={{ mt: 2, pt: 2, borderTop: 1, borderColor: "divider" }}>
                        <Typography variant="caption" color="text.secondary">
                          IBD Distribution Days: Down 0.2%+ on higher volume over 25 days
                        </Typography>
                      </Box>
                    </>
                  ) : (
                    <Typography variant="body2" color="text.secondary">
                      No distribution days data available
                    </Typography>
                  )}
                </>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Enhanced Tabs Section */}
      <Box>
        <Box
          sx={{
            borderBottom: 1,
            borderColor: "divider",
            bgcolor: "background.paper",
          }}
        >
          <Tabs
              value={tabValue}
              onChange={handleTabChange}
              aria-label="market data tabs"
              variant="scrollable"
              scrollButtons="auto"
              sx={{
                "& .MuiTab-root": {
                  minHeight: 56,
                  fontWeight: 600,
                  fontSize: "0.875rem",
                  textTransform: "none",
                  "&.Mui-selected": {
                    color: theme.palette.primary.main,
                  },
                },
                "& .MuiTabs-indicator": {
                  height: 3,
                  borderRadius: "3px 3px 0 0",
                  background: `linear-gradient(90deg, ${theme.palette.primary.main} 0%, ${theme.palette.secondary.main} 100%)`,
                },
              }}
            >
              <Tab
                value={0}
                label="Sentiment History"
                icon={<Timeline />}
                iconPosition="start"
              />
              <Tab
                value={1}
                label="Market Breadth"
                icon={<Equalizer />}
                iconPosition="start"
              />
              <Tab
                value={2}
                label="Seasonality"
                icon={<CalendarToday />}
                iconPosition="start"
              />
            </Tabs>
        </Box>

        {tabsReady && (
          <>
        <TabPanel value={tabValue} index={0}>
          {sentimentLoading ? (
            <LinearProgress />
          ) : (
            <SentimentHistoryPanel />
          )}
        </TabPanel>

        <TabPanel value={tabValue} index={1}>
          {breadthLoading ? (
            <LinearProgress />
          ) : (
            <Grid container spacing={3}>
              <Grid item xs={12} md={6}>
                <Card>
                  <CardContent>
                    <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                      Market Breadth Details
                    </Typography>
                    <Box
                      sx={{
                        display: "flex",
                        justifyContent: "space-between",
                        mb: 2,
                      }}
                    >
                      <Typography variant="body2">Advancing Stocks:</Typography>
                      <Typography
                        variant="body2"
                        color="success.main"
                        fontWeight="600"
                      >
                        {breadthInfo.advancing || 0}
                      </Typography>
                    </Box>
                    <Box
                      sx={{
                        display: "flex",
                        justifyContent: "space-between",
                        mb: 2,
                      }}
                    >
                      <Typography variant="body2">Declining Stocks:</Typography>
                      <Typography
                        variant="body2"
                        color="error.main"
                        fontWeight="600"
                      >
                        {breadthInfo.declining || 0}
                      </Typography>
                    </Box>
                    <Box
                      sx={{
                        display: "flex",
                        justifyContent: "space-between",
                        mb: 2,
                      }}
                    >
                      <Typography variant="body2">Unchanged:</Typography>
                      <Typography variant="body2" fontWeight="600">
                        {breadthInfo.unchanged || 0}
                      </Typography>
                    </Box>
                    <Box
                      sx={{
                        display: "flex",
                        justifyContent: "space-between",
                        mb: 2,
                      }}
                    >
                      <Typography variant="body2">A/D Ratio:</Typography>
                      <Typography variant="body2" fontWeight="600">
                        {breadthInfo.advance_decline_ratio || "N/A"}
                      </Typography>
                    </Box>
                    <Box
                      sx={{
                        display: "flex",
                        justifyContent: "space-between",
                        mb: 2,
                      }}
                    >
                      <Typography variant="body2">Average Change:</Typography>
                      <Typography
                        variant="body2"
                        fontWeight="600"
                        sx={{
                          color: getChangeColor(
                            parseFloat(breadthInfo.average_change_percent) || 0
                          ),
                        }}
                      >
                        {formatPercentage(
                          parseFloat(breadthInfo.average_change_percent) || 0
                        )}
                      </Typography>
                    </Box>
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={12} md={6}>
                <Card>
                  <CardContent>
                    <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                      Breadth Visualization
                    </Typography>
                    <ResponsiveContainer width="100%" height={300}>
                      <PieChart>
                        <Pie
                          data={[
                            {
                              name: "Advancing",
                              value: breadthInfo.advancing || 0,
                              color: "#4CAF50",
                            },
                            {
                              name: "Declining",
                              value: breadthInfo.declining || 0,
                              color: "#F44336",
                            },
                            {
                              name: "Unchanged",
                              value: breadthInfo.unchanged || 0,
                              color: "#9E9E9E",
                            },
                          ]}
                          cx="50%"
                          cy="50%"
                          outerRadius={80}
                          dataKey="value"
                          label={({ name, value }) => `${name}: ${value}`}
                        >
                          <Cell fill="#4CAF50" />
                          <Cell fill="#F44336" />
                          <Cell fill="#9E9E9E" />
                        </Pie>
                        <Tooltip />
                      </PieChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          )}
        </TabPanel>

        <TabPanel value={tabValue} index={2}>
          {seasonalityLoading ? (
            <LinearProgress />
          ) : (
            <Grid container spacing={3}>
              {seasonalityData?.data && (
                <>
                  {/* Current Seasonal Position Summary */}
                  <Grid item xs={12}>
                    <Card
                      sx={{ border: "2px solid", borderColor: "primary.main" }}
                    >
                      <CardContent>
                        <Typography
                          variant="h6"
                          sx={{ mb: 2, fontWeight: 600 }}
                        >
                          Current Seasonal Position
                        </Typography>
                        <Grid container spacing={3}>
                          <Grid item xs={12} md={4}>
                            <Box
                              sx={{
                                textAlign: "center",
                                p: 2,
                                backgroundColor: "info.light",
                                borderRadius: 1,
                              }}
                            >
                              <Typography
                                variant="h4"
                                color="info.contrastText"
                              >
                                {
                                  seasonalityData?.data.currentPosition
                                    .seasonalScore
                                }
                                /100
                              </Typography>
                              <Typography
                                variant="body2"
                                color="info.contrastText"
                              >
                                Seasonal Score
                              </Typography>
                              <Typography
                                variant="caption"
                                color="info.contrastText"
                              >
                                {
                                  seasonalityData?.data.summary
                                    .overallSeasonalBias
                                }
                              </Typography>
                            </Box>
                          </Grid>
                          <Grid item xs={12} md={4}>
                            <Box
                              sx={{
                                textAlign: "center",
                                p: 2,
                                backgroundColor: "secondary.light",
                                borderRadius: 1,
                              }}
                            >
                              <Typography
                                variant="h6"
                                color="secondary.contrastText"
                              >
                                {
                                  seasonalityData?.data.currentPosition
                                    .presidentialCycle
                                }
                              </Typography>
                              <Typography
                                variant="body2"
                                color="secondary.contrastText"
                              >
                                Presidential Cycle
                              </Typography>
                            </Box>
                          </Grid>
                          <Grid item xs={12} md={4}>
                            <Box
                              sx={{
                                textAlign: "center",
                                p: 2,
                                backgroundColor: "warning.light",
                                borderRadius: 1,
                              }}
                            >
                              <Typography
                                variant="h6"
                                color="warning.contrastText"
                              >
                                {
                                  seasonalityData?.data.currentPosition
                                    .nextMajorEvent?.name
                                }
                              </Typography>
                              <Typography
                                variant="body2"
                                color="warning.contrastText"
                              >
                                Next Event (
                                {
                                  seasonalityData?.data.currentPosition
                                    .nextMajorEvent?.daysAway
                                }{" "}
                                days)
                              </Typography>
                            </Box>
                          </Grid>
                        </Grid>
                        <Box sx={{ mt: 3 }}>
                          <Typography variant="body1" sx={{ mb: 1 }}>
                            <strong>Recommendation:</strong>{" "}
                            {seasonalityData?.data.summary.recommendation}
                          </Typography>
                          <Typography variant="body2" color="text.secondary">
                            Active Periods:{" "}
                            {seasonalityData?.data.currentPosition.activePeriods?.join(
                              ", "
                            )}
                          </Typography>
                        </Box>
                      </CardContent>
                    </Card>
                  </Grid>

                  {/* Monthly Seasonality */}
                  <Grid item xs={12} md={6}>
                    <Card>
                      <CardContent>
                        <Typography
                          variant="h6"
                          sx={{ mb: 2, fontWeight: 600 }}
                        >
                          Monthly Seasonality Pattern
                        </Typography>
                        <ResponsiveContainer width="100%" height={300}>
                          <BarChart
                            data={seasonalityData?.data.monthlySeasonality}
                          >
                            <CartesianGrid strokeDasharray="3 3" />
                            <XAxis
                              dataKey="name"
                              angle={-45}
                              textAnchor="end"
                              height={80}
                            />
                            <YAxis
                              label={{
                                value: "Avg Return %",
                                angle: -90,
                                position: "insideLeft",
                              }}
                            />
                            <Tooltip
                              formatter={(value) => [
                                `${value.toFixed(1)}%`,
                                "Average Return",
                              ]}
                            />
                            <Bar
                              dataKey="avgReturn"
                              fill={(entry) =>
                                entry?.isCurrent ? "#82ca9d" : "#8884d8"
                              }
                              name="Monthly Average"
                            />
                          </BarChart>
                        </ResponsiveContainer>
                      </CardContent>
                    </Card>
                  </Grid>

                  {/* Quarterly Patterns */}
                  <Grid item xs={12} md={6}>
                    <Card>
                      <CardContent>
                        <Typography
                          variant="h6"
                          sx={{ mb: 2, fontWeight: 600 }}
                        >
                          Quarterly Performance
                        </Typography>
                        <ResponsiveContainer width="100%" height={300}>
                          <BarChart
                            data={seasonalityData?.data.quarterlySeasonality}
                          >
                            <CartesianGrid strokeDasharray="3 3" />
                            <XAxis dataKey="name" />
                            <YAxis
                              label={{
                                value: "Avg Return %",
                                angle: -90,
                                position: "insideLeft",
                              }}
                            />
                            <Tooltip
                              formatter={(value, _name, _props) => [
                                `${value.toFixed(1)}%`,
                                "Average Return",
                              ]}
                            />
                            <Bar
                              dataKey="avgReturn"
                              fill="#8884d8"
                              name="Quarterly Average"
                            />
                          </BarChart>
                        </ResponsiveContainer>
                      </CardContent>
                    </Card>
                  </Grid>

                  {/* Presidential Cycle Details */}
                  <Grid item xs={12} md={6}>
                    <Card>
                      <CardContent>
                        <Typography
                          variant="h6"
                          sx={{ mb: 2, fontWeight: 600 }}
                        >
                          Presidential Cycle (4-Year Pattern)
                        </Typography>
                        <TableContainer>
                          <Table size="small">
                            <TableHead>
                              <TableRow>
                                <TableCell>Year</TableCell>
                                <TableCell>Phase</TableCell>
                                <TableCell align="right">Avg Return</TableCell>
                                <TableCell align="center">Status</TableCell>
                              </TableRow>
                            </TableHead>
                            <TableBody>
                              {(
                                seasonalityData?.data.presidentialCycle?.data ||
                                []
                              ).map((cycle) => (
                                <TableRow
                                  key={cycle.year}
                                  sx={{
                                    backgroundColor: cycle.isCurrent
                                      ? "primary.light"
                                      : "transparent",
                                  }}
                                >
                                  <TableCell>Year {cycle.year}</TableCell>
                                  <TableCell>{cycle.label}</TableCell>
                                  <TableCell align="right">
                                    {formatPercentage(cycle.avgReturn)}
                                  </TableCell>
                                  <TableCell align="center">
                                    {cycle.isCurrent && (
                                      <Chip
                                        label="CURRENT"
                                        color="primary"
                                        size="small"
                                      />
                                    )}
                                  </TableCell>
                                </TableRow>
                              ))}
                            </TableBody>
                          </Table>
                        </TableContainer>
                      </CardContent>
                    </Card>
                  </Grid>

                  {/* Day of Week Effects */}
                  <Grid item xs={12} md={6}>
                    <Card>
                      <CardContent>
                        <Typography
                          variant="h6"
                          sx={{ mb: 2, fontWeight: 600 }}
                        >
                          Day of Week Effects
                        </Typography>
                        {(seasonalityData?.data.dayOfWeekEffects || []).map(
                          (day) => (
                            <Box
                              key={day.day}
                              sx={{
                                display: "flex",
                                justifyContent: "space-between",
                                mb: 1,
                                p: 1,
                                backgroundColor: day.isCurrent
                                  ? "primary.light"
                                  : "transparent",
                                borderRadius: 1,
                              }}
                            >
                              <Typography
                                variant="body2"
                                fontWeight={day.isCurrent ? 600 : 400}
                              >
                                {day.day}
                              </Typography>
                              <Typography
                                variant="body2"
                                sx={{
                                  color: getChangeColor(day.avgReturn * 100),
                                }}
                                fontWeight={600}
                              >
                                {formatPercentage(day.avgReturn)}
                              </Typography>
                            </Box>
                          )
                        )}
                      </CardContent>
                    </Card>
                  </Grid>

                  {/* Seasonal Anomalies */}
                  <Grid item xs={12}>
                    <Card>
                      <CardContent>
                        <Typography
                          variant="h6"
                          sx={{ mb: 2, fontWeight: 600 }}
                        >
                          Seasonal Anomalies & Effects
                        </Typography>
                        <Grid container spacing={2}>
                          {(seasonalityData?.data.seasonalAnomalies || []).map(
                            (anomaly, index) => (
                              <Grid item xs={12} sm={6} md={3} key={index}>
                                <Box
                                  sx={{
                                    p: 2,
                                    border: 1,
                                    borderColor: "divider",
                                    borderRadius: 1,
                                    height: "100%",
                                  }}
                                >
                                  <Typography
                                    variant="subtitle2"
                                    fontWeight={600}
                                  >
                                    {anomaly.name}
                                  </Typography>
                                  <Typography
                                    variant="caption"
                                    color="text.secondary"
                                    display="block"
                                  >
                                    {anomaly.period}
                                  </Typography>
                                  <Typography
                                    variant="body2"
                                    sx={{ mt: 1, mb: 1 }}
                                  >
                                    {anomaly.description}
                                  </Typography>
                                  <Chip
                                    label={anomaly.strength}
                                    size="small"
                                    color={
                                      anomaly.strength === "Strong"
                                        ? "error"
                                        : anomaly.strength === "Moderate"
                                          ? "warning"
                                          : "info"
                                    }
                                  />
                                </Box>
                              </Grid>
                            )
                          )}
                        </Grid>
                      </CardContent>
                    </Card>
                  </Grid>

                  {/* Holiday Effects */}
                  <Grid item xs={12} md={6}>
                    <Card>
                      <CardContent>
                        <Typography
                          variant="h6"
                          sx={{ mb: 2, fontWeight: 600 }}
                        >
                          Holiday Effects
                        </Typography>
                        <TableContainer>
                          <Table size="small">
                            <TableHead>
                              <TableRow>
                                <TableCell>Holiday</TableCell>
                                <TableCell>Dates</TableCell>
                                <TableCell align="right">Effect</TableCell>
                              </TableRow>
                            </TableHead>
                            <TableBody>
                              {(seasonalityData?.data.holidayEffects || []).map(
                                (holiday, index) => (
                                  <TableRow key={index}>
                                    <TableCell>{holiday.holiday}</TableCell>
                                    <TableCell>{holiday.dates}</TableCell>
                                    <TableCell
                                      align="right"
                                      sx={{
                                        color: getChangeColor(
                                          parseFloat(
                                            holiday.effect.replace("%", "")
                                          )
                                        ),
                                        fontWeight: 600,
                                      }}
                                    >
                                      {holiday.effect}
                                    </TableCell>
                                  </TableRow>
                                )
                              )}
                            </TableBody>
                          </Table>
                        </TableContainer>
                      </CardContent>
                    </Card>
                  </Grid>

                  {/* Sector Seasonality */}
                  <Grid item xs={12} md={6}>
                    <Card>
                      <CardContent>
                        <Typography
                          variant="h6"
                          sx={{ mb: 2, fontWeight: 600 }}
                        >
                          Sector Seasonality
                        </Typography>
                        {(seasonalityData?.data.sectorSeasonality || []).map(
                          (sector, index) => (
                            <Box key={index} sx={{ mb: 2 }}>
                              <Typography variant="subtitle2" fontWeight={600}>
                                {sector.sector}
                              </Typography>
                              <Typography
                                variant="caption"
                                color="text.secondary"
                              >
                                Best:{" "}
                                {sector.bestMonths
                                  .map((m) =>
                                    new Date(0, m - 1).toLocaleString(
                                      "default",
                                      { month: "short" }
                                    )
                                  )
                                  .join(", ")}
                              </Typography>
                              <Typography
                                variant="caption"
                                color="text.secondary"
                                display="block"
                              >
                                Worst:{" "}
                                {sector.worstMonths
                                  .map((m) =>
                                    new Date(0, m - 1).toLocaleString(
                                      "default",
                                      { month: "short" }
                                    )
                                  )
                                  .join(", ")}
                              </Typography>
                              <Typography variant="body2" sx={{ mt: 0.5 }}>
                                {sector.rationale}
                              </Typography>
                            </Box>
                          )
                        )}
                      </CardContent>
                    </Card>
                  </Grid>

                  {/* Summary & Outlook */}
                  <Grid item xs={12}>
                    <Card>
                      <CardContent>
                        <Typography
                          variant="h6"
                          sx={{ mb: 2, fontWeight: 600 }}
                        >
                          Seasonal Outlook Summary
                        </Typography>
                        <Grid container spacing={3}>
                          <Grid item xs={12} md={6}>
                            <Typography
                              variant="body2"
                              fontWeight={600}
                              color="success.main"
                              sx={{ mb: 1 }}
                            >
                              Favorable Factors:
                            </Typography>
                            {seasonalityData?.data.summary.favorableFactors?.map(
                              (factor, index) => (
                                <Typography
                                  key={index}
                                  variant="body2"
                                  sx={{ ml: 2, mb: 0.5 }}
                                >
                                  • {factor}
                                </Typography>
                              )
                            )}
                          </Grid>
                          <Grid item xs={12} md={6}>
                            <Typography
                              variant="body2"
                              fontWeight={600}
                              color="error.main"
                              sx={{ mb: 1 }}
                            >
                              Unfavorable Factors:
                            </Typography>
                            {seasonalityData?.data.summary.unfavorableFactors?.map(
                              (factor, index) => (
                                <Typography
                                  key={index}
                                  variant="body2"
                                  sx={{ ml: 2, mb: 0.5 }}
                                >
                                  • {factor}
                                </Typography>
                              )
                            )}
                          </Grid>
                        </Grid>
                      </CardContent>
                    </Card>
                  </Grid>
                </>
              )}
            </Grid>
          )}
        </TabPanel>


          </>
        )}
      </Box>
    </Box>
  );
}

export default MarketOverview;
