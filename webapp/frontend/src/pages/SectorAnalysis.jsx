import { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Alert,
  Box,
  Card,
  CardContent,
  Chip,
  Container,
  Divider,
  Grid,
  LinearProgress,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import {
  TrendingUp,
  TrendingDown,
  ExpandMore,
  ShowChart,
  BarChart,
} from "@mui/icons-material";
import {
  BarChart as RechartsBarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
  Tooltip,
} from "recharts";
import { useAuth } from "../contexts/AuthContext";
import api, { getMarketResearchIndicators } from "../services/api";
import {
  formatCurrency,
  formatPercentage,
  formatNumber,
  getChangeColor,
} from "../utils/formatters";

const SectorAnalysis = () => {
  const { user } = useAuth();
  const [sectorData, setSectorData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastUpdate, setLastUpdate] = useState(new Date());

  // Sector color mapping (for visualization consistency)
  const sectorColors = {
    "Technology": "#2196F3",
    "Healthcare": "#4CAF50",
    "Financials": "#FF9800",
    "Consumer Discretionary": "#9C27B0",
    "Consumer Staples": "#795548",
    "Energy": "#FF5722",
    "Industrials": "#607D8B",
    "Materials": "#8BC34A",
    "Utilities": "#FFC107",
    "Real Estate": "#E91E63",
    "Communication Services": "#00BCD4",
  };

  // Fetch sector performance data aggregated from industries
  const { data: rotationData, isLoading: rotationLoading, error: rotationError } = useQuery({
    queryKey: ["sector-performance"],
    queryFn: async () => {
      const response = await api.get("/api/market/sectors?limit=20&sortBy=overall_rank");
      return response.data;
    },
    staleTime: 60000,
    enabled: true,
    retry: false,
  });

  // Fetch industry performance data (IBD-style rankings)
  const { data: industryData, isLoading: industryLoading, error: industryError } = useQuery({
    queryKey: ["industry-performance"],
    queryFn: async () => {
      const response = await api.get("/api/market/industries?limit=20&sortBy=overall_rank");
      return response.data;
    },
    staleTime: 60000,
    enabled: true,
    retry: false,
  });

  useEffect(() => {
    loadSectorData();
  }, []);

  const loadSectorData = async () => {
    try {
      setError(null);
      setLoading(true);

      console.log("Loading sector analysis data from /api/sectors/performance");

      // Use the correct backend endpoint
      const resp = await api.get("/api/sectors/performance");

      if (resp?.data?.data && Array.isArray(resp.data.data)) {
        const sectors = resp.data.data.map((s) => ({
          sector: s.sector || "Unknown",
          price: parseFloat(s.avg_price || 0),
          change: 0,
          changePercent: parseFloat(s.performance_pct || 0),
          volume: parseInt(s.total_volume || 0),
          marketCap: parseInt(s.stock_count || 0) * 1e9, // Rough estimate
          color: sectorColors[s.sector] || "#666",
          dataSource: "database",
          stockCount: parseInt(s.stock_count || 0),
          gainingStocks: parseInt(s.gaining_stocks || 0),
          losingStocks: parseInt(s.losing_stocks || 0),
        }));

        setSectorData(sectors);
        setLastUpdate(new Date());
        console.log("✅ Sector data loaded:", sectors.length);
      } else {
        throw new Error("Invalid response structure from API");
      }
    } catch (error) {
      console.error("Failed to load sector data:", error);
      setError(`Failed to load sector data: ${error.message}`);
      setSectorData([]);
    } finally {
      setLoading(false);
    }
  };

  const formatTimeAgo = (date) => {
    const seconds = Math.floor((new Date() - date) / 1000);
    if (seconds < 60) return `${seconds}s ago`;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    return `${hours}h ago`;
  };

  // Prepare chart data
  const chartData = sectorData
    .filter((s) => !s.error)
    .map((s) => ({
      name: s.sector.length > 15 ? s.sector.substring(0, 15) + "..." : s.sector,
      fullName: s.sector,
      performance: parseFloat(s.changePercent.toFixed(2)),
      color: s.color,
    }))
    .sort((a, b) => b.performance - a.performance);

  const pieData = sectorData
    .filter((s) => !s.error)
    .map((s) => ({
      name: s.sector,
      value: s.marketCap / 1e12, // Convert to trillions
      color: s.color,
    }));

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      {/* Header */}
      <Box display="flex" alignItems="center" justifyContent="between" mb={4}>
        <Box>
          <Typography variant="h3" component="h1" gutterBottom>
            Sector Analysis
          </Typography>
          <Typography variant="body1" color="text.secondary">
            Comprehensive sector performance analysis and comparisons
          </Typography>
          <Box display="flex" gap={1} mt={1}>
            <Chip
              label={`${sectorData?.length || 0} sectors`}
              color="primary"
              size="small"
            />
            <Chip
              label={`Updated ${formatTimeAgo(lastUpdate)}`}
              color="info"
              size="small"
              variant="outlined"
            />
          </Box>
        </Box>
      </Box>

      {/* Loading State */}
      {loading && (
        <Card sx={{ mb: 3 }}>
          <CardContent>
            <Box display="flex" alignItems="center" gap={2} py={2}>
              <LinearProgress sx={{ flexGrow: 1 }} />
              <Typography>Loading sector analysis data...</Typography>
            </Box>
          </CardContent>
        </Card>
      )}

      {/* Error State */}
      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          <Typography variant="h6" gutterBottom>
            Failed to Load Sector Data
          </Typography>
          <Typography variant="body2">{error}</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
            Check database connection and ensure sector data is populated.
          </Typography>
        </Alert>
      )}

      {/* Performance Overview */}
      <Grid container spacing={3} mb={4}>
        <Grid item xs={12} md={8}>
          <Card>
            <CardContent>
              <Typography
                variant="h6"
                gutterBottom
                display="flex"
                alignItems="center"
                gap={1}
              >
                <BarChart color="primary" />
                Sector Performance Today
              </Typography>
              <Box height={400}>
                <ResponsiveContainer width="100%" height="100%">
                  <RechartsBarChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis
                      dataKey="name"
                      angle={-45}
                      textAnchor="end"
                      height={80}
                      interval={0}
                    />
                    <YAxis />
                    <Tooltip
                      formatter={(value) => [`${value}%`, "Performance"]}
                    />
                    <Bar
                      dataKey="performance"
                      fill={(entry) => entry.color}
                      radius={[4, 4, 0, 0]}
                    >
                      {(chartData || []).map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={entry.color} />
                      ))}
                    </Bar>
                  </RechartsBarChart>
                </ResponsiveContainer>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid item xs={12} md={4}>
          <Card>
            <CardContent>
              <Typography
                variant="h6"
                gutterBottom
                display="flex"
                alignItems="center"
                gap={1}
              >
                <ShowChart color="primary" />
                Market Cap Distribution
              </Typography>
              <Box height={400}>
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={pieData}
                      cx="50%"
                      cy="50%"
                      innerRadius={60}
                      outerRadius={120}
                      paddingAngle={2}
                      dataKey="value"
                    >
                      {(pieData || []).map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={entry.color} />
                      ))}
                    </Pie>
                    <Tooltip
                      formatter={(value) => [
                        `$${value.toFixed(1)}T`,
                        "Market Cap",
                      ]}
                    />
                    <Legend />
                  </PieChart>
                </ResponsiveContainer>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Top Sector Rankings */}
      <Card sx={{ mb: 4 }}>
        <CardContent>
          <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
            Top Sector Rankings
          </Typography>
          {rotationLoading ? (
            <Box display="flex" justifyContent="center" py={4}>
              <LinearProgress sx={{ width: "50%" }} />
            </Box>
          ) : rotationError ? (
            <Alert severity="error">
              Failed to load sector data: {rotationError?.message || rotationError?.error || String(rotationError)}
            </Alert>
          ) : !rotationData?.data?.sectors?.length ? (
            <Alert severity="warning">
              No sector data available in database. Run loadindustrydata.py loader.
            </Alert>
          ) : (
            <Box>
              {(rotationData?.data?.sectors || []).map((sector, index) => {
                // Find matching industry data for this sector
                const sectorIndustries = (industryData?.data?.industries || []).filter(
                  (ind) => ind.sector === sector.sector
                );

                return (
                  <Accordion key={index}>
                    <AccordionSummary
                      expandIcon={<ExpandMore />}
                      sx={{
                        backgroundColor: "grey.50",
                        "&:hover": { backgroundColor: "grey.100" },
                      }}
                    >
                      <Grid container spacing={2} alignItems="center">
                        <Grid item xs={12} sm={1}>
                          <Chip
                            label={`#${sector.overall_rank}`}
                            size="small"
                            color="primary"
                            variant="outlined"
                          />
                        </Grid>
                        <Grid item xs={12} sm={2}>
                          <Typography variant="body1" fontWeight="bold">
                            {sector.sector}
                          </Typography>
                        </Grid>
                        <Grid item xs={4} sm={2}>
                          <Chip
                            label={`RS ${sector.rs_rating}`}
                            size="small"
                            sx={{
                              bgcolor: sector.rs_rating >= 80
                                ? "success.main"
                                : sector.rs_rating >= 60
                                  ? "info.main"
                                  : sector.rs_rating >= 40
                                    ? "warning.main"
                                    : "error.main",
                              color: "white",
                              fontWeight: "bold",
                            }}
                          />
                        </Grid>
                        <Grid item xs={4} sm={2}>
                          <Chip
                            label={sector.momentum}
                            color={
                              sector.momentum === "Strong"
                                ? "success"
                                : sector.momentum === "Moderate"
                                  ? "info"
                                  : "default"
                            }
                            size="small"
                          />
                        </Grid>
                        <Grid item xs={4} sm={2}>
                          <Chip
                            label={sector.flow}
                            color={
                              sector.flow === "Inflow"
                                ? "success"
                                : sector.flow === "Outflow"
                                  ? "error"
                                  : "default"
                            }
                            size="small"
                          />
                        </Grid>
                        <Grid item xs={4} sm={2}>
                          <Typography
                            variant="body2"
                            fontWeight="bold"
                            sx={{ color: getChangeColor(sector.performance_20d) }}
                          >
                            {formatPercentage(sector.performance_20d)}
                          </Typography>
                        </Grid>
                        <Grid item xs={12} sm={1}>
                          <Chip
                            label={`${sector.industry_count} ind`}
                            size="small"
                            variant="outlined"
                          />
                        </Grid>
                      </Grid>
                    </AccordionSummary>
                    <AccordionDetails>
                      <Box sx={{ p: 2 }}>
                        <Typography variant="h6" gutterBottom>
                          Top Industries in {sector.sector}
                        </Typography>
                        {sectorIndustries.length > 0 ? (
                          <TableContainer>
                            <Table size="small">
                              <TableHead>
                                <TableRow>
                                  <TableCell>Industry</TableCell>
                                  <TableCell align="center">RS Rating</TableCell>
                                  <TableCell align="center">Momentum</TableCell>
                                  <TableCell align="center">Trend</TableCell>
                                  <TableCell align="right">20-Day %</TableCell>
                                  <TableCell align="right">Stocks</TableCell>
                                </TableRow>
                              </TableHead>
                              <TableBody>
                                {sectorIndustries.slice(0, 5).map((industry, idx) => {
                                  const rsColor =
                                    industry.rs_rating >= 80
                                      ? "success.main"
                                      : industry.rs_rating >= 60
                                        ? "info.main"
                                        : industry.rs_rating >= 40
                                          ? "warning.main"
                                          : "error.main";

                                  return (
                                    <TableRow key={idx}>
                                      <TableCell>
                                        <Typography variant="body2" fontWeight="bold">
                                          {industry.industry}
                                        </Typography>
                                      </TableCell>
                                      <TableCell align="center">
                                        <Chip
                                          label={industry.rs_rating}
                                          size="small"
                                          sx={{
                                            bgcolor: rsColor,
                                            color: "white",
                                            fontWeight: "bold",
                                          }}
                                        />
                                      </TableCell>
                                      <TableCell align="center">
                                        <Chip
                                          label={industry.momentum}
                                          color={
                                            industry.momentum === "Strong"
                                              ? "success"
                                              : industry.momentum === "Moderate"
                                                ? "info"
                                                : "default"
                                          }
                                          size="small"
                                        />
                                      </TableCell>
                                      <TableCell align="center">
                                        <Box display="flex" alignItems="center" justifyContent="center" gap={0.5}>
                                          {industry.trend === "Uptrend" && (
                                            <TrendingUp color="success" fontSize="small" />
                                          )}
                                          {industry.trend === "Downtrend" && (
                                            <TrendingDown color="error" fontSize="small" />
                                          )}
                                          <Typography variant="body2">{industry.trend}</Typography>
                                        </Box>
                                      </TableCell>
                                      <TableCell
                                        align="right"
                                        sx={{
                                          color: getChangeColor(industry.performance_20d),
                                          fontWeight: 600,
                                        }}
                                      >
                                        {formatPercentage(industry.performance_20d)}
                                      </TableCell>
                                      <TableCell align="right">
                                        {industry.stock_count}
                                      </TableCell>
                                    </TableRow>
                                  );
                                })}
                              </TableBody>
                            </Table>
                          </TableContainer>
                        ) : (
                          <Typography variant="body2" color="text.secondary">
                            No industry data available for this sector
                          </Typography>
                        )}
                      </Box>
                    </AccordionDetails>
                  </Accordion>
                );
              })}
            </Box>
          )}
        </CardContent>
      </Card>

      {/* Top Industry Rankings */}
      <Card sx={{ mb: 4 }}>
        <CardContent>
          <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
            Top Industry Rankings
          </Typography>
          {industryLoading ? (
            <Box display="flex" justifyContent="center" py={4}>
              <LinearProgress sx={{ width: "50%" }} />
            </Box>
          ) : industryError ? (
            <Alert severity="warning">
              Industry rankings not available. Run loadindustrydata.py to populate data.
            </Alert>
          ) : !industryData?.data?.industries?.length ? (
            <Alert severity="info">
              No industry performance data available yet. Run loadindustrydata.py loader.
            </Alert>
          ) : (
            <Box>
              {(industryData?.data?.industries || []).map((industry, index) => {
                const rsColor =
                  industry.rs_rating >= 80
                    ? "success.main"
                    : industry.rs_rating >= 60
                      ? "info.main"
                      : industry.rs_rating >= 40
                        ? "warning.main"
                        : "error.main";

                return (
                  <Accordion key={index}>
                    <AccordionSummary
                      expandIcon={<ExpandMore />}
                      sx={{
                        backgroundColor: "grey.50",
                        "&:hover": { backgroundColor: "grey.100" },
                      }}
                    >
                      <Grid container spacing={2} alignItems="center">
                        <Grid item xs={12} sm={1}>
                          <Chip
                            label={`#${industry.overall_rank}`}
                            size="small"
                            color="primary"
                            variant="outlined"
                          />
                        </Grid>
                        <Grid item xs={12} sm={3}>
                          <Typography variant="body1" fontWeight="bold">
                            {industry.industry}
                          </Typography>
                          <Typography variant="caption" color="text.secondary">
                            {industry.sector}
                          </Typography>
                        </Grid>
                        <Grid item xs={4} sm={2}>
                          <Chip
                            label={`RS ${industry.rs_rating}`}
                            size="small"
                            sx={{
                              bgcolor: rsColor,
                              color: "white",
                              fontWeight: "bold",
                            }}
                          />
                        </Grid>
                        <Grid item xs={4} sm={2}>
                          <Chip
                            label={industry.momentum}
                            color={
                              industry.momentum === "Strong"
                                ? "success"
                                : industry.momentum === "Moderate"
                                  ? "info"
                                  : "default"
                            }
                            size="small"
                          />
                        </Grid>
                        <Grid item xs={4} sm={2}>
                          <Box display="flex" alignItems="center" gap={0.5}>
                            {industry.trend === "Uptrend" && (
                              <TrendingUp color="success" fontSize="small" />
                            )}
                            {industry.trend === "Downtrend" && (
                              <TrendingDown color="error" fontSize="small" />
                            )}
                            <Typography variant="body2">{industry.trend}</Typography>
                          </Box>
                        </Grid>
                        <Grid item xs={12} sm={2}>
                          <Typography
                            variant="body2"
                            fontWeight="bold"
                            sx={{ color: getChangeColor(industry.performance_20d) }}
                          >
                            {formatPercentage(industry.performance_20d)}
                          </Typography>
                        </Grid>
                      </Grid>
                    </AccordionSummary>
                    <AccordionDetails>
                      <Box sx={{ p: 2 }}>
                        <Grid container spacing={3}>
                          {/* Performance Metrics */}
                          <Grid item xs={12} md={6}>
                            <Typography variant="subtitle2" gutterBottom fontWeight="bold">
                              Performance Metrics
                            </Typography>
                            <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
                              <Box display="flex" justifyContent="space-between">
                                <Typography variant="body2" color="text.secondary">
                                  1-Day Performance:
                                </Typography>
                                <Typography
                                  variant="body2"
                                  fontWeight="bold"
                                  sx={{ color: getChangeColor(industry.performance_1d) }}
                                >
                                  {formatPercentage(industry.performance_1d)}
                                </Typography>
                              </Box>
                              <Box display="flex" justifyContent="space-between">
                                <Typography variant="body2" color="text.secondary">
                                  5-Day Performance:
                                </Typography>
                                <Typography
                                  variant="body2"
                                  fontWeight="bold"
                                  sx={{ color: getChangeColor(industry.performance_5d) }}
                                >
                                  {formatPercentage(industry.performance_5d)}
                                </Typography>
                              </Box>
                              <Box display="flex" justifyContent="space-between">
                                <Typography variant="body2" color="text.secondary">
                                  20-Day Performance:
                                </Typography>
                                <Typography
                                  variant="body2"
                                  fontWeight="bold"
                                  sx={{ color: getChangeColor(industry.performance_20d) }}
                                >
                                  {formatPercentage(industry.performance_20d)}
                                </Typography>
                              </Box>
                              <Divider />
                              <Box display="flex" justifyContent="space-between">
                                <Typography variant="body2" color="text.secondary">
                                  RS vs SPY:
                                </Typography>
                                <Typography
                                  variant="body2"
                                  fontWeight="bold"
                                  sx={{ color: getChangeColor(industry.rs_vs_spy) }}
                                >
                                  {formatPercentage(industry.rs_vs_spy)}
                                </Typography>
                              </Box>
                              <Box display="flex" justifyContent="space-between">
                                <Typography variant="body2" color="text.secondary">
                                  Avg Change %:
                                </Typography>
                                <Typography
                                  variant="body2"
                                  fontWeight="bold"
                                  sx={{ color: getChangeColor(industry.avg_change_percent) }}
                                >
                                  {formatPercentage(industry.avg_change_percent)}
                                </Typography>
                              </Box>
                            </Box>
                          </Grid>

                          {/* Volume & Market Cap */}
                          <Grid item xs={12} md={6}>
                            <Typography variant="subtitle2" gutterBottom fontWeight="bold">
                              Volume & Market Metrics
                            </Typography>
                            <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
                              <Box display="flex" justifyContent="space-between">
                                <Typography variant="body2" color="text.secondary">
                                  Stock Count:
                                </Typography>
                                <Typography variant="body2" fontWeight="bold">
                                  {industry.stock_count}
                                </Typography>
                              </Box>
                              <Box display="flex" justifyContent="space-between">
                                <Typography variant="body2" color="text.secondary">
                                  Total Volume:
                                </Typography>
                                <Typography variant="body2" fontWeight="bold">
                                  {formatNumber(industry.total_volume)}
                                </Typography>
                              </Box>
                              <Box display="flex" justifyContent="space-between">
                                <Typography variant="body2" color="text.secondary">
                                  Avg Volume:
                                </Typography>
                                <Typography variant="body2" fontWeight="bold">
                                  {formatNumber(industry.avg_volume)}
                                </Typography>
                              </Box>
                              <Divider />
                              <Box display="flex" justifyContent="space-between">
                                <Typography variant="body2" color="text.secondary">
                                  Total Market Cap:
                                </Typography>
                                <Typography variant="body2" fontWeight="bold">
                                  ${formatNumber(industry.total_market_cap / 1e9, 1)}B
                                </Typography>
                              </Box>
                              <Box display="flex" justifyContent="space-between">
                                <Typography variant="body2" color="text.secondary">
                                  Avg Market Cap:
                                </Typography>
                                <Typography variant="body2" fontWeight="bold">
                                  ${formatNumber(industry.avg_market_cap / 1e9, 1)}B
                                </Typography>
                              </Box>
                            </Box>
                          </Grid>

                          {/* Top Stocks in Industry */}
                          <Grid item xs={12}>
                            <Typography variant="subtitle2" gutterBottom fontWeight="bold">
                              Top Stocks in {industry.industry}
                            </Typography>
                            <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1, mt: 1 }}>
                              {(industry.stock_symbols || []).slice(0, 10).map((symbol, idx) => (
                                <Chip
                                  key={idx}
                                  label={symbol}
                                  size="small"
                                  variant="outlined"
                                  sx={{ fontFamily: "monospace" }}
                                />
                              ))}
                              {industry.stock_symbols?.length > 10 && (
                                <Chip
                                  label={`+${industry.stock_symbols.length - 10} more`}
                                  size="small"
                                  variant="outlined"
                                  color="primary"
                                />
                              )}
                            </Box>
                          </Grid>
                        </Grid>
                      </Box>
                    </AccordionDetails>
                  </Accordion>
                );
              })}
            </Box>
          )}
          {industryData?.data?.summary && (
            <Box
              sx={{
                mt: 2,
                pt: 2,
                borderTop: "1px solid",
                borderColor: "divider",
              }}
            >
              <Typography variant="body2" color="text.secondary">
                Showing top {industryData.data.industries?.length || 0} of{" "}
                {industryData.data.summary.total_industries} industries |{" "}
                Avg 20-Day Performance:{" "}
                <strong>
                  {formatPercentage(
                    industryData.data.summary.avg_performance_20d
                  )}
                </strong>
              </Typography>
            </Box>
          )}
        </CardContent>
      </Card>

    </Container>
  );
};

export default SectorAnalysis;
