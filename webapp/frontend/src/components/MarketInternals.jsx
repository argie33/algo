import { useState, useEffect, useMemo } from "react";
import {
  Box,
  Card,
  CardContent,
  Grid,
  LinearProgress,
  Typography,
  Alert,
  Chip,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
} from "@mui/material";
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Cell,
} from "recharts";
import {
  TrendingUp,
  TrendingDown,
  WarningAmber,
  CheckCircle,
} from "@mui/icons-material";

const MarketInternals = ({ data, isLoading, error }) => {
  const [_expandedSection, setExpandedSection] = useState(null);

  if (isLoading) {
    return <LinearProgress />;
  }

  if (error || !data?.data) {
    return (
      <Alert severity="error">
        Unable to load market internals data. {error?.message}
      </Alert>
    );
  }

  const {
    market_breadth,
    moving_average_analysis,
    market_extremes,
    overextension_indicator,
    positioning_metrics,
  } = data.data;

  // Color helpers
  const getSignalColor = (signal) => {
    if (signal === "Extreme") return "#dc2626";
    if (signal === "Strong") return "#f97316";
    if (signal === "Extreme Down") return "#0ea5e9";
    if (signal === "Strong Down") return "#3b82f6";
    return "#10b981";
  };

  const getSignalIcon = (level) => {
    if (level && (level.includes("Extreme") || level.includes("Strong"))) {
      return <WarningAmber sx={{ color: getSignalColor(level) }} />;
    }
    return <CheckCircle sx={{ color: "#10b981" }} />;
  };

  // Breadth chart data
  const breadthChartData = [
    { name: "Advancing", value: market_breadth.advancing, fill: "#10b981" },
    { name: "Declining", value: market_breadth.declining, fill: "#ef4444" },
    { name: "Unchanged", value: market_breadth.unchanged, fill: "#6b7280" },
  ];

  // MA analysis data
  const maChartData = [
    {
      name: "SMA 20",
      value: parseFloat(moving_average_analysis.above_sma20.percent) || 0,
    },
    {
      name: "SMA 50",
      value: parseFloat(moving_average_analysis.above_sma50.percent) || 0,
    },
    {
      name: "SMA 200",
      value: parseFloat(moving_average_analysis.above_sma200.percent) || 0,
    },
  ];

  return (
    <Box>
      {/* Overextension Alert */}
      <Grid item xs={12} sx={{ mb: 3 }}>
        <Card
          sx={{
            background: `linear-gradient(135deg, ${getSignalColor(overextension_indicator.level)}22 0%, ${getSignalColor(overextension_indicator.level)}11 100%)`,
            borderLeft: `4px solid ${getSignalColor(overextension_indicator.level)}`,
          }}
        >
          <CardContent>
            <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
              {getSignalIcon(overextension_indicator.level)}
              <Box sx={{ flex: 1 }}>
                <Typography variant="h6" sx={{ fontWeight: 600, mb: 0.5 }}>
                  {overextension_indicator.level} Market Condition
                </Typography>
                {overextension_indicator.signal && (
                  <Typography variant="body2" color="text.secondary">
                    {overextension_indicator.signal}
                  </Typography>
                )}
                <Box sx={{ display: "flex", gap: 2, mt: 1 }}>
                  <Chip
                    label={`Breadth: ${overextension_indicator.breadth_score}%`}
                    size="small"
                    variant="outlined"
                  />
                  <Chip
                    label={`MA200: ${overextension_indicator.ma200_score}%`}
                    size="small"
                    variant="outlined"
                  />
                  <Chip
                    label={`Composite: ${overextension_indicator.composite_score}%`}
                    size="small"
                    color="primary"
                  />
                </Box>
              </Box>
            </Box>
          </CardContent>
        </Card>
      </Grid>

      <Grid container spacing={3}>
        {/* Market Breadth Section */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                Market Breadth
              </Typography>

              {/* Stats Grid */}
              <Grid container spacing={1} sx={{ mb: 3 }}>
                <Grid item xs={6} sm={3}>
                  <Box
                    sx={{
                      p: 1.5,
                      bgcolor: "success.light",
                      borderRadius: 1,
                      textAlign: "center",
                    }}
                  >
                    <Typography variant="body2" color="success.contrastText">
                      Advancing
                    </Typography>
                    <Typography
                      variant="h6"
                      color="success.contrastText"
                      sx={{ fontWeight: 600 }}
                    >
                      {market_breadth.advancing}
                    </Typography>
                  </Box>
                </Grid>
                <Grid item xs={6} sm={3}>
                  <Box
                    sx={{
                      p: 1.5,
                      bgcolor: "error.light",
                      borderRadius: 1,
                      textAlign: "center",
                    }}
                  >
                    <Typography variant="body2" color="error.contrastText">
                      Declining
                    </Typography>
                    <Typography
                      variant="h6"
                      color="error.contrastText"
                      sx={{ fontWeight: 600 }}
                    >
                      {market_breadth.declining}
                    </Typography>
                  </Box>
                </Grid>
                <Grid item xs={6} sm={3}>
                  <Box
                    sx={{
                      p: 1.5,
                      bgcolor: "warning.light",
                      borderRadius: 1,
                      textAlign: "center",
                    }}
                  >
                    <Typography variant="body2" color="warning.contrastText">
                      Unchanged
                    </Typography>
                    <Typography
                      variant="h6"
                      color="warning.contrastText"
                      sx={{ fontWeight: 600 }}
                    >
                      {market_breadth.unchanged}
                    </Typography>
                  </Box>
                </Grid>
                <Grid item xs={6} sm={3}>
                  <Box
                    sx={{
                      p: 1.5,
                      bgcolor: "info.light",
                      borderRadius: 1,
                      textAlign: "center",
                    }}
                  >
                    <Typography variant="body2" color="info.contrastText">
                      Total
                    </Typography>
                    <Typography
                      variant="h6"
                      color="info.contrastText"
                      sx={{ fontWeight: 600 }}
                    >
                      {market_breadth.total_stocks}
                    </Typography>
                  </Box>
                </Grid>
              </Grid>

              {/* Breadth Chart */}
              <Box sx={{ height: 300, width: "100%" }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={breadthChartData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="name" />
                    <YAxis />
                    <Tooltip />
                    <Bar dataKey="value" fill="#8884d8">
                      {breadthChartData.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={entry.fill} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </Box>

              {/* Breadth Details */}
              <Box sx={{ mt: 2, pt: 2, borderTop: 1, borderColor: "divider" }}>
                <Grid container spacing={1}>
                  <Grid item xs={6}>
                    <Typography variant="caption" color="text.secondary">
                      Advancing %
                    </Typography>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>
                      {market_breadth.advancing_percent}%
                    </Typography>
                  </Grid>
                  <Grid item xs={6}>
                    <Typography variant="caption" color="text.secondary">
                      A/D Ratio
                    </Typography>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>
                      {market_breadth.decline_advance_ratio || "N/A"}
                    </Typography>
                  </Grid>
                  <Grid item xs={6}>
                    <Typography variant="caption" color="text.secondary">
                      Avg Daily Change
                    </Typography>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>
                      {market_breadth.avg_daily_change}%
                    </Typography>
                  </Grid>
                  <Grid item xs={6}>
                    <Typography variant="caption" color="text.secondary">
                      Total Volume
                    </Typography>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>
                      {market_breadth.total_volume?.toLocaleString()}
                    </Typography>
                  </Grid>
                </Grid>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Moving Average Analysis */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                Moving Average Analysis
              </Typography>

              <Box sx={{ height: 300, width: "100%", mb: 2 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={maChartData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="name" />
                    <YAxis domain={[0, 100]} />
                    <Tooltip formatter={(value) => {
                      const num = typeof value === 'number' ? value : parseFloat(value) || 0;
                      return `${isNaN(num) ? '0.0' : num.toFixed(1)}%`;
                    }} />
                    <Bar dataKey="value" fill="#3b82f6" />
                  </BarChart>
                </ResponsiveContainer>
              </Box>

              <TableContainer component={Paper} elevation={0}>
                <Table size="small">
                  <TableHead>
                    <TableRow sx={{ backgroundColor: "grey.50" }}>
                      <TableCell sx={{ fontWeight: 600 }}>Period</TableCell>
                      <TableCell align="right" sx={{ fontWeight: 600 }}>
                        Count
                      </TableCell>
                      <TableCell align="right" sx={{ fontWeight: 600 }}>
                        Total
                      </TableCell>
                      <TableCell align="right" sx={{ fontWeight: 600 }}>
                        Percent
                      </TableCell>
                      <TableCell align="right" sx={{ fontWeight: 600 }}>
                        Avg Distance
                      </TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {[
                      {
                        name: "SMA 20",
                        data: moving_average_analysis.above_sma20,
                      },
                      {
                        name: "SMA 50",
                        data: moving_average_analysis.above_sma50,
                      },
                      {
                        name: "SMA 200",
                        data: moving_average_analysis.above_sma200,
                      },
                    ].map((row) => (
                      <TableRow key={row.name} hover>
                        <TableCell>{row.name}</TableCell>
                        <TableCell align="right">{row.data.count}</TableCell>
                        <TableCell align="right">{row.data.total}</TableCell>
                        <TableCell align="right">
                          {row.data.percent}%
                        </TableCell>
                        <TableCell align="right">
                          {row.data.avg_distance_pct}%
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </CardContent>
          </Card>
        </Grid>

        {/* Market Extremes / Percentiles */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                Market Extremes (90-Day)
              </Typography>

              <Grid container spacing={2}>
                <Grid item xs={6} sm={4}>
                  <Box
                    sx={{
                      p: 1.5,
                      bgcolor: "primary.light",
                      borderRadius: 1,
                      textAlign: "center",
                    }}
                  >
                    <Typography variant="caption" color="primary.contrastText">
                      Current
                    </Typography>
                    <Typography
                      variant="h6"
                      color="primary.contrastText"
                      sx={{ fontWeight: 600 }}
                    >
                      {market_extremes.current_breadth_percentile}%
                    </Typography>
                  </Box>
                </Grid>
                <Grid item xs={6} sm={4}>
                  <Box
                    sx={{
                      p: 1.5,
                      bgcolor: "success.light",
                      borderRadius: 1,
                      textAlign: "center",
                    }}
                  >
                    <Typography variant="caption" color="success.contrastText">
                      50th %ile
                    </Typography>
                    <Typography
                      variant="h6"
                      color="success.contrastText"
                      sx={{ fontWeight: 600 }}
                    >
                      {market_extremes.percentile_50}%
                    </Typography>
                  </Box>
                </Grid>
                <Grid item xs={6} sm={4}>
                  <Box
                    sx={{
                      p: 1.5,
                      bgcolor: "info.light",
                      borderRadius: 1,
                      textAlign: "center",
                    }}
                  >
                    <Typography variant="caption" color="info.contrastText">
                      90th %ile
                    </Typography>
                    <Typography
                      variant="h6"
                      color="info.contrastText"
                      sx={{ fontWeight: 600 }}
                    >
                      {market_extremes.percentile_90}%
                    </Typography>
                  </Box>
                </Grid>
              </Grid>

              <Box sx={{ mt: 2 }}>
                <Typography variant="body2" sx={{ mb: 1 }}>
                  <strong>25th Percentile:</strong> {market_extremes.percentile_25}%
                </Typography>
                <Typography variant="body2" sx={{ mb: 1 }}>
                  <strong>75th Percentile:</strong> {market_extremes.percentile_75}%
                </Typography>
                <Typography variant="body2" sx={{ mb: 1 }}>
                  <strong>Average (30d):</strong> {market_extremes.avg_breadth_30d}%
                </Typography>
                <Typography variant="body2" sx={{ mb: 1 }}>
                  <strong>Std Dev:</strong> {market_extremes.stddev_breadth_30d}
                </Typography>
                <Typography variant="body2" sx={{ mb: 1 }}>
                  <strong>Std Devs from Mean:</strong>{" "}
                  {market_extremes.stddev_from_mean}σ
                </Typography>
                <Typography variant="body2">
                  <strong>Breadth Rank:</strong>{" "}
                  {market_extremes.breadth_rank !== null
                    ? `${market_extremes.breadth_rank}%`
                    : "N/A"}
                </Typography>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Strong Moves */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                Strong Moves (5%+ moves)
              </Typography>

              <Grid container spacing={2}>
                <Grid item xs={6}>
                  <Box
                    sx={{
                      p: 2,
                      bgcolor: "success.light",
                      borderRadius: 1,
                      textAlign: "center",
                    }}
                  >
                    <TrendingUp sx={{ color: "success.main", mb: 1 }} />
                    <Typography variant="body2" color="success.contrastText">
                      Strong Up
                    </Typography>
                    <Typography
                      variant="h5"
                      color="success.contrastText"
                      sx={{ fontWeight: 600 }}
                    >
                      {market_breadth.strong_up}
                    </Typography>
                  </Box>
                </Grid>
                <Grid item xs={6}>
                  <Box
                    sx={{
                      p: 2,
                      bgcolor: "error.light",
                      borderRadius: 1,
                      textAlign: "center",
                    }}
                  >
                    <TrendingDown sx={{ color: "error.main", mb: 1 }} />
                    <Typography variant="body2" color="error.contrastText">
                      Strong Down
                    </Typography>
                    <Typography
                      variant="h5"
                      color="error.contrastText"
                      sx={{ fontWeight: 600 }}
                    >
                      {market_breadth.strong_down}
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

export default MarketInternals;
