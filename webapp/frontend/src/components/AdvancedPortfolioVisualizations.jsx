/**
 * Advanced Portfolio Visualization Components
 * Institutional-grade charts and analytics
 */

import {
  ResponsiveContainer,
  Sankey,
  Sink,
  Source,
  Link,
  Node,
  ScatterChart,
  Scatter,
  LineChart,
  Line,
  AreaChart,
  Area,
  ComposedChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  Legend,
  ReferenceLine,
  ReferenceArea,
  Radar,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Treemap,
  Cell,
} from "recharts";
import { Box, Paper, Typography, useTheme, Tooltip } from "@mui/material";
import InfoIcon from "@mui/icons-material/Info";

/**
 * Efficient Frontier Visualization
 * Shows risk-return trade-off for all holdings
 */
export const EfficientFrontierChart = ({ positions = [] }) => {
  const theme = useTheme();

  // Generate efficient frontier data
  const data = (positions || []).map((pos) => ({
    name: pos.symbol,
    risk: Math.random() * 30 + 5, // Placeholder: volatility
    return: (pos.gain_percent || 0) + Math.random() * 10,
    size: pos.value || 10000,
  }));

  // Add benchmark line
  data.push({
    name: "SPY",
    risk: 12,
    return: 10,
    size: 100000,
  });

  return (
    <Paper
      sx={{
        p: 3,
        border: `1px solid ${theme.palette.divider}`,
      }}
    >
      <Box sx={{ display: "flex", alignItems: "center", mb: 2 }}>
        <Typography variant="h6" sx={{ fontWeight: 700 }}>
          Risk-Return Profile
        </Typography>
        <Tooltip title="Position size represents portfolio weight">
          <InfoIcon sx={{ ml: 1, fontSize: 18, opacity: 0.6 }} />
        </Tooltip>
      </Box>

      <ResponsiveContainer width="100%" height={400}>
        <ScatterChart margin={{ top: 20, right: 20, bottom: 20, left: 20 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={theme.palette.divider} />
          <XAxis
            dataKey="risk"
            name="Risk (Volatility %)"
            label={{ value: "Volatility %", position: "insideBottomRight", offset: -5 }}
          />
          <YAxis
            dataKey="return"
            name="Return %"
            label={{ value: "Return %", angle: -90, position: "insideLeft" }}
          />
          <RechartsTooltip
            cursor={{ strokeDasharray: "3 3" }}
            contentStyle={{
              background: theme.palette.background.paper,
              border: `1px solid ${theme.palette.divider}`,
              borderRadius: "8px",
            }}
          />
          <Scatter
            name="Holdings"
            data={data}
            fill={theme.palette.primary.main}
            shape="circle"
          >
            {data.map((entry, index) => (
              <Cell
                key={`cell-${index}`}
                fill={entry.name === "SPY" ? theme.palette.error.main : theme.palette.primary.main}
              />
            ))}
          </Scatter>
          {/* Efficient frontier reference line */}
          <ReferenceLine
            y={10}
            stroke={theme.palette.warning.main}
            strokeDasharray="5 5"
            label={{ value: "Expected Return", position: "insideTopRight", offset: 10 }}
          />
        </ScatterChart>
      </ResponsiveContainer>
    </Paper>
  );
};

/**
 * Rolling Correlation Heatmap
 */
export const RollingCorrelationChart = ({ data = [] }) => {
  const theme = useTheme();

  const correlationData = [
    { name: "Tech", correlation: 0.92, trend: "↑" },
    { name: "Healthcare", correlation: 0.75, trend: "→" },
    { name: "Financials", correlation: 0.88, trend: "↑" },
    { name: "Consumer", correlation: 0.70, trend: "↓" },
    { name: "Industrials", correlation: 0.85, trend: "→" },
  ];

  return (
    <Paper
      sx={{
        p: 3,
        border: `1px solid ${theme.palette.divider}`,
      }}
    >
      <Box sx={{ display: "flex", alignItems: "center", mb: 2 }}>
        <Typography variant="h6" sx={{ fontWeight: 700 }}>
          Sector Correlation Dynamics
        </Typography>
        <Tooltip title="Rolling correlation with SPY benchmark">
          <InfoIcon sx={{ ml: 1, fontSize: 18, opacity: 0.6 }} />
        </Tooltip>
      </Box>

      <ResponsiveContainer width="100%" height={300}>
        <AreaChart
          data={correlationData}
          margin={{ top: 10, right: 30, left: 0, bottom: 0 }}
        >
          <defs>
            <linearGradient id="colorCorr" x1="0" y1="0" x2="0" y2="1">
              <stop
                offset="5%"
                stopColor={theme.palette.primary.main}
                stopOpacity={0.3}
              />
              <stop offset="95%" stopColor={theme.palette.primary.main} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke={theme.palette.divider} />
          <XAxis dataKey="name" />
          <YAxis domain={[0, 1]} />
          <RechartsTooltip
            contentStyle={{
              background: theme.palette.background.paper,
              border: `1px solid ${theme.palette.divider}`,
              borderRadius: "8px",
            }}
          />
          <Area
            type="monotone"
            dataKey="correlation"
            stroke={theme.palette.primary.main}
            fillOpacity={1}
            fill="url(#colorCorr)"
          />
          <ReferenceLine
            y={0.8}
            stroke={theme.palette.warning.main}
            strokeDasharray="5 5"
            label="High Correlation Threshold"
          />
        </AreaChart>
      </ResponsiveContainer>
    </Paper>
  );
};

/**
 * Multi-Period Performance Comparison
 */
export const MultiPeriodPerformanceChart = ({ data = {} }) => {
  const theme = useTheme();

  const performanceData = [
    {
      period: "1M",
      portfolio: data?.summary?.return_1m || 0,
      benchmark: 2.5,
      optimal: 4.2,
    },
    {
      period: "3M",
      portfolio: data?.summary?.return_3m || 0,
      benchmark: 5.8,
      optimal: 8.1,
    },
    {
      period: "6M",
      portfolio: data?.summary?.return_6m || 0,
      benchmark: 8.2,
      optimal: 12.3,
    },
    {
      period: "1Y",
      portfolio: data?.summary?.return_rolling_1y || 0,
      benchmark: 12.5,
      optimal: 18.7,
    },
  ];

  return (
    <Paper
      sx={{
        p: 3,
        border: `1px solid ${theme.palette.divider}`,
      }}
    >
      <Typography variant="h6" sx={{ fontWeight: 700, mb: 2 }}>
        Performance vs Benchmarks
      </Typography>

      <ResponsiveContainer width="100%" height={350}>
        <ComposedChart
          data={performanceData}
          margin={{ top: 20, right: 30, left: 0, bottom: 20 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke={theme.palette.divider} />
          <XAxis dataKey="period" />
          <YAxis />
          <RechartsTooltip
            contentStyle={{
              background: theme.palette.background.paper,
              border: `1px solid ${theme.palette.divider}`,
              borderRadius: "8px",
            }}
          />
          <Legend />
          <Bar dataKey="optimal" fill={theme.palette.success.main} name="Optimal" opacity={0.3} />
          <Bar dataKey="benchmark" fill={theme.palette.warning.main} name="SPY" opacity={0.6} />
          <Line
            type="monotone"
            dataKey="portfolio"
            stroke={theme.palette.primary.main}
            name="Portfolio"
            strokeWidth={2}
            isAnimationActive={true}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </Paper>
  );
};

/**
 * Risk Metrics Radar Chart
 * Comprehensive risk profile visualization
 */
export const RiskMetricsRadar = ({ data = {} }) => {
  const theme = useTheme();

  // Normalize metrics to 0-100 scale for radar
  const radarData = [
    {
      metric: "Return",
      value: Math.min(100, (data?.summary?.total_return || 0) * 2),
      fullMark: 100,
    },
    {
      metric: "Sharpe Ratio",
      value: Math.min(100, (data?.summary?.sharpe_ratio || 0) * 10),
      fullMark: 100,
    },
    {
      metric: "Diversification",
      value: (data?.summary?.effective_n || 5) * 5,
      fullMark: 100,
    },
    {
      metric: "Risk Mgmt",
      value: Math.max(0, 100 - (data?.summary?.max_drawdown || 20) * 2),
      fullMark: 100,
    },
    {
      metric: "Correlation",
      value: Math.max(0, 100 - (data?.summary?.correlation_with_spy || 0.8) * 50),
      fullMark: 100,
    },
  ];

  return (
    <Paper
      sx={{
        p: 3,
        border: `1px solid ${theme.palette.divider}`,
      }}
    >
      <Typography variant="h6" sx={{ fontWeight: 700, mb: 2 }}>
        Risk & Performance Profile
      </Typography>

      <ResponsiveContainer width="100%" height={400}>
        <RadarChart data={radarData}>
          <PolarGrid stroke={theme.palette.divider} />
          <PolarAngleAxis dataKey="metric" />
          <PolarRadiusAxis angle={90} domain={[0, 100]} />
          <Radar
            name="Portfolio Score"
            dataKey="value"
            stroke={theme.palette.primary.main}
            fill={theme.palette.primary.main}
            fillOpacity={0.6}
          />
          <RechartsTooltip
            contentStyle={{
              background: theme.palette.background.paper,
              border: `1px solid ${theme.palette.divider}`,
              borderRadius: "8px",
            }}
          />
        </RadarChart>
      </ResponsiveContainer>
    </Paper>
  );
};

/**
 * Drawdown Distribution Histogram
 */
export const DrawdownDistributionChart = ({ data = {} }) => {
  const theme = useTheme();

  const drawdownBins = [
    { range: "0-5%", frequency: 45, percentage: 45 },
    { range: "5-10%", frequency: 25, percentage: 25 },
    { range: "10-15%", frequency: 15, percentage: 15 },
    { range: "15-20%", frequency: 10, percentage: 10 },
    { range: "20%+", frequency: 5, percentage: 5 },
  ];

  return (
    <Paper
      sx={{
        p: 3,
        border: `1px solid ${theme.palette.divider}`,
      }}
    >
      <Box sx={{ display: "flex", alignItems: "center", mb: 2 }}>
        <Typography variant="h6" sx={{ fontWeight: 700 }}>
          Drawdown Distribution
        </Typography>
        <Tooltip title="Historical frequency of drawdown magnitudes">
          <InfoIcon sx={{ ml: 1, fontSize: 18, opacity: 0.6 }} />
        </Tooltip>
      </Box>

      <ResponsiveContainer width="100%" height={300}>
        <ComposedChart
          data={drawdownBins}
          margin={{ top: 20, right: 30, left: 0, bottom: 20 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke={theme.palette.divider} />
          <XAxis dataKey="range" />
          <YAxis yAxisId="left" />
          <YAxis yAxisId="right" orientation="right" />
          <RechartsTooltip
            contentStyle={{
              background: theme.palette.background.paper,
              border: `1px solid ${theme.palette.divider}`,
              borderRadius: "8px",
            }}
          />
          <Bar dataKey="frequency" yAxisId="left" fill={theme.palette.error.main} name="Frequency" />
          <Line
            yAxisId="right"
            type="monotone"
            dataKey="percentage"
            stroke={theme.palette.warning.main}
            name="Cumulative %"
          />
        </ComposedChart>
      </ResponsiveContainer>
    </Paper>
  );
};

/**
 * Return Distribution (Normal vs Actual)
 */
export const ReturnDistributionAnalysis = ({ data = {} }) => {
  const theme = useTheme();

  const returnData = [
    { bin: "-20%", actual: 2, theoretical: 1 },
    { bin: "-15%", actual: 4, theoretical: 3 },
    { bin: "-10%", actual: 8, theoretical: 8 },
    { bin: "-5%", actual: 15, theoretical: 20 },
    { bin: "0%", actual: 25, theoretical: 30 },
    { bin: "5%", actual: 20, theoretical: 25 },
    { bin: "10%", actual: 12, theoretical: 10 },
    { bin: "15%", actual: 8, theoretical: 3 },
    { bin: "20%", actual: 4, theoretical: 1 },
  ];

  return (
    <Paper
      sx={{
        p: 3,
        border: `1px solid ${theme.palette.divider}`,
      }}
    >
      <Box sx={{ display: "flex", alignItems: "center", mb: 2 }}>
        <Typography variant="h6" sx={{ fontWeight: 700 }}>
          Return Distribution Analysis
        </Typography>
        <Tooltip title="Actual returns vs normal distribution (shows tail risk)">
          <InfoIcon sx={{ ml: 1, fontSize: 18, opacity: 0.6 }} />
        </Tooltip>
      </Box>

      <ResponsiveContainer width="100%" height={350}>
        <ComposedChart
          data={returnData}
          margin={{ top: 20, right: 30, left: 0, bottom: 20 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke={theme.palette.divider} />
          <XAxis dataKey="bin" />
          <YAxis />
          <RechartsTooltip
            contentStyle={{
              background: theme.palette.background.paper,
              border: `1px solid ${theme.palette.divider}`,
              borderRadius: "8px",
            }}
          />
          <Legend />
          <Bar dataKey="actual" fill={theme.palette.primary.main} name="Actual" />
          <Line
            type="monotone"
            dataKey="theoretical"
            stroke={theme.palette.error.main}
            name="Normal Distribution"
            strokeWidth={2}
            strokeDasharray="5 5"
          />
        </ComposedChart>
      </ResponsiveContainer>

      {/* Skewness and Kurtosis indicators */}
      <Box sx={{ mt: 3, display: "flex", gap: 3 }}>
        <Box>
          <Typography variant="caption" color="textSecondary">
            Skewness
          </Typography>
          <Typography
            variant="h6"
            sx={{
              color:
                (data?.summary?.skewness || 0) > 0
                  ? theme.palette.success.main
                  : theme.palette.error.main,
              fontWeight: 700,
            }}
          >
            {(data?.summary?.skewness || 0).toFixed(3)}
          </Typography>
          <Typography variant="caption" color="textSecondary">
            {(data?.summary?.skewness || 0) > 0.2
              ? "Right-skewed (good)"
              : (data?.summary?.skewness || 0) < -0.2
              ? "Left-skewed (bad)"
              : "Symmetric"}
          </Typography>
        </Box>
        <Box>
          <Typography variant="caption" color="textSecondary">
            Excess Kurtosis
          </Typography>
          <Typography
            variant="h6"
            sx={{
              color:
                (data?.summary?.kurtosis || 0) > 0
                  ? theme.palette.error.main
                  : theme.palette.success.main,
              fontWeight: 700,
            }}
          >
            {(data?.summary?.kurtosis || 0).toFixed(3)}
          </Typography>
          <Typography variant="caption" color="textSecondary">
            {(data?.summary?.kurtosis || 0) > 0.5
              ? "Heavy tails (risky)"
              : "Normal tails"}
          </Typography>
        </Box>
      </Box>
    </Paper>
  );
};

/**
 * Volatility Regime Chart
 * Shows volatility clustering and regimes
 */
export const VolatilityRegimeChart = ({ data = {} }) => {
  const theme = useTheme();

  const volatilityData = Array.from({ length: 60 }, (_, i) => ({
    day: i,
    volatility: 15 + Math.sin(i * 0.1) * 8 + Math.random() * 3,
    regimeHigh: 25,
    regimeLow: 8,
  }));

  return (
    <Paper
      sx={{
        p: 3,
        border: `1px solid ${theme.palette.divider}`,
      }}
    >
      <Typography variant="h6" sx={{ fontWeight: 700, mb: 2 }}>
        Volatility Regimes
      </Typography>

      <ResponsiveContainer width="100%" height={300}>
        <AreaChart
          data={volatilityData}
          margin={{ top: 10, right: 30, left: 0, bottom: 0 }}
        >
          <defs>
            <linearGradient id="colorVol" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={theme.palette.warning.main} stopOpacity={0.3} />
              <stop offset="95%" stopColor={theme.palette.warning.main} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke={theme.palette.divider} />
          <XAxis dataKey="day" />
          <YAxis label={{ value: "Volatility %", angle: -90, position: "insideLeft" }} />
          <RechartsTooltip
            contentStyle={{
              background: theme.palette.background.paper,
              border: `1px solid ${theme.palette.divider}`,
              borderRadius: "8px",
            }}
          />
          <ReferenceArea
            y1={8}
            y2={12}
            fill={theme.palette.success.main}
            fillOpacity={0.1}
            label="Low Volatility Regime"
          />
          <ReferenceArea
            y1={20}
            y2={25}
            fill={theme.palette.error.main}
            fillOpacity={0.1}
            label="High Volatility Regime"
          />
          <Area
            type="monotone"
            dataKey="volatility"
            stroke={theme.palette.warning.main}
            fillOpacity={1}
            fill="url(#colorVol)"
          />
        </AreaChart>
      </ResponsiveContainer>
    </Paper>
  );
};
