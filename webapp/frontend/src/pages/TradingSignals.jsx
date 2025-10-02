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
  const [dateRange, setDateRange] = useState("all"); // today, week, month, all
  const [showActiveOnly, setShowActiveOnly] = useState(true); // Show active/recent signals by default

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
    if (!signalsData?.data || !Array.isArray(signalsData?.data)) return null;

    const signals = signalsData?.data;
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
    if (!signalsData?.data || !Array.isArray(signalsData?.data)) {
      console.log("No signals data available or not array:", signalsData);
      return [];
    }

    let filtered = signalsData?.data;

    // Apply active filter - show signals with active positions OR recent signals
    if (showActiveOnly) {
      const sevenDaysAgo = new Date();
      sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);

      filtered = filtered.filter((signal) => {
        // Show if currently in position
        if (signal.inPosition) return true;

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
      originalCount: signalsData.data?.length || 0,
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
  }) => (
    <Card
      sx={{
        ...(isHighlight && {
          border: "2px solid #3B82F6",
          boxShadow: "0 4px 20px rgba(59, 130, 246, 0.15)",
        }),
      }}
    >
      <CardContent>
        <Box display="flex" alignItems="center" mb={1}>
          {icon}
          <Typography variant="h6" ml={1}>
            {title}
          </Typography>
        </Box>
        <Typography variant="h4" sx={{ color, fontWeight: "bold" }}>
          {value}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {subtitle}
        </Typography>
      </CardContent>
    </Card>
  );

  // --- Table for Buy/Sell signals, matching backend fields ---
  const BuySellSignalsTable = () => (
    <TableContainer component={Paper} elevation={0}>
      <Table>
        <TableHead>
          <TableRow sx={{ backgroundColor: "grey.50" }}>
            <TableCell sx={{ fontWeight: "bold" }}>Symbol</TableCell>
            <TableCell sx={{ fontWeight: "bold" }}>Company</TableCell>
            <TableCell sx={{ fontWeight: "bold" }}>Signal</TableCell>
            <TableCell align="right" sx={{ fontWeight: "bold" }}>
              <Tooltip title="Current market price">
                <span>Price</span>
              </Tooltip>
            </TableCell>
            <TableCell align="right" sx={{ fontWeight: "bold" }}>
              <Tooltip title="Entry price for position">
                <span>Buy Level</span>
              </Tooltip>
            </TableCell>
            <TableCell align="right" sx={{ fontWeight: "bold" }}>
              <Tooltip title="Stop loss price (7-8% max risk)">
                <span>Stop</span>
              </Tooltip>
            </TableCell>
            <TableCell align="right" sx={{ fontWeight: "bold" }}>
              <Tooltip title="25% Target - Sell another 20-25%, let final 25% run with trailing stop">
                <span>Target (25%)</span>
              </Tooltip>
            </TableCell>
            <TableCell align="right" sx={{ fontWeight: "bold" }}>
              <Tooltip title="8% Target - Sell 20-25% of position, move stop to breakeven">
                <span>8% Target</span>
              </Tooltip>
            </TableCell>
            <TableCell align="right" sx={{ fontWeight: "bold" }}>
              <Tooltip title="20% Target - Sell another 25-30% of position">
                <span>20% Target</span>
              </Tooltip>
            </TableCell>
            <TableCell align="right" sx={{ fontWeight: "bold" }}>
              <Tooltip title="Risk/Reward Ratio - Minimum 2:1 acceptable, 3:1+ excellent">
                <span>R/R</span>
              </Tooltip>
            </TableCell>
            <TableCell align="right" sx={{ fontWeight: "bold" }}>
              <Tooltip title="Risk % - Maximum 8% acceptable, avoid trades >10%">
                <span>Risk %</span>
              </Tooltip>
            </TableCell>
            <TableCell sx={{ fontWeight: "bold" }}>
              <Tooltip title="Stage & Confidence: Stage 2=BUY zone, confidence 60+ required. Hover to see substage (Early/Mid/Late)">
                <span>Stage</span>
              </Tooltip>
            </TableCell>
            <TableCell align="right" sx={{ fontWeight: "bold" }}>
              <Tooltip title="SATA Score (0-10): Stage Analysis Technical Attributes score from stageanalysis.com. 8-10 = Strong Stage 2, 4-7 = Stage 1/3, 0-3 = Stage 4">
                <span>SATA</span>
              </Tooltip>
            </TableCell>
            <TableCell align="right" sx={{ fontWeight: "bold" }}>
              <Tooltip title="Mansfield RS: Relative Strength vs S&P 500. >0 = outperforming market, <0 = underperforming">
                <span>RS</span>
              </Tooltip>
            </TableCell>
            <TableCell sx={{ fontWeight: "bold" }}>
              <Tooltip title="Volume: Pocket Pivot (200%+ surge) = STRONG BUY, Volume Surge (150%+) = Good, Normal = OK, Dry-up (<70%) = Wait">
                <span>Volume</span>
              </Tooltip>
            </TableCell>
            <TableCell align="right" sx={{ fontWeight: "bold" }}>
              <Tooltip title="21 EMA Distance: -1% to +2% = perfect pullback entry, >5% = too extended">
                <span>21 EMA %</span>
              </Tooltip>
            </TableCell>
            <TableCell align="right" sx={{ fontWeight: "bold" }}>
              <Tooltip title="RSI: 40-55 = BEST buy zone (pullback in uptrend), 55-70 = good, >70 = overbought">
                <span>RSI</span>
              </Tooltip>
            </TableCell>
            <TableCell align="right" sx={{ fontWeight: "bold" }}>
              <Tooltip title="ADX: >30 = very strong trend (best), 25-30 = strong, 20-25 = moderate, <20 = avoid">
                <span>ADX</span>
              </Tooltip>
            </TableCell>
            <TableCell align="center" sx={{ fontWeight: "bold" }}>
              <Tooltip title="Passes 7-point trend template: Price > 50/150/200 SMA, SMAs aligned, Price 0-30% above 200 SMA, 200 SMA rising">
                <span>Trend ✓</span>
              </Tooltip>
            </TableCell>
            <TableCell align="center" sx={{ fontWeight: "bold" }}>
              <Tooltip title="Currently holding this position">
                <span>Position</span>
              </Tooltip>
            </TableCell>
            <TableCell sx={{ fontWeight: "bold" }}>
              <Tooltip title="Next earnings announcement date">
                <span>Next Earnings</span>
              </Tooltip>
            </TableCell>
            <TableCell align="right" sx={{ fontWeight: "bold" }}>
              <Tooltip title="Days until next earnings">
                <span>Days</span>
              </Tooltip>
            </TableCell>
            <TableCell align="right" sx={{ fontWeight: "bold" }}>
              <Tooltip title="Estimated EPS for next earnings">
                <span>Est. EPS</span>
              </Tooltip>
            </TableCell>
            <TableCell align="right" sx={{ fontWeight: "bold" }}>
              <Tooltip title="Last EPS surprise percentage">
                <span>EPS Surprise</span>
              </Tooltip>
            </TableCell>
            <TableCell align="right" sx={{ fontWeight: "bold" }}>
              <Tooltip title="Year-over-year earnings growth">
                <span>Growth YoY</span>
              </Tooltip>
            </TableCell>
            <TableCell sx={{ fontWeight: "bold" }}>Date</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {filteredSignals?.map((signal, index) => (
            <TableRow
              key={`${signal.symbol}-${index}`}
              hover
              sx={{
                "&:hover": {
                  backgroundColor:
                    signal.signal === "Buy" || signal.signal === "BUY"
                      ? "rgba(5, 150, 105, 0.1)"
                      : signal.signal === "Sell" || signal.signal === "SELL"
                        ? "rgba(220, 38, 38, 0.1)"
                        : "action.hover",
                },
                ...(matchesDateRange(signal.date) && {
                  backgroundColor:
                    signal.signal === "Buy" || signal.signal === "BUY"
                      ? "rgba(5, 150, 105, 0.05)"
                      : signal.signal === "Sell" || signal.signal === "SELL"
                        ? "rgba(220, 38, 38, 0.05)"
                        : "rgba(59, 130, 246, 0.05)",
                  borderLeft:
                    signal.signal === "Buy" || signal.signal === "BUY"
                      ? "4px solid #059669"
                      : signal.signal === "Sell" || signal.signal === "SELL"
                        ? "4px solid #DC2626"
                        : "4px solid #3B82F6",
                }),
              }}
            >
              <TableCell>
                <Button
                  variant="text"
                  size="small"
                  sx={{ fontWeight: "bold", minWidth: "auto", p: 0.5 }}
                  onClick={() => {
                    setSelectedSymbol(signal.symbol);
                    setHistoricalDialogOpen(true);
                  }}
                >
                  {signal.symbol}
                </Button>
              </TableCell>
              <TableCell>
                <Typography variant="body2" noWrap>
                  {signal.company_name}
                </Typography>
              </TableCell>
              <TableCell>
                <Tooltip
                  title={
                    matchesDateRange(signal.date)
                      ? `Signal in ${dateRange === "today" ? "today's" : dateRange === "week" ? "this week's" : dateRange === "month" ? "this month's" : "selected"} range`
                      : "Signal outside selected range"
                  }
                >
                  <Box>{getSignalChip(signal.signal, signal.date)}</Box>
                </Tooltip>
              </TableCell>
              <TableCell align="right">
                {formatCurrency(signal.current_price || signal.close)}
              </TableCell>
              <TableCell align="right">
                {formatCurrency(signal.buylevel)}
              </TableCell>
              <TableCell align="right">
                {formatCurrency(signal.stoplevel)}
              </TableCell>
              <TableCell align="right">
                {signal.target_price ? formatCurrency(signal.target_price) : "—"}
              </TableCell>
              <TableCell align="right">
                {signal.profit_target_8pct ? formatCurrency(signal.profit_target_8pct) : "—"}
              </TableCell>
              <TableCell align="right">
                {signal.profit_target_20pct ? formatCurrency(signal.profit_target_20pct) : "—"}
              </TableCell>
              <TableCell align="right">
                {signal.risk_reward_ratio
                  ? `${Number(signal.risk_reward_ratio).toFixed(1)}:1`
                  : "—"}
              </TableCell>
              <TableCell align="right">
                {signal.risk_pct
                  ? `${Number(signal.risk_pct).toFixed(1)}%`
                  : "—"}
              </TableCell>
              <TableCell>
                <Tooltip title={`${signal.market_stage || "Unknown"}\nConfidence: ${signal.stage_confidence || 0}/100\n${signal.substage || ""}`}>
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
                        fontSize: "0.75rem",
                      }}
                    />
                    {signal.stage_confidence && (
                      <Typography variant="caption" sx={{
                        fontSize: "0.65rem",
                        color: signal.stage_confidence >= 75 ? "#059669" :
                               signal.stage_confidence >= 60 ? "#3B82F6" :
                               signal.stage_confidence >= 40 ? "#F59E0B" : "#DC2626",
                        fontWeight: "bold"
                      }}>
                        {signal.stage_confidence}
                      </Typography>
                    )}
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
                    fontSize: "0.75rem",
                  }}
                />
              </TableCell>
              <TableCell align="right">
                <Typography
                  variant="body2"
                  sx={{
                    color: signal.mansfield_rs > 0 ? "#059669" : "#DC2626",
                    fontWeight: signal.mansfield_rs !== 0 ? "bold" : "normal",
                  }}
                >
                  {signal.mansfield_rs !== null && signal.mansfield_rs !== undefined
                    ? Number(signal.mansfield_rs).toFixed(1)
                    : "—"}
                </Typography>
              </TableCell>
              <TableCell>
                <Chip
                  label={signal.volume_analysis || "Normal"}
                  size="small"
                  sx={{
                    backgroundColor:
                      signal.volume_analysis === "Pocket Pivot" ? "rgba(5, 150, 105, 0.2)" :
                      signal.volume_analysis === "Volume Surge" ? "rgba(59, 130, 246, 0.2)" :
                      signal.volume_analysis === "Volume Dry-up" ? "rgba(245, 158, 11, 0.2)" :
                      "rgba(156, 163, 175, 0.2)",
                    color:
                      signal.volume_analysis === "Pocket Pivot" ? "#059669" :
                      signal.volume_analysis === "Volume Surge" ? "#3B82F6" :
                      signal.volume_analysis === "Volume Dry-up" ? "#F59E0B" :
                      "#6B7280",
                    fontWeight: "bold",
                    fontSize: "0.7rem",
                  }}
                />
              </TableCell>
              <TableCell align="right">
                {signal.pct_from_ema_21
                  ? `${Number(signal.pct_from_ema_21).toFixed(1)}%`
                  : "—"}
              </TableCell>
              <TableCell align="right">
                {signal.rsi
                  ? Number(signal.rsi).toFixed(0)
                  : "—"}
              </TableCell>
              <TableCell align="right">
                {signal.adx
                  ? Number(signal.adx).toFixed(0)
                  : "—"}
              </TableCell>
              <TableCell align="center">
                {signal.passes_minervini_template ? (
                  <Chip
                    label="✓"
                    size="small"
                    sx={{
                      backgroundColor: "rgba(5, 150, 105, 0.2)",
                      color: "#059669",
                      fontWeight: "bold",
                    }}
                  />
                ) : (
                  <Chip
                    label="✗"
                    size="small"
                    sx={{
                      backgroundColor: "rgba(156, 163, 175, 0.2)",
                      color: "#6B7280",
                    }}
                  />
                )}
              </TableCell>
              <TableCell align="center">
                {signal.inposition ? (
                  <Chip
                    label="YES"
                    size="small"
                    sx={{
                      backgroundColor: "rgba(5, 150, 105, 0.2)",
                      color: "#059669",
                      fontWeight: "bold",
                    }}
                  />
                ) : (
                  <Chip
                    label="NO"
                    size="small"
                    sx={{
                      backgroundColor: "rgba(156, 163, 175, 0.2)",
                      color: "#6B7280",
                    }}
                  />
                )}
              </TableCell>
              <TableCell>
                <Typography variant="body2">
                  {signal.next_earnings_date
                    ? new Date(signal.next_earnings_date).toLocaleDateString()
                    : "—"}
                </Typography>
              </TableCell>
              <TableCell align="right">
                <Chip
                  label={signal.days_to_earnings || "—"}
                  size="small"
                  sx={{
                    backgroundColor:
                      signal.days_to_earnings <= 7
                        ? "rgba(220, 38, 38, 0.2)"
                        : signal.days_to_earnings <= 14
                          ? "rgba(245, 158, 11, 0.2)"
                          : "rgba(59, 130, 246, 0.2)",
                    color:
                      signal.days_to_earnings <= 7
                        ? "#DC2626"
                        : signal.days_to_earnings <= 14
                          ? "#F59E0B"
                          : "#3B82F6",
                    fontWeight: "bold",
                  }}
                />
              </TableCell>
              <TableCell align="right">
                <Typography variant="body2">
                  {signal.estimated_eps
                    ? `$${Number(signal.estimated_eps).toFixed(2)}`
                    : "—"}
                </Typography>
              </TableCell>
              <TableCell align="right">
                <Typography
                  variant="body2"
                  sx={{
                    color: signal.eps_surprise_pct
                      ? signal.eps_surprise_pct > 0
                        ? "#059669"
                        : "#DC2626"
                      : "text.secondary",
                    fontWeight: signal.eps_surprise_pct ? "bold" : "normal",
                  }}
                >
                  {signal.eps_surprise_pct
                    ? `${signal.eps_surprise_pct > 0 ? "+" : ""}${Number(signal.eps_surprise_pct).toFixed(1)}%`
                    : "—"}
                </Typography>
              </TableCell>
              <TableCell align="right">
                <Typography
                  variant="body2"
                  sx={{
                    color: signal.earnings_growth_yoy
                      ? signal.earnings_growth_yoy > 0
                        ? "#059669"
                        : "#DC2626"
                      : "text.secondary",
                    fontWeight: signal.earnings_growth_yoy ? "bold" : "normal",
                  }}
                >
                  {signal.earnings_growth_yoy
                    ? `${signal.earnings_growth_yoy > 0 ? "+" : ""}${Number(signal.earnings_growth_yoy).toFixed(1)}%`
                    : "—"}
                </Typography>
              </TableCell>
              <TableCell>
                <Typography variant="body2">
                  {signal.date
                    ? new Date(signal.date).toLocaleDateString()
                    : ""}
                </Typography>
              </TableCell>
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
                ...signalsError,
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
            (!signalsData?.data || (signalsData.data?.length || 0) === 0) && (
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
                rowsPerPageOptions={[10, 25, 50, 100]}
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
                    <TableCell align="right">RS</TableCell>
                    <TableCell align="right">Quality</TableCell>
                    <TableCell>Volume</TableCell>
                    <TableCell align="right">% from 21 EMA</TableCell>
                    <TableCell align="right">RSI</TableCell>
                    <TableCell align="right">ADX</TableCell>
                    <TableCell align="center">Trend ✓</TableCell>
                    <TableCell align="center">Status</TableCell>
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
                        <Tooltip title={`${signal.market_stage || "Unknown"}\nConfidence: ${signal.stage_confidence || 0}/100\n${signal.substage || ""}`}>
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
                            {signal.stage_confidence && (
                              <Typography variant="caption" sx={{
                                fontSize: "0.6rem",
                                color: signal.stage_confidence >= 75 ? "#059669" :
                                       signal.stage_confidence >= 60 ? "#3B82F6" :
                                       signal.stage_confidence >= 40 ? "#F59E0B" : "#DC2626",
                                fontWeight: "bold"
                              }}>
                                {signal.stage_confidence}
                              </Typography>
                            )}
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
                        <Typography
                          variant="body2"
                          sx={{
                            color: signal.mansfield_rs > 0 ? "#059669" : "#DC2626",
                            fontWeight: signal.mansfield_rs !== 0 ? "bold" : "normal",
                            fontSize: "0.75rem",
                          }}
                        >
                          {signal.mansfield_rs !== null && signal.mansfield_rs !== undefined
                            ? Number(signal.mansfield_rs).toFixed(1)
                            : "—"}
                        </Typography>
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
                      <TableCell>
                        <Chip
                          label={signal.volume_analysis || "Normal"}
                          size="small"
                          sx={{
                            backgroundColor:
                              signal.volume_analysis === "Pocket Pivot" ? "rgba(5, 150, 105, 0.2)" :
                              signal.volume_analysis === "Volume Surge" ? "rgba(59, 130, 246, 0.2)" :
                              signal.volume_analysis === "Volume Dry-up" ? "rgba(245, 158, 11, 0.2)" :
                              "rgba(156, 163, 175, 0.2)",
                            color:
                              signal.volume_analysis === "Pocket Pivot" ? "#059669" :
                              signal.volume_analysis === "Volume Surge" ? "#3B82F6" :
                              signal.volume_analysis === "Volume Dry-up" ? "#F59E0B" :
                              "#6B7280",
                            fontWeight: "bold",
                            fontSize: "0.65rem",
                          }}
                        />
                      </TableCell>
                      <TableCell align="right">
                        {signal.pct_from_ema_21
                          ? `${Number(signal.pct_from_ema_21).toFixed(1)}%`
                          : "—"}
                      </TableCell>
                      <TableCell align="right">
                        {signal.rsi
                          ? Number(signal.rsi).toFixed(0)
                          : "—"}
                      </TableCell>
                      <TableCell align="right">
                        {signal.adx
                          ? Number(signal.adx).toFixed(0)
                          : "—"}
                      </TableCell>
                      <TableCell align="center">
                        {signal.passes_minervini_template ? (
                          <Chip
                            label="✓"
                            size="small"
                            sx={{
                              backgroundColor: "rgba(5, 150, 105, 0.2)",
                              color: "#059669",
                              fontWeight: "bold",
                            }}
                          />
                        ) : (
                          <Chip
                            label="✗"
                            size="small"
                            sx={{
                              backgroundColor: "rgba(156, 163, 175, 0.2)",
                              color: "#6B7280",
                            }}
                          />
                        )}
                      </TableCell>
                      <TableCell align="center">
                        <Chip
                          label={signal.inposition ? "In Position" : "Closed"}
                          size="small"
                          color={signal.inposition ? "primary" : "default"}
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
