import React, { useState, useEffect, useMemo } from "react";
import { useAuth } from "../contexts/AuthContext";
import { useNavigate } from "react-router-dom";
import {
  Box,
  Container,
  Typography,
  Grid,
  Card,
  CardContent,
  CardHeader,
  Tabs,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Chip,
  CircularProgress,
  Alert,
  Button,
  TextField,
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  TablePagination,
  TableSortLabel,
  InputAdornment,
} from "@mui/material";
import {
  TrendingUp,
  TrendingDown,
  History,
  Download,
  Upload,
  Refresh,
  FilterList,
  Search,
  Analytics,
  ShowChart,
  Timeline,
  Assessment,
  MonetizationOn,
  SwapHoriz,
  Insights,
} from "@mui/icons-material";
import {
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  ResponsiveContainer,
  Bar,
  ComposedChart,
} from "recharts";
import { DatePicker } from "@mui/x-date-pickers/DatePicker";
import { LocalizationProvider } from "@mui/x-date-pickers/LocalizationProvider";
import { AdapterDateFns } from "@mui/x-date-pickers/AdapterDateFns";

const TradeHistory = () => {
  const { user, isAuthenticated } = useAuth();
  const navigate = useNavigate();

  // State management
  const [trades, setTrades] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [tabValue, setTabValue] = useState(0);
  const [sortBy, setSortBy] = useState("date");
  const [sortOrder, setSortOrder] = useState("desc");
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);
  const [searchTerm, setSearchTerm] = useState("");
  const [dateFilter, setDateFilter] = useState({ start: null, end: null });
  const [typeFilter, setTypeFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [showAdvancedFilters, setShowAdvancedFilters] = useState(false);
  const [selectedTrade, setSelectedTrade] = useState(null);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [importDialogOpen, setImportDialogOpen] = useState(false);
  const [analytics, setAnalytics] = useState(null);
  const [insights, setInsights] = useState([]);
  const [performance, setPerformance] = useState(null);
  const [chartData, setChartData] = useState([]);

  // Fetch trade data
  useEffect(() => {
    if (!isAuthenticated) {
      navigate("/");
      return;
    }
    fetchTradeHistory();
    fetchAnalytics();
    fetchInsights();
    fetchPerformance();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    isAuthenticated,
    navigate,
    page,
    rowsPerPage,
    sortBy,
    sortOrder,
    typeFilter,
    statusFilter,
    dateFilter,
  ]);

  const fetchTradeHistory = async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams({
        page: page + 1,
        limit: rowsPerPage,
        sortBy,
        sortOrder,
        ...(typeFilter !== "all" && { type: typeFilter }),
        ...(statusFilter !== "all" && { status: statusFilter }),
        ...(dateFilter.start && { startDate: dateFilter.start.toISOString() }),
        ...(dateFilter.end && { endDate: dateFilter.end.toISOString() }),
        ...(searchTerm && { search: searchTerm }),
      });

      const response = await fetch(`/api/trades/history?${params}`, {
        headers: {
          Authorization: `Bearer ${user.token}`,
        },
      });

      if (!response.ok) throw new Error("Failed to fetch trade history");

      const data = await response.json();
      setTrades(data.trades || []);

      // Generate chart data from trades
      const chartData =
        data.trades?.map((trade) => ({
          date: new Date(trade.executedAt).toLocaleDateString(),
          pnl: trade.realizedPnl || 0,
          value: trade.value || 0,
          cumulative: trade.cumulativePnl || 0,
        })) || [];
      setChartData(chartData);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const fetchAnalytics = async () => {
    try {
      const response = await fetch("/api/trades/analytics/overview", {
        headers: { Authorization: `Bearer ${user.token}` },
      });
      if (response.ok) {
        const data = await response.json();
        setAnalytics(data);
      }
    } catch (err) {
      console.error("Failed to fetch analytics:", err);
    }
  };

  const fetchInsights = async () => {
    try {
      const response = await fetch("/api/trades/insights", {
        headers: { Authorization: `Bearer ${user.token}` },
      });
      if (response.ok) {
        const data = await response.json();
        setInsights(data.insights || []);
      }
    } catch (err) {
      console.error("Failed to fetch insights:", err);
    }
  };

  const fetchPerformance = async () => {
    try {
      const response = await fetch("/api/trades/performance", {
        headers: { Authorization: `Bearer ${user.token}` },
      });
      if (response.ok) {
        const data = await response.json();
        setPerformance(data);
      }
    } catch (err) {
      console.error("Failed to fetch performance:", err);
    }
  };

  const handleImportTrades = async () => {
    try {
      setLoading(true);
      const response = await fetch("/api/trades/import/alpaca", {
        method: "POST",
        headers: { Authorization: `Bearer ${user.token}` },
      });

      if (response.ok) {
        await fetchTradeHistory();
        setImportDialogOpen(false);
      } else {
        throw new Error("Failed to import trades");
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleExportTrades = async (format = "csv") => {
    try {
      const response = await fetch(`/api/trades/export?format=${format}`, {
        headers: { Authorization: `Bearer ${user.token}` },
      });

      if (response.ok) {
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `trades_${new Date().toISOString().split("T")[0]}.${format}`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
      }
    } catch (err) {
      setError(err.message);
    }
  };

  const getTradeTypeColor = (type) => {
    switch (type?.toLowerCase()) {
      case "buy":
        return "success";
      case "sell":
        return "error";
      case "dividend":
        return "info";
      case "split":
        return "warning";
      default:
        return "default";
    }
  };

  const getStatusColor = (status) => {
    switch (status?.toLowerCase()) {
      case "filled":
        return "success";
      case "pending":
        return "warning";
      case "cancelled":
        return "error";
      case "partial":
        return "info";
      default:
        return "default";
    }
  };

  const formatCurrency = (amount) => {
    if (amount === null || amount === undefined) return "$0.00";
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
    }).format(amount);
  };

  const formatPercent = (value) => {
    if (value === null || value === undefined) return "0.00%";
    return `${(value * 100).toFixed(2)}%`;
  };

  // Filtered and sorted trades
  const filteredTrades = useMemo(() => {
    let filtered = trades.filter((trade) => {
      const matchesSearch =
        !searchTerm ||
        trade.symbol?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        trade.type?.toLowerCase().includes(searchTerm.toLowerCase());

      const matchesType = typeFilter === "all" || trade.type === typeFilter;
      const matchesStatus =
        statusFilter === "all" || trade.status === statusFilter;

      return matchesSearch && matchesType && matchesStatus;
    });

    // Sort trades
    filtered.sort((a, b) => {
      const aVal = a[sortBy];
      const bVal = b[sortBy];

      if (sortOrder === "asc") {
        return aVal > bVal ? 1 : -1;
      } else {
        return aVal < bVal ? 1 : -1;
      }
    });

    return filtered;
  }, [trades, searchTerm, typeFilter, statusFilter, sortBy, sortOrder]);

  const paginatedTrades = filteredTrades.slice(
    page * rowsPerPage,
    page * rowsPerPage + rowsPerPage
  );

  const TabPanel = ({ children, value, index, ...other }) => (
    <div role="tabpanel" hidden={value !== index} {...other}>
      {value === index && <Box sx={{ p: 3 }}>{children}</Box>}
    </div>
  );

  if (!isAuthenticated) {
    return (
      <Container maxWidth="md" sx={{ mt: 4 }}>
        <Alert severity="warning">
          Please log in to view your trade history.
        </Alert>
      </Container>
    );
  }

  return (
    <LocalizationProvider dateAdapter={AdapterDateFns}>
      <Container maxWidth="xl" sx={{ py: 3 }}>
        {/* Header */}
        <Box sx={{ mb: 3 }}>
          <Typography
            variant="h4"
            component="h1"
            gutterBottom
            sx={{ fontWeight: "bold" }}
          >
            Trade History
          </Typography>
          <Typography variant="subtitle1" color="text.secondary">
            Complete overview of your trading activity and performance
          </Typography>
        </Box>

        {error && (
          <Alert severity="error" sx={{ mb: 3 }} onClose={() => setError(null)}>
            {error}
          </Alert>
        )}

        {/* Quick Stats Cards */}
        {analytics && (
          <Grid container spacing={3} sx={{ mb: 3 }}>
            <Grid item xs={12} sm={6} md={3}>
              <Card>
                <CardContent>
                  <Box sx={{ display: "flex", alignItems: "center" }}>
                    <SwapHoriz color="primary" sx={{ mr: 1 }} />
                    <Typography variant="h6">Total Trades</Typography>
                  </Box>
                  <Typography variant="h4" sx={{ mt: 1 }}>
                    {analytics.totalTrades || 0}
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Card>
                <CardContent>
                  <Box sx={{ display: "flex", alignItems: "center" }}>
                    <MonetizationOn color="success" sx={{ mr: 1 }} />
                    <Typography variant="h6">Total P&L</Typography>
                  </Box>
                  <Typography
                    variant="h4"
                    sx={{
                      mt: 1,
                      color:
                        analytics.totalPnl >= 0 ? "success.main" : "error.main",
                    }}
                  >
                    {formatCurrency(analytics.totalPnl)}
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Card>
                <CardContent>
                  <Box sx={{ display: "flex", alignItems: "center" }}>
                    <Assessment color="info" sx={{ mr: 1 }} />
                    <Typography variant="h6">Win Rate</Typography>
                  </Box>
                  <Typography variant="h4" sx={{ mt: 1 }}>
                    {formatPercent(analytics.winRate)}
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Card>
                <CardContent>
                  <Box sx={{ display: "flex", alignItems: "center" }}>
                    <Timeline color="secondary" sx={{ mr: 1 }} />
                    <Typography variant="h6">Avg Hold Time</Typography>
                  </Box>
                  <Typography variant="h4" sx={{ mt: 1 }}>
                    {analytics.avgHoldTime || "N/A"}
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        )}

        {/* Action Buttons */}
        <Box sx={{ mb: 3, display: "flex", gap: 2, flexWrap: "wrap" }}>
          <Button
            variant="outlined"
            startIcon={<Upload />}
            onClick={() => setImportDialogOpen(true)}
          >
            Import Trades
          </Button>
          <Button
            variant="outlined"
            startIcon={<Download />}
            onClick={() => handleExportTrades("csv")}
          >
            Export CSV
          </Button>
          <Button
            variant="outlined"
            startIcon={<Download />}
            onClick={() => handleExportTrades("json")}
          >
            Export JSON
          </Button>
          <Button
            variant="outlined"
            startIcon={<Refresh />}
            onClick={fetchTradeHistory}
          >
            Refresh
          </Button>
        </Box>

        {/* Tabs */}
        <Box sx={{ borderBottom: 1, borderColor: "divider", mb: 3 }}>
          <Tabs
            value={tabValue}
            onChange={(e, newValue) => setTabValue(newValue)}
          >
            <Tab icon={<History />} label="Trade List" />
            <Tab icon={<ShowChart />} label="Performance Chart" />
            <Tab icon={<Analytics />} label="Analytics" />
            <Tab icon={<Insights />} label="AI Insights" />
          </Tabs>
        </Box>

        {/* Tab Content */}
        <TabPanel value={tabValue} index={0}>
          {/* Filters */}
          <Card sx={{ mb: 3 }}>
            <CardContent>
              <Box
                sx={{
                  display: "flex",
                  gap: 2,
                  flexWrap: "wrap",
                  alignItems: "center",
                }}
              >
                <TextField
                  size="small"
                  placeholder="Search by symbol or type..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  InputProps={{
                    startAdornment: (
                      <InputAdornment position="start">
                        <Search />
                      </InputAdornment>
                    ),
                  }}
                  sx={{ minWidth: 200 }}
                />

                <FormControl size="small" sx={{ minWidth: 120 }}>
                  <InputLabel>Type</InputLabel>
                  <Select
                    value={typeFilter}
                    label="Type"
                    onChange={(e) => setTypeFilter(e.target.value)}
                  >
                    <MenuItem value="all">All Types</MenuItem>
                    <MenuItem value="buy">Buy</MenuItem>
                    <MenuItem value="sell">Sell</MenuItem>
                    <MenuItem value="dividend">Dividend</MenuItem>
                    <MenuItem value="split">Split</MenuItem>
                  </Select>
                </FormControl>

                <FormControl size="small" sx={{ minWidth: 120 }}>
                  <InputLabel>Status</InputLabel>
                  <Select
                    value={statusFilter}
                    label="Status"
                    onChange={(e) => setStatusFilter(e.target.value)}
                  >
                    <MenuItem value="all">All Status</MenuItem>
                    <MenuItem value="filled">Filled</MenuItem>
                    <MenuItem value="pending">Pending</MenuItem>
                    <MenuItem value="cancelled">Cancelled</MenuItem>
                    <MenuItem value="partial">Partial</MenuItem>
                  </Select>
                </FormControl>

                <Button
                  variant="outlined"
                  startIcon={<FilterList />}
                  onClick={() => setShowAdvancedFilters(!showAdvancedFilters)}
                >
                  Filters
                </Button>
              </Box>

              {showAdvancedFilters && (
                <Box
                  sx={{ mt: 2, pt: 2, borderTop: 1, borderColor: "divider" }}
                >
                  <Grid container spacing={2}>
                    <Grid item xs={12} sm={6}>
                      <DatePicker
                        label="Start Date"
                        value={dateFilter.start}
                        onChange={(date) =>
                          setDateFilter((prev) => ({ ...prev, start: date }))
                        }
                        renderInput={(params) => (
                          <TextField {...params} fullWidth />
                        )}
                      />
                    </Grid>
                    <Grid item xs={12} sm={6}>
                      <DatePicker
                        label="End Date"
                        value={dateFilter.end}
                        onChange={(date) =>
                          setDateFilter((prev) => ({ ...prev, end: date }))
                        }
                        renderInput={(params) => (
                          <TextField {...params} fullWidth />
                        )}
                      />
                    </Grid>
                  </Grid>
                </Box>
              )}
            </CardContent>
          </Card>

          {/* Trade Table */}
          <Card>
            <TableContainer>
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell>
                      <TableSortLabel
                        active={sortBy === "symbol"}
                        direction={sortBy === "symbol" ? sortOrder : "asc"}
                        onClick={() => {
                          setSortBy("symbol");
                          setSortOrder(
                            sortBy === "symbol" && sortOrder === "asc"
                              ? "desc"
                              : "asc"
                          );
                        }}
                      >
                        Symbol
                      </TableSortLabel>
                    </TableCell>
                    <TableCell>Type</TableCell>
                    <TableCell>Quantity</TableCell>
                    <TableCell>Price</TableCell>
                    <TableCell>Value</TableCell>
                    <TableCell>P&L</TableCell>
                    <TableCell>Status</TableCell>
                    <TableCell>
                      <TableSortLabel
                        active={sortBy === "executedAt"}
                        direction={sortBy === "executedAt" ? sortOrder : "asc"}
                        onClick={() => {
                          setSortBy("executedAt");
                          setSortOrder(
                            sortBy === "executedAt" && sortOrder === "asc"
                              ? "desc"
                              : "asc"
                          );
                        }}
                      >
                        Date
                      </TableSortLabel>
                    </TableCell>
                    <TableCell>Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {loading ? (
                    <TableRow>
                      <TableCell colSpan={9} align="center">
                        <CircularProgress />
                      </TableCell>
                    </TableRow>
                  ) : paginatedTrades.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={9} align="center">
                        <Typography variant="body2" color="text.secondary">
                          No trades found
                        </Typography>
                      </TableCell>
                    </TableRow>
                  ) : (
                    paginatedTrades.map((trade) => (
                      <TableRow key={trade.id} hover>
                        <TableCell>
                          <Typography variant="body2" fontWeight="bold">
                            {trade.symbol}
                          </Typography>
                        </TableCell>
                        <TableCell>
                          <Chip
                            label={trade.type}
                            color={getTradeTypeColor(trade.type)}
                            size="small"
                            icon={
                              trade.type === "buy" ? (
                                <TrendingUp />
                              ) : (
                                <TrendingDown />
                              )
                            }
                          />
                        </TableCell>
                        <TableCell>{trade.quantity}</TableCell>
                        <TableCell>{formatCurrency(trade.price)}</TableCell>
                        <TableCell>{formatCurrency(trade.value)}</TableCell>
                        <TableCell>
                          <Typography
                            variant="body2"
                            color={
                              trade.realizedPnl >= 0
                                ? "success.main"
                                : "error.main"
                            }
                            fontWeight="bold"
                          >
                            {formatCurrency(trade.realizedPnl)}
                          </Typography>
                        </TableCell>
                        <TableCell>
                          <Chip
                            label={trade.status}
                            color={getStatusColor(trade.status)}
                            size="small"
                          />
                        </TableCell>
                        <TableCell>
                          {new Date(trade.executedAt).toLocaleDateString()}
                        </TableCell>
                        <TableCell>
                          <IconButton
                            size="small"
                            onClick={() => {
                              setSelectedTrade(trade);
                              setDetailsOpen(true);
                            }}
                          >
                            <Analytics />
                          </IconButton>
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </TableContainer>
            <TablePagination
              rowsPerPageOptions={[10, 25, 50, 100]}
              component="div"
              count={filteredTrades.length}
              rowsPerPage={rowsPerPage}
              page={page}
              onPageChange={(e, newPage) => setPage(newPage)}
              onRowsPerPageChange={(e) => {
                setRowsPerPage(parseInt(e.target.value, 10));
                setPage(0);
              }}
            />
          </Card>
        </TabPanel>

        <TabPanel value={tabValue} index={1}>
          {/* Performance Charts */}
          <Grid container spacing={3}>
            <Grid item xs={12}>
              <Card>
                <CardHeader title="P&L Over Time" />
                <CardContent>
                  <ResponsiveContainer width="100%" height={400}>
                    <ComposedChart data={chartData}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="date" />
                      <YAxis />
                      <Tooltip formatter={(value) => formatCurrency(value)} />
                      <Bar dataKey="pnl" fill="#8884d8" />
                      <Line
                        type="monotone"
                        dataKey="cumulative"
                        stroke="#82ca9d"
                        strokeWidth={2}
                      />
                    </ComposedChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        </TabPanel>

        <TabPanel value={tabValue} index={2}>
          {/* Analytics Dashboard */}
          {analytics && (
            <Grid container spacing={3}>
              <Grid item xs={12} md={6}>
                <Card>
                  <CardHeader title="Trading Statistics" />
                  <CardContent>
                    <Box
                      sx={{ display: "flex", flexDirection: "column", gap: 2 }}
                    >
                      <Box
                        sx={{
                          display: "flex",
                          justifyContent: "space-between",
                        }}
                      >
                        <Typography>Total Trades:</Typography>
                        <Typography fontWeight="bold">
                          {analytics.totalTrades}
                        </Typography>
                      </Box>
                      <Box
                        sx={{
                          display: "flex",
                          justifyContent: "space-between",
                        }}
                      >
                        <Typography>Winning Trades:</Typography>
                        <Typography fontWeight="bold" color="success.main">
                          {analytics.winningTrades}
                        </Typography>
                      </Box>
                      <Box
                        sx={{
                          display: "flex",
                          justifyContent: "space-between",
                        }}
                      >
                        <Typography>Losing Trades:</Typography>
                        <Typography fontWeight="bold" color="error.main">
                          {analytics.losingTrades}
                        </Typography>
                      </Box>
                      <Box
                        sx={{
                          display: "flex",
                          justifyContent: "space-between",
                        }}
                      >
                        <Typography>Average Win:</Typography>
                        <Typography fontWeight="bold">
                          {formatCurrency(analytics.avgWin)}
                        </Typography>
                      </Box>
                      <Box
                        sx={{
                          display: "flex",
                          justifyContent: "space-between",
                        }}
                      >
                        <Typography>Average Loss:</Typography>
                        <Typography fontWeight="bold">
                          {formatCurrency(analytics.avgLoss)}
                        </Typography>
                      </Box>
                      <Box
                        sx={{
                          display: "flex",
                          justifyContent: "space-between",
                        }}
                      >
                        <Typography>Profit Factor:</Typography>
                        <Typography fontWeight="bold">
                          {analytics.profitFactor}
                        </Typography>
                      </Box>
                    </Box>
                  </CardContent>
                </Card>
              </Grid>

              <Grid item xs={12} md={6}>
                <Card>
                  <CardHeader title="Performance Metrics" />
                  <CardContent>
                    {performance && (
                      <Box
                        sx={{
                          display: "flex",
                          flexDirection: "column",
                          gap: 2,
                        }}
                      >
                        <Box
                          sx={{
                            display: "flex",
                            justifyContent: "space-between",
                          }}
                        >
                          <Typography>Total Return:</Typography>
                          <Typography
                            fontWeight="bold"
                            color={
                              performance.totalReturn >= 0
                                ? "success.main"
                                : "error.main"
                            }
                          >
                            {formatPercent(performance.totalReturn)}
                          </Typography>
                        </Box>
                        <Box
                          sx={{
                            display: "flex",
                            justifyContent: "space-between",
                          }}
                        >
                          <Typography>Sharpe Ratio:</Typography>
                          <Typography fontWeight="bold">
                            {performance.sharpeRatio}
                          </Typography>
                        </Box>
                        <Box
                          sx={{
                            display: "flex",
                            justifyContent: "space-between",
                          }}
                        >
                          <Typography>Max Drawdown:</Typography>
                          <Typography fontWeight="bold" color="error.main">
                            {formatPercent(performance.maxDrawdown)}
                          </Typography>
                        </Box>
                        <Box
                          sx={{
                            display: "flex",
                            justifyContent: "space-between",
                          }}
                        >
                          <Typography>Volatility:</Typography>
                          <Typography fontWeight="bold">
                            {formatPercent(performance.volatility)}
                          </Typography>
                        </Box>
                      </Box>
                    )}
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          )}
        </TabPanel>

        <TabPanel value={tabValue} index={3}>
          {/* AI Insights */}
          <Grid container spacing={3}>
            {insights.map((insight, index) => (
              <Grid item xs={12} md={6} key={index}>
                <Card>
                  <CardHeader
                    title={insight.title}
                    subheader={insight.category}
                  />
                  <CardContent>
                    <Typography variant="body2" color="text.secondary">
                      {insight.description}
                    </Typography>
                    {insight.recommendation && (
                      <Alert
                        severity={insight.severity || "info"}
                        sx={{ mt: 2 }}
                      >
                        {insight.recommendation}
                      </Alert>
                    )}
                  </CardContent>
                </Card>
              </Grid>
            ))}

            {insights.length === 0 && (
              <Grid item xs={12}>
                <Card>
                  <CardContent>
                    <Typography
                      variant="body2"
                      color="text.secondary"
                      align="center"
                    >
                      No AI insights available. Execute more trades to generate
                      insights.
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
            )}
          </Grid>
        </TabPanel>

        {/* Import Dialog */}
        <Dialog
          open={importDialogOpen}
          onClose={() => setImportDialogOpen(false)}
        >
          <DialogTitle>Import Trades</DialogTitle>
          <DialogContent>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              Import your trades from connected brokers. This will sync your
              trade history and update your analytics.
            </Typography>
            <Alert severity="info">
              Make sure your broker API keys are configured in Settings before
              importing.
            </Alert>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setImportDialogOpen(false)}>Cancel</Button>
            <Button variant="contained" onClick={handleImportTrades}>
              Import from Alpaca
            </Button>
          </DialogActions>
        </Dialog>

        {/* Trade Details Dialog */}
        <Dialog
          open={detailsOpen}
          onClose={() => setDetailsOpen(false)}
          maxWidth="md"
          fullWidth
        >
          <DialogTitle>Trade Details</DialogTitle>
          <DialogContent>
            {selectedTrade && (
              <Grid container spacing={2}>
                <Grid item xs={12} sm={6}>
                  <Typography variant="subtitle2">Symbol</Typography>
                  <Typography variant="body2">
                    {selectedTrade.symbol}
                  </Typography>
                </Grid>
                <Grid item xs={12} sm={6}>
                  <Typography variant="subtitle2">Type</Typography>
                  <Typography variant="body2">{selectedTrade.type}</Typography>
                </Grid>
                <Grid item xs={12} sm={6}>
                  <Typography variant="subtitle2">Quantity</Typography>
                  <Typography variant="body2">
                    {selectedTrade.quantity}
                  </Typography>
                </Grid>
                <Grid item xs={12} sm={6}>
                  <Typography variant="subtitle2">Price</Typography>
                  <Typography variant="body2">
                    {formatCurrency(selectedTrade.price)}
                  </Typography>
                </Grid>
                <Grid item xs={12} sm={6}>
                  <Typography variant="subtitle2">Total Value</Typography>
                  <Typography variant="body2">
                    {formatCurrency(selectedTrade.value)}
                  </Typography>
                </Grid>
                <Grid item xs={12} sm={6}>
                  <Typography variant="subtitle2">P&L</Typography>
                  <Typography
                    variant="body2"
                    color={
                      selectedTrade.realizedPnl >= 0
                        ? "success.main"
                        : "error.main"
                    }
                  >
                    {formatCurrency(selectedTrade.realizedPnl)}
                  </Typography>
                </Grid>
                <Grid item xs={12} sm={6}>
                  <Typography variant="subtitle2">Execution Date</Typography>
                  <Typography variant="body2">
                    {new Date(selectedTrade.executedAt).toLocaleString()}
                  </Typography>
                </Grid>
                <Grid item xs={12} sm={6}>
                  <Typography variant="subtitle2">Status</Typography>
                  <Typography variant="body2">
                    {selectedTrade.status}
                  </Typography>
                </Grid>
                {selectedTrade.fees && (
                  <Grid item xs={12} sm={6}>
                    <Typography variant="subtitle2">Fees</Typography>
                    <Typography variant="body2">
                      {formatCurrency(selectedTrade.fees)}
                    </Typography>
                  </Grid>
                )}
                {selectedTrade.notes && (
                  <Grid item xs={12}>
                    <Typography variant="subtitle2">Notes</Typography>
                    <Typography variant="body2">
                      {selectedTrade.notes}
                    </Typography>
                  </Grid>
                )}
              </Grid>
            )}
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setDetailsOpen(false)}>Close</Button>
          </DialogActions>
        </Dialog>
      </Container>
    </LocalizationProvider>
  );
};

export default TradeHistory;
