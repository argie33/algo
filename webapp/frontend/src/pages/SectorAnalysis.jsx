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
  Grid,
  LinearProgress,
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
  const [lastUpdate, setLastUpdate] = useState(null);

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

  // Normalize industry sector names to match sector API sector_names
  // Industries API uses different names than Sectors API
  const normalizeSectorName = (industriesSectorName) => {
    const sectorMapping = {
      "Basic Materials": "Materials",
      "Consumer Cyclical": "Consumer Discretionary",
      "Consumer Defensive": "Consumer Staples",
      "Financial Services": "Financials",
    };
    return sectorMapping[industriesSectorName] || industriesSectorName;
  };

  // Fetch sector performance data (consolidated /api/sectors endpoint)
  const { data: rotationData, isLoading: rotationLoading, error: rotationError } = useQuery({
    queryKey: ["sector-performance"],
    queryFn: async () => {
      const response = await api.get("/api/sectors/sectors-with-history?limit=20");
      return response.data;
    },
    staleTime: 60000,
    enabled: true,
    retry: false,
  });

  // Fetch industry performance data (consolidated /api/sectors endpoint)
  const { data: industryData, isLoading: industryLoading, error: industryError } = useQuery({
    queryKey: ["industry-performance"],
    queryFn: async () => {
      const response = await api.get("/api/sectors/industries-with-history?limit=50");
      return response.data;
    },
    staleTime: 60000,
    enabled: true,
    retry: false,
  });

  // Update lastUpdate timestamp when sectors data loads (industries optional)
  useEffect(() => {
    // Update when sectors are loaded (industries are optional for display)
    if (rotationData?.data?.sectors?.length > 0) {
      setLastUpdate(new Date());
    }
  }, [rotationData]);

  // Render sectors if sectors data is available (industries are optional for filtering)
  const shouldRenderSectors = rotationData?.data?.sectors && rotationData?.data?.sectors.length > 0;

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
    .filter((s) => s.sector && s.performance_1d != null && !isNaN(s.performance_1d))
    .map((s) => ({
      name: s.sector.length > 15 ? s.sector.substring(0, 15) + "..." : s.sector,
      fullName: s.sector,
      performance: parseFloat(s.performance_1d.toFixed(2)),
      color: sectorColors[s.sector] || "#666",
    }))
    .sort((a, b) => b.performance - a.performance);

  const pieData = (rotationData?.data?.sectors || [])
    .filter((s) => s.sector && s.overall_rank != null && !isNaN(s.overall_rank))
    .map((s) => ({
      name: s.sector,
      value: Math.abs(s.overall_rank), // Use rank as proxy for significance
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
              label={`Updated ${lastUpdate ? formatTimeAgo(lastUpdate) : "..."}`}
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
          ) : !shouldRenderSectors ? (
            <Box display="flex" justifyContent="center" py={4}>
              <LinearProgress sx={{ width: "50%" }} />
            </Box>
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
              {(rotationData?.data?.sectors || []).map((sector, index) => {
                // Find matching industries for this sector
                // Normalize industry sector names to match sector API sector names
                const sectorIndustries = (industryData?.data?.industries || []).filter(
                  (ind) => normalizeSectorName(ind.sector) === sector.sector
                );

                return (
                  <Accordion key={`${sector.sector}-${index}`} defaultExpanded={index === 0} sx={{ border: "1px solid", borderColor: "divider" }}>
                    <AccordionSummary
                      expandIcon={<ExpandMore />}
                      sx={{
                        backgroundColor: "grey.50",
                        "&:hover": { backgroundColor: "grey.100" },
                        overflow: "visible",
                        minHeight: "60px",
                      }}
                    >
                      <Grid container spacing={1} alignItems="center" sx={{ width: "100%", overflow: "visible" }}>
                        <Grid item xs={12} sm={1.5}>
                          <Typography variant="body2" fontWeight="bold">
                            {sector.sector}
                          </Typography>
                        </Grid>
                        <Grid item xs={3} sm={1.2}>
                          <Chip
                            label={`#${sector.overall_rank || "N/A"}`}
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
                            {sector.rank_8w_ago !== null && sector.rank_8w_ago !== undefined ? sector.rank_8w_ago : "—"}
                          </Typography>
                        </Grid>
                        <Grid item xs={3} sm={1.2}>
                          <Chip
                            label={sector.momentum || "N/A"}
                            size="small"
                            color={
                              sector.momentum === "Strong"
                                ? "success"
                                : sector.momentum === "Moderate"
                                  ? "info"
                                  : "default"
                            }
                          />
                        </Grid>
                        <Grid item xs={3} sm={1.2}>
                          <Box display="flex" alignItems="center" justifyContent="center" gap={0.25}>
                            {sector.momentum === "Uptrend" && (
                              <TrendingUp color="success" fontSize="small" />
                            )}
                            {sector.momentum === "Downtrend" && (
                              <TrendingDown color="error" fontSize="small" />
                            )}
                          </Box>
                        </Grid>
                        <Grid item xs={3} sm={1}>
                          <Typography
                            variant="caption"
                            sx={{
                              color: getChangeColor(sector.performance_1d),
                              fontWeight: 600,
                            }}
                            align="right"
                          >
                            {formatPercentage(sector.performance_1d)}
                          </Typography>
                        </Grid>
                        <Grid item xs={3} sm={1}>
                          <Typography
                            variant="caption"
                            sx={{
                              color: getChangeColor(sector.performance_5d),
                              fontWeight: 600,
                            }}
                            align="right"
                          >
                            {formatPercentage(sector.performance_5d)}
                          </Typography>
                        </Grid>
                        <Grid item xs={3} sm={1}>
                          <Typography
                            variant="caption"
                            sx={{
                              color: getChangeColor(sector.performance_20d),
                              fontWeight: 600,
                            }}
                            align="right"
                          >
                            {formatPercentage(sector.performance_20d)}
                          </Typography>
                        </Grid>
                      </Grid>
                    </AccordionSummary>
                    <AccordionDetails sx={{ backgroundColor: "grey.25", p: 2 }}>
                      <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
                        {/* Metrics Section */}
                        <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 2 }}>
                          <Box>
                            <Typography variant="caption" color="text.secondary" fontWeight="bold">📊 Current Ranking</Typography>
                            <Typography variant="body2">
                              • Overall Rank: #{sector.overall_rank || "N/A"}
                            </Typography>
                            <Typography variant="body2">
                              • Momentum: {sector.momentum || "N/A"}
                            </Typography>
                            <Typography variant="body2">
                              • RSI: {sector.rsi ? sector.rsi.toFixed(2) : "N/A"}
                            </Typography>
                          </Box>
                          <Box>
                            <Typography variant="caption" color="text.secondary" fontWeight="bold">📈 Performance Metrics</Typography>
                            <Typography variant="body2">
                              • 1-Day: {formatPercentage(sector.performance_1d)}
                            </Typography>
                            <Typography variant="body2">
                              • 5-Day: {formatPercentage(sector.performance_5d)}
                            </Typography>
                            <Typography variant="body2">
                              • 20-Day: {formatPercentage(sector.performance_20d)}
                            </Typography>
                          </Box>
                          <Box>
                            <Typography variant="caption" color="text.secondary" fontWeight="bold">💼 Trading Data</Typography>
                            <Typography variant="body2">
                              • Price: ${sector.price?.toFixed(2) || "N/A"}
                            </Typography>
                            <Typography variant="body2">
                              • Change: {formatPercentage(sector.change_percent)} ({sector.change >= 0 ? '+' : ''}{sector.change?.toFixed(2)})
                            </Typography>
                            <Typography variant="body2">
                              • Volume: {(sector.volume / 1000000).toFixed(2)}M
                            </Typography>
                          </Box>
                        </Box>

                        {/* Industries Section */}
                        <Box sx={{ borderTop: "1px solid", borderColor: "divider", pt: 2 }}>
                          <Typography variant="subtitle2" fontWeight="bold" sx={{ mb: 1 }}>
                            📁 Industries ({sectorIndustries.length})
                          </Typography>
                          {sectorIndustries.length > 0 ? (
                            <Box sx={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 1 }}>
                              {sectorIndustries.slice(0, 10).map((industry, idx) => (
                                <Box
                                  key={idx}
                                  sx={{
                                    p: 1,
                                    backgroundColor: "background.paper",
                                    border: "1px solid",
                                    borderColor: "divider",
                                    borderRadius: 1,
                                  }}
                                >
                                  <Typography variant="caption" fontWeight="600" display="block">
                                    #{industry.current_rank || "N/A"}: {industry.industry}
                                  </Typography>
                                  <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.25 }}>
                                    {formatPercentage(industry.performance_1d)} (1D) | {industry.stock_count} stocks
                                  </Typography>
                                </Box>
                              ))}
                            </Box>
                          ) : (
                            <Typography variant="caption" color="text.secondary">
                              No industries available
                            </Typography>
                          )}
                          {sectorIndustries.length > 10 && (
                            <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: "block" }}>
                              ... and {sectorIndustries.length - 10} more industries
                            </Typography>
                          )}
                        </Box>
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
            Industry Rankings
          </Typography>
          {industryLoading ? (
            <Box display="flex" justifyContent="center" py={4}>
              <LinearProgress sx={{ width: "50%" }} />
            </Box>
          ) : industryError || !industryData?.data?.industries?.length ? (
            <Alert severity="info" sx={{ mb: 2 }}>
              Industry performance data is currently loading or unavailable.
              {industryError && " The data will appear once the industry loader completes."}
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
                        overflow: "visible",
                        minHeight: "60px",
                      }}
                    >
                      <Grid container spacing={1} alignItems="center" sx={{ width: "100%", overflow: "visible" }}>
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
                            {industry.rank_8w_ago !== null && industry.rank_8w_ago !== undefined ? industry.rank_8w_ago : "—"}
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
                      <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
                        <Box sx={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 2 }}>
                          <Box>
                            <Typography variant="caption" color="text.secondary" fontWeight="bold">📊 Ranking History</Typography>
                            <Typography variant="body2">
                              • 1W Ago: {industry.rank_1w_ago !== null ? `#${industry.rank_1w_ago}` : "—"}
                            </Typography>
                            <Typography variant="body2">
                              • 4W Ago: {industry.rank_4w_ago !== null ? `#${industry.rank_4w_ago}` : "—"}
                            </Typography>
                            <Typography variant="body2">
                              • 8W Ago: {industry.rank_8w_ago !== null ? `#${industry.rank_8w_ago}` : "—"}
                            </Typography>
                            <Typography variant="body2" sx={{ mt: 0.5, fontWeight: "600", color: "text.primary" }}>
                              Change: {industry.rank_change_1w !== null ? `${industry.rank_change_1w > 0 ? '+' : ''}${industry.rank_change_1w}` : "—"}
                            </Typography>
                          </Box>
                          <Box>
                            <Typography variant="caption" color="text.secondary" fontWeight="bold">📈 Performance</Typography>
                            <Typography variant="body2">
                              • 1-Day: {formatPercentage(industry.performance_1d)}
                            </Typography>
                            <Typography variant="body2">
                              • 5-Day: {formatPercentage(industry.performance_5d)}
                            </Typography>
                            <Typography variant="body2">
                              • 20-Day: {formatPercentage(industry.performance_20d)}
                            </Typography>
                          </Box>
                          <Box>
                            <Typography variant="caption" color="text.secondary" fontWeight="bold">💼 Industry Info</Typography>
                            <Typography variant="body2">
                              • Sector: <strong>{industry.sector}</strong>
                            </Typography>
                            <Typography variant="body2">
                              • Stocks: <strong>{industry.stock_count || 0}</strong>
                            </Typography>
                            <Typography variant="body2">
                              • Rank: <strong>{industry.current_rank || "N/A"}</strong>
                            </Typography>
                          </Box>
                        </Box>
                      </Box>
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
