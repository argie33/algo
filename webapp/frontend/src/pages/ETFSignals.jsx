import React, { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTheme } from "@mui/material/styles";
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
import ErrorBoundary from "../components/ErrorBoundary";
import SignalCardAccordion from "../components/SignalCardAccordion";

// Use console logger for now
const logger = {
  info: (msg) => console.log(`[ETFSignals] ${msg}`),
  error: (msg) => console.error(`[ETFSignals] ${msg}`),
  warn: (msg) => console.warn(`[ETFSignals] ${msg}`),
};

function ETFSignals() {
  useDocumentTitle("ETF Signals");
  const theme = useTheme();
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

  // Helper function to check if signal has real data (not all nulls)
  const hasRealData = (signal) => {
    if (!signal) return false;
    if (!signal.symbol) return false; // Must have a symbol
    if (!signal.signal) return false; // Must have a signal type (Buy/Sell)
    if (!signal.close && signal.close !== 0) return false; // Must have price data
    // If it has symbol, signal, and price - it's real data from the API
    // Don't filter out signals just because some optional fields are null
    return true;
  };

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

  // Fetch buy/sell signals for ALL timeframes in parallel
  const {
    data: allTimeframesData,
    isLoading: allTimeframesLoading,
    error: allTimeframesError,
  } = useQuery({
    queryKey: [
      "tradingSignalsAllTimeframes",
      signalType,
      symbolFilter,
      // Note: timeframe is removed - we load ALL timeframes now
    ],
    queryFn: async () => {
      try {
        const timeframes = ["daily", "weekly", "monthly"];
        const startTime = Date.now();

        logger.info("🔄 LOADING ALL TIMEFRAMES - Starting parallel fetch");

        const requests = timeframes.map(async (tf) => {
          const params = new URLSearchParams();

          // Only add defined parameters
          if (signalType !== "all") {
            params.append("signal_type", signalType);
          }
          params.append("timeframe", tf);

          // Smart loading strategy:
          // - If filtering by symbol: load ALL historical data for that symbol
          // - Otherwise: load only recent signals for performance
          if (symbolFilter) {
            params.append("limit", 100000); // Load all history for specific symbol
          } else {
            params.append("limit", 5000); // Default: load recent signals only
          }

          if (symbolFilter) {
            params.append("symbol", symbolFilter);
          }

          const url = `${API_BASE}/api/signals/etf?${params}`;
          const tfStartTime = Date.now();

          logger.info(`📡 [${tf.toUpperCase()}] Request: ${url}`);

          const response = await fetch(url);
          if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`HTTP ${response.status}: ${errorText}`);
          }

          const data = await response.json();
          const tfDuration = Date.now() - tfStartTime;
          const itemCount = data?.items?.length || 0;

          logger.info(`✅ [${tf.toUpperCase()}] Loaded ${itemCount} signals in ${tfDuration}ms`, {
            items: itemCount,
            pagination: data?.pagination,
          });

          return {
            timeframe: tf,
            data: data,
            loadTime: tfDuration,
          };
        });

        // Execute all requests in parallel
        const results = await Promise.all(requests);

        // Combine results into a single object
        const combined = {
          daily: results.find((r) => r.timeframe === "daily")?.data || { items: [] },
          weekly: results.find((r) => r.timeframe === "weekly")?.data || { items: [] },
          monthly: results.find((r) => r.timeframe === "monthly")?.data || { items: [] },
        };

        const totalTime = Date.now() - startTime;
        const dailyCount = combined.daily?.items?.length || 0;
        const weeklyCount = combined.weekly?.items?.length || 0;
        const monthlyCount = combined.monthly?.items?.length || 0;
        const totalCount = dailyCount + weeklyCount + monthlyCount;

        logger.info(`🎯 ALL TIMEFRAMES LOADED in ${totalTime}ms - Total: ${totalCount} signals`, {
          daily: dailyCount,
          weekly: weeklyCount,
          monthly: monthlyCount,
          total: totalCount,
          totalLoadTime: totalTime,
        });

        // Also log to console for visibility
        console.log(`
═══════════════════════════════════════════════════════════════
🎯 TRADING SIGNALS - ALL TIMEFRAMES LOADED
═══════════════════════════════════════════════════════════════
📊 DAILY:   ${dailyCount} signals
📊 WEEKLY:  ${weeklyCount} signals
📊 MONTHLY: ${monthlyCount} signals
───────────────────────────────────────────────────────────────
🏆 TOTAL:   ${totalCount} signals
⏱️  Load Time: ${totalTime}ms
═══════════════════════════════════════════════════════════════
        `);

        return combined;
      } catch (err) {
        logger.error("fetchETFSignals - Error loading timeframes", err);
        console.error("❌ ERROR LOADING TIMEFRAMES:", err);
        throw err;
      }
    },
    refetchOnWindowFocus: false,
    staleTime: 0, // Always fresh - no stale cache
    cacheTime: 0, // Disable caching - fetch fresh data every time
    refetchInterval: 30000, // Refetch every 30 seconds for real-time updates
    onError: (err) =>
      logger.queryError("tradingSignalsAllTimeframes", err, { signalType }),
  });

  // Get the current timeframe's data from all loaded data
  const signalsData = allTimeframesData ? allTimeframesData[timeframe] : null;
  const signalsLoading = allTimeframesLoading;
  const signalsError = allTimeframesError;

  // Calculate summary statistics from ALL loaded timeframes
  const summaryStats = useMemo(() => {
    // Collect data from all timeframes that were loaded
    const allSignals = [];
    if (allTimeframesData?.daily?.items) allSignals.push(...allTimeframesData.daily.items);
    if (allTimeframesData?.weekly?.items) allSignals.push(...allTimeframesData.weekly.items);
    if (allTimeframesData?.monthly?.items) allSignals.push(...allTimeframesData.monthly.items);

    if (!allSignals || allSignals.length === 0) {
      return null;
    }

    const totalSignals = allSignals?.length || 0;
    // Count signals matching current date range
    const currentRangeSignals = allSignals.filter((s) => matchesDateRange(s.date)).length;
    const buySignals = allSignals.filter((s) => String(s.signal).toLowerCase() === "buy").length;
    const sellSignals = allSignals.filter((s) => String(s.signal).toLowerCase() === "sell").length;

    // Get signals from current timeframe view
    const signals = signalsData?.items || [];

    // Swing Trading Metrics
    const stage2Signals = signals.filter((s) => s.market_stage === "Stage 2 - Advancing").length;
    const highQualitySignals = signals.filter((s) => s.quality_score >= 60).length;
    const pocketPivots = signals.filter((s) => s.volume_analysis === "Pocket Pivot").length;
    const swingPatternCompliant = signals.filter((s) => s.passes_minervini_template).length;
    const inPosition = signals.filter((s) => s.inposition).length;

    // Average metrics for signals with data
    const validRRSignals = signals.filter((s) => s.risk_reward_ratio && s.risk_reward_ratio > 0);
    const avgRiskReward = validRRSignals.length > 0
      ? (validRRSignals.reduce((sum, s) => sum + parseFloat(s.risk_reward_ratio), 0) / validRRSignals.length).toFixed(1)
      : null;

    const validQualitySignals = signals.filter((s) => s.quality_score);
    const avgQualityScore = validQualitySignals.length > 0
      ? Math.round(validQualitySignals.reduce((sum, s) => sum + parseInt(s.quality_score), 0) / validQualitySignals.length)
      : null;

    return {
      totalSignals,
      currentRangeSignals,
      buySignals,
      sellSignals,
      // Swing Trading Metrics
      stage2Signals,
      highQualitySignals,
      pocketPivots,
      swingPatternCompliant,
      inPosition,
      avgRiskReward,
      avgQualityScore,
    };
  }, [allTimeframesData, dateRange]);

  // Filter data based on all filter settings
  const filteredSignals = useMemo(() => {
    // The API response structure is: { items: [...], pagination, success }
    const signalsArray = signalsData?.items;
    if (!signalsArray || !Array.isArray(signalsArray)) {
      if (signalsData) {
        console.log("❌ Signals extraction failed. signalsData keys:", Object.keys(signalsData || {}), "signals:", signalsArray);
      }
      return [];
    }

    let filtered = signalsArray;

    logger.info("filteredSignals init", `Processing ${signalsArray.length} signals`);

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

    // Always filter out signals with no real data (show only signals with substantial data)
    filtered = filtered.filter((signal) => hasRealData(signal));

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

    // Sort by date DESC (newest first)
    filtered.sort((a, b) => {
      const dateA = (a.date || a.signal_triggered_date) ? new Date(a.date || a.signal_triggered_date).getTime() : 0;
      const dateB = (b.date || b.signal_triggered_date) ? new Date(b.date || b.signal_triggered_date).getTime() : 0;
      return dateB - dateA; // DESC order
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
          `${API_BASE}/api/signals/etf?symbol=${selectedSymbol}&timeframe=daily&limit=50`
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

  // Pagination handlers
  const handleChangePage = (event, newPage) => {
    setPage(newPage);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const handleChangeRowsPerPage = (event) => {
    setRowsPerPage(parseInt(event.target.value, 10));
    setPage(0);
  };

  // Early return for loading state
  const isLoading = signalsLoading;
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
    const isRecent = matchesDateRange(signalDate);

    return (
      <Badge
        badgeContent={isRecent ? <NewReleases sx={{ fontSize: 12 }} /> : 0}
        color="secondary"
        overlap="circular"
      >
        <Chip
          label={signal}
          size="medium"
          icon={
            isBuy ? (
              <TrendingUp />
            ) : isSell ? (
              <TrendingDown />
            ) : null
          }
          sx={{
            backgroundColor: isBuy
              ? theme.palette.success.main
              : isSell
                ? theme.palette.error.main
                : theme.palette.action.disabled,
            color: "white",
            fontWeight: "bold",
            fontSize: "0.875rem",
            minWidth: "80px",
            borderRadius: "16px",
            ...(isRecent && {
              boxShadow: isBuy
                ? `0 0 15px ${theme.palette.success.light}40`
                : isSell
                  ? `0 0 15px ${theme.palette.error.light}40`
                  : `0 0 15px ${theme.palette.primary.light}40`,
              animation: "pulse 2s infinite",
            }),
            ...(isBuy && {
              background: `linear-gradient(45deg, ${theme.palette.success.main} 30%, ${theme.palette.success.light} 90%)`,
            }),
            ...(isSell && {
              background: `linear-gradient(45deg, ${theme.palette.error.main} 30%, ${theme.palette.error.light} 90%)`,
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
          border: `2px solid ${theme.palette.primary.main}`,
          boxShadow: `0 4px 20px ${theme.palette.primary.main}25`,
          background: `linear-gradient(135deg, ${theme.palette.primary.main}10 0%, ${theme.palette.primary.main}00 100%)`,
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
            borderTop: `1px solid ${theme.palette.divider}`,
            mt: 1.5,
          }}>
            {Array.isArray(details) ? (
              details.map((detail, idx) => (
                <Box key={`detail-${detail.label}-${idx}`} sx={{ display: "flex", justifyContent: "space-between", mb: 0.75 }}>
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


  // --- Table for Buy/Sell signals with DYNAMIC columns and PAGINATION ---
  const BuySellSignalsTable = () => {
    const columns = getDynamicColumns(filteredSignals);

    // Calculate paginated data
    const totalSignals = filteredSignals?.length || 0;
    const startIndex = page * rowsPerPage;
    const endIndex = startIndex + rowsPerPage;
    const paginatedSignals = filteredSignals?.slice(startIndex, endIndex) || [];

    return (
      <Box>
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
              {paginatedSignals?.map((signal, index) => (
                <TableRow
                  key={`${signal.symbol}-${startIndex + index}`}
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

        {/* Pagination Controls */}
        {filteredSignals?.length > 0 && (
          <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mt: 2 }}>
            <Typography variant="body2" color="text.secondary">
              Showing {startIndex + 1} to {Math.min(endIndex, totalSignals)} of {totalSignals} signals
            </Typography>
            <TablePagination
              rowsPerPageOptions={[10, 25, 50, 100]}
              component="div"
              count={totalSignals}
              rowsPerPage={rowsPerPage}
              page={page}
              onPageChange={handleChangePage}
              onRowsPerPageChange={handleChangeRowsPerPage}
              sx={{ ml: "auto" }}
            />
          </Box>
        )}
      </Box>
    );
  };

  return (
    <Container maxWidth="xl" sx={{ py: 4 }}>
      {/* Enhanced Header */}
      <Box sx={{ mb: 4 }}>
        <Box>
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
                  endpoint: `${API_BASE}/api/signals/etf?timeframe=${timeframe}`,
                  debugEndpoint: `${API_BASE}/api/trading/debug`,
                  filters: { signalType, dateRange, timeframe },
                  component: "ETFSignals",
                },
              }}
              title="Failed to Load ETF Signals"
              onRetry={() => window.location.reload()}
              severity="error"
            />
          )}

          {/* No Data State */}
          {!signalsError &&
            !signalsLoading &&
            (!(signalsData?.items) || (signalsData?.items?.length || 0) === 0) && (
              <ErrorDisplay
                error={{
                  message: "No ETF signals data found",
                  context: {
                    endpoint: `${API_BASE}/api/signals/etf?timeframe=${timeframe}`,
                    filters: { signalType, dateRange },
                    response: signalsData,
                  },
                }}
                title="No Data Available"
                severity="info"
                showDetails={true}
              />
            )}

          {/* Data Display - Accordion View with Pagination */}
          <Card>
            <CardContent>
              {/* Pagination Controls - Top */}
              {filteredSignals?.length > rowsPerPage && (
                <Box sx={{ mb: 2, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <Typography variant="body2" color="text.secondary">
                    Showing {page * rowsPerPage + 1} to {Math.min((page + 1) * rowsPerPage, filteredSignals.length)} of {filteredSignals.length} signals
                  </Typography>
                  <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
                    <FormControl size="small" sx={{ minWidth: 100 }}>
                      <InputLabel>Per Page</InputLabel>
                      <Select
                        value={rowsPerPage}
                        onChange={(e) => {
                          setRowsPerPage(parseInt(e.target.value, 10));
                          setPage(0);
                        }}
                        label="Per Page"
                      >
                        <MenuItem value={25}>25</MenuItem>
                        <MenuItem value={50}>50</MenuItem>
                        <MenuItem value={100}>100</MenuItem>
                        <MenuItem value={250}>250</MenuItem>
                        <MenuItem value={500}>500</MenuItem>
                        <MenuItem value={1000}>All (1000)</MenuItem>
                      </Select>
                    </FormControl>
                    <TablePagination
                      rowsPerPageOptions={[]}
                      component="div"
                      count={filteredSignals.length}
                      rowsPerPage={rowsPerPage}
                      page={page}
                      onPageChange={(e, newPage) => {
                        setPage(newPage);
                        window.scrollTo({ top: 0, behavior: 'smooth' });
                      }}
                      sx={{ ml: 'auto' }}
                    />
                  </Box>
                </Box>
              )}

              {/* Accordion */}
              <SignalCardAccordion signals={filteredSignals.slice(page * rowsPerPage, (page + 1) * rowsPerPage)} />

              {/* Pagination Controls - Bottom */}
              {filteredSignals?.length > rowsPerPage && (
                <Box sx={{ mt: 2, display: 'flex', justifyContent: 'center' }}>
                  <TablePagination
                    rowsPerPageOptions={[]}
                    component="div"
                    count={filteredSignals.length}
                    rowsPerPage={rowsPerPage}
                    page={page}
                    onPageChange={(e, newPage) => {
                      setPage(newPage);
                      window.scrollTo({ top: 0, behavior: 'smooth' });
                    }}
                  />
                </Box>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>


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
                    <TableRow key={`${signal.symbol}-${signal.date || signal.signal_triggered_date}-${index}`}>
                      <TableCell>
                        {signal.signal_triggered_date
                          ? new Date(signal.signal_triggered_date).toLocaleDateString()
                          : signal.date
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
                          : "-"}
                      </TableCell>
                      <TableCell align="right">
                        {signal.stoplevel
                          ? formatCurrency(signal.stoplevel)
                          : "-"}
                      </TableCell>
                      <TableCell align="right">
                        {signal.target_price
                          ? formatCurrency(signal.target_price)
                          : "-"}
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
                          label={signal.quality_score || "—"}
                          size="small"
                          sx={{
                            backgroundColor:
                              signal.quality_score >= 80 ? "rgba(5, 150, 105, 0.2)" :
                              signal.quality_score >= 60 ? "rgba(59, 130, 246, 0.2)" :
                              signal.quality_score >= 40 ? "rgba(245, 158, 11, 0.2)" :
                              "rgba(220, 38, 38, 0.2)",
                            color:
                              signal.quality_score >= 80 ? "#059669" :
                              signal.quality_score >= 60 ? "#3B82F6" :
                              signal.quality_score >= 40 ? "#F59E0B" :
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

function ETFSignalsWithErrorBoundary() {
  return (
    <ErrorBoundary>
      <ETFSignals />
    </ErrorBoundary>
  );
}

export default ETFSignalsWithErrorBoundary;
