import { useState } from "react";
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
import api from "../services/api";
import {
  formatPercentage,
  getChangeColor,
} from "../utils/formatters";

const SectorAnalysis = () => {
  const [lastUpdate] = useState(new Date());

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

  // Fetch sector performance data with historical rankings
  const { data: rotationData, isLoading: rotationLoading, error: rotationError } = useQuery({
    queryKey: ["sector-performance-history"],
    queryFn: async () => {
      const response = await api.get("/api/market/sectors-with-history?limit=20&sortBy=current_rank");
      return response.data;
    },
    staleTime: 60000,
    enabled: true,
    retry: false,
  });

  // Fetch industry performance data with historical rankings
  const { data: industryData, isLoading: industryLoading, error: industryError } = useQuery({
    queryKey: ["industry-performance-history"],
    queryFn: async () => {
      const response = await api.get("/api/market/industries-with-history?limit=50&sortBy=current_rank");
      return response.data;
    },
    staleTime: 60000,
    enabled: true,
    retry: false,
  });



  const formatTimeAgo = (date) => {
    const seconds = Math.floor((new Date() - date) / 1000);
    if (seconds < 60) return `${seconds}s ago`;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    return `${hours}h ago`;
  };

  // Prepare chart data from rotation data
  const chartData = (rotationData?.data?.sectors || [])
    .filter((s) => s.sector && s.performance_1d != null)
    .map((s) => ({
      name: s.sector.length > 15 ? s.sector.substring(0, 15) + "..." : s.sector,
      fullName: s.sector,
      performance: parseFloat(s.performance_1d.toFixed(2)),
      color: sectorColors[s.sector] || "#666",
    }))
    .sort((a, b) => b.performance - a.performance);

  const pieData = (rotationData?.data?.sectors || [])
    .filter((s) => s.sector && s.price != null)
    .map((s) => ({
      name: s.sector,
      value: s.price, // Use price as proxy for market cap
      color: sectorColors[s.sector] || "#666",
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
              label={`${rotationData?.data?.sectors?.length || 0} sectors`}
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



      {/* Sector Rankings */}
      <Card sx={{ mb: 4 }}>
        <CardContent>
          <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
            Sector Rankings
          </Typography>
          {rotationLoading ? (
            <Box display="flex" justifyContent="center" py={4}>
              <LinearProgress sx={{ width: "50%" }} />
            </Box>
          ) : rotationError ? (
            <Alert severity="warning">
              Sector data not available.
            </Alert>
          ) : !rotationData?.data?.sectors?.length ? (
            <Alert severity="info">
              No sector data available.
            </Alert>
          ) : (
            <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
              {/* Header Row */}
              <Box sx={{ display: "flex", mb: 1, px: 2 }}>
                <Grid container spacing={2} alignItems="center" sx={{ width: "100%", fontWeight: "bold" }}>
                  <Grid item xs={12} sm={1.5}>
                    <Typography variant="caption" fontWeight="bold">Sector</Typography>
                  </Grid>
                  <Grid item xs={3} sm={1.2}>
                    <Typography variant="caption" fontWeight="bold" align="center">Rank</Typography>
                  </Grid>
                  <Grid item xs={3} sm={1}>
                    <Typography variant="caption" fontWeight="bold" align="center">1W Ago</Typography>
                  </Grid>
                  <Grid item xs={3} sm={1}>
                    <Typography variant="caption" fontWeight="bold" align="center">4W Ago</Typography>
                  </Grid>
                  <Grid item xs={3} sm={1}>
                    <Typography variant="caption" fontWeight="bold" align="center">8W Ago</Typography>
                  </Grid>
                  <Grid item xs={3} sm={1.2}>
                    <Typography variant="caption" fontWeight="bold" align="center">Momentum</Typography>
                  </Grid>
                  <Grid item xs={3} sm={1.2}>
                    <Typography variant="caption" fontWeight="bold" align="center">Trend</Typography>
                  </Grid>
                  <Grid item xs={3} sm={1}>
                    <Typography variant="caption" fontWeight="bold" align="right">1D%</Typography>
                  </Grid>
                  <Grid item xs={3} sm={1}>
                    <Typography variant="caption" fontWeight="bold" align="right">5D%</Typography>
                  </Grid>
                  <Grid item xs={3} sm={1}>
                    <Typography variant="caption" fontWeight="bold" align="right">20D%</Typography>
                  </Grid>
                </Grid>
              </Box>
              {(rotationData?.data?.sectors || []).map((sector, index) => (
                <Accordion key={`${sector.sector_name}-${index}`} defaultExpanded={index === 0} sx={{ border: "1px solid", borderColor: "divider" }}>
                  <AccordionSummary
                    expandIcon={<ExpandMore />}
                    sx={{
                      backgroundColor: "grey.50",
                      "&:hover": { backgroundColor: "grey.100" },
                    }}
                  >
                    <Grid container spacing={2} alignItems="center" sx={{ width: "100%" }}>
                      <Grid item xs={12} sm={1.5}>
                        <Typography variant="body2" fontWeight="bold">
                          {sector.sector_name}
                        </Typography>
                      </Grid>
                      <Grid item xs={3} sm={1.2}>
                        <Chip
                          label={`#${sector.current_rank || "N/A"}`}
                          size="small"
                          color="primary"
                          variant="outlined"
                        />
                      </Grid>
                      <Grid item xs={3} sm={1}>
                        <Typography variant="caption" fontWeight="bold" align="center">
                          {sector.rank_1w_ago !== null && sector.rank_1w_ago !== undefined ? sector.rank_1w_ago : "—"}
                        </Typography>
                      </Grid>
                      <Grid item xs={3} sm={1}>
                        <Typography variant="caption" fontWeight="bold" align="center">
                          {sector.rank_4w_ago !== null && sector.rank_4w_ago !== undefined ? sector.rank_4w_ago : "—"}
                        </Typography>
                      </Grid>
                      <Grid item xs={3} sm={1}>
                        <Typography variant="caption" fontWeight="bold" align="center">
                          {sector.rank_12w_ago !== null && sector.rank_12w_ago !== undefined ? sector.rank_12w_ago : "—"}
                        </Typography>
                      </Grid>
                      <Grid item xs={3} sm={1.2}>
                        <Chip
                          label={sector.current_momentum || "N/A"}
                          size="small"
                          color={
                            sector.current_momentum === "Strong"
                              ? "success"
                              : sector.current_momentum === "Moderate"
                                ? "info"
                                : "default"
                          }
                        />
                      </Grid>
                      <Grid item xs={3} sm={1.2}>
                        <Box display="flex" alignItems="center" justifyContent="center" gap={0.25}>
                          {sector.current_trend === "Uptrend" && (
                            <TrendingUp color="success" fontSize="small" />
                          )}
                          {sector.current_trend === "Downtrend" && (
                            <TrendingDown color="error" fontSize="small" />
                          )}
                        </Box>
                      </Grid>
                      <Grid item xs={3} sm={1}>
                        <Typography
                          variant="caption"
                          sx={{
                            color: getChangeColor(sector.current_perf_1d),
                            fontWeight: 600,
                          }}
                          align="right"
                        >
                          {formatPercentage(sector.current_perf_1d)}
                        </Typography>
                      </Grid>
                      <Grid item xs={3} sm={1}>
                        <Typography
                          variant="caption"
                          sx={{
                            color: getChangeColor(sector.current_perf_5d),
                            fontWeight: 600,
                          }}
                          align="right"
                        >
                          {formatPercentage(sector.current_perf_5d)}
                        </Typography>
                      </Grid>
                      <Grid item xs={3} sm={1}>
                        <Typography
                          variant="caption"
                          sx={{
                            color: getChangeColor(sector.current_perf_20d),
                            fontWeight: 600,
                          }}
                          align="right"
                        >
                          {formatPercentage(sector.current_perf_20d)}
                        </Typography>
                      </Grid>
                    </Grid>
                  </AccordionSummary>
                  <AccordionDetails sx={{ backgroundColor: "grey.25", p: 2 }}>
                    <Typography variant="body2">
                      <strong>Historical Data:</strong> 1W Ago: {sector.rank_1w_ago !== null && sector.rank_1w_ago !== undefined ? sector.rank_1w_ago : "—"} | 4W Ago: {sector.rank_4w_ago !== null && sector.rank_4w_ago !== undefined ? sector.rank_4w_ago : "—"} | 8W Ago: {sector.rank_12w_ago !== null && sector.rank_12w_ago !== undefined ? sector.rank_12w_ago : "—"}
                    </Typography>
                  </AccordionDetails>
                </Accordion>
              ))}
            </Box>
          )}
        </CardContent>
      </Card>

      {/* Top Industry Rankings */}
      <Card sx={{ mb: 4 }}>
        <CardContent>
          <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
            Industry Rankings with Historical Data
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
            <>
              <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
                {/* Header Row */}
                <Box sx={{ display: "flex", mb: 1, px: 2 }}>
                  <Grid container spacing={2} alignItems="center" sx={{ width: "100%", fontWeight: "bold" }}>
                    <Grid item xs={2} sm={0.8}>
                      <Typography variant="caption" fontWeight="bold" align="center">Rank</Typography>
                    </Grid>
                    <Grid item xs={12} sm={2}>
                      <Typography variant="caption" fontWeight="bold">Industry</Typography>
                    </Grid>
                    <Grid item xs={2} sm={1}>
                      <Typography variant="caption" fontWeight="bold" align="center">1W Ago</Typography>
                    </Grid>
                    <Grid item xs={2} sm={1}>
                      <Typography variant="caption" fontWeight="bold" align="center">4W Ago</Typography>
                    </Grid>
                    <Grid item xs={2} sm={1}>
                      <Typography variant="caption" fontWeight="bold" align="center">8W Ago</Typography>
                    </Grid>
                    <Grid item xs={2} sm={1.2}>
                      <Typography variant="caption" fontWeight="bold" align="center">Momentum</Typography>
                    </Grid>
                    <Grid item xs={2} sm={1.2}>
                      <Typography variant="caption" fontWeight="bold" align="center">Trend</Typography>
                    </Grid>
                    <Grid item xs={2} sm={1}>
                      <Typography variant="caption" fontWeight="bold" align="right">1D%</Typography>
                    </Grid>
                    <Grid item xs={2} sm={1}>
                      <Typography variant="caption" fontWeight="bold" align="right">Count</Typography>
                    </Grid>
                  </Grid>
                </Box>
                {(industryData?.data?.industries || []).map((industry, index) => (
                  <Accordion key={`${industry.industry}-${index}`} defaultExpanded={index === 0} sx={{ border: "1px solid", borderColor: "divider" }}>
                    <AccordionSummary
                      expandIcon={<ExpandMore />}
                      sx={{
                        backgroundColor: "grey.50",
                        "&:hover": { backgroundColor: "grey.100" },
                      }}
                    >
                      <Grid container spacing={2} alignItems="center" sx={{ width: "100%" }}>
                        <Grid item xs={2} sm={0.8}>
                          <Chip
                            label={`#${industry.current_rank || "N/A"}`}
                            size="small"
                            color="primary"
                            variant="outlined"
                          />
                        </Grid>
                        <Grid item xs={12} sm={2}>
                          <Box>
                            <Typography variant="body2" fontWeight="bold">
                              {industry.industry}
                            </Typography>
                            <Typography variant="caption" color="text.secondary">
                              {industry.sector}
                            </Typography>
                          </Box>
                        </Grid>
                        <Grid item xs={2} sm={1}>
                          <Typography variant="caption" fontWeight="bold" align="center">
                            {industry.rank_1w_ago !== null && industry.rank_1w_ago !== undefined ? industry.rank_1w_ago : "—"}
                          </Typography>
                        </Grid>
                        <Grid item xs={2} sm={1}>
                          <Typography variant="caption" fontWeight="bold" align="center">
                            {industry.rank_4w_ago !== null && industry.rank_4w_ago !== undefined ? industry.rank_4w_ago : "—"}
                          </Typography>
                        </Grid>
                        <Grid item xs={2} sm={1}>
                          <Typography variant="caption" fontWeight="bold" align="center">
                            {industry.rank_12w_ago !== null && industry.rank_12w_ago !== undefined ? industry.rank_12w_ago : "—"}
                          </Typography>
                        </Grid>
                        <Grid item xs={2} sm={1.2}>
                          <Chip
                            label={industry.momentum || "N/A"}
                            size="small"
                            color={
                              industry.momentum === "Strong"
                                ? "success"
                                : industry.momentum === "Moderate"
                                  ? "info"
                                  : "default"
                            }
                          />
                        </Grid>
                        <Grid item xs={2} sm={1.2}>
                          <Box display="flex" alignItems="center" justifyContent="center" gap={0.25}>
                            {industry.trend === "Uptrend" && (
                              <TrendingUp color="success" fontSize="small" />
                            )}
                            {industry.trend === "Downtrend" && (
                              <TrendingDown color="error" fontSize="small" />
                            )}
                          </Box>
                        </Grid>
                        <Grid item xs={2} sm={1}>
                          <Typography
                            variant="caption"
                            sx={{
                              color: getChangeColor(industry.performance_1d),
                              fontWeight: 600,
                            }}
                            align="right"
                          >
                            {formatPercentage(industry.performance_1d)}
                          </Typography>
                        </Grid>
                        <Grid item xs={2} sm={1}>
                          <Typography variant="caption" fontWeight="bold" align="right">
                            {industry.stock_count || 0}
                          </Typography>
                        </Grid>
                      </Grid>
                    </AccordionSummary>
                    <AccordionDetails sx={{ backgroundColor: "grey.25", p: 2 }}>
                      <Typography variant="body2">
                        <strong>Historical Data:</strong> 1W Ago: {industry.rank_1w_ago !== null && industry.rank_1w_ago !== undefined ? industry.rank_1w_ago : "—"} | 4W Ago: {industry.rank_4w_ago !== null && industry.rank_4w_ago !== undefined ? industry.rank_4w_ago : "—"} | 8W Ago: {industry.rank_12w_ago !== null && industry.rank_12w_ago !== undefined ? industry.rank_12w_ago : "—"}
                      </Typography>
                    </AccordionDetails>
                  </Accordion>
                ))}
              </Box>
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
            </>
          )}
        </CardContent>
      </Card>

    </Container>
  );
};

export default SectorAnalysis;
