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
  Divider,
  Grid,
  IconButton,
  LinearProgress,
  Paper,
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
  ScatterChart,
  Scatter,
} from "recharts";
import { api } from "../services/api";
import { GRADIENTS } from "../theme/chartGradients";

// Helper functions
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

const SubtleDot = (props, color) => {
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

// === Panel Components ===

const RecessionRiskPanel = ({ data, isLoading, theme }) => {
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

const LeadingIndicatorsPanel = ({ data, isLoading, theme, yieldCurveData }) => {
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
      <Grid item xs={12} md={6} key={idx}>
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
                            formatter={(value) => [value.toFixed(2), "Value"]}
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
  if (isLoading) return <CircularProgress />;
  if (!data) return <Alert severity="warning">No yield curve data available</Alert>;

  const yieldData = data.yieldCurveFullData || data.yieldCurve;
  const spreadHistory = yieldData?.history?.T10Y2Y || [];

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
                      formatter={(v) => `${v?.toFixed(3) || 0}%`}
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
                      <linearGradient id="colorT10Y2Y" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={theme.palette.primary.main} stopOpacity={0.3} />
                        <stop offset="95%" stopColor={theme.palette.primary.main} stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke={theme.palette.divider} opacity={0.2} />
                    <XAxis dataKey="date" tick={{ fontSize: 9 }} tickFormatter={(d) => new Date(d).toLocaleDateString('en-US', { month: 'short' })} interval="preserveStartEnd" />
                    <YAxis tick={{ fontSize: 9 }} width={40} label={{ value: 'bps', angle: -90, position: 'insideLeft' }} />
                    <Tooltip formatter={(v) => `${v.toFixed(0)} bps`} labelFormatter={(d) => new Date(d).toLocaleDateString()} />
                    <ReferenceLine y={0} stroke={theme.palette.error.main} strokeDasharray="5 5" strokeWidth={2} label={{ value: "Inversion", position: "right", fill: theme.palette.error.main, fontSize: 12, fontWeight: 600 }} />
                    <Area type="monotone" dataKey="value" stroke={theme.palette.primary.main} fill="url(#colorT10Y2Y)" strokeWidth={2} />
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

// Reusable metric card for spreads and yields
const MetricCard = ({ label, value, description, trend, unit = "bps", stressLevel, theme }) => {
  const getStressColor = (level) => {
    if (level === 'extreme') return 'error';
    if (level === 'high') return 'warning';
    if (level === 'moderate') return 'info';
    return 'success';
  };

  const getTrendIcon = (trendDir) => {
    if (trendDir === 'rising') return <TrendingUp sx={{ fontSize: 16 }} />;
    if (trendDir === 'falling') return <TrendingDown sx={{ fontSize: 16 }} />;
    return <TrendingFlat sx={{ fontSize: 16 }} />;
  };

  return (
    <Box sx={{ p: 2, backgroundColor: alpha(theme.palette.background.paper, 0.8), border: `1px solid ${theme.palette.divider}`, borderRadius: 1.5, mb: 2 }}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", mb: 1 }}>
        <Box>
          <Typography variant="subtitle2" sx={{ fontWeight: 600, color: "text.secondary" }}>{label}</Typography>
          {description && <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: "block" }}>{description}</Typography>}
        </Box>
        {stressLevel && <Chip label={stressLevel.toUpperCase()} size="small" color={getStressColor(stressLevel)} variant="outlined" />}
      </Box>
      <Box sx={{ display: "flex", alignItems: "baseline", gap: 2, mt: 1.5 }}>
        <Typography variant="h6" sx={{ fontWeight: 700 }}>
          {value} {unit}
        </Typography>
        {trend && (
          <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
            <Box sx={{ color: trend.change > 0 ? 'error.main' : 'success.main' }}>
              {getTrendIcon(trend.trend)}
            </Box>
            <Typography variant="caption" sx={{ fontWeight: 600, color: trend.change > 0 ? 'error.main' : 'success.main' }}>
              {trend.change > 0 ? '+' : ''}{trend.change} {unit}
            </Typography>
          </Box>
        )}
      </Box>
    </Box>
  );
};

const CreditMarketPanel = ({ data, isLoading, theme }) => {
  if (isLoading) return <CircularProgress />;
  if (!data) return <Alert severity="warning">No credit spreads data available</Alert>;

  const creditData = data.creditSpreadsFullData || data.creditSpreads;

  // Calculate spread history for comparison chart
  // API returns history organized by series ID: BAMLH0A0HYM2, BAMLH0A0IG, BAA, AAA
  const spreadHistory = creditData?.history?.BAMLH0A0HYM2 && creditData?.history?.BAMLH0A0IG
    ? creditData.history.BAMLH0A0HYM2.map((hy, idx) => {
        const igValue = creditData.history.BAMLH0A0IG[idx]?.value || 0;
        // Calculate BAA-AAA spread: BAA yield minus AAA yield (already in correct scale)
        const baaValue = creditData.history.BAA?.[idx]?.value || null;
        const aaaValue = creditData.history.AAA?.[idx]?.value || null;
        const baaAaaSpread = (baaValue !== null && aaaValue !== null)
          ? (baaValue - aaaValue)
          : null;
        return {
          date: hy.date,
          "High Yield OAS": hy.value,
          "Investment Grade OAS": igValue,
          ...(baaAaaSpread !== null && { "BAA-AAA": baaAaaSpread })
        };
      })
    : [];

  // Calculate VIX history
  const vixHistory = creditData?.history?.VIXCLS || [];

  // Get overall credit stress level based on HY OAS
  const getStressColor = (value) => {
    if (value > 600) return { color: 'error.main', label: 'EXTREME' };
    if (value > 450) return { color: 'warning.main', label: 'HIGH' };
    if (value > 350) return { color: 'info.main', label: 'MODERATE' };
    return { color: 'success.main', label: 'NORMAL' };
  };

  const hyStress = getStressColor(creditData?.highYield?.value);

  return (
    <Box sx={{ mb: 4 }}>
      <Typography variant="h4" sx={{ fontWeight: 600, mb: 1, display: "flex", alignItems: "center", gap: 1 }}>
        💰 Credit & Corporate Bond Markets
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        Professional credit market analysis showing spreads, yields, and volatility trends
      </Typography>

      <Grid container spacing={3}>
        {/* Credit Stress Status Banner */}
        <Grid item xs={12}>
          <Card sx={{ background: creditData?.highYield?.value > 450
            ? `linear-gradient(135deg, ${alpha(theme.palette.error.main, 0.1)} 0%, ${alpha(theme.palette.warning.main, 0.05)} 100%)`
            : `linear-gradient(135deg, ${alpha(theme.palette.success.main, 0.1)} 0%, ${alpha(theme.palette.info.main, 0.05)} 100%)` }}>
            <CardContent>
              <Box sx={{ display: "flex", alignItems: "center", gap: 3, justifyContent: "space-between" }}>
                <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
                  <Box sx={{ fontSize: 48 }}>{creditData?.highYield?.value > 450 ? "🔴" : "🟢"}</Box>
                  <Box>
                    <Typography variant="h5" sx={{ fontWeight: 700, color: creditData?.highYield?.value > 450 ? "error.main" : "success.main" }}>
                      {creditData?.highYield?.value > 450 ? "ELEVATED CREDIT STRESS" : "NORMAL CREDIT CONDITIONS"}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {creditData?.highYield?.value > 600 ? "Extreme spreads suggest market stress" :
                       creditData?.highYield?.value > 450 ? "Elevated spreads indicate caution" :
                       "Healthy credit conditions"}
                    </Typography>
                  </Box>
                </Box>
                <Box sx={{ textAlign: "right", display: "flex", gap: 3 }}>
                  <Box>
                    <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>HY OAS</Typography>
                    <Typography variant="h4" sx={{ fontWeight: 700, color: "primary.main" }}>
                      {formatBasisPoints(creditData?.highYield?.value)}
                    </Typography>
                  </Box>
                  <Box>
                    <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>IG OAS</Typography>
                    <Typography variant="h4" sx={{ fontWeight: 700, color: "primary.main" }}>
                      {formatBasisPoints(creditData?.investmentGrade?.value)}
                    </Typography>
                  </Box>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* High Yield OAS Historical Trend */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardHeader title="High Yield OAS Trend" subheader="Corporate junk bond spread risk" />
            <CardContent>
              {creditData?.history?.BAMLH0A0HYM2 && creditData.history.BAMLH0A0HYM2.length > 0 ? (
                <ResponsiveContainer width="100%" height={350}>
                  <AreaChart data={creditData.history.BAMLH0A0HYM2}>
                    <defs>
                      <linearGradient id="colorHY" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={theme.palette.error.main} stopOpacity={0.3} />
                        <stop offset="95%" stopColor={theme.palette.error.main} stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke={theme.palette.divider} opacity={0.2} />
                    <XAxis dataKey="date" tick={{ fontSize: 9 }} tickFormatter={(d) => new Date(d).toLocaleDateString('en-US', { month: 'short' })} interval="preserveStartEnd" />
                    <YAxis tick={{ fontSize: 9 }} width={40} label={{ value: 'bps', angle: -90, position: 'insideLeft' }} />
                    <Tooltip formatter={(v) => `${v.toFixed(0)} bps`} labelFormatter={(d) => new Date(d).toLocaleDateString()} />
                    <ReferenceLine y={450} stroke={theme.palette.warning.main} strokeDasharray="5 5" strokeWidth={1.5} label={{ value: "Caution Level (450)", position: "right", fill: theme.palette.warning.main, fontSize: 10 }} />
                    <Area type="monotone" dataKey="value" stroke={theme.palette.error.main} fill="url(#colorHY)" strokeWidth={2.5} />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <Alert severity="info">No historical data available</Alert>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Investment Grade OAS Historical Trend */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardHeader title="Investment Grade OAS Trend" subheader="Corporate bond spread for quality issuers" />
            <CardContent>
              {creditData?.history?.BAMLH0A0IG && creditData.history.BAMLH0A0IG.length > 0 ? (
                <ResponsiveContainer width="100%" height={350}>
                  <AreaChart data={creditData.history.BAMLH0A0IG}>
                    <defs>
                      <linearGradient id="colorIG" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={theme.palette.info.main} stopOpacity={0.3} />
                        <stop offset="95%" stopColor={theme.palette.info.main} stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke={theme.palette.divider} opacity={0.2} />
                    <XAxis dataKey="date" tick={{ fontSize: 9 }} tickFormatter={(d) => new Date(d).toLocaleDateString('en-US', { month: 'short' })} interval="preserveStartEnd" />
                    <YAxis tick={{ fontSize: 9 }} width={40} label={{ value: 'bps', angle: -90, position: 'insideLeft' }} />
                    <Tooltip formatter={(v) => `${v.toFixed(0)} bps`} labelFormatter={(d) => new Date(d).toLocaleDateString()} />
                    <Area type="monotone" dataKey="value" stroke={theme.palette.info.main} fill="url(#colorIG)" strokeWidth={2.5} />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <Alert severity="info">No historical data available</Alert>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Credit Spreads Comparison Chart */}
        <Grid item xs={12}>
          <Card>
            <CardHeader title="Multi-Spread Comparison" subheader="HY OAS vs IG OAS vs BAA-AAA differential" />
            <CardContent>
              {spreadHistory.length > 0 ? (
                <ResponsiveContainer width="100%" height={380}>
                  <LineChart data={spreadHistory}>
                    <CartesianGrid strokeDasharray="3 3" stroke={theme.palette.divider} opacity={0.2} />
                    <XAxis dataKey="date" tick={{ fontSize: 9 }} tickFormatter={(d) => new Date(d).toLocaleDateString('en-US', { month: 'short' })} interval="preserveStartEnd" />
                    <YAxis tick={{ fontSize: 9 }} width={50} label={{ value: 'Basis Points', angle: -90, position: 'insideLeft' }} />
                    <Tooltip formatter={(v) => `${v.toFixed(0)} bps`} labelFormatter={(d) => new Date(d).toLocaleDateString()} />
                    <Legend />
                    <Line type="monotone" dataKey="High Yield OAS" stroke={theme.palette.error.main} strokeWidth={2.5} dot={false} isAnimationActive={false} />
                    <Line type="monotone" dataKey="Investment Grade OAS" stroke={theme.palette.info.main} strokeWidth={2.5} dot={false} isAnimationActive={false} />
                    <Line type="monotone" dataKey="BAA-AAA" stroke={theme.palette.warning.main} strokeWidth={2.5} dot={false} isAnimationActive={false} />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <Alert severity="info">No comparison data available</Alert>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Corporate Bond Yields Comparison */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardHeader title="AAA vs BAA Yields" subheader="Corporate bond yield differential" />
            <CardContent>
              {creditData?.history?.AAA && creditData?.history?.BAA && creditData.history.AAA.length > 0 ? (() => {
                // Merge AAA and BAA data by date
                const combinedYields = creditData.history.AAA.map((aaaData, idx) => ({
                  date: aaaData.date,
                  "AAA Yield": aaaData.value,
                  "BAA Yield": creditData.history.BAA[idx]?.value || null
                }));
                return (
                  <ResponsiveContainer width="100%" height={350}>
                    <ComposedChart data={combinedYields}>
                      <CartesianGrid strokeDasharray="3 3" stroke={theme.palette.divider} opacity={0.2} />
                      <XAxis
                        dataKey="date"
                        tick={{ fontSize: 9 }}
                        tickFormatter={(d) => new Date(d).toLocaleDateString('en-US', { month: 'short' })}
                        interval="preserveStartEnd"
                      />
                      <YAxis tick={{ fontSize: 9 }} width={40} label={{ value: '%', angle: -90, position: 'insideLeft' }} domain={['dataMin - 0.1', 'dataMax + 0.1']} />
                      <Tooltip formatter={(v) => v !== null ? `${v.toFixed(2)}%` : 'N/A'} labelFormatter={(d) => new Date(d).toLocaleDateString()} />
                      <Legend />
                      <Line type="monotone" dataKey="AAA Yield" stroke="#1976d2" strokeWidth={2.5} dot={false} isAnimationActive={false} />
                      <Line type="monotone" dataKey="BAA Yield" stroke="#d32f2f" strokeWidth={2.5} dot={false} isAnimationActive={false} />
                    </ComposedChart>
                  </ResponsiveContainer>
                );
              })() : (
                <Alert severity="info">No historical data available</Alert>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* VIX Volatility Index Trend */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardHeader title="VIX Volatility Index" subheader="Market fear and expected volatility" />
            <CardContent>
              {vixHistory && vixHistory.length > 0 ? (
                <ResponsiveContainer width="100%" height={350}>
                  <AreaChart data={vixHistory}>
                    <defs>
                      <linearGradient id="colorVIX" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={theme.palette.warning.main} stopOpacity={0.3} />
                        <stop offset="95%" stopColor={theme.palette.warning.main} stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke={theme.palette.divider} opacity={0.2} />
                    <XAxis dataKey="date" tick={{ fontSize: 9 }} tickFormatter={(d) => new Date(d).toLocaleDateString('en-US', { month: 'short' })} interval="preserveStartEnd" />
                    <YAxis tick={{ fontSize: 9 }} width={40} label={{ value: 'Index', angle: -90, position: 'insideLeft' }} />
                    <Tooltip formatter={(v) => `${v.toFixed(1)}`} labelFormatter={(d) => new Date(d).toLocaleDateString()} />
                    <ReferenceLine y={20} stroke={theme.palette.info.main} strokeDasharray="5 5" strokeWidth={1.5} label={{ value: "Baseline (20)", position: "right", fill: theme.palette.info.main, fontSize: 10 }} />
                    <Area type="monotone" dataKey="value" stroke={theme.palette.warning.main} fill="url(#colorVIX)" strokeWidth={2.5} />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <Alert severity="info">No VIX data available</Alert>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Key Metrics Summary Table */}
        <Grid item xs={12}>
          <Card>
            <CardHeader title="Current Credit Market Metrics" />
            <CardContent>
              <Grid container spacing={2}>
                <Grid item xs={12} sm={6} md={2.4}>
                  <Box sx={{ p: 1.5, backgroundColor: alpha(theme.palette.error.main, 0.08), borderRadius: 1 }}>
                    <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>HY OAS</Typography>
                    <Typography variant="h6" sx={{ fontWeight: 700, color: "error.main", mt: 0.5 }}>
                      {formatBasisPoints(creditData?.highYield?.value)}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">High Yield Spread</Typography>
                  </Box>
                </Grid>
                <Grid item xs={12} sm={6} md={2.4}>
                  <Box sx={{ p: 1.5, backgroundColor: alpha(theme.palette.info.main, 0.08), borderRadius: 1 }}>
                    <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>IG OAS</Typography>
                    <Typography variant="h6" sx={{ fontWeight: 700, color: "info.main", mt: 0.5 }}>
                      {formatBasisPoints(creditData?.investmentGrade?.value)}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">Inv. Grade Spread</Typography>
                  </Box>
                </Grid>
                <Grid item xs={12} sm={6} md={2.4}>
                  <Box sx={{ p: 1.5, backgroundColor: alpha(theme.palette.warning.main, 0.08), borderRadius: 1 }}>
                    <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>BAA-AAA</Typography>
                    <Typography variant="h6" sx={{ fontWeight: 700, color: "warning.main", mt: 0.5 }}>
                      {formatBasisPoints(creditData?.corporateBond?.value)}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">Quality Spread</Typography>
                  </Box>
                </Grid>
                <Grid item xs={12} sm={6} md={2.4}>
                  <Box sx={{ p: 1.5, backgroundColor: alpha(theme.palette.primary.main, 0.08), borderRadius: 1 }}>
                    <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>AAA YIELD</Typography>
                    <Typography variant="h6" sx={{ fontWeight: 700, color: "primary.main", mt: 0.5 }}>
                      {creditData?.aaaYield?.value?.toFixed(2)}%
                    </Typography>
                    <Typography variant="caption" color="text.secondary">Top Quality Bonds</Typography>
                  </Box>
                </Grid>
                <Grid item xs={12} sm={6} md={2.4}>
                  <Box sx={{ p: 1.5, backgroundColor: alpha(theme.palette.secondary.main, 0.08), borderRadius: 1 }}>
                    <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>VIX</Typography>
                    <Typography variant="h6" sx={{ fontWeight: 700, color: "secondary.main", mt: 0.5 }}>
                      {creditData?.vix?.value?.toFixed(1)}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">Market Fear Index</Typography>
                  </Box>
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </Grid>

        {/* Market Assessment Summary */}
        <Grid item xs={12}>
          <Card>
            <CardHeader title="Credit Market Assessment" />
            <CardContent>
              <Grid container spacing={2}>
                <Grid item xs={12} md={4}>
                  <Box sx={{ p: 2, backgroundColor: alpha(theme.palette.error.main, 0.05), borderRadius: 1 }}>
                    <Typography variant="caption" sx={{ fontWeight: 600, color: "text.secondary", display: "block", mb: 1 }}>
                      STRESS LEVEL
                    </Typography>
                    <Chip
                      label={creditData?.highYield?.value > 600 ? "EXTREME" : creditData?.highYield?.value > 450 ? "HIGH" : "NORMAL"}
                      color={creditData?.highYield?.value > 600 ? "error" : creditData?.highYield?.value > 450 ? "warning" : "success"}
                      size="small"
                    />
                    <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: "block" }}>
                      Based on High Yield OAS level
                    </Typography>
                  </Box>
                </Grid>
                <Grid item xs={12} md={4}>
                  <Box sx={{ p: 2, backgroundColor: alpha(theme.palette.info.main, 0.05), borderRadius: 1 }}>
                    <Typography variant="caption" sx={{ fontWeight: 600, color: "text.secondary", display: "block", mb: 1 }}>
                      SPREAD TREND
                    </Typography>
                    <Chip
                      label={creditData?.highYield?.trend?.change > 0 ? "WIDENING" : "TIGHTENING"}
                      color={creditData?.highYield?.trend?.change > 0 ? "warning" : "success"}
                      size="small"
                    />
                    <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: "block" }}>
                      {creditData?.highYield?.trend?.change > 0 ? "Spreads expanding" : "Spreads contracting"}
                    </Typography>
                  </Box>
                </Grid>
                <Grid item xs={12} md={4}>
                  <Box sx={{ p: 2, backgroundColor: alpha(theme.palette.warning.main, 0.05), borderRadius: 1 }}>
                    <Typography variant="caption" sx={{ fontWeight: 600, color: "text.secondary", display: "block", mb: 1 }}>
                      VOLATILITY
                    </Typography>
                    <Chip
                      label={creditData?.vix?.value > 25 ? "ELEVATED" : "NORMAL"}
                      color={creditData?.vix?.value > 25 ? "warning" : "success"}
                      size="small"
                    />
                    <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: "block" }}>
                      VIX at {creditData?.vix?.value?.toFixed(1)}
                    </Typography>
                  </Box>
                </Grid>
              </Grid>
              <Typography variant="caption" color="text.secondary" sx={{ mt: 3, display: "block" }}>
                Source: Federal Reserve Economic Data (FRED) | Updated: {creditData?.timestamp ? new Date(creditData.timestamp).toLocaleDateString() : 'N/A'}
              </Typography>
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
                  <TableRow key={idx} hover>
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
        leadingIndicators = response;
      } catch (err) {
        console.error("Failed to fetch leading indicators:", err);
        setError("Failed to load economic indicators. Please try again.");
        setLoading(false);
        setRefreshing(false);
        return;
      }

      // Fetch yield curve data
      try {
        const response = await api.get("/api/economic/yield-curve-full");
        yieldCurveFullData = response?.data || null;
        console.log("✅ Yield Curve Data Fetched:", {
          hasCurrentCurve: !!yieldCurveFullData?.currentCurve,
          hasSpreads: !!yieldCurveFullData?.spreads,
          hasHistory: !!yieldCurveFullData?.history,
          data: yieldCurveFullData
        });
      } catch (err) {
        console.warn("❌ Failed to fetch yield curve data:", err?.message || err);
        yieldCurveFullData = null;
      }

      // Fetch credit spreads data
      try {
        const response = await api.get("/api/economic/credit-spreads-full");
        creditSpreadsFullData = response?.data || null;
        console.log("✅ Credit Spreads Data Fetched:", {
          hasCurrentSpreads: !!creditSpreadsFullData?.currentSpreads,
          hasVix: !!creditSpreadsFullData?.vix,
          data: creditSpreadsFullData
        });
      } catch (err) {
        console.warn("❌ Failed to fetch credit spreads data:", err?.message || err);
        creditSpreadsFullData = null;
      }

      // Fetch economic calendar data (optional - use empty defaults if fails)
      try {
        const response = await api.get("/api/economic/calendar");
        economicCalendarData = response?.data?.data || response?.data?.events || [];
        console.log("✅ Economic Calendar Data Fetched:", {
          count: economicCalendarData?.length || 0,
          data: economicCalendarData
        });
      } catch (err) {
        console.warn("❌ Failed to fetch economic calendar:", err?.message || err);
        economicCalendarData = [];
      }

      // Extract data from available endpoints
      const leadData = leadingIndicators?.data || {};

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
          yield: value || 0
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

      // Unemployment stress: 4% = 0 stress, 6% = 50 stress, 8%+ = 100 stress
      if (unrateIndicator?.rawValue) {
        economicStress += Math.min(100, Math.max(0, (unrateIndicator.rawValue - 3.5) * 20));
      }

      // Initial claims stress: 200K = 0, 250K = 25, 300K+ = 100
      if (icsaIndicator?.rawValue) {
        economicStress += Math.min(100, Math.max(0, (icsaIndicator.rawValue / 1000 - 200) * 2));
      }

      // Yield curve stress: inverted = +25 points
      const yieldCurveSpread = yieldCurveFullData?.spreads?.T10Y2Y || 0;
      if (yieldCurveSpread < 0) {
        economicStress += 25;
      }

      // Average out the score
      economicStress = Math.min(100, Math.max(0, economicStress / 3));

      // Calculate Credit Stress Index (0-100 scale) from credit spreads data
      let creditStress = 0;
      if (creditSpreadsFullData?.currentSpreads) {
        const hyOas = creditSpreadsFullData.currentSpreads.highYield?.value || 0;
        const igOas = creditSpreadsFullData.currentSpreads.investmentGrade?.value || 0;

        // HY OAS stress: 300 bps = 25, 400 = 50, 600+ = 100
        creditStress += Math.min(100, Math.max(0, (hyOas - 300) / 3));

        // IG OAS stress: 100 bps = 25, 150 = 50, 250+ = 100
        creditStress += Math.min(100, Math.max(0, (igOas - 100) / 1.5));

        // VIX stress: 15 = 0, 20 = 25, 30+ = 100
        const vix = creditSpreadsFullData.vix?.value || 0;
        creditStress += Math.min(100, Math.max(0, (vix - 15) * 5));

        // Average out
        creditStress = Math.min(100, Math.max(0, creditStress / 3));
      }

      const combinedData = {
        // Recession data - CALCULATED from real indicators
        recessionProbability: Math.round((economicStress + creditStress) / 2 * 0.5),
        riskLevel: economicStress > 60 ? "High" : economicStress > 30 ? "Moderate" : "Low",
        riskIndicator: economicStress > 60 ? "🔴" : economicStress > 30 ? "🟡" : "🟢",
        economicStressIndex: Math.round(economicStress),
        forecastModels: [],
        recessionAnalysis: { summary: economicStress > 60 ? "Economic stress indicators elevated - monitor labor market and yield curve closely." : "Economic indicators show mixed signals." },
        keyRecessionIndicators: {},

        // Leading indicators - THIS IS WHAT WE HAVE
        leadingIndicators: leadData.indicators || [],
        gdpGrowth: leadData.gdpGrowth || 0,
        unemployment: leadData.unemployment || 0,
        inflation: leadData.inflation || 0,
        employment: leadData.employment || {},

        // Yield curve - NEW: full data from dedicated endpoint
        yieldCurveFullData: {
          ...yieldCurveFullData,
          history: transformedYieldHistory // Use transformed history with maturity keys
        },
        yieldCurveData: processedYieldCurveData,
        yieldCurve: yieldCurveFullData ? {
          isInverted: (yieldCurveFullData.spreads?.T10Y2Y || 0) < 0,
          spread: yieldCurveFullData.spreads?.T10Y2Y || 0,
          averageLeadTime: 12
        } : {},

        // Credit spreads - NEW: full data from dedicated endpoint
        creditSpreadsFullData: creditSpreadsFullData,
        creditSpreads: processedCreditSpreads,
        creditStressIndex: Math.round(creditStress),
        financialConditionsIndex: {
          value: creditStress > 60 ? 'HIGH' : creditStress > 30 ? 'MODERATE' : 'NORMAL',
          level: creditStress > 60 ? 'Stressed' : creditStress > 30 ? 'Caution' : 'Healthy'
        },

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
          <CreditMarketPanel data={economicData} isLoading={false} theme={theme} />
          <EconomicCalendarPanel events={economicData.upcomingEvents} isLoading={false} />
        </>
      )}
    </Container>
  );
}
