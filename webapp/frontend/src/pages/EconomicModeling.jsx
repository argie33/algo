import { useState, useEffect } from "react";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CardHeader,
  Chip,
  Container,
  Divider,
  Grid,
  IconButton,
  LinearProgress,
  Typography,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  useTheme,
} from "@mui/material";
import {
  TrendingUp,
  TrendingDown,
  Refresh,
  TrendingFlat,
} from "@mui/icons-material";
import { api } from "../services/api";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  ReferenceLine,
  Area,
  AreaChart,
} from "recharts";


// Safe formatting helpers
const formatPercent = (value, fallback = "N/A") => {
  if (value === null || value === undefined || isNaN(value)) return fallback;
  return Number(value).toFixed(1);
};

const formatBasisPoints = (value, fallback = "N/A") => {
  if (value === null || value === undefined || isNaN(value)) return fallback;
  return Math.round(Number(value));
};

const getRiskColor = (riskLevel) => {
  if (!riskLevel) return "default";
  switch (riskLevel.toLowerCase()) {
    case "high":
      return "error";
    case "medium":
      return "warning";
    case "low":
      return "success";
    default:
      return "default";
  }
};

// Subtle dot component for charts
const SubtleDot = (props, theme, color) => {
  const { cx, cy } = props;
  if (cx === undefined || cy === undefined) return null;

  return (
    <circle
      cx={cx}
      cy={cy}
      r={2.5}
      fill={color}
      stroke="white"
      strokeWidth={1}
      opacity={0.8}
    />
  );
};

// Subtle dot for yield curve
const SubtleYieldDot = (props, theme, color) => {
  const { cx, cy } = props;
  if (cx === undefined || cy === undefined) return null;

  return (
    <circle
      cx={cx}
      cy={cy}
      r={3}
      fill={color}
      stroke="white"
      strokeWidth={1}
      opacity={0.85}
    />
  );
};

const EconomicModeling = () => {
  const theme = useTheme();
  const [economicData, setEconomicData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  // Fetch all economic data from backend
  const fetchEconomicData = async () => {
    try {
      setLoading(true);
      setError(null);

      // Use Promise.allSettled to handle partial failures gracefully
      const results = await Promise.allSettled([
        api.get("/api/market/recession-forecast"),
        api.get("/api/market/leading-indicators"),
        api.get("/api/market/sectoral-analysis"),
        api.get("/api/market/credit-spreads"),
        api.get("/api/market/calendar"), // Economic calendar
      ]);

      // Extract successful responses
      const [
        recessionForecast,
        leadingIndicators,
        _sectoralAnalysis,
        creditSpreads,
        calendar,
      ] = results.map((result) => (result.status === "fulfilled" ? result.value : null));

      // Check for missing data errors (503 responses)
      const missingDataErrors = results
        .filter((r) => r.status === "fulfilled" && r.value?.status === 503)
        .map((r) => r.value?.data?.missing || [])
        .flat();

      if (missingDataErrors.length > 0 || results.some((r) => r.status === "rejected")) {
        console.warn("⚠️ Some economic data endpoints unavailable:", {
          missing: missingDataErrors,
          rejected: results.filter((r) => r.status === "rejected").length,
        });

        const errorMsg =
          missingDataErrors.length > 0
            ? `Missing economic data: ${missingDataErrors.join(", ")}. Please run loadecondata.py to load FRED data.`
            : "Some economic data endpoints are unavailable. Please try again later.";

        setError(errorMsg);
        setEconomicData(null);
        setLoading(false);
        setRefreshing(false);
        return;
      }

      // Extract data from API responses
      const leadingData = leadingIndicators?.data?.data || {};
      const recessionData = recessionForecast?.data?.data || {};
      const creditData = creditSpreads?.data?.data || {};
      const calendarData = calendar?.data?.data || {};

      console.log("✅ Economic data loaded:", {
        recession: recessionData.compositeRecessionProbability,
        indicators: leadingData.indicators?.length,
        creditStress: creditData.creditStressIndex,
        events: leadingData.upcomingEvents?.length,
      });

      const combinedData = {
        // Recession data
        recessionProbability: recessionData.compositeRecessionProbability || 0,
        riskLevel: recessionData.riskLevel || "Medium",
        riskIndicator: recessionData.riskIndicator || "🟢",
        economicStressIndex: recessionData.economicStressIndex || 0,
        forecastModels: recessionData.forecastModels || [],
        recessionAnalysis: recessionData.analysis || {},
        keyRecessionIndicators: recessionData.keyIndicators || {},

        // Leading indicators
        leadingIndicators: leadingData.indicators || [],
        gdpGrowth: leadingData.gdpGrowth || 0,
        unemployment: leadingData.unemployment || 0,
        inflation: leadingData.inflation || 0,
        employment: leadingData.employment || {},

        // Yield curve
        yieldCurve: leadingData.yieldCurve || {},
        yieldCurveData: leadingData.yieldCurveData || [],

        // Credit spreads
        creditSpreads: creditData.spreads || {},
        creditStressIndex: creditData.creditStressIndex || 0,
        financialConditionsIndex: creditData.financialConditionsIndex || {},

        // Calendar
        upcomingEvents: calendarData.upcomingEvents || calendarData.events || [],
      };

      setEconomicData(combinedData);
    } catch (err) {
      console.error("Failed to fetch economic data:", err);
      setError(err.message || "Failed to load economic data. Please try again.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchEconomicData();
  }, []);

  const handleRefresh = async () => {
    setRefreshing(true);
    await fetchEconomicData();
  };

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      {/* Header */}
      <Box display="flex" alignItems="center" justifyContent="space-between" mb={4}>
        <Box>
          <Typography variant="h3" component="h1" gutterBottom>
            🌍 Economic Indicators Dashboard
          </Typography>
          <Typography variant="body1" color="text.secondary">
            Real-time recession probability, credit spreads, and economic health analysis
          </Typography>
        </Box>
        <IconButton onClick={handleRefresh} disabled={refreshing}>
          <Refresh sx={{ animation: refreshing ? "spin 1s linear infinite" : "none" }} />
        </IconButton>
      </Box>

      {/* Loading State */}
      {loading && (
        <Box sx={{ mb: 3 }}>
          <LinearProgress />
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1, textAlign: "center" }}>
            Loading economic data...
          </Typography>
        </Box>
      )}

      {/* Error State */}
      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          <strong>Error:</strong> {error}
          <Button color="inherit" size="small" onClick={handleRefresh} sx={{ ml: 2 }}>
            Retry
          </Button>
        </Alert>
      )}

      {/* Critical Alert if recession probability high */}
      {!loading && economicData && economicData.recessionProbability > 40 && (
        <Alert severity="warning" sx={{ mb: 3 }}>
          <strong>⚠️ Elevated Recession Risk:</strong> {economicData.recessionProbability}%
          probability. Multiple economic warning signals detected. Monitor market conditions closely.
        </Alert>
      )}

      {/* Key Metrics Summary */}
      {!loading && economicData && (
        <>
          <Grid container spacing={3} sx={{ mb: 4 }}>
            <Grid item xs={12} md={3}>
              <Card>
                <CardContent>
                  <Typography variant="subtitle2" color="text.secondary">
                    Recession Probability
                  </Typography>
                  <Typography
                    variant="h3"
                    sx={{
                      color:
                        economicData.recessionProbability > 60
                          ? "error.main"
                          : economicData.recessionProbability > 35
                            ? "warning.main"
                            : "success.main",
                    }}
                  >
                    {economicData.recessionProbability}%
                  </Typography>
                  <LinearProgress
                    variant="determinate"
                    value={economicData.recessionProbability}
                    color={
                      economicData.recessionProbability > 60
                        ? "error"
                        : economicData.recessionProbability > 35
                          ? "warning"
                          : "success"
                    }
                    sx={{ mt: 2 }}
                  />
                </CardContent>
              </Card>
            </Grid>

            <Grid item xs={12} md={3}>
              <Card>
                <CardContent>
                  <Typography variant="subtitle2" color="text.secondary">
                    Economic Stress Index
                  </Typography>
                  <Typography
                    variant="h3"
                    sx={{
                      color:
                        economicData.economicStressIndex > 60
                          ? "error.main"
                          : economicData.economicStressIndex > 30
                            ? "warning.main"
                            : "success.main",
                    }}
                  >
                    {economicData.economicStressIndex}
                  </Typography>
                  <LinearProgress
                    variant="determinate"
                    value={economicData.economicStressIndex}
                    color={
                      economicData.economicStressIndex > 60
                        ? "error"
                        : economicData.economicStressIndex > 30
                          ? "warning"
                          : "success"
                    }
                    sx={{ mt: 2 }}
                  />
                </CardContent>
              </Card>
            </Grid>

            <Grid item xs={12} md={3}>
              <Card>
                <CardContent>
                  <Typography variant="subtitle2" color="text.secondary">
                    Credit Stress Index
                  </Typography>
                  <Typography
                    variant="h3"
                    sx={{
                      color:
                        economicData.creditStressIndex > 50
                          ? "error.main"
                          : economicData.creditStressIndex > 30
                            ? "warning.main"
                            : "success.main",
                    }}
                  >
                    {economicData.creditStressIndex}
                  </Typography>
                  <LinearProgress
                    variant="determinate"
                    value={economicData.creditStressIndex}
                    color={
                      economicData.creditStressIndex > 50
                        ? "error"
                        : economicData.creditStressIndex > 30
                          ? "warning"
                          : "success"
                    }
                    sx={{ mt: 2 }}
                  />
                </CardContent>
              </Card>
            </Grid>

            <Grid item xs={12} md={3}>
              <Card>
                <CardContent>
                  <Box display="flex" alignItems="center" justifyContent="space-between">
                    <Box>
                      <Typography variant="subtitle2" color="text.secondary">
                        Unemployment
                      </Typography>
                      <Typography variant="h4">
                        {formatPercent(economicData.unemployment)}%
                      </Typography>
                    </Box>
                    {economicData.unemployment < 4.5 ? (
                      <TrendingUp color="success" sx={{ fontSize: 40 }} />
                    ) : economicData.unemployment > 5 ? (
                      <TrendingDown color="error" sx={{ fontSize: 40 }} />
                    ) : (
                      <TrendingFlat color="warning" sx={{ fontSize: 40 }} />
                    )}
                  </Box>
                </CardContent>
              </Card>
            </Grid>
          </Grid>

          {/* SECTION: Recession Model */}
          <Box sx={{ mt: 6, mb: 4 }}>
            <Typography variant="h4" sx={{ fontWeight: 600, mb: 3, display: "flex", alignItems: "center", gap: 1 }}>
              📊 Recession Model
            </Typography>
            <Grid container spacing={3}>
              <Grid item xs={12} md={8}>
                <Card>
                  <CardHeader
                    title="Advanced Recession Probability Model"
                    subheader="Multi-factor analysis: Yield Curve (35%), Credit Spreads (25%), Labor Market (20%), Monetary Policy (15%), Volatility (5%)"
                    action={
                      <Chip
                        label={`${economicData.riskLevel} Risk`}
                        color={getRiskColor(economicData.riskLevel)}
                      />
                    }
                  />
                  <CardContent>
                    <Typography variant="h3" color="primary" gutterBottom>
                      {economicData.riskIndicator} {economicData.recessionProbability}% Probability
                    </Typography>
                    <LinearProgress
                      variant="determinate"
                      value={economicData.recessionProbability}
                      color={
                        economicData.recessionProbability > 60
                          ? "error"
                          : economicData.recessionProbability > 35
                            ? "warning"
                            : "success"
                      }
                      sx={{ mb: 3, height: 12 }}
                    />
                    <Typography variant="body1" paragraph>
                      {economicData.recessionAnalysis?.summary}
                    </Typography>
                    <Divider sx={{ my: 2 }} />
                    <Typography variant="h6" gutterBottom>
                      📊 Model Factors
                    </Typography>
                    <Box sx={{ mb: 2 }}>
                      {economicData.recessionAnalysis?.factors?.map((factor, idx) => (
                        <Typography key={idx} variant="body2" sx={{ mb: 1 }}>
                          {factor}
                        </Typography>
                      ))}
                    </Box>
                  </CardContent>
                </Card>
              </Grid>

              <Grid item xs={12} md={4}>
                <Grid container spacing={2}>
                  <Grid item xs={12}>
                    <Card>
                      <CardHeader title="Forecast Models" titleTypographyProps={{ variant: "h6" }} />
                      <CardContent>
                        {economicData.forecastModels?.map((model, idx) => (
                          <Box key={idx} mb={2}>
                            <Box display="flex" justifyContent="space-between" mb={1}>
                              <Typography variant="body2">{model.name}</Typography>
                              <Typography variant="body2" fontWeight="bold">
                                {model.probability}%
                              </Typography>
                            </Box>
                            <LinearProgress variant="determinate" value={model.probability} />
                            <Typography variant="caption" color="text.secondary">
                              Confidence: {model.confidence}%
                            </Typography>
                          </Box>
                        ))}
                      </CardContent>
                    </Card>
                  </Grid>
                  <Grid item xs={12}>
                    <Card>
                      <CardHeader title="Key Indicators" titleTypographyProps={{ variant: "h6" }} />
                      <CardContent>
                        <Typography variant="body2">
                          <strong>Yield Curve (2y10y):</strong> {formatBasisPoints(economicData.keyRecessionIndicators?.yieldCurveSpread2y10y)} bps
                        </Typography>
                        <Typography variant="body2">
                          <strong>HY Spread:</strong> {formatBasisPoints(economicData.keyRecessionIndicators?.highYieldSpread)} bps
                        </Typography>
                        <Typography variant="body2">
                          <strong>IG Spread:</strong> {formatBasisPoints(economicData.keyRecessionIndicators?.investmentGradeSpread)} bps
                        </Typography>
                        <Typography variant="body2">
                          <strong>Fed Rate:</strong> {formatPercent(economicData.keyRecessionIndicators?.fedFundsRate)}%
                        </Typography>
                        <Typography variant="body2">
                          <strong>VIX:</strong> {formatPercent(economicData.keyRecessionIndicators?.vix)}
                        </Typography>
                      </CardContent>
                    </Card>
                  </Grid>
                </Grid>
              </Grid>
            </Grid>
          </Box>

          {/* SECTION: Leading Indicators */}
          <Box sx={{ mt: 6, mb: 4 }}>
            <Card>
              <CardHeader
                title="Leading Economic Indicators"
                subheader="Real-time economic momentum analysis"
                action={
                  <Chip
                    label={`${economicData.leadingIndicators?.length || 0} indicators`}
                    color="primary"
                    variant="outlined"
                  />
                }
              />
              <CardContent>
                <Grid container spacing={3}>
                  {economicData.leadingIndicators?.map((indicator, idx) => (
                    <Grid item xs={12} md={6} key={idx}>
                      <Card variant="outlined">
                        <CardContent>
                          {/* Header: Icon + Name + Signal */}
                          <Box display="flex" alignItems="center" justifyContent="space-between" mb={2}>
                            <Box display="flex" alignItems="center" gap={1}>
                              {indicator.trend === "up" ? (
                                <TrendingUp sx={{ color: "success.main", fontSize: 24 }} />
                              ) : indicator.trend === "down" ? (
                                <TrendingDown sx={{ color: "error.main", fontSize: 24 }} />
                              ) : (
                                <TrendingFlat sx={{ color: "warning.main", fontSize: 24 }} />
                              )}
                              <Typography variant="h6">{indicator.name}</Typography>
                            </Box>
                            <Chip
                              label={indicator.signal}
                              color={
                                indicator.signal === "Positive"
                                  ? "success"
                                  : indicator.signal === "Negative"
                                    ? "error"
                                    : "default"
                              }
                              size="small"
                            />
                          </Box>

                          {/* Value + Change */}
                          <Box display="flex" alignItems="center" justifyContent="space-between" mb={2}>
                            <Typography variant="h4" color="primary">
                              {indicator.value}
                            </Typography>
                            <Typography
                              variant="body2"
                              sx={{
                                fontWeight: "bold",
                                color:
                                  indicator.change > 0
                                    ? "success.main"
                                    : indicator.change < 0
                                      ? "error.main"
                                      : "text.secondary",
                              }}
                            >
                              {indicator.change > 0 ? "+" : ""}
                              {Math.abs(indicator.change)}%
                            </Typography>
                          </Box>

                          {/* Description */}
                          <Typography variant="body2" color="text.secondary" mb={2}>
                            {indicator.description}
                          </Typography>

                          {/* Chart: Sparkline for most indicators, Full chart for GDP quarterly data */}
                          {indicator.history && indicator.history.length > 1 && (
                            <ResponsiveContainer
                              width="100%"
                              height={indicator.name === "GDP Growth" ? 280 : 120}
                            >
                              <AreaChart
                                data={indicator.history}
                                margin={indicator.name === "GDP Growth" ? { top: 10, right: 30, bottom: 30, left: 60 } : { top: 5, right: 15, bottom: 5, left: 50 }}
                              >
                                <defs>
                                  <linearGradient id={`grad-${indicator.name}`} x1="0" y1="0" x2="0" y2="1">
                                    <stop
                                      offset="0%"
                                      stopColor={
                                        indicator.signal === "Positive"
                                          ? theme.palette.success.main
                                          : indicator.signal === "Negative"
                                            ? theme.palette.error.main
                                            : theme.palette.warning.main
                                      }
                                      stopOpacity={0.12}
                                    />
                                    <stop
                                      offset="100%"
                                      stopColor={
                                        indicator.signal === "Positive"
                                          ? theme.palette.success.main
                                          : indicator.signal === "Negative"
                                            ? theme.palette.error.main
                                            : theme.palette.warning.main
                                      }
                                      stopOpacity={0}
                                    />
                                  </linearGradient>
                                </defs>
                                <XAxis
                                  dataKey="date"
                                  hide={indicator.name !== "GDP Growth"}
                                  tick={{ fontSize: 11, fill: "#666" }}
                                  angle={indicator.name === "GDP Growth" ? -45 : 0}
                                  textAnchor={indicator.name === "GDP Growth" ? "end" : "middle"}
                                  height={indicator.name === "GDP Growth" ? 60 : 30}
                                  tickFormatter={(date) => {
                                    if (indicator.name === "GDP Growth") {
                                      const d = new Date(date);
                                      return `${d.getFullYear()}-Q${Math.floor(d.getMonth() / 3) + 1}`;
                                    }
                                    return "";
                                  }}
                                />
                                <YAxis hide />
                                <Tooltip
                                  formatter={(value) => {
                                    if (indicator.name === "GDP Growth") {
                                      return [
                                        `$${(value / 1000).toFixed(2)}T`,
                                        "GDP (Billions)"
                                      ];
                                    }
                                    return [formatPercent(value, "N/A"), "Value"];
                                  }}
                                  labelFormatter={(label) => {
                                    if (indicator.name === "GDP Growth") {
                                      const d = new Date(label);
                                      return `${d.getFullYear()}-Q${Math.floor(d.getMonth() / 3) + 1}`;
                                    }
                                    return new Date(label).toLocaleDateString();
                                  }}
                                  contentStyle={{
                                    backgroundColor: "rgba(255,255,255,0.97)",
                                    border: "1px solid rgba(0,0,0,0.15)",
                                    borderRadius: "6px",
                                    boxShadow: "0 2px 8px rgba(0,0,0,0.12)"
                                  }}
                                  cursor={{ fill: "rgba(0,0,0,0.05)" }}
                                />
                                <Area
                                  type="monotone"
                                  dataKey="value"
                                  stroke={
                                    indicator.signal === "Positive"
                                      ? theme.palette.success.main
                                      : indicator.signal === "Negative"
                                        ? theme.palette.error.main
                                        : theme.palette.warning.main
                                  }
                                  strokeWidth={2}
                                  fill={`url(#grad-${indicator.name})`}
                                  dot={(props) => SubtleDot(props, theme, indicator.signal === "Positive" ? theme.palette.success.main : indicator.signal === "Negative" ? theme.palette.error.main : theme.palette.warning.main)}
                                  isAnimationActive={true}
                                />
                              </AreaChart>
                            </ResponsiveContainer>
                          )}

                          {/* Axis Summary - Show value range and trend */}
                          {indicator.history && indicator.history.length > 0 && (() => {
                            const values = indicator.history
                              .map(h => h.value)
                              .filter(v => v !== null && !isNaN(v));
                            if (values.length === 0) return null;

                            const minVal = Math.min(...values);
                            const maxVal = Math.max(...values);
                            const currentVal = indicator.rawValue || indicator.value;
                            const isUp = indicator.history[0]?.value > indicator.history[indicator.history.length - 1]?.value;

                            // Get the unit and formatter
                            const getUnit = () => {
                              if (indicator.unit) return indicator.unit;
                              if (indicator.name.includes("GDP")) return "Billions $";
                              if (indicator.name.includes("%") || indicator.name.includes("Rate")) return "%";
                              if (indicator.name.includes("Payroll") || indicator.name.includes("Housing") || indicator.name.includes("Jobless")) return "Thousands";
                              return "Index";
                            };

                            const formatValue = (val, unit) => {
                              if (!val && val !== 0) return "N/A";
                              if (unit === "%") return `${Number(val).toFixed(2)}%`;
                              if (unit === "Billions $") return `$${Number(val).toFixed(0)}B`;
                              if (unit === "Thousands") return `${(Number(val) / 1000).toFixed(1)}K`;
                              return Number(val).toFixed(2);
                            };

                            const unit = getUnit();

                            return (
                              <Box sx={{ mt: 3, p: 2, backgroundColor: "rgba(0,0,0,0.02)", borderRadius: 1 }}>
                                <Grid container spacing={2}>
                                  <Grid item xs={6} sm={3}>
                                    <Typography variant="caption" color="text.secondary" display="block">
                                      Current
                                    </Typography>
                                    <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                                      {formatValue(currentVal, unit)}
                                    </Typography>
                                  </Grid>
                                  <Grid item xs={6} sm={3}>
                                    <Typography variant="caption" color="text.secondary" display="block">
                                      Min
                                    </Typography>
                                    <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                                      {formatValue(minVal, unit)}
                                    </Typography>
                                  </Grid>
                                  <Grid item xs={6} sm={3}>
                                    <Typography variant="caption" color="text.secondary" display="block">
                                      Max
                                    </Typography>
                                    <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                                      {formatValue(maxVal, unit)}
                                    </Typography>
                                  </Grid>
                                  <Grid item xs={6} sm={3}>
                                    <Typography variant="caption" color="text.secondary" display="block">
                                      Trend
                                    </Typography>
                                    <Typography variant="subtitle2" sx={{ fontWeight: 600, color: isUp ? theme.palette.success.main : theme.palette.error.main }}>
                                      {isUp ? "📈 Up" : "📉 Down"}
                                    </Typography>
                                  </Grid>
                                </Grid>
                              </Box>
                            );
                          })()}

                          {/* Last Updated & Data Frequency */}
                          {indicator.date && (
                            <>
                              <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 2 }}>
                                Last updated: {new Date(indicator.date).toLocaleDateString()}
                              </Typography>
                              {indicator.name === "GDP Growth" && (
                                <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
                                  📊 {indicator.history?.length || 0} quarterly data points ({((indicator.history?.length || 0) / 4).toFixed(1)} years)
                                </Typography>
                              )}
                            </>
                          )}
                        </CardContent>
                      </Card>
                    </Grid>
                  ))}

                  <Grid item xs={12}>
                    <Card>
                      <CardHeader title="📅 Upcoming Economic Events" />
                      <CardContent>
                        <TableContainer>
                          <Table>
                            <TableHead>
                              <TableRow>
                                <TableCell>Date</TableCell>
                                <TableCell>Event</TableCell>
                                <TableCell>Category</TableCell>
                                <TableCell>Importance</TableCell>
                                <TableCell>Forecast</TableCell>
                                <TableCell>Previous</TableCell>
                              </TableRow>
                            </TableHead>
                            <TableBody>
                              {economicData.upcomingEvents?.length > 0 ? (
                                economicData.upcomingEvents.map((event, idx) => (
                                  <TableRow key={idx}>
                                    <TableCell>{event.date}</TableCell>
                                    <TableCell>{event.event}</TableCell>
                                    <TableCell>{event.category}</TableCell>
                                    <TableCell>
                                      <Chip
                                        label={event.importance}
                                        color={
                                          event.importance === "high"
                                            ? "error"
                                            : event.importance === "medium"
                                              ? "warning"
                                              : "default"
                                        }
                                        size="small"
                                      />
                                    </TableCell>
                                    <TableCell>{event.forecast}</TableCell>
                                    <TableCell>{event.previous}</TableCell>
                                  </TableRow>
                                ))
                              ) : (
                                <TableRow>
                                  <TableCell colSpan={6} align="center">
                                    No upcoming events
                                  </TableCell>
                                </TableRow>
                              )}
                            </TableBody>
                          </Table>
                        </TableContainer>
                      </CardContent>
                    </Card>
                  </Grid>
                </Grid>
              </CardContent>
            </Card>
          </Box>

          {/* SECTION: Yield Curve */}
          <Box sx={{ mt: 6, mb: 4 }}>
            <Typography variant="h4" sx={{ fontWeight: 600, mb: 3, display: "flex", alignItems: "center", gap: 1 }}>
              📊 Yield Curve Analysis
            </Typography>
            <Grid container spacing={3}>
              <Grid item xs={12}>
                <Card>
                  <CardHeader
                    title="Treasury Yield Curve"
                    subheader={
                      economicData.yieldCurve?.isInverted
                        ? "🔴 INVERTED - Recession signal detected"
                        : "🟢 NORMAL - Healthy economic conditions"
                    }
                  />
                  <CardContent>
                    {economicData.yieldCurveData?.length > 0 ? (
                      <ResponsiveContainer width="100%" height={500}>
                        <AreaChart data={economicData.yieldCurveData} margin={{ top: 10, right: 30, left: 0, bottom: 40 }}>
                          <defs>
                            <linearGradient id="yieldGradient" x1="0" y1="0" x2="0" y2="1">
                              <stop offset="0%" stopColor="#1976d2" stopOpacity={0.35}/>
                              <stop offset="100%" stopColor="#1976d2" stopOpacity={0.02}/>
                            </linearGradient>
                          </defs>
                          <XAxis
                            dataKey="maturity"
                            tick={{ fontSize: 12, fill: "#666" }}
                            label={{ value: "Maturity (3M → 30Y)", position: "insideBottomRight", offset: -10, fontSize: 13, fontWeight: 500 }}
                            angle={-45}
                            textAnchor="end"
                            height={80}
                          />
                          <YAxis
                            tick={{ fontSize: 12, fill: "#666" }}
                            label={{ value: "Yield (%)", angle: -90, position: "insideLeft", offset: 10, fontSize: 13, fontWeight: 500 }}
                            width={60}
                            domain={[0, 'auto']}
                          />
                          <Tooltip
                            formatter={(value) => {
                              const numVal = parseFloat(value);
                              return [`${numVal?.toFixed(3) || 0}%`, "Yield"];
                            }}
                            contentStyle={{
                              backgroundColor: "rgba(255,255,255,0.99)",
                              border: "1px solid rgba(0,0,0,0.2)",
                              borderRadius: "8px",
                              boxShadow: "0 4px 12px rgba(0,0,0,0.15)",
                              padding: "12px 14px",
                              fontSize: 13
                            }}
                            labelFormatter={(value) => `Maturity: ${value}`}
                            cursor={{ fill: "rgba(25, 118, 210, 0.1)" }}
                          />
                          <ReferenceLine
                            y={0}
                            stroke="rgba(200,0,0,0.3)"
                            strokeDasharray="4 4"
                            opacity={0.6}
                            label={{ value: "Zero Yield", position: "insideTopRight", offset: -5, fill: "#c00", fontSize: 11 }}
                          />
                          {/* Reference line for 2% (typical neutral rate) */}
                          <ReferenceLine
                            y={2}
                            stroke="rgba(100,150,200,0.3)"
                            strokeDasharray="4 4"
                            opacity={0.5}
                            label={{ value: "2% Level", position: "insideTopRight", offset: -20, fill: "#666", fontSize: 11 }}
                          />
                          <Area
                            type="monotone"
                            dataKey="yield"
                            stroke="#1976d2"
                            strokeWidth={3.5}
                            fill="url(#yieldGradient)"
                            dot={(props) => SubtleYieldDot(props, theme, "#1976d2")}
                            isAnimationActive={true}
                            name="Yield Curve"
                          />
                        </AreaChart>
                      </ResponsiveContainer>
                    ) : (
                      <Alert severity="warning">No yield curve data available</Alert>
                    )}
                  </CardContent>
                </Card>
              </Grid>

              <Grid item xs={12}>
                <Card>
                  <CardHeader
                    title="Yield Curve Summary"
                    subheader={`Updated: ${economicData.yieldCurve ? "Today" : "N/A"}`}
                  />
                  <CardContent>
                    <Grid container spacing={3}>
                      {/* Status and Interpretation */}
                      <Grid item xs={12} md={6}>
                        <Box sx={{ mb: 2 }}>
                          <Typography variant="subtitle2" color="textSecondary" sx={{ mb: 1, fontWeight: 600 }}>
                            Current Status
                          </Typography>
                          <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, mb: 2 }}>
                            {economicData.yieldCurve?.isInverted ? (
                              <>
                                <Box sx={{ fontSize: 28 }}>🔴</Box>
                                <Box>
                                  <Typography variant="h6" sx={{ color: "error.main", fontWeight: 600 }}>
                                    INVERTED CURVE
                                  </Typography>
                                  <Typography variant="body2" color="error">
                                    Historically precedes recession by ~{economicData.yieldCurve?.averageLeadTime || 12} months
                                  </Typography>
                                </Box>
                              </>
                            ) : (
                              <>
                                <Box sx={{ fontSize: 28 }}>🟢</Box>
                                <Box>
                                  <Typography variant="h6" sx={{ color: "success.main", fontWeight: 600 }}>
                                    NORMAL CURVE
                                  </Typography>
                                  <Typography variant="body2" color="success">
                                    Indicates healthy economic conditions
                                  </Typography>
                                </Box>
                              </>
                            )}
                          </Box>
                        </Box>

                        <Divider sx={{ my: 2 }} />

                        <Typography variant="body2" sx={{ lineHeight: 1.7 }}>
                          <strong>Interpretation:</strong> {economicData.yieldCurve?.interpretation}
                        </Typography>
                      </Grid>

                      {/* Key Metrics */}
                      <Grid item xs={12} md={6}>
                        <Box sx={{ mb: 2 }}>
                          <Typography variant="subtitle2" color="textSecondary" sx={{ mb: 2, fontWeight: 600 }}>
                            Key Spreads & Metrics
                          </Typography>

                          <Box sx={{ mb: 2.5 }}>
                            <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 0.5 }}>
                              <Typography variant="body2">
                                <strong>2Y-10Y Spread:</strong>
                              </Typography>
                              <Typography
                                variant="h6"
                                sx={{
                                  color: economicData.yieldCurve?.spread2y10y < 0 ? "error.main" : "success.main",
                                  fontWeight: 700
                                }}
                              >
                                {formatBasisPoints(economicData.yieldCurve?.spread2y10y)} bps
                              </Typography>
                            </Box>
                            <Typography variant="caption" color="textSecondary">
                              Most watched recession indicator
                            </Typography>
                          </Box>

                          <Box sx={{ mb: 2.5 }}>
                            <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 0.5 }}>
                              <Typography variant="body2">
                                <strong>3M-10Y Spread:</strong>
                              </Typography>
                              <Typography
                                variant="h6"
                                sx={{
                                  color: economicData.yieldCurve?.spread3m10y < 0 ? "error.main" : "success.main",
                                  fontWeight: 700
                                }}
                              >
                                {formatBasisPoints(economicData.yieldCurve?.spread3m10y)} bps
                              </Typography>
                            </Box>
                            <Typography variant="caption" color="textSecondary">
                              Measures near-term vs. long-term expectations
                            </Typography>
                          </Box>

                          <Divider sx={{ my: 2 }} />

                          <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1.5 }}>
                            <Typography variant="body2">
                              <strong>Historical Accuracy:</strong>
                            </Typography>
                            <Chip
                              label={`${economicData.yieldCurve?.historicalAccuracy}%`}
                              color={economicData.yieldCurve?.historicalAccuracy > 75 ? "success" : "warning"}
                              variant="outlined"
                              size="small"
                            />
                          </Box>
                          <Typography variant="caption" color="textSecondary">
                            Accuracy rate for this curve&apos;s signal in predicting economic turns
                          </Typography>
                        </Box>
                      </Grid>
                    </Grid>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          </Box>

          {/* SECTION: Credit Spreads */}
          <Box sx={{ mt: 6, mb: 4 }}>
            <Typography variant="h4" sx={{ fontWeight: 600, mb: 3, display: "flex", alignItems: "center", gap: 1 }}>
              💰 Credit Spreads & Financial Conditions
            </Typography>
            <Grid container spacing={3}>
              <Grid item xs={12} md={6}>
                <Card>
                  <CardHeader title="High Yield Spreads" />
                  <CardContent>
                    <Typography variant="h4" color="primary" gutterBottom>
                      {economicData.creditSpreads?.highYield?.oas || "N/A"} bps
                    </Typography>
                    <Chip
                      label={economicData.creditSpreads?.highYield?.signal || "N/A"}
                      size="small"
                      sx={{ mb: 2 }}
                    />
                    <Typography variant="body2" color="text.secondary">
                      {economicData.creditSpreads?.highYield?.historicalContext}
                    </Typography>
                    <Divider sx={{ my: 2 }} />
                    <Typography variant="body2">
                      <strong>BB-Rated:</strong> {economicData.creditSpreads?.highYieldByRating?.bbRated?.oas || "N/A"} bps
                    </Typography>
                    <Typography variant="body2">
                      <strong>B-Rated:</strong> {economicData.creditSpreads?.highYieldByRating?.bRated?.oas || "N/A"} bps
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>

              <Grid item xs={12} md={6}>
                <Card>
                  <CardHeader title="Investment Grade Spreads" />
                  <CardContent>
                    <Typography variant="h4" color="primary" gutterBottom>
                      {economicData.creditSpreads?.investmentGrade?.oas || "N/A"} bps
                    </Typography>
                    <Chip
                      label={economicData.creditSpreads?.investmentGrade?.signal || "N/A"}
                      size="small"
                      sx={{ mb: 2 }}
                    />
                    <Divider sx={{ my: 2 }} />
                    <Typography variant="body2">
                      <strong>AAA-Rated:</strong> {economicData.creditSpreads?.investmentGradeByRating?.aaaRated?.oas || "N/A"} bps
                    </Typography>
                    <Typography variant="body2">
                      <strong>BBB-Rated:</strong> {economicData.creditSpreads?.investmentGradeByRating?.bbbRated?.oas || "N/A"} bps
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>

              <Grid item xs={12}>
                <Card>
                  <CardHeader title="Financial Conditions Index" />
                  <CardContent>
                    <Box mb={2}>
                      <Typography variant="subtitle2" color="text.secondary">
                        FCI Value
                      </Typography>
                      <Typography variant="h3">
                        {economicData.financialConditionsIndex?.value || "N/A"}
                      </Typography>
                      <Typography variant="body2">
                        Level: {economicData.financialConditionsIndex?.level || "Neutral"}
                      </Typography>
                    </Box>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          </Box>

        </>
      )}
    </Container>
  );
};

export default EconomicModeling;
