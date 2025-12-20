import { useState, useMemo, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
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
} from "@mui/icons-material";
import {
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  ResponsiveContainer,
  Bar,
  ComposedChart,
  Tooltip as RechartsTooltip,
} from "recharts";
import { DatePicker } from "@mui/x-date-pickers/DatePicker";
import { LocalizationProvider } from "@mui/x-date-pickers/LocalizationProvider";
import { AdapterDateFns } from "@mui/x-date-pickers/AdapterDateFns";

const API_BASE_URL = (import.meta.env && import.meta.env.VITE_API_URL) || (window.__CONFIG__ && window.__CONFIG__.API_URL) || "http://localhost:3001";

const TradeHistory = () => {
  // State management
  const [viewMode, setViewMode] = useState("trades"); // "trades" or "matched"
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(10000); // Show all trades
  const [selectedTrade, setSelectedTrade] = useState(null);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [importDialogOpen, setImportDialogOpen] = useState(false);
  const [showAdvancedFilters, setShowAdvancedFilters] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [sortBy, setSortBy] = useState("execution_date");
  const [sortOrder, setSortOrder] = useState("desc");
  const [matchedPairs, setMatchedPairs] = useState([]);
  const [matchedPairsLoading, setMatchedPairsLoading] = useState(false);
  const [matchedPairsError, setMatchedPairsError] = useState(null);
  const [matchedPairsSearchTerm, setMatchedPairsSearchTerm] = useState("");
  const [matchedPairsFilter, setMatchedPairsFilter] = useState("all"); // all, profit, loss, wash-sale
  const [dateFilter, setDateFilter] = useState({ start: null, end: null });
  const [error, setError] = useState(null);

  // Fetch trade data using useQuery
  const { data: tradeData, isLoading: tradeLoading, refetch: refetchTrades } = useQuery({
    queryKey: ["tradeHistory", page, rowsPerPage],
    queryFn: async () => {
      const params = new URLSearchParams({
        page: (page + 1).toString(),
        limit: rowsPerPage.toString(),
      });
      const response = await fetch(`${API_BASE_URL}/api/trades?${params}`);
      if (!response.ok) throw new Error('Failed to fetch trades');
      const data = await response.json();
      return { data: { trades: data.items || [], pagination: data.pagination || {}, summary: {} } };
    },
    staleTime: 60000,
  });

  const { data: summaryData, isLoading: summaryLoading } = useQuery({
    queryKey: ["tradeSummary"],
    queryFn: async () => {
      const response = await fetch(`${API_BASE_URL}/api/trades/summary`);
      if (!response.ok) throw new Error('Failed to fetch summary');
      const data = await response.json();
      return { data: data.data };
    },
    staleTime: 60000,
  });

  // Extract data from responses
  const trades = tradeData?.data?.trades || [];
  const tradesSummary = tradeData?.data?.summary || summaryData?.data?.summary || {};
  const loading = tradeLoading || summaryLoading;

  // Generate chart data from trades
  const chartData = useMemo(() => {
    if (!trades || trades.length === 0) return [];

    // Sort trades by date
    const sortedTrades = [...trades].sort((a, b) =>
      new Date(a.execution_date) - new Date(b.execution_date)
    );

    // Aggregate by date to show buy/sell counts and values
    const dateMap = {};
    sortedTrades.forEach((trade) => {
      const dateKey = new Date(trade.execution_date).toLocaleDateString();

      if (!dateMap[dateKey]) {
        dateMap[dateKey] = {
          date: dateKey,
          buyCount: 0,
          sellCount: 0,
          buyValue: 0,
          sellValue: 0,
          totalValue: 0,
        };
      }

      if (trade.type.toLowerCase() === 'buy') {
        dateMap[dateKey].buyCount += 1;
        // Only accumulate actual values, not fake defaults
        if (trade.order_value !== null && trade.order_value !== undefined) {
          dateMap[dateKey].buyValue += trade.order_value;
        }
      } else {
        dateMap[dateKey].sellCount += 1;
        // Only accumulate actual values, not fake defaults
        if (trade.order_value !== null && trade.order_value !== undefined) {
          dateMap[dateKey].sellValue += trade.order_value;
        }
      }
      // Only accumulate actual values, not fake defaults
      if (trade.order_value !== null && trade.order_value !== undefined) {
        dateMap[dateKey].totalValue += trade.order_value;
      }
    });

    return Object.values(dateMap);
  }, [trades]);

  // Calculate analytics metrics from trades
  const analytics = useMemo(() => {
    if (!trades || trades.length === 0) {
      return {
        totalTrades: 0,
        winningTrades: 0,
        losingTrades: 0,
        winRate: 0,
        avgHoldTime: "N/A",
        totalPnl: 0,
        avgWin: 0,
        avgLoss: 0,
        profitFactor: 0,
      };
    }

    // Separate buy and sell trades
    const buyTrades = trades.filter(t => t.type.toLowerCase() === 'buy');
    const sellTrades = trades.filter(t => t.type.toLowerCase() === 'sell');

    // Calculate metrics - only sum actual values, not fake defaults
    const totalBuyValue = buyTrades.reduce((sum, t) =>
      t.order_value !== null && t.order_value !== undefined ? sum + t.order_value : sum, 0);
    const totalSellValue = sellTrades.reduce((sum, t) =>
      t.order_value !== null && t.order_value !== undefined ? sum + t.order_value : sum, 0);
    const closedPnl = totalSellValue - totalBuyValue; // Realized P&L from closed positions

    // Count trades with quantifiable results
    const winCount = sellTrades.length; // Closing trades are "wins" (realizing position)
    const lossCount = buyTrades.filter(t => {
      // Count unclosed buys as potential losses
      return true;
    }).length;

    const avgWin = winCount > 0 ? totalSellValue / winCount : 0;
    const avgLoss = lossCount > 0 ? totalBuyValue / lossCount : 0;
    const profitFactor = totalBuyValue > 0 ? totalSellValue / totalBuyValue : 0;
    const totalTrades = tradesSummary.total_trades || trades.length;

    return {
      totalTrades,
      winningTrades: winCount,
      losingTrades: buyTrades.length - winCount, // Unclosed positions
      winRate: winCount > 0 ? (winCount / totalTrades) * 100 : 0,
      avgHoldTime: "N/A",
      totalPnl: closedPnl,
      avgWin,
      avgLoss,
      profitFactor: isFinite(profitFactor) ? profitFactor : 0,
    };
  }, [trades, tradesSummary]);

  // Filter matched pairs based on search and filter criteria
  const filteredMatchedPairs = useMemo(() => {
    if (!matchedPairs || matchedPairs.length === 0) return [];

    return matchedPairs.filter((pair) => {
      // Search filter
      const searchLower = matchedPairsSearchTerm.toLowerCase();
      const matchesSearch =
        pair.symbol.toLowerCase().includes(searchLower) ||
        pair.buyDate.toString().includes(searchLower) ||
        pair.sellDate.toString().includes(searchLower);

      if (!matchesSearch) return false;

      // P&L filter
      if (matchedPairsFilter !== "all") {
        const pnlValue = parseFloat(pair.pnl);
        if (matchedPairsFilter === "profit" && pnlValue <= 0) return false;
        if (matchedPairsFilter === "loss" && pnlValue >= 0) return false;
        if (matchedPairsFilter === "wash-sale" && !pair.isWashSale) return false;
      }

      return true;
    });
  }, [matchedPairs, matchedPairsSearchTerm, matchedPairsFilter]);

  // Fetch FIFO analysis data when view mode changes to "matched"
  useEffect(() => {
    if (viewMode === "matched") {
      const fetchFifoAnalysis = async () => {
        try {
          setMatchedPairsLoading(true);
          setMatchedPairsError(null);
          const response = await fetch("/api/trades/fifo-analysis");
          const data = await response.json();

          if (data.success && data.data) {
            // Handle nested structures: data.data.analysis or data.data directly
            const analysisData = data.data?.analysis || null;
            const matchedPairsData = analysisData?.matchedPairs || null;
            // Validate array before setting state
            const validMatchedPairs = Array.isArray(matchedPairsData) && matchedPairsData.length > 0 ? matchedPairsData : [];
            setMatchedPairs(validMatchedPairs);
          } else {
            setMatchedPairsError("Failed to load matched pairs data");
          }
        } catch (err) {
          setMatchedPairsError(err.message || "Error fetching matched pairs");
          console.error("Error fetching FIFO analysis:", err);
        } finally {
          setMatchedPairsLoading(false);
        }
      };

      fetchFifoAnalysis();
    }
  }, [viewMode]);

  const handleRefresh = () => {
    refetchTrades();
  };

  const handleImportTrades = async () => {
    try {
      setError(null);
      // Import would go here - for now just refetch
      refetchTrades();
      setImportDialogOpen(false);
    } catch (err) {
      setError(err.message);
    }
  };

  const handleExportTrades = async (format = "csv") => {
    try {
      const response = await fetch(`/api/trades/export?format=${format}`);
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
    if (!Array.isArray(trades)) return [];

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
      const aVal = a[sortBy] || "";
      const bVal = b[sortBy] || "";

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

        {/* View Tabs */}
        <Box sx={{ mb: 3, borderBottom: 1, borderColor: "divider" }}>
          <Tabs value={viewMode} onChange={(e, newValue) => setViewMode(newValue)}>
            <Tab label="All Trades" value="trades" />
            <Tab label="Matched Pairs (FIFO)" value="matched" />
          </Tabs>
        </Box>

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
            onClick={handleRefresh}
            disabled={loading}
          >
            Refresh
          </Button>
        </Box>

        {/* Trade Activity Chart Section */}
        <Grid container spacing={3} sx={{ mb: 4 }}>
          <Grid item xs={12}>
            <Card>
              <CardHeader title="Trade Activity Over Time - Buy/Sell by Day" />
              <CardContent>
                <ResponsiveContainer width="100%" height={400}>
                  <ComposedChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="date" angle={-45} textAnchor="end" height={80} />
                    <YAxis />
                    <RechartsTooltip
                      contentStyle={{ backgroundColor: "#f5f5f5", border: "1px solid #ccc" }}
                      formatter={(value, name) => {
                        if (name === "buyValue" || name === "sellValue") {
                          return formatCurrency(value);
                        }
                        return value;
                      }}
                      labelFormatter={(label) => `Date: ${label}`}
                    />
                    <Bar dataKey="buyValue" fill="#4CAF50" name="Buy Value" />
                    <Bar dataKey="sellValue" fill="#F44336" name="Sell Value" />
                    <Line dataKey="buyCount" stroke="#2196F3" yAxisId="right" strokeWidth={2} name="Buy Count" />
                    <Line dataKey="sellCount" stroke="#FF6F00" yAxisId="right" strokeWidth={2} name="Sell Count" />
                    <YAxis yAxisId="right" orientation="right" />
                  </ComposedChart>
                </ResponsiveContainer>
                <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
                  Green bars = Buy Values | Red bars = Sell Values | Blue line = # Buys | Orange line = # Sells
                </Typography>
              </CardContent>
            </Card>
          </Grid>
        </Grid>

        {/* Analytics Dashboard Section */}
        {analytics && (
          <Grid container spacing={3} sx={{ mb: 4 }}>
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
                <CardHeader title="Position Summary" />
                <CardContent>
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
                      <Typography>Avg Buy Order Value:</Typography>
                      <Typography fontWeight="bold">
                        {formatCurrency(
                          analytics.avgLoss
                        )}
                      </Typography>
                    </Box>
                    <Box
                      sx={{
                        display: "flex",
                        justifyContent: "space-between",
                      }}
                    >
                      <Typography>Avg Sell Order Value:</Typography>
                      <Typography fontWeight="bold">
                        {formatCurrency(
                          analytics.avgWin
                        )}
                      </Typography>
                    </Box>
                    <Box
                      sx={{
                        display: "flex",
                        justifyContent: "space-between",
                      }}
                    >
                      <Typography>Net Closed P&L:</Typography>
                      <Typography
                        fontWeight="bold"
                        color={
                          analytics.totalPnl >= 0
                            ? "success.main"
                            : "error.main"
                        }
                      >
                        {formatCurrency(analytics.totalPnl)}
                      </Typography>
                    </Box>
                    <Typography variant="caption" color="text.secondary" sx={{ mt: 1 }}>
                      Based on buy/sell order values
                    </Typography>
                  </Box>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        )}


        {/* Trade List Section - All Trades View */}
        {viewMode === "trades" && (
          <>
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
                      <TableCell colSpan={8} align="center">
                        <CircularProgress />
                      </TableCell>
                    </TableRow>
                  ) : (paginatedTrades?.length || 0) === 0 ? (
                    <TableRow>
                      <TableCell colSpan={8} align="center">
                        <Typography variant="body2" color="text.secondary">
                          No trades found
                        </Typography>
                      </TableCell>
                    </TableRow>
                  ) : (
                    (paginatedTrades || []).map((trade) => (
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
                        <TableCell>{formatCurrency(trade.execution_price)}</TableCell>
                        <TableCell>{formatCurrency(trade.order_value)}</TableCell>
                        <TableCell>
                          <Chip
                            label="Filled"
                            color="success"
                            size="small"
                          />
                        </TableCell>
                        <TableCell>
                          {new Date(trade.execution_date).toLocaleDateString()}
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
              count={filteredTrades?.length || 0}
              rowsPerPage={rowsPerPage}
              page={page}
              onPageChange={(e, newPage) => setPage(newPage)}
              onRowsPerPageChange={(e) => {
                setRowsPerPage(parseInt(e.target.value, 10));
                setPage(0);
              }}
            />
          </Card>
          </>
        )}

        {/* Matched Pairs Section - Matched Pairs View */}
        {viewMode === "matched" && (
          <>
            {matchedPairsLoading ? (
              <Card sx={{ p: 3, textAlign: "center" }}>
                <CircularProgress />
                <Typography sx={{ mt: 2 }}>Loading matched pairs...</Typography>
              </Card>
            ) : matchedPairsError ? (
              <Alert severity="error" sx={{ mb: 3 }}>
                {matchedPairsError}
              </Alert>
            ) : (
              <>
                {/* Matched Pairs Filters */}
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
                        placeholder="Search by symbol or date..."
                        value={matchedPairsSearchTerm}
                        onChange={(e) => setMatchedPairsSearchTerm(e.target.value)}
                        InputProps={{
                          startAdornment: (
                            <InputAdornment position="start">
                              <Search />
                            </InputAdornment>
                          ),
                        }}
                        sx={{ minWidth: 200 }}
                      />

                      <FormControl size="small" sx={{ minWidth: 150 }}>
                        <InputLabel>P&L Filter</InputLabel>
                        <Select
                          value={matchedPairsFilter}
                          label="P&L Filter"
                          onChange={(e) => setMatchedPairsFilter(e.target.value)}
                        >
                          <MenuItem value="all">All Pairs</MenuItem>
                          <MenuItem value="profit">Profits Only</MenuItem>
                          <MenuItem value="loss">Losses Only</MenuItem>
                          <MenuItem value="wash-sale">Wash Sales Only</MenuItem>
                        </Select>
                      </FormControl>

                      <Button
                        variant="outlined"
                        onClick={() => {
                          setMatchedPairsSearchTerm("");
                          setMatchedPairsFilter("all");
                        }}
                      >
                        Clear Filters
                      </Button>
                    </Box>
                  </CardContent>
                </Card>

                {/* Matched Pairs Table */}
                <Card>
                  <TableContainer>
                  <Table>
                    <TableHead>
                      <TableRow sx={{ backgroundColor: "#f5f5f5" }}>
                        <TableCell><strong>Symbol</strong></TableCell>
                        <TableCell><strong>Buy Date</strong></TableCell>
                        <TableCell align="right"><strong>Buy Price</strong></TableCell>
                        <TableCell><strong>Sell Date</strong></TableCell>
                        <TableCell align="right"><strong>Sell Price</strong></TableCell>
                        <TableCell align="right"><strong>Qty</strong></TableCell>
                        <TableCell align="right"><strong>Cost Basis</strong></TableCell>
                        <TableCell align="right"><strong>Proceeds</strong></TableCell>
                        <TableCell align="right"><strong>P&L</strong></TableCell>
                        <TableCell align="right"><strong>Hold Days</strong></TableCell>
                        <TableCell><strong>Tax Type</strong></TableCell>
                        <TableCell><strong>Wash Sale</strong></TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {filteredMatchedPairs && filteredMatchedPairs.length > 0 ? (
                        filteredMatchedPairs.map((pair, index) => {
                          const pnlValue = parseFloat(pair.pnl);
                          const isProfit = pnlValue >= 0;
                          return (
                            <TableRow key={index} hover>
                              <TableCell>
                                <Typography variant="body2" fontWeight="bold">
                                  {pair.symbol}
                                </Typography>
                              </TableCell>
                              <TableCell>
                                <Typography variant="body2">
                                  {new Date(pair.buyDate).toLocaleDateString()}
                                </Typography>
                              </TableCell>
                              <TableCell align="right">
                                <Typography variant="body2">
                                  {formatCurrency(pair.buyPrice)}
                                </Typography>
                              </TableCell>
                              <TableCell>
                                <Typography variant="body2">
                                  {new Date(pair.sellDate).toLocaleDateString()}
                                </Typography>
                              </TableCell>
                              <TableCell align="right">
                                <Typography variant="body2">
                                  {formatCurrency(pair.sellPrice)}
                                </Typography>
                              </TableCell>
                              <TableCell align="right">
                                <Typography variant="body2">
                                  {pair.quantity}
                                </Typography>
                              </TableCell>
                              <TableCell align="right">
                                <Typography variant="body2">
                                  {formatCurrency(pair.costBasis)}
                                </Typography>
                              </TableCell>
                              <TableCell align="right">
                                <Typography variant="body2">
                                  {formatCurrency(pair.proceeds)}
                                </Typography>
                              </TableCell>
                              <TableCell align="right">
                                <Typography
                                  variant="body2"
                                  fontWeight="bold"
                                  sx={{
                                    color: isProfit ? "success.main" : "error.main",
                                  }}
                                >
                                  {isProfit ? "+" : ""}{formatCurrency(pnlValue)}
                                </Typography>
                              </TableCell>
                              <TableCell align="right">
                                <Typography variant="body2">
                                  {pair.holdDays}
                                </Typography>
                              </TableCell>
                              <TableCell>
                                <Chip
                                  label={pair.taxType}
                                  size="small"
                                  color={pair.taxType === "LONG-TERM" ? "success" : "warning"}
                                  variant="outlined"
                                />
                              </TableCell>
                              <TableCell>
                                {pair.isWashSale ? (
                                  <Chip
                                    label="Wash Sale"
                                    size="small"
                                    color="error"
                                    variant="outlined"
                                  />
                                ) : (
                                  <Typography variant="body2">—</Typography>
                                )}
                              </TableCell>
                            </TableRow>
                          );
                        })
                      ) : (
                        <TableRow>
                          <TableCell colSpan={12} align="center">
                            <Typography variant="body2" color="text.secondary">
                              No matched pairs found
                            </Typography>
                          </TableCell>
                        </TableRow>
                      )}
                    </TableBody>
                  </Table>
                </TableContainer>
                </Card>
              </>
            )}
          </>
        )}

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
              <Grid container spacing={2} sx={{ mt: 1 }}>
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
                  <Typography variant="subtitle2">Execution Price</Typography>
                  <Typography variant="body2">
                    {formatCurrency(selectedTrade.execution_price)}
                  </Typography>
                </Grid>
                <Grid item xs={12} sm={6}>
                  <Typography variant="subtitle2">Total Value</Typography>
                  <Typography variant="body2">
                    {formatCurrency(selectedTrade.order_value)}
                  </Typography>
                </Grid>
                <Grid item xs={12} sm={6}>
                  <Typography variant="subtitle2">P&L</Typography>
                  <Typography
                    variant="body2"
                    color="text.secondary"
                  >
                    {formatCurrency(0)}
                  </Typography>
                </Grid>
                <Grid item xs={12} sm={6}>
                  <Typography variant="subtitle2">Execution Date</Typography>
                  <Typography variant="body2">
                    {new Date(selectedTrade.execution_date).toLocaleString()}
                  </Typography>
                </Grid>
                <Grid item xs={12} sm={6}>
                  <Typography variant="subtitle2">Status</Typography>
                  <Typography variant="body2">
                    Filled
                  </Typography>
                </Grid>
                {selectedTrade.commission ? (
                  <Grid item xs={12} sm={6}>
                    <Typography variant="subtitle2">Commission</Typography>
                    <Typography variant="body2">
                      {formatCurrency(selectedTrade.commission)}
                    </Typography>
                  </Grid>
                ) : null}
                <Grid item xs={12} sm={6}>
                  <Typography variant="subtitle2">Order ID</Typography>
                  <Typography variant="body2">
                    {selectedTrade.order_id}
                  </Typography>
                </Grid>
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
