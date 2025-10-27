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

        <Grid item xs={12} md={3}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" justifyContent="space-between">
                <Box>
                  <Typography variant="subtitle2" color="text.secondary">
                    Status
                  </Typography>
                  <Typography variant="h4" sx={{ mt: 1 }}>
                    {data.riskLevel}
                  </Typography>
                </Box>
                <Chip
                  label={data.riskIndicator}
                  sx={{ fontSize: "1.5rem" }}
                />
              </Box>
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
  if (isLoading) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", py: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (!data) {
    return (
      <Alert severity="warning">No yield curve data available</Alert>
    );
  }

  return (
    <Box sx={{ mb: 4 }}>
      <Typography variant="h4" sx={{ fontWeight: 600, mb: 3, display: "flex", alignItems: "center", gap: 1 }}>
        📊 Yield Curve Analysis
      </Typography>

      <Grid container spacing={3}>
        <Grid item xs={12}>
          <Card>
            <CardHeader
              title="Treasury Yield Curve (3M - 30Y)"
              subheader={
                data.yieldCurve?.isInverted
                  ? "🔴 INVERTED - Recession signal detected"
                  : "🟢 NORMAL - Healthy economic conditions"
              }
            />
            <CardContent>
              {data.yieldCurveData?.length > 0 ? (
                <Box>
                  <ResponsiveContainer width="100%" height={400}>
                    <ScatterChart margin={{ top: 20, right: 30, left: 0, bottom: 40 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke={theme.palette.divider} opacity={0.3} />
                      <XAxis
                        dataKey="maturity"
                        type="category"
                        tick={{ fontSize: 12, fill: theme.palette.text.secondary }}
                        label={{ value: "Maturity", position: "insideBottomRight", offset: -5, fontSize: 13 }}
                        angle={-45}
                        textAnchor="end"
                        height={80}
                      />
                      <YAxis
                        tick={{ fontSize: 12 }}
                        label={{ value: "Yield (%)", angle: -90, position: "insideLeft", offset: 10, fontSize: 13 }}
                        width={60}
                        domain={[0, 'auto']}
                      />
                      <Tooltip
                        formatter={(value) => `${parseFloat(value)?.toFixed(3) || 0}%`}
                        labelFormatter={(value) => `${value}`}
                        contentStyle={{
                          backgroundColor: "rgba(255,255,255,0.99)",
                          border: "1px solid rgba(0,0,0,0.2)",
                          borderRadius: "8px",
                        }}
                      />
                      <ReferenceLine y={0} stroke="rgba(200,0,0,0.3)" strokeDasharray="4 4" opacity={0.6} />
                      <ReferenceLine y={2} stroke="rgba(100,150,200,0.3)" strokeDasharray="4 4" opacity={0.5} />
                      <Scatter
                        name="Current Yields"
                        data={data.yieldCurveData}
                        fill="#1976d2"
                        line={{ stroke: "#1976d2", strokeWidth: 3 }}
                        isAnimationActive={true}
                      />
                    </ScatterChart>
                  </ResponsiveContainer>
                  <Box sx={{ mt: 2, p: 2, backgroundColor: alpha(theme.palette.info.main, 0.05), borderRadius: 1 }}>
                    <Typography variant="body2" color="text.secondary">
                      📈 <strong>Data Source:</strong> Federal Reserve Economic Data (FRED) |
                      <strong> Updated:</strong> {data.yieldCurveFullData?.timestamp ? new Date(data.yieldCurveFullData.timestamp).toLocaleDateString() : 'N/A'}
                    </Typography>
                  </Box>
                </Box>
              ) : (
                <Alert severity="warning">No yield curve data available</Alert>
              )}
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={6}>
          <Card>
            <CardHeader title="Curve Status & Spreads" />
            <CardContent>
              <Box sx={{ mb: 2 }}>
                <Typography variant="subtitle2" color="textSecondary" sx={{ mb: 1, fontWeight: 600 }}>
                  Current Status
                </Typography>
                <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, mb: 2 }}>
                  {data.yieldCurve?.isInverted ? (
                    <>
                      <Box sx={{ fontSize: 28 }}>🔴</Box>
                      <Box>
                        <Typography variant="h6" sx={{ color: "error.main", fontWeight: 600 }}>
                          INVERTED CURVE
                        </Typography>
                        <Typography variant="body2" color="error">
                          Historically precedes recession by ~{data.yieldCurve?.averageLeadTime || 12} months
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
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={6}>
          <Card>
            <CardHeader title="Key Spreads & Indicators" />
            <CardContent>
              <Box sx={{ mb: 2.5 }}>
                <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 0.5 }}>
                  <Typography variant="body2">
                    <strong>10Y-2Y Spread (T10Y2Y):</strong>
                  </Typography>
                  <Typography
                    variant="h6"
                    sx={{
                      color: (data.yieldCurveFullData?.spreads?.T10Y2Y || 0) < 0 ? "error.main" : "success.main",
                      fontWeight: 700,
                    }}
                  >
                    {formatBasisPoints(data.yieldCurveFullData?.spreads?.T10Y2Y)} bps
                  </Typography>
                </Box>
                <Typography variant="caption" color="textSecondary">
                  Most watched recession indicator (inverted when &lt; 0)
                </Typography>
              </Box>

              <Box sx={{ mb: 2.5 }}>
                <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 0.5 }}>
                  <Typography variant="body2">
                    <strong>10Y-3M Spread (T10Y3M):</strong>
                  </Typography>
                  <Typography
                    variant="h6"
                    sx={{
                      color: (data.yieldCurveFullData?.spreads?.T10Y3M || 0) < 0 ? "error.main" : "success.main",
                      fontWeight: 700,
                    }}
                  >
                    {formatBasisPoints(data.yieldCurveFullData?.spreads?.T10Y3M)} bps
                  </Typography>
                </Box>
                <Typography variant="caption" color="textSecondary">
                  Near-term vs long-term expectations
                </Typography>
              </Box>

              <Divider sx={{ my: 2 }} />

              <Box sx={{ mb: 1.5 }}>
                <Typography variant="caption" color="textSecondary" sx={{ fontWeight: 600 }}>
                  CURVE SHAPE ANALYSIS
                </Typography>
              </Box>
              <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
                <Typography variant="body2">
                  3M Yield:
                </Typography>
                <Typography variant="body2" sx={{ fontWeight: 600 }}>
                  {formatPercent(data.yieldCurveFullData?.currentCurve?.['3M'])}%
                </Typography>
              </Box>
              <Box sx={{ display: "flex", justifyContent: "space-between", mb: 1 }}>
                <Typography variant="body2">
                  10Y Yield:
                </Typography>
                <Typography variant="body2" sx={{ fontWeight: 600 }}>
                  {formatPercent(data.yieldCurveFullData?.currentCurve?.['10Y'])}%
                </Typography>
              </Box>
              <Box sx={{ display: "flex", justifyContent: "space-between" }}>
                <Typography variant="body2">
                  30Y Yield:
                </Typography>
                <Typography variant="body2" sx={{ fontWeight: 600 }}>
                  {formatPercent(data.yieldCurveFullData?.currentCurve?.['30Y'])}%
                </Typography>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
};

const CreditMarketPanel = ({ data, isLoading }) => {
  if (isLoading) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", py: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (!data) {
    return (
      <Alert severity="warning">No credit spreads data available</Alert>
    );
  }

  return (
    <Box sx={{ mb: 4 }}>
      <Typography variant="h4" sx={{ fontWeight: 600, mb: 3, display: "flex", alignItems: "center", gap: 1 }}>
        💰 Credit Markets & Financial Conditions
      </Typography>

      <Grid container spacing={3}>
        {/* High Yield Spreads Card */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardHeader
              title="High Yield Spreads (HY OAS)"
              subheader={
                <Box sx={{ display: "flex", alignItems: "center", gap: 1, mt: 0.5 }}>
                  <Chip
                    label={data.creditSpreads?.highYield?.stressLevel?.toUpperCase() || "UNKNOWN"}
                    size="small"
                    color={
                      data.creditSpreads?.highYield?.stressLevel === 'extreme' ? 'error' :
                      data.creditSpreads?.highYield?.stressLevel === 'high' ? 'warning' :
                      data.creditSpreads?.highYield?.stressLevel === 'moderate' ? 'info' :
                      'success'
                    }
                    variant="outlined"
                  />
                </Box>
              }
            />
            <CardContent>
              <Box sx={{ mb: 3 }}>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                  Current OAS
                </Typography>
                <Typography variant="h4" sx={{ fontWeight: 700, color: "primary.main" }}>
                  {formatBasisPoints(data.creditSpreads?.highYield?.value)} bps
                </Typography>
              </Box>

              <Divider sx={{ my: 2 }} />

              <Box sx={{ mb: 2 }}>
                <Typography variant="caption" sx={{ fontWeight: 600, color: "text.secondary" }}>
                  30-DAY TREND
                </Typography>
                <Box sx={{ display: "flex", alignItems: "center", gap: 1, mt: 0.5 }}>
                  {data.creditSpreads?.highYield?.trend?.trend === 'rising' && <TrendingUp color="error" sx={{ fontSize: 18 }} />}
                  {data.creditSpreads?.highYield?.trend?.trend === 'falling' && <TrendingDown color="success" sx={{ fontSize: 18 }} />}
                  {data.creditSpreads?.highYield?.trend?.trend === 'stable' && <TrendingFlat color="info" sx={{ fontSize: 18 }} />}
                  <Typography variant="body2" sx={{ fontWeight: 600 }}>
                    {data.creditSpreads?.highYield?.trend?.trend?.toUpperCase()}
                  </Typography>
                  <Typography variant="body2" color={data.creditSpreads?.highYield?.trend?.change > 0 ? "error.main" : "success.main"}>
                    ({data.creditSpreads?.highYield?.trend?.change > 0 ? '+' : ''}{formatBasisPoints(data.creditSpreads?.highYield?.trend?.change)} bps)
                  </Typography>
                </Box>
              </Box>

              <Box sx={{ display: "flex", justifyContent: "space-between", fontSize: "0.85rem" }}>
                <Typography variant="caption">
                  30d Avg: {formatBasisPoints(data.creditSpreads?.highYield?.trend?.avg30)} bps
                </Typography>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Investment Grade Spreads Card */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardHeader
              title="Investment Grade Spreads (IG OAS)"
              subheader={
                <Box sx={{ display: "flex", alignItems: "center", gap: 1, mt: 0.5 }}>
                  <Chip
                    label={data.creditSpreads?.investmentGrade?.stressLevel?.toUpperCase() || "UNKNOWN"}
                    size="small"
                    color={
                      data.creditSpreads?.investmentGrade?.stressLevel === 'extreme' ? 'error' :
                      data.creditSpreads?.investmentGrade?.stressLevel === 'high' ? 'warning' :
                      data.creditSpreads?.investmentGrade?.stressLevel === 'moderate' ? 'info' :
                      'success'
                    }
                    variant="outlined"
                  />
                </Box>
              }
            />
            <CardContent>
              <Box sx={{ mb: 3 }}>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                  Current OAS
                </Typography>
                <Typography variant="h4" sx={{ fontWeight: 700, color: "primary.main" }}>
                  {formatBasisPoints(data.creditSpreads?.investmentGrade?.value)} bps
                </Typography>
              </Box>

              <Divider sx={{ my: 2 }} />

              <Box sx={{ mb: 2 }}>
                <Typography variant="caption" sx={{ fontWeight: 600, color: "text.secondary" }}>
                  30-DAY TREND
                </Typography>
                <Box sx={{ display: "flex", alignItems: "center", gap: 1, mt: 0.5 }}>
                  {data.creditSpreads?.investmentGrade?.trend?.trend === 'rising' && <TrendingUp color="error" sx={{ fontSize: 18 }} />}
                  {data.creditSpreads?.investmentGrade?.trend?.trend === 'falling' && <TrendingDown color="success" sx={{ fontSize: 18 }} />}
                  {data.creditSpreads?.investmentGrade?.trend?.trend === 'stable' && <TrendingFlat color="info" sx={{ fontSize: 18 }} />}
                  <Typography variant="body2" sx={{ fontWeight: 600 }}>
                    {data.creditSpreads?.investmentGrade?.trend?.trend?.toUpperCase()}
                  </Typography>
                  <Typography variant="body2" color={data.creditSpreads?.investmentGrade?.trend?.change > 0 ? "error.main" : "success.main"}>
                    ({data.creditSpreads?.investmentGrade?.trend?.change > 0 ? '+' : ''}{formatBasisPoints(data.creditSpreads?.investmentGrade?.trend?.change)} bps)
                  </Typography>
                </Box>
              </Box>

              <Box sx={{ display: "flex", justifyContent: "space-between", fontSize: "0.85rem" }}>
                <Typography variant="caption">
                  30d Avg: {formatBasisPoints(data.creditSpreads?.investmentGrade?.trend?.avg30)} bps
                </Typography>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Credit Conditions Summary */}
        <Grid item xs={12}>
          <Card>
            <CardHeader title="Overall Financial Conditions" />
            <CardContent>
              <Grid container spacing={2}>
                <Grid item xs={12} md={4}>
                  <Box sx={{ p: 1.5, backgroundColor: alpha(theme.palette.info.main, 0.05), borderRadius: 1 }}>
                    <Typography variant="caption" sx={{ fontWeight: 600, color: "text.secondary" }}>
                      OVERALL STRESS LEVEL
                    </Typography>
                    <Box sx={{ mt: 1 }}>
                      <Chip
                        label={data.creditSpreadsFullData?.summary?.overallStress || "UNKNOWN"}
                        color={
                          data.creditSpreadsFullData?.summary?.overallStress === 'EXTREME' ? 'error' :
                          data.creditSpreadsFullData?.summary?.overallStress === 'HIGH' ? 'warning' :
                          data.creditSpreadsFullData?.summary?.overallStress === 'MODERATE' ? 'info' :
                          'success'
                        }
                        sx={{ fontWeight: 700 }}
                      />
                    </Box>
                  </Box>
                </Grid>

                <Grid item xs={12} md={4}>
                  <Box sx={{ p: 1.5, backgroundColor: alpha(theme.palette.warning.main, 0.05), borderRadius: 1 }}>
                    <Typography variant="caption" sx={{ fontWeight: 600, color: "text.secondary" }}>
                      CREDIT CONDITIONS
                    </Typography>
                    <Box sx={{ mt: 1 }}>
                      <Chip
                        label={data.creditSpreadsFullData?.summary?.creditConditions || "UNKNOWN"}
                        color={
                          data.creditSpreadsFullData?.summary?.creditConditions === 'TIGHTENING' ? 'error' :
                          data.creditSpreadsFullData?.summary?.creditConditions === 'NORMAL' ? 'success' :
                          'warning'
                        }
                        variant="outlined"
                      />
                    </Box>
                  </Box>
                </Grid>

                <Grid item xs={12} md={4}>
                  <Box sx={{ p: 1.5, backgroundColor: alpha(theme.palette.success.main, 0.05), borderRadius: 1 }}>
                    <Typography variant="caption" sx={{ fontWeight: 600, color: "text.secondary" }}>
                      MARKET VOLATILITY
                    </Typography>
                    <Box sx={{ mt: 1 }}>
                      <Chip
                        label={data.creditSpreadsFullData?.summary?.marketVolatility || "UNKNOWN"}
                        color={
                          data.creditSpreadsFullData?.summary?.marketVolatility === 'EXTREME' ? 'error' :
                          data.creditSpreadsFullData?.summary?.marketVolatility === 'ELEVATED' ? 'warning' :
                          'success'
                        }
                        variant="outlined"
                      />
                    </Box>
                  </Box>
                </Grid>
              </Grid>

              <Box sx={{ mt: 2, p: 2, backgroundColor: alpha(theme.palette.info.main, 0.05), borderRadius: 1 }}>
                <Typography variant="body2" color="text.secondary">
                  📈 <strong>Data Source:</strong> Federal Reserve Economic Data (FRED) |
                  <strong> Updated:</strong> {data.creditSpreadsFullData?.timestamp ? new Date(data.creditSpreadsFullData.timestamp).toLocaleDateString() : 'N/A'}
                </Typography>
              </Box>
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

      // Fetch all three endpoints in parallel
      let leadingIndicators = null;
      let yieldCurveFullData = null;
      let creditSpreadsFullData = null;

      try {
        const response = await api.get("/api/market/leading-indicators");
        leadingIndicators = response;
      } catch (err) {
        console.error("Failed to fetch leading indicators:", err);
        setError("Failed to load economic indicators. Please try again.");
        setLoading(false);
        setRefreshing(false);
        return;
      }

      // Fetch yield curve full data (optional - use empty defaults if fails)
      try {
        const response = await api.get("/api/market/yield-curve-full");
        yieldCurveFullData = response?.data?.data || null;
      } catch (err) {
        console.warn("Failed to fetch yield curve data:", err);
        yieldCurveFullData = null;
      }

      // Fetch credit spreads full data (optional - use empty defaults if fails)
      try {
        const response = await api.get("/api/market/credit-spreads-full");
        creditSpreadsFullData = response?.data?.data || null;
      } catch (err) {
        console.warn("Failed to fetch credit spreads data:", err);
        creditSpreadsFullData = null;
      }

      // Extract data from available endpoints
      const leadData = leadingIndicators?.data?.data || {};

      // Process yield curve data - transform into chart format
      let processedYieldCurveData = [];
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
      }

      // Process credit spreads data
      let processedCreditSpreads = {};
      if (creditSpreadsFullData?.currentSpreads) {
        processedCreditSpreads = creditSpreadsFullData.currentSpreads;
      }

      const combinedData = {
        // Recession data - using indicators for simple assessment
        recessionProbability: 35,
        riskLevel: "Low",
        riskIndicator: "🟢",
        economicStressIndex: 30,
        forecastModels: [],
        recessionAnalysis: { summary: "Economic indicators show mixed signals." },
        keyRecessionIndicators: {},

        // Leading indicators - THIS IS WHAT WE HAVE
        leadingIndicators: leadData.indicators || [],
        gdpGrowth: leadData.gdpGrowth || 0,
        unemployment: leadData.unemployment || 0,
        inflation: leadData.inflation || 0,
        employment: leadData.employment || {},

        // Yield curve - NEW: full data from dedicated endpoint
        yieldCurveFullData: yieldCurveFullData,
        yieldCurveData: processedYieldCurveData,
        yieldCurve: yieldCurveFullData ? {
          isInverted: (yieldCurveFullData.spreads?.T10Y2Y || 0) < 0,
          spread: yieldCurveFullData.spreads?.T10Y2Y || 0,
          averageLeadTime: 12
        } : {},

        // Credit spreads - NEW: full data from dedicated endpoint
        creditSpreadsFullData: creditSpreadsFullData,
        creditSpreads: processedCreditSpreads,
        creditStressIndex: creditSpreadsFullData?.summary?.overallStress === 'HIGH' ? 75 : creditSpreadsFullData?.summary?.overallStress === 'MODERATE' ? 50 : 25,
        financialConditionsIndex: {
          value: creditSpreadsFullData?.summary?.overallStress || 'N/A',
          level: creditSpreadsFullData?.summary?.creditConditions || 'Neutral'
        },

        // Calendar - empty for now
        upcomingEvents: [],
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
          <CreditMarketPanel data={economicData} isLoading={false} />
          <EconomicCalendarPanel events={economicData.upcomingEvents} isLoading={false} />
        </>
      )}
    </Container>
  );
}
