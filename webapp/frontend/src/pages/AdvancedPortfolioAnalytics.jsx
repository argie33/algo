import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Box,
  Typography,
  Grid,
  Card,
  CardContent,
  CardHeader,
  Paper,
  Tabs,
  Tab,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Button,
  Chip,
  LinearProgress,
  Alert,
  List,
  ListItem,
  ListItemText,
  Divider,
} from "@mui/material";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  AreaChart,
  Area,
  BarChart,
  Bar,
} from "recharts";
import {
  TrendingUp,
  Assessment,
  AccountBalance,
  ShowChart,
  Analytics,
  Timeline,
  PieChart as PieChartIcon,
  BarChart as BarChartIcon,
  Download,
  Refresh,
  Warning,
  CheckCircle,
  Error,
} from "@mui/icons-material";
import {
  getPerformanceAnalytics,
  getRiskAnalytics,
  getCorrelationAnalytics,
  getAllocationAnalytics,
  getReturnsAnalytics,
  getSectorsAnalytics,
  getVolatilityAnalytics,
  getTrendsAnalytics,
  exportAnalytics,
} from "../services/api";
import ErrorBoundary from "../components/ErrorBoundary";

const COLORS = [
  "#0088FE",
  "#00C49F",
  "#FFBB28",
  "#FF8042",
  "#8884D8",
  "#82CA9D",
];

const AdvancedPortfolioAnalytics = () => {
  const [activeTab, setActiveTab] = useState(0);
  const [timePeriod, setTimePeriod] = useState("1m");
  const [benchmark, setBenchmark] = useState("SPY");
  const queryClient = useQueryClient();

  // Performance Analytics Query
  const {
    data: performanceData,
    isLoading: performanceLoading,
    error: performanceError,
  } = useQuery({
    queryKey: ["performanceAnalytics", timePeriod, benchmark],
    queryFn: () => getPerformanceAnalytics(timePeriod, benchmark),
    staleTime: 60000,
    retry: 2,
  });

  // Risk Analytics Query
  const { data: riskData, isLoading: riskLoading } = useQuery({
    queryKey: ["riskAnalytics", timePeriod],
    queryFn: () => getRiskAnalytics(timePeriod),
    staleTime: 60000,
  });

  // Correlation Analytics Query
  const { data: correlationData, isLoading: correlationLoading } = useQuery({
    queryKey: ["correlationAnalytics", timePeriod],
    queryFn: () => getCorrelationAnalytics(timePeriod),
    staleTime: 300000, // 5 minutes for correlation data
  });

  // Allocation Analytics Query
  const { data: allocationData, isLoading: allocationLoading } = useQuery({
    queryKey: ["allocationAnalytics"],
    queryFn: () => getAllocationAnalytics(),
    staleTime: 120000,
  });

  // Returns Analytics Query
  const { data: _returnsData, isLoading: returnsLoading } = useQuery({
    queryKey: ["returnsAnalytics", timePeriod],
    queryFn: () => getReturnsAnalytics(timePeriod),
    staleTime: 60000,
  });

  // Sectors Analytics Query
  const { data: _sectorsData, isLoading: sectorsLoading } = useQuery({
    queryKey: ["sectorsAnalytics"],
    queryFn: () => getSectorsAnalytics(),
    staleTime: 120000,
  });

  // Volatility Analytics Query
  const { data: volatilityData, isLoading: volatilityLoading } = useQuery({
    queryKey: ["volatilityAnalytics", timePeriod],
    queryFn: () => getVolatilityAnalytics(timePeriod),
    staleTime: 60000,
  });

  // Trends Analytics Query
  const { data: trendsData, isLoading: trendsLoading } = useQuery({
    queryKey: ["trendsAnalytics", timePeriod],
    queryFn: () => getTrendsAnalytics(timePeriod),
    staleTime: 60000,
  });

  const handleRefresh = () => {
    queryClient.invalidateQueries({ queryKey: ["performanceAnalytics"] });
    queryClient.invalidateQueries({ queryKey: ["riskAnalytics"] });
    queryClient.invalidateQueries({ queryKey: ["correlationAnalytics"] });
    queryClient.invalidateQueries({ queryKey: ["allocationAnalytics"] });
    queryClient.invalidateQueries({ queryKey: ["returnsAnalytics"] });
    queryClient.invalidateQueries({ queryKey: ["sectorsAnalytics"] });
    queryClient.invalidateQueries({ queryKey: ["volatilityAnalytics"] });
    queryClient.invalidateQueries({ queryKey: ["trendsAnalytics"] });
  };

  const handleExport = async () => {
    try {
      const exportData = await exportAnalytics("json", "performance");
      const blob = new Blob([JSON.stringify(exportData, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `portfolio-analytics-${new Date().toISOString().split("T")[0]}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (error) {
      console.error("Export failed:", error);
    }
  };

  const getRiskColor = (riskLevel) => {
    switch (riskLevel?.toLowerCase()) {
      case "low":
        return "#4caf50";
      case "medium":
        return "#ff9800";
      case "high":
        return "#f44336";
      default:
        return "#757575";
    }
  };

  const getRiskIcon = (riskLevel) => {
    switch (riskLevel?.toLowerCase()) {
      case "low":
        return <CheckCircle sx={{ color: "#4caf50" }} />;
      case "medium":
        return <Warning sx={{ color: "#ff9800" }} />;
      case "high":
        return <Error sx={{ color: "#f44336" }} />;
      default:
        return <Assessment />;
    }
  };

  const renderPerformanceTab = () => (
    <Box>
      <Grid container spacing={3}>
        {/* Performance Summary Cards */}
        <Grid item xs={12}>
          <Grid container spacing={2}>
            <Grid item xs={12} sm={6} md={3}>
              <Card>
                <CardContent>
                  <Box display="flex" alignItems="center" gap={2}>
                    <TrendingUp color="primary" />
                    <Box>
                      <Typography variant="h6">
                        {performanceData?.data?.returns
                          ? `${(performanceData.data.returns * 100).toFixed(2)}%`
                          : "N/A"}
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        Total Return
                      </Typography>
                    </Box>
                  </Box>
                </CardContent>
              </Card>
            </Grid>

            <Grid item xs={12} sm={6} md={3}>
              <Card>
                <CardContent>
                  <Box display="flex" alignItems="center" gap={2}>
                    <ShowChart color="secondary" />
                    <Box>
                      <Typography variant="h6">
                        {performanceData?.data?.volatility
                          ? `${(performanceData.data.volatility * 100).toFixed(2)}%`
                          : "N/A"}
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        Volatility
                      </Typography>
                    </Box>
                  </Box>
                </CardContent>
              </Card>
            </Grid>

            <Grid item xs={12} sm={6} md={3}>
              <Card>
                <CardContent>
                  <Box display="flex" alignItems="center" gap={2}>
                    <Timeline />
                    <Box>
                      <Typography variant="h6">
                        {performanceData?.data?.sharpe_ratio
                          ? performanceData.data.sharpe_ratio.toFixed(2)
                          : "N/A"}
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        Sharpe Ratio
                      </Typography>
                    </Box>
                  </Box>
                </CardContent>
              </Card>
            </Grid>

            <Grid item xs={12} sm={6} md={3}>
              <Card>
                <CardContent>
                  <Box display="flex" alignItems="center" gap={2}>
                    <AccountBalance />
                    <Box>
                      <Typography variant="h6">
                        {performanceData?.data?.portfolio_metrics?.total_value
                          ? `$${parseFloat(performanceData.data.portfolio_metrics.total_value).toLocaleString()}`
                          : "N/A"}
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        Portfolio Value
                      </Typography>
                    </Box>
                  </Box>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        </Grid>

        {/* Performance Chart */}
        <Grid item xs={12} lg={8}>
          <Card>
            <CardHeader title="Performance vs Benchmark" />
            <CardContent>
              <ResponsiveContainer width="100%" height={400}>
                <LineChart
                  data={performanceData?.data?.performance_timeline || []}
                >
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis
                    dataKey="date"
                    tickFormatter={(value) =>
                      new Date(value).toLocaleDateString()
                    }
                  />
                  <YAxis tickFormatter={(value) => `${value}%`} />
                  <Tooltip
                    formatter={(value, name) => [
                      `${parseFloat(value).toFixed(2)}%`,
                      name,
                    ]}
                    labelFormatter={(value) =>
                      new Date(value).toLocaleDateString()
                    }
                  />
                  <Legend />
                  <Line
                    type="monotone"
                    dataKey="pnl_percent"
                    stroke="#8884d8"
                    strokeWidth={2}
                    name="Portfolio"
                  />
                  <Line
                    type="monotone"
                    dataKey="benchmark_return"
                    stroke="#82ca9d"
                    strokeWidth={2}
                    name={`${benchmark} Benchmark`}
                    data={
                      performanceData?.data?.benchmark_comparison?.data || []
                    }
                  />
                </LineChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </Grid>

        {/* Top/Bottom Performers */}
        <Grid item xs={12} lg={4}>
          <Card>
            <CardHeader title="Top Performers" />
            <CardContent>
              <List>
                {(
                  performanceData?.data?.portfolio_metrics?.top_performers || []
                )
                  .slice(0, 5)
                  .map((stock, index) => (
                    <ListItem key={index}>
                      <ListItemText
                        primary={stock.symbol}
                        secondary={`${stock.return_percent}% return`}
                      />
                      <Chip
                        label={`+${stock.return_percent}%`}
                        color="success"
                        size="small"
                      />
                    </ListItem>
                  ))}
              </List>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );

  const renderRiskTab = () => (
    <Box>
      <Grid container spacing={3}>
        {/* Risk Summary */}
        <Grid item xs={12}>
          <Card>
            <CardHeader
              title="Risk Assessment"
              action={
                riskData?.data?.risk?.risk_assessment?.overall_risk && (
                  <Chip
                    label={riskData.data.risk.risk_assessment.overall_risk}
                    color={
                      riskData.data.risk.risk_assessment.overall_risk === "Low"
                        ? "success"
                        : riskData.data.risk.risk_assessment.overall_risk ===
                            "Medium"
                          ? "warning"
                          : "error"
                    }
                    icon={getRiskIcon(
                      riskData.data.risk.risk_assessment.overall_risk
                    )}
                  />
                )
              }
            />
            <CardContent>
              <Grid container spacing={3}>
                <Grid item xs={12} md={6}>
                  <Typography variant="h6" gutterBottom>
                    Risk Metrics
                  </Typography>
                  <List>
                    <ListItem>
                      <ListItemText
                        primary="Portfolio Volatility"
                        secondary={`${riskData?.data?.risk?.portfolio_metrics?.portfolio_volatility || "N/A"}%`}
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText
                        primary="Max Drawdown"
                        secondary={`${riskData?.data?.risk?.portfolio_metrics?.max_drawdown || "N/A"}%`}
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText
                        primary="Value at Risk (95%)"
                        secondary={`${riskData?.data?.risk?.portfolio_metrics?.value_at_risk_95 || "N/A"}%`}
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemText
                        primary="Concentration Risk"
                        secondary={
                          riskData?.data?.risk?.portfolio_metrics
                            ?.concentration_risk || "N/A"
                        }
                      />
                    </ListItem>
                  </List>
                </Grid>

                <Grid item xs={12} md={6}>
                  <Typography variant="h6" gutterBottom>
                    Position Analysis
                  </Typography>
                  <List>
                    {(
                      riskData?.data?.risk?.position_analysis
                        ?.position_breakdown || []
                    )
                      .slice(0, 5)
                      .map((position, index) => (
                        <ListItem key={index}>
                          <ListItemText
                            primary={position.symbol}
                            secondary={`${position.position_weight}% of portfolio`}
                          />
                          <Chip
                            label={`${position.unrealized_return}%`}
                            color={
                              parseFloat(position.unrealized_return) >= 0
                                ? "success"
                                : "error"
                            }
                            size="small"
                          />
                        </ListItem>
                      ))}
                  </List>
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );

  const renderAllocationTab = () => (
    <Box>
      <Grid container spacing={3}>
        {/* Sector Allocation */}
        <Grid item xs={12} lg={6}>
          <Card>
            <CardHeader title="Sector Allocation" />
            <CardContent>
              <ResponsiveContainer width="100%" height={400}>
                <PieChart>
                  <Pie
                    data={allocationData?.data?.sectors || []}
                    dataKey="percentage"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    outerRadius={120}
                    fill="#8884d8"
                    label={({ name, percentage }) => `${name}: ${percentage}%`}
                  >
                    {(allocationData?.data?.sectors || []).map((_, index) => (
                      <Cell
                        key={`cell-${index}`}
                        fill={COLORS[index % COLORS.length]}
                      />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </Grid>

        {/* Asset Allocation */}
        <Grid item xs={12} lg={6}>
          <Card>
            <CardHeader title="Top Holdings" />
            <CardContent>
              <ResponsiveContainer width="100%" height={400}>
                <BarChart
                  data={(allocationData?.data?.assets || []).slice(0, 10)}
                >
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="symbol" />
                  <YAxis tickFormatter={(value) => `${value}%`} />
                  <Tooltip formatter={(value) => [`${value}%`, "Weight"]} />
                  <Bar dataKey="percentage" fill="#8884d8" />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </Grid>

        {/* Allocation Summary */}
        <Grid item xs={12}>
          <Card>
            <CardHeader title="Portfolio Holdings" />
            <CardContent>
              <List>
                {(allocationData?.data?.assets || []).map((asset, index) => (
                  <Box key={index}>
                    <ListItem>
                      <ListItemText
                        primary={asset.symbol}
                        secondary={`${asset.shares} shares • ${asset.sector}`}
                      />
                      <Box sx={{ minWidth: 100, textAlign: "right" }}>
                        <Typography variant="body2">
                          ${parseFloat(asset.value).toLocaleString()}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          {asset.percentage}%
                        </Typography>
                      </Box>
                    </ListItem>
                    {index < allocationData.data.assets.length - 1 && (
                      <Divider />
                    )}
                  </Box>
                ))}
              </List>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );

  const renderCorrelationTab = () => (
    <Box>
      <Grid container spacing={3}>
        {/* Correlation Insights */}
        <Grid item xs={12}>
          <Card>
            <CardHeader title="Correlation Analysis" />
            <CardContent>
              <Grid container spacing={3}>
                <Grid item xs={12} md={4}>
                  <Box textAlign="center" p={2}>
                    <Typography variant="h4" color="primary">
                      {correlationData?.data?.correlations?.insights
                        ?.diversification_score || "N/A"}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      Diversification Score
                    </Typography>
                  </Box>
                </Grid>
                <Grid item xs={12} md={4}>
                  <Box textAlign="center" p={2}>
                    <Typography variant="h6">
                      {correlationData?.data?.correlations?.insights
                        ?.average_correlation || "N/A"}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      Average Correlation
                    </Typography>
                  </Box>
                </Grid>
                <Grid item xs={12} md={4}>
                  <Box textAlign="center" p={2}>
                    <Typography variant="h6">
                      {correlationData?.data?.correlations?.assets_analyzed ||
                        "N/A"}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      Assets Analyzed
                    </Typography>
                  </Box>
                </Grid>
              </Grid>

              {correlationData?.data?.correlations?.insights && (
                <Box mt={3}>
                  <Typography variant="h6" gutterBottom>
                    Key Insights
                  </Typography>
                  <Grid container spacing={2}>
                    <Grid item xs={12} md={6}>
                      <Alert severity="info">
                        <Typography variant="subtitle2">
                          Highest Correlation
                        </Typography>
                        <Typography variant="body2">
                          {correlationData.data.correlations.insights.highest_correlation?.pair?.join(
                            " - "
                          ) || "N/A"}
                          :{" "}
                          {correlationData.data.correlations.insights.highest_correlation?.value?.toFixed(
                            3
                          ) || "N/A"}
                        </Typography>
                      </Alert>
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <Alert severity="success">
                        <Typography variant="subtitle2">
                          Lowest Correlation
                        </Typography>
                        <Typography variant="body2">
                          {correlationData.data.correlations.insights.lowest_correlation?.pair?.join(
                            " - "
                          ) || "N/A"}
                          :{" "}
                          {correlationData.data.correlations.insights.lowest_correlation?.value?.toFixed(
                            3
                          ) || "N/A"}
                        </Typography>
                      </Alert>
                    </Grid>
                  </Grid>
                </Box>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );

  const renderVolatilityTab = () => (
    <Box>
      <Grid container spacing={3}>
        <Grid item xs={12} lg={6}>
          <Card>
            <CardHeader title="Volatility Analysis" />
            <CardContent>
              <Grid container spacing={3}>
                <Grid item xs={6}>
                  <Box textAlign="center" p={2}>
                    <Typography
                      variant="h5"
                      sx={{
                        color: getRiskColor(
                          volatilityData?.data?.volatility?.risk_level
                        ),
                      }}
                    >
                      {volatilityData?.data?.volatility
                        ?.annualized_volatility || "N/A"}
                      %
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      Annualized Volatility
                    </Typography>
                  </Box>
                </Grid>
                <Grid item xs={6}>
                  <Box textAlign="center" p={2}>
                    <Chip
                      label={
                        volatilityData?.data?.volatility?.risk_level ||
                        "Unknown"
                      }
                      color={
                        volatilityData?.data?.volatility?.risk_level === "Low"
                          ? "success"
                          : volatilityData?.data?.volatility?.risk_level ===
                              "Medium"
                            ? "warning"
                            : "error"
                      }
                      icon={getRiskIcon(
                        volatilityData?.data?.volatility?.risk_level
                      )}
                    />
                    <Typography variant="body2" color="text.secondary" mt={1}>
                      Risk Level
                    </Typography>
                  </Box>
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} lg={6}>
          <Card>
            <CardHeader title="Trend Analysis" />
            <CardContent>
              <Grid container spacing={3}>
                <Grid item xs={6}>
                  <Box textAlign="center" p={2}>
                    <Typography variant="h6">
                      {trendsData?.data?.trends?.trend_direction || "Unknown"}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      Trend Direction
                    </Typography>
                  </Box>
                </Grid>
                <Grid item xs={6}>
                  <Box textAlign="center" p={2}>
                    <Typography variant="h6">
                      {trendsData?.data?.trends?.trend_strength || "Unknown"}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      Trend Strength
                    </Typography>
                  </Box>
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </Grid>

        {/* Volatility Chart */}
        <Grid item xs={12}>
          <Card>
            <CardHeader title="Daily Returns Distribution" />
            <CardContent>
              <ResponsiveContainer width="100%" height={400}>
                <AreaChart
                  data={volatilityData?.data?.volatility?.returns_data || []}
                >
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis
                    dataKey="date"
                    tickFormatter={(value) =>
                      new Date(value).toLocaleDateString()
                    }
                  />
                  <YAxis tickFormatter={(value) => `${value}%`} />
                  <Tooltip
                    formatter={(value) => [
                      `${parseFloat(value).toFixed(3)}%`,
                      "Daily Return",
                    ]}
                    labelFormatter={(value) =>
                      new Date(value).toLocaleDateString()
                    }
                  />
                  <Area
                    type="monotone"
                    dataKey="daily_return"
                    stroke="#8884d8"
                    fill="#8884d8"
                    fillOpacity={0.3}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );

  const isLoading =
    performanceLoading ||
    riskLoading ||
    correlationLoading ||
    allocationLoading ||
    returnsLoading ||
    sectorsLoading ||
    volatilityLoading ||
    trendsLoading;

  return (
    <ErrorBoundary>
      <Box sx={{ maxWidth: 1400, margin: "auto", p: 3 }}>
        {/* Header */}
        <Box
          display="flex"
          justifyContent="space-between"
          alignItems="center"
          mb={3}
        >
          <Typography variant="h4" component="h1" fontWeight="bold">
            Advanced Portfolio Analytics
          </Typography>
          <Box display="flex" gap={2}>
            <Button
              variant="outlined"
              startIcon={<Refresh />}
              onClick={handleRefresh}
              disabled={isLoading}
            >
              Refresh
            </Button>
            <Button
              variant="contained"
              startIcon={<Download />}
              onClick={handleExport}
              disabled={isLoading}
            >
              Export
            </Button>
          </Box>
        </Box>

        {/* Controls */}
        <Paper sx={{ p: 2, mb: 3 }}>
          <Grid container spacing={2} alignItems="center">
            <Grid item xs={12} sm={4}>
              <FormControl fullWidth size="small">
                <InputLabel>Time Period</InputLabel>
                <Select
                  value={timePeriod}
                  label="Time Period"
                  onChange={(e) => setTimePeriod(e.target.value)}
                >
                  <MenuItem value="1d">1 Day</MenuItem>
                  <MenuItem value="1w">1 Week</MenuItem>
                  <MenuItem value="1m">1 Month</MenuItem>
                  <MenuItem value="3m">3 Months</MenuItem>
                  <MenuItem value="6m">6 Months</MenuItem>
                  <MenuItem value="1y">1 Year</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={4}>
              <FormControl fullWidth size="small">
                <InputLabel>Benchmark</InputLabel>
                <Select
                  value={benchmark}
                  label="Benchmark"
                  onChange={(e) => setBenchmark(e.target.value)}
                >
                  <MenuItem value="SPY">S&P 500 (SPY)</MenuItem>
                  <MenuItem value="QQQ">NASDAQ-100 (QQQ)</MenuItem>
                  <MenuItem value="VTI">Total Stock Market (VTI)</MenuItem>
                  <MenuItem value="IWM">Russell 2000 (IWM)</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={4}>
              <Box display="flex" alignItems="center" gap={1}>
                <Analytics color="primary" />
                <Typography variant="body2" color="text.secondary">
                  Last updated: {new Date().toLocaleTimeString()}
                </Typography>
              </Box>
            </Grid>
          </Grid>
        </Paper>

        {/* Loading indicator */}
        {isLoading && <LinearProgress sx={{ mb: 2 }} />}

        {/* Error handling */}
        {performanceError && (
          <Alert severity="error" sx={{ mb: 2 }}>
            Failed to load performance data: {performanceError.message}
          </Alert>
        )}

        {/* Analytics Tabs */}
        <Paper sx={{ width: "100%" }}>
          <Tabs
            value={activeTab}
            onChange={(_, newValue) => setActiveTab(newValue)}
            variant="scrollable"
            scrollButtons="auto"
          >
            <Tab icon={<TrendingUp />} label="Performance" />
            <Tab icon={<Assessment />} label="Risk Analysis" />
            <Tab icon={<PieChartIcon />} label="Asset Allocation" />
            <Tab icon={<BarChartIcon />} label="Correlation" />
            <Tab icon={<ShowChart />} label="Volatility & Trends" />
          </Tabs>

          <Box sx={{ p: 3 }}>
            {activeTab === 0 && renderPerformanceTab()}
            {activeTab === 1 && renderRiskTab()}
            {activeTab === 2 && renderAllocationTab()}
            {activeTab === 3 && renderCorrelationTab()}
            {activeTab === 4 && renderVolatilityTab()}
          </Box>
        </Paper>
      </Box>
    </ErrorBoundary>
  );
};

export default AdvancedPortfolioAnalytics;
