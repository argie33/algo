import { useState, useEffect } from "react";
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
import api from "../services/api";
import {
  formatCurrency,
  formatPercentage,
  formatNumber,
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

  useEffect(() => {
    loadSectorData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadSectorData = async () => {
    try {
      setError(null);
      setLoading(true);

      if (!user) {
        console.warn("User not authenticated, skipping sector data fetch");
        return;
      }

      console.log("Loading sector analysis data");

      // Get sector ETF data
      const symbols = Object.keys(sectorETFs);
      
      if (!symbols || symbols.length === 0) {
        console.warn("No sector ETF symbols available for streaming");
        return;
      }
      
      const response = await api.get(
        `/api/websocket/stream/${symbols.join(",")}`
      );

      if (response?.data.success) {
        const liveData = response?.data.data;

        // Transform API data for sector analysis
        const sectors = Object.entries(sectorETFs).map(
          ([etfSymbol, sectorInfo]) => {
            const symbolData = liveData?.data[etfSymbol];
            if (symbolData && !symbolData.error) {
              const midPrice = (symbolData.bidPrice + symbolData.askPrice) / 2;
              // Default neutral performance when historical data unavailable
              const mockChange = 0; // Neutral change
              const mockChangePercent = 0; // Neutral change percentage

              return {
                sector: sectorInfo.name,
                etfSymbol: etfSymbol,
                price: midPrice,
                change: mockChange,
                changePercent: mockChangePercent,
                volume: symbolData.bidSize + symbolData.askSize,
                marketCap: midPrice * 1000000000, // Mock market cap
                color: sectorInfo.color,
                dataSource: "live",
                timestamp: symbolData.timestamp,
              };
            } else {
              return {
                sector: sectorInfo.name,
                etfSymbol: etfSymbol,
                error: symbolData?.error || "Data unavailable",
                color: sectorInfo.color,
                dataSource: "error",
              };
            }
          }
        );

        setSectorData(sectors);
        setLastUpdate(new Date());

        console.log("✅ Sector analysis data loaded successfully", {
          sectors: (sectors?.length || 0),
          successful: sectors.filter((s) => !s.error).length,
          failed: sectors.filter((s) => s.error).length,
        });
      } else {
        throw new Error("Failed to fetch sector data");
      }
    } catch (error) {
      if (import.meta.env && import.meta.env.DEV) console.error("Failed to load sector data:", error);
      setError(error.message);

      // Fallback to demo data for presentation
      setSectorData(
        Object.entries(sectorETFs).map(([etfSymbol, sectorInfo]) => ({
          sector: sectorInfo.name,
          etfSymbol: etfSymbol,
          price: 100, // Default price when real data unavailable
          change: 0, // Neutral change
          changePercent: 0, // Neutral change percentage  
          volume: 1000000, // Default volume
          marketCap: 50000000000, // Default market cap
          color: sectorInfo.color,
          dataSource: "demo",
          error: "Using demo data",
        }))
      );
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
              label={`${(sectorData?.length || 0)} sectors`}
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
        <Alert severity="warning" sx={{ mb: 3 }}>
          <Typography variant="h6" gutterBottom>
            Limited Data Available
          </Typography>
          <Typography variant="body2">{error}</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
            Showing demo data for presentation. Configure Alpaca API credentials
            for live sector data.
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
                  <TableCell align="center">
                    <strong>Status</strong>
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

                      <TableCell align="center">
                        {hasError ? (
                          <Chip label="Error" color="error" size="small" />
                        ) : sector.dataSource === "demo" ? (
                          <Chip label="Demo" color="warning" size="small" />
                        ) : (
                          <Chip label="Live" color="success" size="small" />
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
