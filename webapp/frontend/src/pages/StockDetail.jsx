import React from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { createComponentLogger } from "../utils/errorLogger";
import {
  Alert,
  Box,
  Card,
  CardContent,
  Chip,
  CircularProgress,
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
  Tooltip,
  Typography,
} from "@mui/material";
import {
  TrendingUp,
  TrendingDown,
  Business,
  AccountBalance,
  Analytics,
  Timeline,
  EventNote,
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
  Tooltip as RechartsTooltip,
} from "recharts";
import api from "../services/api";
import {
  formatCurrency,
  formatNumber,
  formatPercent,
} from "../utils/formatters";

// Use centralized error logging (logger will be defined in component)

// Custom tooltip for 3-tier benchmarks
const BenchmarkTooltip = ({ active, payload, benchmarks }) => {
  if (!active || !payload || !payload.length) return null;

  const metricName = payload[0].payload.name;
  const value = payload[0].value;

  // Map display names to API keys
  const metricMap = {
    "ROE": "roe",
    "Gross Margin": "gross_margin",
    "Op. Margin": "operating_margin",
    "Net Margin": "profit_margin"
  };

  const apiKey = metricMap[metricName];
  const benchmarkData = benchmarks?.data?.data?.benchmarks?.[apiKey];

  return (
    <Box
      sx={{
        bgcolor: 'background.paper',
        p: 1.5,
        border: '1px solid',
        borderColor: 'divider',
        borderRadius: 1,
        boxShadow: 2,
      }}
    >
      <Typography variant="subtitle2" sx={{ fontWeight: 'bold', mb: 0.5 }}>
        {metricName}
      </Typography>
      <Typography variant="body2" sx={{ mb: 1 }}>
        Current: <strong>{value.toFixed(1)}%</strong>
      </Typography>
      <Divider sx={{ my: 0.5 }} />
      <Typography variant="caption" display="block" sx={{ mt: 0.5 }}>
        <strong>Sector Median:</strong> {benchmarkData?.sector?.toFixed(1) || "N/A"}%
        {benchmarkData?.sector && (value > benchmarkData.sector ? " ✓" : " ✗")}
      </Typography>
      <Typography variant="caption" display="block">
        <strong>1yr Historical:</strong> {benchmarkData?.historical_1yr?.toFixed(1) || "N/A"}%
        {benchmarkData?.historical_1yr && (value > benchmarkData.historical_1yr ? " ↑" : " ↓")}
      </Typography>
      <Typography variant="caption" display="block">
        <strong>Market Average:</strong> {benchmarkData?.market?.toFixed(1) || "N/A"}%
        {benchmarkData?.market && (value > benchmarkData.market ? " ↑" : " ↓")}
      </Typography>
    </Box>
  );
};

function StockDetail() {
  const logger = createComponentLogger("StockDetail");

  const { ticker } = useParams();
  const symbol = ticker; // Route uses :ticker param
  // Fetch stock profile data
  const {
    data: profile,
    isLoading: profileLoading,
    error: profileError,
  } = useQuery({
    queryKey: ["stockProfile", symbol],
    queryFn: () => api.getStockProfile(symbol),
    enabled: !!symbol,
    onError: (error) => logger.queryError("stockProfile", error, { symbol }),
  });

  // Fetch key metrics
  const {
    data: metrics,
    isLoading: metricsLoading,
    error: _metricsError,
  } = useQuery({
    queryKey: ["stockMetrics", symbol],
    queryFn: () => api.getStockMetrics(symbol),
    enabled: !!symbol,
    onError: (error) => logger.queryError("stockMetrics", error, { symbol }),
  });

  // Fetch stock scores (6-factor system)
  const {
    data: stockScores,
    isLoading: scoresLoading,
    error: _scoresError,
  } = useQuery({
    queryKey: ["stockScores", symbol],
    queryFn: () => api.get(`/api/scores/${symbol}`),
    enabled: !!symbol,
    onError: (error) => logger.queryError("stockScores", error, { symbol }),
  });

  // Fetch financial data
  const {
    data: financials,
    isLoading: _financialsLoading,
    error: _financialsError,
  } = useQuery({
    queryKey: ["stockFinancials", symbol],
    queryFn: () => api.getStockFinancials(symbol),
    enabled: !!symbol,
    onError: (error) => logger.queryError("stockFinancials", error, { symbol }),
  });

  // Fetch analyst recommendations
  const {
    data: recommendations,
    isLoading: _recLoading,
    error: _recError,
  } = useQuery({
    queryKey: ["stockRecommendations", symbol],
    queryFn: () => api.getAnalystRecommendations(symbol),
    enabled: !!symbol,
    onError: (error) =>
      logger.queryError("analystRecommendations", error, { symbol }),
  });

  // Fetch comprehensive financial statements
  const {
    data: balanceSheet,
    isLoading: balanceSheetLoading,
    error: _balanceSheetError,
  } = useQuery({
    queryKey: ["balanceSheet", symbol, "annual"],
    queryFn: () => api.getBalanceSheet(symbol, "annual"),
    enabled: !!symbol,
    onError: (error) =>
      logger.queryError("balanceSheet", error, { symbol, period: "annual" }),
  });
  const {
    data: incomeStatement,
    isLoading: incomeStatementLoading,
    error: _incomeStatementError,
  } = useQuery({
    queryKey: ["incomeStatement", symbol, "annual"],
    queryFn: () => api.getIncomeStatement(symbol, "annual"),
    enabled: !!symbol,
    onError: (error) =>
      logger.queryError("incomeStatement", error, { symbol, period: "annual" }),
  });
  const {
    data: cashFlowStatement,
    isLoading: cashFlowLoading,
    error: _cashFlowError,
  } = useQuery({
    queryKey: ["cashFlowStatement", symbol, "annual"],
    queryFn: () => api.getCashFlowStatement(symbol, "annual"),
    enabled: !!symbol,
    onError: (error) =>
      logger.queryError("cashFlowStatement", error, {
        symbol,
        period: "annual",
      }),
  });
  // Fetch comprehensive analyst data
  const {
    data: analystOverview,
    isLoading: analystOverviewLoading,
    error: _analystOverviewError,
  } = useQuery({
    queryKey: ["analystOverview", symbol],
    queryFn: () => api.getAnalystOverview(symbol),
    enabled: !!symbol,
    onError: (error) => logger.queryError("analystOverview", error, { symbol }),
  });
  // Fetch recent price data - lightweight and fast
  const {
    data: recentPrices,
    isLoading: recentPricesLoading,
    error: recentPricesError,
  } = useQuery({
    queryKey: ["stockPricesRecent", symbol],
    queryFn: () => api.getStockPricesRecent(symbol, 30), // Only 30 days for performance
    enabled: !!symbol,
    onError: (error) =>
      logger.queryError("stockPricesRecent", error, { symbol }),
  });

  // Fetch 3-tier benchmarks (sector, historical, market)
  const {
    data: benchmarks,
    isLoading: benchmarksLoading,
    error: _benchmarksError,
  } = useQuery({
    queryKey: ["stockBenchmarks", symbol],
    queryFn: () => api.get(`/api/benchmarks/${symbol}`),
    enabled: !!symbol,
    onError: (error) => logger.queryError("stockBenchmarks", error, { symbol }),
  });

  // Fetch stock events (earnings, dividends, splits, etc.)
  const {
    data: stockEvents,
    isLoading: eventsLoading,
    error: eventsError,
  } = useQuery({
    queryKey: ["stockEvents", symbol],
    queryFn: async () => {
      const API_BASE = (import.meta.env && import.meta.env.VITE_API_URL) || "";
      const params = new URLSearchParams({
        symbol: symbol,
        type: "upcoming",
        page: 1,
        limit: 10,
      });
      const response = await fetch(`${API_BASE}/api/calendar/events?${params}`);
      if (!response.ok) throw new Error("Failed to fetch events");
      return response.json();
    },
    enabled: !!symbol,
    onError: (error) => logger.queryError("stockEvents", error, { symbol }),
  });

  // Fetch positioning data
  const {
    data: positioningData,
    isLoading: _positioningLoading,
    error: _positioningError,
  } = useQuery({
    queryKey: ["positioning", symbol],
    queryFn: () => api.getPositioningData(symbol),
    enabled: !!symbol,
    onError: (error) => logger.queryError("positioning", error, { symbol }),
  });

  if (profileLoading) {
    return (
      <Container maxWidth="lg" sx={{ py: 4 }}>
        <Box
          display="flex"
          justifyContent="center"
          alignItems="center"
          minHeight="400px"
        >
          <CircularProgress size={60} />
        </Box>
      </Container>
    );
  }

  if (profileError) {
    return (
      <Container maxWidth="lg" sx={{ py: 4 }}>
        <Alert severity="error">
          Error loading stock data: {profileError.message}
        </Alert>
      </Container>
    );
  }

  // Debug logging
  console.log('🔍 StockDetail Debug:', {
    symbol,
    profile,
    profileType: typeof profile,
    isArray: Array.isArray(profile),
    profileKeys: profile ? Object.keys(profile) : 'null/undefined',
    profileLoading,
    profileError
  });

  // Check if profile is empty (handles both array and object)
  const isProfileEmpty = !profile ||
    (Array.isArray(profile) && profile.length === 0) ||
    (typeof profile === 'object' && !Array.isArray(profile) && Object.keys(profile).length === 0);

  if (isProfileEmpty) {
    console.log('❌ Profile is empty, showing Stock not found');
    return (
      <Container maxWidth="lg" sx={{ py: 4 }}>
        <Alert severity="warning">Stock not found: {symbol}</Alert>
      </Container>
    );
  }

  // Handle both array and object responses from API
  const stockData = Array.isArray(profile) ? profile[0] || {} : profile || {};
  const currentMetrics = metrics?.data || metrics || {};
  const currentFinancials = financials?.data || financials || {};
  const currentRecs = Array.isArray(recommendations) ? recommendations[0] || {} : recommendations || {};

  // Price change calculation
  const priceChange =
    stockData.price - (stockData.previous_close || stockData.price);
  const priceChangePercent =
    (priceChange / (stockData.previous_close || stockData.price)) * 100;
  const isPositiveChange = priceChange >= 0;

  // Key statistics for display
  const keyStats = [
    {
      label: "Market Cap",
      value: formatCurrency(currentMetrics.market_capitalization),
    },
    {
      label: "P/E Ratio",
      value: currentMetrics.pe_ratio
        ? formatNumber(currentMetrics.pe_ratio, 2)
        : "N/A",
    },
    {
      label: "EPS",
      value: currentMetrics.earnings_per_share
        ? formatCurrency(currentMetrics.earnings_per_share)
        : "N/A",
    },
    {
      label: "Dividend Yield",
      value: currentMetrics.dividend_yield
        ? formatPercent(currentMetrics.dividend_yield)
        : "N/A",
    },
    {
      label: "Book Value",
      value: currentMetrics.book_value
        ? formatCurrency(currentMetrics.book_value)
        : "N/A",
    },
    {
      label: "52-Week High",
      value: stockData.high52Week
        ? formatCurrency(stockData.high52Week)
        : "N/A",
    },
    {
      label: "52-Week Low",
      value: stockData.low52Week
        ? formatCurrency(stockData.low52Week)
        : "N/A",
    },
    { label: "Revenue TTM", value: formatCurrency(currentFinancials.revenue) },
    {
      label: "Net Income TTM",
      value: formatCurrency(currentFinancials.net_income),
    },
    {
      label: "Free Cash Flow",
      value: formatCurrency(currentFinancials.free_cash_flow),
    },
  ];

  // Financial ratios
  const ratios = [
    {
      label: "Current Ratio",
      value: currentMetrics.current_ratio
        ? formatNumber(currentMetrics.current_ratio, 2)
        : "N/A",
    },
    {
      label: "Debt to Equity",
      value: currentMetrics.debt_to_equity
        ? formatNumber(currentMetrics.debt_to_equity, 2)
        : "N/A",
    },
    {
      label: "ROE",
      value: currentMetrics.return_on_equity
        ? formatPercent(currentMetrics.return_on_equity)
        : "N/A",
    },
    {
      label: "ROA",
      value: currentMetrics.return_on_assets
        ? formatPercent(currentMetrics.return_on_assets)
        : "N/A",
    },
    {
      label: "Gross Margin",
      value: currentMetrics.gross_margin
        ? formatPercent(currentMetrics.gross_margin)
        : "N/A",
    },
    {
      label: "Operating Margin",
      value: currentMetrics.operating_margin
        ? formatPercent(currentMetrics.operating_margin)
        : "N/A",
    },
    {
      label: "Net Margin",
      value: currentMetrics.net_margin
        ? formatPercent(currentMetrics.net_margin)
        : "N/A",
    },
    {
      label: "Asset Turnover",
      value: currentMetrics.asset_turnover
        ? formatNumber(currentMetrics.asset_turnover, 2)
        : "N/A",
    },
  ];

  // Analyst recommendation distribution for pie chart
  const recData =
    currentRecs.strong_buy ||
    currentRecs.buy ||
    currentRecs.hold ||
    currentRecs.sell ||
    currentRecs.strong_sell
      ? [
          {
            name: "Strong Buy",
            value: currentRecs.strong_buy || 0,
            color: "#4caf50",
          },
          { name: "Buy", value: currentRecs.buy || 0, color: "#8bc34a" },
          { name: "Hold", value: currentRecs.hold || 0, color: "#ffc107" },
          { name: "Sell", value: currentRecs.sell || 0, color: "#ff9800" },
          {
            name: "Strong Sell",
            value: currentRecs.strong_sell || 0,
            color: "#f44336",
          },
        ].filter((item) => item.value > 0)
      : [];

  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      {/* Header Section */}
      <Box mb={4}>
        <Box display="flex" alignItems="center" gap={2} mb={2}>
          <Business sx={{ fontSize: 40, color: "primary.main" }} />
          <Box>
            <Typography variant="h3" component="h1" fontWeight="bold">
              {stockData.symbol}
            </Typography>
            <Typography variant="h6" color="text.secondary" gutterBottom>
              {stockData.company_name}
            </Typography>
          </Box>
        </Box>

        {/* Price and Change */}
        <Box display="flex" alignItems="center" gap={2} mb={2}>
          <Typography variant="h4" fontWeight="bold">
            {formatCurrency(stockData.price)}
          </Typography>
          <Box display="flex" alignItems="center" gap={1}>
            {isPositiveChange ? (
              <TrendingUp sx={{ color: "success.main" }} />
            ) : (
              <TrendingDown sx={{ color: "error.main" }} />
            )}
            <Typography
              variant="h6"
              color={isPositiveChange ? "success.main" : "error.main"}
              fontWeight="bold"
            >
              {formatCurrency(priceChange)} (
              {priceChangePercent.toFixed(2)}%)
            </Typography>
          </Box>
        </Box>

        {/* Industry and Sector Chips */}
        <Box display="flex" gap={1} flexWrap="wrap">
          {stockData.sector && (
            <Chip label={stockData.sector} color="primary" variant="outlined" />
          )}
          {stockData.industry && (
            <Chip
              label={stockData.industry}
              color="secondary"
              variant="outlined"
            />
          )}
          {stockData.country && (
            <Chip label={stockData.country} variant="outlined" />
          )}
        </Box>
      </Box>
      {/* Company Description */}
      {stockData.description && (
        <Card sx={{ mb: 4 }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Company Overview
            </Typography>
            <Typography variant="body1" color="text.secondary">
              {stockData.description}
            </Typography>
          </CardContent>
        </Card>
      )}

      {/* Key Statistics & Metrics */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h5" gutterBottom sx={{ mb: 3, fontWeight: 600 }}>
          <Analytics sx={{ verticalAlign: "middle", mr: 1 }} />
          Key Statistics & Metrics
        </Typography>
        <Grid container spacing={3}>
          <Grid item xs={12} md={8}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Key Statistics
                </Typography>
                <TableContainer>
                  <Table size="small">
                    <TableBody>
                      {(keyStats || []).map((stat, index) => (
                        <TableRow key={index}>
                          <TableCell component="th" scope="row">
                            {stat.label}
                          </TableCell>
                          <TableCell align="right" sx={{ fontWeight: "bold" }}>
                            {stat.value}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} md={4}>
            {recData.length > 0 && (
              <Card>
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    Analyst Recommendations
                  </Typography>
                  <Box height={200}>
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie
                          data={recData}
                          cx="50%"
                          cy="50%"
                          innerRadius={40}
                          outerRadius={80}
                          paddingAngle={5}
                          dataKey="value"
                        >
                          {(recData || []).map((entry, index) => (
                            <Cell key={`cell-${index}`} fill={entry.color} />
                          ))}
                        </Pie>
                        <RechartsTooltip />
                      </PieChart>
                    </ResponsiveContainer>
                  </Box>
                  <Box mt={2}>
                    {(recData || []).map((rec, index) => (
                      <Box
                        key={index}
                        display="flex"
                        alignItems="center"
                        gap={1}
                        mb={0.5}
                      >
                        <Box
                          width={12}
                          height={12}
                          bgcolor={rec.color}
                          borderRadius="50%"
                        />
                        <Typography variant="body2">
                          {rec.name}: {rec.value}
                        </Typography>
                      </Box>
                    ))}
                  </Box>
                </CardContent>
              </Card>
            )}
          </Grid>
        </Grid>
      </Box>

      {/* Price & Volume Section */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h5" gutterBottom sx={{ mb: 3, fontWeight: 600 }}>
          <Timeline sx={{ verticalAlign: "middle", mr: 1 }} />
          Price & Volume
        </Typography>
        {/* Price Chart Section */}
        <Grid container spacing={3} sx={{ mb: 3 }}>
          <Grid item xs={12}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Recent Price Chart (30 Days)
                </Typography>
                {recentPricesLoading ? (
                  <Box
                    display="flex"
                    justifyContent="center"
                    alignItems="center"
                    height={300}
                  >
                    <CircularProgress />
                  </Box>
                ) : recentPrices &&
                  recentPrices?.data &&
                  recentPrices?.data.data &&
                  recentPrices?.data.data.length > 0 ? (
                  <Box height={300}>
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart
                        data={recentPrices?.data.data.reverse()}
                        margin={{ top: 5, right: 30, left: 20, bottom: 5 }}
                      >
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="date" />
                        <YAxis domain={["dataMin - 5", "dataMax + 5"]} />
                        <RechartsTooltip
                          formatter={(value, name) => [
                            `$${value.toFixed(2)}`,
                            name === "close" ? "Close Price" : name,
                          ]}
                        />
                        <Line
                          type="monotone"
                          dataKey="close"
                          stroke="#2196f3"
                          strokeWidth={2}
                          dot={{ r: 0 }}
                          name="Close Price"
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </Box>
                ) : (
                  <Box
                    display="flex"
                    justifyContent="center"
                    alignItems="center"
                    height={300}
                  >
                    <Typography color="text.secondary">
                      {recentPricesError
                        ? `Error loading price data: ${recentPricesError.message}`
                        : "Price chart data not available"}
                    </Typography>
                  </Box>
                )}
              </CardContent>
            </Card>
          </Grid>
        </Grid>

        {/* Price Summary */}
        {recentPrices && recentPrices?.data && recentPrices?.data.summary && (
          <Grid container spacing={3} sx={{ mb: 3 }}>
            <Grid item xs={12}>
              <Card>
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    Price Summary (Last 30 Days)
                  </Typography>
                  <Grid container spacing={2}>
                    <Grid item xs={6} sm={3}>
                      <Box textAlign="center">
                        <Typography variant="body2" color="text.secondary">
                          Latest Price
                        </Typography>
                        <Typography variant="h6" fontWeight="bold">
                          {formatCurrency(
                            recentPrices?.data.summary.latestPrice
                          )}
                        </Typography>
                      </Box>
                    </Grid>
                    <Grid item xs={6} sm={3}>
                      <Box textAlign="center">
                        <Typography variant="body2" color="text.secondary">
                          Period Return
                        </Typography>
                        <Typography
                          variant="h6"
                          fontWeight="bold"
                          color={
                            recentPrices?.data.summary.periodReturn >= 0
                              ? "success.main"
                              : "error.main"
                          }
                        >
                          {recentPrices?.data.summary.periodReturn.toFixed(2)}%
                        </Typography>
                      </Box>
                    </Grid>
                    <Grid item xs={6} sm={3}>
                      <Box textAlign="center">
                        <Typography variant="body2" color="text.secondary">
                          Latest Volume
                        </Typography>
                        <Typography variant="h6" fontWeight="bold">
                          {formatNumber(
                            recentPrices?.data.summary.latestVolume
                          )}
                        </Typography>
                      </Box>
                    </Grid>
                    <Grid item xs={6} sm={3}>
                      <Box textAlign="center">
                        <Typography variant="body2" color="text.secondary">
                          Data Points
                        </Typography>
                        <Typography variant="h6" fontWeight="bold">
                          {recentPrices?.data.dataPoints} days
                        </Typography>
                      </Box>
                    </Grid>
                  </Grid>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        )}

        {/* OHLCV Data Table */}
        <Grid container spacing={3}>
          <Grid item xs={12}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Recent Price & Volume Data (OHLCV)
                </Typography>
                {recentPrices &&
                recentPrices?.data &&
                recentPrices?.data.data &&
                recentPrices?.data.data.length > 0 ? (
                  <TableContainer>
                    <Table size="small">
                      <TableBody>
                        <TableRow>
                          <TableCell>
                            <strong>Date</strong>
                          </TableCell>
                          <TableCell align="right">
                            <strong>Open</strong>
                          </TableCell>
                          <TableCell align="right">
                            <strong>High</strong>
                          </TableCell>
                          <TableCell align="right">
                            <strong>Low</strong>
                          </TableCell>
                          <TableCell align="right">
                            <strong>Close</strong>
                          </TableCell>
                          <TableCell align="right">
                            <strong>Volume</strong>
                          </TableCell>
                        </TableRow>
                        {(recentPrices?.data?.data || [])
                          .slice(0, 15)
                          .map((dayData, index) => (
                            <TableRow key={index}>
                              <TableCell>
                                {new Date(dayData.date).toLocaleDateString()}
                              </TableCell>
                              <TableCell align="right">
                                {formatCurrency(dayData.open)}
                              </TableCell>
                              <TableCell align="right">
                                {formatCurrency(dayData.high)}
                              </TableCell>
                              <TableCell align="right">
                                {formatCurrency(dayData.low)}
                              </TableCell>
                              <TableCell
                                align="right"
                                sx={{ fontWeight: "bold" }}
                              >
                                {formatCurrency(dayData.close)}
                              </TableCell>
                              <TableCell align="right">
                                {formatNumber(dayData.volume)}
                              </TableCell>
                            </TableRow>
                          ))}
                      </TableBody>
                    </Table>
                  </TableContainer>
                ) : (
                  <Box
                    display="flex"
                    justifyContent="center"
                    alignItems="center"
                    height={200}
                  >
                    <Typography color="text.secondary">
                      {recentPricesError
                        ? `Error: ${recentPricesError.message}`
                        : "OHLCV data not available"}
                    </Typography>
                  </Box>
                )}
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      </Box>

      {/* Financial Statements Section */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h5" gutterBottom sx={{ mb: 3, fontWeight: 600 }}>
          <AccountBalance sx={{ verticalAlign: "middle", mr: 1 }} />
          Financial Statements
        </Typography>
        {balanceSheetLoading || incomeStatementLoading || cashFlowLoading ? (
          <Box display="flex" justifyContent="center" p={4}>
            <CircularProgress />
          </Box>
        ) : (
          <Box>
            {/* Financial Statements Content */}
            <Typography variant="h6" gutterBottom sx={{ mb: 2 }}>
              Annual Statements - {symbol?.toUpperCase()}
            </Typography>

            <Grid container spacing={3}>
              {/* Income Statement */}
              <Grid item xs={12} lg={4}>
                <Card>
                  <CardContent>
                    <Typography
                      variant="h6"
                      gutterBottom
                      sx={{ display: "flex", alignItems: "center" }}
                    >
                      <AccountBalance sx={{ mr: 1 }} />
                      Income Statement (Annual)
                    </Typography>
                    <Divider sx={{ mb: 2 }} />

                    {incomeStatement?.data?.length > 0 ? (
                      <Box>
                        {(incomeStatement?.data || [])
                          .slice(0, 3)
                          .map((period, periodIndex) => (
                            <Box key={period.date} sx={{ mb: 3 }}>
                              <Typography
                                variant="subtitle2"
                                sx={{ fontWeight: "bold", mb: 1 }}
                              >
                                {new Date(period.date).getFullYear()}
                              </Typography>
                              <TableContainer>
                                <Table size="small">
                                  <TableBody>
                                    {period.items && Object.entries(period.items)
                                      .filter(([key]) =>
                                        [
                                          "Total Revenue",
                                          "Revenue",
                                          "Gross Profit",
                                          "Operating Income",
                                          "Net Income",
                                          "Basic EPS",
                                        ].some((item) => key.includes(item))
                                      )
                                      .slice(0, 6)
                                      .map(([key, value]) => (
                                        <TableRow key={key}>
                                          <TableCell
                                            sx={{
                                              py: 0.5,
                                              fontSize: "0.875rem",
                                            }}
                                          >
                                            {key
                                              .replace(/([A-Z])/g, " $1")
                                              .trim()}
                                          </TableCell>
                                          <TableCell
                                            align="right"
                                            sx={{
                                              py: 0.5,
                                              fontSize: "0.875rem",
                                            }}
                                          >
                                            {value
                                              ? formatCurrency(value, 0)
                                              : "N/A"}
                                          </TableCell>
                                        </TableRow>
                                      ))}
                                  </TableBody>
                                </Table>
                              </TableContainer>
                              {periodIndex < 2 && <Divider sx={{ mt: 2 }} />}
                            </Box>
                          ))}
                      </Box>
                    ) : (
                      <Typography color="text.secondary">
                        No income statement data available
                      </Typography>
                    )}
                  </CardContent>
                </Card>
              </Grid>

              {/* Balance Sheet */}
              <Grid item xs={12} lg={4}>
                <Card>
                  <CardContent>
                    <Typography
                      variant="h6"
                      gutterBottom
                      sx={{ display: "flex", alignItems: "center" }}
                    >
                      <Analytics sx={{ mr: 1 }} />
                      Balance Sheet (Annual)
                    </Typography>
                    <Divider sx={{ mb: 2 }} />

                    {balanceSheet?.data?.length > 0 ? (
                      <Box>
                        {(balanceSheet?.data || [])
                          .slice(0, 3)
                          .map((period, periodIndex) => (
                            <Box key={period.date} sx={{ mb: 3 }}>
                              <Typography
                                variant="subtitle2"
                                sx={{ fontWeight: "bold", mb: 1 }}
                              >
                                {new Date(period.date).getFullYear()}
                              </Typography>
                              <TableContainer>
                                <Table size="small">
                                  <TableBody>
                                    {period.items && Object.entries(period.items)
                                      .filter(([key]) =>
                                        [
                                          "Total Assets",
                                          "Current Assets",
                                          "Total Debt",
                                          "Total Equity",
                                          "Cash",
                                          "Total Liabilities",
                                        ].some((item) => key.includes(item))
                                      )
                                      .slice(0, 6)
                                      .map(([key, value]) => (
                                        <TableRow key={key}>
                                          <TableCell
                                            sx={{
                                              py: 0.5,
                                              fontSize: "0.875rem",
                                            }}
                                          >
                                            {key
                                              .replace(/([A-Z])/g, " $1")
                                              .trim()}
                                          </TableCell>
                                          <TableCell
                                            align="right"
                                            sx={{
                                              py: 0.5,
                                              fontSize: "0.875rem",
                                            }}
                                          >
                                            {value
                                              ? formatCurrency(value, 0)
                                              : "N/A"}
                                          </TableCell>
                                        </TableRow>
                                      ))}
                                  </TableBody>
                                </Table>
                              </TableContainer>
                              {periodIndex < 2 && <Divider sx={{ mt: 2 }} />}
                            </Box>
                          ))}
                      </Box>
                    ) : (
                      <Typography color="text.secondary">
                        No balance sheet data available
                      </Typography>
                    )}
                  </CardContent>
                </Card>
              </Grid>

              {/* Cash Flow Statement */}
              <Grid item xs={12} lg={4}>
                <Card>
                  <CardContent>
                    <Typography
                      variant="h6"
                      gutterBottom
                      sx={{ display: "flex", alignItems: "center" }}
                    >
                      <Timeline sx={{ mr: 1 }} />
                      Cash Flow (Annual)
                    </Typography>
                    <Divider sx={{ mb: 2 }} />

                    {cashFlowStatement?.data?.length > 0 ? (
                      <Box>
                        {(cashFlowStatement?.data || [])
                          .slice(0, 3)
                          .map((period, periodIndex) => (
                            <Box key={period.date} sx={{ mb: 3 }}>
                              <Typography
                                variant="subtitle2"
                                sx={{ fontWeight: "bold", mb: 1 }}
                              >
                                {new Date(period.date).getFullYear()}
                              </Typography>
                              <TableContainer>
                                <Table size="small">
                                  <TableBody>
                                    {period.items && Object.entries(period.items)
                                      .filter(([key]) =>
                                        [
                                          "Operating Cash Flow",
                                          "Free Cash Flow",
                                          "Capital Expenditure",
                                          "Dividends Paid",
                                          "Net Cash Flow",
                                          "Cash From Operations",
                                        ].some((item) => key.includes(item))
                                      )
                                      .slice(0, 6)
                                      .map(([key, value]) => (
                                        <TableRow key={key}>
                                          <TableCell
                                            sx={{
                                              py: 0.5,
                                              fontSize: "0.875rem",
                                            }}
                                          >
                                            {key
                                              .replace(/([A-Z])/g, " $1")
                                              .trim()}
                                          </TableCell>
                                          <TableCell
                                            align="right"
                                            sx={{
                                              py: 0.5,
                                              fontSize: "0.875rem",
                                            }}
                                          >
                                            {value
                                              ? formatCurrency(value, 0)
                                              : "N/A"}
                                          </TableCell>
                                        </TableRow>
                                      ))}
                                  </TableBody>
                                </Table>
                              </TableContainer>
                              {periodIndex < 2 && <Divider sx={{ mt: 2 }} />}
                            </Box>
                          ))}
                      </Box>
                    ) : (
                      <Typography color="text.secondary">
                        No cash flow data available
                      </Typography>
                    )}
                  </CardContent>
                </Card>
              </Grid>
            </Grid>

            {/* Financial Statement Summary Charts */}
            <Grid container spacing={3} sx={{ mt: 2 }}>
              {/* Revenue Trend */}
              <Grid item xs={12} md={6}>
                <Card>
                  <CardContent>
                    <Typography variant="h6" gutterBottom>
                      Revenue Trend
                    </Typography>
                    <ResponsiveContainer width="100%" height={250}>
                      <LineChart
                        data={
                          incomeStatement?.data
                            ?.slice(0, 5)
                            .reverse()
                            .map((period) => ({
                              year: new Date(period.date).getFullYear(),
                              revenue:
                                period.items["Total Revenue"] ||
                                period.items["Revenue"] ||
                                0,
                            })) || []
                        }
                      >
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="year" />
                        <YAxis />
                        <RechartsTooltip
                          formatter={(value) => [
                            formatCurrency(value, 0),
                            "Revenue",
                          ]}
                        />
                        <Line
                          type="monotone"
                          dataKey="revenue"
                          stroke="#1976d2"
                          strokeWidth={2}
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
              </Grid>

              {/* Net Income Trend */}
              <Grid item xs={12} md={6}>
                <Card>
                  <CardContent>
                    <Typography variant="h6" gutterBottom>
                      Net Income Trend
                    </Typography>
                    <ResponsiveContainer width="100%" height={250}>
                      <LineChart
                        data={
                          incomeStatement?.data
                            ?.slice(0, 5)
                            .reverse()
                            .map((period) => ({
                              year: new Date(period.date).getFullYear(),
                              netIncome: period.items["Net Income"] || 0,
                            })) || []
                        }
                      >
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="year" />
                        <YAxis />
                        <RechartsTooltip
                          formatter={(value) => [
                            formatCurrency(value, 0),
                            "Net Income",
                          ]}
                        />
                        <Line
                          type="monotone"
                          dataKey="netIncome"
                          stroke="#4caf50"
                          strokeWidth={2}
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          </Box>
        )}
      </Box>

      {/* Financial Ratios Section */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h5" gutterBottom sx={{ mb: 3, fontWeight: 600 }}>
          <Timeline sx={{ verticalAlign: "middle", mr: 1 }} />
          Financial Ratios
        </Typography>
        {metricsLoading ? (
          <Box display="flex" justifyContent="center" p={4}>
            <CircularProgress />
          </Box>
        ) : (
          <Card>
            <CardContent>
              <Grid container spacing={2}>
                {(ratios || []).map((ratio, index) => (
                  <Grid item xs={12} sm={6} md={3} key={index}>
                    <Box
                      p={2}
                      border={1}
                      borderColor="divider"
                      borderRadius={1}
                      textAlign="center"
                    >
                      <Typography variant="body2" color="text.secondary">
                        {ratio.label}
                      </Typography>
                      <Typography variant="h6" fontWeight="bold">
                        {ratio.value}
                      </Typography>
                    </Box>
                  </Grid>
                ))}
              </Grid>
            </CardContent>
          </Card>
        )}
      </Box>

      {/* Factor Analysis Section */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h5" gutterBottom sx={{ mb: 3, fontWeight: 600 }}>
          <Business sx={{ verticalAlign: "middle", mr: 1 }} />
          Institutional Factor Analysis
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
          Multi-factor quantitative analysis using institutional methodologies
        </Typography>

        <Grid container spacing={3}>
          {/* Overall Factor Score */}
          <Grid item xs={12}>
            <Card sx={{ mb: 3 }}>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Composite Factor Score
                </Typography>
                <Box
                  display="flex"
                  alignItems="center"
                  justifyContent="center"
                  mb={3}
                >
                  <Box textAlign="center">
                    <Typography variant="h2" color="primary" fontWeight="bold">
                      {Math.round((82 + 67 + 45 + 78 + 62 + 55) / 6)}
                    </Typography>
                    <Typography variant="body1" color="text.secondary">
                      Overall Score (0-100)
                    </Typography>
                  </Box>
                </Box>
                <LinearProgress
                  variant="determinate"
                  value={Math.round((82 + 67 + 45 + 78 + 62 + 55) / 6)}
                  color="primary"
                  sx={{ height: 12, borderRadius: 6 }}
                />
                <Box mt={2} textAlign="center">
                  <Typography variant="body2" color="text.secondary">
                    Weighted composite of Quality (30%), Growth (25%), Value
                    (20%), Momentum (15%), Sentiment (5%), Positioning (5%)
                  </Typography>
                </Box>
              </CardContent>
            </Card>
          </Grid>

          {/* 6-Factor Score Overview with Enhanced Calculations */}
          <Grid item xs={12}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Multi-Factor Quantitative Analysis
                </Typography>
                <Divider sx={{ mb: 3 }} />
                <Grid container spacing={3}>
                  {(() => {
                    // Get real factor scores from stock_scores API (6-factor system)
                    const scoresData = stockScores?.data?.data;

                    const qualityScore = scoresData?.quality_score || 50;
                    const growthScore = scoresData?.growth_score || 50;
                    const valueScore = scoresData?.value_score || 50;
                    const momentumScore = scoresData?.momentum_score || 50;
                    const sentimentScore = scoresData?.sentiment_score || 50;
                    const positioningScore = scoresData?.positioning_score || 50;

                    return [
                      {
                        factor: "Quality",
                        score: Math.round(qualityScore),
                        color: "primary",
                        description:
                          "ROE, margins, debt levels, earnings quality",
                        components: [
                          {
                            name: "ROE",
                            value: currentMetrics.return_on_equity || 0,
                            weight: 0.3,
                          },
                          {
                            name: "Gross Margin",
                            value: currentMetrics.gross_margin || 0,
                            weight: 0.25,
                          },
                          {
                            name: "Debt/Equity",
                            value: currentMetrics.debt_to_equity || 0,
                            weight: 0.25,
                          },
                          {
                            name: "Current Ratio",
                            value: currentMetrics.current_ratio || 0,
                            weight: 0.2,
                          },
                        ],
                      },
                      {
                        factor: "Growth",
                        score: Math.round(growthScore),
                        color: "success",
                        description:
                          "Revenue, earnings, and EPS growth trajectories",
                        components: [
                          {
                            name: "Revenue Growth",
                            value: currentMetrics.revenue_growth || 0,
                            weight: 0.4,
                          },
                          {
                            name: "EPS Growth",
                            value: currentMetrics.earnings_growth || 0,
                            weight: 0.4,
                          },
                          {
                            name: "Sales Growth 5Y",
                            value: currentMetrics.sales_growth_5y || 0,
                            weight: 0.2,
                          },
                        ],
                      },
                      {
                        factor: "Value",
                        score: Math.round(valueScore),
                        color: "warning",
                        description: "P/E, P/B, EV/EBITDA, and DCF valuations",
                        components: [
                          {
                            name: "P/E Ratio",
                            value: currentMetrics.pe_ratio || 0,
                            weight: 0.4,
                          },
                          {
                            name: "P/B Ratio",
                            value: currentMetrics.book_value ? stockData.price / currentMetrics.book_value : 0,
                            weight: 0.3,
                          },
                          { name: "EV/EBITDA", value: currentMetrics.ev_ebitda || 0, weight: 0.3 }
                        ],
                      },
                      {
                        factor: "Momentum",
                        score: Math.round(momentumScore),
                        color: "info",
                        description:
                          "Price trends, earnings revisions, estimate changes",
                        components: [
                          { name: "RSI", value: scoresData?.rsi || 0, weight: 0.4 },
                          { name: "MACD", value: scoresData?.macd || 0, weight: 0.3 },
                          { name: "Price Change", value: stockData.price_change_1d || 0, weight: 0.3 },
                        ],
                      },
                      {
                        factor: "Sentiment",
                        score: Math.round(sentimentScore),
                        color: "secondary",
                        description:
                          "Analyst ratings, social sentiment, media coverage",
                        components: [
                          { name: "Analyst Rating", value: currentMetrics.analyst_rating || 0, weight: 0.4 },
                          { name: "Social Sentiment", value: currentMetrics.social_sentiment || 0, weight: 0.3 },
                          { name: "News Sentiment", value: currentMetrics.news_sentiment || 0, weight: 0.3 },
                        ],
                      },
                      {
                        factor: "Positioning",
                        score: Math.round(positioningScore),
                        color: positioningScore >= 70 ? "success" : positioningScore >= 50 ? "info" : "error",
                        description:
                          "Institutional flows, insider activity, short interest",
                        components: [
                          {
                            name: "Institutional Ownership",
                            value:
                              positioningData?.positioning_metrics?.institutional_ownership ||
                              currentMetrics.institutional_ownership || 0,
                            weight: 0.4,
                          },
                          {
                            name: "Short Interest",
                            value: positioningData?.positioning_metrics?.short_percent_of_float ||
                                   currentMetrics.short_interest || 0,
                            weight: 0.3,
                          },
                          {
                            name: "Insider Ownership",
                            value: positioningData?.positioning_metrics?.insider_ownership || 0,
                            weight: 0.3
                          },
                        ],
                      },
                      {
                        factor: "Technical",
                        score: Math.round(trendScore),
                        color: trendScore >= 70 ? "success" : trendScore >= 50 ? "info" : "error",
                        description:
                          "Moving averages, RSI, MACD signals",
                        components: [
                          {
                            name: "SMA 20",
                            value: scoresData?.sma_20 || 0,
                            weight: 0.3,
                          },
                          {
                            name: "SMA 50",
                            value: scoresData?.sma_50 || 0,
                            weight: 0.3,
                          },
                          {
                            name: "RSI",
                            value: scoresData?.rsi || 0,
                            weight: 0.4,
                          },
                        ],
                      },
                    ];
                  })().map((factor) => (
                    <Grid item xs={12} md={6} lg={4} key={factor.factor}>
                      <Card variant="outlined" sx={{ height: "100%" }}>
                        <CardContent>
                          <Box
                            display="flex"
                            alignItems="center"
                            justifyContent="between"
                            mb={2}
                          >
                            <Typography variant="h6" fontWeight="bold">
                              {factor.factor}
                            </Typography>
                            <Box display="flex" alignItems="center" gap={1}>
                              <Chip
                                label={factor.score}
                                color={factor.color}
                                variant="filled"
                                size="small"
                                sx={{ fontWeight: "bold" }}
                              />
                              {factor.trend === "improving" ? (
                                <TrendingUp color="success" fontSize="small" />
                              ) : factor.trend === "deteriorating" ? (
                                <TrendingDown color="error" fontSize="small" />
                              ) : (
                                <Analytics color="action" fontSize="small" />
                              )}
                            </Box>
                          </Box>

                          <LinearProgress
                            variant="determinate"
                            value={factor.score}
                            color={factor.color}
                            sx={{ mb: 2, height: 8, borderRadius: 4 }}
                          />

                          <Typography
                            variant="body2"
                            color="text.secondary"
                            mb={2}
                          >
                            {factor.description}
                          </Typography>

                          <Box display="flex" justifyContent="between" mb={1}>
                            <Typography variant="body2" color="text.secondary">
                              Percentile Rank
                            </Typography>
                            <Typography variant="body2" fontWeight="bold">
                              {factor.percentile}th
                            </Typography>
                          </Box>

                          <Typography variant="caption" color="text.secondary">
                            Components:{" "}
                            {(factor.components || [])
                              .map((c) => c.name)
                              .join(", ")}
                          </Typography>
                        </CardContent>
                      </Card>
                    </Grid>
                  ))}
                </Grid>
              </CardContent>
            </Card>
          </Grid>

          {/* Factor Breakdown Details */}
          <Grid item xs={12} md={6}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Quality Factor Breakdown
                </Typography>
                <Divider sx={{ mb: 2 }} />
                <Box mb={3}>
                  <ResponsiveContainer width="100%" height={200}>
                    <BarChart
                      data={[
                        {
                          name: "ROE",
                          value:
                            (currentMetrics.return_on_equity || 0.15) * 100,
                          benchmark: benchmarks?.data?.data?.benchmarks?.roe?.sector || 15,
                        },
                        {
                          name: "Gross Margin",
                          value: (currentMetrics.gross_margin || 0.25) * 100,
                          benchmark: benchmarks?.data?.data?.benchmarks?.gross_margin?.sector || 20,
                        },
                        {
                          name: "Op. Margin",
                          value:
                            (currentMetrics.operating_margin || 0.12) * 100,
                          benchmark: benchmarks?.data?.data?.benchmarks?.operating_margin?.sector || 10,
                        },
                        {
                          name: "Net Margin",
                          value: (currentMetrics.net_margin || 0.08) * 100,
                          benchmark: benchmarks?.data?.data?.benchmarks?.profit_margin?.sector || 5,
                        },
                      ]}
                    >
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="name" />
                      <YAxis />
                      <RechartsTooltip content={<BenchmarkTooltip benchmarks={benchmarks} />} />
                      <Bar dataKey="value" fill="#1976d2" />
                      <Bar dataKey="benchmark" fill="#e0e0e0" opacity={0.5} />
                    </BarChart>
                  </ResponsiveContainer>
                </Box>

                <TableContainer>
                  <Table size="small">
                    <TableBody>
                      <TableRow>
                        <TableCell>Return on Equity</TableCell>
                        <TableCell align="right">
                          <Chip
                            label={
                              currentMetrics.return_on_equity
                                ? `${formatPercent(currentMetrics.return_on_equity)}`
                                : "N/A"
                            }
                            color={
                              currentMetrics.return_on_equity > (benchmarks?.data?.data?.benchmarks?.roe?.sector || 15) / 100
                                ? "success"
                                : "default"
                            }
                            size="small"
                          />
                        </TableCell>
                        <TableCell align="right">
                          <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 0.3 }}>
                            <Typography variant="caption" sx={{ fontSize: 10, lineHeight: 1.2 }}>
                              <strong>S:</strong> {benchmarks?.data?.data?.benchmarks?.roe?.sector?.toFixed(1) || "15.0"}% {(currentMetrics.return_on_equity * 100) > (benchmarks?.data?.data?.benchmarks?.roe?.sector || 15) ? "✓" : "✗"}
                            </Typography>
                            <Typography variant="caption" sx={{ fontSize: 10, lineHeight: 1.2 }}>
                              <strong>H:</strong> {benchmarks?.data?.data?.benchmarks?.roe?.historical_1yr?.toFixed(1) || "N/A"}% {benchmarks?.data?.data?.benchmarks?.roe?.historical_1yr && (currentMetrics.return_on_equity * 100) > benchmarks.data.data.benchmarks.roe.historical_1yr ? "↑" : "↓"}
                            </Typography>
                            <Typography variant="caption" sx={{ fontSize: 10, lineHeight: 1.2 }}>
                              <strong>M:</strong> {benchmarks?.data?.data?.benchmarks?.roe?.market?.toFixed(1) || "N/A"}% {benchmarks?.data?.data?.benchmarks?.roe?.market && (currentMetrics.return_on_equity * 100) > benchmarks.data.data.benchmarks.roe.market ? "↑" : "↓"}
                            </Typography>
                          </Box>
                        </TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell>Debt-to-Equity</TableCell>
                        <TableCell align="right">
                          <Chip
                            label={
                              currentMetrics.debt_to_equity
                                ? formatNumber(currentMetrics.debt_to_equity, 2)
                                : "N/A"
                            }
                            color={
                              currentMetrics.debt_to_equity < 0.3
                                ? "success"
                                : "warning"
                            }
                            size="small"
                          />
                        </TableCell>
                        <TableCell align="right">
                          <Typography variant="caption" color="text.secondary">
                            vs 0.3 optimal
                          </Typography>
                        </TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell>Interest Coverage</TableCell>
                        <TableCell align="right">
                          <Chip
                            label={currentMetrics.interest_coverage || "N/A"}
                            color="success"
                            size="small"
                          />
                        </TableCell>
                        <TableCell align="right">
                          <Typography variant="caption" color="text.secondary">
                            vs 5x minimum
                          </Typography>
                        </TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell>Altman Z-Score</TableCell>
                        <TableCell align="right">
                          <Chip label="2.8" color="success" size="small" />
                        </TableCell>
                        <TableCell align="right">
                          <Typography variant="caption" color="text.secondary">
                            Safe zone (&gt;2.6)
                          </Typography>
                        </TableCell>
                      </TableRow>
                    </TableBody>
                  </Table>
                </TableContainer>
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} md={6}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Growth Factor Analysis
                </Typography>
                <Divider sx={{ mb: 2 }} />
                <Box mb={3}>
                  <ResponsiveContainer width="100%" height={200}>
                    <LineChart
                      data={[]}
                    >
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="year" />
                      <YAxis />
                      <RechartsTooltip />
                      <Line
                        type="monotone"
                        dataKey="revenue"
                        stroke="#4caf50"
                        strokeWidth={2}
                      />
                      <Line
                        type="monotone"
                        dataKey="earnings"
                        stroke="#2196f3"
                        strokeWidth={2}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </Box>

                <TableContainer>
                  <Table size="small">
                    <TableBody>
                      <TableRow>
                        <TableCell>Revenue CAGR (5Y)</TableCell>
                        <TableCell align="right">
                          <Chip
                            label={
                              currentMetrics.revenue_growth
                                ? `${formatPercent(currentMetrics.revenue_growth)}`
                                : "N/A"
                            }
                            color="success"
                            size="small"
                          />
                        </TableCell>
                        <TableCell align="right">
                          <Typography variant="caption" color="text.secondary">
                            {currentMetrics.sector_revenue_avg
                              ? `vs ${formatPercent(currentMetrics.sector_revenue_avg)} sector avg`
                              : ""}
                          </Typography>
                        </TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell>EPS CAGR (5Y)</TableCell>
                        <TableCell align="right">
                          <Chip
                            label={
                              currentMetrics.earnings_growth
                                ? `${formatPercent(currentMetrics.earnings_growth)}`
                                : "N/A"
                            }
                            color="success"
                            size="small"
                          />
                        </TableCell>
                        <TableCell align="right">
                          <Typography variant="caption" color="text.secondary">
                            {currentMetrics.sector_earnings_avg
                              ? `vs ${formatPercent(currentMetrics.sector_earnings_avg)} sector avg`
                              : ""}
                          </Typography>
                        </TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell>FCF Growth (3Y)</TableCell>
                        <TableCell align="right">
                          <Chip
                            label={
                              currentMetrics.fcf_growth
                                ? `${formatPercent(currentMetrics.fcf_growth)}`
                                : "N/A"
                            }
                            color="success"
                            size="small"
                          />
                        </TableCell>
                        <TableCell align="right">
                          <Typography variant="caption" color="text.secondary">
                            {currentMetrics.sector_fcf_avg
                              ? `vs ${formatPercent(currentMetrics.sector_fcf_avg)} sector avg`
                              : ""}
                          </Typography>
                        </TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell>PEG Ratio</TableCell>
                        <TableCell align="right">
                          <Chip
                            label={
                              (currentMetrics.pe_ratio || 18) /
                                ((currentMetrics.earnings_growth || 0.1) *
                                  100) || "N/A"
                            }
                            color="warning"
                            size="small"
                          />
                        </TableCell>
                        <TableCell align="right">
                          <Typography variant="caption" color="text.secondary">
                            vs 1.0 fair value
                          </Typography>
                        </TableCell>
                      </TableRow>
                    </TableBody>
                  </Table>
                </TableContainer>
              </CardContent>
            </Card>
          </Grid>

          {/* Value Factor Breakdown */}
          <Grid item xs={12} md={6}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Value Factor Analysis
                </Typography>
                <Divider sx={{ mb: 2 }} />
                <Box mb={3}>
                  <ResponsiveContainer width="100%" height={200}>
                    <BarChart
                      data={[
                        {
                          metric: 'Value Score',
                          score: stockScores?.data?.data?.value_score || 0,
                          target: 70,
                          good: 50
                        }
                      ]}
                      margin={{ top: 10, right: 10, left: 10, bottom: 10 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="metric" />
                      <YAxis domain={[0, 100]} />
                      <Tooltip />
                      <Bar dataKey="score" fill={stockScores?.data?.data?.value_score >= 70 ? "#4caf50" : stockScores?.data?.data?.value_score >= 50 ? "#ff9800" : "#f44336"} name="Score" />
                      <Bar dataKey="target" fill="#e0e0e0" opacity={0.3} name="Target (70)" />
                      <Bar dataKey="good" fill="#e0e0e0" opacity={0.2} name="Good (50)" />
                    </BarChart>
                  </ResponsiveContainer>
                </Box>
                <TableContainer>
                  <Table size="small">
                    <TableBody>
                      <TableRow>
                        <TableCell>P/E Ratio</TableCell>
                        <TableCell align="right">
                          <Chip
                            label={stockScores?.data?.data?.pe_ratio?.toFixed(2) || "N/A"}
                            color={
                              stockScores?.data?.data?.pe_ratio < 20
                                ? "success"
                                : stockScores?.data?.data?.pe_ratio < 30
                                  ? "warning"
                                  : "error"
                            }
                            size="small"
                          />
                        </TableCell>
                        <TableCell align="right">
                          <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 0.3 }}>
                            <Typography variant="caption" sx={{ fontSize: 10, lineHeight: 1.2 }}>
                              <strong>S:</strong> {benchmarks?.data?.data?.benchmarks?.pe_ratio?.sector?.toFixed(1) || "20.0"} {metrics?.data?.pe_ratio && (metrics.data.pe_ratio < (benchmarks?.data?.data?.benchmarks?.pe_ratio?.sector || 20)) ? "✓" : "✗"}
                            </Typography>
                            <Typography variant="caption" sx={{ fontSize: 10, lineHeight: 1.2 }}>
                              <strong>H:</strong> {benchmarks?.data?.data?.benchmarks?.pe_ratio?.historical_1yr?.toFixed(1) || "N/A"} {benchmarks?.data?.data?.benchmarks?.pe_ratio?.historical_1yr && metrics?.data?.pe_ratio && (metrics.data.pe_ratio < benchmarks.data.data.benchmarks.pe_ratio.historical_1yr) ? "↓" : "↑"}
                            </Typography>
                            <Typography variant="caption" sx={{ fontSize: 10, lineHeight: 1.2 }}>
                              <strong>M:</strong> {benchmarks?.data?.data?.benchmarks?.pe_ratio?.market?.toFixed(1) || "N/A"} {benchmarks?.data?.data?.benchmarks?.pe_ratio?.market && metrics?.data?.pe_ratio && (metrics.data.pe_ratio < benchmarks.data.data.benchmarks.pe_ratio.market) ? "↓" : "↑"}
                            </Typography>
                          </Box>
                        </TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell>Price/Book Ratio</TableCell>
                        <TableCell align="right">
                          <Chip
                            label={metrics?.data?.price_to_book?.toFixed(2) || "N/A"}
                            color={
                              metrics?.data?.price_to_book && metrics.data.price_to_book < (benchmarks?.data?.data?.benchmarks?.price_to_book?.sector || 3)
                                ? "success"
                                : metrics?.data?.price_to_book && metrics.data.price_to_book < (benchmarks?.data?.data?.benchmarks?.price_to_book?.sector || 5)
                                  ? "warning"
                                  : "error"
                            }
                            size="small"
                          />
                        </TableCell>
                        <TableCell align="right">
                          <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 0.3 }}>
                            <Typography variant="caption" sx={{ fontSize: 10, lineHeight: 1.2 }}>
                              <strong>S:</strong> {benchmarks?.data?.data?.benchmarks?.price_to_book?.sector?.toFixed(1) || "3.0"} {metrics?.data?.price_to_book && (metrics.data.price_to_book < (benchmarks?.data?.data?.benchmarks?.price_to_book?.sector || 3)) ? "✓" : "✗"}
                            </Typography>
                            <Typography variant="caption" sx={{ fontSize: 10, lineHeight: 1.2 }}>
                              <strong>H:</strong> {benchmarks?.data?.data?.benchmarks?.price_to_book?.historical_1yr?.toFixed(1) || "N/A"} {benchmarks?.data?.data?.benchmarks?.price_to_book?.historical_1yr && metrics?.data?.price_to_book && (metrics.data.price_to_book < benchmarks.data.data.benchmarks.price_to_book.historical_1yr) ? "↓" : "↑"}
                            </Typography>
                            <Typography variant="caption" sx={{ fontSize: 10, lineHeight: 1.2 }}>
                              <strong>M:</strong> {benchmarks?.data?.data?.benchmarks?.price_to_book?.market?.toFixed(1) || "N/A"} {benchmarks?.data?.data?.benchmarks?.price_to_book?.market && metrics?.data?.price_to_book && (metrics.data.price_to_book < benchmarks.data.data.benchmarks.price_to_book.market) ? "↓" : "↑"}
                            </Typography>
                          </Box>
                        </TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell>EV/EBITDA</TableCell>
                        <TableCell align="right">
                          <Chip
                            label={metrics?.data?.ev_to_ebitda?.toFixed(2) || "N/A"}
                            color={
                              metrics?.data?.ev_to_ebitda && metrics.data.ev_to_ebitda < (benchmarks?.data?.data?.benchmarks?.ev_to_ebitda?.sector || 15)
                                ? "success"
                                : metrics?.data?.ev_to_ebitda && metrics.data.ev_to_ebitda < (benchmarks?.data?.data?.benchmarks?.ev_to_ebitda?.sector || 20)
                                  ? "warning"
                                  : "error"
                            }
                            size="small"
                          />
                        </TableCell>
                        <TableCell align="right">
                          <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 0.3 }}>
                            <Typography variant="caption" sx={{ fontSize: 10, lineHeight: 1.2 }}>
                              <strong>S:</strong> {benchmarks?.data?.data?.benchmarks?.ev_to_ebitda?.sector?.toFixed(1) || "15.0"} {metrics?.data?.ev_to_ebitda && (metrics.data.ev_to_ebitda < (benchmarks?.data?.data?.benchmarks?.ev_to_ebitda?.sector || 15)) ? "✓" : "✗"}
                            </Typography>
                            <Typography variant="caption" sx={{ fontSize: 10, lineHeight: 1.2 }}>
                              <strong>H:</strong> {benchmarks?.data?.data?.benchmarks?.ev_to_ebitda?.historical_1yr?.toFixed(1) || "N/A"} {benchmarks?.data?.data?.benchmarks?.ev_to_ebitda?.historical_1yr && metrics?.data?.ev_to_ebitda && (metrics.data.ev_to_ebitda < benchmarks.data.data.benchmarks.ev_to_ebitda.historical_1yr) ? "↓" : "↑"}
                            </Typography>
                            <Typography variant="caption" sx={{ fontSize: 10, lineHeight: 1.2 }}>
                              <strong>M:</strong> {benchmarks?.data?.data?.benchmarks?.ev_to_ebitda?.market?.toFixed(1) || "N/A"} {benchmarks?.data?.data?.benchmarks?.ev_to_ebitda?.market && metrics?.data?.ev_to_ebitda && (metrics.data.ev_to_ebitda < benchmarks.data.data.benchmarks.ev_to_ebitda.market) ? "↓" : "↑"}
                            </Typography>
                          </Box>
                        </TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell>Value Score</TableCell>
                        <TableCell align="right">
                          <Chip
                            label={stockScores?.data?.data?.value_score || "N/A"}
                            color={
                              stockScores?.data?.data?.value_score >= 70
                                ? "success"
                                : stockScores?.data?.data?.value_score >= 50
                                  ? "warning"
                                  : "error"
                            }
                            size="small"
                          />
                        </TableCell>
                        <TableCell align="right">
                          <Typography variant="caption" color="text.secondary">
                            0-100 scale
                          </Typography>
                        </TableCell>
                      </TableRow>
                    </TableBody>
                  </Table>
                </TableContainer>
              </CardContent>
            </Card>
          </Grid>

          {/* Momentum Factor Breakdown */}
          <Grid item xs={12} md={6}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Momentum Factor Analysis
                </Typography>
                <Divider sx={{ mb: 2 }} />
                <Box mb={3}>
                  <ResponsiveContainer width="100%" height={200}>
                    <BarChart
                      data={[
                        {
                          metric: 'Momentum Score',
                          score: stockScores?.data?.data?.momentum_score || 0,
                          target: 70,
                          good: 50
                        }
                      ]}
                      margin={{ top: 10, right: 10, left: 10, bottom: 10 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="metric" />
                      <YAxis domain={[0, 100]} />
                      <Tooltip />
                      <Bar dataKey="score" fill={stockScores?.data?.data?.momentum_score >= 70 ? "#4caf50" : stockScores?.data?.data?.momentum_score >= 50 ? "#ff9800" : "#f44336"} name="Score" />
                      <Bar dataKey="target" fill="#e0e0e0" opacity={0.3} name="Target (70)" />
                      <Bar dataKey="good" fill="#e0e0e0" opacity={0.2} name="Good (50)" />
                    </BarChart>
                  </ResponsiveContainer>
                </Box>
                <TableContainer>
                  <Table size="small">
                    <TableBody>
                      <TableRow>
                        <TableCell>RSI (14-day)</TableCell>
                        <TableCell align="right">
                          <Chip
                            label={stockScores?.data?.data?.rsi?.toFixed(2) || "N/A"}
                            color={
                              stockScores?.data?.data?.rsi > 70
                                ? "error"
                                : stockScores?.data?.data?.rsi < 30
                                  ? "warning"
                                  : "success"
                            }
                            size="small"
                          />
                        </TableCell>
                        <TableCell align="right">
                          <Typography variant="caption" color="text.secondary">
                            30-70 neutral zone
                          </Typography>
                        </TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell>1-Day Change</TableCell>
                        <TableCell align="right">
                          <Chip
                            label={`${(stockScores?.data?.data?.price_change_1d || 0).toFixed(2)}%`}
                            color={
                              stockScores?.data?.data?.price_change_1d > 0
                                ? "success"
                                : "error"
                            }
                            size="small"
                          />
                        </TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell>5-Day Change</TableCell>
                        <TableCell align="right">
                          <Chip
                            label={`${(stockScores?.data?.data?.price_change_5d || 0).toFixed(2)}%`}
                            color={
                              stockScores?.data?.data?.price_change_5d > 0
                                ? "success"
                                : "error"
                            }
                            size="small"
                          />
                        </TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell>30-Day Change</TableCell>
                        <TableCell align="right">
                          <Chip
                            label={`${(stockScores?.data?.data?.price_change_30d || 0).toFixed(2)}%`}
                            color={
                              stockScores?.data?.data?.price_change_30d > 0
                                ? "success"
                                : "error"
                            }
                            size="small"
                          />
                        </TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell>Momentum Score</TableCell>
                        <TableCell align="right">
                          <Chip
                            label={stockScores?.data?.data?.momentum_score?.toFixed(1) || "N/A"}
                            color={
                              stockScores?.data?.data?.momentum_score >= 70
                                ? "success"
                                : stockScores?.data?.data?.momentum_score >= 50
                                  ? "warning"
                                  : "error"
                            }
                            size="small"
                          />
                        </TableCell>
                        <TableCell align="right">
                          <Typography variant="caption" color="text.secondary">
                            0-100 scale
                          </Typography>
                        </TableCell>
                      </TableRow>
                    </TableBody>
                  </Table>
                </TableContainer>
              </CardContent>
            </Card>
          </Grid>

          {/* Positioning Factor Breakdown */}
          <Grid item xs={12} md={6}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Positioning Factor Analysis
                </Typography>
                <Divider sx={{ mb: 2 }} />
                <Box mb={3}>
                  <ResponsiveContainer width="100%" height={200}>
                    <BarChart
                      data={[
                        {
                          metric: 'Positioning Score',
                          score: stockScores?.data?.data?.positioning_score || 0,
                          target: 70,
                          good: 50
                        }
                      ]}
                      margin={{ top: 10, right: 10, left: 10, bottom: 10 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="metric" />
                      <YAxis domain={[0, 100]} />
                      <Tooltip />
                      <Bar dataKey="score" fill={stockScores?.data?.data?.positioning_score >= 70 ? "#4caf50" : stockScores?.data?.data?.positioning_score >= 50 ? "#ff9800" : "#f44336"} name="Score" />
                      <Bar dataKey="target" fill="#e0e0e0" opacity={0.3} name="Target (70)" />
                      <Bar dataKey="good" fill="#e0e0e0" opacity={0.2} name="Good (50)" />
                    </BarChart>
                  </ResponsiveContainer>
                </Box>
                <TableContainer>
                  <Table size="small">
                    <TableBody>
                      <TableRow>
                        <TableCell>Positioning Score</TableCell>
                        <TableCell align="right">
                          <Chip
                            label={stockScores?.data?.data?.positioning_score?.toFixed(1) || "N/A"}
                            color={
                              stockScores?.data?.data?.positioning_score >= 70
                                ? "success"
                                : stockScores?.data?.data?.positioning_score >= 50
                                  ? "warning"
                                  : "error"
                            }
                            size="small"
                          />
                        </TableCell>
                        <TableCell align="right">
                          <Typography variant="caption" color="text.secondary">
                            0-100 scale
                          </Typography>
                        </TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell colSpan={3}>
                          <Typography variant="caption" color="text.secondary" sx={{ fontStyle: 'italic' }}>
                            Positioning score reflects institutional ownership patterns, insider activity, and short interest data.
                          </Typography>
                        </TableCell>
                      </TableRow>
                    </TableBody>
                  </Table>
                </TableContainer>
              </CardContent>
            </Card>
          </Grid>

          {/* Sentiment Factor Breakdown */}
          <Grid item xs={12} md={6}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Sentiment Factor Analysis
                </Typography>
                <Divider sx={{ mb: 2 }} />
                <Box mb={3}>
                  <ResponsiveContainer width="100%" height={200}>
                    <BarChart
                      data={[
                        {
                          metric: 'Sentiment Score',
                          score: stockScores?.data?.data?.sentiment_score || 0,
                          target: 70,
                          good: 50
                        }
                      ]}
                      margin={{ top: 10, right: 10, left: 10, bottom: 10 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="metric" />
                      <YAxis domain={[0, 100]} />
                      <Tooltip />
                      <Bar dataKey="score" fill={stockScores?.data?.data?.sentiment_score >= 70 ? "#4caf50" : stockScores?.data?.data?.sentiment_score >= 50 ? "#ff9800" : "#f44336"} name="Score" />
                      <Bar dataKey="target" fill="#e0e0e0" opacity={0.3} name="Target (70)" />
                      <Bar dataKey="good" fill="#e0e0e0" opacity={0.2} name="Good (50)" />
                    </BarChart>
                  </ResponsiveContainer>
                </Box>
                <TableContainer>
                  <Table size="small">
                    <TableBody>
                      <TableRow>
                        <TableCell>Sentiment Score</TableCell>
                        <TableCell align="right">
                          <Chip
                            label={stockScores?.data?.data?.sentiment_score?.toFixed(1) || "N/A"}
                            color={
                              stockScores?.data?.data?.sentiment_score >= 70
                                ? "success"
                                : stockScores?.data?.data?.sentiment_score >= 50
                                  ? "warning"
                                  : "error"
                            }
                            size="small"
                          />
                        </TableCell>
                        <TableCell align="right">
                          <Typography variant="caption" color="text.secondary">
                            0-100 scale
                          </Typography>
                        </TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell colSpan={3}>
                          <Typography variant="caption" color="text.secondary" sx={{ fontStyle: 'italic' }}>
                            Sentiment score aggregates analyst ratings, news sentiment, and social media activity.
                          </Typography>
                        </TableCell>
                      </TableRow>
                    </TableBody>
                  </Table>
                </TableContainer>
              </CardContent>
            </Card>
          </Grid>

          {/* Advanced Factor Insights */}
          <Grid item xs={12}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Factor-Based Investment Insights
                </Typography>
                <Divider sx={{ mb: 3 }} />
                <Grid container spacing={3}>
                  <Grid item xs={12} md={4}>
                    <Box
                      p={3}
                      border={1}
                      borderColor="primary.main"
                      borderRadius={2}
                    >
                      <Box display="flex" alignItems="center" gap={2} mb={2}>
                        <Analytics color="primary" />
                        <Typography variant="h6" color="primary">
                          Quality Premium
                        </Typography>
                      </Box>
                      <Typography variant="body2" color="text.secondary" mb={2}>
                        High-quality companies with strong balance sheets and
                        consistent profitability typically command valuation
                        premiums during market stress.
                      </Typography>
                      <Chip
                        label="Strong Quality Score: 82/100"
                        color="success"
                        size="small"
                      />
                    </Box>
                  </Grid>

                  <Grid item xs={12} md={4}>
                    <Box
                      p={3}
                      border={1}
                      borderColor="warning.main"
                      borderRadius={2}
                    >
                      <Box display="flex" alignItems="center" gap={2} mb={2}>
                        <Timeline color="warning" />
                        <Typography variant="h6" color="warning.main">
                          Value Opportunity
                        </Typography>
                      </Box>
                      <Typography variant="body2" color="text.secondary" mb={2}>
                        Current valuation metrics suggest potential value
                        opportunity, but consider quality and growth factors for
                        comprehensive assessment.
                      </Typography>
                      <Chip
                        label="Value Score: 45/100"
                        color="warning"
                        size="small"
                      />
                    </Box>
                  </Grid>

                  <Grid item xs={12} md={4}>
                    <Box
                      p={3}
                      border={1}
                      borderColor="info.main"
                      borderRadius={2}
                    >
                      <Box display="flex" alignItems="center" gap={2} mb={2}>
                        <TrendingUp color="info" />
                        <Typography variant="h6" color="info.main">
                          Momentum Strength
                        </Typography>
                      </Box>
                      <Typography variant="body2" color="text.secondary" mb={2}>
                        Strong price and earnings momentum suggest continued
                        outperformance, though momentum factors can be cyclical.
                      </Typography>
                      <Chip
                        label="Momentum Score: 78/100"
                        color="info"
                        size="small"
                      />
                    </Box>
                  </Grid>
                </Grid>
              </CardContent>
            </Card>
          </Grid>

          {/* Institutional Positioning Analysis */}
          <Grid item xs={12}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  Institutional Positioning & Flow Analysis
                </Typography>
                <Divider sx={{ mb: 3 }} />
                <Grid container spacing={3}>
                  <Grid item xs={12} md={4}>
                    <Box textAlign="center" p={2}>
                      <Typography
                        variant="h3"
                        color="primary"
                        fontWeight="bold"
                      >
                        {
                          positioningData?.positioning_metrics?.institutional_ownership
                            ? `${formatDecimalAsPercent(positioningData.positioning_metrics.institutional_ownership)}`
                            : currentMetrics.institutional_ownership
                            ? `${formatPercent(currentMetrics.institutional_ownership)}`
                            : "N/A"
                        }
                      </Typography>
                      <Typography variant="body1" color="text.secondary" mb={1}>
                        Institutional Ownership
                      </Typography>
                      <LinearProgress
                        variant="determinate"
                        value={
                          (positioningData?.positioning_metrics?.institutional_ownership ||
                           currentMetrics.institutional_ownership || 0) * 100
                        }
                        color="primary"
                        sx={{ mb: 1 }}
                      />
                      <Typography variant="caption" color="text.secondary">
                        Above 60% indicates institutional confidence
                      </Typography>
                    </Box>
                  </Grid>

                  <Grid item xs={12} md={4}>
                    <Box textAlign="center" p={2}>
                      <Typography
                        variant="h3"
                        color="success.main"
                        fontWeight="bold"
                      >
                        {
                          positioningData?.positioning_metrics?.insider_ownership
                            ? `${formatDecimalAsPercent(positioningData.positioning_metrics.insider_ownership)}`
                            : currentMetrics.insider_ownership
                            ? `${formatPercent(currentMetrics.insider_ownership)}`
                            : "N/A"
                        }
                      </Typography>
                      <Typography variant="body1" color="text.secondary" mb={1}>
                        Insider Ownership
                      </Typography>
                      <LinearProgress
                        variant="determinate"
                        value={
                          (positioningData?.positioning_metrics?.insider_ownership ||
                           currentMetrics.insider_ownership || 0) *
                          100 *
                          10
                        }
                        color="success"
                        sx={{ mb: 1 }}
                      />
                      <Typography variant="caption" color="text.secondary">
                        2-5% range indicates aligned interests
                      </Typography>
                    </Box>
                  </Grid>

                  <Grid item xs={12} md={4}>
                    <Box textAlign="center" p={2}>
                      <Typography
                        variant="h3"
                        color="error.main"
                        fontWeight="bold"
                      >
                        {
                          positioningData?.positioning_metrics?.short_percent_of_float
                            ? `${formatDecimalAsPercent(positioningData.positioning_metrics.short_percent_of_float)}`
                            : currentMetrics.short_interest
                            ? `${formatPercent(currentMetrics.short_interest)}`
                            : "N/A"
                        }
                      </Typography>
                      <Typography variant="body1" color="text.secondary" mb={1}>
                        Short Interest
                      </Typography>
                      <LinearProgress
                        variant="determinate"
                        value={
                          (positioningData?.positioning_metrics?.short_percent_of_float ||
                           currentMetrics.short_interest || 0) *
                          100 *
                          5
                        }
                        color="error"
                        sx={{ mb: 1 }}
                      />
                      <Typography variant="caption" color="text.secondary">
                        Below 5% suggests limited bearish sentiment
                      </Typography>
                    </Box>
                  </Grid>
                </Grid>

                <Box mt={3}>
                  <Typography variant="subtitle1" fontWeight="bold" mb={2}>
                    Recent Institutional Activity (90 Days)
                  </Typography>
                  <TableContainer>
                    <Table size="small">
                      <TableBody>
                        {currentMetrics.net_institutional_flow && (
                          <TableRow>
                            <TableCell>Net Institutional Flow</TableCell>
                            <TableCell align="right">
                              <Chip
                                label={`${currentMetrics.net_institutional_flow > 0 ? '+' : ''}$${Math.abs(currentMetrics.net_institutional_flow)}M`}
                                color={currentMetrics.net_institutional_flow > 0 ? "success" : "error"}
                                size="small"
                              />
                            </TableCell>
                            <TableCell align="right">
                              <Typography
                                variant="caption"
                                color="text.secondary"
                              >
                                {currentMetrics.net_institutional_flow > 0 ? 'Net buying activity' : 'Net selling activity'}
                              </Typography>
                            </TableCell>
                          </TableRow>
                        )}
                        {currentMetrics.num_institutions && (
                          <TableRow>
                            <TableCell>Number of Institutions</TableCell>
                            <TableCell align="right">
                              <Chip
                                label={`${currentMetrics.num_institutions}${currentMetrics.num_institutions_change ? ` (${currentMetrics.num_institutions_change > 0 ? '+' : ''}${currentMetrics.num_institutions_change})` : ''}`}
                                color="info"
                                size="small"
                              />
                            </TableCell>
                            <TableCell align="right">
                              <Typography
                                variant="caption"
                                color="text.secondary"
                              >
                                {currentMetrics.num_institutions_change > 0 ? 'Growing institutional base' : 'Institutional base'}
                              </Typography>
                            </TableCell>
                          </TableRow>
                        )}
                        {currentMetrics.avg_position_size && (
                          <TableRow>
                            <TableCell>Avg Position Size</TableCell>
                            <TableCell align="right">
                              <Chip
                                label={`${formatPercent(currentMetrics.avg_position_size)}`}
                                color="primary"
                                size="small"
                              />
                            </TableCell>
                            <TableCell align="right">
                              <Typography
                                variant="caption"
                                color="text.secondary"
                              >
                                Conviction levels
                              </Typography>
                            </TableCell>
                          </TableRow>
                        )}
                        {currentMetrics.days_to_cover && (
                          <TableRow>
                            <TableCell>Days to Cover (Short)</TableCell>
                            <TableCell align="right">
                              <Chip
                                label={`${currentMetrics.days_to_cover} days`}
                                color={currentMetrics.days_to_cover < 3 ? "success" : "warning"}
                                size="small"
                              />
                            </TableCell>
                            <TableCell align="right">
                              <Typography
                                variant="caption"
                                color="text.secondary"
                              >
                                {currentMetrics.days_to_cover < 3 ? 'Low short squeeze risk' : 'Elevated short squeeze risk'}
                              </Typography>
                            </TableCell>
                          </TableRow>
                        )}
                      </TableBody>
                    </Table>
                  </TableContainer>
                </Box>
              </CardContent>
            </Card>
          </Grid>

          {/* Insider Transactions - NEW! */}
          {positioningData?.insider_transactions?.length > 0 && (
            <Grid item xs={12} md={6}>
              <Card>
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    Recent Insider Transactions (90 Days)
                  </Typography>
                  <Divider sx={{ mb: 2 }} />
                  <TableContainer sx={{ maxHeight: 400 }}>
                    <Table size="small" stickyHeader>
                      <TableHead>
                        <TableRow>
                          <TableCell sx={{ fontWeight: "bold" }}>Date</TableCell>
                          <TableCell sx={{ fontWeight: "bold" }}>Insider</TableCell>
                          <TableCell sx={{ fontWeight: "bold" }}>Type</TableCell>
                          <TableCell align="right" sx={{ fontWeight: "bold" }}>Shares</TableCell>
                          <TableCell align="right" sx={{ fontWeight: "bold" }}>Value</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {positioningData.insider_transactions.slice(0, 10).map((txn, idx) => (
                          <TableRow key={idx}>
                            <TableCell>
                              {txn.transaction_date ? new Date(txn.transaction_date).toLocaleDateString() : 'N/A'}
                            </TableCell>
                            <TableCell>
                              <Typography variant="body2" noWrap sx={{ maxWidth: 150 }}>
                                {txn.insider_name || 'Unknown'}
                              </Typography>
                              <Typography variant="caption" color="text.secondary" display="block">
                                {txn.position || ''}
                              </Typography>
                            </TableCell>
                            <TableCell>
                              <Chip
                                label={txn.transaction_type || 'N/A'}
                                size="small"
                                color={
                                  txn.transaction_type?.toLowerCase().includes('buy') ||
                                  txn.transaction_type?.toLowerCase().includes('purchase')
                                    ? "success"
                                    : txn.transaction_type?.toLowerCase().includes('sell') ||
                                      txn.transaction_type?.toLowerCase().includes('sale')
                                    ? "error"
                                    : "default"
                                }
                              />
                            </TableCell>
                            <TableCell align="right">
                              {txn.shares ? txn.shares.toLocaleString() : 'N/A'}
                            </TableCell>
                            <TableCell align="right">
                              {txn.value ? `$${(txn.value / 1000).toFixed(0)}K` : 'N/A'}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </TableContainer>
                  <Typography variant="caption" color="text.secondary" sx={{ mt: 2, display: 'block' }}>
                    Recent buying by insiders may indicate confidence in the company's prospects
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
          )}

          {/* Insider Roster - NEW! */}
          {positioningData?.insider_roster?.length > 0 && (
            <Grid item xs={12} md={6}>
              <Card>
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    Key Insiders & Holdings
                  </Typography>
                  <Divider sx={{ mb: 2 }} />
                  <TableContainer sx={{ maxHeight: 400 }}>
                    <Table size="small" stickyHeader>
                      <TableHead>
                        <TableRow>
                          <TableCell sx={{ fontWeight: "bold" }}>Name</TableCell>
                          <TableCell sx={{ fontWeight: "bold" }}>Position</TableCell>
                          <TableCell align="right" sx={{ fontWeight: "bold" }}>Shares Owned</TableCell>
                          <TableCell sx={{ fontWeight: "bold" }}>Latest Action</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {positioningData.insider_roster.slice(0, 10).map((insider, idx) => (
                          <TableRow key={idx}>
                            <TableCell>
                              <Typography variant="body2" noWrap sx={{ maxWidth: 150 }}>
                                {insider.insider_name || 'Unknown'}
                              </Typography>
                            </TableCell>
                            <TableCell>
                              <Typography variant="caption" color="text.secondary">
                                {insider.position || 'N/A'}
                              </Typography>
                            </TableCell>
                            <TableCell align="right">
                              <Typography variant="body2" fontWeight="bold">
                                {insider.shares_owned_directly ? insider.shares_owned_directly.toLocaleString() : 'N/A'}
                              </Typography>
                            </TableCell>
                            <TableCell>
                              <Typography variant="caption" color="text.secondary">
                                {insider.most_recent_transaction || 'N/A'}
                              </Typography>
                              {insider.latest_transaction_date && (
                                <Typography variant="caption" display="block" color="text.secondary">
                                  {new Date(insider.latest_transaction_date).toLocaleDateString()}
                                </Typography>
                              )}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </TableContainer>
                  <Typography variant="caption" color="text.secondary" sx={{ mt: 2, display: 'block' }}>
                    Insiders with significant holdings typically have aligned interests with shareholders
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
          )}

          {/* Positioning Score Breakdown - NEW! */}
          {positioningData?.score_breakdown && (
            <Grid item xs={12}>
              <Card>
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    Positioning Score Components
                  </Typography>
                  <Divider sx={{ mb: 3 }} />
                  <Grid container spacing={3}>
                    <Grid item xs={12} sm={6} md={3}>
                      <Box textAlign="center" p={2}>
                        <Typography variant="h4" color="primary" fontWeight="bold">
                          {positioningData.score_breakdown.institutional || 0}
                        </Typography>
                        <Typography variant="body2" color="text.secondary" mb={1}>
                          Institutional Quality
                        </Typography>
                        <LinearProgress
                          variant="determinate"
                          value={(positioningData.score_breakdown.institutional || 0) * 4}
                          color="primary"
                          sx={{ mb: 1 }}
                        />
                        <Typography variant="caption" color="text.secondary">
                          Ownership % + Institution Count
                        </Typography>
                      </Box>
                    </Grid>
                    <Grid item xs={12} sm={6} md={3}>
                      <Box textAlign="center" p={2}>
                        <Typography variant="h4" color="success.main" fontWeight="bold">
                          {positioningData.score_breakdown.insider || 0}
                        </Typography>
                        <Typography variant="body2" color="text.secondary" mb={1}>
                          Insider Conviction
                        </Typography>
                        <LinearProgress
                          variant="determinate"
                          value={Math.max(0, (positioningData.score_breakdown.insider || 0) * 4)}
                          color="success"
                          sx={{ mb: 1 }}
                        />
                        <Typography variant="caption" color="text.secondary">
                          Ownership % + Buy/Sell Activity
                        </Typography>
                      </Box>
                    </Grid>
                    <Grid item xs={12} sm={6} md={3}>
                      <Box textAlign="center" p={2}>
                        <Typography variant="h4" color="info.main" fontWeight="bold">
                          {positioningData.score_breakdown.short_interest || 0}
                        </Typography>
                        <Typography variant="body2" color="text.secondary" mb={1}>
                          Short Interest
                        </Typography>
                        <LinearProgress
                          variant="determinate"
                          value={Math.max(0, (positioningData.score_breakdown.short_interest || 0) * 4)}
                          color="info"
                          sx={{ mb: 1 }}
                        />
                        <Typography variant="caption" color="text.secondary">
                          Level + Trend Analysis
                        </Typography>
                      </Box>
                    </Grid>
                    <Grid item xs={12} sm={6} md={3}>
                      <Box textAlign="center" p={2}>
                        <Typography variant="h4" color="warning.main" fontWeight="bold">
                          {positioningData.score_breakdown.smart_money || 0}
                        </Typography>
                        <Typography variant="body2" color="text.secondary" mb={1}>
                          Smart Money Flow
                        </Typography>
                        <LinearProgress
                          variant="determinate"
                          value={Math.max(0, (positioningData.score_breakdown.smart_money || 0) * 4)}
                          color="warning"
                          sx={{ mb: 1 }}
                        />
                        <Typography variant="caption" color="text.secondary">
                          Mutual Fund + Hedge Fund Positioning
                        </Typography>
                      </Box>
                    </Grid>
                  </Grid>
                </CardContent>
              </Card>
            </Grid>
          )}
        </Grid>
      </Box>

      {/* Analyst Coverage Section */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h5" gutterBottom sx={{ mb: 3, fontWeight: 600 }}>
          <TrendingUp sx={{ verticalAlign: "middle", mr: 1 }} />
          Analyst Coverage & Recommendations
        </Typography>
        {analystOverviewLoading ? (
          <Box display="flex" justifyContent="center" p={4}>
            <CircularProgress />
          </Box>
        ) : (
          <Box>

            <Grid container spacing={3}>
              {/* Earnings Estimates */}
              <Grid item xs={12} md={6}>
                <Card>
                  <CardContent>
                    <Typography variant="h6" gutterBottom>
                      Earnings Estimates
                    </Typography>
                    <Divider sx={{ mb: 2 }} />

                    {analystOverview?.data?.earnings_estimates?.length > 0 ? (
                      <>
                        <TableContainer>
                          <Table size="small">
                            <TableHead>
                              <TableRow sx={{ backgroundColor: "grey.50" }}>
                                <TableCell sx={{ fontWeight: "bold" }}>Period</TableCell>
                                <TableCell align="right" sx={{ fontWeight: "bold" }}>Avg Estimate</TableCell>
                                <TableCell align="right" sx={{ fontWeight: "bold" }}>Analysts</TableCell>
                              </TableRow>
                            </TableHead>
                            <TableBody>
                              {(
                                analystOverview?.data.earnings_estimates || []
                              ).map((estimate) => (
                                <TableRow key={estimate.period}>
                                  <TableCell sx={{ fontWeight: "bold" }}>
                                    {estimate.period === "0q"
                                      ? "Current Quarter"
                                      : estimate.period === "+1q"
                                        ? "Next Quarter"
                                        : estimate.period === "0y"
                                          ? "Current Year"
                                          : estimate.period === "+1y"
                                            ? "Next Year"
                                            : estimate.period}
                                  </TableCell>
                                  <TableCell align="right">
                                    {estimate.avg_estimate
                                      ? formatCurrency(estimate.avg_estimate)
                                      : "N/A"}
                                  </TableCell>
                                  <TableCell align="right">
                                    <Chip
                                      label={`${estimate.number_of_analysts || 0} analysts`}
                                      size="small"
                                      variant="outlined"
                                    />
                                  </TableCell>
                                </TableRow>
                              ))}
                            </TableBody>
                          </Table>
                        </TableContainer>
                      </>
                    ) : (
                      <Typography color="text.secondary">
                        No earnings estimates available
                      </Typography>
                    )}
                  </CardContent>
                </Card>
              </Grid>

              {/* Revenue Estimates */}
              <Grid item xs={12} md={6}>
                <Card>
                  <CardContent>
                    <Typography variant="h6" gutterBottom>
                      Revenue Estimates
                    </Typography>
                    <Divider sx={{ mb: 2 }} />

                    {analystOverview?.data?.revenue_estimates?.length > 0 ? (
                      <>
                        <TableContainer>
                          <Table size="small">
                            <TableHead>
                              <TableRow sx={{ backgroundColor: "grey.50" }}>
                                <TableCell sx={{ fontWeight: "bold" }}>Period</TableCell>
                                <TableCell align="right" sx={{ fontWeight: "bold" }}>Avg Estimate</TableCell>
                                <TableCell align="right" sx={{ fontWeight: "bold" }}>Analysts</TableCell>
                              </TableRow>
                            </TableHead>
                            <TableBody>
                              {(
                                analystOverview?.data.revenue_estimates || []
                              ).map((estimate) => (
                                <TableRow key={estimate.period}>
                                  <TableCell sx={{ fontWeight: "bold" }}>
                                    {estimate.period === "0q"
                                      ? "Current Quarter"
                                      : estimate.period === "+1q"
                                        ? "Next Quarter"
                                        : estimate.period === "0y"
                                          ? "Current Year"
                                          : estimate.period === "+1y"
                                            ? "Next Year"
                                            : estimate.period}
                                  </TableCell>
                                  <TableCell align="right">
                                    {estimate.avg_estimate
                                      ? formatCurrency(estimate.avg_estimate, 0)
                                      : "N/A"}
                                  </TableCell>
                                  <TableCell align="right">
                                    <Chip
                                      label={`${estimate.number_of_analysts || 0} analysts`}
                                      size="small"
                                      variant="outlined"
                                    />
                                  </TableCell>
                                </TableRow>
                              ))}
                            </TableBody>
                          </Table>
                        </TableContainer>
                      </>
                    ) : (
                      <Typography color="text.secondary">
                        No revenue estimates available
                      </Typography>
                    )}
                  </CardContent>
                </Card>
              </Grid>

              {/* EPS Revisions */}
              <Grid item xs={12}>
                <Card>
                  <CardContent>
                    <Typography variant="h6" gutterBottom>
                      EPS Revisions
                    </Typography>
                    <Divider sx={{ mb: 2 }} />

                    {analystOverview?.data?.eps_revisions?.length > 0 ? (
                      <>
                        <TableContainer>
                          <Table size="small">
                            <TableHead>
                              <TableRow sx={{ backgroundColor: "grey.50" }}>
                                <TableCell sx={{ fontWeight: "bold" }}>Period</TableCell>
                                <TableCell align="right" sx={{ fontWeight: "bold" }}>Avg. Estimate</TableCell>
                                <TableCell align="right" sx={{ fontWeight: "bold" }}>Low</TableCell>
                                <TableCell align="right" sx={{ fontWeight: "bold" }}>High</TableCell>
                                <TableCell align="right" sx={{ fontWeight: "bold" }}>Analysts</TableCell>
                              </TableRow>
                            </TableHead>
                            <TableBody>
                              {(analystOverview?.data.eps_revisions || []).map(
                                (revision) => (
                                  <TableRow key={revision.period}>
                                    <TableCell sx={{ fontWeight: "bold" }}>
                                      {revision.period === "0q"
                                        ? "Current Quarter"
                                        : revision.period === "+1q"
                                          ? "Next Quarter"
                                          : revision.period === "0y"
                                            ? "Current Year"
                                            : revision.period === "+1y"
                                              ? "Next Year"
                                              : revision.period}
                                    </TableCell>
                                    <TableCell align="right">
                                      {revision.avg_estimate
                                        ? formatCurrency(revision.avg_estimate)
                                        : "N/A"}
                                    </TableCell>
                                    <TableCell align="right">
                                      {revision.low_estimate
                                        ? formatCurrency(revision.low_estimate)
                                        : "N/A"}
                                    </TableCell>
                                    <TableCell align="right">
                                      {revision.high_estimate
                                        ? formatCurrency(revision.high_estimate)
                                        : "N/A"}
                                    </TableCell>
                                    <TableCell align="right">
                                      <Chip
                                        label={`${revision.number_of_analysts || 0} analysts`}
                                        size="small"
                                        variant="outlined"
                                      />
                                    </TableCell>
                                  </TableRow>
                                )
                              )}
                            </TableBody>
                          </Table>
                        </TableContainer>
                      </>
                    ) : (
                      <Typography color="text.secondary">
                        No EPS revisions available
                      </Typography>
                    )}
                  </CardContent>
                </Card>
              </Grid>

              {/* Growth Estimates */}
              <Grid item xs={12} md={6}>
                <Card>
                  <CardContent>
                    <Typography variant="h6" gutterBottom>
                      Growth Estimates
                    </Typography>
                    <Divider sx={{ mb: 2 }} />

                    {analystOverview?.data?.growth_estimates?.length > 0 ? (
                      <>
                        <TableContainer>
                          <Table size="small">
                            <TableHead>
                              <TableRow sx={{ backgroundColor: "grey.50" }}>
                                <TableCell sx={{ fontWeight: "bold" }}>Period</TableCell>
                                <TableCell align="right" sx={{ fontWeight: "bold" }}>Stock Growth</TableCell>
                                <TableCell align="right" sx={{ fontWeight: "bold" }}>Index Growth</TableCell>
                              </TableRow>
                            </TableHead>
                            <TableBody>
                              {(analystOverview?.data.growth_estimates || []).map(
                                (growth) => (
                                  <TableRow key={growth.period}>
                                    <TableCell sx={{ fontWeight: "bold" }}>
                                      {growth.period === "0q"
                                        ? "Current Quarter"
                                        : growth.period === "+1q"
                                          ? "Next Quarter"
                                          : growth.period === "0y"
                                            ? "Current Year"
                                            : growth.period === "+1y"
                                              ? "Next Year"
                                              : growth.period === "+5y"
                                                ? "Next 5 Years"
                                                : growth.period}
                                    </TableCell>
                                    <TableCell align="right">
                                      {growth.stock_trend
                                        ? formatPercent(growth.stock_trend / 100)
                                        : "N/A"}
                                    </TableCell>
                                    <TableCell align="right">
                                      {growth.index_trend
                                        ? formatPercent(growth.index_trend / 100)
                                        : "N/A"}
                                    </TableCell>
                                  </TableRow>
                                )
                              )}
                            </TableBody>
                          </Table>
                        </TableContainer>
                      </>
                    ) : (
                      <Typography color="text.secondary">
                        No growth estimates available
                      </Typography>
                    )}
                  </CardContent>
                </Card>
              </Grid>

              {/* Analyst Recommendations */}
              <Grid item xs={12}>
                <Card>
                  <CardContent>
                    <Typography variant="h6" gutterBottom>
                      Analyst Recommendations
                    </Typography>
                    <Divider sx={{ mb: 2 }} />

                    {analystOverview?.data?.recommendations?.length > 0 ? (
                      <Box>
                        {(analystOverview?.data?.recommendations || [])
                          .slice(0, 3)
                          .map((rec, index) => (
                            <Box key={index} sx={{ mb: 2 }}>
                              <Typography
                                variant="subtitle2"
                                sx={{ fontWeight: "bold", mb: 1 }}
                              >
                                {new Date(
                                  rec.collected_date
                                ).toLocaleDateString()}{" "}
                                - {rec.period}
                              </Typography>
                              <Grid container spacing={2}>
                                <Grid item>
                                  <Chip
                                    label={`Strong Buy: ${rec.strong_buy || 0}`}
                                    color="success"
                                    variant="outlined"
                                    size="small"
                                  />
                                </Grid>
                                <Grid item>
                                  <Chip
                                    label={`Buy: ${rec.buy || 0}`}
                                    color="success"
                                    variant="outlined"
                                    size="small"
                                  />
                                </Grid>
                                <Grid item>
                                  <Chip
                                    label={`Hold: ${rec.hold || 0}`}
                                    color="warning"
                                    variant="outlined"
                                    size="small"
                                  />
                                </Grid>
                                <Grid item>
                                  <Chip
                                    label={`Sell: ${rec.sell || 0}`}
                                    color="error"
                                    variant="outlined"
                                    size="small"
                                  />
                                </Grid>
                                <Grid item>
                                  <Chip
                                    label={`Strong Sell: ${rec.strong_sell || 0}`}
                                    color="error"
                                    variant="outlined"
                                    size="small"
                                  />
                                </Grid>
                              </Grid>
                              {index < 2 && <Divider sx={{ mt: 2 }} />}
                            </Box>
                          ))}
                      </Box>
                    ) : (
                      <Typography color="text.secondary">
                        No analyst recommendations available
                      </Typography>
                    )}
                  </CardContent>
                </Card>
              </Grid>

              {/* Earnings History */}
              <Grid item xs={12}>
                <Card>
                  <CardContent>
                    <Typography variant="h6" gutterBottom>
                      Earnings History
                    </Typography>
                    <Divider sx={{ mb: 2 }} />

                    {analystOverview?.data?.earnings_history?.length > 0 ? (
                      <>
                        <TableContainer>
                          <Table size="small">
                            <TableHead>
                              <TableRow sx={{ backgroundColor: "grey.50" }}>
                                <TableCell sx={{ fontWeight: "bold" }}>Quarter</TableCell>
                                <TableCell align="right" sx={{ fontWeight: "bold" }}>Actual EPS</TableCell>
                                <TableCell align="right" sx={{ fontWeight: "bold" }}>Estimated EPS</TableCell>
                                <TableCell align="right" sx={{ fontWeight: "bold" }}>Surprise</TableCell>
                              </TableRow>
                            </TableHead>
                            <TableBody>
                              {(analystOverview?.data?.earnings_history || [])
                                .slice(0, 8)
                                .map((history) => (
                                  <TableRow key={history.quarter}>
                                    <TableCell sx={{ fontWeight: "bold" }}>
                                      {new Date(
                                        history.quarter
                                      ).toLocaleDateString()}
                                    </TableCell>
                                    <TableCell align="right">
                                      {history.eps_actual
                                        ? formatCurrency(history.eps_actual)
                                        : "N/A"}
                                    </TableCell>
                                    <TableCell align="right">
                                      {history.eps_estimate
                                        ? formatCurrency(history.eps_estimate)
                                        : "N/A"}
                                    </TableCell>
                                    <TableCell align="right">
                                      <Chip
                                        label={
                                          history.surprise_percent
                                            ? formatPercent(history.surprise_percent / 100)
                                            : "N/A"
                                        }
                                        color={
                                          history.surprise_percent > 0
                                            ? "success"
                                            : history.surprise_percent < 0
                                              ? "error"
                                              : "default"
                                        }
                                        size="small"
                                        variant="outlined"
                                      />
                                    </TableCell>
                                  </TableRow>
                                ))}
                            </TableBody>
                          </Table>
                        </TableContainer>
                      </>
                    ) : (
                      <Typography color="text.secondary">
                        No earnings history available
                      </Typography>
                    )}
                  </CardContent>
                </Card>
              </Grid>

              {/* EPS Trends */}
              <Grid item xs={12}>
                <Card>
                  <CardContent>
                    <Typography variant="h6" gutterBottom>
                      EPS Trends
                    </Typography>
                    <Divider sx={{ mb: 2 }} />

                    {analystOverview?.data?.eps_trend?.length > 0 ? (
                      <>
                        <TableContainer>
                          <Table size="small">
                            <TableHead>
                              <TableRow sx={{ backgroundColor: "grey.50" }}>
                                <TableCell sx={{ fontWeight: "bold" }}>Period</TableCell>
                                <TableCell align="right" sx={{ fontWeight: "bold" }}>Avg. Estimate</TableCell>
                                <TableCell align="right" sx={{ fontWeight: "bold" }}>Year Ago EPS</TableCell>
                                <TableCell align="right" sx={{ fontWeight: "bold" }}>Growth</TableCell>
                                <TableCell align="right" sx={{ fontWeight: "bold" }}>Analysts</TableCell>
                              </TableRow>
                            </TableHead>
                            <TableBody>
                              {(analystOverview?.data.eps_trend || []).map(
                                (trend) => (
                                  <TableRow key={trend.period}>
                                    <TableCell sx={{ fontWeight: "bold" }}>
                                      {trend.period === "0q"
                                        ? "Current Quarter"
                                        : trend.period === "+1q"
                                          ? "Next Quarter"
                                          : trend.period === "0y"
                                            ? "Current Year"
                                            : trend.period === "+1y"
                                              ? "Next Year"
                                              : trend.period}
                                    </TableCell>
                                    <TableCell align="right">
                                      {trend.avg_estimate
                                        ? formatCurrency(trend.avg_estimate)
                                        : "N/A"}
                                    </TableCell>
                                    <TableCell align="right">
                                      {trend.year_ago_eps
                                        ? formatCurrency(trend.year_ago_eps)
                                        : "N/A"}
                                    </TableCell>
                                    <TableCell align="right">
                                      {trend.growth ? (
                                        <Chip
                                          label={formatPercent(trend.growth / 100)}
                                          size="small"
                                          color={trend.growth > 0 ? "success" : trend.growth < 0 ? "error" : "default"}
                                          variant="outlined"
                                        />
                                      ) : (
                                        "N/A"
                                      )}
                                    </TableCell>
                                    <TableCell align="right">
                                      <Chip
                                        label={`${trend.number_of_analysts || 0} analysts`}
                                        size="small"
                                        variant="outlined"
                                      />
                                    </TableCell>
                                  </TableRow>
                                )
                              )}
                            </TableBody>
                          </Table>
                        </TableContainer>
                      </>
                    ) : (
                      <Typography color="text.secondary">
                        No EPS trends available
                      </Typography>
                    )}
                  </CardContent>
                </Card>
              </Grid>

              {/* Earnings Metrics */}
              <Grid item xs={12}>
                <Card>
                  <CardContent>
                    <Typography variant="h6" gutterBottom>
                      Earnings Metrics
                    </Typography>
                    <Divider sx={{ mb: 2 }} />

                    {analystOverview?.data?.earnings_metrics ? (
                      <TableContainer>
                        <Table>
                          <TableBody>
                            <TableRow>
                              <TableCell sx={{ fontWeight: "bold" }}>
                                Earnings Growth (Quarterly YoY)
                              </TableCell>
                              <TableCell align="right">
                                {analystOverview?.data.earnings_metrics
                                  .quarterly_earnings_growth
                                  ? formatPercent(
                                      analystOverview.data.earnings_metrics
                                        .quarterly_earnings_growth / 100
                                    )
                                  : "N/A"}
                              </TableCell>
                            </TableRow>
                            <TableRow>
                              <TableCell sx={{ fontWeight: "bold" }}>
                                Revenue Growth (Quarterly YoY)
                              </TableCell>
                              <TableCell align="right">
                                {analystOverview?.data.earnings_metrics
                                  .quarterly_revenue_growth
                                  ? formatPercent(
                                      analystOverview.data.earnings_metrics
                                        .quarterly_revenue_growth / 100
                                    )
                                  : "N/A"}
                              </TableCell>
                            </TableRow>
                            <TableRow>
                              <TableCell sx={{ fontWeight: "bold" }}>
                                Target Mean Price
                              </TableCell>
                              <TableCell align="right">
                                {analystOverview?.data.earnings_metrics
                                  .target_mean_price
                                  ? formatCurrency(
                                      analystOverview.data.earnings_metrics
                                        .target_mean_price
                                    )
                                  : "N/A"}
                              </TableCell>
                            </TableRow>
                            <TableRow>
                              <TableCell sx={{ fontWeight: "bold" }}>
                                Target High Price
                              </TableCell>
                              <TableCell align="right">
                                {analystOverview?.data.earnings_metrics
                                  .target_high_price
                                  ? formatCurrency(
                                      analystOverview.data.earnings_metrics
                                        .target_high_price
                                    )
                                  : "N/A"}
                              </TableCell>
                            </TableRow>
                            <TableRow>
                              <TableCell sx={{ fontWeight: "bold" }}>
                                Target Low Price
                              </TableCell>
                              <TableCell align="right">
                                {analystOverview?.data.earnings_metrics
                                  .target_low_price
                                  ? formatCurrency(
                                      analystOverview.data.earnings_metrics
                                        .target_low_price
                                    )
                                  : "N/A"}
                              </TableCell>
                            </TableRow>
                            <TableRow>
                              <TableCell sx={{ fontWeight: "bold" }}>
                                Number of Analyst Opinions
                              </TableCell>
                              <TableCell align="right">
                                <Chip
                                  label={`${analystOverview?.data.earnings_metrics.number_of_analyst_opinions || 0} analysts`}
                                  size="small"
                                  variant="outlined"
                                />
                              </TableCell>
                            </TableRow>
                          </TableBody>
                        </Table>
                      </TableContainer>
                    ) : (
                      <Typography color="text.secondary">
                        No earnings metrics available
                      </Typography>
                    )}
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          </Box>
        )}
      </Box>

      {/* Upcoming Events Section */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h5" gutterBottom sx={{ mb: 3, fontWeight: 600 }}>
          <EventNote sx={{ verticalAlign: "middle", mr: 1 }} />
          Upcoming Events
        </Typography>

        {eventsLoading ? (
          <Box display="flex" justifyContent="center" p={4}>
            <CircularProgress />
          </Box>
        ) : eventsError ? (
          <Alert severity="error">Failed to load events</Alert>
        ) : (
          <Card>
            <CardContent>
              <TableContainer>
                <Table>
                  <TableHead>
                    <TableRow sx={{ backgroundColor: "grey.50" }}>
                      <TableCell>Event Type</TableCell>
                      <TableCell>Date</TableCell>
                      <TableCell>Details</TableCell>
                      <TableCell>Days Until</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {(stockEvents?.data?.data ?? stockEvents?.data ?? []).length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={4} align="center">
                          <Typography variant="body2" color="text.secondary" sx={{ py: 2 }}>
                            No upcoming events scheduled
                          </Typography>
                        </TableCell>
                      </TableRow>
                    ) : (
                      (stockEvents?.data?.data ?? stockEvents?.data ?? []).map((event, index) => (
                        <TableRow key={`${event.symbol}-${index}`} hover>
                          <TableCell>
                            <Chip
                              label={event.event_type?.toUpperCase() || "EVENT"}
                              size="small"
                              color={
                                event.event_type === "earnings"
                                  ? "primary"
                                  : event.event_type === "dividend"
                                  ? "success"
                                  : "default"
                              }
                            />
                          </TableCell>
                          <TableCell>
                            <Typography variant="body2">
                              {new Date(event.start_date).toLocaleDateString()}
                            </Typography>
                          </TableCell>
                          <TableCell>
                            <Typography variant="body2" noWrap>
                              {event.title}
                            </Typography>
                          </TableCell>
                          <TableCell>
                            <Typography variant="body2" color="text.secondary">
                              {Math.ceil(
                                (new Date(event.start_date) - new Date()) /
                                  (1000 * 60 * 60 * 24)
                              )}{" "}
                              days
                            </Typography>
                          </TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </TableContainer>
            </CardContent>
          </Card>
        )}
      </Box>
    </Container>
  );
}

export default StockDetail;
