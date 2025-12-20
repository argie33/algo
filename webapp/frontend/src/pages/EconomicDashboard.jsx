import { useState, useEffect, useMemo } from "react";
import {
  Alert,
  Box,
  Card,
  CardContent,
  CardHeader,
  Chip,
  CircularProgress,
  Container,
  Grid,
  IconButton,
  LinearProgress,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
  useTheme,
  alpha,
} from "@mui/material";
import {
  TrendingUp,
  TrendingDown,
  TrendingFlat,
  ShowChart,
  Refresh,
} from "@mui/icons-material";
import {
  LineChart,
  Line,
  AreaChart,
  Area,
  ComposedChart,
  XAxis,
  YAxis,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  ReferenceLine,
  Legend,
} from "recharts";
import { api } from "../services/api";

// Helper functions
const formatBasisPoints = (value, fallback = "N/A") => {
  if (value === null || value === undefined || isNaN(value)) return fallback;
  return Math.round(Number(value));
};

// === Panel Components ===

const RecessionRiskPanel = ({ data, isLoading }) => {
  if (isLoading) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", py: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (!data) {
    return (
      <Alert severity="warning">No recession forecast data available</Alert>
    );
  }

  return (
    <Box sx={{ mb: 4 }}>
      <Typography variant="h4" sx={{ fontWeight: 600, mb: 3, display: "flex", alignItems: "center", gap: 1 }}>
        📊 Economic Health Summary
      </Typography>

      <Grid container spacing={3}>
        {/* Key Metrics Summary */}
        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Typography variant="subtitle2" color="text.secondary">
                Recession Risk
              </Typography>
              <Typography
                variant="h3"
                sx={{
                  color:
                    data.recessionProbability > 60
                      ? "error.main"
                      : data.recessionProbability > 35
                        ? "warning.main"
                        : "success.main",
                }}
              >
                {data.recessionProbability}%
              </Typography>
              <LinearProgress
                variant="determinate"
                value={data.recessionProbability}
                color={
                  data.recessionProbability > 60
                    ? "error"
                    : data.recessionProbability > 35
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
                Economic Stress
              </Typography>
              <Typography
                variant="h3"
                sx={{
                  color:
                    data.economicStressIndex > 60
                      ? "error.main"
                      : data.economicStressIndex > 30
                        ? "warning.main"
                        : "success.main",
                }}
              >
                {data.economicStressIndex}
              </Typography>
              <LinearProgress
                variant="determinate"
                value={data.economicStressIndex}
                color={
                  data.economicStressIndex > 60
                    ? "error"
                    : data.economicStressIndex > 30
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
                Credit Stress
              </Typography>
              <Typography
                variant="h3"
                sx={{
                  color:
                    data.creditStressIndex > 50
                      ? "error.main"
                      : data.creditStressIndex > 30
                        ? "warning.main"
                        : "success.main",
                }}
              >
                {data.creditStressIndex}
              </Typography>
              <LinearProgress
                variant="determinate"
                value={data.creditStressIndex}
                color={
                  data.creditStressIndex > 50
                    ? "error"
                    : data.creditStressIndex > 30
                      ? "warning"
                      : "success"
                }
                sx={{ mt: 2 }}
              />
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
};

const LeadingIndicatorsPanel = ({ data, isLoading, theme }) => {
  if (isLoading) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", py: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (!data || data.length === 0) {
    return (
      <Alert severity="warning">No leading indicators data available</Alert>
    );
  }

  const getGradientColor = (signal) => {
    switch (signal) {
      case "Positive":
        return theme.palette.success.main;
      case "Negative":
        return theme.palette.error.main;
      default:
        return theme.palette.primary.main;
    }
  };

  const getTrendColor = (trend) => {
    switch (trend) {
      case "up":
        return theme.palette.success.main;
      case "down":
        return theme.palette.error.main;
      default:
        return theme.palette.info.main;
    }
  };

  // Filter indicators by category
  const leiIndicators = data.filter((ind) => ind.category === "LEI");
  const secondaryIndicators = data.filter((ind) => ind.category === "SECONDARY");
  const laggingIndicators = data.filter((ind) => ind.category === "LAGGING");
  const coincidentIndicators = data.filter((ind) => ind.category === "COINCIDENT");

  const renderIndicatorGrid = (indicators, title, icon) => (
    <Box sx={{ mb: 5 }}>
      <Typography variant="h5" sx={{ fontWeight: 600, mb: 3, display: "flex", alignItems: "center", gap: 1, color: theme.palette.primary.main }}>
        {icon} {title}
      </Typography>
      <Grid container spacing={3}>
        {indicators.map((indicator, idx) => {
          return renderIndicatorCard(indicator, idx);
        })}
      </Grid>
    </Box>
  );

  const renderIndicatorCard = (indicator, idx) => {
    const gradColor = getGradientColor(indicator.signal);
    const trendColor = getTrendColor(indicator.trend);
    const changeColor = indicator.change > 0 ? theme.palette.success.main : indicator.change < 0 ? theme.palette.error.main : theme.palette.text.secondary;

    return (
      <Grid item xs={12} md={6} key={`econ-ind-${indicator.name}-${idx}`}>
              <Card
                sx={{
                  height: "100%",
                  boxShadow: 1,
                  borderRadius: "8px",
                  background: `linear-gradient(135deg, ${alpha(theme.palette.background.paper, 1)}, ${alpha(gradColor, 0.02)})`,
                  transition: "all 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
                  border: `1px solid ${alpha(gradColor, 0.15)}`,
                  "&:hover": {
                    boxShadow: theme.shadows[8],
                    transform: "translateY(-4px)",
                    borderColor: alpha(gradColor, 0.3),
                  },
                }}
              >
                <CardContent sx={{ p: 3 }}>
                  {/* Header with Icon and Title */}
                  <Box display="flex" alignItems="center" gap={1.5} mb={2}>
                    {indicator.trend === "up" ? (
                      <TrendingUp sx={{ color: theme.palette.success.main, fontSize: 28, fontWeight: 700 }} />
                    ) : indicator.trend === "down" ? (
                      <TrendingDown sx={{ color: theme.palette.error.main, fontSize: 28, fontWeight: 700 }} />
                    ) : (
                      <TrendingFlat sx={{ color: theme.palette.info.main, fontSize: 28, fontWeight: 700 }} />
                    )}
                    <Box flex={1}>
                      <Typography variant="h6" gutterBottom sx={{ fontWeight: 700, mb: 0.5, color: theme.palette.text.primary }}>
                        {indicator.name}
                      </Typography>
                      <Typography variant="caption" sx={{ color: theme.palette.text.secondary, fontSize: "0.8rem" }}>
                        {indicator.description}
                      </Typography>
                    </Box>
                    <Chip
                      label={indicator.signal}
                      color={
                        indicator.signal === "Positive"
                          ? "success"
                          : indicator.signal === "Negative"
                            ? "error"
                            : "info"
                      }
                      size="small"
                      variant="filled"
                      sx={{ fontWeight: 600, fontSize: "0.75rem" }}
                    />
                  </Box>

                  {/* Value and Change */}
                  <Box display="flex" alignItems="baseline" gap={2} mb={3}>
                    <Typography
                      variant="h4"
                      sx={{ fontWeight: 700, color: trendColor, letterSpacing: "-0.5px" }}
                    >
                      {indicator.value}
                    </Typography>
                    <Typography
                      variant="body2"
                      sx={{
                        fontWeight: 700,
                        fontSize: "1rem",
                        color: changeColor,
                      }}
                    >
                      {indicator.change > 0 ? "+" : ""}
                      {indicator.change}%
                    </Typography>
                  </Box>

                  {/* Large Chart - Professional Styling */}
                  {indicator.history && indicator.history.length > 1 && (
                    <Box sx={{ width: "100%", height: 280, overflow: "hidden", my: 1 }}>
                      <ResponsiveContainer width="100%" height="100%">
                        <LineChart
                          data={indicator.history}
                          margin={{ top: 5, right: 30, left: 60, bottom: 5 }}
                        >
                          <defs>
                            <linearGradient id={`lei-grad-${idx}`} x1="0" y1="0" x2="0" y2="1">
                              <stop offset="0%" stopColor={gradColor} stopOpacity={0.15} />
                              <stop offset="100%" stopColor={gradColor} stopOpacity={0.02} />
                            </linearGradient>
                          </defs>
                          <CartesianGrid
                            strokeDasharray="3 3"
                            stroke={alpha(theme.palette.divider, 0.25)}
                            vertical={false}
                          />
                          <XAxis
                            dataKey="date"
                            tick={{ fontSize: 10, fill: theme.palette.text.secondary }}
                            axisLine={{ stroke: alpha(theme.palette.divider, 0.2) }}
                            interval={Math.floor(indicator.history.length / 6) || 0}
                            angle={-45}
                            textAnchor="end"
                            height={70}
                          />
                          <YAxis
                            width={50}
                            tick={{ fontSize: 11, fill: theme.palette.text.secondary }}
                            axisLine={{ stroke: alpha(theme.palette.divider, 0.2) }}
                          />
                          <Tooltip
                            contentStyle={{
                              backgroundColor: alpha(theme.palette.background.paper, 0.98),
                              border: `1.5px solid ${gradColor}`,
                              borderRadius: "8px",
                              padding: "12px 14px",
                              boxShadow: theme.shadows[4],
                            }}
                            labelStyle={{ color: theme.palette.text.primary, fontWeight: 700, fontSize: "12px" }}
                            formatter={(value) => [value !== null && value !== undefined ? value.toFixed(2) : "", "Value"]}
                            labelFormatter={(label) => `${label}`}
                            cursor={{ stroke: gradColor, strokeWidth: 2.5, opacity: 0.8 }}
                          />
                          <Line
                            type="monotone"
                            dataKey="value"
                            stroke={gradColor}
                            strokeWidth={2.5}
                            dot={false}
                            isAnimationActive={false}
                            fill={`url(#lei-grad-${idx})`}
                          />
                        </LineChart>
                      </ResponsiveContainer>
                    </Box>
                  )}

                  {/* Last Updated Footer */}
                  {indicator.date && (
                    <Box sx={{ pt: 2, mt: 2, borderTop: `1px solid ${alpha(theme.palette.divider, 0.15)}` }}>
                      <Typography variant="caption" sx={{ color: theme.palette.text.secondary, fontSize: "0.7rem" }}>
                        Updated: {new Date(indicator.date).toLocaleDateString()}
                      </Typography>
                    </Box>
                  )}
                </CardContent>
              </Card>
      </Grid>
    );
  };

  return (
    <Box>
      {renderIndicatorGrid(leiIndicators, "Leading Economic Indicators", <TrendingUp />)}
      {renderIndicatorGrid(laggingIndicators, "Lagging Economic Indicators", <TrendingDown />)}
      {renderIndicatorGrid(coincidentIndicators, "Coincident Economic Indicators", <TrendingFlat />)}
      {renderIndicatorGrid(secondaryIndicators, "Secondary Indicators", <ShowChart />)}
    </Box>
  );
};

const YieldCurvePanel = ({ data, isLoading, theme }) => {
  // Generate unique SVG gradient IDs for this component instance
  const t10y2yId = useMemo(() => `colorT10Y2Y-${Math.random().toString(36).substr(2, 9)}`, []);

  if (isLoading) return <CircularProgress />;
  if (!data) return <Alert severity="warning">No yield curve data available</Alert>;

  const yieldData = data.yieldCurveFullData || data.yieldCurve;
  const spreadHistory = (yieldData && yieldData.history && yieldData.history.T10Y2Y) || [];

  return (
    <Box sx={{ mb: 4 }}>
      <Typography variant="h4" sx={{ fontWeight: 600, mb: 1, display: "flex", alignItems: "center", gap: 1 }}>
        📊 Treasury Yield Curve & Spreads
      </Typography>

      <Grid container spacing={3}>
        {/* Status Banner */}
        <Grid item xs={12}>
          <Card sx={{ background: yieldData?.isInverted ? `linear-gradient(135deg, ${alpha(theme.palette.error.main, 0.1)} 0%, ${alpha(theme.palette.warning.main, 0.05)} 100%)` : `linear-gradient(135deg, ${alpha(theme.palette.success.main, 0.1)} 0%, ${alpha(theme.palette.info.main, 0.05)} 100%)` }}>
            <CardContent>
              <Box sx={{ display: "flex", alignItems: "center", gap: 3, justifyContent: "space-between" }}>
                <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
                  <Box sx={{ fontSize: 48 }}>{yieldData?.isInverted ? "🔴" : "🟢"}</Box>
                  <Box>
                    <Typography variant="h5" sx={{ fontWeight: 700, color: yieldData?.isInverted ? "error.main" : "success.main" }}>
                      {yieldData?.isInverted ? "INVERTED CURVE" : "NORMAL CURVE"}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {yieldData?.isInverted ? "Recession signal active" : "Healthy environment"}
                    </Typography>
                  </Box>
                </Box>
                <Box sx={{ textAlign: "right", display: "flex", gap: 3 }}>
                  <Box>
                    <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>10Y YIELD</Typography>
                    <Typography variant="h4" sx={{ fontWeight: 700, color: "primary.main" }}>
                      {yieldData?.currentCurve?.['10Y']?.toFixed(2)}%
                    </Typography>
                  </Box>
                  <Box>
                    <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>T10Y2Y SPREAD</Typography>
                    <Typography variant="h4" sx={{ fontWeight: 700, color: yieldData?.spreads?.T10Y2Y < 0 ? "error.main" : "success.main" }}>
                      {formatBasisPoints(yieldData?.spreads?.T10Y2Y)} bps
                    </Typography>
                  </Box>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Main Yield Curve Line Chart */}
        <Grid item xs={12}>
          <Card>
            <CardHeader title="Treasury Yield Curve (3M - 30Y)" />
            <CardContent>
              {data.yieldCurveData?.length > 0 ? (
                <ResponsiveContainer width="100%" height={400}>
                  <LineChart data={data.yieldCurveData}>
                    <CartesianGrid strokeDasharray="3 3" stroke={theme.palette.divider} opacity={0.2} />
                    <XAxis dataKey="maturity" tick={{ fontSize: 11, fontWeight: 500 }} />
                    <YAxis tick={{ fontSize: 11 }} width={50} domain={[0, 'auto']} label={{ value: 'Yield (%)', angle: -90, position: 'insideLeft', offset: 10 }} />
                    <Tooltip
                      formatter={(v) => v !== null && v !== undefined ? `${v.toFixed(3)}%` : 'N/A'}
                      labelFormatter={(l) => `Maturity: ${l}`}
                      contentStyle={{ backgroundColor: alpha(theme.palette.background.paper, 0.95), border: `1px solid ${theme.palette.divider}` }}
                    />
                    <Line type="monotone" dataKey="yield" stroke={theme.palette.primary.main} strokeWidth={3} dot={{ fill: theme.palette.primary.main, r: 5 }} activeDot={{ r: 7 }} />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <Alert severity="warning">No data available</Alert>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Spread Analysis - Two Charts Side by Side */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardHeader title="10Y-2Y Spread (T10Y2Y)" subheader="Primary recession indicator" />
            <CardContent>
              {spreadHistory.length > 0 ? (
                <ResponsiveContainer width="100%" height={350}>
                  <AreaChart data={spreadHistory}>
                    <defs>
                      <linearGradient id={t10y2yId} x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={theme.palette.primary.main} stopOpacity={0.3} />
                        <stop offset="95%" stopColor={theme.palette.primary.main} stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke={theme.palette.divider} opacity={0.2} />
                    <XAxis dataKey="date" tick={{ fontSize: 9 }} tickFormatter={(d) => new Date(d).toLocaleDateString('en-US', { month: 'short' })} interval="preserveStartEnd" />
                    <YAxis tick={{ fontSize: 9 }} width={40} label={{ value: 'bps', angle: -90, position: 'insideLeft' }} />
                    <Tooltip formatter={(v) => v !== null && v !== undefined ? `${v.toFixed(0)} bps` : 'N/A'} labelFormatter={(d) => new Date(d).toLocaleDateString()} />
                    <ReferenceLine y={0} stroke={theme.palette.error.main} strokeDasharray="5 5" strokeWidth={2} label={{ value: "Inversion", position: "right", fill: theme.palette.error.main, fontSize: 12, fontWeight: 600 }} />
                    <Area type="monotone" dataKey="value" stroke={theme.palette.primary.main} fill={`url(#${t10y2yId})`} strokeWidth={2} />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <Alert severity="info">No historical data available</Alert>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Historical Rate Comparison */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardHeader title="Rate Comparison" subheader="10Y vs 2Y vs 3M" />
            <CardContent>
              {yieldData?.history?.['10Y'] && yieldData?.history?.['2Y'] ? (
                <ResponsiveContainer width="100%" height={350}>
                  <LineChart>
                    <CartesianGrid strokeDasharray="3 3" stroke={theme.palette.divider} opacity={0.2} />
                    <XAxis
                      dataKey="date"
                      data={yieldData.history['10Y']}
                      tick={{ fontSize: 9 }}
                      tickFormatter={(d) => new Date(d).toLocaleDateString('en-US', { month: 'short' })}
                      interval="preserveStartEnd"
                    />
                    <YAxis tick={{ fontSize: 9 }} width={40} label={{ value: '%', angle: -90, position: 'insideLeft' }} domain={['dataMin - 0.5', 'dataMax + 0.5']} />
                    <Tooltip formatter={(v) => `${v.toFixed(2)}%`} labelFormatter={(d) => new Date(d).toLocaleDateString()} />
                    <Legend />
                    <Line type="monotone" dataKey="value" name="10Y Yield" data={yieldData.history['10Y']} stroke="#1976d2" strokeWidth={2.5} dot={false} />
                    <Line type="monotone" dataKey="value" name="2Y Yield" data={yieldData.history['2Y']} stroke="#f57c00" strokeWidth={2.5} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <Alert severity="info">No historical data</Alert>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Key Metrics Table Supplement */}
        <Grid item xs={12}>
          <Card>
            <CardHeader title="Key Metrics Summary" />
            <CardContent>
              <Grid container spacing={1}>
                <Grid item xs={12} sm={6} md={3}>
                  <Box sx={{ p: 1.5, backgroundColor: alpha(theme.palette.info.main, 0.08), borderRadius: 1 }}>
                    <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>3-MONTH</Typography>
                    <Typography variant="h5" sx={{ fontWeight: 700, color: "primary.main", mt: 0.5 }}>
                      {yieldData?.currentCurve?.['3M']?.toFixed(2)}%
                    </Typography>
                  </Box>
                </Grid>
                <Grid item xs={12} sm={6} md={3}>
                  <Box sx={{ p: 1.5, backgroundColor: alpha(theme.palette.info.main, 0.08), borderRadius: 1 }}>
                    <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>2-YEAR</Typography>
                    <Typography variant="h5" sx={{ fontWeight: 700, color: "primary.main", mt: 0.5 }}>
                      {yieldData?.currentCurve?.['2Y']?.toFixed(2)}%
                    </Typography>
                  </Box>
                </Grid>
                <Grid item xs={12} sm={6} md={3}>
                  <Box sx={{ p: 1.5, backgroundColor: alpha(theme.palette.info.main, 0.08), borderRadius: 1 }}>
                    <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>10-YEAR</Typography>
                    <Typography variant="h5" sx={{ fontWeight: 700, color: "primary.main", mt: 0.5 }}>
                      {yieldData?.currentCurve?.['10Y']?.toFixed(2)}%
                    </Typography>
                  </Box>
                </Grid>
                <Grid item xs={12} sm={6} md={3}>
                  <Box sx={{ p: 1.5, backgroundColor: alpha(theme.palette.info.main, 0.08), borderRadius: 1 }}>
                    <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>30-YEAR</Typography>
                    <Typography variant="h5" sx={{ fontWeight: 700, color: "primary.main", mt: 0.5 }}>
                      {yieldData?.currentCurve?.['30Y']?.toFixed(2)}%
                    </Typography>
                  </Box>
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
};


const EconomicCalendarPanel = ({ events, isLoading }) => {
  if (isLoading) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", py: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (!events || events.length === 0) {
    return (
      <Alert severity="info">No upcoming economic events</Alert>
    );
  }

  return (
    <Box sx={{ mb: 4 }}>
      <Typography variant="h4" sx={{ fontWeight: 600, mb: 3, display: "flex", alignItems: "center", gap: 1 }}>
        📅 Economic Calendar
      </Typography>

      <Card>
        <CardContent>
          <TableContainer component={Paper} elevation={0}>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>Date</TableCell>
                  <TableCell>Event</TableCell>
                  <TableCell>Importance</TableCell>
                  <TableCell>Forecast</TableCell>
                  <TableCell>Previous</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {events.map((event, idx) => (
                  <TableRow key={`event-${event.date}-${event.event}-${idx}`} hover>
                    <TableCell>{new Date(event.date).toLocaleDateString()}</TableCell>
                    <TableCell>{event.event}</TableCell>
                    <TableCell>
                      <Chip
                        label={event.importance}
                        color={
                          event.importance?.toLowerCase() === "high"
                            ? "error"
                            : event.importance?.toLowerCase() === "medium"
                              ? "warning"
                              : "default"
                        }
                        size="small"
                      />
                    </TableCell>
                    <TableCell>{event.forecast_value || "N/A"}</TableCell>
                    <TableCell>{event.previous_value || "N/A"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </CardContent>
      </Card>
    </Box>
  );
};

// === Main Component ===

export default function EconomicDashboard() {
  const theme = useTheme();
  const [economicData, setEconomicData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  // Fetch all economic data with graceful fallback for missing endpoints
  const fetchEconomicData = async () => {
    try {
      setLoading(true);
      setError(null);

      // Fetch all four endpoints in parallel
      let leadingIndicators = null;
      let yieldCurveFullData = null;
      let creditSpreadsFullData = null;
      let economicCalendarData = null;

      try {
        const response = await api.get("/api/economic/leading-indicators");
        // responseFormatter wraps response in { success, data: {...}, timestamp }
        // Extract the inner data property
        leadingIndicators = response?.data?.data || response?.data || {};
      } catch (err) {
        console.warn("⚠️ Failed to fetch leading indicators:", err?.message || err);
        // Use empty array as fallback - UI will show appropriate message
        leadingIndicators = { indicators: [], gdpGrowth: null, unemployment: null, inflation: null };
      }

      // Fetch yield curve data
      try {
        const response = await api.get("/api/economic/yield-curve-full");
        // responseFormatter wraps response in { success, data: {...}, timestamp }
        const rawData = response?.data?.data || response?.data || null;

        // Map the response data to the expected format
        if (rawData) {
          yieldCurveFullData = {
            currentCurve: rawData.currentCurve || {},
            spreads: rawData.spreads || {},
            isInverted: rawData.isInverted || false,
            history: rawData.history || {},
            credit: rawData.credit || { currentSpreads: {}, history: {} },
            source: rawData.source
          };
        } else {
          yieldCurveFullData = null;
        }

        console.log("✅ Yield Curve Data Fetched:", {
          hasCurrentCurve: !!yieldCurveFullData?.currentCurve,
          maturities: yieldCurveFullData?.currentCurve ? Object.keys(yieldCurveFullData.currentCurve) : [],
          hasSpreads: !!yieldCurveFullData?.spreads,
          spreads: yieldCurveFullData?.spreads,
          isInverted: yieldCurveFullData?.isInverted
        });
      } catch (err) {
        console.warn("⚠️ Failed to fetch yield curve data:", err?.message || err);
        yieldCurveFullData = null;
      }

      // Fetch economic calendar data (optional - use empty defaults if fails)
      try {
        const response = await api.get("/api/economic/calendar");
        // responseFormatter wraps response in { success, data: {...}, timestamp }
        const rawData = response?.data?.data || response?.data || {};
        economicCalendarData = rawData?.events || (Array.isArray(rawData) ? rawData : []);
        console.log("✅ Economic Calendar Data Fetched:", {
          count: economicCalendarData?.length || 0,
          data: economicCalendarData
        });
      } catch (err) {
        console.warn("⚠️ Failed to fetch economic calendar:", err?.message || err);
        economicCalendarData = [];
      }

      // Extract data from available endpoints
      const leadData = leadingIndicators || {};

      // Process yield curve data - transform into chart format
      let processedYieldCurveData = [];
      let transformedYieldHistory = {};
      if (yieldCurveFullData?.currentCurve) {
        const maturityMap = {
          '3M': '3 Month',
          '2Y': '2 Year',
          '5Y': '5 Year',
          '10Y': '10 Year',
          '30Y': '30 Year'
        };
        processedYieldCurveData = Object.entries(yieldCurveFullData.currentCurve).map(([key, value]) => ({
          maturity: maturityMap[key] || key,
          yield: value ?? null
        }));

        // Transform history data from series IDs to maturity keys
        // Map series IDs to maturity keys
        const seriesMaturityMap = {
          'DGS3MO': '3M',
          'DGS2': '2Y',
          'DGS5': '5Y',
          'DGS10': '10Y',
          'DGS30': '30Y',
          'T10Y2Y': 'spread_10y2y',
          'T10Y3M': 'spread_10y3m'
        };

        if (yieldCurveFullData?.history) {
          Object.entries(yieldCurveFullData.history).forEach(([seriesId, data]) => {
            const maturityKey = seriesMaturityMap[seriesId] || seriesId;
            transformedYieldHistory[maturityKey] = data || [];
          });
        }
      }

      // Process credit spreads data
      let processedCreditSpreads = {};
      if (creditSpreadsFullData?.currentSpreads) {
        processedCreditSpreads = creditSpreadsFullData.currentSpreads;
      }

      // Transform calendar events to match frontend expectations
      let transformedCalendarEvents = [];
      if (economicCalendarData && Array.isArray(economicCalendarData)) {
        transformedCalendarEvents = economicCalendarData.map((event) => ({
          date: event.event_date || event.date,
          event: event.event_name || event.Event || event.event,
          importance: event.importance || event.Importance,
          forecast: event.forecast_value || event.Forecast,
          previous: event.previous_value || event.Previous,
          category: event.category || event.Category
        }));
      }

      // Calculate Economic Stress Index from real data (0-100 scale)
      let economicStress = 0;
      const indicators = leadData?.indicators || [];
      const unrateIndicator = indicators.find(i => i.name === "Unemployment Rate");
      const icsaIndicator = indicators.find(i => i.name === "Initial Jobless Claims");

      // Track number of economic indicators with real data
      let economicIndicatorCount = 0;

      // Unemployment stress: 4% = 0 stress, 6% = 50 stress, 8%+ = 100 stress
      if (unrateIndicator?.rawValue !== null && unrateIndicator?.rawValue !== undefined) {
        economicStress += Math.min(100, Math.max(0, (unrateIndicator.rawValue - 3.5) * 20));
        economicIndicatorCount++;
      }

      // Initial claims stress: 200K = 0, 250K = 25, 300K+ = 100
      if (icsaIndicator?.rawValue !== null && icsaIndicator?.rawValue !== undefined) {
        economicStress += Math.min(100, Math.max(0, (icsaIndicator.rawValue / 1000 - 200) * 2));
        economicIndicatorCount++;
      }

      // Yield curve stress: inverted = +25 points
      const yieldCurveSpread = yieldCurveFullData?.spreads?.T10Y2Y;
      if (yieldCurveSpread !== null && yieldCurveSpread !== undefined && yieldCurveSpread < 0) {
        economicStress += 25;
        economicIndicatorCount++;
      }

      // Average out the score - only divide by actual indicators with data
      // If no data available, economicStress remains null
      if (economicIndicatorCount > 0) {
        economicStress = Math.min(100, Math.max(0, economicStress / economicIndicatorCount));
      } else {
        economicStress = null;
      }

      // Calculate Credit Stress Index (0-100 scale) from credit spreads data
      let creditStress = null;
      if (creditSpreadsFullData?.currentSpreads) {
        let stressComponents = 0;
        let componentCount = 0;

        // HY OAS stress: 300 bps = 25, 400 = 50, 600+ = 100
        const hyOas = creditSpreadsFullData.currentSpreads.highYield?.value;
        if (hyOas !== null && hyOas !== undefined) {
          stressComponents += Math.min(100, Math.max(0, (hyOas - 300) / 3));
          componentCount++;
        }

        // IG OAS stress: 100 bps = 25, 150 = 50, 250+ = 100
        const igOas = creditSpreadsFullData.currentSpreads.investmentGrade?.value;
        if (igOas !== null && igOas !== undefined) {
          stressComponents += Math.min(100, Math.max(0, (igOas - 100) / 1.5));
          componentCount++;
        }

        // VIX stress: 15 = 0, 20 = 25, 30+ = 100
        const vix = creditSpreadsFullData.vix?.value;
        if (vix !== null && vix !== undefined) {
          stressComponents += Math.min(100, Math.max(0, (vix - 15) * 5));
          componentCount++;
        }

        // Average out - only if we have at least one component
        if (componentCount > 0) {
          creditStress = Math.min(100, Math.max(0, stressComponents / componentCount));
        }
      }

      const combinedData = {
        // Recession data - ONLY if we have real economic data
        recessionProbability: economicStress !== null && creditStress !== null
          ? Math.round((economicStress + creditStress) / 2 * 0.5)
          : economicStress !== null
          ? Math.round(economicStress * 0.5)
          : null,
        riskLevel: economicStress !== null ? (economicStress > 60 ? "High" : economicStress > 30 ? "Moderate" : "Low") : "Unknown",
        riskIndicator: economicStress !== null ? (economicStress > 60 ? "🔴" : economicStress > 30 ? "🟡" : "🟢") : "❓",
        economicStressIndex: economicStress !== null ? Math.round(economicStress) : null,
        forecastModels: [],
        recessionAnalysis: { summary: economicStress !== null
          ? (economicStress > 60 ? "Economic stress indicators elevated - monitor labor market and yield curve closely." : "Economic indicators show mixed signals.")
          : "Insufficient data for recession analysis" },
        keyRecessionIndicators: {},

        // Leading indicators - ONLY real data, no defaults
        leadingIndicators: leadData.indicators || [],
        gdpGrowth: leadData.gdpGrowth ?? null,
        unemployment: leadData.unemployment ?? null,
        inflation: leadData.inflation ?? null,
        employment: leadData.employment || {},

        // Yield curve - NEW: full data from dedicated endpoint
        yieldCurveFullData: {
          ...yieldCurveFullData,
          history: transformedYieldHistory // Use transformed history with maturity keys
        },
        yieldCurveData: processedYieldCurveData,
        yieldCurve: yieldCurveFullData && yieldCurveFullData.spreads?.T10Y2Y !== null && yieldCurveFullData.spreads?.T10Y2Y !== undefined ? {
          isInverted: yieldCurveFullData.spreads.T10Y2Y < 0,
          spread: yieldCurveFullData.spreads.T10Y2Y,
          averageLeadTime: 12
        } : {},

        // Credit spreads - NEW: full data from dedicated endpoint
        creditSpreadsFullData: creditSpreadsFullData,
        creditSpreads: processedCreditSpreads,
        creditStressIndex: creditStress !== null ? Math.round(creditStress) : null,
        financialConditionsIndex: creditStress !== null ? {
          value: creditStress > 60 ? 'HIGH' : creditStress > 30 ? 'MODERATE' : 'NORMAL',
          level: creditStress > 60 ? 'Stressed' : creditStress > 30 ? 'Caution' : 'Healthy'
        } : { value: 'UNKNOWN', level: 'Data Unavailable' },

        // Calendar - FIXED: now fetching from API
        upcomingEvents: transformedCalendarEvents,
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
            🌍 Economic Dashboard
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
          <Box component="button" onClick={handleRefresh} sx={{ ml: 2, cursor: "pointer", textDecoration: "underline", border: "none", background: "none", color: "inherit", fontWeight: "bold" }}>
            Retry
          </Box>
        </Alert>
      )}

      {/* Critical Alert if recession probability high */}
      {!loading && economicData && economicData.recessionProbability > 40 && (
        <Alert severity="warning" sx={{ mb: 3 }}>
          <strong>⚠️ Elevated Recession Risk:</strong> {economicData.recessionProbability}% probability.
          Multiple economic warning signals detected. Monitor market conditions closely.
        </Alert>
      )}

      {/* Content Panels */}
      {!loading && economicData && (
        <>
          <RecessionRiskPanel data={economicData} isLoading={false} theme={theme} />
          <LeadingIndicatorsPanel data={economicData.leadingIndicators} isLoading={false} theme={theme} />
          <YieldCurvePanel data={economicData} isLoading={false} theme={theme} />
          <EconomicCalendarPanel events={economicData.upcomingEvents} isLoading={false} />
        </>
      )}
    </Container>
  );
}
