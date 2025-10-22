import React, { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useDocumentTitle } from "../hooks/useDocumentTitle";
import {
  Badge,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Container,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  FormControl,
  FormControlLabel,
  Grid,
  IconButton,
  InputAdornment,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TablePagination,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import {
  TrendingUp,
  TrendingDown,
  Analytics,
  NewReleases,
  FilterList,
  Close,
  Timeline,
  Search,
  Clear,
  HorizontalRule,
} from "@mui/icons-material";
import { formatCurrency, formatPercentage } from "../utils/formatters";
import { formatCellValue, getCellAlign, getDynamicColumns } from "../utils/signalTableHelpers";
import { getApiConfig } from "../services/api";
import { ErrorDisplay, LoadingDisplay } from "../components/ui/ErrorBoundary";
import SignalPerformanceTracker from "../components/SignalPerformanceTracker";

// Use console logger for now
const logger = {
  info: (msg) => console.log(`[TradingSignals] ${msg}`),
  error: (msg) => console.error(`[TradingSignals] ${msg}`),
  warn: (msg) => console.warn(`[TradingSignals] ${msg}`),
};

function TradingSignals() {
  useDocumentTitle("Trading Signals");
  const { apiUrl: API_BASE } = getApiConfig();

  // Add CSS for pulse animation
  React.useEffect(() => {
    const pulseAnimation = `
      @keyframes pulse {
        0% { transform: scale(1); }
        50% { transform: scale(1.05); }
        100% { transform: scale(1); }
      }
    `;

    if (
      typeof document !== "undefined" &&
      !document.getElementById("pulse-animation")
    ) {
      const style = document.createElement("style");
      style.id = "pulse-animation";
      style.textContent = pulseAnimation;
      document.head.appendChild(style);
    }
  }, []);
  const [signalType, setSignalType] = useState("all");
  const [timeframe, setTimeframe] = useState("daily");
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);
  const [selectedSymbol, setSelectedSymbol] = useState(null);
  const [historicalDialogOpen, setHistoricalDialogOpen] = useState(false);
  const [symbolFilter, setSymbolFilter] = useState("");
  const [searchInput, setSearchInput] = useState("");

  // Date range filter - defaults to "all" to show all signals
  const [dateRange, setDateRange] = useState("all"); // Show ALL signals regardless of date
  const [showActiveOnly, setShowActiveOnly] = useState(false); // Show ALL signals by default (user can toggle to active-only)

  // Helper function to check if signal matches date range
  const matchesDateRange = (signalDate) => {
    if (!signalDate) return false;
    const today = new Date();
    today.setHours(0, 0, 0, 0); // Start of today
    const signal = new Date(signalDate);
    signal.setHours(0, 0, 0, 0);

    const diffTime = today.getTime() - signal.getTime();
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));

    switch(dateRange) {
      case "today":
        return diffDays === 0; // Same day
      case "week":
        return diffDays <= 7;
      case "month":
        return diffDays <= 30;
      case "all":
        return true;
      default:
        return true;
    }
  };

  // Fetch buy/sell signals (moved up before useMemo hooks)
  const {
    data: signalsData,
    isLoading: signalsLoading,
    error: signalsError,
  } = useQuery({
    queryKey: [
      "tradingSignals",
      signalType,
      timeframe,
      page,
      rowsPerPage,
      symbolFilter,
      // Note: dateRange is NOT in queryKey - it's client-side filtering only
    ],
    queryFn: async () => {
      try {
        const params = new URLSearchParams();

        // Only add defined parameters
        if (signalType !== "all") {
          params.append("signal_type", signalType);
        }
        params.append("timeframe", timeframe);
        params.append("page", page + 1);
        params.append("limit", rowsPerPage);
        if (symbolFilter) {
          params.append("symbol", symbolFilter);
        }
        // Note: date filtering happens client-side for better UX
        const url = `${API_BASE}/api/signals?${params}`;
        logger.info("fetchTradingSignals - Request started", {
          url,
          signalType,
          timeframe,
        });

        const response = await fetch(url);
        if (!response.ok) {
          const errorText = await response.text();
          throw new Error(`HTTP ${response.status}: ${errorText}`);
        }

        const data = await response.json();
        logger.info("fetchTradingSignals", "Data retrieved", {
          recordCount: data?.data?.length || 0,
          totalRecords: data?.total || 0,
        });
        return data;
      } catch (err) {
        logger.error("fetchTradingSignals", err);
        throw err;
      }
    },
    refetchOnWindowFocus: false,
    staleTime: 60000, // 1 minute
    cacheTime: 300000, // 5 minutes
    onError: (err) =>
      logger.queryError("tradingSignals", err, { signalType, timeframe }),
  });

  // Calculate summary statistics
  const summaryStats = useMemo(() => {
    const signals = signalsData?.signals || signalsData?.data;
    if (!signals || !Array.isArray(signals)) return null;
    const totalSignals = signals?.length || 0;
    // Count signals matching current date range
    const currentRangeSignals = signals.filter((s) => matchesDateRange(s.date)).length;
    const buySignals = signals.filter((s) => s.signal === "Buy" || s.signal === "BUY").length;
    const sellSignals = signals.filter((s) => s.signal === "Sell" || s.signal === "SELL").length;

    // Swing Trading Metrics
    const stage2Signals = signals.filter((s) => s.market_stage === "Stage 2 - Advancing").length;
    const highQualitySignals = signals.filter((s) => s.entry_quality_score >= 60).length;
    const pocketPivots = signals.filter((s) => s.volume_analysis === "Pocket Pivot").length;
    const minerviniCompliant = signals.filter((s) => s.passes_minervini_template).length;
    const inPosition = signals.filter((s) => s.inposition).length;

    // Average metrics for signals with data
    const validRRSignals = signals.filter((s) => s.risk_reward_ratio && s.risk_reward_ratio > 0);
    const avgRiskReward = validRRSignals.length > 0
      ? (validRRSignals.reduce((sum, s) => sum + parseFloat(s.risk_reward_ratio || 0), 0) / validRRSignals.length).toFixed(1)
      : 0;

    const validQualitySignals = signals.filter((s) => s.entry_quality_score);
    const avgQualityScore = validQualitySignals.length > 0
      ? Math.round(validQualitySignals.reduce((sum, s) => sum + parseInt(s.entry_quality_score || 0), 0) / validQualitySignals.length)
      : 0;

    return {
      totalSignals,
      currentRangeSignals,
      buySignals,
      sellSignals,
      // Swing Trading Metrics
      stage2Signals,
      highQualitySignals,
      pocketPivots,
      minerviniCompliant,
      inPosition,
      avgRiskReward,
      avgQualityScore,
    };
  }, [signalsData, dateRange]);

  // Filter data based on all filter settings
  const filteredSignals = useMemo(() => {
    const signals = signalsData?.signals || signalsData?.data;
    if (!signals || !Array.isArray(signals)) {
      console.log("No signals data available or not array:", signalsData);
      return [];
    }

    let filtered = signals;

    // Apply active filter - show signals with active positions OR recent signals
    if (showActiveOnly) {
      const sevenDaysAgo = new Date();
      sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);

      filtered = filtered.filter((signal) => {
        // Show if currently in position (API returns 'inposition' lowercase)
        if (signal.inposition || signal.in_position) return true;

        // Show if signal is from last 7 days and has an actual signal (not "None")
        if (signal.signal && signal.signal !== "None") {
          const signalDate = new Date(signal.date);
          return signalDate >= sevenDaysAgo;
        }

        return false;
      });
    }

    // Apply date range filter only if not "all"
    if (dateRange !== "all") {
      filtered = filtered.filter((signal) => matchesDateRange(signal.date));
    }

    // Apply symbol filter
    if (symbolFilter) {
      filtered = filtered.filter((signal) =>
        signal.symbol?.toLowerCase().includes(symbolFilter.toLowerCase())
      );
    }

    logger.info("filteredSignals", "Data filtered", {
      originalCount: (signalsData?.signals || signalsData?.data)?.length || 0,
      filteredCount: filtered?.length || 0,
      filters: {
        showActiveOnly,
        dateRange,
        symbolFilter
      }
    });

    return filtered;
  }, [
    signalsData,
    showActiveOnly,
    dateRange,
    symbolFilter
  ]);

  // Fetch historical data for selected symbol
  const { data: historicalData, isLoading: historicalLoading } = useQuery({
    queryKey: ["historicalSignals", selectedSymbol],
    queryFn: async () => {
      if (!selectedSymbol) return null;
      try {
        const response = await fetch(
          `${API_BASE}/api/signals?timeframe=daily&symbol=${selectedSymbol}&limit=50`
        );
        if (!response.ok) throw new Error("Failed to fetch historical data");
        return await response.json();
      } catch (err) {
        logger.error("fetchHistoricalSignals", err, { symbol: selectedSymbol });
        throw err;
      }
    },
    enabled: !!selectedSymbol && historicalDialogOpen,
    onError: (err) =>
      logger.queryError("historicalSignals", err, { symbol: selectedSymbol }),
  });
  // Helper functions for search
  const handleSearch = () => {
    setSymbolFilter(searchInput.trim());
    setPage(0);
  };

  const handleClearSearch = () => {
    setSearchInput("");
    setSymbolFilter("");
    setPage(0);
  };

  // Fetch performance summary
  const { data: performanceData, isLoading: performanceLoading } = useQuery({
    queryKey: ["tradingPerformance"],
    queryFn: async () => {
      try {
        const url = `${API_BASE}/api/signals/performance`;
        logger.info("fetchTradingPerformance - Request started", { url });

        const response = await fetch(url);
        if (!response.ok) {
          const error = new Error(
            `Failed to fetch performance (${response.status})`
          );
          logger.error("fetchTradingPerformance", error, {
            url,
            status: response.status,
            statusText: response.statusText,
          });
          throw error;
        }

        const result = await response.json();
        logger.info("fetchTradingPerformance - Request completed", result);
        return result;
      } catch (err) {
        logger.error("fetchTradingPerformance", err);
        throw err;
      }
    },
    refetchInterval: 600000, // Refresh every 10 minutes
    onError: (err) => logger.queryError("tradingPerformance", err),
  });

  // Early return for loading state
  const isLoading = signalsLoading || performanceLoading;
  if (isLoading && !signalsData) {
    return (
      <Container maxWidth="lg" sx={{ py: 4 }}>
        <LoadingDisplay
          message="Loading trading signals and performance data..."
          fullPage={true}
          size="large"
        />
      </Container>
    );
  }

  const getSignalChip = (signal, signalDate) => {
    const isBuy = signal === "Buy" || signal === "BUY";
    const isSell = signal === "Sell" || signal === "SELL";
    const isHold = signal === "Hold" || signal === "HOLD";
    const isRecent = matchesDateRange(signalDate);

    return (
      <Badge
        badgeContent={isRecent ? <NewReleases sx={{ fontSize: 12 }} /> : 0}
        color="secondary"
        overlap="circular"
      >
        <Chip
          label={signal || "None"}
          size="medium"
          icon={
            isBuy ? (
              <TrendingUp />
            ) : isSell ? (
              <TrendingDown />
            ) : (
              <HorizontalRule />
            )
          }
          sx={{
            backgroundColor: isBuy
              ? "#059669"
              : isSell
                ? "#DC2626"
                : isHold
                  ? "#D97706"
                  : "#6B7280",
            color: "white",
            fontWeight: "bold",
            fontSize: "0.875rem",
            minWidth: "80px",
            borderRadius: "16px",
            ...(isRecent && {
              boxShadow: isBuy
                ? "0 0 15px rgba(5, 150, 105, 0.6)"
                : isSell
                  ? "0 0 15px rgba(220, 38, 38, 0.6)"
                  : "0 0 15px rgba(59, 130, 246, 0.5)",
              animation: "pulse 2s infinite",
            }),
            ...(isBuy && {
              background: "linear-gradient(45deg, #059669 30%, #10B981 90%)",
            }),
            ...(isSell && {
              background: "linear-gradient(45deg, #DC2626 30%, #EF4444 90%)",
            }),
          }}
        />
      </Badge>
    );
  };

  const PerformanceCard = ({
    title,
    value,
    subtitle,
    icon,
    color,
    isHighlight = false,
    details = null,
  }) => (
    <Card
      sx={{
        height: "100%",
        display: "flex",
        flexDirection: "column",
        transition: "all 0.3s ease",
        "&:hover": {
          transform: "translateY(-4px)",
          boxShadow: "0 12px 24px rgba(0, 0, 0, 0.15)",
        },
        ...(isHighlight && {
          border: "2px solid #3B82F6",
          boxShadow: "0 4px 20px rgba(59, 130, 246, 0.15)",
          background: "linear-gradient(135deg, rgba(59, 130, 246, 0.05) 0%, rgba(59, 130, 246, 0) 100%)",
        }),
      }}
    >
      <CardContent sx={{ flexGrow: 1 }}>
        {/* Header with icon and title */}
        <Box display="flex" alignItems="center" mb={2}>
          <Box sx={{ color, fontSize: 24 }}>
            {icon}
          </Box>
          <Typography
            variant="subtitle2"
            sx={{ ml: 1, fontWeight: 600, color: "text.primary" }}
          >
            {title}
          </Typography>
        </Box>

        {/* Main value */}
        <Box sx={{ mb: 1.5 }}>
          <Typography
            variant="h3"
            sx={{
              color,
              fontWeight: "bold",
              fontSize: { xs: "1.8rem", sm: "2.2rem" },
            }}
          >
            {value}
          </Typography>
        </Box>

        {/* Subtitle/description */}
        <Typography
          variant="body2"
          color="text.secondary"
          sx={{ mb: details ? 1.5 : 0 }}
        >
          {subtitle}
        </Typography>

        {/* Additional details if provided */}
        {details && (
          <Box sx={{
            pt: 1.5,
            borderTop: "1px solid #E5E7EB",
            mt: 1.5,
          }}>
            {Array.isArray(details) ? (
              details.map((detail, idx) => (
                <Box key={idx} sx={{ display: "flex", justifyContent: "space-between", mb: 0.75 }}>
                  <Typography variant="caption" color="text.secondary">
                    {detail.label}:
                  </Typography>
                  <Typography variant="caption" sx={{ fontWeight: 600 }}>
                    {detail.value}
                  </Typography>
                </Box>
              ))
            ) : (
              <Typography variant="caption" color="text.secondary">
                {details}
              </Typography>
            )}
          </Box>
        )}
      </CardContent>
    </Card>
  );


  // --- Table for Buy/Sell signals with DYNAMIC columns ---
  const BuySellSignalsTable = () => {
    const columns = getDynamicColumns(filteredSignals);

    return (
      <TableContainer component={Paper} elevation={0} sx={{ overflowX: "auto" }}>
        <Table stickyHeader>
          <TableHead>
            <TableRow>
              {columns.map((col) => (
                <TableCell
                  key={col}
                  align={getCellAlign(col)}
                  sx={{
                    fontWeight: "bold",
                    whiteSpace: "nowrap",
                    minWidth: "100px",
                  }}
                >
                  <Tooltip title={col} placement="top">
                    <span>{col.replace(/_/g, " ").replace(/^./, str => str.toUpperCase())}</span>
                  </Tooltip>
                </TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {filteredSignals?.map((signal, index) => (
              <TableRow
                key={`${signal.symbol}-${index}`}
                hover
                sx={{
                  "&:hover": {
                    backgroundColor: "action.hover",
                  },
                }}
              >
                {columns.map((col) => {
                  const value = signal[col];
                  const isSymbolColumn = col === "symbol";
                  const isSignalColumn = col === "signal";

                  return (
                    <TableCell
                      key={`${signal.symbol}-${col}`}
                      align={getCellAlign(col)}
                      sx={{ whiteSpace: "nowrap" }}
                    >
                      {isSymbolColumn ? (
                        <Button
                          variant="text"
                          size="small"
                          sx={{ fontWeight: "bold", minWidth: "auto", p: 0.5 }}
                          onClick={() => {
                            setSelectedSymbol(signal.symbol);
                            setHistoricalDialogOpen(true);
                          }}
                        >
                          {value}
                        </Button>
                      ) : isSignalColumn ? (
                        <Tooltip
                          title={
                            matchesDateRange(signal.date)
                              ? `Signal in ${dateRange === "today" ? "today's" : dateRange === "week" ? "this week's" : dateRange === "month" ? "this month's" : "selected"} range`
                              : "Signal outside selected range"
                          }
                        >
                          <Box>{getSignalChip(value, signal.date)}</Box>
                        </Tooltip>
                      ) : (
                        <Typography variant="body2">
                          {formatCellValue(value, col)}
                        </Typography>
                      )}
                    </TableCell>
                  );
                })}
              </TableRow>
            ))}
          </TableBody>
        </Table>
        {filteredSignals?.length === 0 && (
          <Box sx={{ p: 4, textAlign: "center" }}>
            <Typography variant="h6" color="text.secondary" gutterBottom>
              No trading signals found
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {dateRange === "all"
                ? "No signals found. Try adjusting your timeframe or other filters."
                : "No signals match your current filters. Try adjusting your date range or other filters."}
            </Typography>
          </Box>
        )}
      </TableContainer>
    );
  };

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      {/* Enhanced Header */}
      <Box sx={{ mb: 4 }}>
        <Typography
          variant="h3"
          component="h1"
          gutterBottom
          sx={{ fontWeight: 700, color: "primary.main" }}
        >
          🎯 Trading Signals
        </Typography>
        <Typography variant="subtitle1" color="text.secondary" sx={{ mb: 3 }}>
          AI-powered trading signals with real-time market analysis and
          institutional-grade insights
        </Typography>
      </Box>

      <Box
        display="flex"
        alignItems="center"
        justifyContent="space-between"
        mb={4}
      >
      </Box>

      {/* Enhanced Performance Summary */}
      <Grid container spacing={3} mb={4}>
        {/* Active Signals Summary - Most Important */}
        {summaryStats && (
          <Grid item xs={12} md={3}>
            <PerformanceCard
              title="Active Signals"
              value={summaryStats.totalSignals}
              subtitle={`${summaryStats.currentRangeSignals} in ${dateRange === 'today' ? 'today' : dateRange === 'week' ? 'this week' : dateRange === 'month' ? 'this month' : 'all time'}`}
              icon={
                <Badge
                  badgeContent={summaryStats.currentRangeSignals}
                  color="secondary"
                >
                  <Analytics />
                </Badge>
              }
              color="#3B82F6"
              isHighlight={summaryStats.currentRangeSignals > 0}
            />
          </Grid>
        )}

        {performanceData?.performance?.map((perf) => (
          <Grid item xs={12} md={3} key={perf.signal}>
            <PerformanceCard
              title={`${perf.signal} Win Rate`}
              value={`${(Number(perf.win_rate) || 0).toFixed(1)}%`}
              subtitle={`${perf.winning_trades || 0}/${perf.total_signals || 0} trades | Avg: ${formatPercentage((Number(perf.avg_performance) || 0) / 100)}`}
              icon={perf.signal === "BUY" ? <TrendingUp /> : <TrendingDown />}
              color={perf.signal === "BUY" ? "#10B981" : "#DC2626"}
            />
          </Grid>
        ))}

        {summaryStats && (
          <Grid item xs={12} md={3}>
            <PerformanceCard
              title="Buy Signals"
              value={summaryStats.buySignals || 0}
              subtitle={`${Math.round(((summaryStats.buySignals || 0) / (summaryStats.totalSignals || 1)) * 100)}% of signals`}
              icon={<TrendingUp />}
              color="#10B981"
            />
          </Grid>
        )}

        {summaryStats && (
          <Grid item xs={12} md={3}>
            <PerformanceCard
              title="Sell Signals"
              value={summaryStats.sellSignals || 0}
              subtitle={`${Math.round(((summaryStats.sellSignals || 0) / (summaryStats.totalSignals || 1)) * 100)}% of signals`}
              icon={<TrendingDown />}
              color="#DC2626"
            />
          </Grid>
        )}
      </Grid>


      {/* Filters and Search - Horizontal Layout */}
      <Card sx={{ mb: 4 }}>
        <CardContent>
          <Grid container spacing={2} alignItems="center">
            <Grid item xs={12}>
              <Typography variant="h6" gutterBottom>
                <FilterList sx={{ mr: 1 }} />
                Filters
              </Typography>
              <Divider sx={{ mb: 2 }} />
            </Grid>

            {/* Search */}
            <Grid item xs={12} md={4}>
              <TextField
                fullWidth
                size="small"
                placeholder="Search symbols..."
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                onKeyPress={(e) => e.key === "Enter" && handleSearch()}
                InputProps={{
                  startAdornment: (
                    <InputAdornment position="start">
                      <Search />
                    </InputAdornment>
                  ),
                  endAdornment: searchInput && (
                    <InputAdornment position="end">
                      <IconButton size="small" onClick={handleClearSearch}>
                        <Clear />
                      </IconButton>
                    </InputAdornment>
                  ),
                }}
              />
            </Grid>

            {/* Signal Type Filter */}
            <Grid item xs={12} md={2}>
              <FormControl fullWidth size="small">
                <InputLabel>Signal Type</InputLabel>
                <Select
                  value={signalType}
                  label="Signal Type"
                  onChange={(e) => setSignalType(e.target.value)}
                >
                  <MenuItem value="all">All Signals</MenuItem>
                  <MenuItem value="buy">Buy Only</MenuItem>
                  <MenuItem value="sell">Sell Only</MenuItem>
                </Select>
              </FormControl>
            </Grid>

            {/* Timeframe Filter */}
            <Grid item xs={12} md={2}>
              <FormControl fullWidth size="small">
                <InputLabel>Timeframe</InputLabel>
                <Select
                  value={timeframe}
                  label="Timeframe"
                  onChange={(e) => setTimeframe(e.target.value)}
                >
                  <MenuItem value="daily">Daily</MenuItem>
                  <MenuItem value="weekly">Weekly</MenuItem>
                  <MenuItem value="monthly">Monthly</MenuItem>
                </Select>
              </FormControl>
            </Grid>

            {/* Active Signals Filter */}
            <Grid item xs={12} md={2}>
              <FormControlLabel
                control={
                  <Switch
                    checked={showActiveOnly}
                    onChange={(e) => {
                      setShowActiveOnly(e.target.checked);
                      setPage(0);
                    }}
                    color="primary"
                  />
                }
                label="Active Only"
                sx={{ mt: 1 }}
              />
              <Typography variant="caption" display="block" color="text.secondary">
                Show current positions & recent signals
              </Typography>
            </Grid>

            {/* Date Range Filter */}
            <Grid item xs={12} md={2}>
              <FormControl fullWidth size="small">
                <InputLabel>Date Range</InputLabel>
                <Select
                  value={dateRange}
                  label="Date Range"
                  onChange={(e) => {
                    setDateRange(e.target.value);
                    setPage(0);
                  }}
                >
                  <MenuItem value="today">Today Only</MenuItem>
                  <MenuItem value="week">This Week</MenuItem>
                  <MenuItem value="month">This Month</MenuItem>
                  <MenuItem value="all">All Time</MenuItem>
                </Select>
              </FormControl>
            </Grid>

            <Grid item xs={12} md={2}>
              <Button
                fullWidth
                variant="contained"
                onClick={handleSearch}
                size="medium"
              >
                Search
              </Button>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      {/* Main Signals Table - Full Width */}
      <Grid container spacing={3}>
        <Grid item xs={12}>
          {/* Standardized Error Handling */}
          {signalsError && (
            <ErrorDisplay
              error={{
                message: signalsError?.message || String(signalsError),
                context: {
                  endpoint: `${API_BASE}/api/signals?timeframe=${timeframe}`,
                  debugEndpoint: `${API_BASE}/api/trading/debug`,
                  filters: { signalType, dateRange, timeframe },
                  component: "TradingSignals",
                },
              }}
              title="Failed to Load Trading Signals"
              onRetry={() => window.location.reload()}
              severity="error"
            />
          )}

          {/* No Data State */}
          {!signalsError &&
            !signalsLoading &&
            (!(signalsData?.signals || signalsData?.data) || ((signalsData?.signals || signalsData?.data)?.length || 0) === 0) && (
              <ErrorDisplay
                error={{
                  message: "No trading signals data found",
                  context: {
                    endpoint: `${API_BASE}/api/signals?timeframe=${timeframe}`,
                    filters: { signalType, dateRange },
                    response: signalsData,
                  },
                }}
                title="No Data Available"
                severity="info"
                showDetails={true}
              />
            )}

          {/* Data Table */}
          <Card>
            <CardContent>
              <BuySellSignalsTable />
              <TablePagination
                component="div"
                count={signalsData?.pagination?.total || 0}
                page={page}
                onPageChange={(e, newPage) => setPage(newPage)}
                rowsPerPage={rowsPerPage}
                onRowsPerPageChange={(e) => {
                  setRowsPerPage(parseInt(e.target.value, 10));
                  setPage(0);
                }}
                rowsPerPageOptions={[10, 25, 50, 100, { label: 'All', value: -1 }]}
              />
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Signal Performance Tracking */}
      {filteredSignals?.length > 0 && (
        <Box sx={{ mt: 4 }}>
          <Typography variant="h5" gutterBottom sx={{ mb: 2 }}>
            Signal Performance Tracking
          </Typography>
          <SignalPerformanceTracker
            symbols={filteredSignals.map(signal => signal.symbol)}
            timeframe="7d"
          />
        </Box>
      )}

      {/* Historical Data Dialog */}
      <Dialog
        open={historicalDialogOpen}
        onClose={() => setHistoricalDialogOpen(false)}
        maxWidth="lg"
        fullWidth
      >
        <DialogTitle>
          <Box
            display="flex"
            alignItems="center"
            justifyContent="space-between"
          >
            <Box display="flex" alignItems="center">
              <Timeline sx={{ mr: 1 }} />
              <Typography variant="h6">
                {selectedSymbol} - Historical Signals
              </Typography>
            </Box>
            <IconButton
              onClick={() => setHistoricalDialogOpen(false)}
              size="small"
            >
              <Close />
            </IconButton>
          </Box>
        </DialogTitle>
        <DialogContent>
          {historicalLoading ? (
            <Box display="flex" justifyContent="center" p={4}>
              <CircularProgress />
            </Box>
          ) : (
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Date</TableCell>
                    <TableCell>Signal</TableCell>
                    <TableCell align="right">Price</TableCell>
                    <TableCell align="right">Buy Level</TableCell>
                    <TableCell align="right">Stop Loss</TableCell>
                    <TableCell align="right">Target</TableCell>
                    <TableCell align="right">R/R Ratio</TableCell>
                    <TableCell>Stage</TableCell>
                    <TableCell align="right">SATA</TableCell>
                    <TableCell align="right">Quality</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {historicalData?.data?.map((signal, index) => (
                    <TableRow key={index}>
                      <TableCell>
                        {signal.date
                          ? new Date(signal.date).toLocaleDateString()
                          : ""}
                      </TableCell>
                      <TableCell>
                        {getSignalChip(signal.signal, signal.date)}
                      </TableCell>
                      <TableCell align="right">
                        {formatCurrency(signal.current_price || signal.close)}
                      </TableCell>
                      <TableCell align="right">
                        {signal.buylevel
                          ? formatCurrency(signal.buylevel)
                          : "—"}
                      </TableCell>
                      <TableCell align="right">
                        {signal.stoplevel
                          ? formatCurrency(signal.stoplevel)
                          : "—"}
                      </TableCell>
                      <TableCell align="right">
                        {signal.target_price
                          ? formatCurrency(signal.target_price)
                          : "—"}
                      </TableCell>
                      <TableCell align="right">
                        {signal.risk_reward_ratio
                          ? `${Number(signal.risk_reward_ratio).toFixed(1)}:1`
                          : "—"}
                      </TableCell>
                      <TableCell>
                        <Tooltip title={`${signal.market_stage || "Unknown"}\n${signal.substage || ""}`}>
                          <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
                            <Chip
                              label={signal.market_stage?.replace("Stage ", "S") || "—"}
                              size="small"
                              sx={{
                                backgroundColor:
                                  signal.market_stage === "Stage 2 - Advancing" ? "rgba(5, 150, 105, 0.2)" :
                                  signal.market_stage === "Stage 1 - Basing" ? "rgba(59, 130, 246, 0.2)" :
                                  signal.market_stage === "Stage 3 - Topping" ? "rgba(245, 158, 11, 0.2)" :
                                  signal.market_stage === "Stage 4 - Declining" ? "rgba(220, 38, 38, 0.2)" :
                                  "rgba(156, 163, 175, 0.2)",
                                color:
                                  signal.market_stage === "Stage 2 - Advancing" ? "#059669" :
                                  signal.market_stage === "Stage 1 - Basing" ? "#3B82F6" :
                                  signal.market_stage === "Stage 3 - Topping" ? "#F59E0B" :
                                  signal.market_stage === "Stage 4 - Declining" ? "#DC2626" :
                                  "#6B7280",
                                fontWeight: "bold",
                                fontSize: "0.7rem",
                              }}
                            />
                          </Box>
                        </Tooltip>
                      </TableCell>
                      <TableCell align="right">
                        <Chip
                          label={signal.sata_score !== null && signal.sata_score !== undefined ? signal.sata_score : "—"}
                          size="small"
                          sx={{
                            backgroundColor:
                              signal.sata_score >= 8 ? "rgba(5, 150, 105, 0.2)" :
                              signal.sata_score >= 4 ? "rgba(59, 130, 246, 0.2)" :
                              "rgba(220, 38, 38, 0.2)",
                            color:
                              signal.sata_score >= 8 ? "#059669" :
                              signal.sata_score >= 4 ? "#3B82F6" :
                              "#DC2626",
                            fontWeight: "bold",
                            fontSize: "0.7rem",
                          }}
                        />
                      </TableCell>
                      <TableCell align="right">
                        <Chip
                          label={signal.entry_quality_score || "—"}
                          size="small"
                          sx={{
                            backgroundColor:
                              signal.entry_quality_score >= 80 ? "rgba(5, 150, 105, 0.2)" :
                              signal.entry_quality_score >= 60 ? "rgba(59, 130, 246, 0.2)" :
                              signal.entry_quality_score >= 40 ? "rgba(245, 158, 11, 0.2)" :
                              "rgba(220, 38, 38, 0.2)",
                            color:
                              signal.entry_quality_score >= 80 ? "#059669" :
                              signal.entry_quality_score >= 60 ? "#3B82F6" :
                              signal.entry_quality_score >= 40 ? "#F59E0B" :
                              "#DC2626",
                            fontWeight: "bold",
                            fontSize: "0.7rem",
                          }}
                        />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setHistoricalDialogOpen(false)}>Close</Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
}

export default TradingSignals;
