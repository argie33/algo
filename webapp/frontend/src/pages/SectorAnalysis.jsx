import { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Alert,
  Box,
  Button,
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
  Refresh,
  TrendingUp,
  TrendingDown,
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

  // Sector ETF mapping for real data
  const sectorETFs = {
    XLK: { name: "Technology", color: "#2196F3" },
    XLV: { name: "Healthcare", color: "#4CAF50" },
    XLF: { name: "Financials", color: "#FF9800" },
    XLY: { name: "Consumer Discretionary", color: "#9C27B0" },
    XLP: { name: "Consumer Staples", color: "#795548" },
    XLE: { name: "Energy", color: "#FF5722" },
    XLI: { name: "Industrials", color: "#607D8B" },
    XLB: { name: "Materials", color: "#8BC34A" },
    XLU: { name: "Utilities", color: "#FFC107" },
    XLRE: { name: "Real Estate", color: "#E91E63" },
  };

  // Fetch sector rotation data - NO AUTH REQUIRED
  const { data: rotationData, isLoading: rotationLoading, error: rotationError } = useQuery({
    queryKey: ["sector-rotation"],
    queryFn: async () => {
      const response = await getMarketResearchIndicators();
      return response;
    },
    staleTime: 60000,
    enabled: true, // No auth required
    retry: false,
  });

  useEffect(() => {
    loadSectorData();

  }, []);

  const loadSectorData = async () => {
    try {
      setError(null);
      setLoading(true);

      console.log("Loading sector analysis data (no auth required)");

      // Try multiple endpoints for sector data
      let sectorResponse = null;
      const endpoints = [
        "/api/market/sectors/performance",
        "/api/market/sectors",
        "/api/analytics/sectors",
      ];

      for (const endpoint of endpoints) {
        try {
          console.log(`Trying sector endpoint: ${endpoint}`);
          const resp = await api.get(endpoint);
          if (resp?.data && (resp.data.success || resp.data.data)) {
            sectorResponse = resp.data.data?.sectors || resp.data.sectors || resp.data;
            console.log(`✅ Success with endpoint: ${endpoint}`, sectorResponse);
            break;
          }
        } catch (err) {
          console.warn(`Failed endpoint ${endpoint}:`, err.message);
        }
      }

      // If API call succeeded, transform the data
      if (sectorResponse && Array.isArray(sectorResponse)) {
        const sectors = sectorResponse.map((s) => ({
          sector: s.sector || s.name,
          etfSymbol: s.symbol || s.etf_symbol || "N/A",
          price: s.price || s.last_price || 100,
          change: s.change || s.price_change || 0,
          changePercent: s.changePercent || s.change_percent || s.performance || 0,
          volume: s.volume || s.total_volume || 1000000,
          marketCap: s.marketCap || s.market_cap || 50000000000,
          color: sectorETFs[s.symbol]?.color || "#666",
          dataSource: "api",
        }));

        setSectorData(sectors);
        setLastUpdate(new Date());
        console.log("✅ Sector data loaded:", sectors.length);
        return;
      }

      throw new Error("No valid sector data from API");
    } catch (error) {
      console.error("Failed to load sector data:", error);
      setError(`Database error: ${error.message}`);
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
              label="Real-time ETF Data"
              color="success"
              size="small"
              variant="outlined"
            />
            <Chip
              label={`Updated ${formatTimeAgo(lastUpdate)}`}
              color="info"
              size="small"
              variant="outlined"
            />
          </Box>
        </Box>

        <Button
          variant="outlined"
          startIcon={<Refresh />}
          onClick={loadSectorData}
          disabled={loading}
        >
          Refresh Data
        </Button>
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

      {/* Sector Rotation Analysis */}
      <Card sx={{ mb: 4 }}>
        <CardContent>
          <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
            Sector Rotation Analysis
          </Typography>
          {rotationLoading ? (
            <Box display="flex" justifyContent="center" py={4}>
              <LinearProgress sx={{ width: "50%" }} />
            </Box>
          ) : rotationError ? (
            <Alert severity="error">
              Failed to load sector rotation data: {rotationError.message}
            </Alert>
          ) : !rotationData?.data?.sectorRotation?.length ? (
            <Alert severity="warning">
              No sector rotation data available in database
            </Alert>
          ) : (
            <TableContainer>
              <Table>
                <TableHead>
                  <TableRow sx={{ backgroundColor: "grey.50" }}>
                    <TableCell sx={{ fontWeight: 600 }}>Sector</TableCell>
                    <TableCell sx={{ fontWeight: 600 }}>Momentum</TableCell>
                    <TableCell sx={{ fontWeight: 600 }}>Money Flow</TableCell>
                    <TableCell align="right" sx={{ fontWeight: 600 }}>
                      Performance
                    </TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {(rotationData?.data?.sectorRotation || []).map(
                    (sector, index) => (
                      <TableRow key={index} hover>
                        <TableCell>{sector.sector}</TableCell>
                        <TableCell>
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
                        </TableCell>
                        <TableCell>
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
                        </TableCell>
                        <TableCell
                          align="right"
                          sx={{
                            color: getChangeColor(sector.performance),
                            fontWeight: 600,
                          }}
                        >
                          {formatPercentage(sector.performance)}
                        </TableCell>
                      </TableRow>
                    )
                  )}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </CardContent>
      </Card>

      {/* Detailed Sector Table */}
      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Detailed Sector Breakdown
          </Typography>
          <TableContainer>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>
                    <strong>Sector</strong>
                  </TableCell>
                  <TableCell>
                    <strong>ETF</strong>
                  </TableCell>
                  <TableCell align="right">
                    <strong>Price</strong>
                  </TableCell>
                  <TableCell align="right">
                    <strong>Change</strong>
                  </TableCell>
                  <TableCell align="right">
                    <strong>Change %</strong>
                  </TableCell>
                  <TableCell align="right">
                    <strong>Volume</strong>
                  </TableCell>
                  <TableCell align="right">
                    <strong>Market Cap</strong>
                  </TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {(sectorData || []).map((sector) => {
                  const hasError = sector.error;
                  const isPositive = sector.changePercent >= 0;

                  return (
                    <TableRow key={sector.etfSymbol} hover>
                      <TableCell>
                        <Box display="flex" alignItems="center" gap={2}>
                          <Box
                            width={16}
                            height={16}
                            borderRadius="50%"
                            bgcolor={sector.color}
                          />
                          <Typography variant="body1" fontWeight="bold">
                            {sector.sector}
                          </Typography>
                        </Box>
                      </TableCell>

                      <TableCell>
                        <Typography variant="body2" fontWeight="bold">
                          {sector.etfSymbol}
                        </Typography>
                      </TableCell>

                      <TableCell align="right">
                        {hasError ? (
                          <Typography color="error">--</Typography>
                        ) : (
                          <Typography fontWeight="bold">
                            {formatCurrency(sector.price)}
                          </Typography>
                        )}
                      </TableCell>

                      <TableCell align="right">
                        {hasError ? (
                          <Typography color="error">--</Typography>
                        ) : (
                          <Box
                            display="flex"
                            alignItems="center"
                            justifyContent="flex-end"
                            gap={1}
                          >
                            {isPositive ? (
                              <TrendingUp color="success" fontSize="small" />
                            ) : (
                              <TrendingDown color="error" fontSize="small" />
                            )}
                            <Typography
                              color={isPositive ? "success.main" : "error.main"}
                              fontWeight="bold"
                            >
                              {formatCurrency(Math.abs(sector.change))}
                            </Typography>
                          </Box>
                        )}
                      </TableCell>

                      <TableCell align="right">
                        {hasError ? (
                          <Typography color="error">--</Typography>
                        ) : (
                          <Typography
                            color={isPositive ? "success.main" : "error.main"}
                            fontWeight="bold"
                          >
                            {formatPercentage(Math.abs(sector.changePercent))}
                          </Typography>
                        )}
                      </TableCell>

                      <TableCell align="right">
                        {hasError ? (
                          <Typography color="error">--</Typography>
                        ) : (
                          <Typography variant="body2">
                            {formatNumber(sector.volume)}
                          </Typography>
                        )}
                      </TableCell>

                      <TableCell align="right">
                        {hasError ? (
                          <Typography color="error">--</Typography>
                        ) : (
                          <Typography variant="body2">
                            ${formatNumber(sector.marketCap / 1e12, 1)}T
                          </Typography>
                        )}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </TableContainer>
        </CardContent>
      </Card>
    </Container>
  );
};

export default SectorAnalysis;
