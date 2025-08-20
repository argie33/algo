import React, { useState } from "react";
import {
  Card,
  CardContent,
  Typography,
  Grid,
  Box,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Chip,
  Alert,
  Button,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
} from "@mui/material";
import {
  Refresh as RefreshIcon,
  TrendingUp as TrendingUpIcon,
  TrendingDown as TrendingDownIcon,
} from "@mui/icons-material";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  ResponsiveContainer,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  Tooltip as Tooltip,
} from "recharts";

const RealTimeAnalytics = ({ _analyticsData, onRefresh }) => {
  const [timeRange, setTimeRange] = useState("1h");
  const [selectedMetric, setSelectedMetric] = useState("latency");

  // Mock analytics data - replace with real data from API
  const mockLatencyData = [
    { time: "14:00", alpaca: 45, polygon: 32, finnhub: 67 },
    { time: "14:05", alpaca: 42, polygon: 28, finnhub: 71 },
    { time: "14:10", alpaca: 48, polygon: 35, finnhub: 69 },
    { time: "14:15", alpaca: 44, polygon: 31, finnhub: 65 },
    { time: "14:20", alpaca: 46, polygon: 29, finnhub: 72 },
    { time: "14:25", alpaca: 43, polygon: 33, finnhub: 68 },
    { time: "14:30", alpaca: 47, polygon: 30, finnhub: 70 },
  ];

  const mockThroughputData = [
    { time: "14:00", messages: 1250, bytes: 245000 },
    { time: "14:05", messages: 1380, bytes: 267000 },
    { time: "14:10", messages: 1420, bytes: 278000 },
    { time: "14:15", messages: 1350, bytes: 262000 },
    { time: "14:20", messages: 1480, bytes: 289000 },
    { time: "14:25", messages: 1390, bytes: 271000 },
    { time: "14:30", messages: 1460, bytes: 285000 },
  ];

  const mockErrorData = [
    { provider: "Alpaca", errors: 3, total: 15420, rate: 0.019 },
    { provider: "Polygon", errors: 8, total: 23150, rate: 0.035 },
    { provider: "Finnhub", errors: 12, total: 18900, rate: 0.063 },
  ];

  const mockCostData = [
    { name: "Alpaca", value: 12.5, color: "#8884d8" },
    { name: "Polygon", value: 18.75, color: "#82ca9d" },
    { name: "Finnhub", value: 8.2, color: "#ffc658" },
  ];

  const getErrorRateColor = (rate) => {
    if (rate < 0.01) return "success";
    if (rate < 0.05) return "warning";
    return "error";
  };

  const _formatBytes = (bytes) => {
    if (bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
  };

  return (
    <Box>
      {/* Analytics Controls */}
      <Card elevation={2} sx={{ mb: 3 }}>
        <CardContent>
          <Box
            display="flex"
            justifyContent="space-between"
            alignItems="center"
            mb={2}
          >
            <Typography variant="h6" fontWeight="bold">
              Real-Time Analytics Dashboard
            </Typography>
            <Box display="flex" gap={2}>
              <FormControl size="small" sx={{ minWidth: 120 }}>
                <InputLabel>Time Range</InputLabel>
                <Select
                  value={timeRange}
                  label="Time Range"
                  onChange={(e) => setTimeRange(e.target.value)}
                >
                  <MenuItem value="15m">15 Minutes</MenuItem>
                  <MenuItem value="1h">1 Hour</MenuItem>
                  <MenuItem value="4h">4 Hours</MenuItem>
                  <MenuItem value="24h">24 Hours</MenuItem>
                </Select>
              </FormControl>
              <FormControl size="small" sx={{ minWidth: 120 }}>
                <InputLabel>Metric</InputLabel>
                <Select
                  value={selectedMetric}
                  label="Metric"
                  onChange={(e) => setSelectedMetric(e.target.value)}
                >
                  <MenuItem value="latency">Latency</MenuItem>
                  <MenuItem value="throughput">Throughput</MenuItem>
                  <MenuItem value="errors">Error Rates</MenuItem>
                  <MenuItem value="costs">Costs</MenuItem>
                </Select>
              </FormControl>
              <Button
                startIcon={<RefreshIcon />}
                variant="outlined"
                onClick={onRefresh}
                size="small"
              >
                Refresh
              </Button>
            </Box>
          </Box>

          {/* Key Performance Indicators */}
          <Grid container spacing={3}>
            <Grid item xs={12} sm={3}>
              <Box
                textAlign="center"
                p={2}
                bgcolor="primary.light"
                borderRadius={1}
              >
                <Typography variant="h4" color="white" fontWeight="bold">
                  42ms
                </Typography>
                <Typography variant="body2" color="white">
                  Avg Latency
                </Typography>
                <Box
                  display="flex"
                  justifyContent="center"
                  alignItems="center"
                  mt={1}
                >
                  <TrendingUpIcon color="inherit" fontSize="small" />
                  <Typography variant="caption" color="white" ml={0.5}>
                    +5% vs last hour
                  </Typography>
                </Box>
              </Box>
            </Grid>
            <Grid item xs={12} sm={3}>
              <Box
                textAlign="center"
                p={2}
                bgcolor="success.light"
                borderRadius={1}
              >
                <Typography variant="h4" color="white" fontWeight="bold">
                  1.4K
                </Typography>
                <Typography variant="body2" color="white">
                  Msg/Min
                </Typography>
                <Box
                  display="flex"
                  justifyContent="center"
                  alignItems="center"
                  mt={1}
                >
                  <TrendingUpIcon color="inherit" fontSize="small" />
                  <Typography variant="caption" color="white" ml={0.5}>
                    +12% vs last hour
                  </Typography>
                </Box>
              </Box>
            </Grid>
            <Grid item xs={12} sm={3}>
              <Box
                textAlign="center"
                p={2}
                bgcolor="warning.light"
                borderRadius={1}
              >
                <Typography variant="h4" color="white" fontWeight="bold">
                  0.04%
                </Typography>
                <Typography variant="body2" color="white">
                  Error Rate
                </Typography>
                <Box
                  display="flex"
                  justifyContent="center"
                  alignItems="center"
                  mt={1}
                >
                  <TrendingDownIcon color="inherit" fontSize="small" />
                  <Typography variant="caption" color="white" ml={0.5}>
                    -23% vs last hour
                  </Typography>
                </Box>
              </Box>
            </Grid>
            <Grid item xs={12} sm={3}>
              <Box
                textAlign="center"
                p={2}
                bgcolor="info.light"
                borderRadius={1}
              >
                <Typography variant="h4" color="white" fontWeight="bold">
                  $39.45
                </Typography>
                <Typography variant="body2" color="white">
                  Daily Cost
                </Typography>
                <Box
                  display="flex"
                  justifyContent="center"
                  alignItems="center"
                  mt={1}
                >
                  <TrendingUpIcon color="inherit" fontSize="small" />
                  <Typography variant="caption" color="white" ml={0.5}>
                    +8% vs yesterday
                  </Typography>
                </Box>
              </Box>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      <Grid container spacing={3}>
        {/* Latency Chart */}
        <Grid item xs={12} lg={8}>
          <Card elevation={2}>
            <CardContent>
              <Typography variant="h6" fontWeight="bold" gutterBottom>
                Provider Latency Trends
              </Typography>
              <Box height={300}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={mockLatencyData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="time" />
                    <YAxis
                      label={{
                        value: "Latency (ms)",
                        angle: -90,
                        position: "insideLeft",
                      }}
                    />
                    <Tooltip />
                    <Line
                      type="monotone"
                      dataKey="alpaca"
                      stroke="#8884d8"
                      strokeWidth={2}
                      name="Alpaca"
                    />
                    <Line
                      type="monotone"
                      dataKey="polygon"
                      stroke="#82ca9d"
                      strokeWidth={2}
                      name="Polygon"
                    />
                    <Line
                      type="monotone"
                      dataKey="finnhub"
                      stroke="#ffc658"
                      strokeWidth={2}
                      name="Finnhub"
                    />
                  </LineChart>
                </ResponsiveContainer>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Cost Distribution */}
        <Grid item xs={12} lg={4}>
          <Card elevation={2}>
            <CardContent>
              <Typography variant="h6" fontWeight="bold" gutterBottom>
                Daily Cost Distribution
              </Typography>
              <Box height={300}>
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={mockCostData}
                      cx="50%"
                      cy="50%"
                      labelLine={false}
                      label={({ name, value }) => `${name}: $${value}`}
                      outerRadius={80}
                      fill="#8884d8"
                      dataKey="value"
                    >
                      {mockCostData.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={entry.color} />
                      ))}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Throughput Chart */}
        <Grid item xs={12} lg={8}>
          <Card elevation={2}>
            <CardContent>
              <Typography variant="h6" fontWeight="bold" gutterBottom>
                Message Throughput
              </Typography>
              <Box height={300}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={mockThroughputData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="time" />
                    <YAxis
                      label={{
                        value: "Messages",
                        angle: -90,
                        position: "insideLeft",
                      }}
                    />
                    <Tooltip />
                    <Bar dataKey="messages" fill="#8884d8" />
                  </BarChart>
                </ResponsiveContainer>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Error Rates Table */}
        <Grid item xs={12} lg={4}>
          <Card elevation={2}>
            <CardContent>
              <Typography variant="h6" fontWeight="bold" gutterBottom>
                Error Rates by Provider
              </Typography>
              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Provider</TableCell>
                      <TableCell align="right">Errors</TableCell>
                      <TableCell align="right">Rate</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {mockErrorData.map((row) => (
                      <TableRow key={row.provider}>
                        <TableCell>{row.provider}</TableCell>
                        <TableCell align="right">{row.errors}</TableCell>
                        <TableCell align="right">
                          <Chip
                            label={`${(row.rate * 100).toFixed(2)}%`}
                            size="small"
                            color={getErrorRateColor(row.rate)}
                          />
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </CardContent>
          </Card>
        </Grid>

        {/* Performance Alerts */}
        <Grid item xs={12}>
          <Card elevation={2}>
            <CardContent>
              <Typography variant="h6" fontWeight="bold" gutterBottom>
                Performance Alerts & Recommendations
              </Typography>
              <Grid container spacing={2}>
                <Grid item xs={12} md={6}>
                  <Alert severity="warning" sx={{ mb: 1 }}>
                    <Typography variant="body2" fontWeight="medium">
                      Finnhub latency above threshold
                    </Typography>
                    <Typography variant="caption">
                      Average latency: 69ms (threshold: 60ms)
                    </Typography>
                  </Alert>
                  <Alert severity="info" sx={{ mb: 1 }}>
                    <Typography variant="body2" fontWeight="medium">
                      Polygon performing optimally
                    </Typography>
                    <Typography variant="caption">
                      Consistently low latency and error rates
                    </Typography>
                  </Alert>
                </Grid>
                <Grid item xs={12} md={6}>
                  <Alert severity="success" sx={{ mb: 1 }}>
                    <Typography variant="body2" fontWeight="medium">
                      Cost optimization opportunity
                    </Typography>
                    <Typography variant="caption">
                      Consider reducing Finnhub usage during low-volume periods
                    </Typography>
                  </Alert>
                  <Alert severity="warning" sx={{ mb: 1 }}>
                    <Typography variant="body2" fontWeight="medium">
                      High message volume detected
                    </Typography>
                    <Typography variant="caption">
                      Current: 1,460 msg/min (90% of limit)
                    </Typography>
                  </Alert>
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
};

export default RealTimeAnalytics;
