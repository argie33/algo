import { useMemo } from "react";
import {
  Box,
  Card,
  CardContent,
  Divider,
  Paper,
  Typography,
  Chip,
  alpha,
  useTheme,
} from "@mui/material";
import { TrendingUp, ShowChart } from "@mui/icons-material";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  Legend,
  ReferenceLine,
  AreaChart,
  Area,
} from "recharts";
import { format } from "date-fns";

const SentimentChartsReimag = ({
  aaii_data,
  fearGreed_data,
  naaim_data,
}) => {
  const theme = useTheme();

  // Professional color palette matching site style
  const chartColors = {
    bullish: "#10b981",      // Green
    neutral: "#f59e0b",      // Amber/Gold
    bearish: "#ef4444",      // Red
    fearGreed: "#f43f5e",    // Rose
    naaim: "#3b82f6",        // Blue
    grid: alpha(theme.palette.divider, 0.15),
    gridDark: alpha(theme.palette.divider, 0.35),
  };

  // Format date for display
  const formatDate = (dateString) => {
    if (!dateString) return "";
    try {
      return format(new Date(dateString), "MMM dd");
    } catch {
      return dateString;
    }
  };

  // Format tooltip date
  const formatTooltipDate = (dateString) => {
    if (!dateString) return "";
    try {
      return format(new Date(dateString), "MMM dd, yyyy");
    } catch {
      return dateString;
    }
  };

  // Process and clean AAII data (handle gaps)
  const processedAAIIData = useMemo(() => {
    if (!aaii_data?.length) return [];
    return aaii_data
      .map(item => ({
        ...item,
        date: item.date || item.timestamp,
        aaii_bullish: parseFloat(item.bullish) || null,
        aaii_neutral: parseFloat(item.neutral) || null,
        aaii_bearish: parseFloat(item.bearish) || null,
      }))
      .filter(item => item.aaii_bullish !== null || item.aaii_neutral !== null || item.aaii_bearish !== null)
      .sort((a, b) => new Date(a.date) - new Date(b.date));
  }, [aaii_data]);

  // Process Fear & Greed data
  const processedFearGreedData = useMemo(() => {
    if (!fearGreed_data?.length) return [];
    return fearGreed_data
      .map(item => ({
        ...item,
        date: item.date || item.timestamp,
        fear_greed: parseFloat(item.value || item.fear_greed) || null,
      }))
      .filter(item => item.fear_greed !== null)
      .sort((a, b) => new Date(a.date) - new Date(b.date));
  }, [fearGreed_data]);

  // Process NAAIM data - properly handle bullish/bearish split
  const processedNAAIMData = useMemo(() => {
    if (!naaim_data?.length) return [];
    return naaim_data
      .map(item => ({
        ...item,
        date: item.date || item.timestamp,
        naaim_bullish: parseFloat(item.bullish_exposure || item.bullish) || 0,
        naaim_bearish: parseFloat(item.bearish_exposure || item.bearish) || 0,
        // Net exposure: bullish - bearish (ranges from -100 to +100)
        naaim_net: (parseFloat(item.bullish_exposure || item.bullish) || 0) - (parseFloat(item.bearish_exposure || item.bearish) || 0),
      }))
      .filter(item => item.naaim_bullish !== null || item.naaim_bearish !== null)
      .sort((a, b) => new Date(a.date) - new Date(b.date));
  }, [naaim_data]);

  // Get latest values for summary cards
  const latestAAII = processedAAIIData[processedAAIIData.length - 1];
  const latestFearGreed = processedFearGreedData[processedFearGreedData.length - 1];

  // Custom tooltip for better display
  const CustomAAIITooltip = ({ active, payload, label }) => {
    if (active && payload?.length) {
      return (
        <Paper
          elevation={3}
          sx={{
            backgroundColor: alpha(theme.palette.background.paper, 0.98),
            border: `1px solid ${theme.palette.divider}`,
            borderRadius: 1,
            p: 1.5,
          }}
        >
          <Typography variant="caption" sx={{ fontWeight: 600, display: "block", mb: 0.5 }}>
            {formatTooltipDate(label)}
          </Typography>
          {payload.map((entry, index) => (
            <Typography key={index} variant="caption" sx={{ color: entry.color, display: "block" }}>
              {entry.name}: {entry.value?.toFixed(1) || "N/A"}%
            </Typography>
          ))}
        </Paper>
      );
    }
    return null;
  };

  const CustomFearGreedTooltip = ({ active, payload, label }) => {
    if (active && payload?.length) {
      const value = payload[0].value;
      let sentiment = "";
      if (value >= 75) sentiment = "Extreme Greed";
      else if (value >= 55) sentiment = "Greed";
      else if (value >= 45) sentiment = "Neutral";
      else if (value >= 25) sentiment = "Fear";
      else sentiment = "Extreme Fear";

      return (
        <Paper
          elevation={3}
          sx={{
            backgroundColor: alpha(theme.palette.background.paper, 0.98),
            border: `1px solid ${theme.palette.divider}`,
            borderRadius: 1,
            p: 1.5,
          }}
        >
          <Typography variant="caption" sx={{ fontWeight: 600, display: "block", mb: 0.5 }}>
            {formatTooltipDate(label)}
          </Typography>
          <Typography variant="caption" sx={{ display: "block" }}>
            Index: {value?.toFixed(1) || "N/A"}
          </Typography>
          <Typography variant="caption" sx={{ color: chartColors.fearGreed, fontWeight: 600 }}>
            {sentiment}
          </Typography>
        </Paper>
      );
    }
    return null;
  };

  const CustomNAAIMTooltip = ({ active, payload, label }) => {
    if (active && payload?.length) {
      return (
        <Paper
          elevation={3}
          sx={{
            backgroundColor: alpha(theme.palette.background.paper, 0.98),
            border: `1px solid ${theme.palette.divider}`,
            borderRadius: 1,
            p: 1.5,
          }}
        >
          <Typography variant="caption" sx={{ fontWeight: 600, display: "block", mb: 0.5 }}>
            {formatTooltipDate(label)}
          </Typography>
          {payload.map((entry, index) => (
            <Typography key={index} variant="caption" sx={{ color: entry.color, display: "block" }}>
              {entry.name}: {entry.value?.toFixed(1) || "N/A"}%
            </Typography>
          ))}
        </Paper>
      );
    }
    return null;
  };

  // Empty state
  if (!processedAAIIData.length && !processedFearGreedData.length && !processedNAAIMData.length) {
    return (
      <Card sx={{ boxShadow: 2 }}>
        <CardContent sx={{ py: 4, textAlign: "center" }}>
          <ShowChart sx={{ fontSize: 48, color: "text.secondary", mb: 2, opacity: 0.5 }} />
          <Typography color="text.secondary" variant="body2">
            No sentiment data available. Run market data loaders to populate data.
          </Typography>
        </CardContent>
      </Card>
    );
  }

  return (
    <Box sx={{ width: "100%" }}>

      {/* AAII Historical Trends Chart - 3 Line Chart */}
      {processedAAIIData.length > 0 && (
        <Card sx={{ mb: 4, boxShadow: 2, background: alpha(theme.palette.primary.main, 0.03) }}>
          <CardContent sx={{ p: 3 }}>
            {/* Header */}
            <Box
              sx={{
                display: "flex",
                alignItems: "center",
                gap: 2,
                mb: 3,
                pb: 2,
                borderBottom: 2,
                borderColor: "divider",
              }}
            >
              <Box sx={{ background: alpha("#10b981", 0.1), p: 1.5, borderRadius: 1 }}>
                <TrendingUp sx={{ color: "#10b981", fontSize: 28 }} />
              </Box>
              <Box>
                <Typography variant="h6" sx={{ fontWeight: 700 }}>
                  AAII Sentiment Trends
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  Historical trend of bullish, neutral, and bearish sentiment over time
                </Typography>
              </Box>
            </Box>

            {/* Chart */}
            <Box sx={{ height: 400, width: "100%" }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={processedAAIIData} margin={{ top: 10, right: 30, left: 60, bottom: 30 }}>
                  <CartesianGrid
                    strokeDasharray="4 4"
                    stroke={chartColors.grid}
                    vertical={true}
                  />
                  <XAxis
                    dataKey="date"
                    tick={{ fontSize: 11, fill: theme.palette.text.secondary }}
                    tickFormatter={formatDate}
                    angle={-45}
                    textAnchor="end"
                    height={60}
                    interval={Math.floor((processedAAIIData.length - 1) / 8)}
                  />
                  <YAxis
                    domain={[0, 100]}
                    tick={{ fontSize: 11, fill: theme.palette.text.secondary }}
                    label={{ value: "Sentiment %", angle: -90, position: "insideLeft", offset: 10 }}
                    width={50}
                  />
                  <ReferenceLine
                    y={50}
                    stroke={chartColors.gridDark}
                    strokeDasharray="5 5"
                    label={{ value: "50% (Neutral)", position: "right", fill: theme.palette.text.secondary, fontSize: 10 }}
                  />
                  <Tooltip
                    content={<CustomAAIITooltip />}
                    cursor={{ stroke: theme.palette.divider, strokeWidth: 1 }}
                  />
                  <Legend wrapperStyle={{ paddingTop: 20, fontSize: 12 }} iconType="line" />
                  <Line
                    type="monotone"
                    dataKey="aaii_bullish"
                    name="Bullish %"
                    stroke={chartColors.bullish}
                    strokeWidth={2.5}
                    dot={false}
                    isAnimationActive={false}
                    connectNulls
                  />
                  <Line
                    type="monotone"
                    dataKey="aaii_neutral"
                    name="Neutral %"
                    stroke={chartColors.neutral}
                    strokeWidth={2.5}
                    dot={false}
                    isAnimationActive={false}
                    connectNulls
                  />
                  <Line
                    type="monotone"
                    dataKey="aaii_bearish"
                    name="Bearish %"
                    stroke={chartColors.bearish}
                    strokeWidth={2.5}
                    dot={false}
                    isAnimationActive={false}
                    connectNulls
                  />
                </LineChart>
              </ResponsiveContainer>
            </Box>

            <Divider sx={{ my: 2 }} />

            {/* Chart Statistics */}
            <Box sx={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 2 }}>
              {latestAAII && (
                <>
                  <Box sx={{ p: 1.5, background: alpha(chartColors.bullish, 0.08), borderRadius: 1 }}>
                    <Typography variant="caption" color="text.secondary">
                      Latest Bullish
                    </Typography>
                    <Typography variant="h6" sx={{ color: chartColors.bullish, fontWeight: 700 }}>
                      {latestAAII.aaii_bullish?.toFixed(1)}%
                    </Typography>
                  </Box>
                  <Box sx={{ p: 1.5, background: alpha(chartColors.neutral, 0.08), borderRadius: 1 }}>
                    <Typography variant="caption" color="text.secondary">
                      Latest Neutral
                    </Typography>
                    <Typography variant="h6" sx={{ color: chartColors.neutral, fontWeight: 700 }}>
                      {latestAAII.aaii_neutral?.toFixed(1)}%
                    </Typography>
                  </Box>
                  <Box sx={{ p: 1.5, background: alpha(chartColors.bearish, 0.08), borderRadius: 1 }}>
                    <Typography variant="caption" color="text.secondary">
                      Latest Bearish
                    </Typography>
                    <Typography variant="h6" sx={{ color: chartColors.bearish, fontWeight: 700 }}>
                      {latestAAII.aaii_bearish?.toFixed(1)}%
                    </Typography>
                  </Box>
                </>
              )}
            </Box>
          </CardContent>
        </Card>
      )}

      {/* AAII Sentiment Chart */}
      {processedAAIIData.length > 0 && (
        <Card sx={{ mb: 4, boxShadow: 2 }}>
          <CardContent sx={{ p: 3 }}>
            {/* Header */}
            <Box
              sx={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                mb: 3,
                pb: 2,
                borderBottom: 2,
                borderColor: "divider",
              }}
            >
              <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
                <ShowChart sx={{ color: "primary.main", fontSize: 28 }} />
                <Box>
                  <Typography variant="h6" sx={{ fontWeight: 700 }}>
                    AAII Sentiment Survey
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    Retail investor sentiment: {processedAAIIData.length} data points
                  </Typography>
                </Box>
              </Box>
            </Box>

            {/* Summary Cards */}
            {latestAAII && (
              <Box sx={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))", gap: 2, mb: 3 }}>
                <Paper
                  elevation={1}
                  sx={{
                    p: 2,
                    background: alpha(chartColors.bullish, 0.08),
                    border: `1px solid ${alpha(chartColors.bullish, 0.3)}`,
                    borderRadius: 1,
                  }}
                >
                  <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                    Bullish
                  </Typography>
                  <Typography variant="h6" sx={{ color: chartColors.bullish, fontWeight: 700 }}>
                    {latestAAII.aaii_bullish?.toFixed(1) || "N/A"}%
                  </Typography>
                </Paper>

                <Paper
                  elevation={1}
                  sx={{
                    p: 2,
                    background: alpha(chartColors.neutral, 0.08),
                    border: `1px solid ${alpha(chartColors.neutral, 0.3)}`,
                    borderRadius: 1,
                  }}
                >
                  <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                    Neutral
                  </Typography>
                  <Typography variant="h6" sx={{ color: chartColors.neutral, fontWeight: 700 }}>
                    {latestAAII.aaii_neutral?.toFixed(1) || "N/A"}%
                  </Typography>
                </Paper>

                <Paper
                  elevation={1}
                  sx={{
                    p: 2,
                    background: alpha(chartColors.bearish, 0.08),
                    border: `1px solid ${alpha(chartColors.bearish, 0.3)}`,
                    borderRadius: 1,
                  }}
                >
                  <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                    Bearish
                  </Typography>
                  <Typography variant="h6" sx={{ color: chartColors.bearish, fontWeight: 700 }}>
                    {latestAAII.aaii_bearish?.toFixed(1) || "N/A"}%
                  </Typography>
                </Paper>
              </Box>
            )}

            <Divider sx={{ mb: 3 }} />

            {/* Chart */}
            <Box sx={{ height: 400, width: "100%" }}>
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={processedAAIIData} margin={{ top: 10, right: 30, left: 60, bottom: 30 }}>
                  <defs>
                    <linearGradient id="aaiiBullishGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={chartColors.bullish} stopOpacity={0.4} />
                      <stop offset="100%" stopColor={chartColors.bullish} stopOpacity={0.05} />
                    </linearGradient>
                    <linearGradient id="aaiiBearishGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={chartColors.bearish} stopOpacity={0.4} />
                      <stop offset="100%" stopColor={chartColors.bearish} stopOpacity={0.05} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid
                    strokeDasharray="4 4"
                    stroke={chartColors.grid}
                    vertical={true}
                    horizontalPoints={[0, 25, 50, 75, 100]}
                  />
                  <XAxis
                    dataKey="date"
                    tick={{ fontSize: 11, fill: theme.palette.text.secondary }}
                    tickFormatter={formatDate}
                    angle={-45}
                    textAnchor="end"
                    height={60}
                    interval={Math.floor((processedAAIIData.length - 1) / 8)}
                  />
                  <YAxis
                    domain={[0, 100]}
                    tick={{ fontSize: 11, fill: theme.palette.text.secondary }}
                    label={{ value: "Sentiment %", angle: -90, position: "insideLeft", offset: 10 }}
                    width={50}
                  />
                  <ReferenceLine
                    y={50}
                    stroke={chartColors.gridDark}
                    strokeDasharray="5 5"
                    label={{ value: "50% (Neutral)", position: "right", fill: theme.palette.text.secondary, fontSize: 10 }}
                  />
                  <Tooltip content={<CustomAAIITooltip />} cursor={{ stroke: theme.palette.divider, strokeWidth: 1 }} />
                  <Legend
                    wrapperStyle={{ paddingTop: 20, fontSize: 12 }}
                    iconType="line"
                  />
                  <Area
                    type="monotone"
                    dataKey="aaii_bullish"
                    name="Bullish %"
                    stroke={chartColors.bullish}
                    fill="url(#aaiiBullishGrad)"
                    strokeWidth={2.5}
                    isAnimationActive={false}
                    connectNulls
                  />
                  <Line
                    type="monotone"
                    dataKey="aaii_neutral"
                    name="Neutral %"
                    stroke={chartColors.neutral}
                    strokeWidth={2.5}
                    dot={false}
                    isAnimationActive={false}
                    connectNulls
                  />
                  <Area
                    type="monotone"
                    dataKey="aaii_bearish"
                    name="Bearish %"
                    stroke={chartColors.bearish}
                    fill="url(#aaiiBearishGrad)"
                    strokeWidth={2.5}
                    isAnimationActive={false}
                    connectNulls
                  />
                </AreaChart>
              </ResponsiveContainer>
            </Box>
          </CardContent>
        </Card>
      )}

      {/* Fear & Greed Index Chart */}
      {processedFearGreedData.length > 0 && (
        <Card sx={{ mb: 4, boxShadow: 2 }}>
          <CardContent sx={{ p: 3 }}>
            {/* Header */}
            <Box
              sx={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                mb: 3,
                pb: 2,
                borderBottom: 2,
                borderColor: "divider",
              }}
            >
              <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
                <TrendingUp sx={{ color: "primary.main", fontSize: 28 }} />
                <Box>
                  <Typography variant="h6" sx={{ fontWeight: 700 }}>
                    Fear & Greed Index
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    Market sentiment index: {processedFearGreedData.length} data points
                  </Typography>
                </Box>
              </Box>
              {latestFearGreed && (
                <Chip
                  label={
                    latestFearGreed.fear_greed >= 75
                      ? "Extreme Greed"
                      : latestFearGreed.fear_greed >= 55
                      ? "Greed"
                      : latestFearGreed.fear_greed >= 45
                      ? "Neutral"
                      : latestFearGreed.fear_greed >= 25
                      ? "Fear"
                      : "Extreme Fear"
                  }
                  sx={{
                    fontWeight: 600,
                    background: alpha(chartColors.fearGreed, 0.15),
                    color: chartColors.fearGreed,
                  }}
                />
              )}
            </Box>

            {/* Chart */}
            <Box sx={{ height: 350, width: "100%" }}>
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={processedFearGreedData} margin={{ top: 10, right: 30, left: 60, bottom: 30 }}>
                  <defs>
                    <linearGradient id="fearGreedGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={chartColors.fearGreed} stopOpacity={0.4} />
                      <stop offset="100%" stopColor={chartColors.fearGreed} stopOpacity={0.05} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid
                    strokeDasharray="4 4"
                    stroke={chartColors.grid}
                    vertical={true}
                  />
                  <XAxis
                    dataKey="date"
                    tick={{ fontSize: 11, fill: theme.palette.text.secondary }}
                    tickFormatter={formatDate}
                    angle={-45}
                    textAnchor="end"
                    height={60}
                    interval={Math.floor((processedFearGreedData.length - 1) / 8)}
                  />
                  <YAxis
                    domain={[0, 100]}
                    tick={{ fontSize: 11, fill: theme.palette.text.secondary }}
                    label={{ value: "Index (0-100)", angle: -90, position: "insideLeft", offset: 10 }}
                    width={50}
                  />
                  <ReferenceLine y={25} stroke={chartColors.gridDark} strokeDasharray="4 4" />
                  <ReferenceLine y={50} stroke={chartColors.gridDark} strokeDasharray="5 5" />
                  <ReferenceLine y={75} stroke={chartColors.gridDark} strokeDasharray="4 4" />
                  <Tooltip content={<CustomFearGreedTooltip />} cursor={{ stroke: theme.palette.divider, strokeWidth: 1 }} />
                  <Legend wrapperStyle={{ paddingTop: 20, fontSize: 12 }} iconType="line" />
                  <Area
                    type="monotone"
                    dataKey="fear_greed"
                    name="Fear & Greed"
                    stroke={chartColors.fearGreed}
                    fill="url(#fearGreedGrad)"
                    strokeWidth={3}
                    isAnimationActive={false}
                    connectNulls
                  />
                </AreaChart>
              </ResponsiveContainer>
            </Box>
          </CardContent>
        </Card>
      )}

      {/* NAAIM Manager Exposure Chart - Bullish vs Bearish */}
      {processedNAAIMData.length > 0 && (
        <Card sx={{ boxShadow: 2 }}>
          <CardContent sx={{ p: 3 }}>
            {/* Header */}
            <Box
              sx={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                mb: 3,
                pb: 2,
                borderBottom: 2,
                borderColor: "divider",
              }}
            >
              <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
                <ShowChart sx={{ color: "primary.main", fontSize: 28 }} />
                <Box>
                  <Typography variant="h6" sx={{ fontWeight: 700 }}>
                    NAAIM Manager Positioning
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    Professional manager bullish/bearish exposure: {processedNAAIMData.length} data points
                  </Typography>
                </Box>
              </Box>
            </Box>

            {/* Chart */}
            <Box sx={{ height: 350, width: "100%" }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={processedNAAIMData} margin={{ top: 10, right: 30, left: 60, bottom: 30 }}>
                  <defs>
                    <linearGradient id="bullishGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={chartColors.bullish} stopOpacity={0.3} />
                      <stop offset="100%" stopColor={chartColors.bullish} stopOpacity={0.05} />
                    </linearGradient>
                    <linearGradient id="bearishGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={chartColors.bearish} stopOpacity={0.3} />
                      <stop offset="100%" stopColor={chartColors.bearish} stopOpacity={0.05} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid
                    strokeDasharray="4 4"
                    stroke={chartColors.grid}
                    vertical={true}
                  />
                  <XAxis
                    dataKey="date"
                    tick={{ fontSize: 11, fill: theme.palette.text.secondary }}
                    tickFormatter={formatDate}
                    angle={-45}
                    textAnchor="end"
                    height={60}
                    interval={Math.floor((processedNAAIMData.length - 1) / 8)}
                  />
                  <YAxis
                    tick={{ fontSize: 11, fill: theme.palette.text.secondary }}
                    label={{ value: "Manager Exposure %", angle: -90, position: "insideLeft", offset: 10 }}
                    width={70}
                  />
                  <ReferenceLine
                    y={0}
                    stroke={chartColors.gridDark}
                    strokeWidth={2}
                    label={{ value: "Neutral (0%)", position: "right", fill: theme.palette.text.secondary, fontSize: 10 }}
                  />
                  <Tooltip content={<CustomNAAIMTooltip />} cursor={{ stroke: theme.palette.divider, strokeWidth: 1 }} />
                  <Legend wrapperStyle={{ paddingTop: 20, fontSize: 12 }} />
                  <Line
                    type="monotone"
                    dataKey="naaim_bullish"
                    name="Bullish Exposure"
                    stroke={chartColors.bullish}
                    strokeWidth={2.5}
                    isAnimationActive={false}
                    connectNulls
                    dot={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="naaim_bearish"
                    name="Bearish Exposure"
                    stroke={chartColors.bearish}
                    strokeWidth={2.5}
                    isAnimationActive={false}
                    connectNulls
                    dot={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="naaim_net"
                    name="Net Exposure"
                    stroke={chartColors.naaim}
                    strokeWidth={3}
                    isAnimationActive={false}
                    connectNulls
                    dot={false}
                    strokeDasharray="5 5"
                  />
                </LineChart>
              </ResponsiveContainer>
            </Box>
          </CardContent>
        </Card>
      )}
    </Box>
  );
};

export default SentimentChartsReimag;
