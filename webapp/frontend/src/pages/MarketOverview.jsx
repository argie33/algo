import { useState, useEffect, useMemo } from "react";
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
  Cell,
  Legend,
  Tooltip,
} from "recharts";
import {
  TrendingUp,
  TrendingDown,
  TrendingFlat,
  Timeline,
} from "@mui/icons-material";

import {
  getMarketTechnicals,
  getMarketSentimentData,
  getMarketSeasonalityData,
  getMarketCorrelation,
} from "../services/api";
import MarketExposure from "../components/MarketExposure";
import {
  formatCurrency,
  formatPercentage,
  formatPercentageChange,
  getChangeColor,
} from "../utils/formatters";
import { createComponentLogger } from "../utils/errorLogger";
import SectorSeasonalityTable from "../components/SectorSeasonalityTable";
import McClellanOscillatorChart from "../components/McClellanOscillatorChart";
import MarketInternals from "../components/MarketInternals";
import MarketVolatility from "../components/MarketVolatility";
import MarketCorrelation from "../components/MarketCorrelation";

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

// Fetch 3 separate market endpoints
const fetchMarketTechnicals = async () => {
  try {
    console.log("📊 Fetching market technicals...");
    const response = await getMarketTechnicals();
    console.log("📊 Market technicals response:", response);
    return response;
  } catch (error) {
    _logger.error("Market technicals error:", error.message || error.toString());
    throw error;
  }
};

const fetchMarketSentiment = async (range = "30d") => {
  try {
    console.log("😊 Fetching market sentiment...");
    const response = await getMarketSentimentData(range);
    console.log("😊 Market sentiment response:", response);
    return response;
  } catch (error) {
    _logger.error("Market sentiment error:", error.message || error.toString());
    throw error;
  }
};

const fetchMarketSeasonality = async () => {
  try {
    console.log("📅 Fetching market seasonality...");
    const response = await getMarketSeasonalityData();
    console.log("📅 Market seasonality response:", response);
    return response;
  } catch (error) {
    _logger.error("Market seasonality error:", error.message || error.toString());
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

  // Generate unique SVG gradient IDs for this component instance
  const { bullishGradientId, bearishGradientId } = useMemo(() => ({
    bullishGradientId: `bullishGradient-${Math.random().toString(36).substr(2, 9)}`,
    bearishGradientId: `bearishGradient-${Math.random().toString(36).substr(2, 9)}`,
  }), []);

  // Fix MUI Tabs validation error by ensuring tabs are ready before rendering
  useEffect(() => {
    const timer = setTimeout(() => setTabsReady(true), 100);
    return () => clearTimeout(timer);
  }, []);

  // MARKET DATA - 3 separate endpoints for focused data fetching
  const {
    data: technicalsData,
    isLoading: technicalsLoading,
    error: technicalsError,
  } = useQuery({
    queryKey: ["market-technicals"],
    queryFn: fetchMarketTechnicals,
    refetchInterval: 60000,
    retry: 2,
    staleTime: 0, // Always fresh
  });

  const {
    data: sentimentData,
    isLoading: sentimentLoading,
    error: sentimentError,
  } = useQuery({
    queryKey: ["market-sentiment-30d"],
    queryFn: () => fetchMarketSentiment("30d"),
    refetchInterval: 60000,
    retry: 2,
    staleTime: 0, // Always fresh
  });

  const {
    data: seasonalityData,
    isLoading: seasonalityLoading,
    error: seasonalityError,
  } = useQuery({
    queryKey: ["market-seasonality"],
    queryFn: fetchMarketSeasonality,
    refetchInterval: 60000,
    retry: 2,
    staleTime: 0, // Always fresh
  });

  // Combined loading and error states
  const marketLoading = technicalsLoading || sentimentLoading || seasonalityLoading;
  const marketError = technicalsError || sentimentError || seasonalityError;

  const { data: correlationData, isLoading: correlationLoading } = useQuery({
    queryKey: ["market-correlation"],
    queryFn: getMarketCorrelation,
    staleTime: 0, // Always fresh
    refetchInterval: 120000,
  });

const handleTabChange = (event, newValue) => {
    setTabValue(newValue);
  };

  // Extract data from 3 SEPARATE market endpoints (BEFORE early returns per React hooks rules)
  const techData = technicalsData?.data || {};
  const sentData = sentimentData?.data || {};
  const seasonData = seasonalityData?.data || {};

  console.log("📊 Market data structure:", { techData, sentData, seasonData });

  // Extract technicals data
  const breadth = techData?.breadth || {};
  const mcclellanRawData = techData?.mcclellan_oscillator || [];
  // Handle distribution_days - API returns {available: true}, but we need symbol-keyed data for MarketExposure
  const rawDistributionDays = techData?.distribution_days || {};
  const distributionDays = rawDistributionDays.available === true ? {} : rawDistributionDays;
  const volatility = techData?.volatility || {};
  const internals = techData?.internals || {};
  const seasonality = seasonData || {};

  // Transform McClellan data to component format
  const mcclellanOscillator = useMemo(() => {
    if (!Array.isArray(mcclellanRawData) || mcclellanRawData.length === 0) {
      return null;
    }
    // Calculate current value from latest data point
    const latest = mcclellanRawData[mcclellanRawData.length - 1];
    const previous = mcclellanRawData[mcclellanRawData.length - 2];
    const adl = latest?.advance_decline_line;
    const currentValue = typeof adl === 'number' ? adl : 0;
    const prevAdl = previous?.advance_decline_line;
    const change = typeof prevAdl === 'number' ? currentValue - prevAdl : 0;

    return {
      current_value: currentValue,
      ema_19: null, // Not available in new endpoint
      ema_39: null, // Not available in new endpoint
      interpretation: currentValue > 0 ? "Bullish breadth" : "Bearish breadth",
      recent_data: mcclellanRawData.slice(-30),
      change
    };
  }, [mcclellanRawData]);

  // Transform Volatility data to component format
  const volatilityFormatted = useMemo(() => {
    // Ensure numeric values to prevent NaN.toFixed() errors
    const mv = volatility?.market_volatility;
    const adc = volatility?.avg_daily_move;

    return {
      data: {
        market_volatility: typeof mv === 'number' ? mv : (typeof mv === 'string' ? parseFloat(mv) || 0 : 0),
        avg_absolute_change: typeof adc === 'number' ? adc : (typeof adc === 'string' ? parseFloat(adc) || 0 : 0)
      }
    };
  }, [volatility]);

  // Transform Internals data to component format
  const internalsFormatted = useMemo(() => {
    // Convert string values from API to numbers (API returns strings for breadth/internals)
    const b_total = parseInt(breadth?.total_stocks || 0, 10);
    const b_adv = parseInt(breadth?.advancing || 0, 10);
    const b_dec = parseInt(breadth?.declining || 0, 10);
    const b_unch = parseInt(breadth?.unchanged || 0, 10);
    const i_200 = parseInt(internals?.above_200_ma || 0, 10);

    // Calculate percentages safely
    const adv_pct = b_total > 0 ? (b_adv / b_total * 100).toFixed(1) : 0;
    const dec_pct = b_total > 0 ? (b_dec / b_total * 100).toFixed(1) : 0;
    const ma200_pct = b_total > 0 ? (i_200 / b_total * 100).toFixed(1) : 0;
    const da_ratio = b_dec > 0 ? (b_adv / b_dec).toFixed(2) : "N/A";

    return {
      data: {
        market_breadth: {
          advancing: b_adv,
          declining: b_dec,
          unchanged: b_unch,
          total_stocks: b_total,
          advancing_percent: adv_pct,
          decline_advance_ratio: da_ratio,
          avg_daily_change: null,  // Not available in API
          total_volume: null,       // Not available in API
          strong_up: null,          // Not available in API
          strong_down: null         // Not available in API
        },
        moving_average_analysis: {
          above_sma20: {
            count: null,            // Not available in API
            total: b_total,
            percent: null,          // Not available in API
            avg_distance_pct: null  // Not available in API
          },
          above_sma50: {
            count: null,            // Not available in API
            total: b_total,
            percent: null,          // Not available in API
            avg_distance_pct: null  // Not available in API
          },
          above_sma200: {
            count: i_200,
            total: b_total,
            percent: ma200_pct,
            avg_distance_pct: null  // Not available in API
          }
        },
        market_extremes: {
          current_breadth_percentile: null,  // Not available in API
          percentile_50: null,
          percentile_90: null,
          percentile_25: null,
          percentile_75: null,
          avg_breadth_30d: null,
          stddev_breadth_30d: null,
          stddev_from_mean: null,
          breadth_rank: null
        },
        overextension_indicator: {
          level: null,           // Not available in API
          signal: null,          // Not available in API
          breadth_score: null,   // Not available in API
          ma200_score: null,     // Not available in API
          composite_score: null  // Not available in API
        },
        positioning_metrics: {}
      }
    };
  }, [breadth, internals]);

  // NOW we can do early returns (after all hooks have been called)
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

  if (marketLoading) {
    return (
      <Box>
        <Typography variant="h4" sx={{ mb: 3, fontWeight: 600 }}>
          Market Overview
        </Typography>
        <CircularProgress />
      </Box>
    );
  }

  // Note: Top movers data not available in new 3-endpoint API structure
  // Would require separate /api/market/top-movers or /api/stocks/gainers endpoints

  // Data structure references
  const marketBreadth = breadth || {};
  // Note: Market cap not available in current API endpoints

  // Sentiment history from 3 separate fields
  const fearGreedHistory = sentData?.fear_greed || [];
  const naaimHistory = sentData?.naaim || [];
  const aaiiHistory = sentData?.aaii || [];

  console.log("✅ Data extraction:", {
    hasBreadth: !!breadth,
    hasFearGreed: fearGreedHistory.length,
    hasAAII: aaiiHistory.length,
    hasNAAIM: naaimHistory.length
  });

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
      // Fear & Greed from new endpoint uses: value, rating
      dateMap[date].fear_greed = item.value || item.index_value;
      dateMap[date].fear_greed_text = item.rating || item.value_text;
      dateMap[date].has_fear_greed = true;
    }
  });
  naaimHistory.forEach((item) => {
    const date = item.date || item.timestamp;
    if (!dateMap[date]) dateMap[date] = { date };
    // NAAIM from new endpoint uses: bullish_exposure, bearish_exposure
    dateMap[date].bullish_exposure = item.bullish_exposure || item.mean || null;
    dateMap[date].bearish_exposure = item.bearish_exposure || null;
    dateMap[date].naaim = item.mean || item.average;
    dateMap[date].has_naaim = true;
  });
  aaiiHistory.forEach((item) => {
    const date = item.date || item.timestamp;
    if (!dateMap[date]) dateMap[date] = { date };
    dateMap[date].bullish = item.bullish;
    dateMap[date].bearish = item.bearish;
    dateMap[date].neutral = item.neutral;
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

  // Get current AAII from the latest AAII sentiment data
  const latestAAII = (aaiiHistory && aaiiHistory.length > 0) ? aaiiHistory[0] : {};

  // Helper to calculate sentiment signal from AAII data
  const getSentimentSignal = (bullish, bearish) => {
    const diff = bullish - bearish;
    if (diff > 10) return { label: "Bullish", color: "success", icon: <TrendingUp /> };
    if (diff < -10) return { label: "Bearish", color: "error", icon: <TrendingDown /> };
    return { label: "Neutral", color: "warning", icon: <TrendingFlat /> };
  };

  // CRITICAL: Only calculate signal if real AAII data available
  // Do not synthesize signals from missing sentiment data
  const _aaiiSignal = (latestAAII.bullish !== null && latestAAII.bullish !== undefined &&
                       latestAAII.bearish !== null && latestAAII.bearish !== undefined)
    ? getSentimentSignal(latestAAII.bullish, latestAAII.bearish)
    : { label: "", color: "default", icon: <TrendingFlat />, unavailable: true };

  // --- Sentiment History Tab ---
  const SentimentHistoryPanel = () => (
    <Box>
      <Grid container spacing={3}>
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

              {marketLoading ? (
                <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", height: 400 }}>
                  <CircularProgress />
                </Box>
              ) : aaiiHistory && aaiiHistory.length > 0 && sentimentChartData.length > 0 ? (
                <Box sx={{ height: 400, width: "100%", minWidth: 0, minHeight: 0 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart
                      data={sentimentChartData}
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
                        domain={[0, 1]}
                        label={{
                          value: "Sentiment (0-1)",
                          angle: -90,
                          position: "insideLeft",
                        }}
                        tickFormatter={(value) => {
                          const num = typeof value === 'number' ? value : parseFloat(value) || 0;
                          return (num * 100).toFixed(0) + "%";
                        }}
                      />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: "rgba(0,0,0,0.8)",
                          border: "1px solid #ccc",
                          color: "#fff",
                          borderRadius: "4px",
                        }}
                        formatter={(value) => {
                          const parsed = parseFloat(value);
                          const num = isNaN(parsed) ? 0 : parsed;
                          return [`${(num * 100).toFixed(1)}%`, ""];
                        }}
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
                  AAII Sentiment Survey: Bullish/bearish sentiment data updated weekly
                  {aaiiHistory?.length && ` | Data points: ${aaiiHistory.length}`}
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

              {marketLoading ? (
                <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", height: 400 }}>
                  <CircularProgress />
                </Box>
              ) : fearGreedHistory && fearGreedHistory.length > 0 && sentimentChartData.length > 0 ? (
                <Box sx={{ height: 400, width: "100%", minWidth: 0, minHeight: 0 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart
                      data={sentimentChartData}
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
                        formatter={(value) => {
                          const parsed = parseFloat(value);
                          const num = isNaN(parsed) ? 0 : parsed;
                          return [`${num.toFixed(1)}`, ""];
                        }}
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
                        dataKey="fear_greed"
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
                  {fearGreedHistory?.length && ` | Data points: ${fearGreedHistory.length}`}
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

              {marketLoading ? (
                <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", height: 400 }}>
                  <CircularProgress />
                </Box>
              ) : naaimHistory && naaimHistory.length > 0 && sentimentChartData.length > 0 ? (
                <Box sx={{ height: 400, width: "100%", minWidth: 0, minHeight: 0 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart
                      data={sentimentChartData.map((d) => ({
                        ...d,
                        // Use real API values without transformation (NAAIM data is already percentage 0-100)
                        bullish_exposure: d.bullish_exposure !== null && d.bullish_exposure !== undefined ? d.bullish_exposure : null,
                        bearish_exposure: d.bearish_exposure !== null && d.bearish_exposure !== undefined ? d.bearish_exposure : null,
                      }))}
                      margin={{ top: 5, right: 30, left: 0, bottom: 5 }}
                    >
                      <defs>
                        <linearGradient id={bullishGradientId} x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                          <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                        </linearGradient>
                        <linearGradient id={bearishGradientId} x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#ef4444" stopOpacity={0.3} />
                          <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
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
                          value: "Manager Exposure (%)",
                          angle: -90,
                          position: "insideLeft",
                          offset: 10,
                        }}
                      />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: "rgba(0,0,0,0.9)",
                          border: "2px solid #10b981",
                          color: "#fff",
                          borderRadius: "6px",
                          padding: "8px 12px",
                        }}
                        formatter={(value, name) => {
                          const parsed = parseFloat(value);
                          const displayValue = isNaN(parsed) ? 0 : Math.abs(parsed);
                          return [`${displayValue.toFixed(1)}%`, name];
                        }}
                        labelFormatter={(date) => {
                          const d = new Date(date);
                          return d.toLocaleDateString("en-US", {
                            year: "numeric",
                            month: "short",
                            day: "numeric",
                          });
                        }}
                      />
                      <Legend
                        wrapperStyle={{ paddingTop: "16px" }}
                        iconType="line"
                      />
                      <Line
                        type="monotone"
                        dataKey="bullish_exposure"
                        stroke="#10b981"
                        strokeWidth={2.5}
                        dot={false}
                        fill={`url(#${bullishGradientId})`}
                        isAnimationActive={true}
                        name="Bullish Exposure"
                      />
                      <Line
                        type="monotone"
                        dataKey="bearish_exposure"
                        stroke="#ef4444"
                        strokeWidth={2.5}
                        dot={false}
                        fill={`url(#${bearishGradientId})`}
                        isAnimationActive={true}
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
                  NAAIM (National Association of Active Investment Managers) Manager Exposure Index: Bullish/bearish exposure levels
                  {naaimHistory?.length && ` | Data points: ${naaimHistory.length}`}
                </Typography>
                <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
                  Bullish = Long exposure | Bearish = Short exposure (displayed as absolute value)
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


      {/* Enhanced Market Indicators - Yield Curve, McClellan Oscillator, Sentiment Divergence */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        {/* McClellan Oscillator Chart */}
        <Grid item xs={12}>
          <McClellanOscillatorChart
            data={mcclellanOscillator}
            isLoading={marketLoading}
          />
        </Grid>
      </Grid>

      {/* Market Exposure Recommendation */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={12} md={6}>
          <MarketExposure
            marketData={{ data: { indices: [] } }}
            breadthData={{ data: breadth }}
            distributionDaysData={distributionDays}
          />
        </Grid>
      </Grid>

      {/* Top Movers Section - Not available in current API structure */}
      {/* To enable: Need to implement /api/market/top-movers or /api/stocks/gainers endpoint */}

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
                        : ""}
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
                        : ""}
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
                        : ""}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      Average Change:{" "}
                      {marketBreadth.average_change_percent !== undefined && marketBreadth.average_change_percent !== null
                        ? (() => {
                            const parsed = parseFloat(marketBreadth.average_change_percent);
                            return isNaN(parsed) ? "N/A" : parsed.toFixed(2) + "%";
                          })()
                        : ""}
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
                    : ""}
                </Typography>
              </Box>
              <Box
                sx={{ display: "flex", justifyContent: "space-between", mb: 2 }}
              >
                <Typography variant="body2">Unchanged:</Typography>
                <Typography variant="body2" fontWeight="600">
                  {marketBreadth.unchanged !== undefined
                    ? parseInt(marketBreadth.unchanged).toLocaleString()
                    : ""}
                </Typography>
              </Box>
            </CardContent>
          </Card>
        </Grid>
        {/* Market Cap Distribution - Not available in current API */}

        {/* Distribution Days Card - IBD Methodology */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                Distribution Days
              </Typography>
              {marketLoading ? (
                <CircularProgress size={24} />
              ) : (
                <>
                  {Object.entries(distributionDays).length > 0 ? (
                    <>
                      {Object.entries(distributionDays).map(([symbol, data]) => {
                        // Skip if data is null
                        if (!data) return null;

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

      {/* Market Internals Section - Above Tabs */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h5" sx={{ mb: 3, fontWeight: 600 }}>
          Market Internals
        </Typography>
        {marketLoading ? (
          <LinearProgress />
        ) : (
          <MarketInternals
            data={internalsFormatted}
            isLoading={marketLoading}
            error={null}
          />
        )}
      </Box>

      {/* Market Volatility Section */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h5" sx={{ mb: 3, fontWeight: 600 }}>
          Market Volatility
        </Typography>
        {marketLoading ? (
          <LinearProgress />
        ) : (
          <MarketVolatility
            data={volatilityFormatted}
            isLoading={marketLoading}
            error={null}
          />
        )}
      </Box>

      {/* Market Correlation Section */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h5" sx={{ mb: 3, fontWeight: 600 }}>
          Asset Correlations
        </Typography>
        {correlationLoading ? (
          <LinearProgress />
        ) : (
          <MarketCorrelation
            data={correlationData}
            isLoading={correlationLoading}
            error={null}
          />
        )}
      </Box>

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
            </Tabs>
        </Box>

        {tabsReady && (
          <>
        <TabPanel value={tabValue} index={0}>
          {marketLoading ? (
            <LinearProgress />
          ) : (
            <SentimentHistoryPanel />
          )}
        </TabPanel>

        {/* Seasonality Section - Moved from tab to main page */}
        <Box sx={{ mt: 6 }}>
          <Typography variant="h5" sx={{ mb: 3, fontWeight: 600 }}>
            Market Seasonality
          </Typography>
          {marketLoading ? (
            <LinearProgress />
          ) : (
            <Grid container spacing={3}>
              {seasonality?.data && (
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
                                  seasonality?.data?.currentPosition
                                    ?.seasonalScore
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
                                  seasonality?.data?.summary
                                    ?.overallSeasonalBias
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
                                  seasonality?.data?.currentPosition
                                    ?.presidentialCycle
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
                                  seasonality?.data?.currentPosition
                                    ?.nextMajorEvent?.name
                                }
                              </Typography>
                              <Typography
                                variant="body2"
                                color="warning.contrastText"
                              >
                                Next Event (
                                {
                                  seasonality?.data?.currentPosition
                                    ?.nextMajorEvent?.daysAway
                                }{" "}
                                days)
                              </Typography>
                            </Box>
                          </Grid>
                        </Grid>
                        <Box sx={{ mt: 3 }}>
                          <Typography variant="body1" sx={{ mb: 1 }}>
                            <strong>Recommendation:</strong>{" "}
                            {seasonality?.data?.summary?.recommendation}
                          </Typography>
                          <Typography variant="body2" color="text.secondary">
                            Active Periods:{" "}
                            {seasonality?.data?.currentPosition?.activePeriods?.join(
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
                              data={seasonality?.data?.monthlySeasonality}
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
                                formatter={(value) => {
                                  const num = value !== null && value !== undefined ? (typeof value === 'number' ? value : parseFloat(value) || 0) : 0;
                                  return [`${isNaN(num) ? '0.0' : num.toFixed(1)}%`, "Average Return"];
                                }}
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
                              data={seasonality?.data?.quarterlySeasonality}
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
                                formatter={(value, _name, _props) => {
                                  const num = value !== null && value !== undefined ? (typeof value === 'number' ? value : parseFloat(value) || 0) : 0;
                                  return [`${isNaN(num) ? '0.0' : num.toFixed(1)}%`, "Average Return"];
                                }}
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
                              data={seasonality?.data?.presidentialCycle?.data || []}
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
                                formatter={(value) => {
                                  const num = value !== null && value !== undefined ? (typeof value === 'number' ? value : parseFloat(value) || 0) : 0;
                                  return [`${isNaN(num) ? '0.00' : num.toFixed(2)}%`, "Average Return"];
                                }}
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
                              data={seasonality?.data?.monthlySeasonality || []}
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
                                  const num = value !== null && value !== undefined ? (typeof value === 'number' ? value : parseFloat(value) || 0) : 0;
                                  const formatted = isNaN(num) ? '0.00' : num.toFixed(2);
                                  if (name === "Monthly Avg Return") {
                                    return [`${formatted}%`, name];
                                  }
                                  return [`${formatted}%`, name];
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
                                {(seasonality?.data?.monthlySeasonality || []).map((entry, index) => (
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
                        {(seasonality?.data?.dayOfWeekEffects || []).map(
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
                          {(seasonality?.data?.seasonalAnomalies || []).map(
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
                              {(seasonality?.data?.holidayEffects || []).map(
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
                        <SectorSeasonalityTable data={seasonality?.data?.sectorSeasonality || []} />
                      </CardContent>
                    </Card>
                  </Grid>

                </>
              )}
            </Grid>
          )}
        </Box>

          </>
        )}
      </Box>
    </Box>
  );
}

export default MarketOverview;
