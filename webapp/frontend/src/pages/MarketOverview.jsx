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
  XAxis,
  YAxis,
  CartesianGrid,
  ResponsiveContainer,
  BarChart,
  Bar,
  ComposedChart,
  Line,
  LineChart,
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
  getMcClellanOscillator,
  getSentimentDivergence,
} from "../services/api";
import {
  formatCurrency,
  formatPercentage,
  formatPercentageChange,
  getChangeColor,
} from "../utils/formatters";
import { createComponentLogger } from "../utils/errorLogger";
import SectorSeasonalityTable from "../components/SectorSeasonalityTable";
import McClellanOscillatorChart from "../components/McClellanOscillatorChart";
import SentimentDivergenceChart from "../components/SentimentDivergenceChart";

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

const fetchMcClellanOscillator = async () => {
  try {
    console.log("📊 Fetching McClellan Oscillator...");
    const response = await getMcClellanOscillator();
    console.log("📊 McClellan response:", response);
    return response;
  } catch (error) {
    _logger.error("McClellan Oscillator error:", error.message || error.toString());
    throw error;
  }
};

const fetchSentimentDivergence = async () => {
  try {
    console.log("💡 Fetching sentiment divergence...");
    const response = await getSentimentDivergence();
    console.log("💡 Sentiment divergence response:", response);
    return response;
  } catch (error) {
    _logger.error("Sentiment divergence error:", error.message || error.toString());
    throw error;
  }
};

function MarketOverview() {
  const [tabValue, setTabValue] = useState(0);
  const [tabsReady, setTabsReady] = useState(false);
  const [_viewMode, _setViewMode] = useState("cards");
  const [_selectedSector, _setSelectedSector] = useState("all");
  const [aaiiRange, setAaiiRange] = useState("30d");
  const [fearGreedRange, setFearGreedRange] = useState("30d");
  const [naaimRange, setNaaimRange] = useState("30d");
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

  const { data: mcOscillatorData, isLoading: mcOscillatorLoading } = useQuery({
    queryKey: ["mcclellan-oscillator"],
    queryFn: fetchMcClellanOscillator,
    staleTime: 60000,
    refetchInterval: 60000,
  });

  const { data: sentimentDivergenceData, isLoading: sentimentDivergenceLoading } = useQuery({
    queryKey: ["sentiment-divergence"],
    queryFn: fetchSentimentDivergence,
    staleTime: 60000,
    refetchInterval: 60000,
  });

  const { data: aaiiData, isLoading: aaiiLoading } = useQuery({
    queryKey: ["aaii-sentiment", aaiiRange],
    queryFn: async () => {
      const response = await fetch(`${import.meta.env.VITE_API_URL || 'http://localhost:3001'}/api/market/aaii?range=${aaiiRange}`);
      if (!response.ok) throw new Error("Failed to fetch AAII data");
      return response.json();
    },
    staleTime: 30000,
    refetchInterval: 300000,
  });

  const { data: fearGreedData, isLoading: fearGreedLoading } = useQuery({
    queryKey: ["fear-greed", fearGreedRange],
    queryFn: async () => {
      const response = await fetch(`${import.meta.env.VITE_API_URL || 'http://localhost:3001'}/api/market/fear-greed?range=${fearGreedRange}`);
      if (!response.ok) throw new Error("Failed to fetch Fear & Greed data");
      return response.json();
    },
    staleTime: 30000,
    refetchInterval: 300000,
  });

  const { data: naaimData, isLoading: naaimLoading } = useQuery({
    queryKey: ["naaim", naaimRange],
    queryFn: async () => {
      const response = await fetch(`${import.meta.env.VITE_API_URL || 'http://localhost:3001'}/api/market/naaim?range=${naaimRange}`);
      if (!response.ok) throw new Error("Failed to fetch NAAIM data");
      return response.json();
    },
    staleTime: 30000,
    refetchInterval: 300000,
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
  const hasBreadthError = !breadthInfo || Object.keys(breadthInfo).length === 0;
  const distributionDays = distributionDaysData?.data || {};
  const sentimentHistory = sentimentData?.data || {};
  console.log("sentimentHistory", sentimentHistory);


  // Prepare sentiment chart data for all indicators
  const fearGreedHistory = sentimentHistory?.fear_greed_history || [];
  const naaimHistory = sentimentHistory?.naaim_history || [];
  const aaiiHistory = sentimentHistory?.aaii_history || [];
  console.log("aaiiHistory", aaiiHistory);

  // Merge by date for multi-line chart - only include dates with actual data
  const dateMap = {};
  fearGreedHistory.forEach((item) => {
    const date = item.date || item.timestamp;
    // Filter out weekends (Saturday=6, Sunday=0) for seamless Fear & Greed line
    const dateObj = new Date(date);
    const dayOfWeek = dateObj.getDay();
    const isWeekend = dayOfWeek === 0 || dayOfWeek === 6;

    if (!isWeekend) {
      if (!dateMap[date]) dateMap[date] = { date };
      dateMap[date].fear_greed = item.value;
      dateMap[date].fear_greed_text = item.value_text;
      dateMap[date].has_fear_greed = true;
    }
  });
  naaimHistory.forEach((item) => {
    const date = item.date || item.timestamp;
    if (!dateMap[date]) dateMap[date] = { date };
    dateMap[date].naaim = item.mean_exposure || item.average;
    dateMap[date].has_naaim = true;
  });
  aaiiHistory.forEach((item) => {
    const date = item.date || item.timestamp;
    if (!dateMap[date]) dateMap[date] = { date };
    dateMap[date].aaii_bullish = item.bullish;
    dateMap[date].aaii_bearish = item.bearish;
    dateMap[date].aaii_neutral = item.neutral;
    dateMap[date].has_aaii = true;
  });

  // Include all dates with any sentiment data (not all three required)
  // Each chart will render only the data it has, allowing partial data display
  const sentimentChartData = Object.values(dateMap)
    .filter(d => d.has_fear_greed || d.has_naaim || d.has_aaii)
    .sort((a, b) => new Date(a.date) - new Date(b.date))
    .map(d => {
      const { has_fear_greed: _has_fear_greed, has_naaim: _has_naaim, has_aaii: _has_aaii, ...cleanData } = d;
      return cleanData;
    })
    .slice(-30);
  console.log("sentimentChartData after filtering:", {
    total_dates: sentimentChartData.length,
    sample: sentimentChartData.length > 0 ? sentimentChartData[0] : null
  });

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

        {/* AAII Historical Sentiment Chart with Time Range Selector */}
        <Grid item xs={12}>
          <Card>
            <CardContent>
              <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 3 }}>
                <Typography variant="h6" sx={{ fontWeight: 600 }}>
                  AAII Sentiment History
                </Typography>
                <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
                  {["30d", "90d", "6m", "1y", "all"].map((range) => (
                    <Chip
                      key={range}
                      label={range.toUpperCase()}
                      onClick={() => setAaiiRange(range)}
                      color={aaiiRange === range ? "primary" : "default"}
                      variant={aaiiRange === range ? "filled" : "outlined"}
                      sx={{ cursor: "pointer" }}
                    />
                  ))}
                </Box>
              </Box>

              {aaiiLoading ? (
                <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", height: 400 }}>
                  <CircularProgress />
                </Box>
              ) : aaiiData?.data && aaiiData.data.length > 0 ? (
                <Box sx={{ height: 400, width: "100%" }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart
                      data={aaiiData.data}
                      margin={{ top: 5, right: 30, left: 0, bottom: 5 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis
                        dataKey="date"
                        tick={{ fontSize: 12 }}
                        tickFormatter={(date) => {
                          const d = new Date(date);
                          return `${(d.getMonth() + 1).toString().padStart(2, "0")}/${d.getDate().toString().padStart(2, "0")}`;
                        }}
                      />
                      <YAxis
                        domain={[0, 100]}
                        label={{
                          value: "Sentiment %",
                          angle: -90,
                          position: "insideLeft",
                        }}
                      />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: "rgba(0,0,0,0.8)",
                          border: "1px solid #ccc",
                          color: "#fff",
                          borderRadius: "4px",
                        }}
                        formatter={(value) => [`${parseFloat(value).toFixed(1)}%`, ""]}
                        labelFormatter={(date) => {
                          const d = new Date(date);
                          return d.toLocaleDateString("en-US", {
                            year: "numeric",
                            month: "short",
                            day: "numeric",
                          });
                        }}
                      />
                      <Legend />
                      <Line
                        type="monotone"
                        dataKey="bullish"
                        stroke={_colorSchemes.sentiment.bullish}
                        strokeWidth={2.5}
                        dot={false}
                        name="Bullish"
                      />
                      <Line
                        type="monotone"
                        dataKey="neutral"
                        stroke={_colorSchemes.sentiment.moderate}
                        strokeWidth={2.5}
                        dot={false}
                        name="Neutral"
                      />
                      <Line
                        type="monotone"
                        dataKey="bearish"
                        stroke={_colorSchemes.sentiment.bearish}
                        strokeWidth={2.5}
                        dot={false}
                        name="Bearish"
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </Box>
              ) : (
                <Box sx={{ textAlign: "center", py: 4 }}>
                  <Typography variant="body2" color="text.secondary">
                    No AAII sentiment data available for the selected range
                  </Typography>
                </Box>
              )}

              <Box sx={{ mt: 2, pt: 2, borderTop: 1, borderColor: "divider" }}>
                <Typography variant="caption" color="text.secondary">
                  AAII Sentiment Survey: Retail investor bullish/bearish sentiment data updated weekly
                  {aaiiData?.dateRange && ` | Data range: ${new Date(aaiiData.dateRange.from).toLocaleDateString()} - ${new Date(aaiiData.dateRange.to).toLocaleDateString()}`}
                </Typography>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Fear & Greed Index Historical Chart with Time Range Selector */}
        <Grid item xs={12}>
          <Card>
            <CardContent>
              <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 3 }}>
                <Typography variant="h6" sx={{ fontWeight: 600 }}>
                  Fear & Greed Index History
                </Typography>
                <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
                  {["30d", "90d", "6m", "1y", "all"].map((range) => (
                    <Chip
                      key={range}
                      label={range.toUpperCase()}
                      onClick={() => setFearGreedRange(range)}
                      color={fearGreedRange === range ? "primary" : "default"}
                      variant={fearGreedRange === range ? "filled" : "outlined"}
                      sx={{ cursor: "pointer" }}
                    />
                  ))}
                </Box>
              </Box>

              {fearGreedLoading ? (
                <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", height: 400 }}>
                  <CircularProgress />
                </Box>
              ) : fearGreedData?.data && fearGreedData.data.length > 0 ? (
                <Box sx={{ height: 400, width: "100%" }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart
                      data={fearGreedData.data}
                      margin={{ top: 5, right: 30, left: 0, bottom: 5 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis
                        dataKey="date"
                        tick={{ fontSize: 12 }}
                        tickFormatter={(date) => {
                          const d = new Date(date);
                          return `${(d.getMonth() + 1).toString().padStart(2, "0")}/${d.getDate().toString().padStart(2, "0")}`;
                        }}
                      />
                      <YAxis
                        domain={[0, 100]}
                        label={{
                          value: "Fear & Greed Index",
                          angle: -90,
                          position: "insideLeft",
                        }}
                      />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: "rgba(0,0,0,0.8)",
                          border: "1px solid #ccc",
                          color: "#fff",
                          borderRadius: "4px",
                        }}
                        formatter={(value) => [`${parseFloat(value).toFixed(1)}`, ""]}
                        labelFormatter={(date) => {
                          const d = new Date(date);
                          return d.toLocaleDateString("en-US", {
                            year: "numeric",
                            month: "short",
                            day: "numeric",
                          });
                        }}
                      />
                      <Legend />
                      <Line
                        type="monotone"
                        dataKey="value"
                        stroke="#FF6B6B"
                        strokeWidth={2.5}
                        dot={false}
                        name="Fear & Greed Index"
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </Box>
              ) : (
                <Box sx={{ textAlign: "center", py: 4 }}>
                  <Typography variant="body2" color="text.secondary">
                    No Fear & Greed data available for the selected range
                  </Typography>
                </Box>
              )}

              <Box sx={{ mt: 2, pt: 2, borderTop: 1, borderColor: "divider" }}>
                <Typography variant="caption" color="text.secondary">
                  CNN Fear & Greed Index: Market sentiment measurement across multiple indicators
                  {fearGreedData?.dateRange && ` | Data range: ${new Date(fearGreedData.dateRange.from).toLocaleDateString()} - ${new Date(fearGreedData.dateRange.to).toLocaleDateString()}`}
                </Typography>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* NAAIM Manager Exposure Chart with Time Range Selector */}
        <Grid item xs={12}>
          <Card>
            <CardContent>
              <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 3 }}>
                <Typography variant="h6" sx={{ fontWeight: 600 }}>
                  NAAIM Manager Exposure
                </Typography>
                <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
                  {["30d", "90d", "6m", "1y", "all"].map((range) => (
                    <Chip
                      key={range}
                      label={range.toUpperCase()}
                      onClick={() => setNaaimRange(range)}
                      color={naaimRange === range ? "primary" : "default"}
                      variant={naaimRange === range ? "filled" : "outlined"}
                      sx={{ cursor: "pointer" }}
                    />
                  ))}
                </Box>
              </Box>

              {naaimLoading ? (
                <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", height: 400 }}>
                  <CircularProgress />
                </Box>
              ) : naaimData?.data && naaimData.data.length > 0 ? (
                <Box sx={{ height: 400, width: "100%" }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart
                      data={naaimData.data}
                      margin={{ top: 5, right: 30, left: 0, bottom: 5 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis
                        dataKey="date"
                        tick={{ fontSize: 12 }}
                        tickFormatter={(date) => {
                          const d = new Date(date);
                          return `${(d.getMonth() + 1).toString().padStart(2, "0")}/${d.getDate().toString().padStart(2, "0")}`;
                        }}
                      />
                      <YAxis
                        label={{
                          value: "Exposure %",
                          angle: -90,
                          position: "insideLeft",
                        }}
                      />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: "rgba(0,0,0,0.8)",
                          border: "1px solid #ccc",
                          color: "#fff",
                          borderRadius: "4px",
                        }}
                        formatter={(value) => [`${parseFloat(value).toFixed(1)}%`, ""]}
                        labelFormatter={(date) => {
                          const d = new Date(date);
                          return d.toLocaleDateString("en-US", {
                            year: "numeric",
                            month: "short",
                            day: "numeric",
                          });
                        }}
                      />
                      <Legend />
                      <Line
                        type="monotone"
                        dataKey="bullish"
                        stroke="#10b981"
                        strokeWidth={2.5}
                        dot={false}
                        name="Bullish Exposure"
                      />
                      <Line
                        type="monotone"
                        dataKey="bearish"
                        stroke="#ef4444"
                        strokeWidth={2.5}
                        dot={false}
                        name="Bearish Exposure"
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </Box>
              ) : (
                <Box sx={{ textAlign: "center", py: 4 }}>
                  <Typography variant="body2" color="text.secondary">
                    No NAAIM data available for the selected range
                  </Typography>
                </Box>
              )}

              <Box sx={{ mt: 2, pt: 2, borderTop: 1, borderColor: "divider" }}>
                <Typography variant="caption" color="text.secondary">
                  NAAIM (National Association of Active Investment Managers) Manager Exposure Index: Measures the positioning of professional managers
                  {naaimData?.dateRange && ` | Data range: ${new Date(naaimData.dateRange.from).toLocaleDateString()} - ${new Date(naaimData.dateRange.to).toLocaleDateString()}`}
                </Typography>
              </Box>
            </CardContent>
          </Card>
        </Grid>

      </Grid>
    </Box>
  );

  return (
    <Box sx={{ minHeight: "100vh", bgcolor: "background.default" }} data-testid="market-overview-page">
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

      {/* Enhanced Market Indicators - Yield Curve, McClellan Oscillator, Sentiment Divergence */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        {/* McClellan Oscillator Chart */}
        <Grid item xs={12}>
          <McClellanOscillatorChart
            data={mcOscillatorData?.data}
            isLoading={mcOscillatorLoading}
          />
        </Grid>
      </Grid>

      {/* Sentiment Divergence Chart - Full Width */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={12}>
          <SentimentDivergenceChart
            data={sentimentDivergenceData?.data}
            isLoading={sentimentDivergenceLoading}
          />
        </Grid>
      </Grid>

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
                              return theme.palette.success.main;
                            case "WATCH":
                              return theme.palette.info.main;
                            case "ELEVATED":
                              return theme.palette.warning.main;
                            case "CAUTION":
                              return theme.palette.warning.dark;
                            case "WARNING":
                              return theme.palette.error.main;
                            case "URGENT":
                              return theme.palette.error.dark;
                            case "PRESSURE":
                              return theme.palette.error.main;
                            case "OMFG!!!":
                              return theme.palette.error.dark;
                            case "SERIOUS_PRESSURE":
                              return theme.palette.error.dark;
                            case "UNDER_PRESSURE":
                              return theme.palette.error.main;
                            default:
                              return theme.palette.text.secondary;
                          }
                        };

                        const getSignalChipColor = (signal) => {
                          switch (signal) {
                            case "NORMAL":
                              return "success";
                            case "WATCH":
                              return "info";
                            case "ELEVATED":
                              return "warning";
                            case "CAUTION":
                              return "warning";
                            case "WARNING":
                              return "error";
                            case "URGENT":
                              return "error";
                            case "PRESSURE":
                              return "error";
                            case "OMFG!!!":
                              return "error";
                            case "SERIOUS_PRESSURE":
                              return "error";
                            case "UNDER_PRESSURE":
                              return "error";
                            default:
                              return "default";
                          }
                        };

                        const getBackgroundColor = (signal) => {
                          switch (signal) {
                            case "NORMAL":
                              return alpha(theme.palette.success.main, 0.08);
                            case "WATCH":
                              return alpha(theme.palette.info.main, 0.08);
                            case "ELEVATED":
                              return alpha(theme.palette.warning.main, 0.08);
                            case "CAUTION":
                              return alpha(theme.palette.warning.main, 0.12);
                            case "WARNING":
                              return alpha(theme.palette.error.main, 0.10);
                            case "URGENT":
                              return alpha(theme.palette.error.main, 0.15);
                            case "PRESSURE":
                              return alpha(theme.palette.error.main, 0.10);
                            case "OMFG!!!":
                              return alpha(theme.palette.error.main, 0.15);
                            case "SERIOUS_PRESSURE":
                              return alpha(theme.palette.error.main, 0.12);
                            case "UNDER_PRESSURE":
                              return alpha(theme.palette.error.main, 0.10);
                            default:
                              return theme.palette.grey[50];
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
                              backgroundColor: getBackgroundColor(data.signal),
                              borderWidth: 1,
                              borderStyle: "solid",
                              borderColor: alpha(getSignalColor(data.signal), 0.3),
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
                        {(hasBreadthError ? "N/A" : breadthInfo.advancing || 0)}
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
                        {(hasBreadthError ? "N/A" : breadthInfo.declining || 0)}
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
                        {(hasBreadthError ? "N/A" : breadthInfo.unchanged || 0)}
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
                    <Box sx={{ height: 300, width: '100%' }}>
                      <ResponsiveContainer width="100%" height="100%">
                        <PieChart>
                          <Pie
                            data={[
                              {
                                name: "Advancing",
                                value: (hasBreadthError ? "N/A" : breadthInfo.advancing || 0),
                                color: "#4CAF50",
                              },
                              {
                                name: "Declining",
                                value: (hasBreadthError ? "N/A" : breadthInfo.declining || 0),
                                color: "#F44336",
                              },
                              {
                                name: "Unchanged",
                                value: (hasBreadthError ? "N/A" : breadthInfo.unchanged || 0),
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
                    </Box>
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
                        <Box sx={{ height: 350, width: '100%' }}>
                          <ResponsiveContainer width="100%" height="100%">
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
                                  `${(value || 0).toFixed(1)}%`,
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
                        </Box>
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
                        <Box sx={{ height: 350, width: '100%' }}>
                          <ResponsiveContainer width="100%" height="100%">
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
                                  `${(value || 0).toFixed(1)}%`,
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
                        </Box>
                      </CardContent>
                    </Card>
                  </Grid>

                  {/* Presidential Cycle - 4 Year Chart */}
                  <Grid item xs={12}>
                    <Card>
                      <CardContent>
                        <Typography
                          variant="h6"
                          sx={{ mb: 2, fontWeight: 600 }}
                        >
                          Presidential Cycle - 4 Year Pattern
                        </Typography>
                        <Box sx={{ height: 300, width: '100%' }}>
                          <ResponsiveContainer width="100%" height="100%">
                            <BarChart
                              data={seasonalityData?.data.presidentialCycle?.data || []}
                            >
                              <CartesianGrid strokeDasharray="3 3" />
                              <XAxis
                                dataKey="label"
                                tick={{ fontSize: 12 }}
                              />
                              <YAxis
                                label={{
                                  value: "Avg Return %",
                                  angle: -90,
                                  position: "insideLeft",
                                }}
                              />
                              <Tooltip
                                formatter={(value) => [`${(value || 0).toFixed(2)}%`, "Average Return"]}
                                contentStyle={{
                                  backgroundColor: "rgba(0,0,0,0.8)",
                                  border: "1px solid #ccc",
                                  color: "#fff"
                                }}
                              />
                              <Legend />
                              <Bar
                                dataKey="avgReturn"
                                name="Average Return"
                                fill={(entry) =>
                                  entry?.isCurrent ? "#3b82f6" : "#8884d8"
                                }
                              />
                            </BarChart>
                          </ResponsiveContainer>
                        </Box>
                      </CardContent>
                    </Card>
                  </Grid>

                  {/* Presidential Cycle - Current Year Monthly with S&P Overlay */}
                  <Grid item xs={12}>
                    <Card>
                      <CardContent>
                        <Typography
                          variant="h6"
                          sx={{ mb: 2, fontWeight: 600 }}
                        >
                          Current Year Monthly Performance vs Typical Cycle Year
                        </Typography>
                        <Typography variant="caption" color="text.secondary" sx={{ mb: 2, display: "block" }}>
                          Bars: Monthly average gain | Lines: Cumulative S&P return (current year vs typical cycle year)
                        </Typography>
                        <Box sx={{ height: 400, width: '100%' }}>
                          <ResponsiveContainer width="100%" height="100%">
                            <ComposedChart
                              data={seasonalityData?.data.monthlySeasonality || []}
                              margin={{ top: 10, right: 60, left: 20, bottom: 0 }}
                            >
                              <CartesianGrid strokeDasharray="3 3" />
                              <XAxis
                                dataKey="name"
                                tick={{ fontSize: 12 }}
                              />
                              <YAxis
                                yAxisId="left"
                                label={{
                                  value: "Monthly Return %",
                                  angle: -90,
                                  position: "insideLeft",
                                }}
                              />
                              <YAxis
                                yAxisId="right"
                                orientation="right"
                                label={{
                                  value: "Cumulative Return %",
                                  angle: 90,
                                  position: "outsideRight",
                                }}
                              />
                              <Tooltip
                                formatter={(value, name) => {
                                  if (name === "Monthly Avg Return") {
                                    return [`${(value || 0).toFixed(2)}%`, name];
                                  }
                                  return [`${(value || 0).toFixed(2)}%`, name];
                                }}
                                contentStyle={{
                                  backgroundColor: "rgba(0,0,0,0.8)",
                                  border: "1px solid #ccc",
                                  color: "#fff"
                                }}
                              />
                              <Legend
                                verticalAlign="top"
                                height={36}
                              />
                              <Line
                                yAxisId="right"
                                type="monotone"
                                dataKey="cumulativeSPCurrentYear"
                                name="Cumulative S&P (Current Year)"
                                stroke="#10b981"
                                strokeWidth={4}
                                dot={{ r: 5, fill: "#10b981", strokeWidth: 2 }}
                                activeDot={{ r: 7 }}
                                connectNulls={true}
                              />
                              <Line
                                yAxisId="right"
                                type="monotone"
                                dataKey="cumulativeSPTypicalYear"
                                name="Cumulative S&P (Typical Cycle Year)"
                                stroke="#f59e0b"
                                strokeWidth={4}
                                dot={{ r: 5, fill: "#f59e0b", strokeWidth: 2 }}
                                activeDot={{ r: 7 }}
                                connectNulls={true}
                              />
                              <Bar
                                yAxisId="left"
                                dataKey="avgReturn"
                                name="Monthly Avg Return"
                                opacity={0.75}
                                radius={[4, 4, 0, 0]}
                              >
                                {(seasonalityData?.data.monthlySeasonality || []).map((entry, index) => (
                                  <Cell
                                    key={`cell-${index}`}
                                    fill={(entry.avgReturn || 0) >= 0 ? "#22c55e" : "#ef4444"}
                                  />
                                ))}
                              </Bar>
                            </ComposedChart>
                          </ResponsiveContainer>
                        </Box>
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
                                (holiday, index) => {
                                  const effectValue = holiday.effect ? parseFloat(holiday.effect.replace("%", "")) : 0;
                                  return (
                                    <TableRow key={index}>
                                      <TableCell>{holiday.holiday}</TableCell>
                                      <TableCell>{holiday.dates}</TableCell>
                                      <TableCell
                                        align="right"
                                        sx={{
                                          color: getChangeColor(effectValue),
                                          fontWeight: 600,
                                        }}
                                      >
                                        {holiday.effect || "N/A"}
                                      </TableCell>
                                    </TableRow>
                                  );
                                }
                              )}
                            </TableBody>
                          </Table>
                        </TableContainer>
                      </CardContent>
                    </Card>
                  </Grid>

                  {/* Sector Seasonality - Calendar View */}
                  <Grid item xs={12}>
                    <Card>
                      <CardContent>
                        <SectorSeasonalityTable data={seasonalityData?.data.sectorSeasonality || []} />
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
