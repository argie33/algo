import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Box,
  Card,
  CardContent,
  CardHeader,
  Chip,
  Container,
  Grid,
  Typography,
  CircularProgress,
  Alert,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  LinearProgress,
  Paper,
  Divider,
} from "@mui/material";
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ScatterChart,
  Scatter,
} from "recharts";
import { TrendingUp, TrendingDown, Info } from "@mui/icons-material";
import api from "../services/api";
import { getChangeColor } from "../utils/formatters";

export default function CommoditiesAnalysis() {
  const [selectedCommodity, setSelectedCommodity] = useState("GC=F");

  // Fetch categories
  const categoriesQuery = useQuery({
    queryKey: ["commodities-categories"],
    queryFn: async () => {
      const response = await api.get("/api/commodities/categories");
      return response.data.data;
    },
    staleTime: 5 * 60 * 1000,
  });

  // Fetch prices
  const pricesQuery = useQuery({
    queryKey: ["commodities-prices"],
    queryFn: async () => {
      const response = await api.get("/api/commodities/prices?limit=100");
      return response.data.data;
    },
    staleTime: 5 * 60 * 1000,
  });

  // Fetch market summary
  const summaryQuery = useQuery({
    queryKey: ["commodities-summary"],
    queryFn: async () => {
      const response = await api.get("/api/commodities/market-summary");
      return response.data.data;
    },
    staleTime: 5 * 60 * 1000,
  });

  // Fetch correlations
  const correlationsQuery = useQuery({
    queryKey: ["commodities-correlations"],
    queryFn: async () => {
      const response = await api.get(
        "/api/commodities/correlations?minCorrelation=0.5"
      );
      return response.data.data.correlations;
    },
    staleTime: 30 * 60 * 1000,
  });

  // Fetch COT data
  const cotQuery = useQuery({
    queryKey: ["commodities-cot", selectedCommodity],
    queryFn: async () => {
      try {
        const response = await api.get(`/api/commodities/cot/${selectedCommodity}`);
        return response.data.data;
      } catch {
        return null;
      }
    },
    staleTime: 24 * 60 * 60 * 1000,
  });

  // Fetch seasonality
  const seasonalityQuery = useQuery({
    queryKey: ["commodities-seasonality", selectedCommodity],
    queryFn: async () => {
      try {
        const response = await api.get(`/api/commodities/seasonality/${selectedCommodity}`);
        return response.data.data;
      } catch {
        return null;
      }
    },
    staleTime: 7 * 24 * 60 * 60 * 1000,
  });

  const isLoading =
    categoriesQuery.isLoading ||
    pricesQuery.isLoading ||
    summaryQuery.isLoading ||
    correlationsQuery.isLoading;

  const COLORS = ["#8884d8", "#82ca9d", "#ffc658", "#ff7c7c", "#8dd1e1", "#d084d0"];

  // Chart data
  const categoriesChartData = categoriesQuery.data?.map((cat) => ({
    name: cat.name,
    change: parseFloat(cat.avgChange1d),
    count: cat.commodityCount,
  })) || [];

  const topMoversData = summaryQuery.data
    ? [
        ...(summaryQuery.data.topGainers || []).slice(0, 5),
        ...(summaryQuery.data.topLosers || []).slice(0, 5),
      ].map((item) => ({
        name: item.name,
        change: parseFloat(item.change),
        type: parseFloat(item.change) >= 0 ? "gainer" : "loser",
      }))
    : [];

  const correlationChartData = correlationsQuery.data
    ?.slice(0, 10)
    .map((item) => ({
      name: `${item.symbol1}/${item.symbol2}`,
      coefficient: parseFloat(item.coefficient),
    })) || [];

  const seasonalityData = seasonalityQuery.data?.seasonality || [];

  const cotHistoryData = cotQuery.data?.cotHistory?.slice(-12) || [];

  const cotSymbols = ["GC=F", "SI=F", "CL=F", "NG=F", "HG=F", "ZC=F", "ZS=F"];

  return (
    <Container maxWidth="xl" sx={{ py: 3 }}>
      {/* Header */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h4" component="h1" sx={{ fontWeight: 700, mb: 1 }}>
          🌾 Commodities Market Analysis
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Real-time market data, correlations, seasonality patterns, and trader positioning
        </Typography>
      </Box>

      {isLoading && (
        <Box sx={{ display: "flex", justifyContent: "center", py: 8 }}>
          <CircularProgress />
        </Box>
      )}

      {!isLoading && (
        <>
          {/* Market Summary Cards */}
          {summaryQuery.data && (
            <Grid container spacing={2} sx={{ mb: 4 }}>
              <Grid item xs={12} sm={6} md={3}>
                <Paper elevation={2}>
                  <CardContent>
                    <Typography color="textSecondary" gutterBottom>
                      Active Contracts
                    </Typography>
                    <Typography variant="h5">
                      {summaryQuery.data.overview?.activeContracts || 0}
                    </Typography>
                  </CardContent>
                </Paper>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <Paper elevation={2}>
                  <CardContent>
                    <Typography color="textSecondary" gutterBottom>
                      Total Volume
                    </Typography>
                    <Typography variant="h5">
                      {(summaryQuery.data.overview?.totalVolume / 1e6).toFixed(1)}M
                    </Typography>
                  </CardContent>
                </Paper>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <Paper elevation={2}>
                  <CardContent>
                    <Typography color="textSecondary" gutterBottom>
                      Top Gainer
                    </Typography>
                    {summaryQuery.data.topGainers?.[0] && (
                      <>
                        <Typography variant="body2" sx={{ fontWeight: 600, mb: 1 }}>
                          {summaryQuery.data.topGainers[0].name}
                        </Typography>
                        <Chip
                          icon={<TrendingUp />}
                          label={`+${summaryQuery.data.topGainers[0].change}%`}
                          color="success"
                          size="small"
                        />
                      </>
                    )}
                  </CardContent>
                </Paper>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <Paper elevation={2}>
                  <CardContent>
                    <Typography color="textSecondary" gutterBottom>
                      Top Loser
                    </Typography>
                    {summaryQuery.data.topLosers?.[0] && (
                      <>
                        <Typography variant="body2" sx={{ fontWeight: 600, mb: 1 }}>
                          {summaryQuery.data.topLosers[0].name}
                        </Typography>
                        <Chip
                          icon={<TrendingDown />}
                          label={`${summaryQuery.data.topLosers[0].change}%`}
                          color="error"
                          size="small"
                        />
                      </>
                    )}
                  </CardContent>
                </Paper>
              </Grid>
            </Grid>
          )}

          {/* Charts Section */}
          <Grid container spacing={3} sx={{ mb: 4 }}>
            {/* Category Performance Chart */}
            <Grid item xs={12} md={6}>
              <Card elevation={2}>
                <CardHeader title="📊 Category Performance (1D Change)" />
                <CardContent>
                  <ResponsiveContainer width="100%" height={300}>
                    <BarChart data={categoriesChartData}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="name" angle={-45} textAnchor="end" height={80} />
                      <YAxis />
                      <Tooltip
                        formatter={(value) => `${value.toFixed(2)}%`}
                        contentStyle={{ backgroundColor: "#f5f5f5" }}
                      />
                      <Bar
                        dataKey="change"
                        radius={[8, 8, 0, 0]}
                        fill="#8884d8"
                      />
                    </BarChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
            </Grid>

            {/* Top Movers Chart */}
            <Grid item xs={12} md={6}>
              <Card elevation={2}>
                <CardHeader title="🚀 Top Movers (Gainers & Losers)" />
                <CardContent>
                  <ResponsiveContainer width="100%" height={300}>
                    <BarChart data={topMoversData}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="name" angle={-45} textAnchor="end" height={80} />
                      <YAxis />
                      <Tooltip formatter={(value) => `${value.toFixed(2)}%`} />
                      <Bar dataKey="change" fill="#82ca9d" radius={[8, 8, 0, 0]}>
                        {topMoversData.map((entry, index) => (
                          <Cell
                            key={`cell-${index}`}
                            fill={entry.type === "gainer" ? "#82ca9d" : "#ff7c7c"}
                          />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
            </Grid>

            {/* Commodity Distribution */}
            <Grid item xs={12} md={6}>
              <Card elevation={2}>
                <CardHeader title="📈 Commodity Distribution by Category" />
                <CardContent>
                  <ResponsiveContainer width="100%" height={300}>
                    <PieChart>
                      <Pie
                        data={categoriesChartData}
                        dataKey="count"
                        nameKey="name"
                        cx="50%"
                        cy="50%"
                        outerRadius={80}
                        label
                      >
                        {categoriesChartData.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                        ))}
                      </Pie>
                      <Tooltip />
                      <Legend />
                    </PieChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
            </Grid>

            {/* Correlations Scatter */}
            <Grid item xs={12} md={6}>
              <Card elevation={2}>
                <CardHeader title="🔗 Price Correlations" />
                <CardContent>
                  <ResponsiveContainer width="100%" height={300}>
                    <BarChart data={correlationChartData}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="name" angle={-45} textAnchor="end" height={80} />
                      <YAxis />
                      <Tooltip formatter={(value) => value.toFixed(2)} />
                      <Bar dataKey="coefficient" fill="#ffc658" radius={[8, 8, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
            </Grid>
          </Grid>

          {/* Seasonality Section */}
          <Card elevation={2} sx={{ mb: 3 }}>
            <CardHeader
              title="📅 Seasonal Patterns"
              subheader="Select commodity to view best trading months"
            />
            <CardContent>
              <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap", mb: 3 }}>
                {cotSymbols.map((symbol) => (
                  <Chip
                    key={symbol}
                    label={symbol}
                    onClick={() => setSelectedCommodity(symbol)}
                    color={selectedCommodity === symbol ? "primary" : "default"}
                    variant={selectedCommodity === symbol ? "filled" : "outlined"}
                  />
                ))}
              </Box>

              {seasonalityQuery.isLoading && <CircularProgress />}
              {seasonalityData.length > 0 ? (
                <>
                  <ResponsiveContainer width="100%" height={300}>
                    <LineChart data={seasonalityData}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="monthName" angle={-45} textAnchor="end" height={80} />
                      <YAxis yAxisId="left" label={{ value: "Win Rate %", angle: -90, position: "insideLeft" }} />
                      <YAxis yAxisId="right" orientation="right" label={{ value: "Avg Return %", angle: 90, position: "insideRight" }} />
                      <Tooltip />
                      <Legend />
                      <Line yAxisId="left" type="monotone" dataKey="winRate" stroke="#8884d8" name="Win Rate %" />
                      <Line yAxisId="right" type="monotone" dataKey="avgReturn" stroke="#82ca9d" name="Avg Return %" />
                    </LineChart>
                  </ResponsiveContainer>

                  <Table size="small" sx={{ mt: 3 }}>
                    <TableHead>
                      <TableRow sx={{ backgroundColor: "#f5f5f5" }}>
                        <TableCell sx={{ fontWeight: 600 }}>Month</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 600 }}>Avg Return</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 600 }}>Win Rate</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 600 }}>Volatility</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {seasonalityData.map((item) => (
                        <TableRow key={item.month}>
                          <TableCell>{item.monthName}</TableCell>
                          <TableCell align="right" sx={{ color: getChangeColor(item.avgReturn) }}>
                            {item.avgReturn}%
                          </TableCell>
                          <TableCell align="right">
                            <Box sx={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 1 }}>
                              {item.winRate}%
                              <LinearProgress variant="determinate" value={Math.min(parseFloat(item.winRate), 100)} sx={{ width: 60, height: 4 }} />
                            </Box>
                          </TableCell>
                          <TableCell align="right">{item.volatility}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </>
              ) : (
                <Alert severity="info">No seasonality data available</Alert>
              )}
            </CardContent>
          </Card>

          {/* COT Analysis Section */}
          <Card elevation={2} sx={{ mb: 3 }}>
            <CardHeader
              title="👥 Trader Positioning (Commitment of Traders)"
              subheader="Commercial hedgers vs. Speculators positioning analysis"
            />
            <CardContent>
              {cotQuery.isLoading && <CircularProgress />}
              {cotQuery.data ? (
                <>
                  {/* COT Summary Cards */}
                  <Grid container spacing={2} sx={{ mb: 3 }}>
                    <Grid item xs={12} sm={6} md={3}>
                      <Paper elevation={1}>
                        <CardContent sx={{ textAlign: "center" }}>
                          <Typography color="textSecondary" gutterBottom>Commercial Sentiment</Typography>
                          <Chip
                            label={cotQuery.data.analysis?.commercialSentiment}
                            color={
                              cotQuery.data.analysis?.commercialSentiment === "bullish"
                                ? "success"
                                : cotQuery.data.analysis?.commercialSentiment === "bearish"
                                ? "error"
                                : "default"
                            }
                            sx={{ mt: 1 }}
                          />
                        </CardContent>
                      </Paper>
                    </Grid>
                    <Grid item xs={12} sm={6} md={3}>
                      <Paper elevation={1}>
                        <CardContent sx={{ textAlign: "center" }}>
                          <Typography color="textSecondary" gutterBottom>Speculator Sentiment</Typography>
                          <Chip
                            label={cotQuery.data.analysis?.speculatorSentiment}
                            color={
                              cotQuery.data.analysis?.speculatorSentiment === "bullish"
                                ? "success"
                                : cotQuery.data.analysis?.speculatorSentiment === "bearish"
                                ? "error"
                                : "default"
                            }
                            sx={{ mt: 1 }}
                          />
                        </CardContent>
                      </Paper>
                    </Grid>
                    <Grid item xs={12} sm={6} md={3}>
                      <Paper elevation={1}>
                        <CardContent sx={{ textAlign: "center" }}>
                          <Typography color="textSecondary" gutterBottom>Divergence Signal</Typography>
                          <Chip
                            label={cotQuery.data.analysis?.divergence}
                            color={cotQuery.data.analysis?.divergence === "divergent" ? "error" : "success"}
                            sx={{ mt: 1 }}
                          />
                        </CardContent>
                      </Paper>
                    </Grid>
                    <Grid item xs={12} sm={6} md={3}>
                      <Paper elevation={1}>
                        <CardContent sx={{ textAlign: "center" }}>
                          <Typography color="textSecondary" gutterBottom>Latest Report</Typography>
                          <Typography variant="body2" sx={{ mt: 1, fontWeight: 600 }}>{cotQuery.data.latestReportDate}</Typography>
                        </CardContent>
                      </Paper>
                    </Grid>
                  </Grid>

                  {/* COT History Chart */}
                  {cotHistoryData.length > 0 && (
                    <Box sx={{ mt: 3 }}>
                      <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
                        Positioning History (Last 12 Weeks)
                      </Typography>
                      <ResponsiveContainer width="100%" height={300}>
                        <LineChart data={cotHistoryData}>
                          <CartesianGrid strokeDasharray="3 3" />
                          <XAxis dataKey="reportDate" angle={-45} textAnchor="end" height={80} />
                          <YAxis />
                          <Tooltip />
                          <Legend />
                          <Line
                            type="monotone"
                            dataKey="commercial.net"
                            stroke="#8884d8"
                            name="Commercial Net"
                          />
                          <Line
                            type="monotone"
                            dataKey="nonCommercial.net"
                            stroke="#82ca9d"
                            name="Speculator Net"
                          />
                        </LineChart>
                      </ResponsiveContainer>
                    </Box>
                  )}
                </>
              ) : (
                <Alert severity="warning">No COT data available for {selectedCommodity}</Alert>
              )}
            </CardContent>
          </Card>

          {/* All Prices Table */}
          <Card elevation={2}>
            <CardHeader title="💰 All Commodity Prices" />
            <CardContent>
              {pricesQuery.data && pricesQuery.data.length > 0 ? (
                <TableContainer sx={{ maxHeight: 600 }}>
                  <Table stickyHeader size="small">
                    <TableHead>
                      <TableRow sx={{ backgroundColor: "#f5f5f5" }}>
                        <TableCell sx={{ fontWeight: 600 }}>Symbol</TableCell>
                        <TableCell sx={{ fontWeight: 600 }}>Name</TableCell>
                        <TableCell sx={{ fontWeight: 600 }}>Category</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 600 }}>Price</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 600 }}>Change %</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 600 }}>Volume</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 600 }}>52W High</TableCell>
                        <TableCell align="right" sx={{ fontWeight: 600 }}>52W Low</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {pricesQuery.data.map((item) => (
                        <TableRow key={item.symbol} hover>
                          <TableCell sx={{ fontWeight: 500 }}>{item.symbol}</TableCell>
                          <TableCell>{item.name}</TableCell>
                          <TableCell>
                            <Chip label={item.category} size="small" variant="outlined" />
                          </TableCell>
                          <TableCell align="right">${item.price?.toFixed(2)}</TableCell>
                          <TableCell align="right" sx={{ color: getChangeColor(item.changePercent), fontWeight: 500 }}>
                            {item.changePercent}%
                          </TableCell>
                          <TableCell align="right">{(item.volume / 1e6).toFixed(2)}M</TableCell>
                          <TableCell align="right">${item.high52w?.toFixed(2)}</TableCell>
                          <TableCell align="right">${item.low52w?.toFixed(2)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              ) : (
                <Alert severity="info">No price data available</Alert>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </Container>
  );
}
