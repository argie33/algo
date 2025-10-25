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
  Refresh,
} from "@mui/icons-material";
import {
  LineChart,
  Line,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  ReferenceLine,
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
        📊 Recession Risk Assessment
      </Typography>

      <Grid container spacing={3}>
        {/* Key Metrics Summary */}
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
                Economic Stress Index
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
                Credit Stress Index
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
                    Risk Level
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

        {/* Main Analysis */}
        <Grid item xs={12} md={8}>
          <Card>
            <CardHeader
              title="Advanced Recession Probability Model"
              subheader="Multi-factor analysis: Yield Curve (35%), Credit Spreads (25%), Labor Market (20%), Monetary Policy (15%), Volatility (5%)"
            />
            <CardContent>
              <Typography variant="h6" gutterBottom>
                {data.riskIndicator} {data.recessionProbability}% Probability
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
                sx={{ mb: 3, height: 12 }}
              />
              <Typography variant="body1" paragraph>
                {data.recessionAnalysis?.summary || "No summary available"}
              </Typography>
              <Divider sx={{ my: 2 }} />
              <Typography variant="h6" gutterBottom>
                📊 Analysis Factors
              </Typography>
              <Box sx={{ mb: 2 }}>
                {data.recessionAnalysis?.factors?.map((factor, idx) => (
                  <Typography key={idx} variant="body2" sx={{ mb: 1 }}>
                    • {factor}
                  </Typography>
                ))}
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Forecast Models */}
        <Grid item xs={12} md={4}>
          <Card>
            <CardHeader title="Forecast Models" titleTypographyProps={{ variant: "h6" }} />
            <CardContent>
              {data.forecastModels?.map((model, idx) => (
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
                            tick={{ fontSize: 11, fill: theme.palette.text.secondary }}
                            axisLine={{ stroke: alpha(theme.palette.divider, 0.2) }}
                            interval={Math.floor(indicator.history.length / 6)}
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
      {renderIndicatorGrid(secondaryIndicators, "Secondary Indicators", <TrendingDown />)}
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
              title="Treasury Yield Curve"
              subheader={
                data.yieldCurve?.isInverted
                  ? "🔴 INVERTED - Recession signal detected"
                  : "🟢 NORMAL - Healthy economic conditions"
              }
            />
            <CardContent>
              {data.yieldCurveData?.length > 0 ? (
                <ResponsiveContainer width="100%" height={400}>
                  <AreaChart data={data.yieldCurveData} margin={{ top: 10, right: 30, left: 0, bottom: 40 }}>
                    <defs>
                      <linearGradient id="yieldGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#1976d2" stopOpacity={0.4} />
                        <stop offset="100%" stopColor="#1976d2" stopOpacity={0.05} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke={theme.palette.divider} opacity={0.3} />
                    <XAxis
                      dataKey="maturity"
                      tick={{ fontSize: 12, fill: theme.palette.text.secondary }}
                      label={{ value: "Maturity (3M → 30Y)", position: "insideBottomRight", offset: -10, fontSize: 13 }}
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
                      labelFormatter={(value) => `Maturity: ${value}`}
                      contentStyle={{
                        backgroundColor: "rgba(255,255,255,0.99)",
                        border: "1px solid rgba(0,0,0,0.2)",
                        borderRadius: "8px",
                      }}
                    />
                    <ReferenceLine y={0} stroke="rgba(200,0,0,0.3)" strokeDasharray="4 4" opacity={0.6} />
                    <ReferenceLine y={2} stroke="rgba(100,150,200,0.3)" strokeDasharray="4 4" opacity={0.5} />
                    <Area
                      type="monotone"
                      dataKey="yield"
                      stroke="#1976d2"
                      strokeWidth={3.5}
                      fill="url(#yieldGradient)"
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

        <Grid item xs={12} md={6}>
          <Card>
            <CardHeader title="Curve Status" />
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
            <CardHeader title="Key Spreads" />
            <CardContent>
              <Box sx={{ mb: 2.5 }}>
                <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 0.5 }}>
                  <Typography variant="body2">
                    <strong>2Y-10Y Spread:</strong>
                  </Typography>
                  <Typography
                    variant="h6"
                    sx={{
                      color: data.yieldCurve?.spread2y10y < 0 ? "error.main" : "success.main",
                      fontWeight: 700,
                    }}
                  >
                    {formatBasisPoints(data.yieldCurve?.spread2y10y)} bps
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
                      color: data.yieldCurve?.spread3m10y < 0 ? "error.main" : "success.main",
                      fontWeight: 700,
                    }}
                  >
                    {formatBasisPoints(data.yieldCurve?.spread3m10y)} bps
                  </Typography>
                </Box>
                <Typography variant="caption" color="textSecondary">
                  Near-term vs long-term expectations
                </Typography>
              </Box>

              <Divider sx={{ my: 2 }} />

              <Box sx={{ display: "flex", justifyContent: "space-between" }}>
                <Typography variant="body2">
                  <strong>Historical Accuracy:</strong>
                </Typography>
                <Chip
                  label={`${data.yieldCurve?.historicalAccuracy}%`}
                  color={data.yieldCurve?.historicalAccuracy > 75 ? "success" : "warning"}
                  variant="outlined"
                  size="small"
                />
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
        <Grid item xs={12} md={6}>
          <Card>
            <CardHeader title="High Yield Spreads" />
            <CardContent>
              <Typography variant="h4" color="primary" gutterBottom>
                {data.creditSpreads?.highYield?.oas || "N/A"} bps
              </Typography>
              <Chip
                label={data.creditSpreads?.highYield?.signal || "N/A"}
                size="small"
                sx={{ mb: 2 }}
              />
              <Typography variant="body2" color="text.secondary">
                {data.creditSpreads?.highYield?.historicalContext}
              </Typography>
              <Divider sx={{ my: 2 }} />
              <Typography variant="body2">
                <strong>BB-Rated:</strong> {data.creditSpreads?.highYieldByRating?.bbRated?.oas || "N/A"} bps
              </Typography>
              <Typography variant="body2">
                <strong>B-Rated:</strong> {data.creditSpreads?.highYieldByRating?.bRated?.oas || "N/A"} bps
              </Typography>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={6}>
          <Card>
            <CardHeader title="Investment Grade Spreads" />
            <CardContent>
              <Typography variant="h4" color="primary" gutterBottom>
                {data.creditSpreads?.investmentGrade?.oas || "N/A"} bps
              </Typography>
              <Chip
                label={data.creditSpreads?.investmentGrade?.signal || "N/A"}
                size="small"
                sx={{ mb: 2 }}
              />
              <Divider sx={{ my: 2 }} />
              <Typography variant="body2">
                <strong>AAA-Rated:</strong> {data.creditSpreads?.investmentGradeByRating?.aaaRated?.oas || "N/A"} bps
              </Typography>
              <Typography variant="body2">
                <strong>BBB-Rated:</strong> {data.creditSpreads?.investmentGradeByRating?.bbbRated?.oas || "N/A"} bps
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
                  {data.financialConditionsIndex?.value || "N/A"}
                </Typography>
                <Typography variant="body2">
                  Level: {data.financialConditionsIndex?.level || "Neutral"}
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

  // Fetch all economic data with Promise.allSettled for graceful failures
  const fetchEconomicData = async () => {
    try {
      setLoading(true);
      setError(null);

      const results = await Promise.allSettled([
        api.get("/api/market/recession-forecast"),
        api.get("/api/market/leading-indicators"),
        api.get("/api/market/credit-spreads"),
        api.get("/api/market/calendar"),
      ]);

      const [recessionForecast, leadingIndicators, creditSpreads, calendar] = results.map(
        (result) => (result.status === "fulfilled" ? result.value : null)
      );

      // Check for critical errors
      const criticalErrors = results
        .map((r, i) => r.status === "rejected" ? i : null)
        .filter(i => i !== null);

      if (criticalErrors.length > 0) {
        const errorNames = ["recession-forecast", "leading-indicators", "credit-spreads", "calendar"]
          .filter((_, i) => criticalErrors.includes(i));
        setError(`Failed to load: ${errorNames.join(", ")}. Please try again.`);
        setEconomicData(null);
        setLoading(false);
        setRefreshing(false);
        return;
      }

      // Extract data
      const recessData = recessionForecast?.data?.data || {};
      const leadData = leadingIndicators?.data?.data || {};
      const creditData = creditSpreads?.data?.data || {};
      const calendarEvents = calendar?.data?.data || [];

      const combinedData = {
        // Recession data
        recessionProbability: recessData.compositeRecessionProbability || 0,
        riskLevel: recessData.riskLevel || "Medium",
        riskIndicator: recessData.riskIndicator || "🟢",
        economicStressIndex: recessData.economicStressIndex || 0,
        forecastModels: recessData.forecastModels || [],
        recessionAnalysis: recessData.analysis || {},
        keyRecessionIndicators: recessData.keyIndicators || {},

        // Leading indicators
        leadingIndicators: leadData.indicators || [],
        gdpGrowth: leadData.gdpGrowth || 0,
        unemployment: leadData.unemployment || 0,
        inflation: leadData.inflation || 0,
        employment: leadData.employment || {},

        // Yield curve
        yieldCurve: leadData.yieldCurve || {},
        yieldCurveData: leadData.yieldCurveData || [],

        // Credit spreads
        creditSpreads: creditData.spreads || {},
        creditStressIndex: creditData.creditStressIndex || 0,
        financialConditionsIndex: creditData.financialConditionsIndex || {},

        // Calendar
        upcomingEvents: calendarEvents || [],
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
